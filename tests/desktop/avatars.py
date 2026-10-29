"""Nothing of a companion may touch the edge of its box: every look at chat, header, pill, tab and picker sizes, still and
through every frame of every move, on a flat background. A non-background pixel on a box's outer pixel ring fails it.
Also checks the Blender avatar files (still-ui/src/assets/avatar): nothing on their outer pixel ring, and the visible body
(alpha 8 and up) at least 10% from every side.

Run: python tests/desktop/avatars.py artifacts/Still-QA/Still.exe
"""
import json
from pathlib import Path
import sys
import time
import uuid

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, rpc, until  # noqa: E402

EXE = sys.argv[1]
PAPER = (246, 243, 238)
# look.ts: ROLE_LOOKS, BLANK, AGENT_LOOKS, plus a look of your own
LOOKS = [{"color": "#f7a26a", "shape": "tall", "prop": "chart"}, {"color": "#f2a5c4", "shape": "gumdrop", "prop": "badge"},
         {"color": "#a6cf9c", "shape": "block", "prop": "clipboard"}, {"color": "#f6d56a", "shape": "round", "prop": "megaphone"},
         {"color": "#86d0c8", "shape": "squat", "prop": "headset"}, {"color": "#8cc3ee", "shape": "bump", "prop": "laptop"},
         {"color": "#c0a3ec", "shape": "lean", "prop": "magnifier"}, {"color": "#ddd4c6", "shape": "bean", "prop": ""},
         {"color": "#e6896b", "shape": "bean", "prop": ""}, {"color": "#10a37f", "shape": "round", "prop": ""},
         {"color": "#2b2b2b", "shape": "block", "prop": ""}, {"color": "#d7a8ff", "shape": "gumdrop", "prop": "", "accessory": "bow"}]
SMALL = (16, 20, 24, 30, 32)  # screenshots stay in the top 100px; tabs, menus, the header, chat turns, the working pill
BIG = (56, 120, 168)          # the picker and the home
STATES = ("idle", "listening", "thinking", "working", "needs", "done", "error", "talking", "pointing")  # Mascot.tsx STATES
RESULT = []


def check(ok, name):
    RESULT.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def files():
    for png in sorted((ROOT / "still-ui" / "src" / "assets" / "avatar").glob("*.png")):
        a = Image.open(png).getchannel("A")
        any_ = a.point(lambda v: 255 if v > 0 else 0).getbbox()
        body = a.point(lambda v: 255 if v >= 8 else 0).getbbox()
        edge = min(any_[0], any_[1], a.width - any_[2], a.height - any_[3])
        clear = min(body[0], body[1], a.width - body[2], a.height - body[3]) / a.width
        check(edge > 0 and clear >= .1, f"{png.name}: {clear:.1%} clear around the body, nearest drawn pixel {edge}px from the edge")


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
    js(process, "(() => { const r = document.querySelector('.mascot-reel'), c = 'rgb%s'; document.documentElement.style.background = document.body.style.background = c; Object.assign(r.style, { display: 'flex', flexWrap: 'wrap', gap: '24px', padding: '24px', background: c }) })()" % (PAPER,))


def frames(process, profile, size, live):
    """Every look in every state and gesture at one size; live ones are posed through each move by the frozen clock."""
    clips = json.loads(js(process, "JSON.stringify(window.__clips)"))
    moves = [(s, "") for s in STATES] + ([("idle", g) for g in clips] if live else [])
    for state, gesture in moves:
        reel(process, size, state, gesture)
        time.sleep(.8)
        if live:
            seconds = clips.get(gesture, 4)  # a gesture plays once; the loops are four seconds
            times = [round(seconds * i / 12, 3) for i in range(13)]
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


files()
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
        frames(process, profile, size, live=True)
finally:
    rpc(process, "quit")
    process.wait(timeout=20)
print(f"{sum(RESULT)}/{len(RESULT)} passed")
sys.exit(0 if all(RESULT) else 1)
