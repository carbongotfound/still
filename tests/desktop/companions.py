"""Phase 2: the chat home, companions, modes, skills, memory and Chat History. No AI plan is used: a fake agent app
(a manifest in Still's agents folder) logs the prompt Still hands it.

Run: python tests/desktop/companions.py artifacts/Still-QA/Still.exe [--shots]
Screenshots (--shots): docs/agentic/compare/ (newtab-v03, modes-v01, companions-v01, companion-profile-v01, skills-v01, chats-v01, skill-chip-v01)
"""
import json
from pathlib import Path
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, companions_page, js, launch, launcher, rpc, send, shots, text, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("companions-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


FAKE = textwrap.dedent(r'''
    import json, os, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a") as log: log.write(json.dumps({"args": args, "prompt": prompt}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if "WAIT" in prompt: time.sleep(4)
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done, fake reply."}]}})
    say({"type": "result", "subtype": "success", "is_error": False})
''')


def click(process, selector):
    return js(process, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.click(); return !!e }})()")


def click_text(process, selector, words):
    return js(process, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => e.innerText.trim().includes({json.dumps(words)})); e?.click(); return !!e }})()")


def type_into(process, selector, value):
    """Types like a user would: React sees an input event with the new value."""
    return js(process, f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false
     if (e.isContentEditable) {{ e.focus(); getSelection().selectAllChildren(e); document.execCommand({json.dumps(value)} ? 'insertText' : 'delete', false, {json.dumps(value)}); return true }}
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {json.dumps(value)})
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); e.focus(); return true }})()""")


def key(process, selector, name):
    js(process, f"document.querySelector({json.dumps(selector)})?.dispatchEvent(new KeyboardEvent('keydown', {{ key: {json.dumps(name)}, bubbles: true }}))")


def state():
    for _ in range(50):  # Still swaps the file in atomically, so a read can land mid-swap
        try:
            return json.loads((PROFILE / "state.json").read_text())
        except (OSError, ValueError):
            time.sleep(.05)
    return {}


def mates():
    return {c["Name"]: c for c in state().get("Preferences", {}).get("Companions", [])}


def open_menu(process, selector):
    """Radix menus open on pointerdown, not click."""
    js(process, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }})) }})()")


def home(process):
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 20)
    time.sleep(.4)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")  # a new tab opens with the address bar's suggestions


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE)
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run"], "model": ["--model", "{model}"], "effort": ["--effort", "{effort}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake"},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    try:
        home(process)
        shown = text(process)
        check(js(process, "document.querySelectorAll('.home-rail-item').length") == 5 and js(process, "!!document.querySelector('.mate-switch')")
              and js(process, "document.querySelector('.home-face')?.getBoundingClientRect().width >= 160") and "Try one of these" not in shown
              and all(w in shown for w in ("Skills", "Companions", "Library", "Help")), "The new tab is the chat home: rail, switcher, a big companion and chips; no ideas with nothing to go on (ideas.py)")
        check(js(process, "document.querySelector('.home-compose [aria-label=Message]')?.getAttribute('aria-placeholder')") == "Ask Maya anything, or hand over a task…", "The message box asks the active companion")

        # Create a companion: Hire a companion opens the library, then Make your own.
        click(process, ".mate-switch-more[aria-label='Hire a companion']")
        until(lambda: js(process, "!!document.querySelector('.companion-library')"), 5)
        click_text(process, ".library-more .role-head", "Make your own")
        until(lambda: js(process, "!!document.querySelector('.companion-dialog')"), 5)
        type_into(process, ".companion-dialog input[required]", "Ines")
        type_into(process, ".companion-dialog textarea", "A careful researcher who cites sources.")
        click_text(process, ".companion-look button", "Customize")  # the look editor: Periwinkle
        until(lambda: js(process, "!!document.querySelector('.look-dialog .look-colors')"), 8)
        click(process, ".look-colors [aria-label=Periwinkle]")
        click(process, ".look-save")
        until(lambda: not js(process, "!!document.querySelector('.look-dialog')"), 3)
        click_text(process, ".companion-modes button", "Thorough")
        click(process, ".companion-save")
        ines = until(lambda: mates().get("Ines"), 10)
        check(until(lambda: js(process, "document.querySelector('.joined-card [data-slot=dialog-title]')?.innerText") == "Ines joined your team", 5), "Ines joined: the card says so")
        click_text(process, ".joined-card button", "Not now")
        until(lambda: not js(process, "!!document.querySelector('.joined-card')"), 3)
        check(ines and '"color":"#a7b5f0"' in ines["Look"].replace(" ", "") and ines["Mode"] == "expert" and "research" in ines["Job"], "Create a companion: name, job, look and mode are saved")
        check(until(lambda: js(process, "!!document.querySelector('.mate-switch-face[aria-label=Ines]')"), 5), "The new companion is in the switcher")

        # Switching companions changes the accent right away.
        hue = lambda: js(process, "getComputedStyle(document.querySelector('.home-compose .ai-send')).backgroundColor")
        type_into(process, ".home-compose [aria-label=Message]", "hello")  # an empty box greys out the send button
        before = hue()
        click(process, f".mate-switch-face[aria-label=Ines]")
        check(until(lambda: hue() == "rgb(167, 181, 240)", 5) and before != "rgb(167, 181, 240)", f"Switching to Ines turns the send button periwinkle ({hue()})")
        check(js(process, "document.querySelector('.home-compose [aria-label=Message]')?.getAttribute('aria-placeholder')") == "Ask Ines anything, or hand over a task…", "The message box now asks Ines")
        type_into(process, ".home-compose [aria-label=Message]", "")

        # The mode menu: companions, the three modes, Advanced.
        open_menu(process, ".home-compose .mode-chip")
        menu = until(lambda: js(process, "document.querySelector('.mode-menu')?.innerText ?? ''"), 5) or ""
        check(all(w in menu for w in ("Maya", "Ines", "Quick", "Everyday", "Thorough", "usual setup", "Advanced")), "The mode menu lists companions, the modes with a line on each, and Advanced")
        if "--shots" in sys.argv:
            rpc(process, "capture", name="modes.png")
        click_text(process, ".mode-menu [role=menuitem]", "Quick")
        check(until(lambda: mates().get("Ines", {}).get("Mode") == "efficient", 5), "Picking Quick saves Ines's mode")
        check(until(lambda: "Quick" in js(process, "document.querySelector('.home-compose .mode-chip')?.innerText ?? ''"), 5), "The chip shows the mode")

        # Edit: how it talks, in its profile (saved as you type).
        click(process, ".mate-switch-on")
        until(lambda: js(process, "!!document.querySelector('.profile-panel')"), 5)
        type_into(process, ".profile-panel textarea[placeholder^='For example: upbeat']", "Calm and precise, always with sources.")
        check(until(lambda: mates().get("Ines", {}).get("Tone") == "Calm and precise, always with sources.", 5), "Edit: how Ines talks is saved")
        key(process, "body", "Escape")
        until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 3)

        # The Companions page: a card per companion, then the crew to pick from; memory opens Settings > Memory.
        companions_page(process)
        check(js(process, "document.querySelectorAll('.mate-card').length") == 5 and "Say hi" in text(process), "The Companions page shows a card per companion")
        check(js(process, "document.querySelectorAll('.crew-card').length") == 7 and "Hire for a role" in text(process), "Below them, the six roles to hire and Make your own")
        js(process, "[...document.querySelectorAll('.mate-card')].find(c => c.innerText.includes('Ines'))?.querySelector('.mate-memory')?.click()")
        check(until(lambda: js(process, "!!document.querySelector('.memory-settings')") and js(process, "document.querySelector('.memory-who [aria-checked=true]')?.innerText.trim()") == "Ines", 5), "What they remember opens Settings > Memory on Ines")
        for fact in ("I prefer peer-reviewed sources.", "I live in Lisbon and pay in euros."):
            type_into(process, ".memory-add input", fact)
            click(process, ".memory-add button[type=submit]")
            time.sleep(.4)
        wren_id = mates().get("Ines", {}).get("Id", "")
        file = PROFILE / "companions" / wren_id / "memory.json"
        check(until(lambda: file.exists() and "Lisbon" in file.read_text(encoding="utf-8") and "peer-reviewed" in file.read_text(encoding="utf-8"), 5), "Facts added on the Memory page are saved to Ines's memory.json")
        check(until(lambda: js(process, "document.querySelectorAll('.memory-row').length") == 2, 5), "and listed there")
        click_text(process, ".memory-who button", "Maya")
        type_into(process, ".memory-add input", "My sister Maya lives in Porto.")
        click(process, ".memory-add button[type=submit]")
        check(until(lambda: (PROFILE / "companions" / "maya" / "memory.json").exists(), 5) and "Lisbon" not in (PROFILE / "companions" / "maya" / "memory.json").read_text(encoding="utf-8"), "Each companion keeps its own memory")
        js(process, "document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")  # closes Settings
        until(lambda: not js(process, "!!document.querySelector('.memory-settings')"), 5)

        # A skill: make it, then use it with / in the message box.
        click(process, ".home-rail-item[aria-label='Skills & plugins']")
        until(lambda: js(process, "!!document.querySelector(\".home-page[aria-label='Skills & plugins']\")"), 5)
        click_text(process, ".plug-all", "New skill")
        until(lambda: js(process, "!!document.querySelector('.skill-dialog')"), 5)
        type_into(process, ".skill-dialog input[required]", "Trip plan")
        type_into(process, ".skill-dialog input[placeholder^='Lays out']", "Lays out a trip day by day")
        type_into(process, ".skill-dialog textarea", "SKILL-BODY: plan each day as morning, afternoon, evening.")
        click_text(process, ".skill-dialog button[type=submit]", "Save")
        skill = PROFILE / "skills" / "trip-plan.md"
        check(until(lambda: skill.exists(), 5) and "name: Trip plan" in skill.read_text() and "SKILL-BODY" in skill.read_text(), "A skill is saved as a Markdown file with front matter")
        click(process, ".home-rail-item[aria-label='New chat']")
        until(lambda: js(process, "!!document.querySelector('.home-compose [aria-label=Message]')"), 5)
        type_into(process, ".home-compose [aria-label=Message]", "/tri")
        check(until(lambda: "/trip-plan" in js(process, "document.querySelector('.skill-menu')?.innerText ?? ''"), 5), "Typing / lists matching skills")
        key(process, ".home-compose [aria-label=Message]", "Enter")
        check(until(lambda: "Trip plan" in js(process, "document.querySelector('.home-compose .mention.is-skill')?.innerText ?? ''"), 5), "Enter puts the skill in the text")
        if "--shots" in sys.argv:
            type_into(process, ".home-compose [aria-label=Message]", "/trip-plan Three days in Lisbon in May")
            rpc(process, "capture", name="skill-chip.png")
        type_into(process, ".home-compose [aria-label=Message]", "/trip-plan Three days in Lisbon in May")
        key(process, ".home-compose [aria-label=Message]", "Enter")
        prompts = BIN / "prompts.jsonl"
        sent = until(lambda: prompts.exists() and json.loads(prompts.read_text().splitlines()[-1])["prompt"], 30) or ""
        check("SKILL-BODY" in sent and '[Skill "Trip plan"' in sent, "The skill's steps go into the AI's prompt")
        check("What you remember about the user" in sent and "Lisbon and pay in euros" in sent and "peer-reviewed" in sent and "Maya" not in sent, "Ines's memory goes into the first prompt, and not Maya's")
        check("Calm and precise, always with sources." in sent, "So does how Ines talks")
        check("Your name is Ines" in sent and "cites sources" in sent, "Ines's name and job go into the prompt")
        args = json.loads(prompts.read_text().splitlines()[-1])["args"]
        check("--effort" in args and args[args.index("--effort") + 1] == "low" and "--model" not in args, "Quick mode runs another AI app with --effort low and its own model")
        reply = until(lambda: "Done, fake reply." in text(process) and text(process), 20) or ""
        check("Loaded skill Trip plan" in reply, "The chat shows a Loaded skill row")
        check(js(process, "!!document.querySelector('.ai-msg.is-user .mention.is-skill')"), "The user's message shows the skill inline")

        # Chat History: unread, archive, search, the companion filter.
        until(lambda: not js(process, "!!document.querySelector('[aria-label=Stop]')"), 10)
        home(process)
        send(process, "aiSend", text="WAIT then answer", home=True)
        until(lambda: len(prompts.read_text().splitlines()) >= 2, 15)
        home(process)  # look away while it works
        time.sleep(5.5)
        click(process, ".home-rail-item[aria-label=Chats]")
        until(lambda: js(process, "!!document.querySelector('.home-page[aria-label=\"Chat History\"]')"), 5)
        check(until(lambda: js(process, "!!document.querySelector('.history-row .is-unread')"), 10), "A reply that lands while you're away shows the blue unread dot")
        rows = lambda: js(process, "[...document.querySelectorAll('.history-row')].map(r => r.innerText)")
        check(any("Three days in Lisbon" in r for r in rows()) and js(process, "document.querySelectorAll('.history-group h2')[0]?.innerText") == "Today", "Chat History groups chats by day")
        type_into(process, ".history-find input", "lisbon")
        check(until(lambda: len(rows()) == 1, 5), "Search filters chats")
        type_into(process, ".history-find input", "")
        click_text(process, ".history-chip", "Unread")
        check(until(lambda: len(rows()) == 1 and "WAIT" in rows()[0], 5), "The Unread filter keeps only unread chats")
        click_text(process, ".history-chip", "Unread")
        until(lambda: any("Lisbon" in r for r in rows()), 5)  # the filter is off once the other chat is back
        js(process, "[...document.querySelectorAll('.history-row')].find(r => r.innerText.includes('Lisbon')).querySelector('[aria-label^=Archive]').click()")
        check(until(lambda: len(rows()) == 1, 5), "Archive hides a chat")
        click_text(process, ".history-chip", "Archived")
        check(until(lambda: len(rows()) == 1 and "Lisbon" in rows()[0], 5), "The Archived filter shows it")
        if "--shots" in sys.argv:
            click_text(process, ".history-chip", "Archived")
            time.sleep(.4)
            rpc(process, "capture", name="chats.png")

        # Fire a companion: each card on the Companions page has a Fire button, and it asks first.
        companions_page(process)
        asking = lambda: js(process, "document.querySelector('[data-slot=alert-dialog-content]')?.innerText ?? ''")
        check(click(process, ".mate-fire[aria-label='Fire Ines']") and until(lambda: "Fire Ines?" in asking(), 3), "A companion's card has a Fire button that asks first")
        click_text(process, "[data-slot=alert-dialog-content] button", "Keep Ines")
        check(until(lambda: not asking(), 3) and "Ines" in mates(), "Keep Ines keeps her")
        # The profile's More menu asks the same way.
        click(process, ".mate-portrait[aria-label='Edit Ines']")
        until(lambda: js(process, "!!document.querySelector('.profile-panel')"), 5)
        open_menu(process, ".profile-head [aria-label=More]")
        until(lambda: js(process, "!!document.querySelector('[role=menuitem]')"), 3)
        click_text(process, "[role=menuitem]", "Fire Ines")
        check(until(lambda: "Fire Ines?" in asking(), 3), "and so does Fire in her profile's More menu")
        click_text(process, "[data-slot=alert-dialog-content] button", "Keep Ines")
        until(lambda: not asking(), 3)
        key(process, "body", "Escape")
        until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 3)
        click(process, ".mate-fire[aria-label='Fire Ines']")
        until(lambda: asking(), 3)
        click(process, "[data-slot=alert-dialog-action]")
        check(until(lambda: "Ines" not in mates(), 5) and until(lambda: js(process, "document.querySelectorAll('.mate-card').length") == 4, 5), "Fire removes the companion and its card")
        check(until(lambda: not file.exists(), 5), "and its memory file")
        check("Codex" not in text(process), "No Codex on screen")
    finally:
        try:
            rpc(process, "quit")
            process.wait(timeout=15)
        except Exception:
            process.kill()

    # Memory persists across a restart.
    process = launch(EXE, PROFILE)
    try:
        home(process)
        companions_page(process)
        js(process, "[...document.querySelectorAll('.mate-card')].find(c => c.innerText.includes('Maya'))?.querySelector('.mate-memory')?.click()")
        check(until(lambda: "Maya lives in Porto" in (js(process, "document.querySelector('.memory-settings')?.innerText") or ""), 10), "Maya's memory is still there after a restart")
        check(len(state()["Preferences"]["Companions"]) == 4, "The crew is saved")
    finally:
        rpc(process, "quit")
        process.wait(timeout=15)


def screens():
    def newtab(p):
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        home(p)
        time.sleep(.5)
    def hue(p):
        newtab(p)
        send(p, "companionSave", name="Ines", face="", color="berry", job="A careful researcher: reads several sources and cites them.", mode="expert")
        until(lambda: js(p, "!!document.querySelector('.mate-switch-face[aria-label=Ines]')"), 5)
    def modes(p):
        newtab(p)
        type_into(p, ".home-compose [aria-label=Message]", "Help me plan a three-day trip to Lisbon in May")
        open_menu(p, ".home-compose .mode-chip")
        until(lambda: js(p, "!!document.querySelector('.mode-menu')"), 5)
    def companions(p):
        hue(p)
        companions_page(p)
    def editor(p):
        companions(p)
        time.sleep(.3)
        click(p, ".mate-portrait[aria-label='Edit Ines']")
    def skills(p):
        newtab(p)
        send(p, "skillSave", name="Trip plan", description="Lays out a trip day by day, with costs", when="Planning any trip", body="1. Ask where I'm starting from.")
        send(p, "skillSave", name="Price check", description="Compares three stores and shows a table", when="Shopping", body="1. Find three stores.")
        click(p, ".home-rail-item[aria-label='Skills & plugins']")
    shots(EXE, "newtab", "v03", newtab)
    shots(EXE, "modes", "v01", modes)
    shots(EXE, "companions", "v01", companions)
    shots(EXE, "companion-profile", "v01", editor)
    shots(EXE, "skills", "v01", skills)


if __name__ == "__main__":
    try:
        main()
    finally:
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
    if "--shots" in sys.argv:
        out = ROOT / "docs" / "agentic" / "compare"
        import shutil
        for name, to in (("modes.png", "modes-v01-live.png"), ("skill-chip.png", "skill-chip-v01.png"), ("chats.png", "chats-v01.png")):
            if (PROFILE / name).exists():
                shutil.copy(PROFILE / name, out / to)
        screens()
