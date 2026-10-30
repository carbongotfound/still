"""The companion library: New companion opens Still's six first (live mascot, name, role, what to expect, Add or Added),
then Make your own and Paste a shared companion, all as cards in the companion's color. A card opens a preview in the
profile panel; Add there hires it, with its routine, off.

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
SIX = ["Jonah", "Talia", "Nora", "Leo", "Ivan", "Maya"]


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
    return until(lambda: shown(p, ".companion-library"), 5)


def paste(p, selector, value):
    js(p, f"(() => {{ const d = new DataTransfer(); d.setData('text/plain', {json.dumps(value)}); document.querySelector({json.dumps(selector)})?.dispatchEvent(new ClipboardEvent('paste', {{ clipboardData: d, bubbles: true, cancelable: true }})) }})()")


def main():
    PROFILE.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    crew = [{**c, "Crew": {"jonah": "sales", "maya": "research"}[c["Id"]]} for c in CREW if c["Id"] in ("jonah", "maya")]
    crew.sort(key=lambda c: c["Id"] != "jonah")
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        send(p, "new")
        until(lambda: shown(p, ".home-face"), 20)
        time.sleep(.4)
        escape(p)  # a new tab opens with the address bar's suggestions

        # The library: six cards in order, each a live mascot with a role and what to expect; the two you have say Added.
        check(open_library(p), "New companion opens the library")
        names = json.loads(js(p, "JSON.stringify([...document.querySelectorAll('.library-card .role-title')].map(e => e.innerText))") or "[]")
        check(names == SIX, f"Still's six come first, in order ({names})")
        check(js(p, "[...document.querySelectorAll('.library-card')].every(c => c.querySelector('.role-glow .mascot') && c.querySelector('.role-tag')?.innerText && c.querySelector('.role-expect h4')?.innerText === 'What to expect' && c.querySelectorAll('.role-expect li').length === 3)"),
              "Every card has its mascot, its role and three things to expect")
        check(js(p, "document.querySelector('.library-card:nth-child(6) .role-expect')?.innerText.includes('Deep research with cited sources')"), "Maya's list starts with deep research with cited sources")
        check(not js(p, "/\\bI'(ll|m)\\b|\\bI will\\b/.test(document.querySelector('.companion-library').innerText)"), "No card speaks in the first person")
        added = json.loads(js(p, "JSON.stringify([...document.querySelectorAll('.library-card.is-added .role-title')].map(e => e.innerText))") or "[]")
        check(added == ["Jonah", "Maya"] and js(p, "document.querySelectorAll('.library-card .library-add').length") == 4, f"The ones you have are marked Added; the rest have Add ({added})")
        check(js(p, "(() => { const rows = [...document.querySelectorAll('.library-more .role-card')].map(e => e.innerText); const grid = document.querySelector('.library-grid'), more = document.querySelector('.library-more'); return rows.length === 2 && rows[0].includes('Make your own') && rows[1].includes('Paste a shared companion') && !!(grid.compareDocumentPosition(more) & Node.DOCUMENT_POSITION_FOLLOWING) })()"),
              "Below the library: Make your own, then Paste a shared companion")
        live = "(() => { const box = document.querySelector('.companion-library').getBoundingClientRect(); return [...document.querySelectorAll('.library-card')].filter(c => { const r = c.getBoundingClientRect(); return r.bottom > box.top && r.top < box.bottom }).every(c => c.querySelector('.role-glow canvas[data-live]')) })()"
        check(until(lambda: js(p, live), 15), "Every mascot in view is animated")
        js(p, "document.querySelector('.library-card:nth-child(6)').scrollIntoView({ block: 'center' })")
        check(until(lambda: js(p, "!!document.querySelector('.library-card:nth-child(6) .role-glow canvas[data-live]')"), 10), "and Maya's starts when it scrolls into view")
        js(p, "document.querySelector('.companion-library').scrollTop = 0")
        # The look: one UI typeface, the card tinted in its companion's color, a soft glow instead of a ring.
        look = json.loads(js(p, """JSON.stringify((() => { const d = document.querySelector('.companion-library'), t = getComputedStyle(d.querySelector('[data-slot=dialog-title]')),
            c = document.querySelector('.library-card:nth-child(2)'), cs = getComputedStyle(c), n = getComputedStyle(c.querySelector('.role-title')), li = getComputedStyle(c.querySelector('.role-expect li')),
            g = getComputedStyle(c.querySelector('.role-glow')), tag = getComputedStyle(c.querySelector('.role-tag')), own = getComputedStyle(document.querySelector('.library-own')), ds = getComputedStyle(d)
            return { title: [t.fontFamily, t.fontSize, t.fontWeight], name: [n.fontFamily, n.fontSize, n.fontWeight], body: [li.fontSize, li.lineHeight], card: [cs.borderRadius, cs.paddingTop], tinted: cs.backgroundColor !== ds.backgroundColor && cs.backgroundColor !== getComputedStyle(document.querySelector('.library-card:nth-child(3)')).backgroundColor && cs.borderTopColor !== getComputedStyle(document.querySelector('.library-card:nth-child(3)')).borderTopColor,
             gap: getComputedStyle(document.querySelector('.library-grid')).rowGap, glow: [g.backgroundImage.startsWith('radial-gradient'), g.boxShadow], tag: [tag.fontVariantCaps, tag.backgroundColor], own: own.borderTopStyle,
             dialog: [ds.paddingTop, ds.borderTopLeftRadius] } })())""") or "{}")
        check(all("Geist" in look.get(k, ["serif"])[0] for k in ("title", "name")) and look["title"][1:] == ["26px", "600"] and look["name"][1:] == ["18px", "600"] and look["body"] == ["14px", "21px"],
              f"Geist throughout: a 26px title, 18px names, 14px body at 1.5 ({look.get('title')}, {look.get('name')}, {look.get('body')})")
        check(look.get("card") == ["18px", "20px"] and look.get("gap") == "16px" and look.get("tinted"),
              f"Cards: 18px corners, 20px padding, 16px apart, tinted in their color ({look.get('card')}, {look.get('gap')})")
        check(look.get("glow") == [True, "none"] and look.get("tag", [""])[0] == "all-small-caps" and look["tag"][1] == "rgba(0, 0, 0, 0)" and look.get("own") == "dashed" and look.get("dialog") == ["28px", "24px"],
              f"The mascot sits on a soft glow, the role is small caps with no pill, Make your own is dashed, the dialog has 28px padding and 24px corners ({look})")
        time.sleep(1.5)
        capture(p, "library.png")

        # Add straight from a card.
        click(p, ".library-add", "Add Leo")
        check(until(lambda: mates().get("Leo", {}).get("Crew") == "marketing", 5), "Add on a card hires that companion")
        check(until(lambda: shown(p, ".joined-card"), 3) and click(p, ".joined-card button", "Not now") and until(lambda: not shown(p, ".joined-card"), 3), "It says Leo joined; Not now goes back to the library")
        routines = mates().get("Leo", {}).get("Routines") or []
        check(len(routines) == 1 and routines[0].get("On") is False and routines[0].get("Days") == [5] and "Don't post" in routines[0].get("Text", ""), f"Leo comes with its routine, off until you turn it on ({routines})")
        check(until(lambda: js(p, "[...document.querySelectorAll('.library-card.is-added .role-title')].some(e => e.innerText === 'Leo')"), 5), "and its card turns to Added")

        # A card opens the preview: the profile panel, before anything is saved.
        click(p, ".library-card .role-head", "Meet Talia")
        check(until(lambda: shown(p, ".profile-panel.is-preview[aria-label='Meet Talia']"), 5) and not shown(p, ".companion-library"), "A card opens Talia's preview in the profile panel")
        check(js(p, "document.querySelector('.profile-tablist')?.innerText.replace(/\\s+/g, ' ').trim()") == "General Skills & plugins Routines Model", "The preview has the tabs that make sense before hiring")
        check(until(lambda: shown(p, ".profile-panel .profile-stage .mascot"), 5) and js(p, "document.querySelectorAll('.profile-will li').length") == 3, "It shows the live mascot and what Talia does")
        check("Talia" not in mates(), "Nothing is saved while you look")
        js(p, """(() => { const e = document.querySelector('.profile-field input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, 'Blossom'); e.dispatchEvent(new Event('input', { bubbles: true })) })()""")
        time.sleep(1)
        check("Blossom" not in mates(), "Changing the name in the preview saves nothing yet")
        time.sleep(1)
        capture(p, "library-preview.png")
        click(p, ".profile-foot button", "Add Blossom")
        check(until(lambda: mates().get("Blossom", {}).get("Crew") == "growth", 5), "Add in the preview hires Talia, with your changes")
        check(until(lambda: shown(p, ".joined-card"), 3) and "Blossom joined your team" in (js(p, "document.querySelector('.joined-card')?.innerText") or ""), "and says Blossom joined")
        click(p, ".joined-card button", "Not now")
        check(until(lambda: shown(p, ".companion-library") and not shown(p, ".profile-panel"), 5), "and goes back to the library")
        check(until(lambda: js(p, "[...document.querySelectorAll('.library-card.is-added .role-title')].some(e => e.innerText === 'Talia')"), 5), "where Talia is Added")

        # Esc in a preview goes back to the library; an added card opens the real profile.
        click(p, ".library-card .role-head", "Meet Nora")
        until(lambda: shown(p, ".profile-panel.is-preview"), 5)
        escape(p)
        check(until(lambda: shown(p, ".companion-library") and not shown(p, ".profile-panel"), 5) and "Nora" not in mates(), "Esc in the preview goes back to the library without adding")
        click(p, ".library-card .role-head", "Open Jonah's profile")
        check(until(lambda: shown(p, ".profile-panel[aria-label=\"Jonah's profile\"]") and not shown(p, ".profile-panel.is-preview"), 5), "A card you already have opens its profile")
        escape(p)
        until(lambda: not shown(p, ".profile-panel"), 3)

        # Paste a shared companion: a wrong paste says so, a right one adds them.
        check(open_library(p), "The library opens again")
        click(p, ".library-more .role-head", "Paste a shared companion")
        until(lambda: shown(p, ".library-paste textarea"), 3)
        paste(p, ".library-paste textarea", "hello")
        check(until(lambda: shown(p, ".library-bad"), 3), "Pasting something else says it isn't a shared companion")
        share = {"kind": "still.companion", "v": 1, "name": "Pasty", "look": "", "job": "Checks prices.", "tone": "", "mode": "default", "crew": ""}
        paste(p, ".library-paste textarea", json.dumps(share))
        check(until(lambda: mates().get("Pasty", {}).get("Job") == "Checks prices.", 5) and until(lambda: not shown(p, ".companion-library"), 3), "Pasting a shared companion adds them and closes the library")
        check(until(lambda: shown(p, ".joined-card"), 3) and click(p, ".joined-card button", "Not now") and until(lambda: not shown(p, ".joined-card"), 3), "and says Pasty joined")

        # Make your own opens the create dialog. The Companions page's button opens the library too.
        open_library(p)
        click(p, ".library-more .role-head", "Make your own")
        check(until(lambda: shown(p, ".companion-dialog") and not shown(p, ".companion-library"), 5), "Make your own opens the create dialog")
        escape(p)
        until(lambda: not shown(p, ".companion-dialog"), 3)
        js(p, "document.querySelector('.home-rail-item[aria-label=Companions]')?.click()")
        until(lambda: shown(p, ".mate-grid"), 5)
        click(p, ".home-new", "New companion")
        check(until(lambda: shown(p, ".companion-library"), 5), "The Companions page's New companion opens the library")
        escape(p)

        errors = js(p, "JSON.stringify(window.__errors || [])")
        check(errors in (None, "[]"), f"No script errors ({errors})")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
    print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'ALL PASSED'}  shots in {OUT}")
    sys.exit(1 if FAILED else 0)


main()
