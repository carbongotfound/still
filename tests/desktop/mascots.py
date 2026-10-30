"""The companions in 3D: every sample look in every state, live, in light and dark (docs/agentic/compare/mascots-*.png).
  --gifs       one GIF per animation of the default look, posed frame by frame (docs/agentic/mascot/*.gif)
  --fallbacks  the default look's pictures drawn ahead, 3D and 2D (still-ui/src/assets/companion; rebuild the shell afterwards)
  --screens    the companions where people meet them, at the brief's sizes
Also: the Blender companions hold no prop, a companion saved holding its
role's old prop keeps its rig, and Make your own's props never go into the body or a nub.

Run: python tests/desktop/mascots.py artifacts/Still-QA/Still.exe [--gifs] [--fallbacks] [--screens]
"""
import base64
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = sys.argv[1]
OUT = ROOT / "docs" / "agentic" / "compare"
OUT.mkdir(parents=True, exist_ok=True)
LOOKS, STATES = 7, 9  # Mascot.tsx: SHEET_LOOKS and STATES
RESULT = []


def check(ok, name):
    RESULT.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def window(preferences=None, tab="about:blank"):
    profile = ROOT / "artifacts" / ("mascots-" + uuid.uuid4().hex[:8]) / "profile"
    profile.mkdir(parents=True)
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Width": 1260, "Height": 860, **(preferences or {})},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": tab}], "ActiveId": "home"}))
    return launch(EXE, profile), profile


def quit(process):
    rpc(process, "quit")
    process.wait(timeout=15)


def engine_loaded(process):
    if MAC:  # WebKit keeps no resource timing for still:// files: the app says what it served
        return any("companion3d" in f for f in rpc(process, "served")["files"])
    return js(process, "performance.getEntriesByType('resource').some(e => e.name.includes('companion3d'))")


def plain_window():
    """A window on a web page doesn't load three.js for the toolbar's small companion; once the chat opens, it draws."""
    process, _ = window({"AiHarness": "claude", "Companions": CREW}, "data:text/html,<title>Page</title><p>Page")
    try:
        time.sleep(4)
        check(engine_loaded(process) is False, "A plain window doesn't load three.js")
        send(process, "aiToggle")
        check(until(lambda: js(process, "!!document.querySelector('.ai-sidebar .mascot canvas[data-live]')") and engine_loaded(process), 30),
              "Once the chat opens, its companion is drawn by the 3D engine")
    finally:
        quit(process)


def gallery(theme):
    process, profile = window({"Theme": theme})
    js(process, "document.dispatchEvent(new Event('still-mascot-sheet'))")
    until(lambda: js(process, "!!document.querySelector('.mascot-sheet')"), 15)
    js(process, f"document.documentElement.classList.toggle('dark', {str(theme == 'Dark').lower()})")
    check(js(process, "document.querySelectorAll('.mascot-sheet canvas').length") == LOOKS * STATES, f"{theme}: the sheet has all {LOOKS * STATES} companions")
    # Only companions on screen draw live; scrolled away, they rest. Check the top half, then the bottom.
    on_screen = ("[...document.querySelectorAll('.mascot-sheet canvas')].filter(c => { const r = c.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.left < innerWidth })"
                 ".every(c => c.dataset.live !== undefined)")
    for half in ("top", "bottom"):
        if half == "bottom":
            js(process, "(s => s.style.transform = `translateY(${innerHeight - s.scrollHeight}px)`)(document.querySelector('.mascot-sheet'))")  # the shell doesn't scroll
        check(until(lambda: js(process, on_screen), 30), f"{theme}: every companion on screen draws live ({half})")
        time.sleep(1.5)
        rpc(process, "capture", name="sheet.png")
        shutil.copy(profile / "sheet.png", OUT / f"mascots-v02-{theme.lower()}{'-2' if half == 'bottom' else ''}.png")
    return process


# Each animation the companion has: its state or gesture, and how many seconds of its clip to show.
REEL = [("idle", "idle", ""), ("happy", "idle", "happy"), ("thinking", "thinking", ""), ("working", "working", ""), ("pointing", "pointing", ""),
        ("needs-you", "needs", ""), ("done", "done", ""), ("sad", "error", ""), ("talking", "talking", ""), ("wave", "idle", "wave"),
        ("admire", "idle", "admire"), ("pop", "idle", "pop")]


def gifs():
    """Every animation of the default look as a GIF: the clip posed at 20 frames a second on a warm paper background."""
    from PIL import Image
    folder = ROOT / "docs" / "agentic" / "mascot"
    folder.mkdir(parents=True, exist_ok=True)
    process, profile = window()
    try:
        js(process, "document.documentElement.dataset.mascotFreeze = '0'; document.dispatchEvent(new CustomEvent('still-mascot-reel', { detail: { state: 'idle' } }))")
        until(lambda: js(process, "!!document.querySelector('.mascot-reel canvas[data-live]')"), 30)
        chunk = js(process, "performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('companion3d'))")
        js(process, f"import({json.dumps(chunk)}).then(m => {{ window.__clips = m.DUR }})")
        clips = until(lambda: js(process, "window.__clips && JSON.stringify(window.__clips)"), 10)
        clips = json.loads(clips)
        made = 0
        for name, state, gesture in REEL:
            js(process, f"document.dispatchEvent(new CustomEvent('still-mascot-reel', {{ detail: {{ state: {json.dumps(state)}, gesture: {json.dumps(gesture)} }} }}))")
            until(lambda: js(process, "!!document.querySelector('.mascot-reel canvas[data-live]')"), 10)
            seconds = clips.get(gesture or state, 4)  # a gesture plays once; the loops are four seconds
            frames, out = [], profile / name
            out.mkdir()
            for i in range(int(seconds * 20)):
                js(process, f"document.documentElement.dataset.mascotFreeze = '{i / 20:.3f}'")
                time.sleep(.09)  # a tick or two of the stage
                url = js(process, "document.querySelector('.mascot-reel canvas').toDataURL()")
                shot = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
                paper = Image.new("RGBA", shot.size, (246, 243, 237, 255))
                paper.alpha_composite(shot)
                paper.convert("RGB").resize((240, 240), Image.LANCZOS).save(out / f"{i:03d}.png")
                frames.append(i)
            gif = folder / f"{name}.gif"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "20", "-i", str(out / "%03d.png"), "-filter_complex",
                            "split[a][b];[a]palettegen=max_colors=128:reserve_transparent=0[p];[b][p]paletteuse=dither=sierra2_4a", "-loop", "0", str(gif)], check=True)
            made += gif.exists()
            print(f"  {name}: {len(frames)} frames, {gif.stat().st_size // 1024} KB", flush=True)
        check(made == len(REEL), f"A GIF for each of the {len(REEL)} animations")
    finally:
        quit(process)


# look.ts RIGS: the six roles' looks (no props) and Make your own's, and the model each wears
RIGS = [({"color": "#f7a26a", "shape": "tall", "prop": ""}, "jonah"), ({"color": "#f2a5c4", "shape": "gumdrop", "prop": ""}, "talia"),
        ({"color": "#a6cf9c", "shape": "block", "prop": ""}, "nora"), ({"color": "#f6d56a", "shape": "round", "prop": ""}, "leo"),
        ({"color": "#8cc3ee", "shape": "bump", "prop": ""}, "ivan"), ({"color": "#c0a3ec", "shape": "lean", "prop": ""}, "maya"),
        ({"color": "#ddd4c6", "shape": "bean", "prop": ""}, "custom")]
PROPS = ["laptop", "mug", "headphones", "notebook", "phone", "magnifier", "wrench", "paintbrush", "camera", "briefcase"]  # look.ts PROPS
SHAPES = ["bean", "tall", "gumdrop", "block", "round", "squat", "bump", "lean"]  # look.ts SHAPES


def glb(path):
    b = path.read_bytes()
    return json.loads(b[20:20 + struct.unpack_from("<I", b, 12)[0]])


def art():
    """Every Blender companion: no prop in its model."""
    assets = ROOT / "still-ui" / "src" / "assets"
    for _, app in RIGS:
        g = glb(assets / "rig" / f"{app}.glb")
        held = [n["name"] for n in g["nodes"] if n.get("name", "").startswith("prop")]
        check(not held, f"{app}: holds nothing")


def looks():
    """The roles' looks (no props) wear their own models; a companion saved holding its role's old prop still does; and
    Make your own's props, on every shape, never go into the body or a nub through any state or gesture."""
    old = [{"Id": "jonah", "Name": "Jonah", "Job": "Sales.", "Crew": "sales", "Look": json.dumps({"color": "#f7a26a", "shape": "tall", "prop": "chart", "accessory": ""})},
           {"Id": "maya", "Name": "Maya", "Job": "Research.", "Crew": "research", "Look": json.dumps({"color": "#c0a3ec", "shape": "lean", "prop": "magnifier", "accessory": ""})}]
    process, _ = window({"AiHarness": "claude", "Companions": old})
    try:
        js(process, "document.dispatchEvent(new CustomEvent('still-mascot-reel', { detail: %s }))" % json.dumps({"state": "idle", "size": 120, "looks": [l for l, _ in RIGS]}))
        worn = until(lambda: js(process, "document.querySelectorAll('.mascot-reel .mascot').length && JSON.stringify([...document.querySelectorAll('.mascot-reel .mascot')].map(m => m.dataset.rig ?? ''))"), 20)
        check(worn and json.loads(worn) == [a for _, a in RIGS], f"The roles' looks, no props, wear their own models: {worn}")
        looks = [{"color": "#f7a26a", "shape": sh, "prop": pr, "accessory": ""} for pr in PROPS for sh in SHAPES]
        t = time.monotonic()
        js(process, "document.dispatchEvent(new CustomEvent('still-mascot-clashes', { detail: %s }))" % json.dumps(looks))
        got = until(lambda: js(process, "window.__clashes && JSON.stringify(window.__clashes)"), 300)
        bad = [f"{l['prop']}/{l['shape']}: {c}" for l, c in zip(looks, json.loads(got or "[]")) if c]
        check(got and not bad, f"Make your own's {len(PROPS)} props on {len(SHAPES)} shapes clear the body and nubs ({time.monotonic() - t:.0f} s)" + "".join("\n  " + b for b in bad[:12]))
    finally:
        quit(process)
    process, _ = window({"AiHarness": "claude", "Companions": old})
    try:
        send(process, "new")
        until(lambda: js(process, "!!document.querySelector('.home-face .mascot')"), 30)
        go = "document.querySelector('.mate-portrait') || [...document.querySelectorAll('.home-chips button')].find(b => b.innerText.includes('Companions'))?.click(); "
        rigs = until(lambda: js(process, go + "document.querySelectorAll('.mate-portrait .mascot').length === 2 && JSON.stringify([...document.querySelectorAll('.mate-portrait .mascot')].map(m => m.dataset.rig ?? ''))"), 20)
        check(rigs and json.loads(rigs) == ["jonah", "maya"], f"Saved holding their role's old prop (chart, magnifier), they still wear their rigs: {rigs}")
    finally:
        quit(process)


def blinks():
    """A blink (Blender's, held by the test clock) shuts every rig's eyes, and they open again after it."""
    looks = [l for l, _ in RIGS]
    process, _ = window()
    try:
        js(process, "document.documentElement.dataset.mascotFreeze = '0.5'; document.dispatchEvent(new CustomEvent('still-mascot-reel', { detail: %s }))"
           % json.dumps({"state": "idle", "size": 240, "looks": looks}))
        until(lambda: js(process, "document.querySelectorAll('.mascot-reel canvas[data-live]').length") >= len(looks), 30)
        dark = ("JSON.stringify([...document.querySelectorAll('.mascot-reel canvas[data-live]')].map(c => { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
                " let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200 && d[i] + d[i + 1] + d[i + 2] < 90) n++; return n }))")

        def eyes(blink):
            js(process, f"document.documentElement.dataset.mascotBlink = '{blink}'" if blink else "delete document.documentElement.dataset.mascotBlink")
            time.sleep(.8)
            return json.loads(js(process, dark))
        open_, shut, again = eyes(None), eyes(.14), eyes(None)
        print("dark pixels: open", open_, "shut", shut, "after", again)
        check(len(open_) == len(looks) and all(s < o * .5 for o, s in zip(open_, shut)), "A blink shuts every rig's eyes")
        check(all(abs(a - o) <= o * .1 for o, a in zip(open_, again)), "After the blink every rig's eyes are open again (the lids don't keep it)")
    finally:
        quit(process)


def fallbacks():
    """Without WebGL, Still shows the default look drawn ahead, one picture per framing (whole, and the look editor's top half),
    and its 2D one at chat sizes (so a plain window's toolbar companion needs no three.js)."""
    process, _ = window()
    try:
        js(process, "document.dispatchEvent(new CustomEvent('still-mascot-reel', { detail: { state: 'idle' } }))")
        until(lambda: js(process, "!!document.querySelector('.mascot-reel canvas[data-live]')"), 30)
        chunk = js(process, "performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('companion3d'))")
        look = json.dumps({"color": "#8cc3ee", "shape": "bean", "prop": "", "accessory": ""})  # look.ts: DEFAULT_LOOK
        js(process, f"import({json.dumps(chunk)}).then(m => window.__pics = {{ full: m.picture({look}, 'idle', 384, 'full'), bust: m.picture({look}, 'idle', 384, 'bust'), flat: m.picture({look}, 'idle', 144, 'full', true) }})")
        until(lambda: js(process, "!!window.__pics"), 10)
        folder = ROOT / "still-ui" / "src" / "assets" / "companion"
        folder.mkdir(parents=True, exist_ok=True)
        for frame in ("full", "bust", "flat"):
            (folder / f"default-{frame}-idle.webp").write_bytes(base64.b64decode(js(process, f"window.__pics.{frame}").split(",", 1)[1]))
        check(all((folder / f"default-{f}-idle.webp").stat().st_size > 1000 for f in ("full", "bust", "flat")), "The three fallback pictures are drawn")
    finally:
        quit(process)


art()
plain_window()
looks()
blinks()
quit(gallery("Light"))
quit(gallery("Dark"))
if "--gifs" in sys.argv:
    gifs()
if "--fallbacks" in sys.argv:
    fallbacks()

if "--screens" in sys.argv:
    from qa import shots
    live = "canvas[data-live]"

    def home(p):
        send(p, "new")  # the profile starts on about:blank: open the new tab page
        until(lambda: js(p, f"!!document.querySelector('.home-face {live}')"), 30)
        time.sleep(.5)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")  # a new tab opens with the address bar's suggestions

    def sidebar(p):
        send(p, "aiToggle")
        until(lambda: js(p, "!!document.querySelector('.ai-sidebar .mascot img, .ai-sidebar .mascot canvas[data-live]')"), 30)

    signed_in = {"AiHarness": "claude", "Companions": CREW}
    shots(EXE, "newtab-mascot", "v03", home, signed_in)
    shots(EXE, "sidebar-mascot", "v03", sidebar, signed_in)

print(("PASSED " if all(RESULT) else "FAILED ") + f"{sum(RESULT)}/{len(RESULT)}")
