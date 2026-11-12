"""Tasks: every run has a state (running, paused, waiting, interrupted, completed, failed) and a checkpoint on disk after
each step. A fake AI app drives a local shop through Still's MCP server.

1. States: a question and an approval card wait, Take over pauses, Stop ends it, a crash of the AI app fails it.
2. Still is killed while Place order is under way (the shop holds its answer). After the restart nothing shows as running,
   one offer lists both cut-off chats, and Resume the others leaves out the one whose order may have gone through.
3. That one is resumed from its chat: the AI app has lost its session, so Still starts a new one from the checkpoint and
   says so. The new run is told what it did and what to check, and Place order asks again with a card (no countdown,
   though a standing rule allows it), so cancelling it leaves one order at the shop, not two.

Run: python tests/desktop/tasks.py artifacts/Still-QA/Still.exe
Out: artifacts/tasks-*/
"""
import http.server
import json
from pathlib import Path
import shutil
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
import qa
from qa import press_ready, js, rpc, send, until

EXE = Path(sys.argv[1]).resolve()
RUN = Path(__file__).resolve().parents[2] / "artifacts" / f"tasks-{uuid.uuid4().hex[:8]}"
PROFILE, BIN = RUN / "profile", RUN / "bin"
ORDERS, HOLD = [], threading.Event()
results = []


def check(ok, name):
    results.append({"name": name, "ok": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


SHOP = """<!doctype html><meta charset=utf-8><title>Maple Market</title><h1>Trail mug</h1>
<button type=button id=cart onclick="this.dataset.n=(+this.dataset.n||0)+1">Add to cart</button>
<form id=checkout method=post action=/order><label>Name <input id=name name=name></label><button id=order>Place order</button></form>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.page(SHOP)

    def do_POST(self):
        ORDERS.append(urllib.parse.parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()))
        HOLD.wait(30)  # the first order: Still is killed before the shop answers
        self.page("<!doctype html><title>Thanks</title><h1>Thanks, your order is placed</h1>")

    def page(self, html):
        body = html.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        try: self.wfile.write(body)
        except OSError: pass

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
SITE = f"http://127.0.0.1:{SERVER.server_port}"

FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, threading, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed out" if os.path.exists(os.path.join(here, "signedout")) else "signed in"); sys.exit(0)
    prompt = sys.stdin.buffer.read().decode("utf-8")
    tag = prompt.rsplit("\n\n", 1)[-1].strip() if "[Still] Still closed" not in prompt else "RESUME " + re.search(r"What you were asked: (\S+)", prompt)[1]
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"tag": tag, "args": args, "prompt": prompt}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    if "--resume" in args and os.path.exists(os.path.join(here, "forget")):
        print("No conversation found with session ID: " + args[args.index("--resume") + 1], file=sys.stderr, flush=True); sys.exit(1)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if tag.startswith("FAIL"): print("Something broke", file=sys.stderr, flush=True); sys.exit(1)
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
    def call(tool, **a):
        r = request("tools/call", {"name": tool, "arguments": a})["result"]
        ok = not r.get("isError")
        with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"tag": tag, "tool": tool, "ok": ok, "t": time.time()}) + "\n")
        return ok
    def reply(text): say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    site = re.search(r"(http://127\.0\.0\.1:\d+)", prompt)[1]
    if tag.startswith("ASK"):
        call("ask_user", question="Which size?", options=["Small", "Large"])
    elif tag.startswith("CART"):
        call("open_tab", url=site + "/shop"); call("click", selector="#cart")
    elif tag.startswith("SLOW"):
        call("open_tab", url=site + "/shop")
        for _ in range(20): call("wait_for", text="never shows up", timeoutMs=30000)
    elif tag.startswith("BUY"):
        call("open_tab", url=site + "/shop"); call("type", selector="#name", text="Sam"); call("click", selector="#order")
    elif tag == "RESUME BUY":
        call("open_tab", url=site + "/shop"); call("read_page")
        call("click", selector="#order")  # a careless app tries again: Still asks the user first
        reply("Already done: opened the shop and typed the name. Checked again: the order page."); sys.exit(0)
    elif tag.startswith("RESUME SLOW"):
        for _ in range(20): call("wait_for", text="never shows up", timeoutMs=30000)
    reply("Done.")
    still.stdin.close()
''')


def task(chat):
    try: return json.loads((PROFILE / "ai" / "tasks" / f"{chat}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


def chats():
    try: return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return []


def chat_id(tag):
    return next((c["Id"] for c in chats() if c["Title"].startswith(tag)), None)


def state(tag):
    t = task(chat_id(tag) or "-")
    return (t.get("State"), t.get("Reason", ""))


def prompts(tag):
    file = BIN / "prompts.jsonl"
    return [p for p in (json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.endswith("}")) if p["tag"] == tag] if file.exists() else []


def calls(tag):
    file = BIN / "calls.jsonl"
    return [c for c in (json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.endswith("}")) if c["tag"].startswith(tag)] if file.exists() else []


def ask(p, tag):
    send(p, "new"); until(lambda: js(p, "!!document.querySelector('.home-rail')"), 20); time.sleep(.4)
    send(p, "aiSend", text=f"{tag} {SITE}", home=True, companion="maya")
    return until(lambda: chat_id(tag), 15)


def press(p, words, within=".ask-card"):
    return press_ready(p, f"[...document.querySelectorAll({json.dumps(within + ' button')})].find(b => b.innerText.trim() === {json.dumps(words)})")


def toasts(p):
    return js(p, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.innerText).join(' | ')") or ""


def quit(p):
    try: rpc(p, "quit")
    except RuntimeError: pass
    try: p.wait(timeout=20)
    except Exception: p.kill()


shutil.rmtree(RUN, ignore_errors=True)
(PROFILE / "agents").mkdir(parents=True); BIN.mkdir()
(BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8"); qa.launcher(BIN / "fakeagent", BIN / "fake_agent.py")
(PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
    "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "home", "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}],
    "Preferences": {"AiHarness": "fake", "AgentsEnabled": True, "Companions": qa.CREW}}))

p = qa.launch(EXE, PROFILE)
try:
    # 1. States.
    ask(p, "ASK")
    check(until(lambda: state("ASK") == ("waiting", "answer"), 20), f"A question: waiting for an answer ({state('ASK')})")
    check(task(chat_id("ASK")).get("Pending") == "Which size?", "...and the checkpoint has the question")
    send(p, "aiAnswer", text="Small")
    check(until(lambda: state("ASK") == ("completed", ""), 20), f"Answered and done: completed ({state('ASK')})")

    ask(p, "CART")
    check(until(lambda: state("CART") == ("waiting", "approval"), 20), f"An approval card: waiting for approval ({state('CART')})")
    press(p, "Allow")
    check(until(lambda: state("CART") == ("completed", ""), 20), f"Allowed and done: completed ({state('CART')})")
    steps = [s["What"] for s in task(chat_id("CART")).get("Steps", [])]
    check(len(steps) == 2 and all(s["Ok"] for s in task(chat_id("CART"))["Steps"]), f"A checkpoint after each step ({steps})")
    check(any(SITE in u for u in task(chat_id("CART")).get("Tabs", [])) and task(chat_id("CART")).get("LastAudit"), "...with its tabs and the last audit entry")

    slow = ask(p, "SLOW one")
    check(until(lambda: state("SLOW one") == ("running", "") and len(calls("SLOW one")) >= 1, 20), f"At work: running ({state('SLOW one')})")
    send(p, "agentTakeOver", on=True, key=slow)
    check(until(lambda: state("SLOW one")[0] == "paused", 10), f"Take over: paused ({state('SLOW one')})")
    send(p, "agentTakeOver", on=False, key=slow)
    check(until(lambda: state("SLOW one")[0] == "running", 10), "Handed back: running")
    send(p, "aiStop", id=slow)
    check(until(lambda: state("SLOW one") == ("completed", "stopped"), 20), f"Stop: completed, stopped by you ({state('SLOW one')})")

    ask(p, "FAIL")
    check(until(lambda: state("FAIL") == ("failed", ""), 20), f"The AI app fails: failed ({state('FAIL')})")

    # 2. Killed mid-task, one of them during Place order.
    send(p, "permSet", site="127.0.0.1", action="interact", companion="", mode="chat")
    send(p, "permSet", site="127.0.0.1", action="sensitive", companion="", mode="always")
    ask(p, "SLOW two")
    until(lambda: len(calls("SLOW two")) >= 1, 20)
    ask(p, "BUY")
    until(lambda: press(p, "Allow"), 20)  # typing the name: allowed for this chat only
    until(lambda: press(p, "Do it now", ".countdown-card"), 20)  # the standing rule for purchases counts down
    check(until(lambda: ORDERS, 20), "Place order reached the shop")
    unsure = [s for s in task(chat_id("BUY")).get("Sensitive", []) if s.get("Outcome") is None]
    check(len(unsure) == 1 and "Place order" in unsure[0]["What"], f"Before it runs, the step is on disk with no outcome yet ({unsure})")
finally:
    p.kill(); p.wait(timeout=20)  # a crash, mid-order
HOLD.set()
(PROFILE / "qa-pipe.txt").unlink(missing_ok=True)
buy, two = chat_id("BUY"), chat_id("SLOW two")
saved = chats()
check(next(c for c in saved if c["Id"] == buy).get("Session"), "The order chat's session was on disk before the crash")
for c in saved:
    if c["Id"] == buy: c["Allowed"] = ["interact 127.0.0.1"]  # an approval for this chat, as a later save would have kept it
    if c["Id"] == two: c["Session"], c["Started"] = None, False  # a session that never reached the disk
(PROFILE / "ai" / "chats.json").write_text(json.dumps(saved), encoding="utf-8")

p = qa.launch(EXE, PROFILE)
try:
    until(lambda: js(p, "!!document.body.innerText.length"), 20)
    check(state("BUY") == ("interrupted", "") and state("SLOW two") == ("interrupted", ""), f"After the restart both are interrupted ({state('BUY')}, {state('SLOW two')})")
    check(not rpc(p).get("runs") and not js(p, "document.querySelector('.tasks-button')?.getAttribute('aria-label')?.match(/[1-9]\\d* running/)"), "Nothing shows as running")
    offer = until(lambda: "stopped mid-task" in toasts(p) and toasts(p), 15) or ""
    check("BUY" in offer and "SLOW two" in offer, f"One offer lists the cut-off chats ({offer!r})")
    check("may not have finished" in offer and "Resume the others" in offer and "Resume all" not in offer, "...and leaves out the one with an order that may have gone through")
    # Signed out between runs: the task waits with Sign in, and nothing runs.
    (BIN / "signedout").write_text(""); send(p, "aiCheck"); time.sleep(3)
    press(p, "Resume the others", "[data-sonner-toast]")
    check(until(lambda: state("SLOW two") == ("waiting", "signin"), 15) and not prompts("RESUME SLOW"), f"Signed out: Resume leaves it waiting for a sign-in ({state('SLOW two')})")
    send(p, "chatOpen", id=two)
    bar = until(lambda: (lambda b: b if "sign in" in b else "")(js(p, "document.querySelector('.task-bar')?.innerText ?? ''") or ""), 15) or ""
    check("sign in" in bar and "Sign in" in bar and "Resume" in bar, f"The chat offers Sign in and Resume ({bar!r})")
    (BIN / "signedout").unlink(); send(p, "aiCheck"); time.sleep(3)
    press(p, "Resume", ".task-bar")
    check(until(lambda: prompts("RESUME SLOW"), 15), "Signed in again, Resume picks it up")
    brief = (prompts("RESUME SLOW") or [{}])[0].get("prompt", "")
    check("What you were asked: SLOW two" in brief and "read each page again" in brief and "Tabs you had open" in brief, "...told what it was doing, its tabs, and to read pages again")
    note = lambda chat: [m["Text"] for c in chats() if c["Id"] == chat for m in c["Messages"] if m["Role"] == "note"]
    check(until(lambda: any("starts a new one from where the task got to" in n for n in note(two)), 10), f"Its session was never saved: the chat says it starts a new one ({note(two)})")
    time.sleep(2)
    check(not prompts("RESUME BUY"), "The order chat isn't resumed with the others")
    send(p, "aiStop", id=two)

    # 3. Resumed by hand; its AI app has lost the session.
    (BIN / "forget").write_text("")
    send(p, "chatOpen", id=buy)
    bar = until(lambda: js(p, "document.querySelector('.task-bar')?.innerText ?? ''"), 15) or ""
    check("may not have finished" in bar and bar.startswith("Stopped: "), f"The chat says it stopped, and a step may not have finished ({bar!r})")
    press(p, "Continue", ".task-bar")
    check(until(lambda: any("--resume" not in x["args"] for x in prompts("RESUME BUY")), 20), "The lost session is replaced by a new one")
    check(any("--resume" in x["args"] for x in prompts("RESUME BUY")), "It tried the saved session first")
    check(until(lambda: any("started a new one from where the task got to" in n for n in note(buy)), 10), f"...and the chat says so ({note(buy)})")
    brief = next(x["prompt"] for x in prompts("RESUME BUY") if "--resume" not in x["args"])
    check("Click “Place order”" in brief and "may or may not have gone through" in brief and "Check the site first" in brief, "The new run is told what it did and to check the order first")
    card = until(lambda: js(p, "document.querySelector('.approve-card')?.innerText ?? ''"), 45) or ""  # opening the shop can take up to 15 s
    check("Place order" in card and not js(p, "!!document.querySelector('.countdown-card')"), f"Trying it again asks with a card, not a countdown ({card[:80]!r})")
    press(p, "Not now")
    check(until(lambda: state("BUY")[0] == "completed", 20), f"The resumed task completes ({state('BUY')})")
    check(any("Already done:" in m.get("Text", "") for c in chats() if c["Id"] == buy for m in c["Messages"] if m["Role"] == "assistant"), "The reply says what was done and what was checked again")
    check(len(ORDERS) == 1, f"One order at the shop, not two ({len(ORDERS)})")
    allowed = next(c for c in chats() if c["Id"] == buy).get("Allowed", [])
    check("interact 127.0.0.1" not in allowed, f"The chat's own approval ended with the restart ({allowed})")
    rules = json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"].get("Permissions", [])
    check(any(r["Action"] == "sensitive" and r["Mode"] == "always" for r in rules), "The standing rule is still there")
    errors = rpc(p).get("shellErrors") or js(p, "window.__shellErrors")
    check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))

    # 4. Quit normally mid-task: the next start offers it too.
    four = ask(p, "SLOW four")
    until(lambda: len(calls("SLOW four")) >= 1, 20)
finally:
    quit(p)
(PROFILE / "qa-pipe.txt").unlink(missing_ok=True)
check(state("SLOW four")[0] in ("running", "interrupted"), f"Quitting mid-task leaves it unfinished ({state('SLOW four')})")
p = qa.launch(EXE, PROFILE)
try:
    until(lambda: js(p, "!!document.body.innerText.length"), 20)
    check(state("SLOW four") == ("interrupted", ""), f"After a normal quit and start it's interrupted ({state('SLOW four')})")
    check(until(lambda: "SLOW four" in toasts(p), 15), "...and offered to resume")
finally:
    quit(p)
    SERVER.shutdown()

(RUN / "results.json").write_text(json.dumps(results, indent=1))
failed = [r for r in results if not r["ok"]]
print(f"{'FAILED' if failed else 'PASSED'} {len(results) - len(failed)}/{len(results)} -> {RUN}")
sys.exit(1 if failed else 0)
