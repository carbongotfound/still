"""Phase 4: the permission layer. A fake AI app drives a local shop through Still's MCP server, and the test answers
the cards like a person would.

  CART <site> <n>   clicks Add to cart n times (interact)
  ORDER <site>      types a name, then clicks Place order on a form that posts (sensitive)
  BOTH <site>       clicks Add to cart and Save for later at the same time (two cards: Approve all)

Checks: once per chat / always / ask every time, a sensitive step always shows a card or a countdown, Cancel and the
countdown running out, Approve all, sensitive sites, Stop during a card, an outside AI app asking in the bar, the
settings page and Reset all, and the audit log in the chat's details.

Run: python tests/desktop/permissions.py artifacts/Still-QA/Still.exe
Screenshots: docs/agentic/compare/ (approval-v01, sensitive-v01, countdown-v01, approve-all-v01, permissions-v01, audit-v01)
"""
import http.server
import json
from pathlib import Path
import re
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, rpc, send, until  # noqa: E402
from mcp_client import Mcp, call_async  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("permissions-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
OUT = ROOT / "docs" / "agentic" / "compare"
RESULT = {"checks": []}
ORDERS = []


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
<button type=button id=cart onclick="this.dataset.n=(+this.dataset.n||0)+1">Add to cart</button> <button type=button id=wish onclick="this.dataset.n=1">Save for later</button></section>
<section><h2>Checkout</h2><form id=checkout method=post action=/order><p><label>Name <input id=name name=name></label></p><button id=order>Place order</button></form></section></main>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.page(SHOP if self.path.startswith("/shop") else "<!doctype html><title>Page</title><p>Page")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        ORDERS.append({"path": self.path, "body": urllib.parse.parse_qs(body), "t": time.time()})
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
    def log(entry):
        with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(entry) + "\n")
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
    def call(tool, **a):
        r = request("tools/call", {"name": tool, "arguments": a})["result"]
        ok, text = not r.get("isError"), "\n".join(c.get("text", "") for c in r.get("content", []))
        log({"chat": tag, "tool": tool, "args": a, "ok": ok, "text": text[:300], "t": time.time()})
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
    reply("Done.")
    still.stdin.close()
''')


def calls(chat):
    file = BIN / "calls.jsonl"
    rows = [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []
    return [c for c in rows if c["chat"] == chat and c["tool"] != "open_tab"]


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
    return js(process, f"(() => {{ const b = [...document.querySelectorAll({json.dumps(within + ' button')})].find(b => b.innerText.trim() === {json.dumps(words)}); b?.click(); return !!b }})()")


def ask(process, tag):
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 20)
    time.sleep(.4)
    send(process, "aiSend", text=tag, home=True, companion="pip")


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
    (BIN / "fakeagent.cmd").write_text(f'@"{sys.executable}" -I "{BIN / "fake_agent.py"}" %*\r\n')
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 5, "Welcome": False, "Preferences": {"AgentsEnabled": True, "AiHarness": "fake", "Theme": "Light", "Width": 1720, "Height": 1080},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    try:
        once_per_chat(process)
        ask_every_time(process)
        sensitive(process)
        approve_all(process)
        outside(process)
        settings(process)
        check(not js(process, "window.__shellErrors?.length") and not rpc(process).get("shellErrors"), "No interface errors")
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


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
    send(process, "permSet", site="shop.example", action="interact", companion="pip", mode="ask")
    send(process, "permSensitive", site="mybank.example", on=True)
    send(process, "openPanel", name="settings")
    until(lambda: js(process, "!!document.querySelector('.settings-tabs')"), 10)
    js(process, "[...document.querySelectorAll('.settings-tabs [role=tab]')].find(t => t.innerText.includes('AI permissions'))?.focus()")  # tabs switch on focus
    table = until(lambda: js(process, "document.querySelector('.perm-table')?.textContent ?? ''"), 10) or ""
    check("Any site" in table and "Sensitive steps" in table and "shop.example" in table and "Pip" in table, "Settings list the defaults and the rule for Pip on shop.example")
    check("mybank.example" in (js(process, "document.querySelector('.perm-sites')?.textContent ?? ''") or ""), "Settings list the sensitive sites")
    capture(process, "permissions-v01")
    press(process, "Reset all", ".perm-settings")
    press(process, "Reset now", ".perm-settings")
    check(until(lambda: not rules() and "shop.example" not in (js(process, "document.querySelector('.perm-table')?.textContent ?? ''") or ""), 10), "Reset all goes back to the defaults")
    js(process, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    until(lambda: not js(process, "!!document.querySelector('.settings-tabs')"), 5)

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
