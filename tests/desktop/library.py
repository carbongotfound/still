"""The companion library: Hire a companion opens Still's six first, three across: each card the live character big on a
soft glow of its color, its role-first name, one line, Hire (or Hired) and View profile. Then Make your own and Paste a
shared companion. Hiring one adds its skills, knowledge files and routine (off). View profile opens its profile: its card
on the left, what's included, skills, routine, knowledge files, About, tips and its full instructions on the right. Then
the switcher: every companion's face, scrolling sideways when they don't fit.

Run: python tests/desktop/library.py artifacts/Still-QA/Still.exe [OUTDIR]  (screenshots of the library, a profile and the switcher)
"""
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, companions_page, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("library-" + uuid.uuid4().hex[:8])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else RUN / "shots"
PROFILE = RUN / "profile"
FAILED = []
SIX = ["Sales Jonah", "Growth Talia", "Planner Nora", "Marketing Leo", "Engineer Ivan", "Research Maya"]


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
    click(p, ".mate-switch-more[aria-label='Hire a companion']")
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

        # The library: six cards in order, each a live mascot with its role-first name and one line; the two you have say Hired.
        check(open_library(p), "Hire a companion opens the library")
        check(js(p, "document.querySelector('.companion-library [data-slot=dialog-description]')?.innerText") == "Each one comes with instructions and skills for its role, and starts working as soon as you hire it.",
              "The header says what hiring one gives you")
        names = json.loads(js(p, "JSON.stringify([...document.querySelectorAll('.library-card .role-title')].map(e => e.innerText))") or "[]")
        check(names == SIX + ["Assistant Ruth"], f"Still's six come first, in order, each with its role in front, then Assistant Ruth ({names})")
        check(js(p, "[...document.querySelectorAll('.library-card')].every(c => c.querySelector('.role-art .mascot') && !c.querySelector('.role-tag') && !c.querySelector('.role-expect h4') && c.querySelectorAll('.role-expect p').length === 1 && c.querySelector('.role-act .role-profile')?.innerText === 'View profile')"),
              "Every card has its character, its name, one line and View profile: no role tag, no list")
        check(js(p, "document.querySelector('.library-card:nth-child(6) .role-expect p')?.innerText") == "Researches anything and backs every claim with a source.", "Maya's line says what she does")
        check(not js(p, "/\\bI'(ll|m)\\b|\\bI will\\b/.test(document.querySelector('.companion-library').innerText)"), "No card speaks in the first person")
        added = json.loads(js(p, "JSON.stringify([...document.querySelectorAll('.library-card.is-added .role-title')].map(e => e.innerText))") or "[]")
        check(added == ["Sales Jonah", "Research Maya"] and js(p, "document.querySelectorAll('.library-card .library-add').length") == 5, f"The ones you have are marked Hired; the rest have Hire ({added})")
        check(js(p, "[...document.querySelectorAll('.library-card .library-add')].every(b => b.innerText.trim() === 'Hire' && b.getAttribute('aria-label').startsWith('Hire ')) && [...document.querySelectorAll('.library-card .library-added')].every(b => b.innerText.trim() === 'Hired' && b.querySelector('svg'))"),
              "The buttons say Hire, and hired ones say Hired with a check")
        btn = json.loads(js(p, """JSON.stringify((() => { const a = document.querySelector('.library-card .library-add'), b = getComputedStyle(a), l = getComputedStyle(a.nextElementSibling)
            return [b.backgroundColor, a.nextElementSibling.className, l.backgroundColor, Math.round(a.getBoundingClientRect().left - a.closest('.role-body').getBoundingClientRect().left)] })())""") or "[]")
        check(btn[:3] == ["rgb(255, 255, 255)", "role-profile", "rgba(0, 0, 0, 0)"] and abs(btn[3] - 18) <= 1, f"Hire is a solid white button on the left, with View profile beside it as a plain link ({btn})")
        # Built around the character: the stage is at least 40% of the card, the character about 70% of the stage; three
        # across at this width, two when the library is narrower.
        size = json.loads(js(p, """JSON.stringify([...document.querySelectorAll('.library-card')].map(c => { const r = c.getBoundingClientRect(), a = c.querySelector('.role-art').getBoundingClientRect(), m = c.querySelector('.role-art .mascot').getBoundingClientRect()
            return [+(a.height / r.height).toFixed(2), +(m.height / a.height).toFixed(2), Math.round(a.width - r.width)] }))""") or "[]")
        check(size and all(a >= .4 and m >= .7 and w >= -2 for a, m, w in size), f"Each card's art spans its width, is 40%+ of the card, and the character fills 70%+ of it ({size})")
        cols = "getComputedStyle(document.querySelector('.library-grid')).gridTemplateColumns.split(' ').length"
        check(js(p, cols) == 3, f"Three cards across in a wide window ({js(p, cols)})")
        js(p, "document.querySelector('.companion-library').style.width = '700px'")
        time.sleep(.4)
        check(js(p, cols) == 2, f"and two when it's narrower ({js(p, cols)})")
        js(p, "document.querySelector('.companion-library').style.width = ''")
        time.sleep(.4)
        check(js(p, "(() => { const rows = [...document.querySelectorAll('.library-more .role-card')].map(e => e.innerText); const grid = document.querySelector('.library-grid'), more = document.querySelector('.library-more'); return rows.length === 2 && rows[0].includes('Make your own') && rows[1].includes('Paste a shared companion') && !!(grid.compareDocumentPosition(more) & Node.DOCUMENT_POSITION_FOLLOWING) })()"),
              "Below the library: Make your own, then Paste a shared companion")
        live = "(() => { const box = document.querySelector('.companion-library').getBoundingClientRect(); return [...document.querySelectorAll('.library-card')].filter(c => { const r = c.getBoundingClientRect(); return r.bottom > box.top && r.top < box.bottom }).every(c => c.querySelector('.role-art canvas[data-live]')) })()"
        check(until(lambda: js(p, live), 15), "Every mascot in view is animated")
        js(p, "document.querySelector('.library-card:nth-child(6)').scrollIntoView({ block: 'center' })")
        check(until(lambda: js(p, "!!document.querySelector('.library-card:nth-child(6) .role-art canvas[data-live]')"), 10), "and Maya's starts when it scrolls into view")
        js(p, "document.querySelector('.companion-library').scrollTop = 0")
        # The look: one UI typeface, plain cards, each character on a soft glow of its color.
        look = json.loads(js(p, """JSON.stringify((() => { const d = document.querySelector('.companion-library'), t = getComputedStyle(d.querySelector('[data-slot=dialog-title]')),
            c = document.querySelector('.library-card:nth-child(2)'), cs = getComputedStyle(c), n = getComputedStyle(c.querySelector('.role-title')), line = getComputedStyle(c.querySelector('.role-expect p')),
            g = getComputedStyle(c.querySelector('.role-art')), g3 = getComputedStyle(document.querySelector('.library-card:nth-child(3) .role-art')), body = getComputedStyle(c.querySelector('.role-body')), own = getComputedStyle(document.querySelector('.library-own')), ds = getComputedStyle(d)
            return { title: [t.fontFamily, t.fontSize, t.fontWeight], name: [n.fontFamily, n.fontSize, n.fontWeight], body: [line.fontSize, line.lineHeight], card: [cs.borderRadius, body.paddingTop],
             plain: cs.backgroundColor === getComputedStyle(document.querySelector('.library-card:nth-child(3)')).backgroundColor, gap: getComputedStyle(document.querySelector('.library-grid')).rowGap,
             glow: [g.backgroundImage.startsWith('radial-gradient'), g.backgroundImage !== g3.backgroundImage, g.boxShadow], own: own.borderTopStyle, dialog: [ds.paddingTop, ds.borderTopLeftRadius] } })())""") or "{}")
        check(all("Geist" in look.get(k, ["serif"])[0] for k in ("title", "name")) and look["title"][1:] == ["26px", "600"] and look["name"][1:] == ["18px", "600"] and look["body"] == ["14px", "21px"],
              f"Geist throughout: a 26px title, 18px names, 14px body at 1.5 ({look.get('title')}, {look.get('name')}, {look.get('body')})")
        check(look.get("card") == ["18px", "16px"] and look.get("gap") == "16px" and look.get("plain"), f"Cards: 18px corners, 16px padding under the art, 16px apart, all on the same plain card ({look.get('card')}, {look.get('gap')})")
        check(look.get("glow") == [True, True, "none"] and look.get("own") == "dashed" and look.get("dialog") == ["28px", "24px"],
              f"Each character stands on a soft glow of its own color, Make your own is dashed, the dialog has 28px padding and 24px corners ({look})")
        time.sleep(1.5)
        capture(p, "library.png")

        # Hire straight from a card: it comes with its role's four skills, its three knowledge files and its routine, off.
        click(p, ".library-add", "Hire Marketing Leo")
        check(until(lambda: mates().get("Leo", {}).get("Crew") == "marketing", 5), "Hire on a card hires that companion")
        check(until(lambda: shown(p, ".joined-card"), 3) and js(p, "document.querySelector('.joined-card [data-slot=dialog-title]')?.innerText") == "Marketing Leo joined your team"
              and click(p, ".joined-card button", "Not now") and until(lambda: not shown(p, ".joined-card"), 3), "It says Marketing Leo joined; Not now goes back to the library")
        leo = mates().get("Leo", {})
        routines = leo.get("Routines") or []
        check(len(routines) == 1 and routines[0].get("On") is False and routines[0].get("Days") == [5] and routines[0].get("Text", "").startswith("/post-set ") and "Don't post" in routines[0].get("Text", ""),
              f"Leo comes with its routine, off until you turn it on, and it runs Leo's post set skill ({routines})")
        kit = ["launch-post", "newsletter", "post-set", "voice-match"]
        check(sorted(leo.get("Skills") or []) == kit and all((PROFILE / "skills" / (k + ".md")).exists() for k in kit), f"and its four skills, added and turned on ({leo.get('Skills')})")
        notes = sorted(f.stem for f in (PROFILE / "companions" / leo.get("Id", "?") / "knowledge").glob("*.md"))
        check(notes == ["audience", "landed", "voice"], f"and its three knowledge files, empty to start ({notes})")
        check(until(lambda: js(p, "[...document.querySelectorAll('.library-card.is-added .role-title')].some(e => e.innerText === 'Marketing Leo')"), 5), "and its card turns to Hired")

        # View profile opens Talia's profile, before anything is saved: her card on the left, what hiring her gives you on the right.
        js(p, "[...document.querySelectorAll('.library-card')].find(c => c.querySelector('.role-title')?.innerText === 'Growth Talia')?.querySelector('.role-profile')?.click()")
        check(until(lambda: shown(p, ".hire-profile"), 5) and until(lambda: not shown(p, ".companion-library"), 3), "View profile opens Talia's profile in place of the library")
        prof = json.loads(js(p, """JSON.stringify((() => { const d = document.querySelector('.hire-profile'), q = s => d.querySelector(s)?.innerText.trim(), all = s => [...d.querySelectorAll(s)].map(e => e.innerText.trim().replace(/\\s+/g, ' '))
            const part = h => [...d.querySelectorAll('.hire-profile-section')].find(s => s.querySelector('h3')?.innerText === h)
            return { title: q('[data-slot=dialog-title]'), font: getComputedStyle(d.querySelector('[data-slot=dialog-title]')).fontFamily, line: q('[data-slot=dialog-description]'), hire: q('.hire-profile-hire'), apps: all('.hire-profile-works .plug-chip').length, web: all('.hire-profile-works .plug-chip').at(-1),
             counts: all('.hire-profile-counts div'), skills: all('.hire-profile-skill b'), lines: all('.hire-profile-skill small').every(Boolean), icons: d.querySelectorAll('.hire-profile-skill > span svg').length,
             routine: q('.hire-profile-routine b'), when: q('.hire-profile-routine small'), files: all('.hire-profile-files b'), notes: all('.hire-profile-note'), sections: all('.hire-profile-section h3'),
             about: part('About')?.innerText, tips: part('Tips')?.querySelectorAll('p').length, full: q('.hire-profile-full'), mascot: Math.round(d.querySelector('.hire-profile-art .mascot')?.getBoundingClientRect().height ?? 0) } })())""") or "{}")
        check(prof.get("title") == "Growth Talia" and "Geist" in prof.get("font", "") and prof.get("hire") == "Hire Growth Talia" and prof.get("mascot", 0) >= 200 and len(prof.get("line") or "") > 40,
              f"Her card: the character big, Growth Talia, a short summary and Hire Growth Talia ({prof.get('title')}, {prof.get('hire')}, {prof.get('mascot')})")
        check(prof.get("apps") == 4 and prof.get("web") == "Any website", f"Works in: her three apps and any website ({prof.get('apps')}, {prof.get('web')})")
        check(prof.get("sections") == ["What's included", "Skills", "Routines", "Knowledge files", "About", "Tips"], f"One card per section ({prof.get('sections')})")
        check(prof.get("counts") == ["4 Skills", "1 Routine", "3 Knowledge files", "3 Apps"], f"What's included counts what she really comes with ({prof.get('counts')})")
        check(prof.get("skills") == ["Experiment plan", "Funnel audit", "Lifecycle emails", "Weekly numbers"] and prof.get("lines") and prof.get("icons") == 4, f"Her four skills as tiles, each with an icon and a line ({prof.get('skills')})")
        check(prof.get("routine") == "Check this week's growth numbers" and prof.get("when") == "Every Monday at 9:00 · uses Weekly numbers", f"Her routine, when it runs and the skill it uses ({prof.get('routine')}, {prof.get('when')})")
        check(any("off until you turn them on" in n and "suggests" in n for n in prof.get("notes", [])) and any("fill in as you work" in n for n in prof.get("notes", [])),
              "Routines stay off until turned on; knowledge files fill in as you work")
        check(prof.get("files") == ["Experiments", "Your numbers", "Your product"], f"Her knowledge files and what each holds ({prof.get('files')})")
        check((prof.get("about") or "").rstrip().endswith("I won't send, post or change anything without your OK.") and "I'm Talia" in (prof.get("about") or "") and prof.get("tips") == 3,
              "About in her own words, promising nothing goes out without your OK, then three tips")
        check(prof.get("full") == "See full instructions" and not shown(p, ".hire-profile-instructions"), "The full instructions wait behind See full instructions")
        stay = json.loads(js(p, """JSON.stringify((() => { const d = document.querySelector('.hire-profile'), c = d.querySelector('.hire-profile-card').getBoundingClientRect(), m = d.querySelector('.hire-profile-main'), r = m.getBoundingClientRect()
            m.scrollTop = 400; return [Math.round(c.right) <= Math.round(r.left), m.scrollTop > 0, Math.round(d.querySelector('.hire-profile-card').getBoundingClientRect().top - c.top)] })())""") or "[]")
        check(stay == [True, True, 0], f"Two columns, and the card stays put while the right side scrolls ({stay})")
        js(p, "document.querySelector('.hire-profile-main').scrollTop = 0")
        check("Talia" not in mates(), "Nothing is saved while you look")
        time.sleep(1.5)
        capture(p, "profile.png")
        click(p, ".hire-profile-full")
        check(until(lambda: "## How you judge the work" in (js(p, "document.querySelector('.hire-profile-instructions')?.innerText") or ""), 3)
              and js(p, "document.querySelector('.hire-profile-full').getAttribute('aria-expanded')") == "true", "See full instructions opens the whole job brief")
        escape(p)
        check(until(lambda: shown(p, ".companion-library") and not shown(p, ".hire-profile"), 5) and "Talia" not in mates(), "Esc goes back to the library without hiring")

        # Hire from a profile: Nora joins and the library is back, with her card Hired.
        js(p, "[...document.querySelectorAll('.library-card')].find(c => c.querySelector('.role-title')?.innerText === 'Planner Nora')?.querySelector('.role-art')?.click()")
        check(until(lambda: shown(p, ".hire-profile-hire"), 5) and click(p, ".hire-profile-hire", "Hire Planner Nora"), "The art opens Nora's profile too")
        check(until(lambda: mates().get("Nora", {}).get("Crew") == "planner", 5), "Hire on her profile hires Nora")
        check(until(lambda: shown(p, ".joined-card"), 3) and "Planner Nora joined your team" in (js(p, "document.querySelector('.joined-card')?.innerText") or ""), "and says Planner Nora joined")
        click(p, ".joined-card button", "Not now")
        check(until(lambda: shown(p, ".companion-library") and not shown(p, ".hire-profile"), 5), "and goes back to the library")
        check(until(lambda: js(p, "[...document.querySelectorAll('.library-card.is-added .role-title')].some(e => e.innerText === 'Planner Nora')"), 5), "where Nora is Hired")
        js(p, "[...document.querySelectorAll('.library-card')].find(c => c.querySelector('.role-title')?.innerText === 'Sales Jonah')?.querySelector('.role-profile')?.click()")
        check(until(lambda: shown(p, ".hire-profile-hired"), 5) and not shown(p, ".hire-profile-hire") and js(p, "document.querySelector('.hire-profile-hired').innerText.trim()") == "Hired",
              "A companion you have says Hired, with a check, on its profile")
        escape(p)
        until(lambda: shown(p, ".companion-library") and not shown(p, ".hire-profile"), 5)
        escape(p)
        until(lambda: not shown(p, ".companion-library"), 3)

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

        # Make your own opens the companion editor on a new companion. The Companions page's button opens the library too.
        open_library(p)
        click(p, ".library-more .role-head", "Make your own")
        check(until(lambda: shown(p, ".profile-panel .profile-foot") and not shown(p, ".companion-library"), 5), "Make your own opens the companion editor, with Hire at the bottom")
        escape(p)
        until(lambda: not shown(p, ".profile-panel"), 3)
        companions_page(p)
        click(p, ".home-new", "Hire a companion")
        check(until(lambda: shown(p, ".companion-library"), 5), "The Companions page's Hire a companion opens the library")
        escape(p)

        # The switcher: every companion's face (the one you're with by name), then +, and no menu. When they don't all
        # fit, the row scrolls sideways.
        until(lambda: not shown(p, ".companion-library"), 3)
        send(p, "new")
        until(lambda: shown(p, ".home-face") and shown(p, ".mate-switch"), 10)
        time.sleep(.4)
        escape(p)  # the new tab's address bar suggestions
        time.sleep(1)
        sw = json.loads(js(p, """JSON.stringify((() => { const s = document.querySelector('.mate-switch')
            return { faces: s.querySelectorAll('.mate-switch-face').length, on: s.querySelector('.mate-switch-on')?.innerText.trim(), last: s.lastElementChild?.getAttribute('aria-label'), menu: !!s.querySelector('[aria-haspopup]') } })())""") or "{}")
        check(sw.get("faces") == len(mates()) and sw.get("on") and sw.get("last") == "Hire a companion" and not sw.get("menu"), f"The switcher shows every companion, the one you're with by name, then +, and no menu ({sw})")
        capture(p, "switcher.png")
        js(p, "document.querySelector('.mate-switch').style.maxWidth = '150px'")
        time.sleep(.3)
        check(js(p, "(() => { const s = document.querySelector('.mate-switch'); return s.scrollWidth > s.clientWidth && getComputedStyle(s).overflowX === 'auto' && s.getBoundingClientRect().height < 42 })()"),
              "When they don't fit, the row scrolls sideways on one line")
        js(p, "document.querySelector('.mate-switch').style.maxWidth = ''")

        errors = js(p, "JSON.stringify(window.__errors || [])")
        check(errors in (None, "[]"), f"No script errors ({errors})")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
    print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'ALL PASSED'}  shots in {OUT}")
    sys.exit(1 if FAILED else 0)


main()
