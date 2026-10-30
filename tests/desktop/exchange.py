"""Companions message each other: ask_companion waits for the teammate's reply, tell_companion hands work over, and
list_companions says who's on the team. The one asked answers in its own chat with its own memory, and the chat the user
is in shows each exchange as a card (who asked whom, the message, Working / Replied / Failed / Stopped, the reply) that
opens to all of it and to the other side's chat. Stop on a card stops that exchange; stopping a chat stops whoever it
asked. Exchanges go at most 3 hops deep and about 10 messages per request, a teammate already in one can't be asked again
(a loop), and none messages itself. @Name in the message box has the current companion ask that teammate. Team chats
from before are split into each companion's own chat, so nothing is lost. The # and @ pickers in the message box too.

No AI plan is used: a fake agent app plays every companion. It finds who it is in the prompt ("Your name is Glint.", or
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
    calls = ([{"name": "remember", "arguments": {"fact": line["remember"], "kind": "project"}}] if line.get("remember") else []) + line.get("calls", [])
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
    text = line["text"]
    for i, r in enumerate(results): text = text.replace("{%d}" % i, r)
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
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
    until(lambda: js(P, "!!document.querySelector('.home-compose textarea')"), 10)
    js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    send(P, "aiSend", text=text, home=True, **extra)
    return until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before and not c.get("From")), None), 10) or ""


def type_in(text):
    """Types into the message box without sending."""
    js(P, f"""(() => {{ const e = document.querySelector('.chat-view textarea, .home-compose textarea'); e.focus();
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(e, {json.dumps(text)}); e.setSelectionRange(e.value.length, e.value.length); e.dispatchEvent(new Event('input', {{ bubbles: true }})) }})()""")
    time.sleep(.25)


def key(name, caret=None):
    js(P, f"""(() => {{ const e = document.querySelector('.chat-view textarea, .home-compose textarea'); e.focus(); {f'e.setSelectionRange({caret}, {caret});' if caret is not None else ''}
        e.dispatchEvent(new KeyboardEvent('keydown', {{ key: {json.dumps(name)}, bubbles: true, cancelable: true }})) }})()""")
    time.sleep(.25)


def picker():
    """The open picker: its label and each option's text."""
    return json.loads(js(P, "JSON.stringify((m => m ? [m.getAttribute('aria-label'), [...m.querySelectorAll('[role=option]')].map(o => o.querySelector(':scope > b').innerText + ' · ' + o.querySelector(':scope > span:last-child').innerText)] : null)(document.querySelector('.chat-view .skill-menu, .home-compose .skill-menu')))") or "null")


def chips():
    return json.loads(js(P, "JSON.stringify([...document.querySelectorAll('.chat-view .mention-chip, .home-compose .mention-chip')].map(c => c.innerText.trim()))") or "[]")


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


# A team chat from before: Glint and Zest in one thread, a handoff between them, each on its own AI session.
OLD_TEAM = {"Id": "oldteam", "Title": "Launch the desk lamp", "Harness": "fake", "Started": True, "Companion": "zest", "Session": "Zest-1",
            "Team": ["glint", "zest"], "Sessions": {"glint": "Glint-1", "zest": "Zest-1"}, "Updated": "2026-10-01T10:00:00Z", "Messages": [
                {"Role": "user", "Text": "Help me launch our new desk lamp."},
                {"Role": "assistant", "Text": "People ask about glare, warmth and price.", "Who": "glint"},
                {"Role": "handoff", "Text": "Write a two-line launch pitch.", "Who": "glint", "To": "zest", "Status": "done"},
                {"Role": "assistant", "Text": "No glare. Warm light. Fair price.", "Who": "zest"}]}


def setup(theme="Light"):
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    crew = [{**c, "Crew": {"glint": "researcher", "zest": "closer", "noon": "chief", "mallow": "organizer"}.get(c["Id"], "")} for c in CREW]
    crew.append({"Id": "fizz", "Name": "Fizz", "Job": "A marketer: writes posts and plans campaigns.", "Crew": "marketer"})
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
        until(lambda: js(P, "!!document.querySelector('.home-compose textarea')"), 10)
        js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        time.sleep(.5)
        check(not js(P, "!!document.querySelector('.mate-switch-team')") and "Team chat" not in (js(P, "document.body.innerText") or ""), "There's no Team chat button any more")
        shot("home.png")

        # The old team chat: Glint keeps the original (and its session), Zest gets the whole thread as its own chat.
        old, mine = chat("oldteam"), next((c for c in chats() if c["Id"] != "oldteam" and c["Title"] == "Launch the desk lamp"), {})
        check(old.get("Companion") == "glint" and old.get("Session") == "Glint-1" and not old.get("Team") and not old.get("Sessions"), f"Glint keeps the old team chat, on its own session ({old.get('Companion')}, {old.get('Session')})")
        check(mine.get("Companion") == "zest" and mine.get("Session") == "Zest-1" and [m["Text"] for m in mine["Messages"]] == [m["Text"] for m in old["Messages"]],
              "Zest gets the whole thread as a chat of its own, on its own session")
        check(cards(old) == [("tell", "glint", "zest", "replied")] and old["Messages"][2].get("Chat") == mine.get("Id"), f"The handoff becomes a card that opens Zest's chat ({cards(old)})")
        check([m.get("Who") for m in old["Messages"] if m["Role"] == "assistant"] == [None, "zest"] and [m.get("Who") for m in mine["Messages"] if m["Role"] == "assistant"] == ["glint", None],
              "In each, the other companion's lines keep their face")
        plan({"Zest": [{"text": "Still here: the pitch was No glare. Warm light. Fair price."}]})
        send(P, "chatOpen", id=mine["Id"])
        until(lambda: js(P, "!!document.querySelector('.chat-view textarea')"), 10)
        shot("migrated.png")
        send(P, "aiSend", text="What was the pitch again?")
        check(settled(mine["Id"], 3), "Zest answers in its migrated chat")
        last = prompts()[-1]
        check(last["name"] == "Zest" and "--resume" in last["args"] and last["args"][last["args"].index("--resume") + 1] == "Zest-1", "picking up its own session from the team chat")

        # Ask and reply: Glint lists the team, asks Zest and uses the answer. Zest answers in its own chat and remembers
        # in its own memory; asking itself is refused.
        site = pages()
        send(P, "new", url=site + "/secret", private=True)
        plan({"Glint": [{"text": "Zest's pitch: {1}", "calls": [{"name": "list_companions", "arguments": {}}, {"name": "ask_companion", "arguments": {"name": "Zest", "message": "Write a one-line pitch for a warm desk lamp."}},
                                                                {"name": "ask_companion", "arguments": {"name": "Glint", "message": "Hi me."}}]}],
              "Zest": [{"text": "**No glare, warm light, fair price.**", "remember": "Pitches lead with comfort", "sleep": 1.5, "calls": [{"name": "list_tabs", "arguments": {}}]}]})
        ask = new_chat("Find me a desk lamp, and get a pitch for it.", companion="glint")
        check(until(lambda: cards(chat(ask)) == [("ask", "glint", "zest", "working")], 15), "Glint's ask shows in the chat as a card, Working")
        check(until(lambda: [c[1:] for c in shown_cards()] == [["working", "Working"]], 5), "The card says Working on screen")
        shot("ask-working.png")
        check(settled(ask, 1), "Glint finishes")
        c, z = chat(ask), asked_by(ask, "zest")
        team = calls("Glint", "list_companions")[0]["text"]
        check(all(n in team for n in ("Glint", "Zest", "Noon", "Mallow", "Fizz")) and "savvy shopper" in team, f"list_companions names the team and what each does ({team[:160]!r})")
        check(cards(c) == [("ask", "glint", "zest", "replied")] and next(m for m in c["Messages"] if m["Role"] == "ask").get("Reply") == "**No glare, warm light, fair price.**", f"The card ends Replied, with Zest's reply ({cards(c)})")
        check(said(c) == ["Zest's pitch: " + calls("Glint", "ask_companion")[0]["text"]] and "No glare, warm light, fair price." in said(c)[0], "Glint gets the reply back and uses it")
        check(z.get("Companion") == "zest" and z["Messages"][0] == {"Role": "user", "Text": "Write a one-line pitch for a warm desk lamp.", "Who": "glint"} and said(z) == ["**No glare, warm light, fair price.**"],
              "Zest answers in its own chat, where the message shows as Glint's")
        zp = next(p for p in prompts() if p["name"] == "Zest" and "one-line pitch" in p["prompt"])
        check("[Still] Glint, your teammate, asks you this" in zp["prompt"] and "Find me a desk lamp" not in zp["prompt"] and "# Your role: Deal closer" in zp["prompt"],
              "Zest is told Glint asks, in its own role, and sees only what Glint sent")
        check(any(f["Text"] == "Pitches lead with comfort" for f in facts("zest")) and not any("comfort" in f["Text"] for f in facts("glint")), "What Zest remembers stays in Zest's memory")
        check(not any(p["name"] in ("Noon", "Mallow", "Fizz") for p in prompts()), "Nobody else sees the exchange")
        own = calls("Glint", "ask_companion")[1]
        check(own["error"] and "can't message itself" in own["text"], f"A companion can't message itself ({own['text']!r})")
        tabs = calls("Zest", "list_tabs")[0]["text"]
        check("Secret plans" not in tabs, "The one asked still never sees a private tab")
        check([c[1:] for c in shown_cards()] == [["replied", "Replied"]] and "Glint asked Zest" in shown_cards()[0][0], f"On screen: Glint asked Zest, Replied ({shown_cards()})")
        check("No glare, warm light, fair price." in (js(P, "document.querySelector('.exchange-reply').innerText") or ""), "The reply shows on the card")
        js(P, "document.querySelector('.exchange-head').click()")
        check(until(lambda: js(P, "!!document.querySelector('.exchange[data-open] .exchange-reply strong')"), 3), "It opens to the whole exchange")
        shot("ask-replied.png")
        js(P, "[...document.querySelectorAll('.exchange-actions button')].find(b => b.innerText.includes(\"Open Zest's chat\")).click()")
        check(until(lambda: rpc(P).get("tabs") and next((t for t in rpc(P)["tabs"] if t["Id"] == rpc(P)["activeId"]), {}).get("ChatId") == z["Id"], 5), "Open Zest's chat shows it from Zest's side")
        check(until(lambda: "Glint asked" in (js(P, "document.querySelector('.ai-msg.is-teammate')?.innerText") or ""), 3), "where Glint's message says Glint asked")
        shot("asked-side.png")

        # Handing over: tell_companion doesn't wait; the card turns Done when Noon finishes.
        plan({"Glint": [{"text": "Noon is checking the reviews.", "calls": [{"name": "tell_companion", "arguments": {"name": "Noon", "message": "Check two reviews of the lamp."}}]}],
              "Noon": [{"text": "Both reviews hold up.", "sleep": 4}]})
        tell = new_chat("Have someone check the reviews.", companion="glint")
        check(settled(tell, 1, 15) and cards(chat(tell)) == [("tell", "glint", "noon", "working")], f"Glint hands it to Noon and finishes without waiting ({cards(chat(tell))})")
        check(until(lambda: cards(chat(tell)) == [("tell", "glint", "noon", "replied")], 15) and next(m for m in chat(tell)["Messages"] if m["Role"] == "tell").get("Reply") == "Both reviews hold up.", "The card turns Done with Noon's work")
        check(until(lambda: [c[2] for c in shown_cards()] == ["Done"], 5) and "Glint handed this to Noon" in shown_cards()[0][0], f"On screen: Glint handed this to Noon, Done ({shown_cards()})")

        # A chain: Glint asks Zest, Zest asks Noon (asking Glint back is a loop), Noon asks Mallow, and Mallow can't go a
        # 4th hop. The user's chat shows every exchange.
        plan({"Glint": [{"text": "Plan done. {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Zest", "message": "Draft the pitch."}}]}],
              "Zest": [{"text": "Pitch drafted. Loop: {0} Noon: {1}", "calls": [{"name": "ask_companion", "arguments": {"name": "Glint", "message": "What's the price?"}},
                                                                                  {"name": "ask_companion", "arguments": {"name": "Noon", "message": "Check the claims."}}]}],
              "Noon": [{"text": "Claims hold. Mallow: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Mallow", "message": "Is Tuesday free for the launch?"}}]}],
              "Mallow": [{"text": "Tuesday is free. Fizz: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Fizz", "message": "Post about it?"}}]}]})
        chain = new_chat("Plan the launch with the team.", companion="glint")
        check(settled(chain, 1, 60), "The chain finishes")
        loop = calls("Zest", "ask_companion")[-2]
        check(loop["error"] and "loop" in loop["text"] and "Glint → Zest" in loop["text"], f"Zest asking Glint back is a loop, and stops there ({loop['text']!r})")
        deep = calls("Mallow", "ask_companion")[-1]
        check(deep["error"] and "3 hops deep" in deep["text"] and not any(p["name"] == "Fizz" for p in prompts()), f"Mallow can't go a 4th hop: Fizz is never asked ({deep['text']!r})")
        c = chat(chain)
        check(cards(c) == [("ask", "glint", "zest", "replied"), ("ask", "zest", "noon", "replied"), ("ask", "noon", "mallow", "replied")], f"The user's chat shows every exchange in the chain ({cards(c)})")
        check("Tuesday is free" in said(c)[0], "and Glint's answer carries what came back up the chain")
        shot("chain.png")

        # About 10 messages per request: the 11th ask is refused; the user's next message starts a fresh count.
        plan({"Glint": [{"text": "Asked eleven times: {10}", "calls": [{"name": "ask_companion", "arguments": {"name": "Zest", "message": f"Question {i + 1}"}} for i in range(11)]},
                        {"text": "Asked again: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Zest", "message": "One more"}}]}],
              "Zest": [{"text": "Yes."}]})
        cap = new_chat("Ask Zest a lot.", companion="glint")
        check(settled(cap, 1, 90), "Glint's eleven asks finish")
        asks = calls("Glint", "ask_companion")[-11:]
        check([a["error"] for a in asks] == [False] * 10 + [True] and "10 messages" in asks[-1]["text"], f"The first 10 go through, the 11th is refused ({asks[-1]['text']!r})")
        send(P, "aiSend", text="Once more, please.")
        check(settled(cap, 2, 20) and not calls("Glint", "ask_companion")[-1]["error"], "The next request starts a fresh count")

        # Stop on the card stops that exchange: Zest stops, the card says Stopped, Glint is told and carries on.
        plan({"Glint": [{"text": "Carrying on without it: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Zest", "message": "Research every lamp ever made."}}]}],
              "Zest": [{"text": "Too late.", "sleep": 30}]})
        stop = new_chat("Get Zest on a big job.", companion="glint")
        check(until(lambda: js(P, "!!document.querySelector('.exchange[data-status=working] .exchange-actions button:last-child')") and any("every lamp" in p["prompt"] for p in prompts()), 15),
              "While Zest works, the card has Stop")
        time.sleep(.5)
        shot("stop.png")
        js(P, "document.querySelector('.exchange[data-status=working] .exchange-actions button:last-child').click()")
        check(until(lambda: cards(chat(stop)) == [("ask", "glint", "zest", "stopped")] and not asked_by(stop, "zest").get("Running"), 10), "Stop stops Zest, and the card says Stopped")
        check(settled(stop, 1, 15) and "The user stopped Zest's answer" in said(chat(stop))[0], "Glint is told the user stopped it, and carries on")
        check("Too late." not in json.dumps(asked_by(stop, "zest")), "Zest's answer never lands")

        # Stopping the chat stops whoever it asked too.
        plan({"Glint": [{"text": "Never said.", "calls": [{"name": "ask_companion", "arguments": {"name": "Mallow", "message": "Sort my whole inbox."}}]}],
              "Mallow": [{"text": "Too late.", "sleep": 30}]})
        whole = new_chat("Get Mallow on my inbox.", companion="glint")
        check(until(lambda: asked_by(whole, "mallow").get("Running"), 15), "Mallow works on Glint's ask")
        time.sleep(.5)
        send(P, "aiStop")
        check(until(lambda: not chat(whole).get("Running") and not asked_by(whole, "mallow").get("Running") and cards(chat(whole)) == [("ask", "glint", "mallow", "stopped")], 20),
              f"Stopping Glint stops Mallow, and the card says Stopped ({chat(whole).get('Running')}, {asked_by(whole, 'mallow').get('Running')}, {cards(chat(whole))}, {rpc(P)['activeId']})")

        # @Zest in the message box: Noon is told to bring Zest in, and asks.
        plan({"Noon": [{"text": "Hello."}, {"text": "Read it: the review likes the warm light."}, {"text": "I can only see the one you shared."},
                       {"text": "Zest says: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Zest", "message": "Is this a good pitch?"}}]}],
              "Zest": [{"text": "Warm light sells. I'd lead with it."}]})
        send(P, "new", url=site + "/review")
        until(lambda: any(t.get("Title") == "Desk lamp review" for t in rpc(P)["tabs"]), 10)
        secret = next(t["Id"] for t in rpc(P)["tabs"] if t.get("Private"))
        talk = new_chat("Hi Noon.", companion="noon")
        settled(talk, 1)

        # Mentions: # lists the open tabs (never a private one) and attaches one as a chip; the AI is told to read it.
        type_in("Sum up #")
        got = picker()
        check(got and got[0] == "Tabs" and any("Desk lamp review" in o for o in got[1]) and not any("Secret" in o for o in got[1]), f"# lists the open tabs, never a private one ({got})")
        type_in("Sum up #lamp")
        got = picker()
        check(got and len(got[1]) == 1 and got[1][0].startswith("Desk lamp review"), f"Typing after # filters the tabs ({got})")
        key("Enter")
        check(chips() == ["Desk lamp review"] and js(P, "document.querySelector('.chat-view textarea').value") == "Sum up " and not picker(), "Enter attaches it as a chip and takes #lamp out of the text")
        key("Backspace", 0)
        check(chips() == [], "Backspace at the start of the box removes the last chip")
        type_in("Sum up #lamp")
        key("Tab")
        check(chips() == ["Desk lamp review"], "Tab picks too")
        type_in("Sum up this review.")
        key("Enter")
        check(settled(talk, 2), "Noon answers")
        asked = [m["Text"] for m in chat(talk)["Messages"] if m["Role"] == "user"][-1]
        check(asked == f"Sum up this review.\n\n[Desk lamp review]({site}/review)", f"The message shows the tab as a link ({asked!r})")
        last = prompts()[-1]["prompt"]
        check(f'[Still] The user attached this tab: "Desk lamp review" {site}/review (tabId ' in last and "Read each with read_page" in last, "The AI is told which tab it is and to read it")
        check(chips() == [], "Sending clears the chips")
        send(P, "aiSend", text="And this one?", tabs=[secret])
        check(settled(talk, 3), "Noon answers again")
        check("Secret plans" not in json.dumps(chat(talk)["Messages"]) and "Secret plans" not in prompts()[-1]["prompt"] and "/secret" not in prompts()[-1]["prompt"], "A private tab is never attached")

        # @ lists companions with their role; Esc closes it, arrows move, Enter picks; x removes a chip.
        type_in("What do you think @")
        got = picker()
        check(got and got[0] == "Companions" and "Zest · Deal closer" in got[1] and "Glint · Researcher" in got[1], f"@ lists companions with their role ({got})")
        key("Escape")
        check(not picker() and js(P, "document.querySelector('.chat-view textarea').value") == "What do you think @", "Esc closes the picker and keeps the text")
        type_in("What do you think @ma")
        key("Enter")
        check(chips() == ["@Mallow"], "Enter picks the companion as a chip")
        js(P, "document.querySelector('.chat-view .mention-chip button[aria-label=\"Remove Mallow\"]').click()")
        time.sleep(.2)
        check(chips() == [], "x removes it")
        type_in("What do you think @")
        names = [o.split(" · ")[0] for o in picker()[1]]
        key("ArrowDown")
        key("Enter")
        check(chips() == ["@" + names[1]], f"Arrows move through the list ({chips()})")
        key("Backspace", 0)
        type_in("What do you think @zest")
        key("Enter")
        type_in("is this a good pitch?")
        key("Enter")
        check(settled(talk, 4), "Noon answers")
        c = chat(talk)
        check([m["Text"] for m in c["Messages"] if m["Role"] == "user"][-1] == "@Zest is this a good pitch?", "The message names who it's for")
        noon = prompts()
        noon = next(p for p in reversed(noon) if p["name"] == "Noon")
        check("[Still] The user mentioned Zest: bring them in with ask_companion" in noon["prompt"], "Noon is told to bring Zest in")
        check(cards(c) == [("ask", "noon", "zest", "replied")] and said(c)[-1] == "Zest says: " + calls("Noon", "ask_companion")[-1]["text"], f"@Zest: Noon asks Zest and uses the reply ({cards(c)})")
        check(c["Companion"] == "noon" and not c.get("Team"), "The chat stays Noon's")
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
