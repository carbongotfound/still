"""The companions in 3D: every sample look in every state, live, in light and dark (docs/agentic/compare/mascots-*.png).
  --gifs       one GIF per animation of the default look, posed frame by frame (docs/agentic/mascot/*.gif)
  --fallbacks  the three pictures shown when WebGL is off (still-ui/src/assets/companion; rebuild the shell afterwards)
  --screens    the companions where people meet them, at the brief's sizes

Run: python tests/desktop/mascots.py artifacts/Still-QA/Still.exe [--gifs] [--fallbacks] [--screens]
"""
import base64
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = sys.argv[1]
OUT = ROOT / "docs" / "agentic" / "compare"
OUT.mkdir(parents=True, exist_ok=True)
LOOKS, STATES = 8, 9  # Mascot.tsx: SHEET_LOOKS and STATES
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


def fallbacks():
    """Without WebGL, Still shows the default look drawn ahead, one picture per framing."""
    process, _ = window()
    try:
        js(process, "document.dispatchEvent(new CustomEvent('still-mascot-reel', { detail: { state: 'idle' } }))")
        until(lambda: js(process, "!!document.querySelector('.mascot-reel canvas[data-live]')"), 30)
        chunk = js(process, "performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('companion3d'))")
        look = json.dumps({"color": "#8cc3ee", "shape": "bean", "prop": "", "accessory": ""})  # look.ts: DEFAULT_LOOK
        js(process, f"import({json.dumps(chunk)}).then(m => window.__pics = {{ full: m.picture({look}, 'idle', 384, 'full'), bust: m.picture({look}, 'idle', 384, 'bust'), head: m.picture({look}, 'idle', 96, 'head') }})")
        until(lambda: js(process, "!!window.__pics"), 10)
        folder = ROOT / "still-ui" / "src" / "assets" / "companion"
        folder.mkdir(parents=True, exist_ok=True)
        for frame in ("full", "bust", "head"):
            (folder / f"default-{frame}-idle.webp").write_bytes(base64.b64decode(js(process, f"window.__pics.{frame}").split(",", 1)[1]))
        check(all((folder / f"default-{f}-idle.webp").stat().st_size > 1000 for f in ("full", "bust", "head")), "The three fallback pictures are drawn")
    finally:
        quit(process)


plain_window()
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
