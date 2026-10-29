"""Team chat: several companions in one thread. Handoffs become cards (waiting, on it, done, stopped), @Name asks a
teammate, the user can jump in or stop the team at any point, the team pauses after 8 turns on its own, notes one
companion keeps in the chat reach the rest, and each companion keeps its own memory and its own AI session.

No AI plan is used: a fake agent app plays every companion. It finds who it is in the prompt ("You're Glint, ...") and
says that companion's next line from plan.json ({name: [{text, sleep, remember}]}). Every run goes to prompts.jsonl.

Run: python tests/desktop/team.py artifacts/Still-QA/Still.exe [OUTDIR]  (OUTDIR: a screenshot of the finished thread)
"""
import json
from pathlib import Path
import shutil
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

RUN = ROOT / "artifacts" / ("team-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []

FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    found = re.search(r"\[Team chat\] You're (\w+),", prompt) or re.search(r"Your name is (\w+)\.", prompt)
    name = found.group(1) if found else "nobody"
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"name": name, "args": args, "prompt": prompt}) + "\n")
    lines = json.load(open(os.path.join(here, "plan.json"), encoding="utf-8")).get(name) or [{"text": "Okay."}]
    count = os.path.join(here, "n-" + name)
    n = int(open(count).read()) if os.path.exists(count) else 0
    open(count, "w").write(str(n + 1))
    line = lines[min(n, len(lines) - 1)]
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": args[args.index("--resume") + 1] if "--resume" in args else "%s-%d" % (name, time.time_ns())})
    if line.get("remember"):
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
        request(2, "tools/call", {"name": "remember", "arguments": {"fact": line["remember"], "kind": "project"}})
        still.stdin.close()
    time.sleep(line.get("sleep", 0))
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": line["text"]}]}})
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


def prompts():
    file = BIN / "prompts.jsonl"
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def chats():
    for _ in range(50):
        try:
            return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.05)
    return []


def chat(id):
    return next((c for c in chats() if c["Id"] == id), {})


def facts(who):
    try:
        return json.loads((PROFILE / "companions" / who / "memory.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def said(c):
    return [m.get("Who") for m in c.get("Messages", []) if m["Role"] == "assistant"]


def handoffs(c):
    return [(m.get("Who"), m.get("To"), m.get("Status")) for m in c.get("Messages", []) if m["Role"] == "handoff"]


def settled(id, turns, wait=30):
    """Waits for the chat to stop running after at least turns replies."""
    return until(lambda: (c := chat(id)) and not c.get("Running") and len(said(c)) >= turns and not js(P, "!!document.querySelector('.team-bar-face[data-on]')"), wait)


def new_chat(text, **extra):
    """A new chat from a new tab; returns its id once it exists."""
    before = {c["Id"] for c in chats()}
    send(P, "new")
    until(lambda: js(P, "!!document.querySelector('.home-compose textarea')"), 10)
    js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    send(P, "aiSend", text=text, home=True, **extra)
    found = until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before), None), 10)
    return found or ""


def type_and_send(text):
    js(P, f"""(() => {{ const e = document.querySelector('.chat-view textarea, .home-compose textarea'); e.focus();
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(e, {json.dumps(text)}); e.dispatchEvent(new Event('input', {{ bubbles: true }})) }})()""")
    time.sleep(.2)
    js(P, "document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")


def setup(theme="Light"):
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    crew = [{**c, "Crew": {"glint": "researcher", "zest": "closer", "noon": "chief", "mallow": "organizer"}.get(c["Id"], "")} for c in CREW]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake", "Theme": theme,
        "Width": 1280, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, PROFILE)


HANDOFF = {
    "Glint": [{"text": "People ask three things about desk lamps: glare, warmth and price.\n\nHANDOFF @Zest: Write a two-line launch pitch around glare, warmth and price.", "remember": "The lamp launches in March", "sleep": 1.2},
              {"text": "Same three, in that order."}],
    "Zest": [{"text": "**No glare. Warm light. Fair price.** A desk lamp that's easy on your eyes, all evening.\n\n**HANDOFF @Noon:** Check the pitch's claims against two reviews.", "sleep": 1.2}],
    "Noon": [{"text": "Both claims hold up: two reviews call out the low glare and the warm 2700K light.", "sleep": 1.2},
             {"text": "The price is in line with similar lamps."}],
}


def main():
    global P
    OUT.mkdir(parents=True, exist_ok=True)
    P = setup()
    try:
        until(lambda: js(P, "!!document.body.innerText.length"), 20)
        send(P, "new")
        until(lambda: js(P, "!!document.querySelector('.home-compose textarea')"), 10)
        js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")

        # Start one from the new tab: Team chat, pick three, and the first message starts it with all three.
        plan(HANDOFF)
        check(js(P, "!!document.querySelector('.mate-switch-team')"), "The new tab has a Team chat button")
        js(P, "document.querySelector('.mate-switch-team').click()")
        check(until(lambda: js(P, "document.querySelectorAll('.team-dialog .team-pick-card').length") == 4, 5), "It opens a picker of every companion")
        for name in ("Glint", "Zest"):
            js(P, f"[...document.querySelectorAll('.team-pick-card')].find(e => e.innerText.includes('{name}')).click()")
        check(js(P, "!document.querySelector('.team-start').disabled"), "Two companions are enough to start")
        js(P, "[...document.querySelectorAll('.team-pick-card')].find(e => e.innerText.includes('Noon')).click()")
        check(js(P, "document.querySelector('.team-start').innerText") == "Start with Glint, Zest and Noon", "Start names who's in it")
        js(P, "document.querySelector('.team-start').click()")
        check(until(lambda: js(P, "document.querySelectorAll('.home-team-face').length") == 3 and not js(P, "!!document.querySelector('.team-dialog[data-state=open]')"), 5),
              "The new tab shows the three of them")
        before = {c["Id"] for c in chats()}
        type_and_send("Help me launch our new desk lamp.")
        id = until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before), None), 10) or ""
        check(chat(id).get("Team") == ["glint", "zest", "noon"], f"The first message starts a team chat with them, in the order picked ({chat(id).get('Team')})")
        check(settled(id, 3), "The team works through it on its own")
        c = chat(id)
        check(said(c) == ["glint", "zest", "noon"], f"Glint starts, hands to Zest, who hands to Noon ({said(c)})")
        check(handoffs(c) == [("glint", "zest", "done"), ("zest", "noon", "done")], f"Each handoff is a card that ends Done ({handoffs(c)})")
        check(not any("HANDOFF" in m["Text"] for m in c["Messages"]), "The HANDOFF lines become the cards, not text")
        cards = [m["Text"] for m in c["Messages"] if m["Role"] == "handoff"]
        check(cards == ["Write a two-line launch pitch around glare, warmth and price.", "Check the pitch's claims against two reviews."], f"A card holds what was handed over ({cards})")
        runs = {p["name"]: p for p in prompts()}
        check("[Team chat] You're Glint" in runs["Glint"]["prompt"] and "Zest (" in runs["Glint"]["prompt"] and "Noon (" in runs["Glint"]["prompt"], "Each companion is told who's on the team")
        check("Glint handed this to you: Write a two-line launch pitch" in runs["Zest"]["prompt"] and "Glint: People ask three things" in runs["Zest"]["prompt"],
              "The one taking a handoff gets the task and what was said")
        check("What the team noted in this chat:" in runs["Noon"]["prompt"] and "The lamp launches in March" in runs["Noon"]["prompt"], "What Glint remembered in the chat reaches the team")
        check(any(f["Text"] == "The lamp launches in March" for f in facts("glint")) and not any("March" in f["Text"] for f in facts("zest") + facts("noon")),
              "but it stays in Glint's own memory")
        check(all(any(f["Kind"] == "chat" and f["Chat"] == id for f in facts(w)) for w in ("glint", "zest", "noon")), "Everyone who spoke remembers the chat")
        check(len(set(c["Sessions"].values())) == 3 and set(c["Sessions"]) == {"glint", "zest", "noon"}, "Each companion has its own AI session")
        # On screen: each turn starts with its speaker's face, the cards show, the team sits over the message box.
        faces = json.loads(js(P, "JSON.stringify([...document.querySelectorAll('.chat-view .ai-turn-face')].map(e => e.getAttribute('aria-label')))") or "[]")
        check(faces == ["Glint's profile", "Zest's profile", "Noon's profile"], f"Each turn starts with its speaker's face ({faces})")
        check(js(P, "[...document.querySelectorAll('.team-handoff')].map(e => e.dataset.status + ':' + e.querySelector('.team-handoff-status').innerText).join()") == "done:Done,done:Done",
              "The handoff cards show in the thread")
        check((js(P, "document.querySelector('.team-handoff p')?.textContent") or "").startswith("Glint handed this to Zest"), "A card says who handed what to whom")
        check(js(P, "document.querySelectorAll('.team-bar .team-bar-face').length") == 3 and js(P, "document.querySelector('.team-bar-line')?.innerText") == "Your turn",
              "The team sits over the message box, and it's the user's turn")
        time.sleep(1)
        shot = rpc(P, "capture", name="team.png")
        if (PROFILE / "team.png").exists():
            shutil.copy(PROFILE / "team.png", OUT / "team.png")
        else:
            print("capture:", shot)

        # Talking to one of them: @Noon answers, in its own session, told what's new since it last spoke.
        type_and_send("@Noon could you check the price too?")
        check(settled(id, 4), "@Noon gets the next turn")
        c, last = chat(id), prompts()[-1]
        check(said(c)[-1] == "noon" and last["name"] == "Noon" and "--resume" in last["args"] and last["args"][last["args"].index("--resume") + 1] == c["Sessions"]["noon"],
              "Noon picks up its own session")
        check("Since you last spoke:" in last["prompt"] and "User: @Noon could you check the price too?" in last["prompt"] and "People ask three things" not in last["prompt"],
              "and hears only what's new since it last spoke")

        # @ in a chat with one companion brings another in: it becomes a team chat, and Glint keeps its session.
        plan({"Glint": [{"text": "Tuesday looks good for the launch."}, {"text": "Yes please, hold it."}],
              "Mallow": [{"text": "Tuesday is free. @Glint, want me to hold the morning?"}]})
        solo = new_chat("Find us a launch day.", companion="glint")
        settled(solo, 1)
        session = chat(solo).get("Session")
        check(not chat(solo).get("Team"), "A chat starts with one companion")
        type_and_send("@Mallow is Tuesday free?")
        check(settled(solo, 3), "@Mallow joins and answers")
        c = chat(solo)
        check(c.get("Team") == ["glint", "mallow"] and any(m["Role"] == "note" and m["Text"] == "Mallow joined the chat." for m in c["Messages"]), "It becomes a team chat: Mallow joined the chat")
        check(said(c) == ["glint", "mallow", "glint"], f"Mallow's @Glint question goes back to Glint ({said(c)})")
        check(c["Sessions"].get("glint") == session and "--resume" in prompts()[-1]["args"], "Glint keeps the session it had before")
        mallow = next(p for p in prompts() if p["name"] == "Mallow")
        check("The chat so far:" in mallow["prompt"] and "Glint: Tuesday looks good for the launch." in mallow["prompt"], "Mallow is new here, so it hears the chat so far")

        # Jumping in: what the user sends shows at once, and whoever they name goes next; the waiting handoff runs after.
        plan({"Glint": [{"text": "Here's the research.\n\nHANDOFF @Noon: Double-check the research.", "sleep": 4}],
              "Zest": [{"text": "Pitch: bright where you work, never in your eyes."}], "Noon": [{"text": "Checked: it holds up."}]})
        jump = new_chat("Research desk lamps.", team=["glint", "zest", "noon"])
        until(lambda: prompts() and prompts()[-1]["name"] == "Glint" and chat(jump).get("Running"), 10)
        send(P, "aiSend", text="@Zest write the pitch now, please")
        check(until(lambda: js(P, "[...document.querySelectorAll('.chat-view .ai-msg.is-user')].at(-1)?.innerText") == "@Zest write the pitch now, please", 3) and not said(chat(jump)),
              "What the user sends mid-turn shows in the thread right away")
        check(settled(jump, 3), "The team carries on")
        c = chat(jump)
        check(said(c) == ["glint", "zest", "noon"] and handoffs(c) == [("glint", "noon", "done")], f"Zest, whom the user named, goes first; the handoff to Noon runs after ({said(c)}, {handoffs(c)})")

        # Stop: the one working stops, open handoffs say Stopped, and nobody else starts.
        plan({"Glint": [{"text": "HANDOFF @Zest: Write it up."}], "Zest": [{"text": "Too late.", "sleep": 30}]})
        stop = new_chat("Write up the lamp.", team=["glint", "zest"])
        check(until(lambda: handoffs(chat(stop)) == [("glint", "zest", "working")], 10) and until(lambda: js(P, "document.querySelector('.team-bar-line')?.innerText") == "Zest is on it", 5),
              "A handoff is On it while Zest works, and the team bar says so")
        check(js(P, "[...document.querySelectorAll('.team-bar-face')].map(e => !!e.dataset.on).join()") == "false,true", "Zest's face is the one speaking")
        time.sleep(.5)
        send(P, "aiStop")
        check(until(lambda: not chat(stop).get("Running") and handoffs(chat(stop)) == [("glint", "zest", "stopped")], 10), "Stop stops it, and the handoff says Stopped")
        time.sleep(1.5)
        check(said(chat(stop)) == [] and chat(stop)["Messages"][-1]["Text"] == "Stopped.", "Nobody else starts")

        # Left alone, a team pauses after 8 turns.
        plan({"Glint": [{"text": "HANDOFF @Zest: Your go."}], "Zest": [{"text": "HANDOFF @Glint: Back to you."}]})
        ran = len(prompts())
        loop = new_chat("Keep passing it.", team=["glint", "zest"])
        check(until(lambda: not chat(loop).get("Running") and chat(loop)["Messages"][-1]["Text"] == "The team paused after 8 turns. Reply to keep them going.", 40), "The team pauses after 8 turns")
        check(len(prompts()) - ran == 8, f"after taking 8 turns ({len(prompts()) - ran})")

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
