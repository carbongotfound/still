"""The companion library: New companion opens Still's seven first (live mascot, name, role, one line, Add or Added),
then Make your own and Paste a shared companion. A card opens a preview in the profile panel; Add there hires it.

Run: python tests/desktop/library.py artifacts/Still-QA/Still.exe [OUTDIR]  (screenshots of the library and a preview)
"""
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("library-" + uuid.uuid4().hex[:8])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else RUN / "shots"
PROFILE = RUN / "profile"
FAILED = []
SEVEN = ["Zest", "Bloom", "Noon", "Fizz", "Mallow", "Rivet", "Glint"]


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


def shown(p, selector):
    return js(p, f"!!document.querySelector({json.dumps(selector)})")


def click(p, selector, words=""):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => (e.innerText + (e.getAttribute('aria-label') ?? '')).includes({json.dumps(words)})); e?.click(); return !!e }})()")


def escape(p):
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")


def capture(p, name):
    got = rpc(p, "capture", name=name)
    if "error" in got:  # the first capture after the 3D views start can be slow
        got = rpc(p, "capture", name=name)
    if (PROFILE / name).exists():
        shutil.copy(PROFILE / name, OUT / name)
    else:
        print("capture:", got)


def open_library(p):
    click(p, ".mate-switch-more[aria-label='New companion']")
    return until(lambda: shown(p, ".library-dialog"), 5)


def paste(p, selector, value):
    js(p, f"(() => {{ const d = new DataTransfer(); d.setData('text/plain', {json.dumps(value)}); document.querySelector({json.dumps(selector)})?.dispatchEvent(new ClipboardEvent('paste', {{ clipboardData: d, bubbles: true, cancelable: true }})) }})()")


def main():
    PROFILE.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    crew = [{**c, "Crew": {"zest": "closer", "glint": "researcher"}[c["Id"]]} for c in CREW if c["Id"] in ("zest", "glint")]
    crew.sort(key=lambda c: c["Id"] != "zest")
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        send(p, "new")
        until(lambda: shown(p, ".home-face"), 20)
        time.sleep(.4)
        escape(p)  # a new tab opens with the address bar's suggestions

        # The library: seven cards in order, each a live mascot with a role and a line; the two you have say Added.
        check(open_library(p), "New companion opens the library")
        names = json.loads(js(p, "JSON.stringify([...document.querySelectorAll('.library-card .library-text b')].map(e => e.innerText))") or "[]")
        check(names == SEVEN, f"Still's seven come first, in order ({names})")
        check(js(p, "[...document.querySelectorAll('.library-card')].every(c => c.querySelector('.library-portrait .mascot') && c.querySelector('.library-text small')?.innerText && c.querySelector('.library-text > span')?.innerText.length > 20)"),
              "Every card has its mascot, its role and a one-line description")
        added = json.loads(js(p, "JSON.stringify([...document.querySelectorAll('.library-card.is-added .library-text b')].map(e => e.innerText))") or "[]")
        check(added == ["Zest", "Glint"] and js(p, "document.querySelectorAll('.library-card .library-add').length") == 5, f"The ones you have are marked Added; the rest have Add ({added})")
        check(js(p, "(() => { const rows = [...document.querySelectorAll('.library-more .library-row')].map(e => e.innerText); const grid = document.querySelector('.library-grid'), more = document.querySelector('.library-more'); return rows.length === 2 && rows[0].includes('Make your own') && rows[1].includes('Paste a shared companion') && !!(grid.compareDocumentPosition(more) & Node.DOCUMENT_POSITION_FOLLOWING) })()"),
              "Below the library: Make your own, then Paste a shared companion")
        check(until(lambda: js(p, "document.querySelectorAll('.library-card .library-portrait canvas[data-live]').length") == 7, 15), "All seven mascots are animated")
        time.sleep(1.5)
        capture(p, "library.png")

        # Add straight from a card.
        click(p, ".library-add", "Add Fizz")
        check(until(lambda: mates().get("Fizz", {}).get("Crew") == "marketer", 5), "Add on a card hires that companion")
        check(until(lambda: js(p, "[...document.querySelectorAll('.library-card.is-added .library-text b')].some(e => e.innerText === 'Fizz')"), 5), "and its card turns to Added")

        # A card opens the preview: the profile panel, before anything is saved.
        click(p, ".library-open", "Meet Bloom")
        check(until(lambda: shown(p, ".profile-panel.is-preview[aria-label='Meet Bloom']"), 5) and not shown(p, ".library-dialog"), "A card opens Bloom's preview in the profile panel")
        check(js(p, "document.querySelector('.profile-tablist')?.innerText.replace(/\\s+/g, ' ').trim()") == "General Skills Routines Model", "The preview has the tabs that make sense before hiring")
        check(until(lambda: shown(p, ".profile-panel .profile-stage .mascot"), 5) and js(p, "document.querySelectorAll('.profile-will li').length") == 3, "It shows the live mascot and what Bloom does")
        check("Bloom" not in mates(), "Nothing is saved while you look")
        js(p, """(() => { const e = document.querySelector('.profile-field input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, 'Blossom'); e.dispatchEvent(new Event('input', { bubbles: true })) })()""")
        time.sleep(1)
        check("Blossom" not in mates(), "Changing the name in the preview saves nothing yet")
        time.sleep(1)
        capture(p, "library-preview.png")
        click(p, ".profile-foot button", "Add Blossom")
        check(until(lambda: mates().get("Blossom", {}).get("Crew") == "scout", 5), "Add in the preview hires Bloom, with your changes")
        check(until(lambda: shown(p, ".library-dialog") and not shown(p, ".profile-panel"), 5), "and goes back to the library")
        check(until(lambda: js(p, "[...document.querySelectorAll('.library-card.is-added .library-text b')].some(e => e.innerText === 'Bloom')"), 5), "where Bloom is Added")

        # Esc in a preview goes back to the library; an added card opens the real profile.
        click(p, ".library-open", "Meet Noon")
        until(lambda: shown(p, ".profile-panel.is-preview"), 5)
        escape(p)
        check(until(lambda: shown(p, ".library-dialog") and not shown(p, ".profile-panel"), 5) and "Noon" not in mates(), "Esc in the preview goes back to the library without adding")
        click(p, ".library-open", "Open Zest's profile")
        check(until(lambda: shown(p, ".profile-panel[aria-label=\"Zest's profile\"]") and not shown(p, ".profile-panel.is-preview"), 5), "A card you already have opens its profile")
        escape(p)
        until(lambda: not shown(p, ".profile-panel"), 3)

        # Paste a shared companion: a wrong paste says so, a right one adds them.
        check(open_library(p), "The library opens again")
        click(p, ".library-row", "Paste a shared companion")
        until(lambda: shown(p, ".library-row textarea"), 3)
        paste(p, ".library-row textarea", "hello")
        check(until(lambda: shown(p, ".library-bad"), 3), "Pasting something else says it isn't a shared companion")
        share = {"kind": "still.companion", "v": 1, "name": "Pasty", "look": "", "job": "Checks prices.", "tone": "", "mode": "default", "crew": ""}
        paste(p, ".library-row textarea", json.dumps(share))
        check(until(lambda: mates().get("Pasty", {}).get("Job") == "Checks prices.", 5) and until(lambda: not shown(p, ".library-dialog"), 3), "Pasting a shared companion adds them and closes the library")

        # Make your own opens the create dialog. The Companions page's button opens the library too.
        open_library(p)
        click(p, ".library-row", "Make your own")
        check(until(lambda: shown(p, ".companion-dialog") and not shown(p, ".library-dialog"), 5), "Make your own opens the create dialog")
        escape(p)
        until(lambda: not shown(p, ".companion-dialog"), 3)
        js(p, "document.querySelector('.home-rail-item[aria-label=Companions]')?.click()")
        until(lambda: shown(p, ".mate-grid"), 5)
        click(p, ".home-new", "New companion")
        check(until(lambda: shown(p, ".library-dialog"), 5), "The Companions page's New companion opens the library")
        escape(p)

        errors = js(p, "JSON.stringify(window.__errors || [])")
        check(errors in (None, "[]"), f"No script errors ({errors})")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
    print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'ALL PASSED'}  shots in {OUT}")
    sys.exit(1 if FAILED else 0)


main()
