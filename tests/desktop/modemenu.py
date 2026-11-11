"""The message box's companion and mode menu, in a full chat, on the new tab page and in the side chat, light and dark,
at 100% and 150% (on Windows through DevTools' device metrics, which lay the page out as a display at that scale does)
and in a narrow window (720 px; the side chat 320 px):
- no two rows overlap, no text runs out of its row or into other text, and nothing in it is cut off;
- turning Advanced on hides Quick, Everyday and Thorough (not greyed out) and leaves its switch where it was; off
  brings them back;
- six of the eight companions show before the list scrolls; with six or fewer it doesn't scroll;
- it opens upward with a small gap above the message box, its right edge on its pill's (unless that would leave the
  chat panel or the page column), never over the tab strip or the address bar; with no room it scrolls inside itself;
- one row style: every icon, every title and every check in its own column.
A fake agent app stands in for the AI, so no plan is used. The Mac runs at its own scale (no device metrics there).

Run: python tests/desktop/modemenu.py artifacts/Still-QA/Still.exe [--shots DIR]
--shots DIR saves the open menu for each place, theme, scale and width as modemenu-<os>-<...>.png in DIR.
"""
import base64
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
RUN = ROOT / "artifacts" / ("modemenu-" + uuid.uuid4().hex[:8])
FAILS, PASSES = [], [0]
GROUP = [""]

FAKE = textwrap.dedent(r'''
    import json, sys, time
    if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
    sys.stdin.read()
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done, fake reply."}]}})
    say({"type": "result", "subtype": "success", "is_error": False})
''')

# The open menu's rows and text, measured once its opening animation is over: rows that overlap, text outside its row
# or over other text, anything cut off, the icon / title / check columns, the companion list and where it sits.
GEOM = r"""(chip => { const m = [...document.querySelectorAll('.mode-menu')].filter(e => e.dataset.state !== 'closed').pop(); if (!m) return null
 if (m.getAnimations({ subtree: true }).some(a => a.playState === 'running')) return null
 const box = e => e.getBoundingClientRect(), say = e => (e.innerText || e.placeholder || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 30)
 const cut = (a, b) => { const l = Math.max(a.left, b.left), t = Math.max(a.top, b.top), r = Math.min(a.right, b.right), bt = Math.min(a.bottom, b.bottom); return r > l && bt > t ? { left: l, top: t, right: r, bottom: bt } : null }
 const hit = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1
 const mates = m.querySelector('.mode-mates')
 const seen = e => { let v = cut(box(e), box(m)); if (v && mates && mates.contains(e)) v = cut(v, box(mates)); return v }  // the part not scrolled away
 const rows = [...m.querySelectorAll('[data-slot=dropdown-menu-item], [data-slot=dropdown-menu-label], .mode-find-row, .mode-none')].map(e => ({ e, r: box(e), v: seen(e) })).filter(x => x.v)
 const clash = [], spill = [], texts = []
 rows.forEach((a, i) => rows.slice(i + 1).forEach(b => hit(a.v, b.v) && clash.push(say(a.e) + ' over ' + say(b.e))))
 rows.forEach(({ e, r, v }) => { const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT); let n
  while ((n = w.nextNode())) { if (!n.data.trim()) continue; const g = document.createRange(); g.selectNodeContents(n)
   for (const t of g.getClientRects()) { if (!t.width) continue
    if (t.left < r.left - 1 || t.right > r.right + 1 || t.top < r.top - 1 || t.bottom > r.bottom + 1) spill.push(n.data.trim().slice(0, 24) + ' out of ' + say(e))
    const tv = cut(t, v); if (tv) texts.push({ n, t: tv }) } } })
 texts.forEach((a, i) => texts.slice(i + 1).forEach(b => a.n !== b.n && hit(a.t, b.t) && clash.push('"' + a.n.data.trim().slice(0, 20) + '" on "' + b.n.data.trim().slice(0, 20) + '"')))
 const clipped = [m, ...m.querySelectorAll('*')].filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible').map(say)
 const items = [...m.querySelectorAll('[data-slot=dropdown-menu-item], .mode-advanced, .mode-find-row')].filter(e => seen(e))
 const lefts = items.map(e => (b => b.left + b.width / 2)(box(e.firstElementChild))), titles = items.filter(e => !e.matches('.mode-find-row')).map(e => {
  const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) if (n.data.trim()) { const g = document.createRange(); g.selectNodeContents(n); const t = g.getClientRects()[0]; if (t && t.width) return t.left } return null })
 const checks = [...m.querySelectorAll('.mode-check, .mode-advanced [role=switch]')].filter(e => seen(e)).map(e => box(e).right)
 const spread = v => v.length ? Math.max(...v) - Math.min(...v) : 0
 const c = document.querySelector(chip), pill = box(c), comp = box(c.closest('.composer')), bound = box(c.closest('.ai-sidebar, .page-column')), r = box(m)
 const chrome = Math.max(0, ...[...document.querySelectorAll('.window-bar, .top-tab-strip')].map(box).filter(b => b.height).map(b => b.bottom))
 const list = mates && { rows: mates.children.length, full: [...mates.children].filter(e => box(e).top >= box(mates).top - .5 && box(e).bottom <= box(mates).bottom + .5).length, scrolls: mates.scrollHeight > mates.clientHeight + 1 }
 const sw = m.querySelector('.mode-advanced [role=switch]')
 return { clash, spill, clipped, icons: spread(lefts), titles: spread(titles.filter(v => v != null)), checks: spread(checks), list,
  modes: [...m.querySelectorAll('.mode-item')].map(e => e.innerText.split('\n')[0]), advanced: sw?.getAttribute('aria-checked'), switchAt: sw && box(sw).top,
  at: { l: r.left, t: r.top, r: r.right, b: r.bottom, pill: pill.right, boxTop: comp.top, bl: bound.left, br: bound.right, bt: bound.top, chrome, scrolls: m.scrollHeight > m.clientHeight + 1 } } })"""


def check(ok, name):
    if ok:
        PASSES[0] += 1
    else:
        FAILS.append(f"[{GROUP[0]}] {name}")
    print(("PASS " if ok else "FAIL ") + f"[{GROUP[0]}] {name}", flush=True)


def q(v):
    return json.dumps(v)


def escape(p):
    js(p, "document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    until(lambda: not js(p, "!!document.querySelector('.mode-menu')"), 3)
    time.sleep(.15)


def measure(p, chip):
    return until(lambda: js(p, f"{GEOM}({q(chip)})"), 4)


def rows_ok(name, g):
    check(not g["clash"] and not g["spill"] and not g["clipped"], f"{name}: no rows or text overlap, nothing runs out of its row or is cut off ({g['clash'][:4]} {g['spill'][:4]} {g['clipped'][:4]})")


def shot(p, name, chip):
    if not SHOTS:
        return
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / f"modemenu-{'mac' if MAC else 'windows'}-{name}.png"
    if MAC:
        reply = rpc(p, "capture", name=out.name, scale=2)
        if isinstance(reply, dict) and reply.get("path"):
            shutil.copy(reply["path"], out)
        return
    a = js(p, f"""(() => {{ const m = document.querySelector('.mode-menu').getBoundingClientRect(), b = document.querySelector({q(chip)}).closest('.composer').getBoundingClientRect()
     const l = Math.max(0, Math.min(m.left, b.left) - 16), t = Math.max(0, m.top - 16); return {{ x: l, y: t, width: Math.min(innerWidth, Math.max(m.right, b.right) + 16) - l, height: Math.min(innerHeight, b.bottom + 16) - t, scale: 1 }} }})()""")
    data = rpc(p, "shellCdp", method="Page.captureScreenshot", parameters={"format": "png", "clip": a})
    if isinstance(data, dict) and data.get("data"):
        out.write_bytes(base64.b64decode(data["data"]))


def place(p, name, chip, companions, file):
    escape(p)
    if not js(p, f"""(() => {{ const e = document.querySelector({q(chip)}); if (!e) return false
     e.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, cancelable: true, button: 0, pointerType: 'mouse' }})); return true }})()"""):
        check(False, f"{name}: the pill is there")
        return
    g = measure(p, chip)
    if not g:
        check(False, f"{name}: the menu opens")
        return
    rows_ok(name, g)
    a = g["at"]
    fits = a["pill"] <= a["br"] - 8 + .5 and a["pill"] - (a["r"] - a["l"]) >= a["bl"] + 8 - .5
    check(0 <= a["boxTop"] - a["b"] <= 12 and a["l"] >= a["bl"] + 8 - .5 and a["r"] <= a["br"] - 8 + .5 and (abs(a["r"] - a["pill"]) <= 1 or not fits),
          f"{name}: opens upward just above the box, its right edge on the pill's, inside its panel or page (gap {a['boxTop'] - a['b']:.0f}, right {a['r']:.0f} vs pill {a['pill']:.0f}, in {a['bl']:.0f}-{a['br']:.0f})")
    check(a["t"] >= max(a["bt"], a["chrome"]) + 8 - .5, f"{name}: never over the tab strip or address bar (top {a['t']:.0f}, chrome ends {a['chrome']:.0f}, area {a['bt']:.0f}){', scrolls inside' if a['scrolls'] else ''}")
    check(g["icons"] <= 1 and g["titles"] <= 1 and g["checks"] <= 1, f"{name}: one row style, icons, titles and checks each in one column (spread {g['icons']:.1f}, {g['titles']:.1f}, {g['checks']:.1f})")
    check(g["modes"][:3] == ["Quick", "Everyday", "Thorough"], f"{name}: Quick, Everyday and Thorough with Advanced off ({g['modes']})")
    if companions:
        lst = g["list"] or {}
        check(lst.get("rows") == 8 and lst.get("full") == 6 and lst.get("scrolls"), f"{name}: six of the eight companions before the list scrolls ({lst})")
        js(p, """(e => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, 'o'); e.dispatchEvent(new Event('input', { bubbles: true })) })(document.querySelector('.mode-find'))""")
        few = until(lambda: (lambda x: x if x and x["list"] and x["list"]["rows"] < 8 else None)(js(p, f"{GEOM}({q(chip)})")), 4) or {}
        lst = few.get("list") or {}
        check(0 < lst.get("rows", 0) <= 6 and lst.get("full") == lst.get("rows") and not lst.get("scrolls"), f"{name}: with six or fewer it doesn't scroll ({lst})")
        if few:
            rows_ok(name + ", found by name", few)
        js(p, """(e => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, ''); e.dispatchEvent(new Event('input', { bubbles: true })) })(document.querySelector('.mode-find'))""")
        until(lambda: ((js(p, f"{GEOM}({q(chip)})") or {}).get("list") or {}).get("rows") == 8, 4)
    shot(p, file, chip)
    # Advanced from its own switch, with the menu open: the modes go, the switch stays put; off brings them back.
    before = g["switchAt"]
    js(p, "document.querySelector('.mode-menu .mode-advanced [role=switch]')?.click()")
    on = until(lambda: (lambda x: x if x and x["advanced"] == "true" else None)(js(p, f"{GEOM}({q(chip)})")), 5) or {}
    check(on and not any(w in m for m in on["modes"] for w in ("Quick", "Everyday", "Thorough")) and abs((on.get("switchAt") or 0) - (before or 0)) <= 1,
          f"{name}: Advanced on hides Quick, Everyday and Thorough and keeps its switch in place ({on.get('modes')}, switch {before} -> {on.get('switchAt')})")
    if on:
        rows_ok(name + ", Advanced on", on)
        shot(p, file + "-advanced", chip)
    js(p, "document.querySelector('.mode-menu .mode-advanced [role=switch]')?.click()")
    off = until(lambda: (lambda x: x if x and x["advanced"] == "false" and len(x["modes"]) == 6 else None)(js(p, f"{GEOM}({q(chip)})")), 5) or {}
    check(off.get("modes", [])[:3] == ["Quick", "Everyday", "Thorough"], f"{name}: Advanced off brings them back ({off.get('modes')})")
    escape(p)


def main():
    (RUN / "bin").mkdir(parents=True)
    (RUN / "bin" / "fake_agent.py").write_text(FAKE)
    launcher(RUN / "bin" / "fakeagent", RUN / "bin" / "fake_agent.py")
    profile = RUN / "profile"
    (profile / "agents").mkdir(parents=True)
    (profile / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(RUN / "bin" / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run"], "model": ["--model", "{model}"], "models": ["fast-1", "big-2"],
        "effort": ["--effort", "{effort}"], "output": "stream-json"}))
    crew = CREW + [{"Id": i.lower(), "Name": i, "Job": "A helper."} for i in ("Tomas", "Ines", "Kofi", "Lena")]
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False,
        "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake", "Width": 1280, "Height": 800},
        "Tabs": [{"Id": "home", "Title": "New tab", "Url": ""}], "ActiveId": "home"}))
    p = launch(EXE, profile)
    try:
        # A chat with a reply, opened as a full chat tab.
        send(p, "aiToggle")
        until(lambda: js(p, "!!document.querySelector('.ai-sidebar [aria-label=Message]')"), 30)
        send(p, "aiSend", text="hello")
        GROUP[0] = "setup"
        check(bool(until(lambda: js(p, "!!document.querySelector('.ai-sidebar .ai-actions button')"), 30)), "The fake reply arrives")
        js(p, "document.querySelector(\".ai-sidebar .ai-head button[aria-label='Open as a tab']\")?.click()")
        chat = ".chat-view[data-mode=tab] .mode-chip"
        check(bool(until(lambda: js(p, f"!!document.querySelector({q(chat)})"), 10)), "The chat opens as a full chat tab")
        tab = rpc(p).get("activeId") or next((t.get("Id") for t in rpc(p).get("tabs", []) if t.get("ChatId")), None)
        base = js(p, "[innerWidth, innerHeight, devicePixelRatio]")
        print("Window", base, flush=True)
        for scale in ((base[2],) if MAC else (1, 1.5)):
            for width in ("full", "narrow"):
                if not MAC:
                    w = 720 if width == "narrow" else round(base[0] * base[2] / scale)
                    rpc(p, "shellCdp", method="Emulation.setDeviceMetricsOverride", parameters={"width": w, "height": round(base[1] * base[2] / scale), "deviceScaleFactor": scale, "mobile": False})
                    time.sleep(.6)
                for theme in ("Light", "Dark"):
                    GROUP[0] = f"{scale * 100:.0f}% {width} {theme}"
                    file = f"{theme.lower()}-{scale * 100:.0f}-{width}"
                    send(p, "preference", key="theme", value=theme)
                    until(lambda: js(p, "document.documentElement.classList.contains('dark')") == (theme == "Dark"), 5)
                    send(p, "select", id=tab)
                    if until(lambda: js(p, f"!!document.querySelector({q(chat)})"), 8):
                        time.sleep(.3)
                        place(p, "Full chat", chat, False, "chat-" + file)
                    else:
                        check(False, "Full chat: back on the chat tab")
                    send(p, "new")
                    if until(lambda: js(p, "!!document.querySelector('.home-compose .mode-chip')"), 10):
                        time.sleep(.4)
                        place(p, "New tab", ".home-compose .mode-chip", True, "newtab-" + file)
                    else:
                        check(False, "New tab: the page opens")
                    if not js(p, "!!document.querySelector('.ai-sidebar')"):
                        send(p, "aiToggle")
                    send(p, "aiNew")
                    if until(lambda: js(p, "!!document.querySelector('.ai-sidebar .ai-hello') && !!document.querySelector('.ai-sidebar .mode-chip')"), 10):
                        js(p, f"document.querySelector('.ai-sidebar').style.width = {q('320px' if width == 'narrow' else '')}")
                        time.sleep(.4)
                        place(p, "Side chat", ".ai-sidebar .mode-chip", True, "side-" + file)
                        js(p, "document.querySelector('.ai-sidebar').style.width = ''")
                    else:
                        check(False, "Side chat: a new chat opens")
                    send(p, "aiToggle")
                    until(lambda: not js(p, "!!document.querySelector('.ai-sidebar')"), 5)
                    new = rpc(p).get("activeId")
                    if new and new != tab:
                        send(p, "closeTab", id=new)
                        time.sleep(.3)
        if not MAC:
            rpc(p, "shellCdp", method="Emulation.clearDeviceMetricsOverride", parameters={})
    finally:
        rpc(p, "quit")
        until(lambda: p.poll() is not None, 15)
    print(f"\n{PASSES[0]} passed {len(FAILS)} failed")
    for f in FAILS:
        print("  " + f)
    shutil.rmtree(RUN, ignore_errors=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
