"""Where companions browse: the user's own browser profile (the default) or a separate companion profile, per chat.

Checks that existing users keep browsing in their own profile, that a chat started with the companion setting browses
in its own engine profile and remembers it, that a sign-in in either never shows in the other (both ways), that switching
one chat is announced and closes its pages, that clearing the companion profile is one action that leaves the user's
sign-ins alone, that two incognito windows never share a sign-in, and that incognito chats have no connected apps.

Usage: python tests/desktop/profiles.py <QA exe>
The fake AI app answers:
  TAB: <url>     opens the page with open_tab, reads it, and writes what it got to results.jsonl
  TOOLS          writes the tool names Still offers it, and what list_connected_plugins says, to results.jsonl
"""
import http.server
import json
import os
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

from mcp_client import Mcp, call_async  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("profiles-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}
VISITS = []  # (path, cookie header) for every request the test site gets


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        cookie = self.headers.get("Cookie") or ""
        VISITS.append((self.path, cookie))
        extra = []
        if url.path == "/signin":  # /signin?as=<who>: signs this profile in as <who>
            who = query.get("as", ["someone"])[0]
            body, extra = f"<title>Signed in {who}</title><h1>Welcome {who}</h1>", [("Set-Cookie", f"still_qa={urllib.parse.quote(who)}; Path=/; Max-Age=86400")]
        else:  # /whoami: who this profile is signed in as
            who = next((c.split("=", 1)[1] for c in cookie.split("; ") if c.startswith("still_qa=")), "")
            title = f"Signed in as {who}" if who else "Signed out"
            body = f"<title>{title}</title><h1>{title}</h1>"
        data = ("<!doctype html><meta charset=utf-8>" + body).encode()
        self.send_response(200)
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
SITE = f"http://127.0.0.1:{SERVER.server_port}"

FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    last = next((l for l in reversed(prompt.strip().splitlines()) if l.split(": ")[0] in ("TAB", "TOOLS", "HI")), "")
    verb, _, rest = last.partition(": ")
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if verb in ("TAB", "TOOLS"):
        server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
        still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        n = 0
        def request(method, params):
            global n
            n += 1
            still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params}) + "\n").encode()); still.stdin.flush()
            for line in still.stdout:
                try: m = json.loads(line)
                except ValueError: continue
                if m.get("id") == n: return m
        request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
        still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
        out = {"verb": verb, "arg": rest}
        def call(key, tool, arguments):
            r = request("tools/call", {"name": tool, "arguments": arguments})["result"]
            out[key] = {"error": bool(r.get("isError")), "text": r["content"][0].get("text", "")}
        if verb == "TAB":
            call("open_tab", "open_tab", {"url": rest})
            time.sleep(.5)
            call("read_page", "read_page", {})
        else:
            out["tools"] = [t["name"] for t in request("tools/list", {})["result"]["tools"]]
            call("plugins", "list_connected_plugins", {})
        with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(out) + "\n")
        still.stdin.close()
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay."}]}})
''')


def results():
    file = BIN / "results.jsonl"
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def prompts():
    file = BIN / "prompts.jsonl"
    return [json.loads(l)["prompt"] for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def window(p, wid, op="state", **args):
    return rpc(p, op, window=wid, **args)


def wsend(p, wid, op, **args):
    window(p, wid, "shellEval", script="window.chrome.webview.postMessage(" + json.dumps({"op": op, **args}) + ")")


def open_incognito(p):
    before = {w["id"] for w in rpc(p)["windows"]}
    send(p, "incognitoWindow")
    wid = until(lambda: next((w["id"] for w in rpc(p)["windows"] if w["incognito"] and w["id"] not in before), None), 15)
    until(lambda: window(p, wid, "shellEval", script="!!document.querySelector('.home-compose [aria-label=Message]')"), 15)
    return wid


def run_tab(p, url, chat=None, wid=None, **extra):
    """Has a chat's AI open url; returns (what read_page said, the agent tab's state)."""
    n = len(results())
    if wid:
        wsend(p, wid, "aiSend", text=f"TAB: {url}", companion="maya", home=True, **extra)
    elif chat:
        send(p, "chatOpen", id=chat)  # the Still tab shows the chat, so the message goes to it
        until(lambda: next((t for t in rpc(p)["tabs"] if t.get("ChatId") == chat), None) and js(p, "!!document.querySelector('.chat-view [aria-label=Message]')"), 10)
        send(p, "aiSend", text=f"TAB: {url}", **extra)
    else:
        new_chat(p)
        send(p, "aiSend", text=f"TAB: {url}", companion="maya", home=True, **extra)
    said = until(lambda: len(results()) > n and results()[-1], 60) or {}
    tabs = (window(p, wid) if wid else rpc(p))["tabs"]
    tab = until(lambda: next((t for t in (window(p, wid) if wid else rpc(p))["tabs"] if t["Url"] == url and not t.get("Loading")), None), 10) or {}
    return said.get("read_page", {}).get("text", ""), tab


def new_chat(p):
    """A new tab's message box: a message sent there starts a new chat (from a chat's tab it goes to that chat)."""
    send(p, "new")
    until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")


def page_says(p, url, wid=None):
    """Opens url as the user's own tab and returns its title once loaded."""
    (wsend(p, wid, "new", url=url) if wid else send(p, "new", url=url))
    tab = until(lambda: next((t for t in (window(p, wid) if wid else rpc(p))["tabs"] if t["Url"] == url and not t.get("Loading") and t["Title"] not in ("", "New tab", url)), None), 10) or {}
    return tab.get("Title", ""), tab


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    allow = [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate", "interact")]
    # A chat from before this setting existed: no profile saved with it.
    old = {"Id": "oldchat", "Title": "An older chat", "Harness": "fake", "Companion": "maya", "Started": True, "Messages": [
        {"Role": "user", "Text": "HI: hello"}, {"Role": "assistant", "Text": "Okay.", "Who": "maya"}]}
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([old]), encoding="utf-8")
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake",
        "Permissions": allow, "Theme": "Light"}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")

        # The user signs in to the test site in their own profile.
        title, mine = page_says(p, SITE + "/signin?as=regular")
        check(title == "Signed in regular" and mine.get("engineProfile") == "Default", "The user's own tab signs in, in the regular engine profile")

        # By default a companion browses in the user's own profile, as before.
        text, tab = run_tab(p, SITE + "/whoami?p=default")
        check("Signed in as regular" in text and tab.get("engineProfile") == "Default", "By default a companion's tab is in the user's own profile and signed in")
        first = next((c for c in chats() if c["Title"].startswith("TAB") or "p=default" in json.dumps(c)), {})
        check(first.get("Profile") in (None, "regular"), "and the chat keeps that profile")

        # The setting: new chats browse in the companion profile.
        send(p, "preference", key="agentProfile", value="companion")
        text, tab = run_tab(p, SITE + "/whoami?p=companion1")
        check("Signed out" in text and tab.get("engineProfile") == "Companion", "With the companion profile, a new chat's tab is in its own engine profile, signed out")
        comp = next((c for c in chats() if "p=companion1" in json.dumps(c)), {})
        check(comp.get("Profile") == "companion", "The chat remembers the companion profile")
        check(any("companion profile" in x.lower() for x in prompts()[-1:]), "Its prompt tells the AI it's in the companion profile")
        text, _ = run_tab(p, SITE + "/signin?as=helper", chat=comp.get("Id"))
        check("Welcome helper" in text, "A companion signs in in its profile")
        title, _ = page_says(p, SITE + "/whoami?p=mine2")
        check(title == "Signed in as regular", "The companion's sign-in never shows in the user's profile")
        text, _ = run_tab(p, SITE + "/whoami?p=companion2", chat=comp.get("Id"))
        check("Signed in as helper" in text, "and the user's sign-in never shows in the companion's")
        check(not any("still_qa=regular" in c for path, c in VISITS if "p=companion" in path), "No regular cookie is ever sent from the companion profile")

        # The profile keeps the AI out of the user's tabs too: not listed, not named in its prompt, not usable by id.
        _, own = page_says(p, SITE + "/whoami?p=mine-kept")
        n = len(results())
        send(p, "aiSend", text=f"TAB: {SITE}/whoami?p=companion-kept", companion="maya")  # from the user's tab, in the side chat
        until(lambda: len(results()) > n, 60)
        told = prompts()[-1]
        check("you stay out of" in told and "p=mine-kept" not in told and own["Id"] not in told, f"A companion-profile chat isn't told about the user's own tab ({told[-160:]!r})")
        probe = Mcp(EXE, "Probe", PROFILE)
        try:
            pending = call_async(probe, "list_tabs")
            until(lambda: "Probe" in (js(p, "document.body.innerText") or ""), 30)
            send(p, "agentAnswer", allow=True)
            pending.get(timeout=60)
            ok, listed = probe.call("list_tabs", seconds=30)
            check(ok and "p=mine-kept" not in listed and "p=companion-kept" in listed, "Its tab list has only the companion profile's tabs")
            ok, said = probe.call("read_page", tabId=own["Id"], seconds=30)
            check(not ok and "own browser profile" in said and "regular" not in said, "It can't read the user's own tab by its id")
            ok, said = probe.call("click", tabId=own["Id"], selector="body", seconds=30)
            check(not ok and "own browser profile" in said, "...or act in it")
        finally:
            probe.close()

        # A chat from before keeps the user's profile, whatever the setting.
        text, tab = run_tab(p, SITE + "/whoami?p=old", chat="oldchat")
        check("Signed in as regular" in text and tab.get("engineProfile") == "Default", "An older chat keeps browsing in the user's profile")

        # Switching one chat is said in the chat and to the AI, and closes its pages.
        before = [t for t in rpc(p)["tabs"] if (t.get("InChat") or t.get("RunChat")) == "oldchat"]
        send(p, "aiChatProfile", id="oldchat", profile="companion")
        notice = until(lambda: next((m["Text"] for c in chats() if c["Id"] == "oldchat" for m in c["Messages"] if m["Role"] == "note" and "companion profile" in m["Text"]), None), 5)
        check(before and notice, "Switching a chat's profile says so in the chat")
        check(until(lambda: not any((t.get("InChat") or t.get("RunChat")) == "oldchat" for t in rpc(p)["tabs"]), 5), "and closes the pages it opened in the old profile")
        chip = until(lambda: js(p, "document.querySelector('.chat-profile')?.innerText"), 5) or ""
        check("Companion profile" in chip, "The chat shows its profile: " + chip)
        js(p, "document.querySelector('.chat-profile')?.click()")
        time.sleep(.6)
        rpc(p, "capture", name="profile-chip.png")
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        text, tab = run_tab(p, SITE + "/whoami?p=old2", chat="oldchat")
        check("Signed in as helper" in text and tab.get("engineProfile") == "Companion", "Its next page is in the companion profile")
        check("browse in the companion profile" in prompts()[-1] and "sign" in prompts()[-1], "and the AI is told before it acts")

        # Clearing the companion profile: one action, the user's sign-ins stay.
        send(p, "clearCompanionData")
        time.sleep(1.5)
        text, _ = run_tab(p, SITE + "/whoami?p=companion3", chat=comp.get("Id"))
        check("Signed out" in text, "Clearing the companion profile signs companions out")
        title, _ = page_says(p, SITE + "/whoami?p=mine3")
        check(title == "Signed in as regular", "and the user stays signed in")

        # Two incognito windows never share a sign-in.
        main = next(w["id"] for w in rpc(p)["windows"] if not w["incognito"])
        w1, w2 = open_incognito(p), open_incognito(p)
        title1, t1 = page_says(p, SITE + "/signin?as=one", wid=w1)
        title2, t2 = page_says(p, SITE + "/whoami?p=two", wid=w2)
        check(title1 == "Signed in one" and title2 == "Signed out", "A sign-in in one incognito window never shows in another")
        check(MAC or t1.get("engineProfile") and t1.get("engineProfile") != t2.get("engineProfile"), "Each incognito window has its own private engine profile")
        title3, _ = page_says(p, SITE + "/whoami?p=mine4", wid=main)
        check(title3 == "Signed in as regular", "and neither reaches the user's own profile")

        # Incognito: no profile choice, no connected apps.
        n = len(results())
        wsend(p, w1, "aiSend", text="TOOLS", companion="maya", home=True)
        said = until(lambda: len(results()) > n and results()[-1], 60) or {}
        offered = said.get("tools", [])
        check(offered and not any(t in offered for t in ("list_connected_plugins", "find_plugins", "get_plugin_tools", "run_plugin_action")), "An incognito chat isn't offered connected apps")
        check(said.get("plugins", {}).get("error") and "incognito" in said.get("plugins", {}).get("text", ""), "and calling one anyway is refused: " + said.get("plugins", {}).get("text", "")[:80])
        note = until(lambda: window(p, w1, "shellEval", script="document.querySelector('.chat-incognito')?.innerText"), 10) or ""
        check("Connected apps are off" in note, "The incognito chat says connected apps are off")
        check(not window(p, w1, "shellEval", script="!!document.querySelector('.chat-profile')"), "and shows no profile choice")
        agent = until(lambda: next((t for t in window(p, w1)["tabs"] if t.get("InChat") or t.get("RunChat")), None), 2)
        check(not agent or agent.get("engineProfile") not in ("Default", "Companion"), "Its pages never use either persistent profile")
        for w in (w1, w2):
            rpc(p, "closeWindow", id=w)
        until(lambda: len(rpc(p)["windows"]) == 1, 10)
        n = len(results())
        new_chat(p)
        send(p, "aiSend", text="TOOLS", companion="maya", home=True)
        said = until(lambda: len(results()) > n and results()[-1], 60) or {}
        check("run_plugin_action" in said.get("tools", []), "A regular chat still has connected apps' tools")

        # The Settings page.
        send(p, "openPanel", name="settings")
        until(lambda: js(p, "!!document.querySelector('.set-shell')"), 10)
        js(p, "[...document.querySelectorAll('.set-nav-item')].find(t => t.innerText.trim() === 'Privacy & permissions')?.click()")
        picked = until(lambda: js(p, "document.querySelector('#set-agentProfile [role=combobox]')?.innerText"), 5) or ""
        check(picked.strip() == "Companion profile", "Settings has Where companions browse, set to the companion profile: " + picked)
        check(js(p, "!!document.querySelector('#set-clearCompanion button')"), "and a Clear button for the companion profile")
        js(p, "document.querySelector('#set-agentProfile')?.scrollIntoView({block: 'center'})")
        time.sleep(.5)
        rpc(p, "capture", name="profile-settings.png")
        errors = rpc(p).get("shellErrors") or []
        check(not errors, "No interface errors" + (f": {errors[:1]}" if errors else ""))
    finally:
        try:
            rpc(p, "quit")
            p.wait(timeout=20)
        except Exception:
            p.kill()
    passed = sum(c["passed"] for c in RESULT["checks"])
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=1))
    print(("PASSED" if passed == len(RESULT["checks"]) else "FAILED") + f" {passed}/{len(RESULT['checks'])} -> {RUN}")
    sys.exit(0 if passed == len(RESULT["checks"]) else 1)


if __name__ == "__main__":
    main()
