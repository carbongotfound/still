"""Every menu, picker and tooltip in the chat panel stays inside the window and the panel, 8 px in from their edges.
Each one is opened with the panel 320, 400, 480 and 600 px wide, in a maximized window and in a snapped-half one, in
light and dark. The mode menu also has to open upward from its chip, line up with the message box's right edge and
keep each mode's line inline (no side card). A fake agent app stands in for the AI, so no plan is used.

Run: python tests/desktop/popovers.py artifacts/Still-QA/Still.exe [--shots DIR]
--shots DIR saves the 400 px panel with the mode menu open, light and dark, as popovers-<os>-<theme>.png in DIR.
"""
import json
from pathlib import Path
import shutil
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
SHOTS = Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
RUN = ROOT / "artifacts" / ("popovers-" + uuid.uuid4().hex[:8])
PAD = 8
TALLY = {}  # "<layout> <theme>": [passed, failed]
GROUP = ["", ""]

FAKE = textwrap.dedent(r'''
    import json, sys, time
    if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if "WAIT" in prompt: time.sleep(30)
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done, fake reply."}]}})
    say({"type": "result", "subtype": "success", "is_error": False})
''')

# The box of the newest open popover matching a selector, with the panel's and window's, once its opening animation
# is over (the zoom-in would otherwise measure it 95% of its size).
MEASURE = """(sel => { const e = [...document.querySelectorAll(sel)].filter(e => e.dataset.state !== 'closed').pop(); if (!e) return null
 if (e.getAnimations({ subtree: true }).some(a => a.playState === 'running')) return null
 const r = e.getBoundingClientRect(), p = document.querySelector('.ai-sidebar').getBoundingClientRect()
 return { l: r.left, t: r.top, r: r.right, b: r.bottom, pl: p.left, pt: p.top, pr: p.right, pb: p.bottom, w: innerWidth, h: innerHeight } })"""


def check(ok, name):
    key = " ".join(GROUP)
    TALLY.setdefault(key, [0, 0])[0 if ok else 1] += 1
    print(("PASS " if ok else "FAIL ") + f"[{key}] {name}", flush=True)


def q(selector):
    return json.dumps(selector)


def press(process, selector, event="pointerdown"):
    """Radix menus and selects open on pointerdown, not click."""
    return js(process, f"""(() => {{ const e = document.querySelector({q(selector)}); if (!e) return false
     e.dispatchEvent(new PointerEvent({q(event)}, {{ bubbles: true, cancelable: true, button: 0, pointerType: 'mouse' }})); return true }})()""")


def escape(process):
    js(process, "document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    until(lambda: not js(process, "!!document.querySelector('[data-slot=dropdown-menu-content], [data-slot=select-content], [data-slot=tooltip-content]')"), 3)
    time.sleep(.15)  # a menu hands focus back to its button as it goes, which would close the next tooltip


def type_into(process, selector, value):
    return js(process, f"""(() => {{ const e = document.querySelector({q(selector)}); if (!e) return false
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {q(value)})
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); e.focus(); return true }})()""")


def submit(process, words):
    type_into(process, ".ai-sidebar .composer textarea", words)
    js(process, "document.querySelector('.ai-sidebar .composer textarea').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")


def inside(process, name, selector):
    """The popover's whole box sits 8 px inside both the window and the chat panel."""
    box = until(lambda: js(process, f"{MEASURE}({q(selector)})"), 4)
    if not box:
        check(False, f"{name}: opens")
        return None
    left, top = max(box["pl"], 0) + PAD, max(box["pt"], 0) + PAD
    right, bottom = min(box["pr"], box["w"]) - PAD, min(box["pb"], box["h"]) - PAD
    ok = box["l"] >= left - .5 and box["t"] >= top - .5 and box["r"] <= right + .5 and box["b"] <= bottom + .5
    check(ok, f"{name}: inside the window and panel ({box['l']:.0f},{box['t']:.0f})-({box['r']:.0f},{box['b']:.0f}) in ({left:.0f},{top:.0f})-({right:.0f},{bottom:.0f})")
    return box


def menu(process, name, trigger, content="[data-slot=dropdown-menu-content]"):
    escape(process)
    if not press(process, trigger):
        check(False, f"{name}: its button is there")
        return None
    return inside(process, name, content)


def tip(process, name, trigger):
    """Tooltips open on hover or focus; a native title= one never shows up in the page, so it fails here."""
    escape(process)
    if not js(process, f"""(() => {{ const e = document.querySelector({q(trigger)}); if (!e) return false; e.focus()
     e.dispatchEvent(new PointerEvent('pointermove', {{ bubbles: true, pointerType: 'mouse' }})); return true }})()"""):
        check(False, f"{name} tooltip: its button is there")
        return
    inside(process, f"{name} tooltip", "[data-slot=tooltip-content]")
    js(process, f"document.activeElement?.blur(); document.querySelector({q(trigger)})?.dispatchEvent(new PointerEvent('pointerout', {{ bubbles: true, pointerType: 'mouse', relatedTarget: document.body }}))")


def mode_menu(process, fresh, shot=None):
    box = menu(process, "Mode menu" + (" with companions" if fresh else ""), ".ai-sidebar .mode-chip", ".mode-menu")
    if box:
        above(process, "Mode menu", box, "r")
        check(js(process, "document.querySelectorAll('.mode-menu .mode-item small').length") == 3
              and not js(process, "!!document.querySelector('.mode-card, [data-slot=tooltip-content]:not([data-state=closed])')"), "Mode menu: each mode's line is inline, no side card")
        if shot:
            copy(rpc(process, "capture", name=shot), shot)
    escape(process)


def above(process, name, box, edge):
    """A message box menu opens upward, above the whole box (not over the text), lined up with the box's edge."""
    b = js(process, "(() => { const b = document.querySelector('.ai-sidebar .composer').getBoundingClientRect(); return { t: b.top, l: b.left, r: b.right } })()")
    check(box["b"] <= b["t"] and abs(box[edge] - b[edge]) <= 1,
          f"{name} opens above the message box, lined up with its {'right' if edge == 'r' else 'left'} edge (bottom {box['b']:.0f} vs {b['t']:.0f}, edge {box[edge]:.0f} vs {b[edge]:.0f})")


def copy(reply, name):
    path = Path(reply.get("path") or "") if isinstance(reply, dict) else None
    if SHOTS and path and path.exists():
        SHOTS.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, SHOTS / name)


def idle(process):
    return until(lambda: js(process, "!!document.querySelector('.ai-sidebar .ai-send:not(.is-stop)') && !document.querySelector('.ai-sidebar .ai-working')"), 20)


def popovers(process, layout, theme):
    """Every popover in the panel, in a new chat, after a reply and while the AI works."""
    GROUP[:] = [layout, theme]
    send(process, "preference", key="theme", value=theme)
    until(lambda: js(process, "document.documentElement.classList.contains('dark')") == (theme == "Dark"), 5)
    send(process, "aiNew")
    until(lambda: js(process, "!!document.querySelector('.ai-sidebar .ai-hello')"), 10)
    time.sleep(.3)
    shot = f"popovers-{'mac' if MAC else 'windows'}-{theme.lower()}.png" if SHOTS and layout == "400" else None
    mode_menu(process, True, shot)
    box = menu(process, "Add a skill or a tab menu", ".ai-sidebar .composer-add")
    if box:
        above(process, "Add a skill or a tab menu", box, "l")
    type_into(process, ".ai-sidebar .composer textarea", "/")
    inside(process, "Skill picker (/)", ".ai-sidebar .skill-menu")
    type_into(process, ".ai-sidebar .composer textarea", "")
    send(process, "aiAdvanced", on=True)
    if until(lambda: js(process, "!!document.querySelector('.ai-sidebar .ai-model')"), 5):
        menu(process, "Model picker", ".ai-sidebar .ai-model", "[data-slot=select-content]")
        menu(process, "Effort picker", ".ai-sidebar .ai-pick:not(.ai-model)", "[data-slot=select-content]")
    else:
        check(False, "Advanced shows the model and effort pickers")
    escape(process)
    send(process, "aiAdvanced", on=False)
    until(lambda: not js(process, "!!document.querySelector('.ai-sidebar .ai-model')"), 5)
    tip(process, "Page chip", ".ai-sidebar span.chat-chip")
    tip(process, "Remember this chat", ".ai-sidebar .chat-memory [role=switch]")
    for label in ("AI settings", "Close chat"):
        tip(process, label, f".ai-sidebar .ai-head button[aria-label='{label}']")

    submit(process, "hello")
    if until(lambda: js(process, "!!document.querySelector('.ai-sidebar .ai-actions button')"), 20):
        tip(process, "Copy", ".ai-sidebar .ai-actions button")
    else:
        check(False, "The fake reply arrives")
    mode_menu(process, False)
    for label in ("Open as a tab", "New chat", "AI settings", "Close chat"):
        tip(process, label, f".ai-sidebar .ai-head button[aria-label='{label}']")

    submit(process, "WAIT a moment")
    if until(lambda: js(process, "!!document.querySelector('.ai-sidebar .ai-send.is-stop')"), 15):
        tip(process, "Stop", ".ai-sidebar .ai-send.is-stop")
        submit(process, "and then this")
        if until(lambda: js(process, "!!document.querySelector('.ai-sidebar .ai-queued button[aria-label=\"Don\\'t send\"]')"), 5):
            tip(process, "Don't send", ".ai-sidebar .ai-queued button[aria-label=\"Don't send\"]")
        else:
            check(False, "A message sent while it works waits as Up next")
        escape(process)
        send(process, "aiUnqueue")
    else:
        check(False, "The AI starts working")
    send(process, "aiStop")
    idle(process)


def start(name, width, height):
    profile = RUN / name
    (profile / "agents").mkdir(parents=True)
    (profile / "skills").mkdir()
    for i, skill in enumerate(("Trip plan", "Price check", "Weekly digest", "Recipe swap", "Inbox sweep", "Gift ideas", "Read later", "Compare laptops")):
        (profile / "skills" / f"skill-{i}.md").write_text(f"---\nname: {skill}\ndescription: {skill}, step by step, with a long line that has to wrap or cut off\n---\n\nDo it.\n")
    (profile / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(RUN / "bin" / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run"], "model": ["--model", "{model}"], "models": ["fast-1", "big-2"],
        "effort": ["--effort", "{effort}"], "output": "stream-json"}))
    crew = CREW + [{"Id": "tomas", "Name": "Tomas", "Job": "A builder."}, {"Id": "ines", "Name": "Ines", "Job": "A writer."}]
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False,
        "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake", "Width": width, "Height": height},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, profile)
    send(process, "aiToggle")
    until(lambda: js(process, "!!document.querySelector('.ai-sidebar .composer textarea')"), 30)
    return process


def main():
    (RUN / "bin").mkdir(parents=True)
    (RUN / "bin" / "fake_agent.py").write_text(FAKE)
    launcher(RUN / "bin" / "fakeagent", RUN / "bin" / "fake_agent.py")
    full = None
    process = start("window", 1280, 800)
    try:
        for width in (320, 400, 480, 600):
            js(process, f"document.querySelector('.ai-sidebar').style.width = '{width}px'")
            for theme in ("Light", "Dark"):
                popovers(process, str(width), theme)
        js(process, "document.querySelector('.ai-sidebar').style.width = ''")
        before = js(process, "innerWidth")
        send(process, "maximize")
        full = until(lambda: js(process, "innerWidth > " + str(before) + " && [innerWidth, innerHeight]"), 10)
        time.sleep(.5)
        GROUP[:] = ["maximized", "Light"]
        check(bool(full), f"The window maximizes ({full})")
        for theme in ("Light", "Dark"):
            popovers(process, "maximized", theme)
    finally:
        rpc(process, "quit")
        until(lambda: process.poll() is not None, 15)
    # Snapped to half the screen: half the maximized width, the full height.
    width, height = (full[0] // 2, full[1]) if full else (960, 1040)
    if MAC:  # the Mac keeps its window's frame under its own name, not in Still's Width and Height
        import plistlib
        import subprocess
        bundle = plistlib.loads((EXE.parents[1] / "Info.plist").read_bytes())["CFBundleIdentifier"]
        subprocess.run(["defaults", "write", bundle, "NSWindow Frame StillMain", f"0 0 {width} {height} 0 0 {width * 2} {height}"], check=True)
    process = start("snapped", width, height)
    print(f"Snapped half: {width} x {height}", flush=True)
    try:
        for theme in ("Light", "Dark"):
            popovers(process, "snapped-half", theme)
    finally:
        rpc(process, "quit")
        until(lambda: process.poll() is not None, 15)

    print()
    for key, (passed, failed) in TALLY.items():
        print(f"{key:20} {passed:3} passed {failed:3} failed")
    total = [sum(v[i] for v in TALLY.values()) for i in (0, 1)]
    print(f"{'all':20} {total[0]:3} passed {total[1]:3} failed")
    shutil.rmtree(RUN, ignore_errors=True)
    return 1 if total[1] else 0


if __name__ == "__main__":
    sys.exit(main())
