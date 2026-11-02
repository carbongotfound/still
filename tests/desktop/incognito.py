"""Incognito chats are ephemeral: nothing from one reaches the profile folder, its AI browses and looks things up in the
private engine profile (never with the regular profile's cookies), memory, knowledge, routines and saved files are
refused, closing the window stops the run and deletes its files, and a crash leaves nothing to resume.
No AI plan is used: a fake AI app (a manifest in Still's agents folder) connects to Still's MCP server and runs the
command on the last line of its prompt:
  RUN: <phrase> | <a regular tab's id>   calls every tool below and writes what each said to results.jsonl
  SLOW: <words>                           writes its process id to pids.txt and waits two minutes
  HI: <words>                             just answers

Run: python tests/desktop/incognito.py artifacts/Still-QA/Still.exe
Out: artifacts/incognito-*/ (incognito-chat.png)
"""
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, alive, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("incognito-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}
STARTED = time.time()
# The engine's own data: WebView2 keeps it in the profile; WebKit keeps the QA build's in ~/Library (only files changed
# since this test started are read there).
ENGINE = [Path.home() / "Library" / d / "com.carbongotfound.still.qa" for d in ("WebKit", "Caches", "HTTPStorages")] if MAC else []
PHRASE = "Zanzibar" + uuid.uuid4().hex[:10]  # appears nowhere but in the incognito chat
VISITS = []  # (path, cookie header) for every request the test site gets


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        cookie = self.headers.get("Cookie") or ""
        VISITS.append((self.path, cookie))
        extra = []
        if url.path == "/signin":
            body, extra = "<title>Signed in</title><h1>Welcome back</h1>", [("Set-Cookie", "still_qa=regular; Path=/; Max-Age=86400")]
        elif url.path == "/search":
            body = '<title>Results</title><div class="result"><h2><a class="result__a" href="/whoami?from=search">Who am I</a></h2><a class="result__snippet">A page that says who you are.</a></div>'
        else:  # /whoami: says whether the regular profile's sign-in came along
            who = "Signed in as regular" if "still_qa=regular" in cookie else "Signed out"
            body = f"<title>{who}</title><h1>{who}</h1>"
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
    import json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt, "cwd": os.getcwd()}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    last = next((l for l in reversed(prompt.strip().splitlines()) if l.split(": ")[0] in ("RUN", "SLOW", "HI")), "")  # notes can follow it
    verb, _, rest = last.partition(": ")
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if verb == "SLOW":
        with open(os.path.join(here, "pids.txt"), "a") as f: f.write("%d %s\n" % (os.getpid(), rest))
        time.sleep(120); sys.exit(0)
    if verb == "RUN":
        site = os.environ.get("STILL_QA_SITE", "")
        phrase, _, user_tab = rest.partition(" | ")
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
        out = {}
        def call(key, tool, arguments):
            r = request("tools/call", {"name": tool, "arguments": arguments})["result"]
            out[key] = {"error": bool(r.get("isError")), "text": r["content"][0].get("text", "")}
        call("open_tab", "open_tab", {"url": site + "/whoami?p=agent"})
        call("read_page", "read_page", {})
        call("list_tabs", "list_tabs", {})
        call("user_tab", "read_page", {"tabId": user_tab})
        call("remember", "remember", {"fact": phrase, "kind": "preference"})
        call("update_knowledge", "update_knowledge", {"file": "findings", "text": phrase})
        call("forget", "forget", {"about": "anything"})
        call("save_file", "save_file", {"name": "notes.md", "content": phrase})
        call("offer_routine", "offer_routine", {"text": phrase, "time": "09:00"})
        call("web_search", "web_search", {"query": phrase})
        call("read_url", "read_url", {"url": site + "/whoami?p=lookup"})
        found = re.search(r"id ([0-9a-f]{16})", prompt)
        if found: call("read_attachment", "read_attachment", {"id": found.group(1)})
        with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(out) + "\n")
        still.stdin.close()
        say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done with " + phrase + "."}]}})
        print("failed on " + phrase, file=sys.stderr, flush=True)
        sys.exit(3)  # a failed run: Still keeps a log of it
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay."}]}})
''')


def lines(name):
    file = BIN / name
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def pids():
    file = BIN / "pids.txt"
    return [(int(l.split()[0]), l.split(" ", 1)[1]) for l in file.read_text().splitlines()] if file.exists() else []


def chats_file():
    try:
        return (PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")
    except OSError:
        return ""


def snapshot():
    """What an incognito chat must leave as it was: the saved chats, memory, knowledge, attachments, the AI apps'
    folders and logs, the library and the error log."""
    out = {}
    for rel in ["ai/chats.json", "ai/attachments", "ai/chats", "companions", "library", "errors.log"]:
        p = PROFILE / rel
        for f in ([p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file()) if p.exists() else []):
            out[str(f.relative_to(PROFILE))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def found_phrase(skip=None, also=()):
    """Files under the profile holding the phrase (as UTF-8 or UTF-16), and how many couldn't be read (in use)."""
    hits, locked = [], 0
    needles = [PHRASE.encode(), PHRASE.encode("utf-16-le")]
    for f in [*PROFILE.rglob("*"), *(f for d in also if d.exists() for f in d.rglob("*") if f.is_file() and f.stat().st_mtime >= STARTED)]:
        if not f.is_file() or skip and str(f).startswith(skip):
            continue
        try:
            data = f.read_bytes()
        except OSError:
            locked += 1
            continue
        if any(n in data for n in needles):
            hits.append(str(f.relative_to(PROFILE)) if f.is_relative_to(PROFILE) else str(f))
    return hits, locked


def window(p, wid, op="state", **args):
    return rpc(p, op, window=wid, **args)


def wsend(p, wid, op, **args):
    """Posts a message to the native side from that window's interface."""
    window(p, wid, "shellEval", script="window.chrome.webview.postMessage(" + json.dumps({"op": op, **args}) + ")")


def open_incognito(p):
    before = {w["id"] for w in rpc(p)["windows"]}
    send(p, "incognitoWindow")
    wid = until(lambda: next((w["id"] for w in rpc(p)["windows"] if w["incognito"] and w["id"] not in before), None), 15)
    until(lambda: window(p, wid, "shellEval", script="document.body.innerText.length > 0"), 15)
    return wid


def main():
    crashed, folder3 = None, RUN / "none"
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    allow = [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate", "interact")]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": [{**c, "Crew": "research"} if c["Id"] == "maya" else c for c in CREW], "AgentsEnabled": True, "AiHarness": "fake",
        "Permissions": allow}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "STILL_QA_SEARCH": SITE + "/search?q=", "STILL_QA_SITE": SITE}
    p = launch(EXE, PROFILE, env)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)

        # The regular profile is signed in to the test site, and a regular chat is saved.
        send(p, "new", url=SITE + "/signin")
        until(lambda: any(t["Title"] == "Signed in" for t in rpc(p)["tabs"]), 10)
        send(p, "new", url=SITE + "/whoami?p=regular")
        regular = until(lambda: next((t for t in rpc(p)["tabs"] if t["Title"] == "Signed in as regular"), None), 10)
        check(regular and regular["engineProfile"] == "Default" and not regular["enginePrivate"], "A regular tab is signed in, in the regular engine profile")
        send(p, "aiSend", text="HI: a regular chat", companion="maya")
        until(lambda: "a regular chat" in chats_file() and '"Running":false' in chats_file(), 20)
        js(p, "localStorage.setItem('still.qa.probe', '1')")
        before = snapshot()
        check(before.get("ai\\chats.json") or before.get("ai/chats.json"), "The regular chat is saved in chats.json")

        # An incognito chat: an attachment, every tool, a failed run.
        w = open_incognito(p)
        check(w and window(p, w)["incognitoFolder"].startswith(str(PROFILE / "ai" / "incognito")), "An incognito window has its own folder under ai/incognito")
        folder = Path(window(p, w)["incognitoFolder"])
        wsend(p, w, "aiAttach", to="box", name="secret.txt", data=base64.b64encode(PHRASE.encode()).decode())
        attached = until(lambda: next(iter((folder / "attachments").glob("*")), None), 10)
        check(attached and (attached / "secret.txt").read_text() == PHRASE, "An attachment goes to the window's folder")
        wsend(p, w, "aiSend", text=f"RUN: {PHRASE} | {regular['Id'] if regular else ''}", companion="maya", home=True, files=[attached.name if attached else ""])
        said = until(lambda: lines("results.jsonl") and lines("results.jsonl")[-1], 60) or {}
        state = until(lambda: (s := window(p, w)) and s["privateChats"] and not any(t.get("Loading") for t in s["tabs"]) and s, 10) or window(p, w)
        chat = (state.get("privateChats") or [""])[0]
        check(chat and chat not in chats_file() and PHRASE not in chats_file(), "The incognito chat lives in its window, never in chats.json")
        check(chat not in rpc(p).get("privateChats", []) and chat not in json.dumps(rpc(p).get("interrupted", [])), "A regular window never has it")
        prompt = lines("prompts.jsonl")[-1]
        check(prompt["cwd"].startswith(str(folder)), "The AI app runs in the window's folder")
        check("incognito chat" in prompt["prompt"] and "Active tab:" not in prompt["prompt"] and SITE + "/whoami?p=regular" not in prompt["prompt"], "Its prompt says so and names none of the user's tabs")

        agent = next((t for t in state["tabs"] if "whoami?p=agent" in t["Url"]), None)
        check(not said.get("open_tab", {}).get("error") and agent and agent["Private"] and agent["enginePrivate"] is True and agent["engineProfile"] != "Default",
              "Its agent tab is private, in the private engine profile")
        check("Signed out" in said.get("read_page", {}).get("text", ""), "and isn't signed in: no cookies from the regular profile")
        agent_visits = [c for path, c in VISITS if "p=agent" in path or "p=lookup" in path or path.startswith("/search")]
        check(len(agent_visits) >= 3 and not any("still_qa=regular" in c for c in agent_visits), "Its tab, web_search and read_url never send the regular profile's cookies")
        check("Signed out" in said.get("read_url", {}).get("text", "") and not said.get("web_search", {}).get("error"), "Lookups run in the private profile too")
        listed = said.get("list_tabs", {}).get("text", "")
        check("p=agent" in listed and "p=regular" not in listed and "/signin" not in listed, "list_tabs shows only its own tabs")
        check(said.get("user_tab", {}).get("error") and "only uses the tabs it opened" in said.get("user_tab", {}).get("text", ""), "The user's regular tab is off-limits to it")
        for tool in ("remember", "update_knowledge", "forget", "save_file", "offer_routine"):
            r = said.get(tool, {})
            check(r.get("error") and "incognito chat" in r.get("text", ""), f"{tool} is refused with a clear error")
        check(PHRASE in said.get("read_attachment", {}).get("text", ""), "read_attachment reads the window's attachment")
        logs = list(folder.rglob("logs/*.log"))
        check(logs and PHRASE in logs[0].read_text(encoding="utf-8", errors="replace"), "The failed run's log is kept in the window's folder")

        # The chat says what still leaves the machine, and keeps no draft on disk.
        note = until(lambda: window(p, w, "shellEval", script="document.querySelector('.chat-incognito')?.innerText"), 10) or ""
        check("keeps nothing" in note and "still get what's sent to them" in note and "own record" in note, "The chat says what Still keeps and what the AI and sites still get")
        check(not window(p, w, "shellEval", script="!!document.querySelector('.chat-memory')"), "and has no Don't remember switch")
        window(p, w, "capture", name="incognito-chat.png")
        box = "[aria-label=Message]"
        window(p, w, "shellEval", script=f"(() => {{ const e = document.querySelector({json.dumps(box)}); if (!e) return false; e.focus(); document.execCommand('insertText', false, {json.dumps(PHRASE + ' draft')}); return true }})()")
        time.sleep(.5)
        drafts = js(p, "JSON.stringify(Object.entries(localStorage))") or ""
        check("still.qa.probe" in drafts and PHRASE not in drafts, "A draft typed in the incognito chat stays out of the interface's storage")

        hits, locked = found_phrase(str(folder))
        after = snapshot()
        changed = sorted(k for k in {*before, *after} if before.get(k) != after.get(k))
        check(not changed, "chats.json, memory, knowledge, attachments, AI folders, logs and the library are unchanged" + (f" ({changed})" if changed else ""))
        check(not hits, "Outside the window's folder, the phrase is nowhere in the profile" + (f" ({hits})" if hits else "") + f" [{locked} files in use, unread]")

        # Closing the window deletes its folder.
        rpc(p, "closeWindow", id=w)
        check(until(lambda: not folder.exists(), 15), "Closing the window deletes its folder")
        hits, locked = found_phrase()
        check(not hits, "After closing, the phrase is nowhere in the profile" + (f" ({hits})" if hits else "") + f" [{locked} files in use, unread]")

        # Closing it mid-run stops the run and kills the AI app.
        w2 = open_incognito(p)
        folder2 = Path(window(p, w2)["incognitoFolder"])
        wsend(p, w2, "aiSend", text="SLOW: closing", companion="maya", home=True)
        pid = until(lambda: next((n for n, why in pids() if why == "closing"), None), 20)
        check(pid and alive(pid) and folder2.exists(), "A run in an incognito window is working")
        rpc(p, "closeWindow", id=w2)
        check(pid and until(lambda: not alive(pid), 10), "Closing the window kills its AI app")
        check(until(lambda: not folder2.exists(), 15), "and deletes the window's folder")

        # A crash mid-run: the regular chat is offered again, the incognito one is gone.
        send(p, "aiSend", text="SLOW: regular", companion="maya", home=True)
        w3 = open_incognito(p)
        folder3 = Path(window(p, w3)["incognitoFolder"])
        wsend(p, w3, "aiSend", text=f"SLOW: crash {PHRASE}", companion="maya", home=True)
        crashed = until(lambda: next((n for n, why in pids() if why.startswith("crash")), None), 20)
        until(lambda: next((n for n, why in pids() if why == "regular"), None), 20)
        check(crashed and folder3.exists() and PHRASE not in chats_file() and '"Running":true' in chats_file(), "Mid-run, only the regular chat is saved as running")
    finally:
        try:
            p.kill(); p.wait(timeout=20)  # a crash
        except Exception:
            pass
    check(crashed and until(lambda: not alive(crashed), 10), "A crash takes the incognito run's AI app with it")
    check(folder3.exists(), "The crash left the incognito folder behind")
    p = launch(EXE, PROFILE, env)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        interrupted = until(lambda: rpc(p).get("interrupted"), 10) or []
        check(len(interrupted) == 1 and interrupted[0] in chats_file() and "SLOW: regular" in chats_file(), "After the crash, only the regular chat is offered to resume")
        check(until(lambda: not folder3.exists(), 10), "and the next start deletes the incognito leftovers")
        hits, locked = found_phrase()
        check(not hits, "The phrase is nowhere in the profile" + (f" ({hits})" if hits else "") + f" [{locked} files in use, unread]")
        errors = rpc(p).get("shellErrors") or js(p, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        send(p, "aiResumeDismiss")
        rpc(p, "quit")
        p.wait(timeout=20)
    for n, _ in pids():
        if alive(n):
            os.kill(n, 9)
    hits, _ = found_phrase(also=ENGINE)
    check(not hits, "With Still closed, the phrase is nowhere in the profile or the engine's data" + (f" ({hits})" if hits else ""))


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
