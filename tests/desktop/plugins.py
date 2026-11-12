"""Plugins through Composio, against a local stand-in for Composio's API (STILL_QA_COMPOSIO points test builds at it).
A fake AI app plays a companion that uses them.

  NOPLUG       loads Gmail's actions and runs one, with no key
  READMAIL     lists what's connected, loads Gmail's actions, then reads mail (a read: no card)
  FINDAPPS     looks apps up by name and category, asks for an app that doesn't exist and runs another app's action
  SENDMAIL     sends an email (a write: a card, Not now or Allow)
  SLACK        posts in Slack, which isn't connected (a card that connects it, then the write's card)
  PEEK         writes down its environment and Still's tool list, looking for the key
  WEB <site>   opens a page (the browser still works when Composio doesn't)

The stand-in answers like Composio's v3.1 API: x-api-key takes a project key (ak_) and nothing else, so the Connect key
(ck_) that Composio's For You page hands out gets a 401, as it does there; lists come paged ({items, next_cursor, ...}),
the catalog over two pages; errors are { error: { message, code, slug, status, ... } }; connected accounts don't echo
user_id back. Every app Composio had when Still was built shows the logo that ships with Still; only the two newer
apps here (Self Hosted Thing and Weather) get theirs from the stand-in, one with no image type and one missing.

Checks: the Plugins page (Plugins on the home's rail) is titled Plugins with what's connected at the top, one
search for plugins (skills have their own page), category chips with the rest under More, Recommended first and then a section per category
with View all, apps two across with their logo, name and Connect (or a Connected check), no description. With no key
the apps still show and Connect goes to the key field, which says where the key comes from (Platform → Settings →
Project Settings → API Keys, ak_); a Connect key (ck_) is named as the wrong kind and never sent or kept; off with no
key and nothing else breaks, not even a logo is fetched; a bad key isn't kept; a good one is kept encrypted (DPAPI on
Windows, the Keychain on the Mac) and never reaches a file in the clear, the interface, an agent, its tools or its
environment. Composio's whole catalog loads page by page and is cached, logos too, fetched without the key; an error
says why and the saved list stays. The Composio connect flow: Connect opens Composio's sign-in in a Still window, which
closes when it's done, and a connect Composio refuses shows on that app. Companions get four small lookups and no app's
actions until they ask for one app: list_connected_plugins (names only), find_plugins, get_plugin_tools,
run_plugin_action; reads go ahead, writes ask (Not now or Allow, nothing else); per-companion switches under the
Connected check and in the profile; a missing app gets a card that connects it; Composio down; Disconnect. Settings
shows the key only as set with its last four characters: Change checks a new key before it replaces the old one, and
Delete turns plugins off. Setup has no plugins step since 2.10: plugins come up from the home page and Settings.

Run: python tests/desktop/plugins.py artifacts/Still-QA/Still.exe
"""
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
from qa import press_ready, CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("plugins-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}
KEY = "ak_test_" + uuid.uuid4().hex  # a project key nobody else knows: it's looked for everywhere it mustn't be
KEY2 = "ak_next_" + uuid.uuid4().hex  # the key it's changed to in Settings
WRONG = "ak_wrong_" + uuid.uuid4().hex[:12]  # a key Composio refuses
CONSUMER = "ck_" + uuid.uuid4().hex[:22]  # what Composio's For You → Sessions & API Key page shows: for its MCP endpoint, not the API
MOCK = {"down": False, "broken": False, "refuse_config": False, "accounts": {}, "configs": {}, "executed": [], "deleted": [], "seen": [], "pages": [], "catalog": []}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


CATS = lambda *names: [{"id": n.lower().replace(" ", "-"), "name": n} for n in names]
KIT = lambda slug, name, cats, managed=("OAUTH2",), no_auth=False: {"slug": slug, "name": name, "type": "native", "auth_schemes": ["OAUTH2"], "composio_managed_auth_schemes": list(managed),
    "is_local_toolkit": False, "no_auth": no_auth, "auth_guide_url": None, "deprecated": {"toolkitId": "tk_" + slug},
    "meta": {"description": "What " + name + " does.", "logo": "", "categories": CATS(*cats), "tools_count": 20, "triggers_count": 2, "version": "20260101_00", "app_url": None, "created_at": "2025-01-01", "updated_at": "2026-01-01"}}
TOOLKITS = [KIT("gmail", "Gmail", ["Communication"]), KIT("googlecalendar", "Google Calendar", ["Productivity"]), KIT("slack", "Slack", ["Communication"]),
            KIT("selfhosted", "Self Hosted Thing", ["Developer tools"], ()), KIT("notion", "Notion", ["Productivity"]), KIT("github", "GitHub", ["Developer tools"]),
            KIT("linear", "Linear", ["Productivity", "Developer tools"]), KIT("figma", "Figma", ["Design"]), KIT("stripe", "Stripe", ["Finance"]), KIT("hubspot", "HubSpot", ["CRM"]),
            KIT("asana", "Asana", ["Productivity"]), KIT("trello", "Trello", ["Productivity"]), KIT("canva", "Canva", ["Design"]), KIT("quickbooks", "QuickBooks", ["Finance", "Accounting"]),
            KIT("mailchimp", "Mailchimp", ["Marketing"]), KIT("zendesk", "Zendesk", ["Support"]), KIT("clickup", "ClickUp", ["Productivity"]), KIT("weather", "Weather", [], no_auth=True),
            KIT("discord", "Discord", ["Communication"]), KIT("airtable", "Airtable", ["Productivity"]), KIT("xero", "Xero", ["Accounting"]), KIT("intercom", "Intercom", ["Support"])]
FIRST_PAGE = 12
LOGO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" rx="2" fill="#d33"/></svg>'
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
        if parts[0] in ("oauth", "page", "logos"):  # what a browser opens: Composio's sign-in, a plain page, and logos
            MOCK["pages"].append({"path": url.path, "key": self.headers.get("x-api-key")})
            if parts[0] == "logos":  # Weather's is missing, and Self Hosted Thing's doesn't say it's an image
                return self.send(404, "Not found", "text/plain") if parts[1] == "weather" else self.send(200, LOGO, "application/octet-stream" if parts[1] == "selfhosted" else "image/svg+xml")
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
        if key not in (KEY, KEY2):  # Composio's API only takes a project key here: a Connect (ck_) or personal (uak_) key is refused too
            return self.send(401, ERR(401, "Invalid API key", "Auth_InvalidApiKey"))
        if MOCK["down"]:
            return self.send(503, ERR(503, "Service unavailable", "Internal_ServiceUnavailable"))
        path = parts[2:]  # after api/v3.1
        if path == ["toolkits"]:
            if MOCK["broken"]:
                return self.send(400, ERR(400, "Invalid value for sort_by", "Request_InvalidQuery"))
            MOCK["catalog"].append(q.get("cursor", ""))
            kits = [{**t, "meta": {**t["meta"], "logo": f"{SITE}/logos/{t['slug']}"}} for t in TOOLKITS]
            later = q.get("cursor") == "page2"
            return self.send(200, {"items": kits[FIRST_PAGE:] if later else kits[:FIRST_PAGE], "next_cursor": None if later else "page2", "total_pages": 2, "current_page": 2 if later else 1, "total_items": len(kits)})
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
    def call(name, /, **a):
        m = request("tools/call", {"name": name, "arguments": a}) or {}
        r = m.get("result") or {"isError": True, "content": [{"text": "MCP error: " + json.dumps(m.get("error"))}]}
        ok, text = not r.get("isError"), "\n".join(c.get("text", "") for c in r.get("content", []))
        log({"chat": tag, "tool": name, "args": a, "ok": ok, "text": text, "t": time.time()})
        return ok
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if "NOPLUG" in tag:
        call("get_plugin_tools", plugin="gmail")
        call("run_plugin_action", plugin="gmail", action="GMAIL_FETCH_EMAILS", args={})
    elif "READMAIL" in tag:
        call("list_connected_plugins")
        call("get_plugin_tools", plugin="Gmail", query="emails")
        call("run_plugin_action", plugin="Gmail", action="GMAIL_FETCH_EMAILS", args={"query": "is:unread"})
    elif "FINDAPPS" in tag:
        call("find_plugins", query="cal")
        call("find_plugins", category="finance")
        call("get_plugin_tools", plugin="Nothing Real")
        call("run_plugin_action", plugin="Slack", action="GMAIL_SEND_EMAIL", args={"to": "x@example.com"})
    elif "LONGMAIL" in tag:
        call("run_plugin_action", plugin="gmail", action="GMAIL_SEND_EMAIL", args={"a": "1", "b": "2", "c": "3", "to": "sam@example.com", "cc": ["copy@example.com"], "tries": 2, "body": "w" * 3000})
    elif "HELPMAIL" in tag:
        call("ask_companion", name="Nora", message="READMAIL")
    elif "SENDMAIL" in tag:
        call("run_plugin_action", plugin="gmail", action="GMAIL_SEND_EMAIL", args={"to": "sam@example.com", "subject": "Lunch on Friday", "body": "Still on for nora?"})
    elif "SLACK" in tag:
        call("run_plugin_action", plugin="Slack", action="SLACK_SEND_MESSAGE", args={"channel": "#general", "text": "Shipping today"})
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
    send(process, "aiSend", text=tag, home=True, companion="maya")


def idle(process):
    time.sleep(1)
    return until(lambda: not js(process, "document.querySelector('.tasks-button')?.getAttribute('aria-label')?.match(/[1-9]\\d* running/)"), 60)


def cards(process):
    return js(process, "[...document.querySelectorAll('.approve-card .approve-steps li')].map(e => e.innerText)") or []


def buttons(process):
    return js(process, "[...document.querySelectorAll('.approve-card .approve-actions button')].map(b => b.innerText.trim())") or []


def press(process, words, within=".approve-card"):
    return press_ready(process, f"[...document.querySelectorAll({json.dumps(within + ' button')})].find(b => b.innerText.trim() === {json.dumps(words)})")


def type_into(process, selector, value):
    js(process, f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; e.focus();
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {json.dumps(value)});
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); return true }})()""")


def page_text(process):
    return js(process, "document.querySelector('.plug-page')?.innerText ?? ''") or ""


def turned_off(companion):
    try:  # Still may be writing it
        return next((c.get("PluginsOff", []) for c in json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]["Companions"] if c["Id"] == companion), [])
    except (OSError, ValueError):
        return []


def open_plugins(process):
    """Plugins, from the home's rail, in a new tab: once it's open, click until the page is there (a busy Still can be slow)."""
    count = lambda: sum(len(w["tabs"]) for w in rpc(process, "tabs").get("windows", []))
    before = count()
    send(process, "new")
    until(lambda: count() > before and js(process, "!!document.querySelector('.home-rail')"), 20)
    time.sleep(.3)
    return until(lambda: js(process, """document.querySelector(".home-page.plug-page[aria-label='Plugins']") ? true
     : (document.querySelector(".home-rail-item[aria-label='Plugins']")?.click(), false)"""), 15)


SEARCH = ".plug-page input[aria-label='Search plugins']"


def tiles(process, group=""):
    """Each app on the page (or in one section) as "Name: what its button says"."""
    scope = f".plug-group[aria-label='{group}']" if group else ".plug-page"
    return js(process, f"[...document.querySelectorAll(\"{scope} .plug-tile\")].map(t => t.querySelector('.plug-name').innerText + ': ' + t.querySelector('button')?.innerText.trim())") or []


def head(process):
    return js(process, "document.querySelector('.plug-count')?.lastChild?.textContent.trim()") or ""  # past the logos


def manage(process, slug):
    """A connected app's check: it opens who can use it, and Disconnect."""
    js(process, f"document.querySelector(\".plug-tile[data-slug={slug}] .plug-done\")?.click()")
    return until(lambda: js(process, "!!document.querySelector('.plug-manage')"), 5)


def close_panel(process):
    js(process, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    until(lambda: not js(process, "!!document.querySelector('.set-shell')"), 5)


def paste_key(process, key, scope=".plug-page"):
    type_into(process, scope + " input[aria-label='Composio API key']", key)
    time.sleep(.2)
    js(process, f"document.querySelector('{scope} .plug-key button[type=submit]')?.click()")


def key_file(profile=None):
    folder = profile or PROFILE
    return folder / ("composio.sealed" if MAC else "composio.dpapi")


def nowhere(profile=None):
    """Every file in the profile, read as UTF-8 and UTF-16: the key must not be in any of them in the clear."""
    hits = []
    for f in (profile or PROFILE).rglob("*"):
        try:
            raw = f.read_bytes() if f.is_file() else b""
        except OSError:
            continue
        if any(k.encode() in raw or k.encode("utf-16-le") in raw for k in (KEY, KEY2)):
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
        finds(process)
        missing(process)
        stack(process)
        secret(process)
        down(process)
        disconnect(process)
        errors = rpc(process).get("shellErrors") or js(process, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


def home_stack(process, capture=""):
    """The home row's Plugins button, in a new tab: its label and its tiles."""
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-chips .home-plugins')"), 20)
    time.sleep(.4)
    if capture:
        rpc(process, "capture", name=capture)
    return js(process, "(b => [b.getAttribute('aria-label'), [...b.querySelectorAll('.plug-stack i')].map(i => i.innerText.trim() || 'icon'), b === b.parentElement.lastElementChild])(document.querySelector('.home-chips .home-plugins'))") or ["", [], False]


def stack(process):
    """Five apps connected: three logos and +2; the button opens the Plugins page."""
    user = next(iter(MOCK["accounts"].values()))["_user"]
    extra = {f"ca_x{i}": {"id": f"ca_x{i}", "status": "ACTIVE", "status_reason": None, "is_disabled": False, "toolkit": {"slug": slug}, "_user": user,
                          "auth_config": {"id": "ac_" + slug, "auth_scheme": "OAUTH2", "is_composio_managed": True, "is_disabled": False}, "word_id": None, "alias": None}
             for i, slug in enumerate(["notion", "github", "linear"])}
    MOCK["accounts"].update(extra)
    send(process, "pluginRefresh")
    home_stack(process)
    until(lambda: js(process, "document.querySelectorAll('.home-chips .plug-stack i').length") == 4 and js(process, "!!document.querySelector('.home-chips .plug-stack i.is-image img')"), 10)
    label, tiles_, last = home_stack(process, "plugins-stack.png")
    check(len(tiles_) == 4 and tiles_[-1] == "+2" and js(process, "document.querySelectorAll('.home-chips .plug-stack i.is-image img').length") == 3 and last,
          f"Five apps connected: three logos, then +2, at the right end of the home row ({tiles_})")
    check(label.startswith("Plugins: Gmail, Slack") and label.endswith(" connected"), f"and it names them for screen readers ({label!r})")
    js(process, "document.querySelector('.home-chips .home-plugins').click()")
    check(until(lambda: js(process, "!!document.querySelector('.home-page.plug-page')") and head(process) == "5 connected", 10), "It opens the Plugins page, which says 5 connected")
    js(process, "document.querySelector('.plug-count').click()")
    check(until(lambda: [t.split(":")[0] for t in tiles(process, "Connected")] == ["Gmail", "Slack", "Notion", "GitHub", "Linear"], 5), "and the count shows what's connected")
    for cid in extra:
        MOCK["accounts"].pop(cid)
    send(process, "pluginRefresh")
    until(lambda: head(process) == "2 connected", 10)


def no_key(process):
    label, tiles_, last = home_stack(process, "plugins-stack-empty.png")
    check(label == "Plugins: none connected yet" and tiles_ == ["icon"] and last, f"With nothing connected, the home row ends with Plugins and a plain plug ({label!r}, {tiles_})")
    check(open_plugins(process), "Plugins have their own page, on the home's rail")
    words = page_text(process)
    check(js(process, "document.querySelector('.plug-page h1')?.innerText") == "Plugins" and head(process) == "None connected", f"The page is titled Plugins, with what's connected at the top ({head(process)!r})")
    check(js(process, "document.querySelector(\".plug-page input[aria-label='Composio API key']\")?.type") == "password", "With no key, it asks for your Composio API key, right there")
    check(all(w in words for w in ("Get a key", "Platform", "Settings → Project Settings → API Keys", "ak_")), "The connect step says where the key comes from: Composio's Platform, Settings → Project Settings → API Keys, the one that starts with ak_")
    check("third-party service" in words and "pricing" not in words.lower(), "It says Composio is a third party, with no pricing in Still's words")
    listed = tiles(process)
    check(len(listed) == 24 and all(t.endswith(": Connect") for t in listed), f"With no key the apps still show, each with Connect ({len(listed)})")
    check(not js(process, "!!document.querySelector('.plug-tile small, .plug-tile p')"), "Tiles have no description under the name")
    until(lambda: js(process, "[...document.querySelectorAll('.plug-page .plug-logo img')].every(i => i.complete)"), 5)
    rpc(process, "capture", name="plugins-page.png")  # the page with no key: every app with the logo that ships with Still
    js(process, "document.querySelector('.plug-tile[data-slug=gmail] .plug-go')?.click()")
    check(until(lambda: js(process, "document.activeElement?.getAttribute('aria-label')") == "Composio API key", 3), "Connect with no key takes you to the key field")
    type_into(process, SEARCH, "sla")
    check(until(lambda: tiles(process) == ["Slack: Connect"], 5), "One search finds apps too")
    type_into(process, SEARCH, "")
    send(process, "openPanel", name="settings", value="plugins")
    until(lambda: js(process, "!!document.querySelector('.set-shell')"), 10)
    check(until(lambda: "Not set" in (js(process, "document.querySelector('.set-main #set-composio')?.innerText") or ""), 5)
          and js(process, "!!document.querySelector(\".set-main #set-composio input[aria-label='Composio API key']\")"), "Settings → Skills & plugins has the Composio key: not set, with a field to add it")
    js(process, "[...document.querySelectorAll('.set-main button')].find(b => b.innerText.trim() === 'Open Plugins')?.click()")
    check(until(lambda: not js(process, "!!document.querySelector('.set-shell')") and js(process, "!!document.querySelector('.home-page.plug-page')"), 10), "and a button that opens the Plugins page")
    ask(process, "NOPLUG")
    idle(process)
    done = until(lambda: len(calls("NOPLUG")) == 2 and calls("NOPLUG"), 20) or calls("NOPLUG")  # the run's first chat can start late
    check(len(done) == 2 and not any(c["ok"] for c in done) and all("Plugins page" in c["text"] for c in done), "Without a key, plugin tools say plugins are off and where to turn them on")
    check(not MOCK["seen"] and not MOCK["pages"], "Without a key, Still never calls Composio, not even for a logo")
    ask(process, "WEB " + SITE)
    idle(process)
    check([c["ok"] for c in calls("WEB " + SITE)] == [True], "Everything else works as usual")


def keys(process):
    send(process, "skillSave", name="Weekly report", description="Turns this week's numbers into a one-page summary", when="Reporting", body="1. Collect the numbers.")
    open_plugins(process)
    paste_key(process, CONSUMER)
    check(until(lambda: "Connect key (ck_…)" in page_text(process) and "starts with ak_" in page_text(process), 10), "A Connect key (ck_), what Composio's For You page shows, is named as the wrong kind, with the right one")
    check(not key_file().exists() and not any(s["key"] == CONSUMER for s in MOCK["seen"]), "It's never sent to Composio, and isn't kept")
    paste_key(process, WRONG)
    check(until(lambda: "didn't accept that key" in page_text(process), 10), "A key Composio refuses says so")
    check(not key_file().exists(), "and isn't kept")
    paste_key(process, KEY)
    check(until(lambda: len(tiles(process, "Recommended")) == 8 and not js(process, "!!document.querySelector(\".plug-page input[aria-label='Composio API key']\")"), 10), "A good key turns plugins on")
    check(key_file().exists(), "It's kept encrypted, " + ("for this Mac" if MAC else "with DPAPI") + ", like saved passwords")
    check(not js(process, f"document.documentElement.outerHTML.includes({json.dumps(KEY[-8:])}) || JSON.stringify(window.__stillState ?? {{}}).includes({json.dumps(KEY[-8:])})")
          and KEY[-4:] in page_text(process), "The field empties, and the interface only ever gets the key's last four characters")
    catalog = PROFILE / "plugin-catalog.json"
    saved = until(lambda: catalog.exists() and catalog.read_text(encoding="utf-8"), 10) or "{}"
    check(len(json.loads(saved).get("apps", [])) == len(TOOLKITS) and MOCK["catalog"][-2:] == ["", "page2"] and KEY not in saved,
          f"Composio's whole catalog loads page by page and is kept on this computer, without the key ({MOCK['catalog']})")
    rec = tiles(process, "Recommended")
    check([t.split(":")[0] for t in rec] == ["Gmail", "Google Calendar", "Slack", "Notion", "GitHub", "Linear", "Figma", "Stripe"] and all(t.endswith(": Connect") for t in rec),
          f"Recommended comes first: the most used apps Composio signs in to itself, each with Connect ({rec})")
    layout = js(process, """(() => { const t = [...document.querySelectorAll(".plug-group[aria-label='Recommended'] .plug-tile")].map(e => e.getBoundingClientRect())
     return [getComputedStyle(document.querySelector('.plug-tiles')).gridTemplateColumns.split(' ').length, Math.abs(t[0].top - t[1].top) < 2, t[2].top > t[0].top + 10] })()""")
    check(layout == [2, True, True], f"Apps sit two across ({layout})")
    chips = js(process, "[...document.querySelectorAll('.plug-page .history-chips .history-chip')].map(b => b.innerText.trim())") or []
    check(chips == ["All", "Productivity", "Communication", "Design", "Developer tools", "Finance", "Marketing", "More"], f"Category chips: All, the main categories, the rest under More ({chips})")
    groups = js(process, "[...document.querySelectorAll('.plug-page .plug-group')].map(g => g.getAttribute('aria-label') + ':' + g.querySelectorAll('.plug-tile').length)") or []
    check(groups[:2] == ["Recommended:8", "Productivity:4"] and groups[-1] == "Other:1" and len(groups) == 11, f"Then a section per category, and no skills with up to four apps ({groups})")
    check(until(lambda: js(process, "(imgs => imgs.length >= 3 && imgs.every(i => i.src.endsWith('/apps/' + i.closest('.plug-tile').dataset.slug + '.svg') && i.naturalWidth > 0))([...document.querySelectorAll('.plug-tile[data-slug=gmail] .plug-logo img, .plug-tile[data-slug=github] .plug-logo img, .plug-tile[data-slug=stripe] .plug-logo img')])"), 10),
          "Each app shows the logo that ships with Still")
    check(until(lambda: js(process, "(i => !!i && i.src.startsWith('data:image/svg+xml') && i.naturalWidth > 0)(document.querySelector('.plug-tile[data-slug=selfhosted] .plug-logo img'))"), 10),
          "An app newer than this build gets its logo from Composio's catalog, even when its server doesn't say it's an image")
    check(js(process, "document.querySelector('.plug-tile[data-slug=weather] .plug-logo')?.innerText") == "W", "A logo that doesn't load keeps the app's initial")
    fetched = sorted({p["path"] for p in MOCK["pages"] if p["path"].startswith("/logos/")})
    check(fetched == ["/logos/selfhosted", "/logos/weather"] and not any(p["key"] for p in MOCK["pages"] if p["path"].startswith("/logos/")) and (PROFILE / "Cache" / "PluginLogos" / "selfhosted").exists(),
          f"Only those two are fetched, without the key, and they stay on this computer ({fetched})")
    js(process, "document.querySelector(\".plug-group[aria-label='Productivity'] .plug-all\")?.click()")
    check(until(lambda: len(tiles(process, "Productivity")) == 7 and js(process, "[...document.querySelectorAll('.history-chip')].find(b => b.innerText.trim() === 'Productivity')?.getAttribute('aria-pressed')") == "true", 5),
          "View all shows the whole category, with its chip on")
    js(process, "[...document.querySelectorAll('.history-chip')].find(b => b.innerText.trim() === 'More')?.click()")
    js(process, "[...document.querySelectorAll('.history-chip')].find(b => b.innerText.trim() === 'Accounting')?.click()")
    check(until(lambda: tiles(process, "Accounting") == ["QuickBooks: Connect", "Xero: Connect"], 5), "More has the rest of the categories")
    js(process, "[...document.querySelectorAll('.history-chip')].find(b => b.innerText.trim() === 'All')?.click()")
    type_into(process, SEARCH, "cal")
    check(until(lambda: tiles(process, "Apps") == ["Google Calendar: Connect"], 5), "Search finds an app")
    type_into(process, SEARCH, "weekly")
    check(until(lambda: "No apps match" in page_text(process), 5) and not js(process, "!!document.querySelector(\".plug-group[aria-label='Skills']\")"), "and no skills: they're on the Skills page")
    type_into(process, SEARCH, "")
    MOCK["broken"] = True
    send(process, "pluginRefresh", force=True)
    check(until(lambda: "Invalid value for sort_by" in page_text(process), 5) and len(tiles(process, "Recommended")) == 8, "When Composio can't list its apps, it says why, and the saved list stays")
    MOCK["broken"] = False
    send(process, "pluginRefresh", force=True)
    until(lambda: "Invalid value" not in page_text(process), 5)


def connect(process):
    """The Composio connect flow."""
    MOCK["refuse_config"] = True
    js(process, "document.querySelector('.plug-tile[data-slug=googlecalendar] .plug-go')?.click()")
    check(until(lambda: "Google Calendar: Try again" in tiles(process, "Recommended") and "Google Calendar didn't connect: Composio managed auth isn't available" in page_text(process), 10), "Composio connect flow: a connect Composio refuses shows on that app, with Composio's reason")
    MOCK["refuse_config"] = False
    js(process, "document.querySelector('.plug-tile[data-slug=gmail] .plug-go')?.click()")
    sign_in(process, "Gmail")
    check(until(lambda: "Gmail: Connected" in tiles(process, "Recommended") and head(process) == "1 connected" and "didn't connect" not in page_text(process), 10), "Composio connect flow: Gmail shows a Connected check, and the top says 1 connected")
    account = next(iter(MOCK["accounts"].values()))
    check(account["_user"].startswith("still-") and MOCK["configs"].get("ac_gmail", {}).get("is_composio_managed"), "It uses Composio's own sign-in, for this profile's own user")
    manage(process, "gmail")
    who = js(process, "[...document.querySelectorAll('.plug-manage .plug-who button')].map(b => b.innerText.trim() + ':' + b.getAttribute('aria-pressed'))") or []
    check(who[:2] == ["Maya:true", "Nora:true"], f"The Connected check opens who can use it, a switch per companion ({who})")
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-face')"), 10)
    time.sleep(.4)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    js(process, "document.querySelector('.home-face')?.click()")
    until(lambda: js(process, "!!document.querySelector('.profile-tablist')"), 10)
    tabs = js(process, "document.querySelector('.profile-tablist')?.innerText.replace(/\\s+/g, ' ').trim()")
    js(process, "document.querySelector(\".profile-tablist [role=tab][id$='-trigger-skills']\")?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }))")
    check(until(lambda: js(process, "document.querySelector(\".profile-panel [role=switch][aria-label='Gmail for Maya']\")?.getAttribute('aria-checked')") == "true", 5) and "Plugins" not in tabs.replace("Skills & plugins", ""),
          f"A companion's profile has no Plugins tab; its Skills & plugins tab has a switch for Gmail ({tabs})")
    js(process, "document.querySelector('.profile-panel [aria-label=Close]')?.click()")
    until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 5)


def reads_and_writes(process):
    ask(process, "READMAIL")
    idle(process)
    done = calls("READMAIL")
    named = json.loads(done[0]["text"]) if done and done[0]["ok"] else None
    check(named == ["Gmail"], f"list_connected_plugins gives only the names of what's connected ({named})")
    listed = json.loads(done[1]["text"]) if len(done) > 1 and done[1]["ok"] else {}
    actions = {t["action"]: t["asksFirst"] for t in listed.get("actions", [])}
    check(actions == {"GMAIL_FETCH_EMAILS": False, "GMAIL_SEND_EMAIL": True} and listed.get("plugin") == "Gmail", f"get_plugin_tools loads Gmail's actions, by its name, and which ones ask first ({actions})")
    ran = [e for e in MOCK["executed"] if e["tool"] == "GMAIL_FETCH_EMAILS"]
    check(len(done) == 3 and done[2]["ok"] and "Contract signed" in done[2]["text"] and ran and ran[0]["arguments"] == {"query": "is:unread"}, "Reading mail goes ahead, no card, and the companion gets the mail")
    check(ran and ran[0]["connected_account_id"] == next(iter(MOCK["accounts"])) and ran[0]["user_id"].startswith("still-"), "It runs on the Gmail account you connected")

    ask(process, "SENDMAIL")
    card = until(lambda: cards(process), 20)
    check(card and "Send email in Gmail" in card[0] and "sam@example.com" in card[0], f"Sending an email waits on a card that says what and to whom ({card})")
    check(buttons(process) == ["Not now", "Allow"] and not js(process, "!!document.querySelector('.approve-card .approve-always')"), f"Its only choices are Not now and Allow ({buttons(process)})")
    press(process, "Not now")
    idle(process)
    ask(process, "LONGMAIL")
    card = until(lambda: cards(process), 20)
    shown = " ".join(card or [])
    check("sam@example.com" in shown and "copy@example.com" in shown and "tries: 2" in shown and "more characters not shown" in shown, f"The card shows everything the action carries, and says when it can't ({shown[:160]})")
    press(process, "Not now")
    idle(process)
    ask(process, "SENDMAIL")
    until(lambda: cards(process), 20)
    check(not [e for e in MOCK["executed"] if e["tool"] == "GMAIL_SEND_EMAIL"], "Nothing is sent while it waits")
    press(process, "Not now")
    idle(process)
    check(calls("SENDMAIL")[-1]["ok"] is False and not [e for e in MOCK["executed"] if e["tool"] == "GMAIL_SEND_EMAIL"], "Deny: nothing is sent, and the companion is told no")
    ask(process, "SENDMAIL")
    until(lambda: cards(process), 20)
    press(process, "Allow")
    idle(process)
    sent = [e for e in MOCK["executed"] if e["tool"] == "GMAIL_SEND_EMAIL"]
    check(len(sent) == 1 and sent[0]["arguments"]["to"] == "sam@example.com" and calls("SENDMAIL")[-1]["ok"], "Allow: it's sent, once")
    ask(process, "SENDMAIL")
    check(until(lambda: cards(process), 20), "The next send asks again: no silent sends")
    press(process, "Not now")
    idle(process)

    open_plugins(process)
    manage(process, "gmail")
    js(process, "document.querySelector('.plug-manage .plug-who button')?.click()")  # Maya
    until(lambda: js(process, "document.querySelector('.plug-manage .plug-who button')?.getAttribute('aria-pressed')") == "false", 5)
    close_panel(process)
    check(until(lambda: "gmail" in turned_off("maya"), 5), "Turning Gmail off for Maya is saved")
    before = len(MOCK["executed"])
    ask(process, "READMAIL")
    idle(process)
    check(calls("READMAIL")[-1]["ok"] is False and "turned Gmail off for you" in calls("READMAIL")[-1]["text"] and len(MOCK["executed"]) == before, "Then Maya can't use Gmail, and is told why")
    asked = len(calls("READMAIL"))
    ask(process, "HELPMAIL")
    until(lambda: len(calls("READMAIL")) > asked, 40)
    idle(process)
    check(len(calls("READMAIL")) > asked and calls("READMAIL")[-1]["ok"] is False and "turned Gmail off for you" in calls("READMAIL")[-1]["text"] and len(MOCK["executed"]) == before, "...and Nora can't use it on Maya's behalf")
    open_plugins(process)
    manage(process, "gmail")
    js(process, "document.querySelector('.plug-manage .plug-who button')?.click()")
    until(lambda: js(process, "document.querySelector('.plug-manage .plug-who button')?.getAttribute('aria-pressed')") == "true", 5)
    close_panel(process)


def finds(process):
    ask(process, "FINDAPPS")
    idle(process)
    done = calls("FINDAPPS")
    got = [json.loads(c["text"]) if c["ok"] else c["text"] for c in done]
    check(len(got) == 4 and got[0] == {"apps": [{"name": "Google Calendar", "categories": ["Productivity"], "connected": False}], "more": 0}, f"find_plugins finds an app by name: its name, categories and whether it's connected ({got[:1]})")
    check(len(got) == 4 and [a["name"] for a in got[1]["apps"]] == ["Stripe", "QuickBooks"], f"and by category ({got[1:2]})")
    check(len(done) == 4 and not done[2]["ok"] and "find_plugins" in done[2]["text"], "An app that doesn't exist sends the companion to find_plugins")
    check(len(done) == 4 and not done[3]["ok"] and "no action called GMAIL_SEND_EMAIL" in done[3]["text"] and not cards(process) and not [e for e in MOCK["executed"] if e["tool"] == "GMAIL_SEND_EMAIL" and e["arguments"].get("to") == "x@example.com"],
          "Another app's action isn't run under the wrong app, and no card comes up")


def missing(process):
    ask(process, "SLACK")
    card = until(lambda: cards(process), 20)
    head = js(process, "document.querySelector('.approve-card .ask-q')?.innerText.trim()")
    check(card and "Connect Slack" in card[0] and head == "Maya needs Slack for this." and buttons(process) == ["Not now", "Connect Slack"], f"Slack isn't connected: Maya says it needs it, with a button that connects it ({head}; {buttons(process)})")
    press(process, "Not now")
    idle(process)
    check(calls("SLACK")[-1]["ok"] is False and not [e for e in MOCK["executed"] if e["tool"] == "SLACK_SEND_MESSAGE"], "Not now: nothing connects and nothing is posted")
    ask(process, "SLACK")
    until(lambda: cards(process), 20)
    press(process, "Connect Slack")
    sign_in(process, "Slack")
    card = until(lambda: (c := cards(process)) and "Send message in Slack" in c[0] and c, 20)
    check(card, "Once Slack is connected, the post itself still asks first")
    press(process, "Allow")
    idle(process)
    check(calls("SLACK")[-1]["ok"] and [e for e in MOCK["executed"] if e["tool"] == "SLACK_SEND_MESSAGE"], "Then it's posted")


def secret(process):
    ask(process, "PEEK")
    idle(process)
    seen = calls("PEEK")
    check(len(seen) == 2 and KEY not in seen[0]["text"], "The key isn't in the AI app's environment, arguments or instructions")
    listed = [t["name"] for t in json.loads(seen[1]["text"]).get("tools", [])] if len(seen) == 2 else []
    check({"list_connected_plugins", "find_plugins", "get_plugin_tools", "run_plugin_action"} <= set(listed) and "plugin_tools" not in listed and "use_plugin" not in listed and KEY not in seen[1]["text"],
          "Companions get list_connected_plugins, find_plugins, get_plugin_tools and run_plugin_action, and no tool hands out the key")
    check(len(seen) == 2 and "GMAIL_FETCH_EMAILS" not in seen[0]["text"] and "GMAIL_FETCH_EMAILS" not in seen[1]["text"], "No app's actions are in a companion's instructions or tool list until it asks for that app")
    every = [json.loads(line) for line in (BIN / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.endswith("}")]
    check(not any(KEY in c["text"] for c in every), "No tool result ever has the key")
    check(not nowhere(), f"The key isn't in any file in the profile in the clear ({nowhere()})")
    check(all(s["key"] in (KEY, WRONG, KEY2) for s in MOCK["seen"] if s["key"]) and not any(p["key"] for p in MOCK["pages"]), "It only ever goes to Composio's API, never to a page, and a Connect key never goes anywhere")


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
    manage(process, "gmail")
    js(process, "[...document.querySelectorAll('.plug-manage button')].find(b => b.innerText.trim() === 'Disconnect')?.click()")
    until(lambda: js(process, "!!document.querySelector('[data-slot=alert-dialog-action]')"), 3)
    js(process, "document.querySelector('[data-slot=alert-dialog-action]')?.click()")
    check(until(lambda: len(MOCK["deleted"]) == 1 and head(process) == "1 connected", 15), "Disconnect asks, then removes the account at Composio and from the page")
    send(process, "openPanel", name="settings", value="skills")
    row = lambda: js(process, "document.querySelector('.set-main #set-composio')?.innerText") or ""
    check(until(lambda: "ending in" in row() and KEY[-4:] in row(), 10) and not js(process, f"document.documentElement.outerHTML.includes({json.dumps(KEY[-8:])})"),
          "Settings shows the key only as set, with its last four characters")
    js(process, "[...document.querySelectorAll('#set-composio button')].find(b => b.innerText.trim() === 'Change')?.click()")
    until(lambda: js(process, "!!document.querySelector(\"#set-composio input[aria-label='Composio API key']\")"), 5)
    paste_key(process, WRONG, ".set-main #set-composio")
    check(until(lambda: "didn't accept that key" in row(), 10) and key_file().exists() and KEY[-4:] in row(), "Change: a key Composio refuses doesn't replace the one that works")
    paste_key(process, KEY2, ".set-main #set-composio")
    check(until(lambda: KEY2[-4:] in row() and not js(process, "!!document.querySelector('#set-composio input')"), 10) and until(lambda: MOCK["seen"][-1]["key"] == KEY2, 5),
          "and a good one does: Composio gets the new key from then on")
    js(process, "[...document.querySelectorAll('#set-composio button')].find(b => b.innerText.trim() === 'Delete')?.click()")
    check(until(lambda: "Delete the Composio key?" in (js(process, "document.querySelector('[data-slot=alert-dialog-content]')?.innerText") or ""), 5) and key_file().exists(), "Delete asks first")
    js(process, "document.querySelector('[data-slot=alert-dialog-action]')?.click()")
    check(until(lambda: not key_file().exists() and "Not set" in row() and js(process, "!!document.querySelector(\"#set-composio input[aria-label='Composio API key']\")"), 15),
          "Delete forgets the key, and Settings offers the field again")
    check(len(MOCK["deleted"]) == 1 and not nowhere(), "Your apps stay connected in your Composio account, and no key is left in any file")
    close_panel(process)
    open_plugins(process)
    check(until(lambda: head(process) == "None connected" and js(process, "!!document.querySelector(\".plug-page input[aria-label='Composio API key']\")"), 10), "Plugins are off: nothing connected, and the page asks for a key")
    ask(process, "NOPLUG")
    idle(process)
    check(not any(c["ok"] for c in calls("NOPLUG")), "and companions are back to plugins off")


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
