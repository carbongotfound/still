"""Companions message each other: ask_companion waits for the teammate's reply, tell_companion hands work over, and
list_companions says who's on the team. The one asked answers in its own chat with its own memory, and the chat the user
is in shows each exchange as a card (who asked whom, the message, Working / Replied / Failed / Stopped, the reply) that
opens to all of it and to the other side's chat. Stop on a card stops that exchange; stopping a chat stops whoever it
asked. Exchanges go at most 3 hops deep and about 10 messages per request, a teammate already in one can't be asked again
(a loop), and none messages itself. @Name in the message box has the current companion ask that teammate. Team chats
from before are split into each companion's own chat, so nothing is lost. The # and @ pickers in the message box too.

No AI plan is used: a fake agent app plays every companion. It finds who it is in the prompt ("Your name is Maya.", or
its session on a resumed run) and plays that companion's next line from plan.json ({name: [{text, sleep, remember,
calls}]}): calls are Still tools it calls through MCP in order, and {0}, {1}... in its text are their results. Every run
goes to prompts.jsonl and every call to calls.jsonl.

Run: python tests/desktop/exchange.py artifacts/Still-QA/Still.exe [OUTDIR]  (OUTDIR: screenshots)
"""
import http.server
import json
from pathlib import Path
import shutil
import sys
import textwrap
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

RUN = ROOT / "artifacts" / ("exchange-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []

FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    found = re.search(r"Your name is (\w+)\.", prompt)
    name = found.group(1) if found else args[args.index("--resume") + 1].split("-")[0] if "--resume" in args else "nobody"
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"name": name, "args": args, "prompt": prompt}) + "\n")
    lines = json.load(open(os.path.join(here, "plan.json"), encoding="utf-8")).get(name) or [{"text": "Okay."}]
    count = os.path.join(here, "n-" + name)
    n = int(open(count).read()) if os.path.exists(count) else 0
    open(count, "w").write(str(n + 1))
    line = lines[min(n, len(lines) - 1)]
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": args[args.index("--resume") + 1] if "--resume" in args else "%s-%d" % (name, time.time_ns())})
    if line.get("say"): say({"type": "assistant", "message": {"content": [{"type": "text", "text": line["say"]}]}})  # written before its tool calls
    calls = ([{"name": "remember", "arguments": {"fact": line["remember"], "kind": "project"}}] if line.get("remember") else []) + line.get("calls", [])
    for call in line.get("calls", []) if line.get("steps") else []: say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": call["name"], "name": "mcp__still__" + call["name"], "input": call["arguments"]}]}})
    results = []
    if calls:
        server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
        still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        def request(i, method, params):
            still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n").encode()); still.stdin.flush()
            for out in still.stdout:
                try: m = json.loads(out)
                except ValueError: continue
                if m.get("id") == i: return m
        request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
        still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
        for i, call in enumerate(calls):
            r = request(10 + i, "tools/call", call) or {}
            text = "".join(c.get("text", "") for c in r.get("result", {}).get("content", []))
            if call["name"] != "remember": results.append(text)
            with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"name": name, "call": call, "error": r.get("result", {}).get("isError", False), "text": text}) + "\n")
        still.stdin.close()
    time.sleep(line.get("sleep", 0))
    text = line.get("text", "")
    for i, r in enumerate(results): text = text.replace("{%d}" % i, r)
    if text: say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
''')


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def plan(lines):
    """What each companion says next, from its first line on."""
    for f in BIN.glob("n-*"):
        f.unlink()
    (BIN / "plan.json").write_text(json.dumps(lines), encoding="utf-8")


def jsonl(name):
    file = BIN / name
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def prompts():
    return jsonl("prompts.jsonl")


def calls(name=None, tool=None):
    return [c for c in jsonl("calls.jsonl") if (name is None or c["name"] == name) and (tool is None or c["call"]["name"] == tool)]


def chats():
    for _ in range(50):
        try:
            return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.05)
    return []


def chat(id):
    return next((c for c in chats() if c["Id"] == id), {})


def asked_by(id, who):
    """The chat where companion who answers what chat id asked it."""
    return next((c for c in chats() if c.get("From") == id and c["Companion"] == who), {})


def facts(who):
    try:
        return json.loads((PROFILE / "companions" / who / "memory.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def said(c):
    return [m["Text"] for m in c.get("Messages", []) if m["Role"] == "assistant"]


def cards(c):
    return [(m["Role"], m.get("Who"), m.get("To"), m.get("Status")) for m in c.get("Messages", []) if m["Role"] in ("ask", "tell")]


def settled(id, replies, wait=40):
    """Waits for the chat to stop running after at least that many replies."""
    return until(lambda: (c := chat(id)) and not c.get("Running") and len(said(c)) >= replies, wait)


def new_chat(text, **extra):
    """A new chat from a new tab; returns its id once it exists."""
    before = {c["Id"] for c in chats()}
    send(P, "new")
    until(lambda: js(P, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
    js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    send(P, "aiSend", text=text, home=True, **extra)
    return until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before and not c.get("From")), None), 10) or ""


BOX = ".chat-view [aria-label=Message], .home-compose [aria-label=Message]"


def type_in(text, more=False):
    """Types into the message box without sending: in place of what's there, or (more) after it."""
    js(P, f"""(() => {{ const e = document.querySelector('{BOX}'), s = getSelection(); e.focus(); s.selectAllChildren(e); {'s.collapseToEnd();' if more else ''}
        document.execCommand({json.dumps('insertText' if text else 'delete')}, false, {json.dumps(text)}) }})()""")
    time.sleep(.25)


def key(name, caret=None):
    """A key the box handles itself (pickers, Enter, Backspace), with the caret at the end or at the start (caret=0)."""
    js(P, f"""(() => {{ const e = document.querySelector('{BOX}'), s = getSelection(); e.focus(); {'s.selectAllChildren(e); s.collapse' + ('ToStart' if caret == 0 else 'ToEnd') + '();' if caret is not None else ''}
        e.dispatchEvent(new KeyboardEvent('keydown', {{ key: {json.dumps(name)}, bubbles: true, cancelable: true }})) }})()""")
    time.sleep(.25)


KEYS = {"Backspace": 8, "Delete": 46, "ArrowLeft": 37, "ArrowRight": 39}


def press(name):
    """A real key press, as the keyboard sends it."""
    for kind in ("rawKeyDown", "keyUp"):
        rpc(P, "shellCdp", method="Input.dispatchKeyEvent", parameters={"type": kind, "key": name, "code": name, "windowsVirtualKeyCode": KEYS[name]})
    time.sleep(.25)


def box_text():
    """The box's text, a mention as its name."""
    return js(P, f"document.querySelector('{BOX}').innerText.replace(/\\u00a0/g, ' ')")


def before_caret():
    """What's before the caret: its text and how many mentions."""
    return json.loads(js(P, f"""JSON.stringify((() => {{ const e = document.querySelector('{BOX}'), s = getSelection(), r = document.createRange()
        r.setStart(e, 0); r.setEnd(s.anchorNode, s.anchorOffset); const d = r.cloneContents(); return [d.textContent.replace(/\\u00a0/g, ' '), d.querySelectorAll('[data-mention]').length] }})())"""))


def picker():
    """The open picker: its label and each option's text."""
    return json.loads(js(P, "JSON.stringify((m => m ? [m.getAttribute('aria-label'), [...m.querySelectorAll('[role=option]')].map(o => o.querySelector(':scope > b').innerText + ' · ' + o.querySelector(':scope > span:last-child').innerText)] : null)(document.querySelector('.chat-view .skill-menu, .home-compose .skill-menu')))") or "null")


def chips():
    """The mentions in the box, by name, in order."""
    return json.loads(js(P, f"JSON.stringify([...document.querySelectorAll('{BOX}')].flatMap(b => [...b.querySelectorAll('.mention')].map(c => c.innerText.trim())))") or "[]")


def shown_cards():
    return json.loads(js(P, "JSON.stringify([...document.querySelectorAll('.chat-view .exchange')].map(e => [e.querySelector('.exchange-who').innerText, e.dataset.status, e.querySelector('.exchange-status').innerText]))") or "[]")


def shot(name):
    time.sleep(.8)
    rpc(P, "capture", name=name)
    if (PROFILE / name).exists():
        shutil.copy(PROFILE / name, OUT / name)


def pages():
    """Two pages: a review, and one that will sit in a private tab."""
    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            title = "Desk lamp review" if "review" in self.path else "Secret plans"
            body = f"<!doctype html><title>{title}</title><h1>{title}</h1><p>Warm 2700K light, no glare.</p>".encode()
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


# A team chat from before: Maya and Jonah in one thread, a handoff between them, each on its own AI session.
OLD_TEAM = {"Id": "oldteam", "Title": "Launch the desk lamp", "Harness": "fake", "Started": True, "Companion": "jonah", "Session": "Jonah-1",
            "Team": ["maya", "jonah"], "Sessions": {"maya": "Maya-1", "jonah": "Jonah-1"}, "Updated": "2026-10-01T10:00:00Z", "Messages": [
                {"Role": "user", "Text": "Help me launch our new desk lamp."},
                {"Role": "assistant", "Text": "People ask about glare, warmth and price.", "Who": "maya"},
                {"Role": "handoff", "Text": "Write a two-line launch pitch.", "Who": "maya", "To": "jonah", "Status": "done"},
                {"Role": "assistant", "Text": "No glare. Warm light. Fair price.", "Who": "jonah"}]}


def setup(theme="Light"):
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    crew = [{**c, "Crew": {"maya": "research", "jonah": "sales", "nora": "planner", "rosa": "organizer"}.get(c["Id"], "")} for c in CREW]
    crew.append({"Id": "leo", "Name": "Leo", "Job": "A marketer: writes posts and plans campaigns.", "Crew": "marketing"})
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([OLD_TEAM]))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake", "Theme": theme,
        "Width": 1280, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, PROFILE)


def main():
    global P
    OUT.mkdir(parents=True, exist_ok=True)
    P = setup()
    try:
        until(lambda: js(P, "!!document.body.innerText.length"), 20)
        send(P, "new")
        until(lambda: js(P, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
        js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        time.sleep(.5)
        check(not js(P, "!!document.querySelector('.mate-switch-team')") and "Team chat" not in (js(P, "document.body.innerText") or ""), "There's no Team chat button any more")
        shot("home.png")

        # The old team chat: Maya keeps the original (and its session), Jonah gets the whole thread as its own chat.
        old, mine = chat("oldteam"), next((c for c in chats() if c["Id"] != "oldteam" and c["Title"] == "Launch the desk lamp"), {})
        check(old.get("Companion") == "maya" and old.get("Session") == "Maya-1" and not old.get("Team") and not old.get("Sessions"), f"Maya keeps the old team chat, on its own session ({old.get('Companion')}, {old.get('Session')})")
        check(mine.get("Companion") == "jonah" and mine.get("Session") == "Jonah-1" and [m["Text"] for m in mine["Messages"]] == [m["Text"] for m in old["Messages"]],
              "Jonah gets the whole thread as a chat of its own, on its own session")
        check(cards(old) == [("tell", "maya", "jonah", "replied")] and old["Messages"][2].get("Chat") == mine.get("Id"), f"The handoff becomes a card that opens Jonah's chat ({cards(old)})")
        check([m.get("Who") for m in old["Messages"] if m["Role"] == "assistant"] == [None, "jonah"] and [m.get("Who") for m in mine["Messages"] if m["Role"] == "assistant"] == ["maya", None],
              "In each, the other companion's lines keep their face")
        plan({"Jonah": [{"text": "Still here: the pitch was No glare. Warm light. Fair price."}]})
        send(P, "chatOpen", id=mine["Id"])
        until(lambda: js(P, "!!document.querySelector('.chat-view [aria-label=Message]')"), 10)
        shot("migrated.png")
        send(P, "aiSend", text="What was the pitch again?")
        check(settled(mine["Id"], 3), "Jonah answers in its migrated chat")
        last = prompts()[-1]
        check(last["name"] == "Jonah" and "--resume" in last["args"] and last["args"][last["args"].index("--resume") + 1] == "Jonah-1", "picking up its own session from the team chat")

        # Ask and reply: Maya lists the team, asks Jonah and uses the answer. Jonah answers in its own chat and remembers
        # in its own memory; asking itself is refused.
        site = pages()
        send(P, "new", url=site + "/secret", private=True)
        plan({"Maya": [{"text": "Jonah's pitch: {1}", "calls": [{"name": "list_companions", "arguments": {}}, {"name": "ask_companion", "arguments": {"name": "Jonah", "message": "Write a one-line pitch for a warm desk lamp."}},
                                                                {"name": "ask_companion", "arguments": {"name": "Maya", "message": "Hi me."}}]}],
              "Jonah": [{"text": "**No glare, warm light, fair price.**", "remember": "Pitches lead with comfort", "sleep": 1.5, "calls": [{"name": "list_tabs", "arguments": {}}]}]})
        ask = new_chat("Find me a desk lamp, and get a pitch for it.", companion="maya")
        check(until(lambda: cards(chat(ask)) == [("ask", "maya", "jonah", "working")], 15), "Maya's ask shows in the chat as a card, Working")
        check(until(lambda: [c[1:] for c in shown_cards()] == [["working", "Working"]], 5), "The card says Working on screen")
        shot("ask-working.png")
        check(settled(ask, 1), "Maya finishes")
        c, z = chat(ask), asked_by(ask, "jonah")
        team = calls("Maya", "list_companions")[0]["text"]
        check(all(n in team for n in ("Maya", "Jonah", "Nora", "Rosa", "Leo")) and "savvy shopper" in team, f"list_companions names the team and what each does ({team[:160]!r})")
        check(cards(c) == [("ask", "maya", "jonah", "replied")] and next(m for m in c["Messages"] if m["Role"] == "ask").get("Reply") == "**No glare, warm light, fair price.**", f"The card ends Replied, with Jonah's reply ({cards(c)})")
        check(said(c) == ["Jonah's pitch: " + calls("Maya", "ask_companion")[0]["text"]] and "No glare, warm light, fair price." in said(c)[0], "Maya gets the reply back and uses it")
        check(z.get("Companion") == "jonah" and z["Messages"][0] == {"Role": "user", "Text": "Write a one-line pitch for a warm desk lamp.", "Who": "maya"} and said(z) == ["**No glare, warm light, fair price.**"],
              "Jonah answers in its own chat, where the message shows as Maya's")
        zp = next(p for p in prompts() if p["name"] == "Jonah" and "one-line pitch" in p["prompt"])
        check("[Still] Maya, your teammate, asks you this" in zp["prompt"] and "Find me a desk lamp" not in zp["prompt"] and "# Sales" in zp["prompt"],
              "Jonah is told Maya asks, in its own role, and sees only what Maya sent")
        check(any(f["Text"] == "Pitches lead with comfort" for f in facts("jonah")) and not any("comfort" in f["Text"] for f in facts("maya")), "What Jonah remembers stays in Jonah's memory")
        check(not any(p["name"] in ("Nora", "Rosa", "Leo") for p in prompts()), "Nobody else sees the exchange")
        own = calls("Maya", "ask_companion")[1]
        check(own["error"] and "can't message itself" in own["text"], f"A companion can't message itself ({own['text']!r})")
        tabs = calls("Jonah", "list_tabs")[0]["text"]
        check("Secret plans" not in tabs, "The one asked still never sees a private tab")
        check([c[1:] for c in shown_cards()] == [["replied", "Replied"]] and "Maya asked Jonah" in shown_cards()[0][0], f"On screen: Maya asked Jonah, Replied ({shown_cards()})")
        check("No glare, warm light, fair price." in (js(P, "document.querySelector('.exchange-reply').innerText") or ""), "The reply shows on the card")
        js(P, "document.querySelector('.exchange-head').click()")
        check(until(lambda: js(P, "!!document.querySelector('.exchange[data-open] .exchange-reply strong')"), 3), "It opens to the whole exchange")
        shot("ask-replied.png")
        js(P, "[...document.querySelectorAll('.exchange-actions button')].find(b => b.innerText.includes(\"Open Jonah's chat\")).click()")
        check(until(lambda: rpc(P).get("tabs") and next((t for t in rpc(P)["tabs"] if t["Id"] == rpc(P)["activeId"]), {}).get("ChatId") == z["Id"], 5), "Open Jonah's chat shows it from Jonah's side")
        check(until(lambda: "Maya asked" in (js(P, "document.querySelector('.ai-msg.is-teammate')?.innerText") or ""), 3), "where Maya's message says Maya asked")
        shot("asked-side.png")

        # Handing over: tell_companion doesn't wait; the card turns Done when Nora finishes. Maya uses Nora's old name.
        plan({"Maya": [{"text": "Nora is checking the reviews.", "calls": [{"name": "tell_companion", "arguments": {"name": "Noon", "message": "Check two reviews of the lamp."}}]}],
              "Nora": [{"text": "Both reviews hold up.", "sleep": 4}]})
        tell = new_chat("Have someone check the reviews.", companion="maya")
        check(settled(tell, 1, 15) and cards(chat(tell)) == [("tell", "maya", "nora", "working")], f"Maya hands it to Nora and finishes without waiting ({cards(chat(tell))})")
        check(until(lambda: cards(chat(tell)) == [("tell", "maya", "nora", "replied")], 15) and next(m for m in chat(tell)["Messages"] if m["Role"] == "tell").get("Reply") == "Both reviews hold up.", "The card turns Done with Nora's work")
        check(until(lambda: [c[2] for c in shown_cards()] == ["Done"], 5) and "Maya handed this to Nora" in shown_cards()[0][0], f"On screen: Maya handed this to Nora, Done ({shown_cards()})")

        # A chain: Maya asks Jonah, Jonah asks Nora (asking Maya back is a loop), Nora asks Rosa, and Rosa can't go a
        # 4th hop. The user's chat shows every exchange.
        plan({"Maya": [{"text": "Plan done. {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Jonah", "message": "Draft the pitch."}}]}],
              "Jonah": [{"text": "Pitch drafted. Loop: {0} Nora: {1}", "calls": [{"name": "ask_companion", "arguments": {"name": "Maya", "message": "What's the price?"}},
                                                                                  {"name": "ask_companion", "arguments": {"name": "Nora", "message": "Check the claims."}}]}],
              "Nora": [{"text": "Claims hold. Rosa: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Rosa", "message": "Is Tuesday free for the launch?"}}]}],
              "Rosa": [{"text": "Tuesday is free. Leo: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Leo", "message": "Post about it?"}}]}]})
        chain = new_chat("Plan the launch with the team.", companion="maya")
        check(settled(chain, 1, 60), "The chain finishes")
        loop = calls("Jonah", "ask_companion")[-2]
        check(loop["error"] and "loop" in loop["text"] and "Maya → Jonah" in loop["text"], f"Jonah asking Maya back is a loop, and stops there ({loop['text']!r})")
        deep = calls("Rosa", "ask_companion")[-1]
        check(deep["error"] and "3 hops deep" in deep["text"] and not any(p["name"] == "Leo" for p in prompts()), f"Rosa can't go a 4th hop: Leo is never asked ({deep['text']!r})")
        c = chat(chain)
        check(cards(c) == [("ask", "maya", "jonah", "replied"), ("ask", "jonah", "nora", "replied"), ("ask", "nora", "rosa", "replied")], f"The user's chat shows every exchange in the chain ({cards(c)})")
        check("Tuesday is free" in said(c)[0], "and Maya's answer carries what came back up the chain")
        shot("chain.png")

        # About 10 messages per request: the 11th ask is refused; the user's next message starts a fresh count.
        plan({"Maya": [{"text": "Asked eleven times: {10}", "calls": [{"name": "ask_companion", "arguments": {"name": "Jonah", "message": f"Question {i + 1}"}} for i in range(11)]},
                        {"text": "Asked again: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Jonah", "message": "One more"}}]}],
              "Jonah": [{"text": "Yes."}]})
        cap = new_chat("Ask Jonah a lot.", companion="maya")
        check(settled(cap, 1, 90), "Maya's eleven asks finish")
        asks = calls("Maya", "ask_companion")[-11:]
        check([a["error"] for a in asks] == [False] * 10 + [True] and "10 messages" in asks[-1]["text"], f"The first 10 go through, the 11th is refused ({asks[-1]['text']!r})")
        send(P, "aiSend", text="Once more, please.")
        check(settled(cap, 2, 20) and not calls("Maya", "ask_companion")[-1]["error"], "The next request starts a fresh count")

        # Stop on the card stops that exchange: Jonah stops, the card says Stopped, Maya is told and carries on.
        plan({"Maya": [{"text": "Carrying on without it: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Jonah", "message": "Research every lamp ever made."}}]}],
              "Jonah": [{"text": "Too late.", "sleep": 30}]})
        stop = new_chat("Get Jonah on a big job.", companion="maya")
        check(until(lambda: js(P, "!!document.querySelector('.exchange[data-status=working] .exchange-actions button:last-child')") and any("every lamp" in p["prompt"] for p in prompts()), 15),
              "While Jonah works, the card has Stop")
        time.sleep(.5)
        shot("stop.png")
        js(P, "document.querySelector('.exchange[data-status=working] .exchange-actions button:last-child').click()")
        check(until(lambda: cards(chat(stop)) == [("ask", "maya", "jonah", "stopped")] and not asked_by(stop, "jonah").get("Running"), 10), "Stop stops Jonah, and the card says Stopped")
        check(settled(stop, 1, 15) and "The user stopped Jonah's answer" in said(chat(stop))[0], "Maya is told the user stopped it, and carries on")
        check("Too late." not in json.dumps(asked_by(stop, "jonah")), "Jonah's answer never lands")

        # Stopping the chat stops whoever it asked too.
        plan({"Maya": [{"text": "Never said.", "calls": [{"name": "ask_companion", "arguments": {"name": "Rosa", "message": "Sort my whole inbox."}}]}],
              "Rosa": [{"text": "Too late.", "sleep": 30}]})
        whole = new_chat("Get Rosa on my inbox.", companion="maya")
        check(until(lambda: asked_by(whole, "rosa").get("Running"), 15), "Rosa works on Maya's ask")
        time.sleep(.5)
        send(P, "aiStop")
        check(until(lambda: not chat(whole).get("Running") and not asked_by(whole, "rosa").get("Running") and cards(chat(whole)) == [("ask", "maya", "rosa", "stopped")], 20),
              f"Stopping Maya stops Rosa, and the card says Stopped ({chat(whole).get('Running')}, {asked_by(whole, 'rosa').get('Running')}, {cards(chat(whole))}, {rpc(P)['activeId']})")

        # @Jonah in the message box: Nora is told to bring Jonah in, and asks.
        plan({"Nora": [{"text": "Hello."}, {"text": "Read it: the review likes the warm light."}, {"text": "I can only see the one you shared."},
                       {"text": "Jonah says: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Jonah", "message": "Is this a good pitch?"}}]}],
              "Jonah": [{"text": "Warm light sells. I'd lead with it."}]})
        send(P, "new", url=site + "/review")
        until(lambda: any(t.get("Title") == "Desk lamp review" for t in rpc(P)["tabs"]), 10)
        secret = next(t["Id"] for t in rpc(P)["tabs"] if t.get("Private"))
        talk = new_chat("Hi Nora.", companion="nora")
        settled(talk, 1)

        # Mentions: # lists the open tabs (never a private one) and puts one in the text; the AI is told to read it.
        type_in("Sum up #")
        got = picker()
        check(got and got[0] == "Tabs" and any("Desk lamp review" in o for o in got[1]) and not any("Secret" in o for o in got[1]), f"# lists the open tabs, never a private one ({got})")
        type_in("Sum up #lamp")
        got = picker()
        check(got and len(got[1]) == 1 and got[1][0].startswith("Desk lamp review"), f"Typing after # filters the tabs ({got})")
        key("Enter")
        check(chips() == ["Desk lamp review"] and box_text() == "Sum up Desk lamp review " and not picker(), "Enter puts the tab in the text where #lamp was")
        pill = json.loads(js(P, f"JSON.stringify((m => m && [m.className, !!m.querySelector('img, i'), m.contentEditable, getComputedStyle(m).borderTopWidth, !!m.querySelector('button')])(document.querySelector('.chat-view .composer-input .mention')))"))
        check(pill == ["mention is-tab", True, "false", "0px", False], f"Inline: an icon and the title, one piece, no box and no x ({pill})")
        check(not js(P, "!!document.querySelector('.chat-view .mention-chip')"), "No chip row above the box")
        press("Backspace")
        check(chips() == ["Desk lamp review"] and box_text() == "Sum up Desk lamp review", f"Backspace takes the space after it first ({box_text()!r})")
        press("Backspace")
        check(chips() == [] and box_text().strip() == "Sum up", f"Backspace right after it deletes the whole mention ({box_text()!r})")
        js(P, "document.execCommand('undo')"); time.sleep(.25)
        check(chips() == ["Desk lamp review"], "Undo brings it back whole")
        type_in("Sum up #lamp")
        key("Tab")
        check(chips() == ["Desk lamp review"], "Tab picks too")
        press("ArrowLeft")
        press("ArrowLeft")
        check(before_caret() == ["Sum up ", 0], f"The arrow keys step over it as one piece ({before_caret()})")
        press("ArrowRight")
        check(before_caret() == ["Sum up Desk lamp review", 1], f"...both ways ({before_caret()})")
        press("Delete")
        check(chips() == ["Desk lamp review"], "Delete takes the space after it, not the mention")
        js(P, "document.execCommand('undo')"); time.sleep(.25)
        clip = json.loads(js(P, f"""JSON.stringify((() => {{ const e = document.querySelector('{BOX}'), d = new DataTransfer(); e.focus(); getSelection().selectAllChildren(e)
            e.dispatchEvent(new ClipboardEvent('copy', {{ bubbles: true, cancelable: true, clipboardData: d }})); window.__clip = d; return [d.getData('text/plain'), d.types.length] }})())"""))
        check(clip == ["Sum up Desk lamp review ", 2], f"Copy gives the text, and the mention for Still ({clip})")
        type_in("")
        js(P, f"(e => {{ e.focus(); e.dispatchEvent(new ClipboardEvent('paste', {{ bubbles: true, cancelable: true, clipboardData: window.__clip }})) }})(document.querySelector('{BOX}'))"); time.sleep(.25)
        check(chips() == ["Desk lamp review"] and box_text().rstrip() == "Sum up Desk lamp review", f"Paste brings it back as a mention ({chips()}, {box_text()!r})")
        type_in("")
        js(P, f"(e => {{ const d = new DataTransfer(); d.setData('text/plain', 'Plain words'); e.focus(); e.dispatchEvent(new ClipboardEvent('paste', {{ bubbles: true, cancelable: true, clipboardData: d }})) }})(document.querySelector('{BOX}'))"); time.sleep(.25)
        check(chips() == [] and box_text() == "Plain words", "Text from elsewhere pastes as plain text")
        type_in("Sum up #lamp")
        key("Enter")
        type_in("please.", more=True)
        key("Enter")
        check(settled(talk, 2), "Nora answers")
        asked = [m["Text"] for m in chat(talk)["Messages"] if m["Role"] == "user"][-1]
        check(asked == f"Sum up Desk lamp review please.\n\n[Desk lamp review]({site}/review)", f"The message has the tab inline, and its link as before ({asked!r})")
        last = prompts()[-1]["prompt"]
        check(f'[Still] The user attached this tab: "Desk lamp review" {site}/review (tabId ' in last and "Read each with read_page" in last, "The AI is told which tab it is and to read it")
        check(chips() == [] and box_text().strip() == "", "Sending empties the box")
        sent = json.loads(js(P, "JSON.stringify((m => m && [m.innerText.replace(/\\u00a0/g, ' '), [...m.querySelectorAll('.mention')].map(x => [x.className, x.innerText])])([...document.querySelectorAll('.chat-view .ai-msg.is-user')].at(-1)))"))
        check(sent == ["Sum up Desk lamp review please.", [["mention is-tab", "Desk lamp review"]]], f"The sent message shows it inline too ({sent})")
        send(P, "aiSend", text="And this one?", tabs=[secret])
        check(settled(talk, 3), "Nora answers again")
        check("Secret plans" not in json.dumps(chat(talk)["Messages"]) and "Secret plans" not in prompts()[-1]["prompt"] and "/secret" not in prompts()[-1]["prompt"], "A private tab is never attached")

        # @ lists companions with their role; Esc closes it, arrows move, Enter picks.
        type_in("What do you think @")
        got = picker()
        check(got and got[0] == "Companions" and "Jonah · Sales" in got[1] and "Maya · Research" in got[1], f"@ lists companions with their role ({got})")
        key("Escape")
        check(not picker() and box_text() == "What do you think @", "Esc closes the picker and keeps the text")
        type_in("What do you think @ro")
        key("Enter")
        check(chips() == ["Rosa"] and box_text() == "What do you think Rosa ", "Enter puts the companion in the text")
        rosa = json.loads(js(P, "JSON.stringify((m => [m.className, m.querySelector('img')?.src.length > 0, getComputedStyle(m).color !== getComputedStyle(m.parentElement).color, getComputedStyle(m).backgroundColor])(document.querySelector('.chat-view .composer-input .mention')))"))
        check(rosa[:3] == ["mention is-mate", True, True] and rosa[3] in ("rgba(0, 0, 0, 0)", "transparent"), f"A companion: their face and their name in their color, no highlight ({rosa})")
        type_in("@ro", more=True)
        check(not picker() or not any(o.startswith("Rosa") for o in picker()[1]), f"A companion already in the text isn't offered again ({picker()})")
        type_in("What do you think @")
        names = [o.split(" · ")[0] for o in picker()[1]]
        key("ArrowDown")
        key("Enter")
        check(chips() == [names[1]], f"Arrows move through the list ({chips()})")
        type_in("@jonah")
        key("Enter")
        type_in("is this a good pitch?", more=True)
        key("Enter")
        check(settled(talk, 4), "Nora answers")
        c = chat(talk)
        check([m["Text"] for m in c["Messages"] if m["Role"] == "user"][-1] == "@Jonah is this a good pitch?", "The message names who it's for")
        nora = prompts()
        nora = next(p for p in reversed(nora) if p["name"] == "Nora")
        check("[Still] The user mentioned Jonah: bring them in with ask_companion" in nora["prompt"], "Nora is told to bring Jonah in")
        check(cards(c) == [("ask", "nora", "jonah", "replied")] and said(c)[-1] == "Jonah says: " + calls("Nora", "ask_companion")[-1]["text"], f"@Jonah: Nora asks Jonah and uses the reply ({cards(c)})")
        check(c["Companion"] == "nora" and not c.get("Team"), "The chat stays Nora's")
        jonah = json.loads(js(P, "JSON.stringify([...[...document.querySelectorAll('.chat-view .ai-msg.is-user')].at(-1).querySelectorAll('.mention')].map(x => [x.className, x.innerText]))"))
        check(jonah == [["mention is-mate", "Jonah"]], f"@Jonah shows inline in the sent message ({jonah})")
        shot("mention.png")

        errors = js(P, "JSON.stringify(window.__errors || [])")
        check(errors in (None, "[]"), f"No script errors ({errors})")
    finally:
        rpc(P, "quit")
        P.wait(timeout=20)
    print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'ALL PASSED'}  shots in {OUT}")
    sys.exit(1 if FAILED else 0)


EXE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else RUN / "shots"
P = None
if __name__ == "__main__":
    main()
