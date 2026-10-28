"""The mascot gallery: every mascot in every state, live, in light and dark (docs/agentic/compare/mascots-*.png).
With --pictures it also renders the still pictures used without WebGL or with reduced motion, from the same models,
into still-ui/src/assets/mascots (rebuild the shell afterwards).

Run: python tests/desktop/mascots.py artifacts/Still-QA/Still.exe [--pictures]
"""
import base64
import io
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, rpc, until  # noqa: E402

EXE = sys.argv[1]
OUT = ROOT / "docs" / "agentic" / "compare"
OUT.mkdir(parents=True, exist_ok=True)


def gallery(theme):
    profile = ROOT / "artifacts" / ("mascots-" + uuid.uuid4().hex[:8]) / "profile"
    profile.mkdir(parents=True)
    (profile / "state.json").write_text(json.dumps({"UiVersion": 5, "Welcome": False, "Preferences": {"Theme": theme, "Width": 1260, "Height": 860},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, profile)
    js(process, "document.dispatchEvent(new Event('still-mascot-sheet'))")
    until(lambda: js(process, "!!document.querySelector('.mascot-sheet')"), 15)
    js(process, f"document.documentElement.classList.toggle('dark', {str(theme == 'Dark').lower()})")
    live = until(lambda: js(process, "document.querySelectorAll('.mascot-sheet canvas[data-live]').length") == 21, 30)
    return process, profile, bool(live)


process, profile, live = gallery("Light")
try:
    print("live canvases:", live, js(process, "document.querySelectorAll('.mascot-sheet canvas[data-live]').length"), rpc(process)["shellErrors"])
    time.sleep(1.5)
    rpc(process, "capture", name="sheet.png")
    shutil.copy(profile / "sheet.png", OUT / "mascots-v01-light.png")
    if "--pictures" in sys.argv:
        from PIL import Image
        js(process, "document.documentElement.dataset.mascotFreeze = '0.35'")
        time.sleep(1)
        shots = js(process, "JSON.stringify([...document.querySelectorAll('.mascot-sheet .mascot')].map(m => [m.dataset.kind, m.dataset.state, m.querySelector('canvas').toDataURL()]))")
        folder = ROOT / "still-ui" / "src" / "assets" / "mascots"
        folder.mkdir(parents=True, exist_ok=True)
        for kind, state, url in json.loads(shots):
            image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
            image.save(folder / f"{kind}-{state}.webp", "WEBP", quality=88, method=6)
        print("pictures:", len(json.loads(shots)), sum(f.stat().st_size for f in folder.glob("*.webp")) // 1024, "KB")
finally:
    rpc(process, "quit")
    process.wait(timeout=15)

process, profile, live = gallery("Dark")
try:
    time.sleep(1.5)
    rpc(process, "capture", name="sheet.png")
    shutil.copy(profile / "sheet.png", OUT / "mascots-v01-dark.png")
finally:
    rpc(process, "quit")
    process.wait(timeout=15)

# --screens: the mascots where people meet them, at the brief's sizes in light and dark.
if "--screens" in sys.argv:
    from qa import send, shots
    REFS = Path(r"D:\Still\work\strawberry-refs\screens")
    live = "canvas[data-live]"

    def home(p):
        send(p, "new")  # the profile starts on about:blank: open the new tab page
        until(lambda: js(p, f"!!document.querySelector('.home-face {live}')"), 30)
        time.sleep(.5)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")  # a new tab opens with the address bar's suggestions

    def sidebar(p):
        send(p, "aiToggle")
        until(lambda: js(p, f"!!document.querySelector('.ai-head-buddy {live}')"), 30)

    def picker(p):
        home(p)
        js(p, "document.querySelector('.home-mate.is-add').click()")
        until(lambda: js(p, f"document.querySelectorAll('.companion-faces {live}').length === 3"), 30)

    signed_in = {"AiHarness": "claude"}
    shots(EXE, "newtab-mascot", "v02", home, signed_in, REFS / "hero_newtab.png")
    shots(EXE, "sidebar-mascot", "v02", sidebar, signed_in)
    shots(EXE, "picker-mascot", "v02", picker, signed_in)
