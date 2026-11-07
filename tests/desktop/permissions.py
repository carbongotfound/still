"""Phase 4: the permission layer. A fake AI app drives a local shop through Still's MCP server, and the test answers
the cards like a person would.

  CART <site> <n>   clicks Add to cart n times (interact)
  ORDER <site>      types a name, then clicks Place order on a form that posts (sensitive)
  BOTH <site>       clicks Add to cart and Save for later at the same time (two cards: Approve all)
  PAIR <url>        the same on a page of its own, so each run's clicks can be counted on the server
  QUEUE <url>       a click on a link to a slow page (it holds the page's turn), and a second one waiting behind it
  SWAP <url>        clicks #swap on a page that turns it into something else while the card waits (see TRICKY)
  KEY <url>         presses Enter in a field: the page moves the focus while the card waits
  LATER <url>       clicks Add to cart, then a moment later Save for later: a second step arrives under a waiting card

Checks: once per chat / always / ask every time, a sensitive step always shows a card or a countdown, Cancel and the
countdown running out, Cancel right at the end of it, Approve all, sensitive sites, Stop during a card, an outside AI app asking in the bar, the
settings page and Reset all, and the audit log in the chat's details.

With --live it runs one small real task through Claude (Haiku) instead: buy a mug. You take over mid-run, the page
wants a texted code only you have (Help with this page), and Place order asks first. By hand only: it uses your plan.

Run: python tests/desktop/permissions.py artifacts/Still-QA/Still.exe [--live]
Screenshots: docs/agentic/compare/ (approval-v01, sensitive-v01, countdown-v01, approve-all-v01, permissions-v01, audit-v01)
"""
import http.server
import json
from pathlib import Path
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, press_ready, rpc, send, until  # noqa: E402
from mcp_client import Mcp, call_async  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("permissions-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
OUT = ROOT / "docs" / "agentic" / "compare"
RESULT = {"checks": []}
ORDERS = []
HITS = []  # what the shop's buttons told the server, as /hit/<button>?k=<which run>
GO = {}  # query string -> True: time for that tricky page to change
LIVE = "--live" in sys.argv
CODE = "482913"  # the code "texted to your phone": only the test (you) knows it


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


# ---- a small shop: a button that only adds to a cart, and a checkout form that posts ----
SHOP = """<!doctype html><meta charset=utf-8><title>Maple Market</title>
<style>body{margin:0;font:15px system-ui;color:#2a2118;background:#fbf7f1}header{display:flex;gap:16px;align-items:center;padding:14px 28px;background:#7a3e1d;color:#fff}
header b{font-size:19px}header form{display:flex;gap:6px}input{padding:8px 11px;border-radius:8px;border:1px solid #d9c9b6;font:inherit}
main{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding:24px 28px}section{background:#fff;border-radius:14px;padding:18px;box-shadow:0 1px 3px #0002}
button{padding:8px 14px;border-radius:8px;border:1px solid #7a3e1d;background:#fff;font:inherit}#order{background:#7a3e1d;color:#fff}.pic{height:120px;border-radius:10px;background:linear-gradient(135deg,#ead9c4,#f6ede2)}</style>
<header><b>Maple Market</b><form action=/shop role=search><input id=q name=q placeholder="Search the shop"><button>Search</button></form></header>
<main><section><div class=pic></div><h2>Trail mug</h2><p>$18</p>
<div id=row><button type=button id=cart onclick="this.dataset.n=(+this.dataset.n||0)+1;hit(this)">Add to cart</button> <button type=button id=wish onclick="this.dataset.n=1;hit(this)">Save for later</button> <a id=slow href=/slow>Details</a></div></section>
<section><h2>Checkout</h2><form id=checkout method=post action=/order><p><label>Name <input id=name name=name></label></p><button id=order>Place order</button></form></section></main>
<script>const hit = b => fetch('/hit/' + b.id + location.search, { method: 'POST' }); document.getElementById('row').addEventListener('click', e => { if (e.target.id === 'row') fetch('/hit/row' + location.search, { method: 'POST' }); });</script>"""
# A shop that changes its mind. /tricky?do=... decides how; the test's own fetches tell it when.
TRICKY = """<!doctype html><meta charset=utf-8><title>Tricky shop</title>
<form id=f method=post action=/order?who=tricky><input type=hidden name=name value=tricky><input id=field name=note placeholder="Note"><button type=button id=swap>Add to cart</button></form>
<input id=other placeholder="Other">
<script>
const q = new URLSearchParams(location.search), how = q.get('do');
const b = document.getElementById('swap');
b.addEventListener('click', () => fetch('/hit/cart' + location.search, { method: 'POST' }));
const change = () => {
 if (how === 'order') { b.type = 'submit'; b.textContent = 'Place order'; }       // the classic: Add to cart becomes Place order
 if (how === 'quiet') { b.type = 'submit'; }                                      // same words, but now it submits
 if (how === 'away') location.href = q.get('to');                                 // the tab goes to another site
 if (how === 'focus') document.getElementById('other').focus();                   // the key would go somewhere else
 fetch('/hit/changed' + location.search, { method: 'POST' });
};
const poll = setInterval(async () => { if (await (await fetch('/go' + location.search)).text() === 'go') { clearInterval(poll); change(); } }, 60);
if (how === 'focus') document.getElementById('field').focus();
// A page that swaps on the press itself, past every check before it.
if (how === 'press') b.addEventListener('pointerdown', () => { b.type = 'submit'; b.textContent = 'Place order'; }, true);
</script>"""
# The live run's page: one checkout that needs a code only you have.
MUG = SHOP.split("<main>")[0].replace("Maple Market</title>", "Trail mug - Maple Market</title>") + """<main><section><div class=pic></div><h2>Trail mug</h2><p>$18 each</p></section>
<section><h2>Checkout</h2><form id=checkout method=post action=/buy><p><label>Quantity <input id=qty name=qty type=number min=1 value=1></label></p>
<p><label>Name <input id=name name=name></label></p><p><label>Delivery note <input id=note name=note></label></p><p><label>Code from your phone <input id=code name=code inputmode=numeric autocomplete=one-time-code></label><br>
<small>We texted a 6-digit code to the phone on your account. Enter it to place the order.</small></p><button id=order>Place order</button></form></section></main>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/tricky"):
            return self.page(TRICKY)
        if self.path.startswith("/go"):
            return self.page("go" if GO.get(self.path.split("?", 1)[-1]) else "wait")
        if self.path.startswith("/slow"):
            HITS.append("/slow")
            time.sleep(4)  # the click waits for the page, and holds its turn
        self.page(SHOP if self.path.startswith("/shop") else MUG if self.path.startswith("/mug") else "<!doctype html><title>Page</title><p>Page")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        if self.path.startswith("/hit/"):
            HITS.append(self.path)
            return self.page("ok")
        ORDERS.append({"path": self.path, "body": urllib.parse.parse_qs(body), "t": time.time()})
        if self.path == "/buy" and urllib.parse.parse_qs(body).get("code") != [CODE]:
            return self.page("<!doctype html><title>Checkout</title><h1>That code didn't match</h1><p><a href=/mug>Try again</a>")
        self.page("<!doctype html><title>Thanks</title><h1>Thanks, your order is placed</h1>")

    def page(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
SITE = f"http://127.0.0.1:{SERVER.server_port}"
OTHER = f"http://localhost:{SERVER.server_port}"  # the same shop under another site name

# ---- the fake AI app: Still's MCP server, driven by a script; calls can run side by side ----
FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, threading, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    logging = threading.Lock()  # two steps at once: appends from both threads would overwrite each other on Windows
    def log(entry):
        with logging, open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(entry) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
    still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    replies, lock, n = {}, threading.Condition(), [0]
    def read():
        for line in still.stdout:
            try: m = json.loads(line)
            except ValueError: continue
            with lock: replies[m.get("id")] = m; lock.notify_all()
    threading.Thread(target=read, daemon=True).start()
    def request(method, params):
        with lock: n[0] += 1; rid = n[0]
        still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n").encode()); still.stdin.flush()
        with lock:
            lock.wait_for(lambda: rid in replies, 900)
            return replies.pop(rid)
    request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
    still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
    tag = prompt.rsplit("\n\n", 1)[-1].strip()
    last = [""]
    def call(tool, **a):
        r = request("tools/call", {"name": tool, "arguments": a})["result"]
        ok, text = not r.get("isError"), "\n".join(c.get("text", "") for c in r.get("content", []))
        log({"chat": tag, "tool": tool, "args": a, "ok": ok, "text": text[:300], "t": time.time()})
        last[0] = text
        return ok
    def reply(text): say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if m := re.search(r"CART (\S+) (\d+)", tag):
        call("open_tab", url=m[1] + "/shop")
        for _ in range(int(m[2])): call("click", selector="#cart")
    elif m := re.search(r"ORDER (\S+)", tag):
        call("open_tab", url=m[1] + "/shop")
        call("type", selector="#name", text="Sam")
        call("click", selector="#order")
    elif m := re.search(r"BOTH (\S+)", tag):
        call("open_tab", url=m[1] + "/shop")
        both = [threading.Thread(target=call, args=("click",), kwargs={"selector": s}) for s in ("#cart", "#wish")]
        for t in both: t.start()
        for t in both: t.join()
    elif m := re.search(r"PAIR (\S+)", tag):
        call("open_tab", url=m[1])
        both = [threading.Thread(target=call, args=("click",), kwargs={"selector": s}) for s in ("#cart", "#wish")]
        for t in both: t.start()
        for t in both: t.join()
    elif m := re.search(r"QUEUE (\S+)", tag):
        call("open_tab", url=m[1])
        first = threading.Thread(target=call, args=("click",), kwargs={"selector": "#slow"})
        first.start()
        time.sleep(.3)
        call("click", selector="#wish")
        first.join()
    elif m := re.search(r"SWAP (\S+)", tag):
        call("open_tab", url=m[1])
        call("click", selector="#swap")
    elif m := re.search(r"LATER (\S+)", tag):
        call("open_tab", url=m[1])
        both = [threading.Thread(target=call, args=("click",), kwargs={"selector": "#cart"}), threading.Thread(target=lambda: (time.sleep(4), call("click", selector="#wish")))]
        for t in both: t.start()
        for t in both: t.join()
    elif m := re.search(r"KEY (\S+)", tag):
        call("open_tab", url=m[1])
        call("press_key", key="Enter")
    elif m := re.search(r"HELP (\S+)", tag):
        call("open_tab", url=m[1] + "/shop")
        call("ask_user", question="This page wants a code from your phone. Could you enter it?", tabId=json.loads(last[0])["tabId"])
    elif m := re.search(r"CAP (\S+)", tag):
        for i in range(7): call("open_tab", url=m[1] + "/shop?n=%d" % i)
    elif re.search(r"AGAIN", tag):  # the tab this chat already has
        call("click", selector="#order")
    elif m := re.search(r"SLOW (\S+)", tag):
        call("open_tab", url=m[1] + "/shop")
        call("wait_for", text="never shows up", timeoutMs=30000)
        call("wait_for", text="never shows up", timeoutMs=30000)
    reply("Done.")
    still.stdin.close()
''')


def calls(chat, opens=False):
    file = BIN / "calls.jsonl"
    rows = [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.endswith("}")] if file.exists() else []  # skips a line being written
    return [c for c in rows if c["chat"] == chat and (opens or c["tool"] != "open_tab")]


def chat_of(tag):
    try:
        return next((c for c in json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")) if c["Title"].startswith(tag)), None)
    except (OSError, ValueError):
        return None


def audit(tag):
    return [a["Result"] for a in (chat_of(tag) or {}).get("Audit", [])]


def cards(process):
    """The steps waiting on the card, and any countdown."""
    return js(process, "[...document.querySelectorAll('.approve-card .approve-steps li')].map(e => e.innerText)") or []


def counting(process):
    return js(process, "document.querySelector('.countdown-card')?.innerText ?? ''") or ""


def press(process, words, within=".approve-card"):
    return press_ready(process, f"[...document.querySelectorAll({json.dumps(within + ' button')})].find(b => b.innerText.trim() === {json.dumps(words)})")


def ask(process, tag):
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 20)
    time.sleep(.4)
    send(process, "aiSend", text=tag, home=True, companion="maya")


def idle(process):
    return until(lambda: not js(process, "document.querySelector('.tasks-button')?.getAttribute('aria-label')?.match(/[1-9]\\d* running/)"), 60)


def capture(process, name):
    time.sleep(.7)  # let the card finish fading in
    rpc(process, "capture", name=name + ".png")
    (OUT / f"{name}.png").write_bytes((PROFILE / f"{name}.png").read_bytes())


def rules():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"].get("Permissions", [])
    except (OSError, ValueError, KeyError):
        return []


def main():
    BIN.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "claude" if LIVE else "fake", "Theme": "Light", "Width": 1720, "Height": 1080,
        # Live: clicking and typing go ahead, so the only card is the sensitive step's.
        **({"Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}]} if LIVE else {})},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    try:
        if LIVE:
            return live(process)
        once_per_chat(process)
        ask_every_time(process)
        sensitive(process)
        cancel_at_the_end(process)
        one_at_a_time(process)
        only_what_was_shown(process)
        steady_buttons(process)
        approve_all(process)
        keys_and_help(process)
        outside(process)
        settings(process)
        process = crash_resume(process)
        errors = rpc(process).get("shellErrors") or js(process, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


def live(process):
    """One real task through Claude on Haiku, the way you'd use it: you take over mid-run, give it the code it can't
    know, and approve the purchase."""
    send(process, "aiCheck")
    time.sleep(3)  # the model list loads in the background
    send(process, "aiAdvanced", on=True)  # without Advanced, the companion's mode picks the model
    send(process, "aiModel", harness="claude", model="haiku")
    started = time.monotonic()
    ask(process, f"Buy one Trail mug for me at {SITE}/mug. The name for the order is Sam Rivera.")
    page = lambda: next((t for t in rpc(process)["tabs"] if t.get("Url", "").endswith("/mug")), None)
    on_page = lambda script: rpc(process, "evalTab", id=page()["Id"], script=script)
    control = lambda: js(process, "document.querySelector('.page-control')?.innerText ?? ''") or ""
    working = lambda: js(process, "document.querySelector('.page-control')?.dataset.state === 'working'")
    check(until(lambda: page() and working(), 180, .3), "Live: Claude opens the shop in front, and the pill says it's in control")

    js(process, "document.querySelector('.page-take').click()")
    check(until(lambda: "You're in control" in control(), 5), "Live: Take over mid-run hands you the page")
    until(lambda: on_page("document.readyState === 'complete' && !!document.querySelector('#note')"), 15, .2)  # you type into a page you can see
    on_page("note.value = 'Leave it at the door'; note.dispatchEvent(new Event('input', {bubbles: true}))")  # something only you'd add
    capture(process, "live-takeover-v01")
    time.sleep(3)
    js(process, "document.querySelector('.page-take').click()")
    check(until(lambda: working() or not control(), 5), "Live: Hand back gives Claude the page again")

    helped = until(lambda: "Help with this page" in (js(process, "document.querySelector('.ask-help')?.innerText ?? ''") or ""), 240, .5)
    check(helped, "Live: the code only you have shows a Help with this page card")
    capture(process, "live-help-v01")
    if helped:
        press(process, "Open the page", ".ask-card")
        on_page(f"code.value = {json.dumps(CODE)}; code.dispatchEvent(new Event('input', {{bubbles: true}}))")
        # Answer in your own words: the AI picks the card's options, so there may be no "I'm done".
        js(process, "document.querySelector('.ask-card .ask-own input').focus()")
        rpc(process, "shellCdp", method="Input.insertText", parameters={"text": "I typed the code into the page. Go ahead."})
        js(process, "document.querySelector('.ask-card .ask-own button[type=submit]').click()")

    card = until(lambda: cards(process), 240, .5)
    check(card and "Place order" in " ".join(card), "Live: Place order waits on an approval card")
    capture(process, "live-approval-v01")
    press(process, "Allow once")

    bought = until(lambda: next((o for o in ORDERS if o["path"] == "/buy" and o["body"].get("code") == [CODE]), None), 180, .5)
    done = until(lambda: not js(process, "!!document.querySelector('[aria-label=Stop]')"), 120, 1)
    body = (bought or {}).get("body", {})
    check(bought and body.get("name") == ["Sam Rivera"] and body.get("qty") == ["1"], "Live: the order goes through with the name and your code")
    check(body.get("note") == ["Leave it at the door"], "Live: the note you typed while in control is still there")
    check(done, "Live: Claude finishes and says so")
    chat = max(json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")), key=lambda c: c.get("Updated", ""))
    RESULT["live"] = {"seconds": round(time.monotonic() - started, 1), "orders": ORDERS, "audit": chat.get("Audit", []),
                      "messages": [(m["Role"], m["Text"][:300]) for m in chat["Messages"]]}
    check(any(role == "tool" and "Place order" in text for role, text in RESULT["live"]["messages"]), "Live: the chat's steps say which button it clicked")
    capture(process, "live-done-v01")


def once_per_chat(process):
    """The default for clicking and typing: ask once per site in each chat."""
    ask(process, f"CART {SITE} 2 a")
    shown = until(lambda: cards(process), 30)
    check(shown and "Add to cart" in shown[0] and "127.0.0.1" in shown[0], "A first click on a site shows a card with the step and the site")
    check(js(process, "/need you/.test(document.querySelector('.tasks-button')?.getAttribute('aria-label') ?? '')"), "The runner says the chat needs you")
    capture(process, "approval-v01")
    press(process, "Allow in this chat")
    until(lambda: len(calls("CART " + SITE + " 2 a")) == 2, 30)
    done = calls("CART " + SITE + " 2 a")
    check(len(done) == 2 and all(c["ok"] for c in done), "Allow in this chat lets both clicks run")
    check(until(lambda: audit("CART " + SITE + " 2 a") == ["You allowed it in this chat", "Allowed in this chat"], 10), "The second click didn't ask again, and both are in the log")
    idle(process)

    ask(process, f"CART {SITE} 1 b")
    check(until(lambda: cards(process), 30), "A new chat asks again")
    press(process, "Deny")
    until(lambda: calls("CART " + SITE + " 1 b"), 30)
    denied = calls("CART " + SITE + " 1 b")
    check(denied and not denied[0]["ok"] and "said no" in denied[0]["text"], "Deny refuses the step and tells the AI")
    idle(process)

    ask(process, f"CART {SITE} 1 c")
    until(lambda: cards(process), 30)
    press(process, "Always on this site")
    check(until(lambda: any(r["Site"] == "127.0.0.1" and r["Action"] == "interact" and r["Mode"] == "always" for r in rules()), 10), "Always allow saves a rule for the site")
    idle(process)
    ask(process, f"CART {SITE} 1 d")
    until(lambda: calls("CART " + SITE + " 1 d"), 30)
    check(calls("CART " + SITE + " 1 d")[0]["ok"] and until(lambda: audit("CART " + SITE + " 1 d") == ["Allowed by your settings"], 10), "With the rule it doesn't ask, and the log says why")
    idle(process)

    ask(process, f"CART {OTHER} 1 e")
    shown = until(lambda: cards(process), 30)
    check(shown and "localhost" in shown[0], "The rule is for that site only: another site still asks")
    press(process, "Allow once")
    idle(process)


def ask_every_time(process):
    send(process, "permSet", site="localhost", action="interact", companion="", mode="ask")
    ask(process, f"CART {OTHER} 2 f")
    until(lambda: cards(process), 30)
    press(process, "Allow in this chat")
    until(lambda: calls("CART " + OTHER + " 2 f"), 30)
    again = until(lambda: cards(process), 15)
    check(again, "Ask every time asks again, even after Allow in this chat")
    press(process, "Allow once")
    until(lambda: len(calls("CART " + OTHER + " 2 f")) == 2, 30)
    check(all(c["ok"] for c in calls("CART " + OTHER + " 2 f")), "Both asked clicks ran")
    idle(process)


def sensitive(process):
    # 127.0.0.1 is "always" for clicks by now, but Place order posts a form: it still asks.
    ask(process, f"ORDER {SITE} g")
    shown = until(lambda: cards(process), 30)
    check(shown and "Place order" in shown[0] and "purchase" in shown[0], "A purchase asks even where clicks are always allowed, and says why")
    check(js(process, "!!document.querySelector('.approve-steps li.is-sensitive')"), "The card marks it as sensitive")
    check(any(c["tool"] == "type" and c["ok"] for c in calls("ORDER " + SITE + " g")), "Typing the name didn't ask (clicks and typing are allowed there)")
    capture(process, "sensitive-v01")
    press(process, "Deny")
    until(lambda: len(calls("ORDER " + SITE + " g")) == 2, 30)
    check(not ORDERS and not calls("ORDER " + SITE + " g")[-1]["ok"], "Deny: the order never reaches the shop")
    idle(process)

    send(process, "permSet", site="127.0.0.1", action="sensitive", companion="", mode="always")
    ask(process, f"ORDER {SITE} h")
    started = until(lambda: counting(process), 30)
    check(started and "Going ahead in" in started and "Place order" in started, "Allowed without asking, a sensitive step counts down first")
    check(not cards(process), "The countdown has no approval card")
    capture(process, "countdown-v01")
    press(process, "Cancel", ".countdown-card")
    until(lambda: len(calls("ORDER " + SITE + " h")) == 2, 30)
    check(until(lambda: audit("ORDER " + SITE + " h")[-1:] == ["You cancelled it"], 10) and not ORDERS, "Cancel stops it, and the log says so")
    idle(process)

    ask(process, f"ORDER {SITE} i")
    until(lambda: counting(process), 30)
    shown_at = time.time()
    until(lambda: ORDERS, 20)
    check(ORDERS and ORDERS[0]["t"] - shown_at > 6.5, "Left alone, it goes ahead after the countdown")
    check(until(lambda: audit("ORDER " + SITE + " i")[-1:] == ["Went ahead after 8 seconds"], 10), "The log says it went ahead on its own")
    idle(process)


def cancel_at_the_end(process):
    """Cancel right as a countdown ends: it stops the step, the chat and its tab keep working, and one that really is
    too late says so. late: send Cancel that many ms after the deadline, as a click that's still on its way to Still."""
    def arm(late=None):
        js(process, """(() => { window.__card = window.__end = null;
          if (!window.__rejected) { window.__rejected = []; addEventListener('unhandledrejection', e => __rejected.push(String(e.reason))) }
          if (window.__seen) window.chrome.webview.removeEventListener('message', window.__seen);
          window.__seen = e => { const card = e.data?.kind === 'ai' && e.data.data.approvals?.find(a => a.until); if (!card || __card?.id === card.id) return; __card = card;
            const wait = Date.parse(card.until) - Date.now(), late = %s;
            setTimeout(() => { __end = { said: document.querySelector('.countdown-card .ask-q')?.innerText, off: [...document.querySelectorAll('.countdown-card button')].every(b => b.disabled) } }, wait + 250);
            if (late !== null) setTimeout(cancel, wait + late) };
          window.cancel = () => window.chrome.webview.postMessage({ op: 'permAnswer', id: __card.id, run: __card.run, answer: 'cancel' });
          window.chrome.webview.addEventListener('message', window.__seen); return true })()""" % json.dumps(late))

    def toasts():
        return js(process, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.innerText).join(' | ')") or ""

    orders = len(ORDERS)
    tag = f"ORDER {SITE} s"
    arm(300)
    ask(process, tag)
    until(lambda: len(calls(tag)) == 2, 30)
    step = calls(tag)[-1] if len(calls(tag)) == 2 else {}
    end = js(process, "window.__end") or {}
    check(not step.get("ok") and "cancelled" in step.get("text", "") and len(ORDERS) == orders, "A Cancel on its way as the countdown ends stops the step, and the AI hears it")
    check(end.get("off") and end.get("said") == "Going ahead…", f"At zero the card says it's going ahead and its buttons are off ({end})")
    check(until(lambda: audit(tag)[-1:] == ["You cancelled it"], 10), "The log says you cancelled it")
    js(process, "cancel()")
    time.sleep(.5)
    check("Too late" not in toasts(), "Cancelling that step twice doesn't say it was too late")

    arm()
    front = rpc(process).get("activeId")
    send(process, "aiSend", text="AGAIN s")  # at once, as the report did: the same chat, on the tab it already has
    check(until(lambda: counting(process), 30), "The next message in the chat runs on its tab, and counts down again")
    check(until(lambda: len(ORDERS) == orders + 1, 20) and until(lambda: calls("AGAIN s") and calls("AGAIN s")[-1]["ok"], 15), "Left alone this time, the step goes ahead")
    check(not cards(process) and not counting(process), "No card is left behind")
    check(rpc(process).get("activeId") == front, "None of it moved you off the tab you're on")
    js(process, "cancel()")
    check(until(lambda: "Too late to cancel" in toasts(), 5), "A Cancel after it went ahead says it was too late")
    check(not js(process, "window.__rejected.length"), "No unhandled rejections through all this")
    idle(process)

    ask(process, "AGAIN u")
    until(lambda: calls("AGAIN u"), 30)
    step = (calls("AGAIN u") or [{}])[-1]
    check(not step.get("ok") and "open_tab" in step.get("text", ""), f"A chat with no page yet is told to open one ({step.get('text', '')[:80]!r})")
    idle(process)


def one_at_a_time(process):
    """Two calls in one breath, over and over: both clicks reach their own buttons, and both say so."""
    send(process, "permReset")
    until(lambda: not rules(), 10)
    good = 0
    for n in range(10):
        tag = f"PAIR {SITE}/shop?k=p{n} r"
        ask(process, tag)
        until(lambda: len(cards(process)) == 2, 30)
        press(process, "Approve all (2)")
        until(lambda: len(calls(tag)) == 2, 30)
        idle(process)
        until(lambda: len([h for h in HITS if h.endswith(f"k=p{n}")]) >= 2, 5)
        here = sorted(h for h in HITS if h.endswith(f"k=p{n}"))
        if len(calls(tag)) == 2 and all(c["ok"] for c in calls(tag)) and here == [f"/hit/cart?k=p{n}", f"/hit/wish?k=p{n}"]:
            good += 1
        else:
            print("   run", n, [(c["ok"], c["text"][:120]) for c in calls(tag)], here, flush=True)
    check(good == 10, f"Two clicks at once land on their own buttons, once each, and neither is reported as missed ({good} of 10)")
    check(not any("/hit/row" in h for h in HITS), "No click lands on the buttons' shared parent")

    # Stop while a click waits its turn: it never happens, even after the first one finishes.
    send(process, "permSet", site="", companion="maya", action="interact", mode="always")
    until(lambda: rules(), 10)
    tag = f"QUEUE {SITE}/shop?k=q r"
    ask(process, tag)
    until(lambda: calls(tag, opens=True), 30, .05)
    time.sleep(1.5)  # the first click is waiting for the slow page, the second behind it
    send(process, "aiStop")
    idle(process)
    time.sleep(5)  # the slow page is in, the turn is free: time enough for a stray click to land
    check("/slow" in HITS, "The first click went through, holding the page's turn")
    check(f"/hit/wish?k=q" not in HITS, "A click still waiting its turn when you press Stop never happens")
    send(process, "permReset")
    until(lambda: not rules(), 10)


def only_what_was_shown(process):
    """Allow is for what the card showed. If the page changes, nothing happens until you've been asked again."""
    send(process, "permReset")
    until(lambda: not rules(), 10)
    orders = lambda who: [o for o in ORDERS if who in o["path"]]

    def change(query):
        """The page changes, and says so: a hidden page's timers run when they like."""
        GO[query] = True
        until(lambda: "/hit/changed?" + query in HITS, 15)

    def swap(how, extra=""):
        query = f"do={how}&k={uuid.uuid4().hex[:6]}{extra}"
        tag = f"SWAP {SITE}/tricky?{query} s"
        ask(process, tag)
        shown = until(lambda: cards(process), 30)
        return query, tag, shown

    # Add to cart turns into a real Place order while the card waits, and you press Allow once.
    before = len(orders("tricky"))
    query, tag, shown = swap("order")
    check(shown and "Add to cart" in shown[0], "The card shows Add to cart")
    change(query)
    press(process, "Allow once")
    again = until(lambda: any("Place order" in c for c in cards(process)) and cards(process), 15)
    check(again and "changed since you were asked" in again[0], "The page changed: Still asks again, naming the new button, and says why")
    check(len(orders("tricky")) == before, "Allow once on Add to cart did not place the order")
    press(process, "Deny")
    idle(process)
    check(len(orders("tricky")) == before, "Denying the new card places nothing")
    logged = lambda: any(a["Result"] == "The page changed, so Still asked again" for c in json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")) for a in c.get("Audit", []))
    check(until(logged, 10), "The log says the page changed")

    # Same words, but now it submits a form: still not what was approved.
    before = len(orders("tricky"))
    query, tag, shown = swap("quiet")
    change(query)
    press(process, "Allow once")
    again = until(lambda: any("changed since you were asked" in c for c in cards(process)), 15)
    check(again, "A button that keeps its words but now submits a form asks again")
    check(len(orders("tricky")) == before, "...and nothing was sent")
    press(process, "Deny")
    idle(process)

    # The tab goes to another site while the card waits.
    query, tag, shown = swap("away", "&to=" + urllib.parse.quote(OTHER + "/tricky?do=none&k=away"))
    GO[query] = True
    time.sleep(1.5)
    press(process, "Allow once")
    again = until(lambda: [c for c in cards(process) if "localhost" in c and "changed since you were asked" in c], 15)
    check(again, "The tab went to another site while the card waited: Still asks again, naming that site")
    check(not [h for h in HITS if "k=away" in h], "...and Allow once for the first site did nothing on the second")
    press(process, "Deny")
    idle(process)

    # The swap happens on the press itself, past every check before it: the guard in the page stops it.
    before = len(orders("tricky"))
    query, tag, shown = swap("press")
    press(process, "Allow once")
    time.sleep(3)
    check(len(orders("tricky")) == before, "A button that swaps at the moment of the press doesn't get the click")
    if any("changed since you were asked" in c for c in cards(process)):
        press(process, "Deny")
    idle(process)

    # A key: the page moves the focus while the card waits (a sensitive site, so Enter asks first).
    send(process, "permSensitive", site="127.0.0.1", on=True)
    query = f"do=focus&k={uuid.uuid4().hex[:6]}"
    tag = f"KEY {SITE}/tricky?{query} s"
    ask(process, tag)
    shown = until(lambda: cards(process), 30)
    check(shown and "Press Enter" in shown[0], "The card shows the key")
    change(query)
    press(process, "Allow once")
    again = until(lambda: any("changed since you were asked" in c for c in cards(process)), 15)
    check(again, "The focus moved while the card waited: Still asks again")
    press(process, "Deny")
    idle(process)
    send(process, "permSensitive", site="127.0.0.1", on=False)

    # The countdown is the same: Add to cart, allowed in this chat as sensitive, turns into Place order at the last moment.
    send(process, "permSet", site="127.0.0.1", action="sensitive", companion="", mode="always")
    send(process, "permSensitive", site="127.0.0.1", on=True)
    before = len(orders("tricky"))
    query = f"do=order&k={uuid.uuid4().hex[:6]}"
    ask(process, f"SWAP {SITE}/tricky?{query} s")
    shown = until(lambda: counting(process), 30)
    check("Add to cart" in (shown or ""), "A sensitive step you allowed counts down, showing Add to cart")
    GO[query] = True  # it runs out with the button already changed
    again = until(lambda: "Place order" in counting(process) and counting(process), 15)
    check(again and "changed since you were asked" in again, "At the end of the countdown the page has changed: a new countdown, naming what's there now")
    check(len(orders("tricky")) == before, "Nothing was ordered on a countdown shown for Add to cart")
    press(process, "Cancel", ".countdown-card")
    idle(process)
    check(len(orders("tricky")) == before, "Cancel on the new countdown: still nothing ordered")
    send(process, "permSensitive", site="127.0.0.1", on=False)
    send(process, "permReset")
    until(lambda: not rules(), 10)


def steady_buttons(process):
    """A new step can't move a button under the cursor, and a press meant for one step can't land on the next."""
    send(process, "permReset")
    until(lambda: not rules(), 10)
    spot = lambda: js(process, """[...document.querySelectorAll('.approve-actions button')].map(b => { const r = b.getBoundingClientRect(); return b.innerText.trim() + '@' + Math.round(r.left) + ',' + Math.round(r.top) + (b.hasAttribute('data-approve') ? '*' : '') })""")
    tag = f"LATER {SITE}/shop?k=l r"
    ask(process, tag)
    until(lambda: len(cards(process)) == 1, 30, .05)
    fresh = js(process, "[...document.querySelectorAll('.approve-actions button')].every(b => b.disabled)")
    check(fresh, "A card that has just appeared doesn't take a click yet")
    time.sleep(.7)
    alone = spot()
    check(alone and alone[-1].startswith("Allow once@") and alone[-1].endswith("*"), f"Allow once is the last button, and the one Ctrl+Enter presses ({alone})")
    until(lambda: len(cards(process)) == 2, 30, .05)
    time.sleep(.7)
    two = spot()
    check(two == alone, f"A second step arriving moves none of the buttons, and they're the same buttons ({two})")
    check(js(process, "!document.querySelector('.approve-all [data-approve]') && !![...document.querySelectorAll('.approve-all button')].find(b => b.innerText.trim() === 'Approve all (2)')"), "Approve all sits apart from them, and Ctrl+Enter can't press it")
    # A double press on Allow once: the first answers the first step, the second lands on a button that isn't ready.
    js(process, """(() => { const once = () => [...document.querySelectorAll('.approve-actions button')].find(b => b.innerText.trim() === 'Allow once'); once().click(); setTimeout(() => once()?.click(), 120); setTimeout(() => once()?.click(), 300); return true })()""")
    until(lambda: "/hit/cart?k=l" in HITS, 15)
    time.sleep(1.5)
    check("/hit/cart?k=l" in HITS and "/hit/wish?k=l" not in HITS, "A quick second press doesn't approve the next step")
    check(len(cards(process)) == 1 and "Save for later" in cards(process)[0], "The next step is still waiting, on its own card")
    press(process, "Deny")
    idle(process)
    check("/hit/wish?k=l" not in HITS, "Deny: it doesn't run")

    send(process, "permSensitive", site="127.0.0.1", on=True)
    ask(process, f"CART {SITE} 1 u")
    check(until(lambda: cards(process), 30), "A sensitive step waits on its card")
    rpc(process, "key", key="K", mods="Control, Shift")
    until(lambda: js(process, "!!document.querySelector('.tasks-menu')"), 5)
    menu = until(lambda: js(process, "[...document.querySelectorAll('.tasks-ask')].map(e => e.innerText).join(' ')"), 5) or ""
    check("Open to decide" in menu and "Allow once" not in menu and "marked" in menu, f"The running tasks menu sends a sensitive step to its card, and says why ({menu})")
    rpc(process, "key", key="Escape", mods="None")
    press(process, "Deny")
    idle(process)
    send(process, "permSensitive", site="127.0.0.1", on=False)


def approve_all(process):
    send(process, "permReset")
    until(lambda: not rules(), 10)
    ask(process, f"BOTH {SITE} j")
    shown = until(lambda: len(cards(process)) == 2 and cards(process), 30)
    check(shown, "Two steps at once share one card")
    capture(process, "approve-all-v01")
    press(process, "Approve all (2)")
    until(lambda: len(calls("BOTH " + SITE + " j")) == 2, 30)
    check(len(calls("BOTH " + SITE + " j")) == 2 and all(c["ok"] for c in calls("BOTH " + SITE + " j")), "Approve all runs both")
    idle(process)

    send(process, "permSensitive", site="localhost", on=True)
    ask(process, f"CART {OTHER} 1 k")
    shown = until(lambda: cards(process), 30)
    check(shown and "marked localhost as sensitive" in shown[0], "On a sensitive site even Add to cart is sensitive")
    send(process, "aiStop")
    check(until(lambda: not cards(process), 10), "Stop takes the card away")
    check(until(lambda: audit("CART " + OTHER + " 1 k")[-1:] == ["Stopped"], 10), "The log says it was stopped")
    idle(process)


def keys_and_help(process):
    """Phase 6: the keyboard over live cards and runs, the help card, the tab cap."""
    ask(process, f"CART {SITE} 1 m")
    check(until(lambda: cards(process), 30), "A card waits for Ctrl+Enter")
    time.sleep(.7)
    js(process, "document.activeElement?.blur?.(); window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))")
    check(until(lambda: calls("CART " + SITE + " 1 m") and calls("CART " + SITE + " 1 m")[-1]["ok"], 15), "Ctrl+Enter approves the card in front of you")
    idle(process)

    ask(process, f"SLOW {SITE} n")
    until(lambda: chat_of(f"SLOW {SITE} n") and calls(f"SLOW {SITE} n") and js(process, "!!document.querySelector('.tasks-button b')"), 30)
    rpc(process, "key", key="K", mods="Control, Shift")
    check(until(lambda: js(process, "!!document.querySelector('.tasks-menu')"), 5), "Ctrl+Shift+K opens the running tasks")
    rpc(process, "key", key="Escape", mods="None")
    check(rpc(process, "key", key="OemPeriod", mods="Control").get("ok") and idle(process), "Ctrl+. stops the chat's run")

    ask(process, f"HELP {SITE} o")
    check(until(lambda: "Help with this page" in (js(process, "document.querySelector('.ask-help')?.innerText ?? ''") or ""), 30), "A page that needs you shows a Help with this page card")
    capture(process, "help-card-v01")
    send(process, "chatPage", on=False)
    check(until(lambda: not js(process, "!!document.querySelector('.page-nav-url')"), 5), "The page beside the chat can be closed")
    check(press(process, "Open the page", ".ask-card") and until(lambda: "127.0.0.1" in (js(process, "document.querySelector('.page-nav-url')?.innerText ?? ''") or "") or any(t["Id"] == rpc(process)["activeId"] and t["Url"].endswith("/shop") for t in rpc(process)["tabs"]), 10), "Open the page shows the page")
    js(process, "[...document.querySelectorAll('.ask-card .ask-option')].find(b => b.innerText.includes(\"I'm done\"))?.click()")
    check(until(lambda: any(c["tool"] == "ask_user" and c["ok"] and "done" in c["text"] for c in calls("HELP " + SITE + " o")), 15), "Its answer reaches the AI")
    idle(process)

    ask(process, f"CAP {SITE} p")
    until(lambda: len(calls("CAP " + SITE + " p", True)) == 7, 60)
    opened = [c["ok"] for c in calls("CAP " + SITE + " p", True)]
    check(opened == [True] * 6 + [False] and "6 tabs" in calls("CAP " + SITE + " p", True)[-1]["text"], "A chat can have 6 tabs open; the 7th is refused and says why")
    idle(process)


def crash_resume(process):
    """A crash mid-run: the next start offers Resume all."""
    tag = f"SLOW {SITE} q"
    ask(process, tag)
    until(lambda: (chat_of(tag) or {}).get("Running"), 30)
    process.kill(); process.wait(timeout=20)
    process = launch(EXE, PROFILE)
    offer = until(lambda: "Resume all" in (js(process, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.innerText).join(' | ')") or ""), 15)
    check(offer, "After a crash, Still offers to resume the chat that was working")
    capture(process, "resume-all-v01")
    js(process, "[...document.querySelectorAll('[data-sonner-toast] button')].find(b => b.innerText.trim() === 'Resume all')?.click()")
    check(until(lambda: any("Picked up where it stopped" in (m.get("Text") or "") for m in (chat_of(tag) or {}).get("Messages", [])), 15), "Resume all sends the chat on")
    send(process, "aiStop", id=(chat_of(tag) or {}).get("Id", ""))
    return process


def outside(process):
    """Another AI app (no chat) keeps today's behavior: allowed, unless a rule for everyone says to ask. Then it asks in
    the bar at the top, once per site until Still closes."""
    agent = Mcp(EXE, "Probe", PROFILE)
    try:
        pending = call_async(agent, "list_tabs")
        until(lambda: "Probe" in (js(process, "document.body.innerText") or ""), 30)
        send(process, "agentAnswer", allow=True)
        pending.get(timeout=60)
        agent.call("open_tab", url=SITE + "/shop")
        started = time.monotonic()
        ok, text = agent.call("click", selector="#cart", seconds=20)
        check(ok and time.monotonic() - started < 5, "Without a rule an outside AI app clicks without asking, as before")
        send(process, "permSet", site="127.0.0.1", action="interact", companion="", mode="chat")
        pending = call_async(agent, "click", selector="#cart")
        asked = until(lambda: "wants to click" in (js(process, "document.body.innerText") or ""), 30)
        check(asked, "With a rule for everyone it asks in the bar first")
        send(process, "agentAnswer", allow=True)
        ok, text = pending.get(timeout=60)
        if not ok and "Allow" in text:  # the user counted as away: the answer applies to the next call
            ok, text = agent.call("click", selector="#cart")
        check(ok, "Allow lets it click")
        started = time.monotonic()
        ok, text = agent.call("click", selector="#cart", seconds=20)
        check(ok and time.monotonic() - started < 5, "The next click on that site doesn't ask again")
    finally:
        agent.close()
        send(process, "permSet", site="127.0.0.1", action="interact", companion="", mode="")


def settings(process):
    send(process, "permSet", site="shop.example", action="interact", companion="maya", mode="ask")
    send(process, "permSensitive", site="mybank.example", on=True)
    send(process, "openPanel", name="settings")
    until(lambda: js(process, "!!document.querySelector('.set-shell')"), 10)
    js(process, "[...document.querySelectorAll('.set-nav-item')].find(t => t.innerText.trim() === 'Privacy & permissions')?.click()")
    table = until(lambda: js(process, "document.querySelector('.perm-table')?.textContent ?? ''"), 10) or ""
    check("Any site" in table and "Sensitive steps" in table and "shop.example" in table and "Maya" in table, "Settings list the defaults and the rule for Maya on shop.example")
    check("mybank.example" in (js(process, "document.querySelector('.perm-sites')?.textContent ?? ''") or ""), "Settings list the sensitive sites")
    capture(process, "permissions-v01")
    press(process, "Reset all", ".perm-settings")
    until(lambda: js(process, "!!document.querySelector('[data-slot=alert-dialog-action]')"), 3)
    js(process, "document.querySelector('[data-slot=alert-dialog-action]')?.click()")
    check(until(lambda: not rules() and "shop.example" not in (js(process, "document.querySelector('.perm-table')?.textContent ?? ''") or ""), 15), "Reset all asks, then goes back to the defaults once Undo is gone")
    js(process, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    until(lambda: not js(process, "!!document.querySelector('.set-shell')"), 5)

    first = chat_of("CART " + SITE + " 2 a")
    send(process, "chatOpen", id=first["Id"])
    until(lambda: js(process, "!!document.querySelector('[aria-label=\"Chat details\"]')"), 10)
    if not js(process, "!!document.querySelector('.chat-info')"):
        js(process, "document.querySelector('[aria-label=\"Chat details\"]').click()")
    log = until(lambda: js(process, "document.querySelector('.audit-list')?.innerText ?? ''"), 10) or ""
    check("You allowed it in this chat" in log and "Add to cart" in log, "The chat's details show its permission log")
    capture(process, "audit-v01")


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
