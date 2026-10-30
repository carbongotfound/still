"""Plugins through Composio, against a local stand-in for Composio's API (STILL_QA_COMPOSIO points test builds at it).
A fake AI app plays a companion that uses them.

  NOPLUG       looks for Gmail's tools and runs one, with no key
  READMAIL     finds Gmail's tools, then reads mail (a read: no card)
  SENDMAIL     sends an email (a write: a card, Deny or Allow once)
  SLACK        posts in Slack, which isn't connected (a card that connects it, then the write's card)
  PEEK         writes down its environment and Still's tool list, looking for the key
  WEB <site>   opens a page (the browser still works when Composio doesn't)

The stand-in answers like Composio's v3.1 API: x-api-key takes a project key (ak_) and nothing else, so the Connect key
(ck_) that Composio's For You page hands out gets a 401, as it does there; lists come paged ({items, next_cursor, ...});
errors are { error: { message, code, slug, status, ... } }; connected accounts don't echo user_id back.

Checks: plugins live in Skills & plugins (Settings only links there, a companion's profile has no Plugins tab); with no
key the plugin list still loads, every app marked Needs a key, under a step that says where the key comes from (Platform
→ Settings → Project Settings → API Keys, ak_) and where to paste it; a Connect key (ck_) is named as the wrong kind and
never sent or kept; off with no key and nothing else breaks; a bad key isn't kept; a good one is kept encrypted (DPAPI on
Windows, the Keychain on the Mac) and never reaches a file in the clear, the interface, an agent, its tools or its
environment; with a key the list loads from Composio, and an error says why instead of an empty list; the Composio
connect flow: Connect opens Composio's sign-in in a Still window, which closes when it's done, and a connect Composio
refuses shows on that app; reads go ahead, writes ask (Deny or Allow once, nothing else); per-companion switches, on the
page and in the profile; a missing app offers a button that connects it; Composio down; Disconnect; Remove key. Then
setup's Connect your tools step with a key: the belt turns into a grid, a tap connects Gmail, and Zest, who works in it,
bounces and says so.

Run: python tests/desktop/plugins.py artifacts/Still-QA/Still.exe
"""
import http.server
import json
import os
from pathlib import Path
import shutil
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("plugins-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}
KEY = "ak_test_" + uuid.uuid4().hex  # a project key nobody else knows: it's looked for everywhere it mustn't be
WRONG = "ak_wrong_" + uuid.uuid4().hex[:12]  # a key Composio refuses
CONSUMER = "ck_" + uuid.uuid4().hex[:22]  # what Composio's For You → Sessions & API Key page shows: for its MCP endpoint, not the API
MOCK = {"down": False, "broken": False, "refuse_config": False, "accounts": {}, "configs": {}, "executed": [], "deleted": [], "seen": [], "pages": []}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


KIT = lambda slug, name, about, managed=("OAUTH2",): {"slug": slug, "name": name, "type": "native", "auth_schemes": ["OAUTH2"], "composio_managed_auth_schemes": list(managed),
    "is_local_toolkit": False, "no_auth": False, "auth_guide_url": None, "deprecated": {"toolkitId": "tk_" + slug},
    "meta": {"description": about, "logo": f"https://logos.composio.dev/api/{slug}", "categories": [], "tools_count": 20, "triggers_count": 2, "version": "20260101_00", "app_url": None, "created_at": "2025-01-01", "updated_at": "2026-01-01"}}
TOOLKITS = [KIT("gmail", "Gmail", "Read, send and organize your email."), KIT("googlecalendar", "Google Calendar", "Events, invites and free time."),
            KIT("slack", "Slack", "Channels and messages."), KIT("selfhosted", "Self Hosted Thing", "Needs your own developer app.", ())]
PAGE = lambda items: {"items": items, "next_cursor": None, "total_pages": 1, "current_page": 1, "total_items": len(items)}  # how v3.1 lists come
ERR = lambda status, message, slug: {"error": {"message": message, "code": status * 10, "slug": slug, "status": status, "request_id": str(uuid.uuid4()), "suggested_fix": ""}}
SEEN = lambda account: {k: v for k, v in account.items() if not k.startswith("_")}  # user_id is kept, not sent back (deprecated in v3.1)
SCHEMA = lambda *names: {"type": "object", "properties": {n: {"type": "string", "description": "The " + n} for n in names}, "required": list(names[:1])}
TOOLS = {
    "GMAIL_FETCH_EMAILS": {"name": "Fetch emails", "description": "Fetch emails from the inbox.", "toolkit": "gmail", "input_parameters": SCHEMA("query")},
    "GMAIL_SEND_EMAIL": {"name": "Send email", "description": "Send an email.", "toolkit": "gmail", "input_parameters": SCHEMA("to", "subject", "body")},
    "SLACK_SEND_MESSAGE": {"name": "Send message", "description": "Post a message in a channel.", "toolkit": "slack", "input_parameters": SCHEMA("channel", "text")},
}
tool = lambda slug: {"slug": slug, **{k: v for k, v in TOOLS[slug].items() if k != "toolkit"}, "toolkit": {"slug": TOOLS[slug]["toolkit"], "name": next(t["name"] for t in TOOLKITS if t["slug"] == TOOLS[slug]["toolkit"])}, "tags": []}
ALLOW = """<!doctype html><meta charset=utf-8><title>Connect %s</title><style>body{font:15px system-ui;margin:60px auto;max-width:420px;text-align:center}button{font:inherit;padding:10px 22px;border-radius:10px}</style>
<h1>Let Composio use your %s?</h1><p>Still will be able to read and, when you say so, send.</p><button id=allow onclick="fetch(location.pathname + '/allow', {method: 'POST'}).then(() => document.body.innerHTML = '<h1>Connected</h1><p>You can close this window.</p>')">Allow</button>"""


class Composio(http.server.BaseHTTPRequestHandler):
    def do_GET(self): self.route("GET")
    def do_POST(self): self.route("POST")
    def do_DELETE(self): self.route("DELETE")

    def route(self, method):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        parts = url.path.strip("/").split("/")
        if parts[0] in ("oauth", "page"):  # pages a browser opens: Composio's sign-in, and a plain page
            MOCK["pages"].append({"path": url.path, "key": self.headers.get("x-api-key")})
            if parts[0] == "page":
                return self.send(200, "<!doctype html><title>A page</title><p>Still works.", "text/html")
            account = MOCK["accounts"].get(parts[1])
            if method == "POST" and account:
                account["status"] = "ACTIVE"
                return self.send(200, {})
            name = next((t["name"] for t in TOOLKITS if account and t["slug"] == account["toolkit"]["slug"]), "account")
            return self.send(200, ALLOW % (name, name), "text/html")
        key = self.headers.get("x-api-key")
        MOCK["seen"].append({"method": method, "path": url.path, "key": key})
        if not key:
            return self.send(401, ERR(401, "No authentication provided", "Auth_NoAuthProvided"))
        if key != KEY:  # Composio's API only takes a project key here: a Connect (ck_) or personal (uak_) key is refused too
            return self.send(401, ERR(401, "Invalid API key", "Auth_InvalidApiKey"))
        if MOCK["down"]:
            return self.send(503, ERR(503, "Service unavailable", "Internal_ServiceUnavailable"))
        path = parts[2:]  # after api/v3.1
        if path == ["toolkits"]:
            if MOCK["broken"]:
                return self.send(400, ERR(400, "Invalid value for sort_by", "Request_InvalidQuery"))
            s = q.get("search", "").lower()
            return self.send(200, PAGE([t for t in TOOLKITS if s in (t["name"] + " " + t["slug"] + " " + t["meta"]["description"]).lower()]))
        if path == ["auth_configs"] and method == "GET":
            return self.send(200, PAGE([c for c in MOCK["configs"].values() if c["toolkit"]["slug"] in q.get("toolkit_slug", "").split(",")]))
        if path == ["auth_configs"] and method == "POST":
            slug = body["toolkit"]["slug"]
            if MOCK["refuse_config"]:
                return self.send(400, ERR(400, "Composio managed auth isn't available for this toolkit", "AuthConfig_ManagedAuthUnavailable"))
            MOCK["configs"]["ac_" + slug] = {"id": "ac_" + slug, "status": "ENABLED", "is_composio_managed": body["auth_config"]["type"] == "use_composio_managed_auth", "toolkit": {"slug": slug}}
            return self.send(201, {"toolkit": {"slug": slug}, "auth_config": {"id": "ac_" + slug, "auth_scheme": "OAUTH2"}})
        if path == ["connected_accounts", "link"]:
            config = MOCK["configs"][body["auth_config_id"]]
            cid = "ca_%d" % (len(MOCK["accounts"]) + 1)
            MOCK["accounts"][cid] = {"id": cid, "status": "INITIATED", "status_reason": None, "is_disabled": False, "toolkit": {"slug": config["toolkit"]["slug"]}, "_user": body["user_id"],
                                     "auth_config": {"id": config["id"], "auth_scheme": "OAUTH2", "is_composio_managed": True, "is_disabled": False}, "word_id": None, "alias": None}
            return self.send(201, {"link_token": "lt", "redirect_url": f"{SITE}/oauth/{cid}", "expires_at": "2099-01-01T00:00:00Z", "connected_account_id": cid})
        if path == ["connected_accounts"]:
            users, statuses = q.get("user_ids", "").split(","), q.get("statuses", "ACTIVE").split(",")
            return self.send(200, PAGE([SEEN(a) for a in MOCK["accounts"].values() if a["_user"] in users and a["status"] in statuses]))
        if path[:1] == ["connected_accounts"] and len(path) == 2:
            account = MOCK["accounts"].get(path[1])
            if method == "DELETE" and account:
                MOCK["deleted"].append(MOCK["accounts"].pop(path[1]))
                return self.send(200, {"success": True})
            return self.send(200, SEEN(account)) if account else self.send(404, ERR(404, "Connected account not found", "ConnectedAccount_NotFound"))
        if path == ["tools"]:
            return self.send(200, PAGE([tool(s) for s, t in TOOLS.items() if t["toolkit"] == q.get("toolkit_slug")]))
        if path[:1] == ["tools"] and len(path) == 2:
            return self.send(200, tool(path[1])) if path[1] in TOOLS else self.send(404, ERR(404, "Tool not found", "Tool_NotFound"))
        if path[:2] == ["tools", "execute"]:
            MOCK["executed"].append({"tool": path[2], **body})
            data = {"messages": [{"from": "dana@example.com", "subject": "Contract signed"}]} if "FETCH" in path[2] else {"sent": True}
            return self.send(200, {"data": data, "error": None, "successful": True, "log_id": "log_1"})
        self.send(404, ERR(404, "No such endpoint", "Request_NotFound"))

    def send(self, code, data, kind="application/json"):
        body = (data if isinstance(data, str) else json.dumps(data)).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Composio)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
SITE = f"http://127.0.0.1:{SERVER.server_port}"

FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def log(entry):
        with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(entry) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
    still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = [0]
    def request(method, params):
        n[0] += 1
        still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": n[0], "method": method, "params": params}) + "\n").encode()); still.stdin.flush()
        for line in still.stdout:
            try: m = json.loads(line)
            except ValueError: continue
            if m.get("id") == n[0]: return m
    request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
    still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
    tag = prompt.rsplit("\n\n", 1)[-1].strip()
    def call(name, **a):
        m = request("tools/call", {"name": name, "arguments": a}) or {}
        r = m.get("result") or {"isError": True, "content": [{"text": "MCP error: " + json.dumps(m.get("error"))}]}
        ok, text = not r.get("isError"), "\n".join(c.get("text", "") for c in r.get("content", []))
        log({"chat": tag, "tool": name, "args": a, "ok": ok, "text": text, "t": time.time()})
        return ok
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if "NOPLUG" in tag:
        call("plugin_tools", plugin="gmail")
        call("use_plugin", tool="GMAIL_FETCH_EMAILS", arguments={})
    elif "READMAIL" in tag:
        call("plugin_tools", plugin="gmail", query="emails")
        call("use_plugin", tool="GMAIL_FETCH_EMAILS", arguments={"query": "is:unread"})
    elif "SENDMAIL" in tag:
        call("use_plugin", tool="GMAIL_SEND_EMAIL", arguments={"to": "sam@example.com", "subject": "Lunch on Friday", "body": "Still on for noon?"})
    elif "SLACK" in tag:
        call("use_plugin", tool="SLACK_SEND_MESSAGE", arguments={"channel": "#general", "text": "Shipping today"})
    elif "PEEK" in tag:
        log({"chat": tag, "tool": "env", "ok": True, "text": json.dumps(dict(os.environ)) + "\n" + prompt + "\n" + " ".join(args), "t": time.time()})
        log({"chat": tag, "tool": "tools/list", "ok": True, "text": json.dumps(request("tools/list", {})["result"]), "t": time.time()})
    elif m := re.search(r"WEB (\S+)", tag):
        call("open_tab", url=m[1] + "/page")
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}})
    still.stdin.close()
''')


def calls(tag):
    file = BIN / "calls.jsonl"
    rows = [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.endswith("}")] if file.exists() else []
    return [c for c in rows if c["chat"] == tag]


def ask(process, tag):
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 20)
    time.sleep(.4)
    send(process, "aiSend", text=tag, home=True, companion="glint")


def idle(process):
    time.sleep(1)
    return until(lambda: not js(process, "document.querySelector('.tasks-button')?.getAttribute('aria-label')?.match(/[1-9]\\d* running/)"), 60)


def cards(process):
    return js(process, "[...document.querySelectorAll('.approve-card .approve-steps li')].map(e => e.innerText)") or []


def buttons(process):
    return js(process, "[...document.querySelectorAll('.approve-card .approve-actions button')].map(b => b.innerText.trim())") or []


def press(process, words, within=".approve-card"):
    return js(process, f"(() => {{ const b = [...document.querySelectorAll({json.dumps(within + ' button')})].find(b => b.innerText.trim() === {json.dumps(words)}); b?.click(); return !!b }})()")


def type_into(process, selector, value):
    js(process, f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; e.focus();
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {json.dumps(value)});
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); return true }})()""")


def page_text(process):
    return js(process, "document.querySelector('.plug-settings')?.innerText ?? ''") or ""


def turned_off(companion):
    try:  # Still may be writing it
        return next((c.get("PluginsOff", []) for c in json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]["Companions"] if c["Id"] == companion), [])
    except (OSError, ValueError):
        return []


def open_plugins(process):
    """Skills & plugins, from the home's rail, in a new tab: once it's open, click until the page is there (a busy Still can be slow)."""
    count = lambda: sum(len(w["tabs"]) for w in rpc(process, "tabs").get("windows", []))
    before = count()
    send(process, "new")
    until(lambda: count() > before and js(process, "!!document.querySelector('.home-rail')"), 20)
    time.sleep(.3)
    return until(lambda: js(process, """document.querySelector(".home-page[aria-label='Skills & plugins'] .plug-settings") ? true
     : (document.querySelector(".home-rail-item[aria-label='Skills & plugins']")?.click(), false)"""), 15)


SEARCH = ".home-page input[aria-label='Search skills and plugins']"


def apps(process, which="is-found"):
    return js(process, f"[...document.querySelectorAll('.plug-list.{which} li')].map(l => l.querySelector('.plug-chip').lastChild.textContent + ': ' + (l.querySelector('.plug-on')?.innerText.trim() ?? ''))") or []


def close_panel(process):
    js(process, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    until(lambda: not js(process, "!!document.querySelector('.settings-tabs')"), 5)


def paste_key(process, key, scope=".plug-settings"):
    type_into(process, scope + " input[aria-label='Composio API key']", key)
    time.sleep(.2)
    js(process, f"document.querySelector('{scope} .plug-key button[type=submit]')?.click()")


def key_file(profile=None):
    folder = profile or PROFILE
    return folder / ("composio.qa" if MAC else "composio.dpapi")


def nowhere(profile=None):
    """Every file in the profile, read as UTF-8 and UTF-16: the key must not be in any of them in the clear."""
    hits = []
    for f in (profile or PROFILE).rglob("*"):
        if MAC and f.name == "composio.qa":
            continue  # the Keychain's stand-in in test builds
        try:
            raw = f.read_bytes() if f.is_file() else b""
        except OSError:
            continue
        if KEY.encode() in raw or KEY.encode("utf-16-le") in raw:
            hits.append(str(f.relative_to(profile or PROFILE)))
    return hits


def oauth_tab(process):
    for w in rpc(process, "tabs").get("windows", []):
        for t in w["tabs"]:
            if "/oauth/" in (t.get("Url") or ""):
                return w, t
    return None, None


def sign_in(process, name):
    """Composio's page opens in its own Still window; Allow there, and the window closes once it's connected."""
    window = until(lambda: oauth_tab(process)[0], 15)
    main_window = rpc(process, "tabs")["windows"][0]["id"]
    check(window and window["id"] != main_window, f"Connect {name} opens Composio's sign-in in a Still window")
    _, tab = oauth_tab(process)
    check(until(lambda: rpc(process, "evalTab", id=tab["Id"], script="!!document.querySelector('#allow')") is True, 20), f"Composio's page for {name} loads in it")
    rpc(process, "evalTab", id=tab["Id"], script="document.querySelector('#allow').click()")
    check(until(lambda: not oauth_tab(process)[0], 15), f"Once {name} is connected, that window closes")


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake", "Theme": "Light", "Width": 1720, "Height": 1080},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "STILL_QA_COMPOSIO": SITE + "/api/v3.1"}
    process = launch(EXE, PROFILE, env)
    try:
        no_key(process)
        keys(process)
        connect(process)
        reads_and_writes(process)
        missing(process)
        secret(process)
        down(process)
        disconnect(process)
        errors = rpc(process).get("shellErrors") or js(process, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
    setup(env)


def no_key(process):
    check(open_plugins(process), "Plugins live in Skills & plugins, on the home's rail")
    words = page_text(process)
    check(js(process, "document.querySelector(\".plug-settings input[aria-label='Composio API key']\")?.type") == "password", "With no key, it asks for your Composio API key, right there")
    check(all(w in words for w in ("Get a key", "Platform", "Settings → Project Settings → API Keys", "ak_")), "The connect step says where the key comes from: Composio's Platform, Settings → Project Settings → API Keys, the one that starts with ak_")
    check("third-party service" in words and "pricing" not in words.lower(), "It says Composio is a third party, with no pricing in Still's words")
    listed = apps(process, "is-preview")
    check(len(listed) == 24 and all(a.endswith(": Needs a key") for a in listed), f"Plugin list loads with no key: every app, marked Needs a key, not an empty list ({len(listed)})")
    type_into(process, SEARCH, "sla")
    check(until(lambda: apps(process, "is-preview") == ["Slack: Needs a key"], 5), "One search finds apps too")
    type_into(process, SEARCH, "")
    js(process, "[...document.querySelectorAll('.home-page .history-chip')].find(b => b.innerText.trim() === 'Skills')?.click()")
    check(until(lambda: not js(process, "!!document.querySelector('.plug-settings')") and js(process, "!!document.querySelector('.skills-part[aria-label=Skills]')"), 5), "The Skills filter shows only skills")
    js(process, "[...document.querySelectorAll('.home-page .history-chip')].find(b => b.innerText.trim() === 'Plugins')?.click()")
    check(until(lambda: js(process, "!!document.querySelector('.plug-settings') && !document.querySelector('.skills-part[aria-label=Skills]')"), 5), "and Plugins only plugins")
    send(process, "openPanel", name="settings", value="plugins")
    until(lambda: js(process, "!!document.querySelector('.settings-tabs')"), 10)
    card = until(lambda: js(process, "[...document.querySelectorAll('.settings-content button')].find(b => b.innerText.trim() === 'Open Skills & plugins')?.innerText"), 5)
    check(card and not js(process, "!!document.querySelector('.settings-content .plug-settings')"), "Settings → Plugins is only a card that opens Skills & plugins")
    js(process, "[...document.querySelectorAll('.settings-content button')].find(b => b.innerText.trim() === 'Open Skills & plugins')?.click()")
    check(until(lambda: not js(process, "!!document.querySelector('.settings-tabs')") and js(process, "!!document.querySelector(\".home-page[aria-label='Skills & plugins'] .plug-settings\")"), 10), "and it does")
    ask(process, "NOPLUG")
    idle(process)
    done = until(lambda: len(calls("NOPLUG")) == 2 and calls("NOPLUG"), 20) or calls("NOPLUG")  # the run's first chat can start late
    check(len(done) == 2 and not any(c["ok"] for c in done) and all("Skills & plugins" in c["text"] for c in done), "Without a key, plugin tools say plugins are off and where to turn them on")
    check(not MOCK["seen"], "Without a key, Still never calls Composio")
    ask(process, "WEB " + SITE)
    idle(process)
    check([c["ok"] for c in calls("WEB " + SITE)] == [True], "Everything else works as usual")


def keys(process):
    open_plugins(process)
    paste_key(process, CONSUMER)
    check(until(lambda: "Connect key (ck_…)" in page_text(process) and "starts with ak_" in page_text(process), 10), "A Connect key (ck_), what Composio's For You page shows, is named as the wrong kind, with the right one")
    check(not key_file().exists() and not any(s["key"] == CONSUMER for s in MOCK["seen"]), "It's never sent to Composio, and isn't kept")
    paste_key(process, WRONG)
    check(until(lambda: "didn't accept that key" in page_text(process), 10), "A key Composio refuses says so")
    check(not key_file().exists(), "and isn't kept")
    paste_key(process, KEY)
    check(until(lambda: "Add an app" in page_text(process), 10), "A good key turns plugins on")
    check(key_file().exists(), "It's kept encrypted, " + ("in the Keychain (a test file here)" if MAC else "with DPAPI, like saved passwords"))
    check(not js(process, f"document.documentElement.outerHTML.includes({json.dumps(KEY)}) || JSON.stringify(window.__stillState ?? {{}}).includes({json.dumps(KEY)})")
          and js(process, "document.querySelector(\".plug-settings input[aria-label='Composio API key']\")") is None, "The field empties, and the interface never gets the key back")
    found = until(lambda: apps(process), 10) or []
    check(found == ["Gmail: Needs sign-in", "Google Calendar: Needs sign-in", "Slack: Needs sign-in"], f"Plugin list loads with a key: what Composio signs in to itself, from its paged list, each Needs sign-in ({found})")
    type_into(process, SEARCH, "cal")
    check(until(lambda: apps(process) == ["Google Calendar: Needs sign-in"], 5), "Search finds an app")
    MOCK["broken"] = True
    type_into(process, SEARCH, "slack")
    check(until(lambda: "Invalid value for sort_by" in page_text(process), 5) and "Loading apps" not in page_text(process), "When Composio can't list apps, it says why instead of an empty list")
    MOCK["broken"] = False
    type_into(process, SEARCH, "")
    until(lambda: js(process, "document.querySelectorAll('.plug-list.is-found li').length") == 3 and "Invalid value" not in page_text(process), 5)


def connect(process):
    """The Composio connect flow."""
    MOCK["refuse_config"] = True
    js(process, "[...document.querySelectorAll('.plug-list.is-found li')].find(l => l.innerText.includes('Google Calendar'))?.querySelector('button')?.click()")
    check(until(lambda: "Google Calendar: Didn't connect" in apps(process) and "Google Calendar didn't connect: Composio managed auth isn't available" in page_text(process), 10), "Composio connect flow: a connect Composio refuses shows on that app, with Composio's reason")
    MOCK["refuse_config"] = False
    js(process, "[...document.querySelectorAll('.plug-list.is-found li')].find(l => l.innerText.includes('Gmail'))?.querySelector('button')?.click()")
    sign_in(process, "Gmail")
    check(until(lambda: js(process, "document.querySelector('.plug-section .plug-list:not(.is-found) .plug-chip')?.lastChild.textContent") == "Gmail" and "Gmail: Connected" in apps(process, "is-found")
                and "didn't connect" not in page_text(process), 10), "Composio connect flow: Gmail ends up Connected, at the top and in the list")
    account = next(iter(MOCK["accounts"].values()))
    check(account["_user"].startswith("still-") and MOCK["configs"].get("ac_gmail", {}).get("is_composio_managed"), "It uses Composio's own sign-in, for this profile's own user")
    who = js(process, "[...document.querySelectorAll('.plug-settings .plug-who button')].map(b => b.innerText.trim() + ':' + b.getAttribute('aria-pressed'))") or []
    check(who[:2] == ["Glint:true", "Noon:true"], f"Each companion can use it, with a switch each ({who})")
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-face')"), 10)
    time.sleep(.4)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    js(process, "document.querySelector('.home-face')?.click()")
    until(lambda: js(process, "!!document.querySelector('.profile-tablist')"), 10)
    tabs = js(process, "document.querySelector('.profile-tablist')?.innerText.replace(/\\s+/g, ' ').trim()")
    js(process, "document.querySelector(\".profile-tablist [role=tab][id$='-trigger-skills']\")?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }))")
    check(until(lambda: js(process, "document.querySelector(\".profile-panel [role=switch][aria-label='Gmail for Glint']\")?.getAttribute('aria-checked')") == "true", 5) and "Plugins" not in tabs.replace("Skills & plugins", ""),
          f"A companion's profile has no Plugins tab; its Skills & plugins tab has a switch for Gmail ({tabs})")
    js(process, "document.querySelector('.profile-panel [aria-label=Close]')?.click()")
    until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 5)


def reads_and_writes(process):
    ask(process, "READMAIL")
    idle(process)
    done = calls("READMAIL")
    listed = json.loads(done[0]["text"]) if done and done[0]["ok"] else []
    tools = {t["tool"]: t["asksFirst"] for t in (listed[0]["tools"] if listed else [])}
    check(tools == {"GMAIL_FETCH_EMAILS": False, "GMAIL_SEND_EMAIL": True}, f"plugin_tools lists Gmail's tools and which ones ask first ({tools})")
    ran = [e for e in MOCK["executed"] if e["tool"] == "GMAIL_FETCH_EMAILS"]
    check(len(done) == 2 and done[1]["ok"] and "Contract signed" in done[1]["text"] and ran and ran[0]["arguments"] == {"query": "is:unread"}, "Reading mail goes ahead, no card, and the companion gets the mail")
    check(ran and ran[0]["connected_account_id"] == next(iter(MOCK["accounts"])) and ran[0]["user_id"].startswith("still-"), "It runs on the Gmail account you connected")

    ask(process, "SENDMAIL")
    card = until(lambda: cards(process), 20)
    check(card and "Send email in Gmail" in card[0] and "sam@example.com" in card[0], f"Sending an email waits on a card that says what and to whom ({card})")
    check(buttons(process) == ["Deny", "Allow once"], f"Its only choices are Deny and Allow once ({buttons(process)})")
    check(not [e for e in MOCK["executed"] if e["tool"] == "GMAIL_SEND_EMAIL"], "Nothing is sent while it waits")
    press(process, "Deny")
    idle(process)
    check(calls("SENDMAIL")[-1]["ok"] is False and not [e for e in MOCK["executed"] if e["tool"] == "GMAIL_SEND_EMAIL"], "Deny: nothing is sent, and the companion is told no")
    ask(process, "SENDMAIL")
    until(lambda: cards(process), 20)
    press(process, "Allow once")
    idle(process)
    sent = [e for e in MOCK["executed"] if e["tool"] == "GMAIL_SEND_EMAIL"]
    check(len(sent) == 1 and sent[0]["arguments"]["to"] == "sam@example.com" and calls("SENDMAIL")[-1]["ok"], "Allow once: it's sent, once")
    ask(process, "SENDMAIL")
    check(until(lambda: cards(process), 20), "The next send asks again: no silent sends")
    press(process, "Deny")
    idle(process)

    open_plugins(process)
    js(process, "document.querySelector('.plug-settings .plug-who button')?.click()")  # Glint
    until(lambda: js(process, "document.querySelector('.plug-settings .plug-who button')?.getAttribute('aria-pressed')") == "false", 5)
    close_panel(process)
    check(until(lambda: "gmail" in turned_off("glint"), 5), "Turning Gmail off for Glint is saved")
    before = len(MOCK["executed"])
    ask(process, "READMAIL")
    idle(process)
    check(calls("READMAIL")[-1]["ok"] is False and "turned Gmail off for you" in calls("READMAIL")[-1]["text"] and len(MOCK["executed"]) == before, "Then Glint can't use Gmail, and is told why")
    open_plugins(process)
    js(process, "document.querySelector('.plug-settings .plug-who button')?.click()")
    until(lambda: js(process, "document.querySelector('.plug-settings .plug-who button')?.getAttribute('aria-pressed')") == "true", 5)
    close_panel(process)


def missing(process):
    ask(process, "SLACK")
    card = until(lambda: cards(process), 20)
    head = js(process, "document.querySelector('.approve-card .ask-q')?.innerText.trim()")
    check(card and "Connect Slack" in card[0] and head == "Glint needs Slack for this." and buttons(process) == ["Not now", "Connect Slack"], f"Slack isn't connected: Glint says it needs it, with a button that connects it ({head}; {buttons(process)})")
    press(process, "Not now")
    idle(process)
    check(calls("SLACK")[-1]["ok"] is False and not [e for e in MOCK["executed"] if e["tool"] == "SLACK_SEND_MESSAGE"], "Not now: nothing connects and nothing is posted")
    ask(process, "SLACK")
    until(lambda: cards(process), 20)
    press(process, "Connect Slack")
    sign_in(process, "Slack")
    card = until(lambda: (c := cards(process)) and "Send message in Slack" in c[0] and c, 20)
    check(card, "Once Slack is connected, the post itself still asks first")
    press(process, "Allow once")
    idle(process)
    check(calls("SLACK")[-1]["ok"] and [e for e in MOCK["executed"] if e["tool"] == "SLACK_SEND_MESSAGE"], "Then it's posted")


def secret(process):
    ask(process, "PEEK")
    idle(process)
    seen = calls("PEEK")
    check(len(seen) == 2 and KEY not in seen[0]["text"], "The key isn't in the AI app's environment, arguments or instructions")
    listed = [t["name"] for t in json.loads(seen[1]["text"]).get("tools", [])] if len(seen) == 2 else []
    check("plugin_tools" in listed and "use_plugin" in listed and KEY not in seen[1]["text"], "Companions get plugin_tools and use_plugin, and no tool hands out the key")
    every = [json.loads(line) for line in (BIN / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.endswith("}")]
    check(not any(KEY in c["text"] for c in every), "No tool result ever has the key")
    check(not nowhere(), f"The key isn't in any file in the profile in the clear ({nowhere()})")
    check(all(s["key"] in (KEY, WRONG) for s in MOCK["seen"] if s["key"]) and not any(p["key"] for p in MOCK["pages"]), "It only ever goes to Composio's API, never to a page, and a Connect key never goes anywhere")


def down(process):
    MOCK["down"] = True
    open_plugins(process)
    check(until(lambda: "isn't answering" in page_text(process), 10), "Composio down: Plugins says they're unavailable and the rest of Still works")
    close_panel(process)
    ask(process, "READMAIL")
    idle(process)
    check(calls("READMAIL")[-1]["ok"] is False and "isn't answering" in calls("READMAIL")[-1]["text"], "and the companion is told plugins are unavailable")
    ask(process, "WEB " + SITE)
    idle(process)
    check(all(c["ok"] for c in calls("WEB " + SITE)) and len(calls("WEB " + SITE)) == 2, "Browsing still works")
    MOCK["down"] = False


def disconnect(process):
    open_plugins(process)
    js(process, "document.querySelector('.plug-settings .plug-list:not(.is-found) li > button:last-child')?.click()")  # Disconnect, on the first app
    check(until(lambda: len(MOCK["deleted"]) == 1 and js(process, "document.querySelectorAll('.plug-section .plug-list:not(.is-found) li').length") == 1, 10), "Disconnect removes the account at Composio and from the list")
    js(process, "[...document.querySelectorAll('.plug-settings button')].find(b => b.innerText.trim() === 'Remove key')?.click()")
    check(until(lambda: not key_file().exists() and js(process, "!!document.querySelector(\".plug-settings input[aria-label='Composio API key']\")"), 10), "Remove key forgets it and turns plugins off")
    close_panel(process)
    ask(process, "NOPLUG")
    idle(process)
    check(not any(c["ok"] for c in calls("NOPLUG")), "and companions are back to plugins off")


def setup(env):
    """Setup's Connect your tools with a key: the belt turns into a grid, a tap connects Gmail, and Zest bounces and says so."""
    profile = RUN / "profile2"
    (profile / "agents").mkdir(parents=True)
    shutil.copy(PROFILE / "agents" / "fake.json", profile / "agents" / "fake.json")
    MOCK["accounts"].clear()
    process = launch(EXE, profile, env)
    try:
        js(process, "localStorage.setItem('still.intro', '1'); location.reload()")
        step = lambda: js(process, "Number(document.querySelector('.ob-dots')?.getAttribute('aria-valuenow') ?? 0)")
        def forward(selector=".ob-next"):
            at = step()
            js(process, f"document.querySelector('{selector}')?.click()")
            until(lambda: step() == at + 1, 6)
            time.sleep(1.2)
        until(lambda: js(process, "!!document.querySelector('.welcome.ob .ob-next')"), 20)
        time.sleep(1.5)
        forward()  # hello -> import
        forward(".ob-not-now")  # -> ai
        if not until(lambda: js(process, "(() => { const b = [...document.querySelectorAll('.byo-main')].find(b => b.innerText.includes('Fake agent')); b?.click(); return !!b })()"), 4):
            js(process, "document.querySelector('.byo-more')?.click()")
            until(lambda: js(process, "(() => { const b = [...document.querySelectorAll('.byo-main')].find(b => b.innerText.includes('Fake agent')); b?.click(); return !!b })()"), 6)
        until(lambda: js(process, "!!document.querySelector('.byo-row[data-chosen] .byo-ok')"), 10)
        time.sleep(1)
        forward()  # -> crew
        until(lambda: js(process, "document.querySelectorAll('.crew-card').length") >= 8, 5)
        js(process, "document.querySelector(\".crew-pick[aria-label='Hire Zest']\")?.click()")
        time.sleep(.6)
        forward()  # -> tools
        check(until(lambda: js(process, "!!document.querySelector('.plug-belt')"), 5), "Setup: Connect your tools shows the belt")
        paste_key(process, KEY, ".ob-talk")
        check(until(lambda: js(process, "document.querySelectorAll('.plug-grid .plug-pick').length") == 24 and not js(process, "!!document.querySelector('.plug-belt')"), 10), "With a key, the belt stops and becomes a grid to pick from")
        check(not js(process, f"document.documentElement.outerHTML.includes({json.dumps(KEY)})") and key_file(profile).exists() and not nowhere(profile), "The key is kept encrypted there too, and never shows")
        js(process, "document.querySelector(\".plug-pick[aria-label='Connect Gmail']\")?.click()")
        sign_in(process, "Gmail")
        check(until(lambda: js(process, "document.querySelector(\".plug-pick[aria-label='Gmail is connected']\")?.getAttribute('aria-pressed')") == "true", 10), "Gmail gets its check")
        check(until(lambda: "Now I can work in Gmail" in (js(process, "document.querySelector('.ob-team-line, .ob-cheer')?.innerText") or ""), 5), "Zest, who works in Gmail, bounces and says so")
        rpc(process, "capture", name="tools-connected.png")
        foot = js(process, "[...document.querySelectorAll('.ob-foot button')].map(b => b.innerText.trim() + (b.disabled ? ' (off)' : ''))") or []
        check(foot == ["Back", "Continue"], f"With an app connected, Continue goes on ({foot})")
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
