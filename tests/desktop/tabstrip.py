"""The tab strip and the bookmarks bar never overlap: the selected tab sits inside the strip, the toolbar starts below
it, the bookmarks bar has its own solid background below the toolbar, and the page starts below the bookmarks bar.
Checked in light and dark, at 100/125/150% display scale and at three window widths, by element rects and by the
pixels just under the selected tab (the toolbar's own color, not the tab's).

Run: python tests/desktop/tabstrip.py artifacts/Still-QA/Still.exe
Out: artifacts/tabstrip-*/ (result.json, a shot per theme and scale)
"""
import json
from pathlib import Path
import shutil
import struct
import sys
import time
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, launch, rpc  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("tabstrip-" + uuid.uuid4().hex[:8])
CHECKS = []
RECTS = """JSON.stringify(Object.fromEntries([['strip','.top-tab-strip'],['sel','.tab-row.is-selected'],['bar','.window-bar'],['marks','.bookmarks-bar']]
 .map(([k,s])=>{const e=document.querySelector(s);if(!e)return[k,null];const r=e.getBoundingClientRect();return[k,{top:r.top,bottom:r.bottom,left:r.left,right:r.right,bg:getComputedStyle(e).backgroundColor}]})))"""


def check(ok, name):
    CHECKS.append({"name": name, "passed": bool(ok)}); print(("PASS " if ok else "FAIL ") + name)


def pixels(path):
    """RGBA rows of a PNG (8-bit RGB or RGBA, as WebView2 captures)."""
    data = Path(path).read_bytes(); pos = 8; idat = b""
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IHDR": w, h, depth, color = struct.unpack(">IIBB", data[pos + 8:pos + 18])
        if kind == b"IDAT": idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    bpp = 4 if color == 6 else 3; raw = zlib.decompress(idat); rows = []; prev = bytearray(w * bpp); i = 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + w * bpp]); i += 1 + w * bpp
        for x in range(len(line)):
            a = line[x - bpp] if x >= bpp else 0; b = prev[x]; c = prev[x - bpp] if x >= bpp else 0
            p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            line[x] = (line[x] + [0, a, b, (a + b) // 2, a if pa <= pb and pa <= pc else b if pb <= pc else c][f]) & 255
        rows.append(line); prev = line
    return w, h, bpp, rows


for theme in ("Light", "Dark"):
    profile = RUN / theme / "profile"; profile.mkdir(parents=True)
    tabs = [{"Id": "a", "Title": "Garden notes", "Url": "about:blank"}, {"Id": "b", "Title": "How to connect to a VPN in Windows - Microsoft Support", "Url": "about:blank"},
            {"Id": "c", "Title": "Recipes", "Url": "about:blank"}]
    marks = [{"Title": t, "Url": f"https://{t.lower()}.example/"} for t in ("Mail", "Calendar", "Docs", "News", "Maps", "Music", "Photos")]
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Theme": theme, "Width": 1280, "Height": 800},
                                                    "Tabs": tabs, "ActiveId": "b", "Bookmarks": marks}))
    p = launch(EXE, profile)
    try:
        time.sleep(1.5)
        for scale in (1, 1.25, 1.5):
            for width in (0, 900, 640):
                rpc(p, "shellCdp", method="Emulation.setDeviceMetricsOverride", parameters={"width": width, "height": 0, "deviceScaleFactor": scale, "mobile": False})
                time.sleep(.5)
                r = rpc(p, "shellEval", script=RECTS); r = json.loads(r) if isinstance(r, str) else r
                r = json.loads(r) if isinstance(r, str) else r
                strip, sel, bar, marks_ = r["strip"], r["sel"], r["bar"], r["marks"]
                at = f"{theme.lower()} {int(scale * 100)}% {width or 'full'} wide"
                check(sel and sel["top"] >= strip["top"] - .01 and sel["bottom"] <= strip["bottom"] + .01, f"{at}: the selected tab sits inside the strip ({sel['top']:.1f}-{sel['bottom']:.1f} in {strip['top']:.1f}-{strip['bottom']:.1f})")
                check(bar["top"] >= sel["bottom"] - .01 and marks_["top"] >= bar["bottom"] - .01, f"{at}: toolbar below the tab, bookmarks below the toolbar")
                check(marks_["bg"] not in ("rgba(0, 0, 0, 0)", "transparent") and not marks_["bg"].startswith("rgba") , f"{at}: the bookmarks bar has a solid background ({marks_['bg']})")
                if width == 0:
                    name = f"{theme.lower()}-{int(scale * 100)}.png"
                    rpc(p, "capture", name="t.png"); shutil.copy(profile / "t.png", RUN / name)
                    w, h, bpp, rows = pixels(RUN / name)
                    k = w / rpc(p, "shellEval", script="innerWidth")  # capture pixels per CSS px
                    x0, x1 = int((sel["left"] + 12) * k), int((sel["right"] - 12) * k)
                    under = rows[int((bar["top"] + 3) * k)][x0 * bpp:x1 * bpp]
                    beside = rows[int((bar["top"] + 3) * k)][int((sel["right"] + 30) * k) * bpp:][:bpp]
                    same = all(abs(under[i] - beside[i % bpp]) <= 6 for i in range(0, len(under)) if i % bpp < 3)
                    check(same, f"{at}: nothing of the tab shows on the toolbar under it")
            rpc(p, "shellCdp", method="Emulation.clearDeviceMetricsOverride", parameters={})
    finally:
        rpc(p, "quit"); p.wait(timeout=15)

(RUN / "result.json").write_text(json.dumps({"checks": CHECKS}, indent=1))
print(("PASSED " if all(c["passed"] for c in CHECKS) else "FAILED ") + f"{sum(c['passed'] for c in CHECKS)}/{len(CHECKS)} -> {RUN}")
