"""Nothing of a companion may touch the edge of its box: every look at chat, header, pill, tab and picker sizes, still and
through every frame of every move, on a flat background. A non-background pixel on a box's outer pixel ring fails it.
Also checks the Blender avatar files (still-ui/src/assets/avatar): nothing on their outer pixel ring, the visible body
(alpha 8 and up) at least 10% from every side, and that they're the 2D ones (a dark outline round the body); and that
chat sizes (48px and under) are 2D, bigger ones live 3D. And the places people meet them, at their sizes (places()); the
Blender companions' every clip, ten frames a second, at the Companions page's corner size.

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
# look.ts: ROLE_LOOKS, BLANK, AGENT_LOOKS, plus a look of your own
LOOKS = [{"color": "#f7a26a", "shape": "tall", "prop": "chart"}, {"color": "#f2a5c4", "shape": "gumdrop", "prop": "badge"},
         {"color": "#a6cf9c", "shape": "block", "prop": "clipboard"}, {"color": "#f6d56a", "shape": "round", "prop": "megaphone"},
         {"color": "#86d0c8", "shape": "squat", "prop": "headset"}, {"color": "#8cc3ee", "shape": "bump", "prop": "laptop"},
         {"color": "#c0a3ec", "shape": "lean", "prop": "magnifier"}, {"color": "#ddd4c6", "shape": "bean", "prop": ""},
         {"color": "#e6896b", "shape": "bean", "prop": ""}, {"color": "#10a37f", "shape": "round", "prop": ""},
         {"color": "#2b2b2b", "shape": "block", "prop": ""}, {"color": "#d7a8ff", "shape": "gumdrop", "prop": "", "accessory": "bow"}]
SMALL = (16, 20, 24, 30, 32, 40, 48)  # 2D (Mascot.tsx FLAT): tabs, menus, the header, chat turns, the working pill
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


# The body's box in each companion canvas (opaque pixels: the shadow is fainter), in CSS px, against its art's box.
BODY = """(sel, box) => [...document.querySelectorAll(sel)].map(m => { const c = m.querySelector('canvas[data-live]'), r = m.getBoundingClientRect()
 const art = (box ? m.closest(box) : m).getBoundingClientRect(), o = { size: Math.round(r.width), art: Math.round(art.height), inside: r.left >= art.left - 1 && r.right <= art.right + 1 }
 if (!c) return o
 const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, k = r.width / c.width; let t = 1e9, b = -1
 for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) if (d[(y * c.width + x) * 4 + 3] > 200) { t = Math.min(t, y); b = Math.max(b, y) }
 return { ...o, body: Math.round((b - t + 1) * k), share: +((b - t + 1) * k / art.height).toFixed(2) } })"""


def places():
    """Where people meet them, at the brief's sizes: a chat turn's companion at least 40px; the Companions page's, in its
    card's corner, at least 96px, whole (nothing clips it) with room round it; home's space with the companion at 35-45%
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
        check(me and .35 <= me[0].get("body", 0) / view <= .45 and team == len(crew) - 1,
              f"Home's space: the companion is {me and me[0].get('body', 0) / view:.0%} of the view's height, {team} teammates behind")
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
places()
profile = ROOT / "artifacts" / ("avatars-" + uuid.uuid4().hex[:8]) / "profile"
profile.mkdir(parents=True)
(profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Width": 1400, "Height": 900},
    "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
process = launch(EXE, profile)
try:
    reel(process, 168)
    until(lambda: js(process, "!!document.querySelector('.mascot-reel canvas[data-live]')"), 30)
    chunk = js(process, "performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('companion3d'))")
    js(process, f"import({json.dumps(chunk)}).then(m => {{ window.__clips = m.DUR }})")
    until(lambda: js(process, "!!window.__clips"), 10)
    for size in SMALL:
        frames(process, profile, size, live=False)
    for size in BIG:
        frames(process, profile, size, live=True, rig=size == 112)
finally:
    rpc(process, "quit")
    process.wait(timeout=20)
print(f"{sum(RESULT)}/{len(RESULT)} passed")
sys.exit(0 if all(RESULT) else 1)
