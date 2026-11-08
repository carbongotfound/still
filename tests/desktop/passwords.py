"""The password manager: save, update, fill, several accounts, two-step sign-in, the strong-password suggestion, Never
for this site, auto sign-in, insecure pages, cross-site frames, private tabs, Windows Hello / Touch ID before a password
shows (answered by the QA hook), CSV export, import from CSV, Firefox and Chrome, and that AIs (MCP, CLI, companions'
memory) never get a password: no tool lists one, fields holding a saved login read as hidden, and a sign-in page
pauses the AI until the user signs in and hands it back.

Run: python tests/desktop/passwords.py <Still.exe or Still.app/Contents/MacOS/Still>
Out: artifacts/passwords-*/ (result.json, shots/*.png: save prompt, fill menu and Passwords, light and dark)
"""
import csv
import hashlib
import csv
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
import traceback
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, text, until  # noqa: E402
from mcp_client import Mcp  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("passwords-" + uuid.uuid4().hex[:8])
PROFILE, BIN, SHOTS = RUN / "profile", RUN / "bin", RUN / "shots"
RESULT = {"checks": []}
FIXTURES = Path(__file__).parent / "fixtures"
SAFE_STORAGE = "qa-safe-storage"  # on the Mac, the key Chrome keeps in the Keychain (test builds take it from the environment)


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


FORM = "<!doctype html><meta charset=utf-8><title>{title}</title><style>body{{font:16px system-ui;margin:40px}}input{{display:block;font:inherit;padding:8px;width:300px;margin:8px 0}}button{{font:inherit;padding:8px 16px}}</style><h1>{title}</h1>{body}"
PAGES = {
    "/login": ("Sign in", '<form method=post action=/welcome><input id=user name=username autocomplete=username aria-label=Email placeholder=Email>'
               '<input id=pw name=password type=password autocomplete=current-password aria-label=Password placeholder=Password><button id=go>Sign in</button></form>'),
    "/signup": ("Create your account", '<form method=post action=/welcome><input id=user name=email autocomplete=email aria-label=Email placeholder=Email>'
                '<input id=pw name=password type=password autocomplete=new-password aria-label="New password" placeholder="New password"><button id=go>Create account</button></form>'),
    "/change": ("Change password", '<form method=post action=/welcome><input id=user name=username autocomplete=username aria-label=Email placeholder=Email>'
                '<input id=cur type=password autocomplete=current-password aria-label="Current password"><input id=new type=password autocomplete=new-password aria-label="New password">'
                '<input id=again type=password autocomplete=new-password aria-label="Confirm new password"><button id=go>Change password</button></form>'),
    "/step1": ("Sign in", '<form method=get action=/step2><input id=user name=identifier autocomplete=username aria-label=Email placeholder=Email><button id=go>Next</button></form>'),
    "/step2": ("Enter your password", '<form method=post action=/welcome><input id=pw type=password autocomplete=current-password aria-label=Password><button id=go>Sign in</button></form>'),
    "/frame": ("A page with a sign-in frame", '<p>The frame below is another site.</p><iframe id=f src="{other}/login" style="width:420px;height:320px;border:1px solid #ccc"></iframe>'),
    "/ghost": ("Sign in", '<form method=post action=/welcome><input id=user name=username autocomplete=username style="opacity:.01"><input id=pw name=password type=password autocomplete=current-password style="opacity:.01"><button id=go>Sign in</button></form>'),
    "/trap": ("Sign in", '<form method=post action=/welcome><input id=user name=username autocomplete=username><input id=pw name=password type=password autocomplete=current-password><button id=go>Sign in</button></form>'
              '<script>window.__stolen=[];if(window.chrome?.webview){const real=chrome.webview.postMessage;chrome.webview.postMessage=function(m){__stolen.push(JSON.stringify(m));return real.call(this,m)}}'
              'const bind=Function.prototype.bind;Function.prototype.bind=function(...a){__stolen.push("bind");return bind.apply(this,a)};'
              'Object.prototype.toJSON=function(){if(this.token)__stolen.push(this.token);return this};</script>'),
    "/stands-in": ("Sign in", '<form method=post action="{other}/welcome"><input type=hidden name=action value=/welcome><input id=user name=username autocomplete=username><input id=pw name=password type=password autocomplete=current-password><button id=go>Sign in</button></form>'),
    "/button-away": ("Sign in", '<form method=post action=/welcome><input id=user name=username autocomplete=username><input id=pw name=password type=password autocomplete=current-password><button id=go formaction="{other}/welcome">Sign in</button></form>'),
    "/welcome": ("Welcome back", "<p>You're signed in.</p>"),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def page(self):
        title, body = PAGES.get(self.path.split("?")[0], PAGES["/welcome"])
        data = FORM.format(title=title, body=body.replace("{other}", OTHER)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.page()

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.page()

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
PORT = SERVER.server_port
SITE = f"http://127.0.0.1:{PORT}"          # this computer: treated as secure
OTHER = f"http://localhost:{PORT}"         # another site, also on this computer
# An ordinary http site: on Windows a name mapped to 127.0.0.1 for the browser; on the Mac "localhost." with its
# dot, which reaches this computer but isn't one of the names Still trusts as it.
INSECURE = f"http://localhost.:{PORT}" if MAC else f"http://insecure.test:{PORT}"

# A companion that only remembers (see memory.py): its MCP call shows whether Still keeps a saved password.
FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def say(e): print(json.dumps(e), flush=True)
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
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    fact = prompt.strip().splitlines()[-1].partition("REMEMBER: ")[2]
    r = request("tools/call", {"name": "remember", "arguments": {"fact": fact, "kind": "preference"}})["result"]
    with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"error": bool(r.get("isError")), "text": r["content"][0]["text"]}) + "\n")
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay."}]}})
    still.stdin.close()
''')

# ---- the page, used as a person would: trusted clicks and typing ----
LISTEN = """window.__msgs = []; window.__tools = {};
window.chrome.webview.addEventListener('message', e => { const d = e.data; if (d?.kind === 'tools') __tools[d.name] = d.data; else if (/^vault/.test(d?.kind || '')) __msgs.push(d) })"""


def page(process, script):
    return rpc(process, "eval", script=script)


def rect(process, selector):
    return page(process, f"(() => {{ const r = document.querySelector({json.dumps(selector)})?.getBoundingClientRect(); return r ? {{x: r.x, y: r.y, h: r.height, bottom: r.bottom}} : null }})()")


def click_at(process, x, y):
    for kind in ("mousePressed", "mouseReleased"):
        rpc(process, "pageCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})


def click(process, selector):
    r = rect(process, selector)
    click_at(process, r["x"] + 20, r["y"] + r["h"] / 2)


def type_into(process, selector, value):
    click(process, selector)
    time.sleep(.15)
    rpc(process, "pageCdp", method="Input.insertText", parameters={"text": value})


def values(process, *selectors):
    return [page(process, f"document.querySelector({json.dumps(s)})?.value ?? null") for s in selectors]


def helper(process):
    """Still's login helper in the page: in the page itself on Windows, in Still's own script world on the Mac."""
    return rpc(process, "eval", script="typeof window.__stillLoginCleanup", world="still")


def settle(process):
    """The page has loaded, reported its form, and Still has answered with this site's logins."""
    until(lambda: page(process, "document.readyState") == "complete" and helper(process) == "function", 10)
    time.sleep(.6)


def go(process, url):
    send(process, "navigate", url=url)
    until(lambda: page(process, "location.href") == url, 15)
    settle(process)


def shadow(process, **want):
    """Centre of a button in Still's closed menu in the page, found through DevTools (which sees closed shadow roots)."""
    if MAC:
        return None
    stack = [rpc(process, "pageCdp", method="DOM.getDocument", parameters={"depth": -1, "pierce": True})["root"]]
    while stack:
        node = stack.pop(0)
        raw = node.get("attributes", [])
        attrs = dict(zip(raw[::2], raw[1::2]))
        if node.get("nodeName", "").lower() == "button" and all(attrs.get(k) == v for k, v in want.items()):
            quad = rpc(process, "pageCdp", method="DOM.getBoxModel", parameters={"nodeId": node["nodeId"]})["model"]["border"]
            rpc(process, "pageCdp", method="DOM.disable", parameters={})
            return ((quad[0] + quad[2]) / 2, (quad[1] + quad[5]) / 2)
        stack += node.get("children", []) + node.get("shadowRoots", [])
    rpc(process, "pageCdp", method="DOM.disable", parameters={})  # getDocument turned DevTools' DOM tracking on: leave the page as it was
    return None


def menu_item(process, field, index, warned=False, **want):
    """A row of the menu under a field: found exactly on Windows, from the menu's fixed layout on the Mac (an insecure page's warning sits above the rows)."""
    if not MAC:
        return shadow(process, **want)
    r = rect(process, field)
    return (r["x"] + 40, r["bottom"] + 6 + 1 + 6 + (59 if warned else 0) + 49 * index + 24) if page(process, "!!document.querySelector('still-passwords')") else None


def has_key(process):
    if MAC:
        return page(process, "!!document.querySelector('still-passwords')")
    return shadow(process, **{"aria-label": "Saved passwords"}) is not None


def pick(process, field, index, login, warned=False, wait=.7):
    """Opens the menu under a field and clicks one of its logins."""
    page(process, "document.activeElement?.blur()")
    click(process, field)
    at = until(lambda: menu_item(process, field, index, warned, **{"data-id": login["id"]}), 5)
    if at:
        time.sleep(wait)
        click_at(process, *at)
    return at


# ---- Still's side ----
def bar(process):
    return js(process, "document.querySelector('.permission-wrap.is-open .save-login')?.textContent ?? ''")


def bar_button(process, label):
    js(process, f"[...document.querySelectorAll('.save-login button')].find(b => b.innerText === {json.dumps(label)}).click()")
    until(lambda: not bar(process), 5)


def vault(process):
    js(process, "window.__tools.passwords = null")
    send(process, "refreshTools", name="passwords")
    return until(lambda: js(process, "window.__tools.passwords?.vault ?? null"), 5) or []


def entry(process, origin, username):
    return next((v for v in vault(process) if v["origin"] == origin and v["username"] == username), None)


def reveal(process, item):
    rpc(process, "osAuth", answer="allow")
    send(process, "vaultReveal", id=item["id"])
    return until(lambda: js(process, f"__msgs.filter(m => m.kind === 'vaultRevealed' && m.id === {json.dumps(item['id'])}).pop()?.password ?? null"), 5)


def row(username, script):
    """Runs script with `r` as the Passwords row for username."""
    return f"(r => {script})([...document.querySelectorAll('.password-row')].find(r => r.querySelector('small')?.innerText === {json.dumps(username)}))"


def shot(process, name):
    rpc(process, "capture", name=name + ".png")
    until(lambda: (PROFILE / (name + ".png")).exists(), 5)
    shutil.copy(PROFILE / (name + ".png"), SHOTS / (name + ".png"))


def themed(process, name, setup):
    for theme in ("Light", "Dark"):
        send(process, "preference", key="theme", value=theme)
        time.sleep(.6)
        setup()
        time.sleep(.6)
        shot(process, f"{'mac' if MAC else 'win'}-{name}-{theme.lower()}")
    send(process, "preference", key="theme", value="Light")


def plain_text_anywhere(needle):
    """A file in the profile holding needle as plain text (UTF-8 or UTF-16), if any."""
    for path in PROFILE.rglob("*"):
        try:
            if path.is_file() and path.suffix != ".png" and path.stat().st_size < 20_000_000:
                data = path.read_bytes()
                if needle.encode() in data or needle.encode("utf-16-le") in data:
                    return str(path.relative_to(PROFILE))
        except OSError:
            pass
    return None


def account_login(folder, sealed):
    """Chrome signed in to an account keeps that account's passwords in a second file."""
    db = sqlite3.connect(folder / "Login Data For Account")
    db.execute("CREATE TABLE logins (origin_url TEXT, username_value TEXT, password_value BLOB, blacklisted_by_user INTEGER)")
    db.execute("INSERT INTO logins VALUES ('https://account.example/', 'synced', ?, 0)", (sealed,))
    db.commit()
    db.close()


def chrome_profile(folder):
    """A Chrome profile with one login Windows can decrypt and one locked by Chrome's app-bound encryption."""
    import ctypes
    import ctypes.wintypes as wt

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def protect(plain):
        buf = ctypes.create_string_buffer(plain, len(plain))
        out = Blob()
        assert ctypes.windll.crypt32.CryptProtectData(ctypes.byref(Blob(len(plain), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))), None, None, None, None, 0, ctypes.byref(out))
        got = ctypes.string_at(out.pbData, out.cbData)
        ctypes.windll.kernel32.LocalFree(out.pbData)
        return got
    sealed = protect(b"Chrome-dpapi-77")
    folder.mkdir(parents=True)
    db = sqlite3.connect(folder / "Cookies")
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO meta VALUES ('version', '24')")
    db.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB, path TEXT, expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER, samesite INTEGER, has_expires INTEGER)")
    db.execute("INSERT INTO cookies VALUES ('chrome.example', 'own', '', ?, '/', 0, 0, 0, 1, 0)", (protect(hashlib.sha256(b"chrome.example").digest() + b"here"),))
    db.execute("INSERT INTO cookies VALUES ('moved.example', 'moved', '', ?, '/', 0, 0, 0, 1, 0)", (protect(hashlib.sha256(b"chrome.example").digest() + b"another site's"),))
    db.commit()
    db.close()
    (folder / "Bookmarks").write_text(json.dumps({"roots": {"bookmark_bar": {"children": [{"type": "url", "name": "Chrome page", "url": "https://chrome.example/"}]}}}))
    db = sqlite3.connect(folder / "Login Data")
    db.execute("CREATE TABLE logins (origin_url TEXT, username_value TEXT, password_value BLOB, blacklisted_by_user INTEGER)")
    db.execute("INSERT INTO logins VALUES ('https://chrome.example/login', 'chromie', ?, 0)", (sealed,))
    db.execute("INSERT INTO logins VALUES ('https://bound.example/', 'locked', ?, 0)", (b"v20" + os.urandom(60),))
    db.commit()
    db.close()
    account_login(folder, sealed)


def mac_chrome_profile(folder):
    """A Chrome profile on the Mac with one login and two sign-in cookies for this computer's test site (one only the
    server sees), sealed with the key Chrome keeps in the Keychain (AES-128-CBC, v10)."""
    key = hashlib.pbkdf2_hmac("sha1", SAFE_STORAGE.encode(), b"saltysalt", 1003, 16)

    def seal(plain):
        return b"v10" + subprocess.run(["openssl", "enc", "-aes-128-cbc", "-K", key.hex(), "-iv", "20" * 16], input=plain, capture_output=True, check=True).stdout
    sealed = seal(b"Chrome-keychain-77")[3:]
    folder.mkdir(parents=True)
    (folder / "Bookmarks").write_text(json.dumps({"roots": {"bookmark_bar": {"children": [{"type": "url", "name": "Chrome page", "url": "https://chrome.example/"}]}}}))
    db = sqlite3.connect(folder / "Login Data")
    db.execute("CREATE TABLE logins (origin_url TEXT, username_value TEXT, password_value BLOB, blacklisted_by_user INTEGER)")
    db.execute("INSERT INTO logins VALUES ('https://chrome.example/login', 'chromie', ?, 0)", (b"v10" + sealed,))
    db.commit()
    db.close()
    account_login(folder, b"v10" + sealed)
    # Since Chrome's cookie database version 24, each value starts with SHA-256 of its host.
    db = sqlite3.connect(folder / "Cookies")
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("INSERT INTO meta VALUES ('version', '24')")
    db.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB, path TEXT, expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER, samesite INTEGER, has_expires INTEGER)")
    host, later = b"127.0.0.1", int((time.time() + 86400 + 11_644_473_600) * 1_000_000)
    db.execute("INSERT INTO cookies VALUES ('127.0.0.1', 'chromesid', '', ?, '/', ?, 0, 0, 1, 1)", (seal(hashlib.sha256(host).digest() + b"Session-keychain-55"),later))
    db.execute("INSERT INTO cookies VALUES ('127.0.0.1', 'chromehttp', '', ?, '/', 0, 0, 1, -1, 0)", (seal(hashlib.sha256(host).digest() + b"server-only"),))
    db.execute("INSERT INTO cookies VALUES ('moved.example', 'moved', '', ?, '/', 0, 0, 0, 1, 0)", (seal(hashlib.sha256(host).digest() + b"another site's"),))
    db.commit()
    db.close()


def stage_profile(process, path, name, picked=False):
    js(process, "window.__tools.import = null")
    rpc(process, "stageExternalProfile", path=str(path), name=name, picked=picked)
    return until(lambda: js(process, "window.__tools.import?.external?.preview ?? null"), 15)


def main():
    for d in (PROFILE / "agents", BIN, SHOTS):
        d.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {
        # Edge's own form autofill stays off: closing a tab while its suggestion list is open crashes
        # the engine (WebView2 156, also on builds without saved passwords). Still's passwords don't use it.
        "Autofill": False,
        "Companions": CREW, "AiHarness": "fake", "AgentsEnabled": True, "ApprovedAgents": ["Claude"],
        "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}]},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = dict(os.environ, STILL_QA_BROWSER_ARGS='--host-resolver-rules="MAP insecure.test 127.0.0.1"', STILL_QA_SAFE_STORAGE=SAFE_STORAGE)
    process = launch(EXE, PROFILE, env)
    agent = None
    try:
        js(process, LISTEN)
        rpc(process, "osAuth", answer="deny", exportPath=str(RUN / "export.csv"))

        # Save: sign in on a site, and Still offers to save, with both fields editable.
        go(process, SITE + "/login")
        type_into(process, "#user", "ada@example.com")
        type_into(process, "#pw", "Lighthouse-Keeper-42")
        click(process, "#go")
        offered = until(lambda: bar(process), 8)
        check(offered and "Save your password for" in offered and "127.0.0.1" in offered, "Signing in offers to save the password")
        check(js(process, "document.querySelector('.save-login input[aria-label=Username]')?.value") == "ada@example.com"
              and js(process, "document.querySelector('.save-login input[type=password]')?.value") == "Lighthouse-Keeper-42", "The prompt shows the username and password, ready to edit")
        themed(process, "save-prompt", lambda: None)
        js(process, "document.querySelector('.save-login button[type=submit]').click()")
        until(lambda: not bar(process), 5)
        # The notice in the address bar is for the page it came on: going to another page, opening a new tab or switching
        # tabs shows that tab's address at once.
        def address():
            return js(process, "document.querySelector('.address-bar:not(.is-editing) .address-input')?.value ?? null")

        def notice_ends(move, want):
            shown = until(lambda: "Password saved" in (address() or ""), 3)
            move()
            return bool(shown) and until(lambda: address() == want, 1.5) is not None
        here = f"127.0.0.1:{PORT}/welcome?next=1"
        moved = notice_ends(lambda: go(process, SITE + "/welcome?next=1"), here)
        home = rpc(process)["activeId"]

        def resave():
            send(process, "vaultSave", origin="https://notice.example", username="notice", password="Notice-Only-1")
        resave()
        count = len(rpc(process)["tabs"])

        def new_tab():
            send(process, "new")
            until(lambda: len(rpc(process)["tabs"]) == count + 1, 5)
            js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        opened = notice_ends(new_tab, "")
        fresh = rpc(process)["activeId"]
        resave()
        switched = notice_ends(lambda: send(process, "select", id=home), here)
        send(process, "closeTab", id=fresh)
        send(process, "vaultDelete", id=entry(process, "https://notice.example", "notice")["id"])
        check(moved and opened and switched, "A notice in the address bar ends when you go to another page, open a new tab or switch tabs"
              + ("" if moved and opened and switched else f" (page {moved}, new tab {opened}, switch {switched})"))
        ada = entry(process, SITE, "ada@example.com")
        check(ada and reveal(process, ada) == "Lighthouse-Keeper-42", "Save keeps the login")
        if not MAC:
            found = plain_text_anywhere("Lighthouse-Keeper-42")
            check((PROFILE / "logins.dpapi").exists() and not found, "It's encrypted: the password isn't in plain text anywhere in the profile" + (f" (found in {found})" if found else ""))

        # Update: a change-password form updates the saved login.
        go(process, SITE + "/change")
        type_into(process, "#user", "ada@example.com")
        type_into(process, "#cur", "Lighthouse-Keeper-42")
        type_into(process, "#new", "Lighthouse-Keeper-43")
        type_into(process, "#again", "Lighthouse-Keeper-43")
        click(process, "#go")
        offered = until(lambda: bar(process), 8)
        check(offered and "Update your password for" in offered, "Changing a password offers to update the saved one")
        js(process, "document.querySelector('.save-login button[type=submit]').click()")
        until(lambda: not bar(process), 5)
        check(len([v for v in vault(process) if v["origin"] == SITE]) == 1 and reveal(process, entry(process, SITE, "ada@example.com")) == "Lighthouse-Keeper-43",
              "Update replaces the password and keeps one login")

        # Fill: the key in the field opens this site's logins; a click fills.
        go(process, SITE + "/login")
        click(process, "#user")
        check(until(lambda: has_key(process), 5), "A saved login puts a key in the field")
        ada = entry(process, SITE, "ada@example.com")
        pick(process, "#user", 0, ada)
        check(until(lambda: values(process, "#user", "#pw") == ["ada@example.com", "Lighthouse-Keeper-43"], 5), "Picking the login fills the username and password")

        # Several accounts: the menu lists each one.
        send(process, "vaultSave", origin=SITE, username="grace@example.com", password="Compiler-Admiral-06")
        time.sleep(.5)
        grace = entry(process, SITE, "grace@example.com")
        go(process, SITE + "/login")
        click(process, "#user")
        listed = MAC or until(lambda: all(shadow(process, **{"data-id": v["id"]}) for v in (ada, grace)), 5)
        check(until(lambda: has_key(process), 5) and listed, "With two saved logins the menu lists both")
        themed(process, "fill-menu", lambda: (go(process, SITE + "/login"), click(process, "#user")))
        pick(process, "#user", 1, grace)
        check(until(lambda: values(process, "#user", "#pw") == ["grace@example.com", "Compiler-Admiral-06"], 5), "Picking the second login fills that one")

        # The page itself: focusing a field gets it no names, and a list it hides or covers fills nothing.
        go(process, SITE + "/login")
        page(process, "document.querySelector('#user').focus()")
        time.sleep(.8)
        check(not has_key(process), "A field the page focuses by itself shows no saved accounts")
        go(process, SITE + "/login")
        pick(process, "#user", 0, ada, wait=0)
        time.sleep(.6)
        check(values(process, "#user", "#pw") == ["", ""], "A click the moment the list appears fills nothing")
        tricks = [("still-passwords{opacity:0!important}", "A list the page made see-through fills nothing"), ("body{opacity:.05}", "A list on a page faded out fills nothing")]
        if not MAC:  # Safari can't tell about something laid over the list that lets clicks through
            tricks.append((None, "A list with something laid over it fills nothing"))
        for rule, name in tricks:
            go(process, SITE + "/login")
            page(process, f"document.head.insertAdjacentHTML('beforeend', '<style>{rule}</style>')" if rule else
                 "document.documentElement.insertAdjacentHTML('beforeend', '<div style=\"position:fixed;inset:0;z-index:2147483647;background:#fff;pointer-events:none\"></div>')")
            pick(process, "#user", 0, ada)
            time.sleep(.6)
            check(values(process, "#user", "#pw") == ["", ""], name)
            if "see-through" in name:
                check("covering" in (until(lambda: js(process, "document.body.innerText.includes('covering') ? 'covering' : ''"), 3) or ""), "...and Still says why")

        # Auto sign-in: one saved login fills at the first touch; with two, it never guesses.
        send(process, "passwordPermission", feature="fill", enabled=True)
        time.sleep(.5)
        go(process, SITE + "/login")
        check(values(process, "#user", "#pw") == ["", ""], "Auto sign-in never guesses between two logins")
        send(process, "vaultDelete", id=grace["id"])
        time.sleep(.5)
        go(process, SITE + "/login")
        time.sleep(1)
        check(values(process, "#user", "#pw") == ["", ""], "Auto sign-in doesn't fill as the page opens")
        page(process, "document.querySelector('#pw').focus(); document.querySelector('#pw').click()")
        time.sleep(1)
        check(values(process, "#user", "#pw") == ["", ""], "...and the page's own script can't set it off")
        click(process, "#user")
        check(until(lambda: values(process, "#user", "#pw") == ["ada@example.com", "Lighthouse-Keeper-43"], 5), "Your first click in the field fills the only login")
        go(process, SITE + "/ghost")
        click(process, "#pw")
        time.sleep(1)
        check(values(process, "#user", "#pw") == ["", ""], "Auto sign-in leaves a field nobody can see alone, even at a click")

        # A page's own scripts: a changed setting doesn't run the helper again in a page already going, where they could catch it.
        send(process, "passwordPermission", feature="fill", enabled=False)
        go(process, SITE + "/trap")
        click(process, "#user")
        time.sleep(.3)
        send(process, "passwordPermission", feature="fill", enabled=True)
        time.sleep(.5)
        send(process, "passwordPermission", feature="fill", enabled=False)
        time.sleep(.8)
        page(process, "document.querySelector('#pw').insertAdjacentHTML('afterend', '<input type=password autocomplete=new-password>')")
        time.sleep(.8)
        check(page(process, "__stolen.filter(x => x !== 'bind' && /[0-9a-f]{32}/.test(x)).length") == 0 and page(process, "__stolen.includes('bind')") is False, "A changed setting gives a page's own scripts nothing to catch")
        go(process, SITE + "/login")
        at = pick(process, "#user", 0, ada)
        check(until(lambda: values(process, "#user", "#pw") == ["ada@example.com", "Lighthouse-Keeper-43"], 5), "...and the helper works as before after it")
        send(process, "passwordPermission", feature="fill", enabled=True)
        time.sleep(.5)

        # Where a form really sends what's in it. A field named "action" can't stand in for its address, nor one button's address go unseen.
        send(process, "passwordPermission", feature="fill", enabled=False)
        time.sleep(.3)
        for where, name in (("/stands-in", "A field named action can't hide where a form goes"), ("/button-away", "A button that sends it to another site counts")):
            go(process, SITE + where)
            pick(process, "#user", 0, ada)
            time.sleep(1)
            check(values(process, "#user", "#pw") == ["", ""], name)
        send(process, "passwordPermission", feature="fill", enabled=True)
        time.sleep(.5)

        # Strong passwords: the length asked for, every character from the list.
        helper_source = (ROOT / "still" / "Assets" / "LoginObserver.js").read_text(encoding="utf-8")
        strong = helper_source[helper_source.index("function strong"):helper_source.index("  function ui()")]
        bad = page(process, "(() => { const random = crypto.getRandomValues.bind(crypto); " + strong + " let bad = 0; for (let i = 0; i < 400; i++) { const p = strong(20); if (p.length !== 20 || /undefined/.test(p)) bad++; } return bad })()")
        check(bad == 0, f"A strong password is exactly as long as asked, with nothing odd in it ({bad} of 400 weren't)")

        # Cross-site frames: a sign-in form from another site inside this page gets nothing.
        send(process, "vaultSave", origin=OTHER, username="frame@example.com", password="Frame-Never-Fill-1")
        go(process, SITE + "/frame")
        time.sleep(1.5)
        f = rect(process, "#f")
        click_at(process, f["x"] + 60, f["y"] + 120)
        time.sleep(1)
        check(not page(process, "!!document.querySelector('still-passwords')") and not has_key(process),
              "A sign-in form in a frame from another site gets no key and no fill")

        # Insecure pages: auto sign-in stays off, and the first click only warns; the second fills.
        send(process, "vaultSave", origin=INSECURE, username="open@example.com", password="Plain-Http-Page-9")
        time.sleep(.5)
        plain = entry(process, INSECURE, "open@example.com")
        go(process, INSECURE + "/login")
        check(values(process, "#user", "#pw") == ["", ""], "Auto sign-in never fills on an insecure page")
        first = pick(process, "#user", 0, plain, warned=True)
        time.sleep(.5)
        armed = values(process, "#user", "#pw") == ["", ""]
        at = until(lambda: menu_item(process, "#user", 0, True, **{"data-id": plain["id"]}), 5)
        if at:
            click_at(process, *at)
        check(first and armed and until(lambda: values(process, "#user", "#pw") == ["open@example.com", "Plain-Http-Page-9"], 5),
              "On an http page the first click only warns; the second fills")
        send(process, "passwordPermission", feature="fill", enabled=False)

        # Two-step sign-in: the username from the first page goes with the password from the second.
        go(process, SITE + "/step1")
        type_into(process, "#user", "kit@example.com")
        click(process, "#go")
        until(lambda: "/step2" in page(process, "location.href"), 8)
        settle(process)
        type_into(process, "#pw", "Two-Step-Fox-31")
        click(process, "#go")
        offered = until(lambda: bar(process), 8)
        check(offered and js(process, "document.querySelector('.save-login input[aria-label=Username]')?.value") == "kit@example.com",
              "A two-step sign-in is offered with the username from its first step")
        bar_button(process, "Not now")
        check(entry(process, SITE, "kit@example.com") is None, "Not now saves nothing")

        # Strong passwords: a new-password field suggests one, and taking it saves the login straight away.
        go(process, SITE + "/signup")
        type_into(process, "#user", "new@example.com")
        page(process, "document.activeElement?.blur()")
        click(process, "#pw")
        at = until(lambda: menu_item(process, "#pw", 0, **{"data-generate": "1"}), 5)
        if at:
            time.sleep(.7)
            click_at(process, *at)
        made = until(lambda: values(process, "#pw")[0], 5) or ""
        strong = len(made) == 20 and any(c.isupper() for c in made) and any(c.islower() for c in made) and any(c.isdigit() for c in made) and any(not c.isalnum() for c in made)
        saved = until(lambda: entry(process, SITE, "new@example.com"), 5)
        check(strong and saved and reveal(process, saved) == made, "The suggested strong password fills the field and is saved at once")
        check(until(lambda: "Strong password saved for 127.0.0.1" in text(process), 3), "and Still says so")
        click(process, "#go")
        time.sleep(2)
        check(not bar(process), "Signing up with the suggestion asks nothing more")

        # Over a login that's already saved, the suggestion waits for the form and the Update bar.
        send(process, "vaultSave", origin=SITE, username="kept@example.com", password="Kept-Password-41")
        kept = until(lambda: entry(process, SITE, "kept@example.com"), 5)
        go(process, SITE + "/signup")
        type_into(process, "#user", "kept@example.com")
        page(process, "document.activeElement?.blur()")
        click(process, "#pw")
        at = until(lambda: menu_item(process, "#pw", 0, **{"data-generate": "1"}), 5)
        if at:
            click_at(process, *at)
        made = until(lambda: values(process, "#pw")[0], 5) or ""
        check(made and reveal(process, kept) == "Kept-Password-41", "The suggestion doesn't replace a saved password")
        check(until(lambda: "Still will ask before replacing" in text(process), 3), "and Still says it will ask")
        click(process, "#go")
        said = until(lambda: bar(process), 8) or ""
        check("Update" in said, f"Sending the form brings the Update bar ({said[:60]!r})")
        if said:
            bar_button(process, "Not now")
        check(reveal(process, kept) == "Kept-Password-41", "and Not now leaves the old one")
        emptied = until(lambda: js(process, "(b => !!b && [...b.querySelectorAll('input')].every(i => !i.value) && !!b.closest('[inert]'))(document.querySelector('.save-login'))"), 3)
        check(emptied, "and the bar lets go of the password and can't be reached by the keyboard")
        send(process, "vaultDelete", id=kept["id"])

        # Never for this site.
        def sign_in_elsewhere():
            go(process, OTHER + "/login")
            type_into(process, "#user", "someone@example.com")
            type_into(process, "#pw", "Other-Site-Pass-8")
            click(process, "#go")
        sign_in_elsewhere()
        until(lambda: bar(process), 8)
        bar_button(process, "Never for this site")
        sign_in_elsewhere()
        time.sleep(2.5)
        vault(process)
        check(not bar(process) and OTHER in (js(process, "window.__tools.passwords?.never ?? []") or []), "Never for this site stops the offers there and lists the site")

        # Private tabs never save and get no helper.
        send(process, "new", url=SITE + "/login", private=True)
        until(lambda: any(t.get("Private") for t in rpc(process)["tabs"]), 10)
        until(lambda: page(process, "location.pathname") == "/login" and page(process, "document.readyState") == "complete", 10)
        time.sleep(.6)
        script = helper(process)
        type_into(process, "#user", "private@example.com")
        type_into(process, "#pw", "Private-Tab-Pass-5")
        click(process, "#go")
        time.sleep(2.5)
        check(script == "undefined" and not bar(process) and entry(process, SITE, "private@example.com") is None, "A private tab never saves a password")
        send(process, "select", id="home")

        # Passwords: showing one asks Windows Hello / Touch ID first (answered here by the QA hook).
        send(process, "openPanel", name="passwords")
        until(lambda: js(process, "!!document.querySelector('.passwords-list')"), 5)
        before = rpc(process, "osAuth", answer="deny")["asks"]
        js(process, "__msgs.length = 0")
        js(process, row("ada@example.com", "r.querySelector('[aria-label^=\"Show password\"]').click()"))
        time.sleep(1)
        denied = not js(process, "__msgs.some(m => m.kind === 'vaultRevealed')") and rpc(process, "osAuth")["asks"] == before + 1
        rpc(process, "osAuth", answer="allow")
        js(process, row("ada@example.com", "r.querySelector('[aria-label^=\"Show password\"]').click()"))
        shown = until(lambda: js(process, row("ada@example.com", "r.querySelector('.password-shown')?.innerText")), 5)
        check(denied and shown == "Lighthouse-Keeper-43", "A password shows only after Windows Hello or Touch ID says yes")
        js(process, row("ada@example.com", "r.querySelector('[aria-label^=\"Copy password\"]').click()"))
        check(until(lambda: "Password copied" in text(process), 5), "Copy works after the check (test builds never touch the clipboard)")
        send(process, "vaultSave", origin="https://weak.example", username="me", password="password")
        send(process, "vaultSave", origin="https://reuse.example", username="me", password="Lighthouse-Keeper-43")
        send(process, "vaultSave", origin="https://sheet.example", username='=HYPERLINK("https://x.example")', password="=Keeps-Its-Own-Form-5")
        time.sleep(.6)
        flags = {(v["origin"], v["username"]): (v["weak"], v["reused"]) for v in vault(process)}
        check(flags.get(("https://weak.example", "me")) == (True, False) and flags.get(("https://reuse.example", "me")) == (False, True)
              and flags.get((SITE, "ada@example.com")) == (False, True) and flags.get((SITE, "new@example.com")) == (False, False), "Weak and reused passwords are flagged")
        themed(process, "manager", lambda: (send(process, "openPanel", name="passwords"), until(lambda: js(process, "!!document.querySelector('.passwords-list')"), 5)))

        # Export: a CSV other browsers can import, only after the check.
        send(process, "openPanel", name="passwords")
        until(lambda: js(process, "!!document.querySelector('.passwords-list')"), 5)
        rpc(process, "osAuth", answer="deny")
        send(process, "vaultExport")
        time.sleep(1)
        refused = not (RUN / "export.csv").exists()
        rpc(process, "osAuth", answer="allow")
        js(process, "document.querySelector('[aria-label=\"Export passwords\"]').click()")
        until(lambda: js(process, "!!document.querySelector('[role=alertdialog]:not(.permission-bar)')"), 5)
        js(process, "[...document.querySelectorAll('[role=alertdialog]:not(.permission-bar) button')].find(b => b.innerText === 'Confirm').click()")
        exported = until(lambda: (RUN / "export.csv").exists() and (RUN / "export.csv").read_text(encoding="utf-8"), 5) or ""
        sheet = next((r for r in csv.reader(io.StringIO(exported)) if len(r) > 3 and r[1].startswith("https://sheet.example")), [])
        check(sheet[2:4] == ['\'=HYPERLINK("https://x.example")', "=Keeps-Its-Own-Form-5"], f"A username can't act as a spreadsheet formula, and the password stays exact ({sheet})")
        rows = list(csv.DictReader(exported.splitlines()))
        check(refused and any(r["username"] == "ada@example.com" and r["password"] == "Lighthouse-Keeper-43" and r["url"].startswith(SITE) for r in rows),
              "Export writes a CSV only after the check")

        # Import a CSV.
        (RUN / "import.csv").write_text("name,url,username,password\nbreakfast,https://csv.example/login,csvuser,maple syrup pancakes forever\n", encoding="utf-8")
        js(process, "window.__tools.import = null")
        rpc(process, "stageImport", kind="passwords", path=str(RUN / "import.csv"))
        preview = until(lambda: js(process, "window.__tools.import?.preview ?? null"), 5) or {}
        send(process, "importConfirm", id=preview.get("id", ""), replace=False)
        time.sleep(.6)
        found = entry(process, "https://csv.example", "csvuser")
        check(preview.get("logins") == 1 and found and reveal(process, found) == "maple syrup pancakes forever", "Importing a password CSV adds its logins")

        # A hand-made Firefox key with an absurd IV is simply not read.
        def der(tag, *parts):
            body = b"".join(parts)
            return bytes([tag]) + (bytes([len(body)]) if len(body) < 128 else bytes([0x82, len(body) >> 8, len(body) & 255])) + body
        odd = RUN / "firefox-odd"
        shutil.copytree(FIXTURES / "firefox-profile", odd)
        pbes2, pbkdf2, aes = bytes.fromhex("2a864886f70d01050d"), bytes.fromhex("2a864886f70d01050c"), bytes.fromhex("60864801650304012a")
        item = der(0x30, der(0x30, der(6, pbes2), der(0x30, der(0x30, der(6, pbkdf2), der(0x30, der(4, b"s" * 32), der(2, b"\x01"))), der(0x30, der(6, aes), der(4, b"i" * 300)))), der(4, b"d" * 32))
        db = sqlite3.connect(odd / "key4.db")
        db.execute("UPDATE metaData SET item2=? WHERE id='password'", (item,))
        db.commit()
        db.close()
        stage_profile(process, odd, "Firefox")
        check(process.poll() is None and rpc(process).get("tabs") is not None, "A Firefox key made to crash the import leaves Still running")

        # Import from Firefox (a fixture profile without a primary password), and one with a primary password.
        fox = RUN / "firefox"
        shutil.copytree(FIXTURES / "firefox-profile", fox)
        external = stage_profile(process, fox, "Firefox") or {}
        check(external.get("passwords") == 2 and external.get("bookmarks") == 1 and external.get("history") == 2, "Firefox's passwords, bookmarks and history are read")
        send(process, "externalConfirm", id=external.get("id", ""), passwords=True)
        time.sleep(1)
        a, b = entry(process, "https://fox.example", "fox@example.com"), entry(process, "https://burrow.example", "kit")
        check(a and b and reveal(process, a) == "Fennec-3des-91!" and reveal(process, b) == "Burrow-aes-27?", "Firefox logins import with the right passwords (3DES and AES)")
        locked = RUN / "firefox-locked"
        shutil.copytree(FIXTURES / "firefox-profile", locked)
        db = sqlite3.connect(locked / "key4.db")
        item = bytearray(db.execute("SELECT item2 FROM metaData WHERE id='password'").fetchone()[0])
        item[-1] ^= 0xFF  # as with a primary password: the empty one no longer opens the check
        db.execute("UPDATE metaData SET item2=? WHERE id='password'", (bytes(item),))
        db.commit()
        db.close()
        external = stage_profile(process, locked, "Firefox") or {}
        check(external.get("passwords") == 0 and any("primary password" in w and "Export passwords" in w for w in external.get("warnings", [])),
              "A Firefox primary password is explained, with the way through (export a CSV)")
        send(process, "externalCancel")

        # Import from Chrome: what Windows can decrypt comes in; app-bound passwords are explained. On the Mac, Chrome's
        # key comes from the Keychain (macOS asks you first).
        if MAC:
            chrome = RUN / "Google" / "Chrome" / "Default"
            mac_chrome_profile(chrome)
            external = stage_profile(process, chrome, "Chrome") or {}
            check(external.get("passwords") == 2 and external.get("bookmarks") == 1 and external.get("cookies") == 2, f"Chrome passwords (the account's too) and cookies are read with the key from the Keychain ({external.get('cookies')} cookies)")
            send(process, "externalConfirm", id=external.get("id", ""), passwords=True, cookies=True)
            done = until(lambda: js(process, "window.__tools.import?.external?.done || null"), 10) or ""
            check("2 passwords and 2 cookies" in done and "Reload open sites" in done, f"Still says what came over ({done!r})")
            go(process, SITE + "/welcome")
            check(page(process, "document.cookie") == "chromesid=Session-keychain-55", "Chrome's sign-in cookie arrives, readable by its site")
            send(process, "refreshTools", name="cookies")
            jar = until(lambda: js(process, "window.__tools.cookies?.cookies ?? null"), 5) or []
            check(any(c["name"] == "chromehttp" and c["httpOnly"] and c["session"] for c in jar), "and a server-only session cookie keeps its HttpOnly flag")
            c = entry(process, "https://chrome.example", "chromie")
            s = entry(process, "https://account.example", "synced")
            check(c and reveal(process, c) == "Chrome-keychain-77" and s and reveal(process, s) == "Chrome-keychain-77", "The Chrome logins arrive with their passwords")
        else:
            chrome = RUN / "chrome"
            chrome_profile(chrome)
            external = stage_profile(process, chrome, "Chrome") or {}
            check(external.get("cookies") == 1 and external.get("skipped", 0) >= 1, f"A sealed cookie that isn't its site's own stays behind ({external.get('cookies')} cookies)")
            check(not external.get("picked"), "A browser Still found isn't treated as a folder you picked")
            send(process, "externalCancel")
            hand = stage_profile(process, chrome, "chrome", picked=True) or {}
            check(hand.get("picked") is True and "chrome.example" in hand.get("sites", []), f"A folder you picked says which sites its passwords are for ({hand.get('sites')})")
            send(process, "externalCancel")
            external = stage_profile(process, chrome, "Chrome") or {}
            check(external.get("passwords") == 2 and any("locked to the browser" in w and "Export your passwords" in w for w in external.get("warnings", [])),
                  "Chrome passwords import, and app-bound ones point to Chrome's own CSV export")
            send(process, "externalConfirm", id=external.get("id", ""), passwords=True)
            time.sleep(1)
            c = entry(process, "https://chrome.example", "chromie")
            s = entry(process, "https://account.example", "synced")
            check(c and reveal(process, c) == "Chrome-dpapi-77" and s and reveal(process, s) == "Chrome-dpapi-77", "The Chrome logins (the account's too) arrive with their passwords")

        # ---- AIs never get a password ----
        js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        agent = Mcp(EXE, "Claude", PROFILE)
        tools = [t["name"] for t in agent.request("tools/list", {})["result"]["tools"]]
        check(tools and not any(w in t for t in tools for w in ("pass", "vault", "login", "credential", "secret")), "No MCP tool reads, lists, fills or exports passwords")
        ok, _ = agent.call("get_passwords")
        check(not ok, "Asking for passwords over MCP fails")
        helped = subprocess.run([str(EXE), "--cli", "help"], capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
        commands = [line.split()[0] for line in helped.splitlines() if line.startswith("  ") and not line.startswith("   ") and line.strip()]
        check(len(commands) > 10 and not any(w in c for c in commands for w in ("pass", "vault", "login", "credential")), "The CLI has no password command")

        # A sign-in page pauses the AI and brings the page to the user.
        ok, opened = agent.call("open_tab", url=SITE + "/login")
        tab = json.loads(opened)["tabId"] if ok else ""
        ok, said = agent.call("read_page", tabId=tab)
        paused = until(lambda: rpc(process).get("activeId") == tab and "Sign in, then hand it back" in (js(process, "document.querySelector('.page-control')?.innerText") or ""), 8)
        check(ok and "sign-in page" in said and "never type or see passwords" in said and paused, "On a sign-in page the AI pauses and the user is asked to sign in")
        settle(process)
        # The user fills their saved login from the key, then hands the tab back without sending the form.
        pick(process, "#user", 0, ada)
        filled = until(lambda: values(process, "#user", "#pw") == ["ada@example.com", "Lighthouse-Keeper-43"], 5)
        js(process, "document.querySelector('.page-take').click()")
        time.sleep(.5)
        ok, seen = agent.call("read_page", tabId=tab)
        check(filled and ok and "[saved login, hidden]" in seen and "ada@example.com" not in seen and "Lighthouse" not in seen and "sign-in page" not in seen,
              "After the user signs in, what the AI reads hides the saved login")
        ok, found = agent.call("find", tabId=tab, text="Lighthouse-Keeper-43")
        check("Lighthouse" not in found and "No buttons, links or fields match" in found, "find can't search for a saved password")
        # An error's look at the page hides them too, even clipped short or with the spaces closed up.
        wordy = "Marble  Harbor " * 6
        send(process, "vaultSave", origin=SITE, username="wordy@example.com", password=wordy.strip())
        until(lambda: entry(process, SITE, "wordy@example.com"), 5)
        page(process, f"document.body.insertAdjacentHTML('beforeend', '<div id=shown><input value=\"Lighthouse-Keeper-43\"><input value=\"{wordy.strip()}\"></div>')")
        ok, said = agent.call("click", tabId=tab, selector="#no-such-thing", seconds=30)
        check(not ok and "The page now" in said and "[hidden]" in said and "Lighthouse" not in said and "Marble" not in said, f"An error's look at the page hides saved passwords ({said[-200:]!r})")
        page(process, "document.querySelector('#shown').remove()")
        send(process, "vaultDelete", id=entry(process, SITE, "wordy@example.com")["id"])
        until(lambda: not entry(process, SITE, "wordy@example.com"), 5)
        page(process, "window.__masks = 0; new MutationObserver(r => __masks += r.length).observe(document.querySelector('#user'), { attributes: true, attributeFilter: ['style'] })")
        ok, _ = agent.call("screenshot", tabId=tab)
        check(ok and page(process, "window.__masks") >= 2 and not page(process, "document.querySelector('#user').getAttribute('style')"),
              "A screenshot masks fields that show a saved login, then puts them back")
        started = time.monotonic()
        ok, said = agent.call("type", tabId=tab, selector="#pw", text="guessing")
        check(not ok and "never type or see passwords" in said and time.monotonic() - started < 5 and values(process, "#pw") == ["Lighthouse-Keeper-43"],
              "An AI can't type into a password field")
        until(lambda: js(process, "!!document.querySelector('.page-control.is-paused .page-take')"), 5)
        js(process, "document.querySelector('.page-control.is-paused .page-take').click()")
        time.sleep(.5)
        # While an AI drives the tab, the key fills nothing.
        agent.call("scroll", tabId=tab, direction="down")
        page(process, "document.querySelector('#user').value = ''; document.querySelector('#pw').value = ''")
        at = pick(process, "#user", 0, ada)
        time.sleep(1)
        check(at and values(process, "#user", "#pw") == ["", ""], "While an AI drives the tab, nothing fills")
        agent.call("close_tab", tabId=tab)
        agent.close()
        agent = None

        if not MAC:  # test builds never touch the clipboard, so this reads what would go on it
            clip = rpc(process, "passwordClip")
            check(all(clip.get(k) == 0 for k in ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")) and "UnicodeText" in clip, f"A copied password is marked to stay out of clipboard history and the cloud ({clip})")

        # Companions' memory never keeps a saved password.
        results = BIN / "results.jsonl"
        send(process, "new")
        until(lambda: js(process, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
        js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        send(process, "aiSend", text="REMEMBER: Loves maple syrup pancakes forever", home=True, companion="rosa")
        said = until(lambda: results.exists() and json.loads(results.read_text(encoding="utf-8").splitlines()[0]), 30) or {}
        memory = PROFILE / "companions" / "rosa" / "memory.json"
        check(said.get("error") and "Still never keeps those" in said.get("text", "") and "saved password" not in said.get("text", "") and (not memory.exists() or "pancakes" not in memory.read_text(encoding="utf-8")),
              f"A companion can't remember a saved password, and isn't told that's what it was ({said.get('text')!r})")
        send(process, "aiSend", text="REMEMBER: " + "several guesses here " * 20 + "maple syrup pancakes forever", home=True, companion="rosa")
        said = until(lambda: results.exists() and len(rows := results.read_text(encoding="utf-8").splitlines()) > 1 and json.loads(rows[1]), 30) or {}
        check(said.get("error") and "characters" in said.get("text", "") and "Still never keeps those" not in said.get("text", ""), f"A list of guesses is just too long ({said.get('text')!r})")
        errors = rpc(process).get("shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    except Exception as error:
        traceback.print_exc()
        check(False, "The run finished (" + type(error).__name__ + ")")
    finally:
        if agent:
            agent.close()
        try:
            rpc(process, "quit")
            process.wait(timeout=15)
        except Exception:
            process.kill()
        SERVER.shutdown()
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
