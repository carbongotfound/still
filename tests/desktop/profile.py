"""A companion's profile panel: opened from its mascots, every tab, the ⋯ menu, Share and paste, and a routine that
runs once at its time. A fake agent app answers (no AI plan is used).

Run: python tests/desktop/profile.py artifacts/Still-QA/Still.exe [OUTDIR]  (a screenshot per tab goes to OUTDIR)
"""
import datetime
import json
from pathlib import Path
import shutil
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, companions_page, js, launch, launcher, rpc, send, text, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("profile-" + uuid.uuid4().hex[:8])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else RUN / "shots"
PROFILE, BIN = RUN / "profile", RUN / "bin"
FAILED = []
FAKE = textwrap.dedent(r'''
    import json, os, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a") as log: log.write(json.dumps({"prompt": prompt}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done, fake reply."}]}})
    say({"type": "result", "subtype": "success", "is_error": False})
''')


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def mates():
    for _ in range(50):  # Still swaps the file in atomically, so a read can land mid-swap
        try:
            return {c["Name"]: c for c in json.loads((PROFILE / "state.json").read_text())["Preferences"]["Companions"]}
        except (OSError, ValueError, KeyError):
            time.sleep(.05)
    return {}


def click(p, selector, words=""):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => e.innerText.includes({json.dumps(words)})); e?.click(); return !!e }})()")


def press(p, selector, event="pointerdown"):
    """Radix menus open on pointerdown and tabs switch on mousedown, not click."""
    return js(p, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.dispatchEvent(new (window[{json.dumps('PointerEvent' if event == 'pointerdown' else 'MouseEvent')}])({json.dumps(event)}, {{ bubbles: true, button: 0, pointerType: 'mouse' }})); return !!e }})()")


def type_into(p, selector, value, blur=False):
    return js(p, f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false
     Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set.call(e, {json.dumps(value)})
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); {"e.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))" if blur else ""}; return true }})()""")


def shown(p, selector):
    return js(p, f"!!document.querySelector({json.dumps(selector)})")


def escape(p):
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")


def menu(p, words):
    press(p, ".profile-head [aria-label=More]")
    until(lambda: shown(p, "[role=menuitem]"), 3)
    return click(p, "[role=menuitem]", words)


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (BIN / "fake_agent.py").write_text(FAKE)
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run"], "output": "stream-json"}))
    crew = [{**c, "Crew": "sales"} for c in CREW if c["Id"] == "jonah"] + [c for c in CREW if c["Id"] != "jonah"]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake", "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        send(p, "new")
        until(lambda: shown(p, ".home-face"), 20)
        time.sleep(.4)
        escape(p)  # a new tab opens with the address bar's suggestions
        send(p, "skillSave", name="Price check", description="Compares three stores and shows a table", when="Shopping", body="1. Find three stores.")

        # The home mascot opens Jonah's profile, on General.
        js(p, "document.querySelector('.home-face')?.click()")
        check(until(lambda: shown(p, ".profile-panel[aria-label=\"Jonah's profile\"] .profile-stage canvas, .profile-panel .profile-stage img"), 10), "Clicking the home mascot opens its profile, with a live mascot on the stage")
        check(js(p, "document.querySelector('.profile-tablist')?.innerText.replace(/\\s+/g, ' ').trim()") == "General Skills & plugins Routines Files Memory Model", "Six tabs: General, Skills & plugins, Routines, Files, Memory, Model (no Plugins tab)")
        time.sleep(1)

        # A screenshot per tab, and what each one holds.
        for tab, ready in (("general", ".profile-stage"), ("skills", ".profile-list [role=switch]"), ("routines", ".profile-routine"), ("files", ".companion-folder"),
                           ("memory", ".memory-settings"), ("model", ".profile-modes")):
            press(p, f".profile-tablist [role=tab][id$='-trigger-{tab}']", "mousedown")
            check(until(lambda: shown(p, f".profile-panel [role=tabpanel][data-state=active] {ready}"), 5), f"The {tab.title()} tab shows its content")
            time.sleep(.5)
            got = rpc(p, "capture", name=f"profile-{tab}.png")
            if "error" in got:  # the first capture after the 3D view starts can be slow
                got = rpc(p, "capture", name=f"profile-{tab}.png")
            if (PROFILE / f"profile-{tab}.png").exists():
                shutil.copy(PROFILE / f"profile-{tab}.png", OUT / f"profile-{tab}.png")
            else:
                print("capture:", got)

        # Model: Thorough is saved. Skills: Jonah came with the Sales kit's skills, and a switch turns one off.
        click(p, ".profile-modes button", "Thorough")
        check(until(lambda: mates().get("Jonah", {}).get("Mode") == "expert", 5), "Model: picking Thorough saves it")
        press(p, ".profile-tablist [role=tab][id$='-trigger-skills']", "mousedown")
        until(lambda: shown(p, ".profile-list [role=switch]"), 3)
        kit = mates().get("Jonah", {}).get("Skills") or []
        check(sorted(kit) == ["call-brief", "follow-up", "lead-list", "pipeline-check"], f"Skills: Jonah, hired before roles had kits, gets the Sales kit's four when Still starts ({kit})")
        js(p, "document.querySelector('.profile-list [role=switch][aria-checked=true]')?.click()")
        check(until(lambda: len(mates().get("Jonah", {}).get("Skills", [])) == 3, 5), "and turning one off saves it for Jonah")

        # General: rename on blur; instructions autosave.
        press(p, ".profile-tablist [role=tab][id$='-trigger-general']", "mousedown")
        until(lambda: shown(p, ".profile-field input"), 3)
        check("inside Still" in (js(p, "document.querySelectorAll('.profile-field textarea')[0]?.placeholder") or ""), "The Instructions box's hint says 'inside Still'")
        type_into(p, ".profile-field input", "Zesty", blur=True)
        check(until(lambda: "Zesty" in mates(), 5), "Rename saves when you leave the field")
        type_into(p, ".profile-field textarea", "Finds the best price before I buy anything.")
        check(until(lambda: mates().get("Zesty", {}).get("Job") == "Finds the best price before I buy anything.", 5), "Instructions save as you type")

        # An official companion's full instructions: Still's version, editable, and a reset back to it.
        rows = js(p, "[...document.querySelectorAll('.profile-rows button')].map(b => b.innerText.replace(/\\s+/g, ' ').trim())") or []
        z = mates().get("Zesty", {})
        check(rows == [f"Skills {len(z.get('Skills') or [])}", f"Routines {len(z.get('Routines') or [])}"], f"Skills and Routines rows with their counts, above the instructions ({rows})")
        box = ".profile-field.is-instructions textarea"
        brief = js(p, f"document.querySelector('{box}')?.value") or ""
        check(brief.startswith("# Sales") and "## How you judge the work" in brief and "offer_routine" in brief, "Instructions show Still's whole setup for the role")
        type_into(p, box, brief + "\n\nALWAYS END WITH A HAIKU.")
        check(until(lambda: mates().get("Zesty", {}).get("Instructions", "").endswith("ALWAYS END WITH A HAIKU."), 5), "An edit saves as you type")
        check(until(lambda: click(p, ".profile-instructions-foot button", "Reset to Still's version"), 3) and until(lambda: mates().get("Zesty", {}).get("Instructions") == "", 5)
              and js(p, f"document.querySelector('{box}')?.value") == brief, "Reset to Still's version brings it back")
        type_into(p, box, brief + "\n\nALWAYS END WITH A HAIKU.")
        until(lambda: mates().get("Zesty", {}).get("Instructions", "").endswith("HAIKU."), 5)
        js(p, "document.querySelector('.profile-rows')?.scrollIntoView({ block: 'start' })")
        time.sleep(.3)
        rpc(p, "capture", name="profile-instructions.png")

        # Routines: one due now runs once, in a new chat, through the companion.
        press(p, ".profile-tablist [role=tab][id$='-trigger-routines']", "mousedown")
        until(lambda: shown(p, ".profile-routine textarea"), 3)
        now = datetime.datetime.now()
        today = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][(now.weekday() + 1) % 7]
        if js(p, f"document.querySelector('.profile-days [aria-label={today}]')?.getAttribute('aria-pressed')") != "true":
            js(p, f"document.querySelector('.profile-days [aria-label={today}]')?.click()")
        type_into(p, ".profile-routine textarea", "ROUTINE check the price of the blue kettle")
        type_into(p, ".profile-routine input[type=time]", now.strftime("%H:%M"))
        click(p, ".profile-routine button[type=submit]")
        saved = until(lambda: mates().get("Zesty", {}).get("Routines"), 5) or []
        check(len(saved) == 1 and saved[0]["Time"] == now.strftime("%H:%M") and saved[0]["On"], "A routine is saved with its time and days")
        log = BIN / "prompts.jsonl"
        ran = until(lambda: log.exists() and "ROUTINE check the price" in log.read_text(), 45, .5)
        check(ran, "At its time, the routine runs through the fake agent")
        check(ran and "ALWAYS END WITH A HAIKU." in log.read_text() and "## How you judge the work" in log.read_text(), "and it follows the edited instructions")
        last = until(lambda: (mates().get("Zesty", {}).get("Routines") or [{}])[0].get("Last"), 5)
        check(last == now.strftime("%Y-%m-%d"), "and it's marked as run today, so it runs once")
        time.sleep(32)
        check(log.read_text().count("ROUTINE check the price") == 1, "It doesn't run again on the next tick")
        check(shown(p, ".profile-panel"), "The profile stays open while a routine starts")

        # Share copies the companion without memory, folder or plugins; pasting it on the Companions page adds them.
        js(p, "navigator.clipboard.writeText = t => { window.__shared = t; return Promise.resolve() }")
        press(p, ".profile-tablist [role=tab][id$='-trigger-general']", "mousedown")
        until(lambda: shown(p, ".profile-stage-actions"), 3)
        click(p, ".profile-stage-actions button", "Share")
        shared = json.loads(until(lambda: js(p, "window.__shared ?? ''"), 3) or "{}")
        check(shared.get("name") == "Zesty" and "memory" not in shared and "folder" not in shared and "routines" not in shared and "skills" not in shared, f"Share copies no memory, folder, skills or routines ({sorted(shared)})")

        # ⋯ menu: duplicate, then delete the copy.
        menu(p, "Duplicate")
        check(until(lambda: "Zesty 2" in mates(), 5) and until(lambda: js(p, "document.querySelector('.profile-switch b')?.innerText") == "Zesty 2", 3), "Duplicate makes a copy and shows it")
        check(not mates().get("Zesty 2", {}).get("Routines"), "The copy starts without routines")
        menu(p, "Fire Zesty 2")
        until(lambda: shown(p, "[role=alertdialog]"), 3)
        js(p, "document.querySelector('[data-slot=alert-dialog-action]')?.click()")
        check(until(lambda: not shown(p, ".profile-panel"), 3) and until(lambda: "Zesty 2" not in mates(), 15), "Fire asks first, closes the panel and removes the copy once Undo is gone")

        # Esc closes; paste the shared companion on the Companions page.
        js(p, "document.querySelector('.home-face')?.click()")
        until(lambda: shown(p, ".profile-panel"), 5)
        menu(p, "Reset")
        until(lambda: shown(p, "[role=alertdialog]"), 3)
        js(p, "document.querySelector('[data-slot=alert-dialog-action]')?.click()")
        check(until(lambda: "Jonah" in mates() and mates()["Jonah"].get("Routines"), 5), "Reset brings back Jonah's name and keeps the routines")
        check(mates()["Jonah"].get("Instructions") == "", "and Still's instructions")
        escape(p)
        check(until(lambda: not shown(p, ".profile-panel"), 2), "Esc closes the profile")
        companions_page(p)
        js(p, f"(() => {{ const d = new DataTransfer(); d.setData('text/plain', {json.dumps(json.dumps({**shared, 'name': 'Pasty'}))}); document.body.dispatchEvent(new ClipboardEvent('paste', {{ clipboardData: d, bubbles: true }})) }})()")
        check(until(lambda: "Pasty" in mates(), 5) and mates()["Pasty"]["Job"] == "Finds the best price before I buy anything.", "Pasting a shared companion on the Companions page adds them")
        js(p, "document.querySelector(\".mate-portrait[aria-label='Edit Pasty']\")?.click()")
        check(until(lambda: shown(p, ".profile-panel[aria-label=\"Pasty's profile\"]"), 5), "The Companions page portrait opens the profile")
        escape(p)
        until(lambda: not shown(p, ".profile-panel"), 2)

        # A chat turn's avatar opens the profile too.
        send(p, "aiSend", text="Hello there", home=True)
        until(lambda: shown(p, ".ai-turn-face"), 20)
        js(p, "document.querySelector('.ai-turn-face')?.click()")
        check(until(lambda: shown(p, ".profile-panel"), 5), "A chat turn's avatar opens the profile")
        escape(p)
        shown_text = text(p)
        check("Codex" not in shown_text, "No Codex on screen")
        errors = js(p, "JSON.stringify(window.__errors || [])")
        check(errors in ("[]", None), f"No script errors ({errors})")
    finally:
        try:
            rpc(p, "quit")
            p.wait(timeout=15)
        except Exception:
            p.kill()
    print(f"{'FAILED: ' + ', '.join(FAILED) if FAILED else 'All passed'}; screenshots in {OUT}")
    sys.exit(1 if FAILED else 0)


main()
