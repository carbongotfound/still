"""Nothing of a companion may touch the edge of its box: every look at chat, header, pill, tab and picker sizes, still and
through every frame of every move, on a flat background. A non-background pixel on a box's outer pixel ring fails it.
Also checks the Blender avatar files (still-ui/src/assets/avatar): nothing on their outer pixel ring, the visible body
(alpha 8 and up) at least 10% from every side, and that they're the 2D ones (a dark outline round the body); and that
chat sizes (48px and under) are 2D, bigger ones live 3D. And the places people meet them, at their sizes (places()); the
Blender companions' every clip, ten frames a second, at the Companions page's corner size. Under 40px a head
(head_files(), heads()): the tier by size, the head at 85 to 90% of the box, sharper files when scaled, the initial if it fails.

Run: python tests/desktop/avatars.py artifacts/Still-QA/Still.exe
"""
import json
from pathlib import Path
import struct
import sys
import time
import uuid

from PIL import Image, ImageChops, ImageFilter, ImageStat

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = sys.argv[1]
PAPER = (246, 243, 238)
# look.ts: ROLE_LOOKS (no props), BLANK, AGENT_LOOKS, plus looks of your own with props
LOOKS = [{"color": "#f7a26a", "shape": "tall", "prop": ""}, {"color": "#f2a5c4", "shape": "gumdrop", "prop": ""},
         {"color": "#a6cf9c", "shape": "block", "prop": ""}, {"color": "#f6d56a", "shape": "round", "prop": ""},
         {"color": "#86d0c8", "shape": "squat", "prop": "headphones"}, {"color": "#8cc3ee", "shape": "bump", "prop": ""},
         {"color": "#c0a3ec", "shape": "lean", "prop": ""}, {"color": "#ddd4c6", "shape": "bean", "prop": ""},
         {"color": "#f39079", "shape": "tall", "prop": "mug"}, {"color": "#93d6bd", "shape": "bean", "prop": "laptop"},
         {"color": "#e6896b", "shape": "bean", "prop": ""}, {"color": "#10a37f", "shape": "round", "prop": ""},
         {"color": "#2b2b2b", "shape": "block", "prop": ""}, {"color": "#d7a8ff", "shape": "gumdrop", "prop": "", "accessory": "bow"}]
SMALL = (40, 48)  # 2D whole bodies (Mascot.tsx FLAT): chat turns; under 40px a head (heads())
BIG = (56, 112, 260)          # the picker, the Companions page's corner, card art (every Blender clip at 112)
STATES = ("idle", "listening", "thinking", "working", "needs", "done", "error", "talking", "pointing")  # Mascot.tsx STATES
RESULT = []


def check(ok, name):
    RESULT.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def rim(im):
    """How light the body's outermost pixels are (median, 0-1): a 2D one's are its dark outline."""
    m = im.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    return ImageStat.Stat(im.convert("L"), ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(3)))).median[0] / 255


def files():
    for png in sorted((ROOT / "still-ui" / "src" / "assets" / "avatar").glob("*.png")):
        a = Image.open(png).getchannel("A")
        any_ = a.point(lambda v: 255 if v > 0 else 0).getbbox()
        body = a.point(lambda v: 255 if v >= 8 else 0).getbbox()
        edge = min(any_[0], any_[1], a.width - any_[2], a.height - any_[3])
        clear = min(body[0], body[1], a.width - body[2], a.height - body[3]) / a.width
        check(edge > 0 and clear >= .1, f"{png.name}: {clear:.1%} clear around the body, nearest drawn pixel {edge}px from the edge")
        check(rim(Image.open(png).convert("RGBA")) < .35, f"{png.name}: 2D, outlined")
    for strip in sorted((ROOT / "still-ui" / "src" / "assets" / "sprite").glob("*/*.webp")):  # every frame of the rigs' strips
        a = Image.open(strip).getchannel("A")
        rows = json.loads((strip.parent / (strip.parent.name + ".json")).read_text())[strip.stem.split("-", 1)[1]].get("rows", 1)
        px = a.height // rows  # a long clip goes on more rows (rig/sprites.py)
        n, worst, edge = a.width // px * rows, 1.0, px
        for i in range(n):
            x, y = i % (a.width // px) * px, i // (a.width // px) * px
            f = a.crop((x, y, x + px, y + px))
            any_, body = f.point(lambda v: 255 if v > 0 else 0).getbbox(), f.point(lambda v: 255 if v >= 8 else 0).getbbox()
            edge = min(edge, any_[0], any_[1], f.width - any_[2], f.height - any_[3])
            worst = min(worst, min(body[0], body[1], f.width - body[2], f.height - body[3]) / f.width)
        check(edge > 0 and worst >= .1, f"{strip.name}: {n} frames, at least {worst:.1%} clear around the body, nearest drawn pixel {edge}px from the edge")
        check(rim(Image.open(strip).convert("RGBA")) < .35, f"{strip.name}: 2D, outlined")


CANVAS_RING = """JSON.stringify([...document.querySelectorAll('.mascot-reel .mascot')].map((m, i) => {
  const c = m.querySelector('canvas[data-live]'); if (!c) return i
  const w = c.width, h = c.height, a = c.getContext('2d').getImageData(0, 0, w, h).data, on = (x, y) => a[(y * w + x) * 4 + 3] > 0
  for (let x = 0; x < w; x++) if (on(x, 0) || on(x, h - 1)) return i
  for (let y = 0; y < h; y++) if (on(0, y) || on(w - 1, y)) return i
  return -1 }).filter(i => i >= 0))"""


def touching(process, profile, n, live=False):
    """The boxes with a drawn pixel on their outer ring: read from a live companion's own canvas (alpha above 0, or
    not live at all), and for pictures from a screenshot of the page (anything but plain paper)."""
    if live:
        return json.loads(js(process, CANVAS_RING))
    rpc(process, "capture", name="edge.png")
    shot = Image.open(profile / "edge.png").convert("RGB")
    boxes = json.loads(js(process, "JSON.stringify([innerWidth, ...[...document.querySelectorAll('.mascot-reel .mascot')].map(m => (r => [r.x, r.y, r.width, r.height])(m.getBoundingClientRect()))])"))
    k, bad = shot.width / boxes[0], []
    px = shot.load()
    for i, (x, y, w, h) in enumerate(boxes[1:n + 1]):
        x0, y0, x1, y1 = round(x * k), round(y * k), round((x + w) * k) - 1, round((y + h) * k) - 1
        ring = [(u, y0) for u in range(x0, x1 + 1)] + [(u, y1) for u in range(x0, x1 + 1)] + [(x0, v) for v in range(y0, y1 + 1)] + [(x1, v) for v in range(y0, y1 + 1)]
        if any(max(abs(a - b) for a, b in zip(px[p], PAPER)) > 10 for p in ring):
            bad.append(i)
    return bad


def reel(process, size, state="idle", gesture=""):
    js(process, "document.dispatchEvent(new CustomEvent('still-mascot-reel', { detail: %s }))" % json.dumps({"state": state, "gesture": gesture, "size": size, "looks": LOOKS}))
    js(process, "chrome.webview.postMessage({ op: 'bounds', x: 0, y: 0, width: 1, height: 1, viewportWidth: innerWidth })")  # the page's view out of the way
    js(process, "(() => { const r = document.querySelector('.mascot-reel'), c = 'rgb%s'; document.documentElement.style.background = document.body.style.background = c; Object.assign(r.style, { display: 'flex', flexWrap: 'wrap', gap: '24px', padding: '24px', background: c }) })()" % (PAPER,))


def rig_clips():
    """The Blender companions' own clips (every rig ships the same set), name: seconds, from a glb's animations."""
    b = (ROOT / "still-ui" / "src" / "assets" / "rig" / "jonah.glb").read_bytes()
    g = json.loads(b[20:20 + struct.unpack_from("<I", b, 12)[0]])
    return {a["name"]: max(g["accessors"][s["input"]]["max"][0] for s in a["samplers"]) for a in g["animations"]}


def frames(process, profile, size, live, rig=False):
    """Every look in every state and gesture at one size; live ones are posed through each move by the frozen clock.
    rig: every Blender clip too, played by name (a look without it stays idle), ten frames a second."""
    clips = json.loads(js(process, "JSON.stringify(window.__clips)"))
    own = {n: d for n, d in rig_clips().items() if rig and not n.startswith("pose.") and n not in ("idle_a", "thinking", "working", "drop_in")}
    reel(process, size)
    flat = lambda: json.loads(js(process, "JSON.stringify([...document.querySelectorAll('.mascot-reel .mascot')].map(m => [m.classList.contains('is-flat'), !!m.querySelector('canvas[data-live]')]))"))
    if live:
        until(lambda: all(c for _, c in flat()), 30)
    k = flat()
    check(len(k) == len(LOOKS) and all(f != live and c == live for f, c in k), f"{size}px: every look {'live 3D' if live else '2D, not live'}")
    moves = [(s, "") for s in STATES] + ([("idle", g) for g in clips] if live else []) + [("idle", n) for n in own]
    for state, gesture in moves:
        reel(process, size, state, gesture)
        time.sleep(.8)
        if live:
            seconds = clips.get(gesture, 4)  # a gesture plays once; the loops are four seconds
            times = [round(seconds * i / 12, 3) for i in range(13)] if gesture not in own else [i / 10 for i in range(int(own[gesture] * 10) + 1)]
            if gesture == "drop":  # it falls in from above the frame on purpose (companion3d.ts); every companion lands by .55 s
                times = [t for t in times if t >= .6]
        else:
            times = [None] if state not in ("working", "thinking") else [i / 8 for i in range(8)]  # the small avatars' bob
        bad = set()
        for t in times:
            if live:
                js(process, f"document.documentElement.dataset.mascotFreeze = '{t}'")
                time.sleep(.12)
            elif t is not None:
                js(process, f"document.getAnimations().forEach(a => {{ a.pause(); a.currentTime = {t} * 1400 }})")
                time.sleep(.05)
            bad.update(touching(process, profile, len(LOOKS), live))
        if not live:
            js(process, "document.getAnimations().forEach(a => a.play())")
        what = gesture or state
        check(not bad, f"{size}px {what}: {len(times)} frame{'s' * (len(times) > 1)} clear of the edge" + (f" (touching: looks {sorted(bad)})" if bad else ""))

# Stage 11 head tiers (Mascot.tsx tierOf): the icon up to 20px, the portrait 21 to 39px, the whole body from 40px.
HEAD_SIZES = (16, 18, 20, 22, 24, 28, 32, 34, 40)
tier_of = lambda size: "icon" if size <= 20 else "portrait" if size <= 39 else "full"


def drawn(im):
    """The share of the box the drawn head takes (alpha 128 and up, the longer side), and whether its outer ring is clear."""
    a = im.getchannel("A")
    box = a.point(lambda v: 255 if v >= 128 else 0).getbbox()
    w, h = im.size
    ring = [a.getpixel((x, y)) for x in range(w) for y in (0, h - 1)] + [a.getpixel((x, y)) for y in range(h) for x in (0, w - 1)]
    return (max(box[2] - box[0], box[3] - box[1]) / w if box else 0), not any(ring)


def head_files():
    """The shipped heads (still-ui/src/assets/head): every rig's icon at 16, 20, 32, 40, 48 and 60px and portrait at 40, 80
    and 120px, the head at 85 to 90% of the box (from 40px up: at 20px a pixel is 5% of the box) and nothing on the outer
    ring."""
    pngs = sorted((ROOT / "still-ui" / "src" / "assets" / "head").glob("*.png"))
    check(len(pngs) == 72, f"{len(pngs)} head files: 8 rigs, the icon at six sizes and the portrait at three")
    for png in pngs:
        share, clear = drawn(Image.open(png).convert("RGBA"))
        px = int(png.stem.rsplit("-", 1)[1])
        ok = clear and (px < 40 or .85 <= share <= .90)
        check(ok, f"{png.name}: the head takes {share:.0%} of the box, outer ring {'clear' if clear else 'TOUCHED'}")


SHARE = """JSON.stringify([...document.querySelectorAll('.mascot-reel .mascot')].map(m => { const i = m.querySelector('img')
 const w = i?.srcset ? +(i.srcset.split(', ').find(s => new URL(s.split(' ')[0], location.href).href === i.currentSrc) || ' 0w').split(' ').pop().slice(0, -1) : 0
 const o = { tier: m.dataset.tier || 'full', img: !!i, ok: !!i && i.complete && i.naturalWidth > 0, set: !!i?.srcset, w, src: (i?.currentSrc || '').split('/').pop().slice(0, 40), initial: !!m.querySelector('.mascot-initial') }
 if (!o.ok || o.set) return o
 const c = document.createElement('canvas'); c.width = i.naturalWidth; c.height = i.naturalHeight; const g = c.getContext('2d'); g.drawImage(i, 0, 0)
 const d = g.getImageData(0, 0, c.width, c.height).data; let l = 1e9, t = 1e9, r = -1, b = -1, edge = false
 for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) { const a = d[(y * c.width + x) * 4 + 3]; if (a >= 128) { l = Math.min(l, x); r = Math.max(r, x); t = Math.min(t, y); b = Math.max(b, y) } if (a && (x === 0 || y === 0 || x === c.width - 1 || y === c.height - 1)) edge = true }
 return { ...o, px: c.width, share: r < 0 ? 0 : +(Math.max(r - l + 1, b - t + 1) / c.width).toFixed(3), edge } }))"""


def heads(process, profile, out):
    """Every look, the shipped rigs and looks of your own (three made at random), at every size from 16 to 40px: the tier
    by size, a picture for each (a look of your own is drawn on demand with the head frame), the head at 85 to 90% of the
    box, nothing touching the box on screen; at 150% and 200% scale the sharper files; a picture that fails shows the
    initial on the companion's color. Light and dark sheets for review go to out."""
    import random
    seed = random.randrange(1 << 16)
    rnd = random.Random(seed)
    shapes, props, extras = ["bean", "tall", "gumdrop", "block", "round", "squat", "bump", "lean"], ["", "laptop", "mug", "headphones", "notebook", "phone", "camera"], ["", "glasses", "bow", "sprout", "flower"]
    mine = [{"color": "#%02x%02x%02x" % tuple(rnd.randrange(40, 240) for _ in range(3)), "shape": rnd.choice(shapes), "prop": rnd.choice(props), "accessory": rnd.choice(extras)} for _ in range(3)]
    print(f"Random looks (seed {seed}): {json.dumps(mine)}")
    looks = LOOKS + mine
    def show(size):
        js(process, "document.dispatchEvent(new CustomEvent('still-mascot-reel', { detail: %s }))" % json.dumps({"size": size, "looks": looks}))
        js(process, "window.chrome?.webview?.postMessage({ op: 'bounds', x: 0, y: 0, width: 1, height: 1, viewportWidth: innerWidth }) ?? 1")  # the page's view out of the way
    for size in HEAD_SIZES:
        show(size)
        js(process, "(() => { const r = document.querySelector('.mascot-reel'); document.documentElement.style.background = document.body.style.background = 'rgb%s'; Object.assign(r.style, { display: 'flex', flexWrap: 'wrap', gap: '24px', padding: '24px' }); return 1 })()" % (PAPER,))
        want = tier_of(size)
        got = lambda: json.loads(js(process, SHARE) or "[]")
        until(lambda: len(got()) == len(looks) and all(g["ok"] or want == "full" for g in got()), 30)
        k = got()
        check(len(k) == len(looks) and all(g["tier"] == want for g in k), f"{size}px: every look at the {want} tier")
        if want != "full":
            check(all(g["ok"] for g in k), f"{size}px: every look has its picture ({sum(g['ok'] for g in k)}/{len(k)})")
            own = [g for g in k if not g["set"]]
            check(own and all(.85 <= g["share"] <= .90 and not g["edge"] for g in own),
                  f"{size}px: looks drawn on demand ({len(own)}) take {min((g['share'] for g in own), default=0):.0%} to {max((g['share'] for g in own), default=0):.0%} of the box, clear of its edge")
        bad = touching(process, profile, len(looks))
        check(not bad, f"{size}px: nothing touches the box on screen" + (f" (looks {bad})" if bad else ""))
    # The review sheets: every look at every head size, light and dark.
    for dark in (False, True):
        js(process, """(() => { const root = document.getElementById('root'); document.documentElement.classList.toggle('dark', %s); const bg = %s
          document.documentElement.style.background = document.body.style.background = bg; return 1 })()""" % ("true" if dark else "false", json.dumps("#1c1c1e" if dark else "#ffffff")))
        for size in (16, 20, 24, 32):
            show(size)
            until(lambda: all(g["ok"] for g in json.loads(js(process, SHARE) or "[]")), 20)
            js(process, "Object.assign(document.querySelector('.mascot-reel').style, { display: 'flex', flexWrap: 'wrap', gap: '14px', padding: '20px' })")
            time.sleep(.3)
            rpc(process, "capture", name=f"heads-{'dark' if dark else 'light'}-{size}.png")
    js(process, "document.documentElement.classList.remove('dark')")
    # At 150% and 200% scale (Windows only: the shell's DevTools), the browser takes a file at least as sharp as the screen.
    if sys.platform == "win32":
        for scale in (1.5, 2):
            rpc(process, "shellCdp", method="Emulation.setDeviceMetricsOverride", parameters={"width": 0, "height": 0, "deviceScaleFactor": scale, "mobile": False})
            for size in (20, 32):
                show(size)
                until(lambda: all(g["ok"] for g in json.loads(js(process, SHARE) or "[]")), 20)
                k = [g for g in json.loads(js(process, SHARE) or "[]") if g["set"]]
                dpr = js(process, "devicePixelRatio")
                check(dpr == scale and k and all(g["w"] >= size * scale for g in k), f"At {scale:.0%} scale, {size}px heads use the sharper files ({k[0]['w'] if k else 'none'}w)")
                rpc(process, "capture", name=f"heads-{int(scale * 100)}-{size}.png")
        rpc(process, "shellCdp", method="Emulation.clearDeviceMetricsOverride", parameters={})
    # A picture that fails: the initial on the companion's color.
    show(24)
    until(lambda: all(g["ok"] for g in json.loads(js(process, SHARE) or "[]")), 20)
    js(process, "document.querySelector('.mascot-reel .mascot img').dispatchEvent(new Event('error'))")
    initial = until(lambda: js(process, "(() => { const i = document.querySelector('.mascot-reel .mascot .mascot-initial'); return i ? getComputedStyle(i).backgroundColor : '' })()"), 5)
    check(initial == "rgb(247, 162, 106)", f"A picture that fails shows the initial on the companion's color ({initial})")
    for f in profile.glob("heads-*.png"):
        f.replace(out / f.name)


# The body's box in each companion canvas (opaque pixels: the shadow is fainter), in CSS px, against its art's box.
BODY = """(sel, box) => [...document.querySelectorAll(sel)].map(m => { const c = m.querySelector('canvas[data-live]'), r = m.getBoundingClientRect()
 const art = (box ? m.closest(box) : m).getBoundingClientRect(), o = { size: Math.round(r.width), art: Math.round(art.height), inside: r.left >= art.left - 1 && r.right <= art.right + 1 }
 if (!c) return o
 const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, k = r.width / c.width; let t = 1e9, b = -1
 for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) if (d[(y * c.width + x) * 4 + 3] > 200) { t = Math.min(t, y); b = Math.max(b, y) }
 return { ...o, body: Math.round((b - t + 1) * k), share: +((b - t + 1) * k / art.height).toFixed(2) } })"""


def places():
    """Where people meet them, at the brief's sizes: a chat turn's companion at least 40px; the Companions page's, in its
    card's corner, at least 96px, whole (nothing clips it) with room round it; home's space with the companion at 15-25%
    of the view's height and the rest of the team behind it."""
    profile = ROOT / "artifacts" / ("avatars-" + uuid.uuid4().hex[:8]) / "profile"
    (profile / "ai").mkdir(parents=True)
    roles = {"jonah": "sales", "maya": "research", "nora": "planner"}
    crew = [{**c, "Crew": roles[c["Id"]]} for c in CREW if c["Id"] in roles]
    chat = {"Id": "lamp", "Title": "A desk lamp", "Harness": "claude", "Started": True, "Companion": "jonah", "Updated": "2026-10-01T10:00:00Z",
            "Messages": [{"Role": "user", "Text": "Find me a desk lamp."}, {"Role": "assistant", "Text": "Warm light, no glare, fair price.", "Who": "jonah"}]}
    (profile / "ai" / "chats.json").write_text(json.dumps([chat]))
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AiHarness": "claude", "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, profile)
    body = lambda sel, box="": json.loads(js(p, f"JSON.stringify(({BODY})({json.dumps(sel)}, {json.dumps(box)}))") or "[]")
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.home-face canvas[data-live]')"), 30)
        time.sleep(1.5)
        view, me = js(p, "document.querySelector('.home-main').clientHeight"), body(".home-face .mascot")
        team = js(p, "document.querySelectorAll('.space-mate').length")
        check(me and .15 <= me[0].get("body", 0) / view <= .25 and team == len(crew) - 1,
              f"Home's space: the companion is {me and me[0].get('body', 0) / view:.0%} of the view's height, {team} teammates behind")
        # A teammate's body where the companion's picture overlaps it takes the pointer, and the picture's clear corner takes nothing
        hits = js(p, """(() => { const at = (x, y) => document.elementFromPoint(x, y)?.closest('button'), m = document.querySelector('.home-face').getBoundingClientRect()
            return [...document.querySelectorAll('.space-mate')].every(e => { const b = e.getBoundingClientRect(); return at(b.left + b.width * (b.left < m.left ? .7 : .3), b.top + b.height * .55) === e })
              && !at(m.left + m.width * .08, m.top + m.height * .1) })()""")
        check(hits, "Home's space: only a body takes the pointer, so a teammate behind the companion's picture still gets its click")
        js(p, "[...document.querySelectorAll('.home-chips button')].find(b => b.innerText.includes('Companions'))?.click()")
        until(lambda: js(p, "document.querySelectorAll('.mate-portrait canvas[data-live]').length") == len(crew), 20)
        time.sleep(1)
        corner = body(".mate-portrait .mascot", ".mate-portrait")
        whole = js(p, "[...document.querySelectorAll('.mate-portrait')].every(e => getComputedStyle(e).overflow === 'visible')")
        check(len(corner) == len(crew) and all(c["size"] >= 96 and c["inside"] and c["art"] - c["size"] >= 8 for c in corner) and whole,
              f"The Companions page's corner companion: {corner[0]['size'] if corner else 0}px, whole, with room round it")
        send(p, "chatOpen", id="lamp")
        until(lambda: js(p, "!!document.querySelector('.ai-turn-face .mascot')"), 15)
        turn = js(p, "Math.min(...[...document.querySelectorAll('.ai-turn-face .mascot')].map(m => m.getBoundingClientRect().width))")
        check(turn >= 40, f"A chat turn's companion: {turn}px")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)


files()
head_files()
places()
profile = ROOT / "artifacts" / ("avatars-" + uuid.uuid4().hex[:8]) / "profile"
profile.mkdir(parents=True)
(profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Width": 1400, "Height": 900},
    "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
process = launch(EXE, profile)
try:
    reel(process, 168)
    until(lambda: js(process, "!!document.querySelector('.mascot-reel canvas[data-live]')"), 30)
    chunk = js(process, "performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('companion3d'))")         or js(process, "new URL(%s, location.href).href" % json.dumps("assets/" + next((ROOT / "still" / "Shell" / "assets").glob("companion3d-*.js")).name))  # WKWebView lists no chunks
    js(process, f"import({json.dumps(chunk)}).then(m => {{ window.__clips = m.DUR }})")
    until(lambda: js(process, "!!window.__clips"), 10)
    heads(process, profile, profile.parent)
    for size in SMALL:
        frames(process, profile, size, live=False)
    for size in BIG:
        frames(process, profile, size, live=True, rig=size == 112)
finally:
    rpc(process, "quit")
    process.wait(timeout=20)
print(f"{sum(RESULT)}/{len(RESULT)} passed")
sys.exit(0 if all(RESULT) else 1)
