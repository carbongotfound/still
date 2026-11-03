"""Look v2 (Stage 12) and every saved look before it.
  Goldens: every saved look in tests/fixtures/looks.json (each v1 shape, the six roles and Ruth, props, accessories and
  the legacy formats) drawn whole and as a head icon, against the pictures the build before v2 drew
  (tests/fixtures/looks/<win|mac>/): a look nobody edited looks the same after the update.
  v2: the eyes show at 18px on every start, team look, 40 Surprise me draws and kept props
  (tests/fixtures/looks-v2.json); the five bodies' silhouettes stay apart; and the editor: a classic look shown as it
  is until Try the new style, Keep prop, picks, undo, redo, Reset, Surprise me with a lock, Cancel, a team look that
  needs one change, each change on the preview within 100ms, and six companions shot at 280px and in the editor (360,
  and 40, 24 and 18px in light and dark).

Run: python tests/desktop/looks.py <Still.exe> [--goldens]   (--goldens: write the pictures, from the build before v2)
"""
import base64
import io
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, companions_page, js, launch, rpc, send, until  # noqa: E402

EXE = sys.argv[1]
GOLD = ROOT / "tests" / "fixtures" / "looks" / ("mac" if MAC else "win")
OUT = ROOT / "artifacts" / ("looks-" + uuid.uuid4().hex[:8])
OUT.mkdir(parents=True)
FIXTURES = json.loads((ROOT / "tests" / "fixtures" / "looks.json").read_text())
V2 = json.loads((ROOT / "tests" / "fixtures" / "looks-v2.json").read_text())  # tests/ui/look.test.ts keeps it current
FORM_SHAPE = {"pebble": "round", "column": "tall", "block": "block", "gumdrop": "gumdrop", "bean": "lean"}
PLAIN = {"v": 2, "color": "#ddd4c6", "prop": "", "accessory": "", "second": "#8a6a50", "marking": "none", "eye": "round", "mouth": "smile", "top": "none", "finish": "matte"}
PIP = '{"color":"#f39079","shape":"bean","prop":"laptop","accessory":"bow"}'  # made before the new style, holding a laptop
PROFILE = OUT / "profile"
RESULT = []


def check(ok, name):
    RESULT.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def window():
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Width": 1260, "Height": 860},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, PROFILE)


def quit(process):
    rpc(process, "quit")
    process.wait(timeout=15)


def engine(process):
    """Loads the 3D engine (the props check asks for it, and leaves the app on screen) and keeps its module as window.__m."""
    js(process, "document.dispatchEvent(new CustomEvent('still-mascot-clashes', { detail: [] }))")
    until(lambda: js(process, "!!window.__clashes"), 30)
    if MAC:  # WebKit keeps no resource timing for still:// files: the app says what it served
        path = next(f for f in rpc(process, "served")["files"] if "companion3d" in f)
        chunk = js(process, f"new URL({json.dumps(path)}, location.origin + '/').href")
    else:
        chunk = js(process, "performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('companion3d'))")
    js(process, f"import({json.dumps(chunk)}).then(m => window.__m = m)")
    until(lambda: js(process, "!!window.__m"), 10)


def picture(process, look, px, tier):
    """The look's still picture as PNG bytes, drawn by the engine; None if it never comes."""
    raw = look if isinstance(look, str) else json.dumps(look)
    for _ in range(80):
        url = js(process, f"window.__m.picture(JSON.parse({json.dumps(raw)}), 'idle', {px}, '{tier}')")
        if url:  # a data URL (WebP, or PNG where WebKit can't write WebP): stored as PNG
            from PIL import Image
            out = io.BytesIO()
            Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA").save(out, "PNG")
            return out.getvalue()
        time.sleep(.25)
    return None


def pixels(png):
    from PIL import Image
    return Image.open(io.BytesIO(png)).convert("RGBA")


def differs(a, b):
    """(mean difference per channel 0-255, share of pixels off by more than 24 in any channel)."""
    from PIL import ImageChops
    if a.size != b.size:
        return 255.0, 1.0
    data = list(ImageChops.difference(a, b).getdata())
    return sum(sum(p) for p in data) / (len(data) * 4), sum(1 for p in data if max(p) > 24) / len(data)


def goldens(process, write):
    GOLD.mkdir(parents=True, exist_ok=True)
    for i, raw in enumerate(FIXTURES["v1"] + FIXTURES["legacy"]):
        look = FIXTURES["parsed"][raw]  # what the build before v2 read it as (tests/ui/look.test.ts: this build reads it the same)
        for px, tier in ((192, "full"), (60, "icon")):
            name = f"{i:02d}-{tier}.png"
            png = picture(process, look, px, tier)
            if write:
                if png:
                    (GOLD / name).write_bytes(png)
                check(png is not None, f"Golden {name}: {raw[:70]}")
                continue
            if not png or not (GOLD / name).exists():
                check(False, f"{name} drawn and has a golden: {raw[:70]}")
                continue
            (OUT / name).write_bytes(png)
            mean, off = differs(pixels(png), pixels((GOLD / name).read_bytes()))
            check(mean < 1.5 and off < .01, f"Unchanged after the update, {tier}: {raw[:60]} (mean {mean:.2f}, {off:.1%} of pixels off)")


def eyes(img):
    """Opaque pixels near the pupils' color: how much of the eyes shows at this size."""
    return sum(1 for r, g, b, a in img.getdata() if a > 200 and abs(r - 27) + abs(g - 20) + abs(b - 32) < 90)


def outline(img):
    """The silhouette, cut to its own box and scaled to fit 64 by 64 standing on the bottom edge: the height to width
    stays, since that is most of what tells two bodies apart."""
    from PIL import Image
    m = img.getchannel("A").point(lambda a: 255 if a > 128 else 0)
    m = m.crop(m.getbbox())
    k = 64 / max(m.size)
    m = m.resize((max(1, round(m.width * k)), max(1, round(m.height * k))))
    out = Image.new("L", (64, 64), 0)
    out.paste(m, ((64 - m.width) // 2, 64 - m.height))
    return out


def overlap(a, b):
    pa, pb = [v > 127 for v in a.getdata()], [v > 127 for v in b.getdata()]
    return sum(x and y for x, y in zip(pa, pb)) / max(1, sum(x or y for x, y in zip(pa, pb)))


def new_style(process):
    looks = [l for _, l in V2["starts"]] + [l for _, l in V2["team"]] + V2["surprise"] + V2["kept"]
    small = []
    for raw in looks:
        png = picture(process, raw, 18, "icon")
        n = eyes(pixels(png)) if png else 0
        if n < 2:
            small.append(f"{raw[:90]} ({n} px)")
    check(not small, f"At 18px the eyes show on all {len(looks)} new-style looks: starts, team looks, 40 Surprise me draws, kept props ({small[:3]})")
    shapes = {}
    for form in FORM_SHAPE:
        png = picture(process, {**PLAIN, "form": form, "shape": FORM_SHAPE[form]}, 192, "full")
        if png:
            (OUT / f"form-{form}.png").write_bytes(png)
            shapes[form] = outline(pixels(png))
    pairs = sorted(((overlap(shapes[a], shapes[b]), a, b) for i, a in enumerate(shapes) for b in list(shapes)[i + 1:]), reverse=True)
    check(len(shapes) == 5 and pairs[0][0] <= .82, f"The five bodies stay apart: most alike {pairs[0][1]} and {pairs[0][2]}, {pairs[0][0]:.0%} overlap at one size (about 80% at most)" if pairs else "The five bodies draw")


def click(process, selector):
    return js(process, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.click(); return !!e }})()")


def click_text(process, selector, words):
    return js(process, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => e.innerText.trim().includes({json.dumps(words)})); e?.click(); return !!e }})()")


def look_of(name):
    try:
        mates = json.loads((PROFILE / "state.json").read_text(encoding="utf-8")).get("Preferences", {}).get("Companions", [])
    except (OSError, ValueError):
        return None
    return next((c.get("Look", "") for c in mates if c.get("Name") == name), None)


def editor(process, name):
    """Opens name's look editor from the Companions page."""
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    companions_page(process)
    until(lambda: click(process, f".mate-portrait[aria-label='Edit {name}']"), 5)
    until(lambda: js(process, "!!document.querySelector('.profile-panel')"), 5)
    click_text(process, ".profile-stage-actions button", "Edit look")
    return until(lambda: js(process, "!!document.querySelector('.look-dialog .look-stage .mascot canvas, .look-dialog .look-stage .mascot img')"), 8)


def close(process, button="Cancel"):
    click_text(process, ".look-dialog .look-foot button", button)
    until(lambda: not js(process, "!!document.querySelector('.look-dialog')"), 3)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    if not until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 2):
        click(process, ".profile-head [aria-label=Close]")


def picked(process, group):
    return js(process, f"document.querySelector('.look-dialog [aria-label={json.dumps(group)}] [aria-checked=true]')?.getAttribute('aria-label')")


def tab(process, name):
    click_text(process, ".look-tabs [role=tab]", name)
    time.sleep(.3)


def timed(process, selector):
    """Milliseconds from a click on selector to the preview drawing the change (the clock frozen, so only a change redraws
    it), or -1 if it never does."""
    js(process, """(() => { // the preview's canvas now, whichever it is: a new body may come in a new one
     const sum = () => { const cv = document.querySelector('.look-stage .mascot canvas'); if (!cv) return 0; const d = cv.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, cv.width, cv.height).data; let s = 0; for (let i = 0; i < d.length; i += 28) s = (s * 31 + d[i]) | 0; return s }
     const before = sum(); window.__took = null; const t0 = performance.now(); document.querySelector(%s).click()
     const tick = () => { const now = sum(); if (now && now !== before) window.__took = performance.now() - t0; else if (performance.now() - t0 < 3000) requestAnimationFrame(tick); else window.__took = -1 }
     requestAnimationFrame(tick); return true })()""" % json.dumps(selector))
    return until(lambda: js(process, "window.__took"), 5)


def edit(process):
    mates = [("pip", "Pip", PIP), ("kit", "Kit", V2["starts"][1][1])] + [(f"m{i}", f"Mate{i}", look) for i, (_, look) in enumerate(V2["starts"][:3] + V2["team"][:3])]
    for id, name, look in mates:
        send(process, "companionSave", id=id, name=name, job="", look=look)
    until(lambda: look_of("Mate5"), 5)
    send(process, "new")  # the home page, for its Companions chip
    js(process, "document.documentElement.dataset.mascotFreeze = '0'")

    # An old look with a prop: shown as it is; nothing changes until Try the new style
    check(editor(process, "Pip"), "Pip's look editor opens")
    tabs = js(process, "[...document.querySelectorAll('.look-tabs [role=tab]')].filter(t => !t.disabled).map(t => t.innerText).join()")
    classic = js(process, "document.querySelector('.look-classic')?.innerText") or ""
    check(tabs == "Start" and "classic look" in classic and "Try the new style" in classic, f"A classic look opens as it is, with Try the new style ({tabs})")
    rpc(process, "capture", name="pip-classic.png")
    close(process)
    time.sleep(.8)
    check(look_of("Pip") == PIP, "Cancel keeps the classic look byte for byte")
    editor(process, "Pip")
    click_text(process, ".look-classic button", "Try the new style")
    tab(process, "Extras")
    kept = until(lambda: js(process, "document.querySelector('.look-dialog .look-check input')?.checked"), 3)
    check(kept and "laptop" in (js(process, "document.querySelector('.look-dialog .look-check')?.innerText") or ""), "Try the new style keeps the laptop, with Keep the laptop to take it off")
    time.sleep(1.5)
    rpc(process, "capture", name="pip-new.png")
    close(process, "Save look")
    until(lambda: json.loads(look_of("Pip") or "{}").get("v") == 2, 5)  # the host stores it a moment later
    pip = json.loads(look_of("Pip") or "{}")
    check(pip.get("v") == 2 and pip.get("prop") == "laptop" and pip.get("color") == "#f39079" and pip.get("form") == "bean" and pip.get("accessory") == "bow", f"Saved in the new style, the laptop and bow kept ({pip})")

    # A new-style look: picks, undo, redo, Reset, Surprise me with a lock, Cancel
    editor(process, "Kit")
    until(lambda: js(process, "!!document.querySelector('.look-stage .mascot canvas')"), 10)  # the live preview, not its still picture
    time.sleep(1.5)
    took = [timed(process, ".look-dialog [data-option=block]")]
    time.sleep(.3)
    first = picked(process, "Body")
    click(process, ".look-foot [aria-label=Undo]")
    time.sleep(.3)
    undone = picked(process, "Body")
    click(process, ".look-foot [aria-label=Redo]")
    time.sleep(.3)
    check((first, undone, picked(process, "Body")) == ("Block", "Column", "Block"), "A pick shows at once; Undo goes back to the column, Redo to the block")
    tab(process, "Face")
    took.append(timed(process, ".look-dialog [data-option=sleepy]"))
    tab(process, "Extras")
    took.append(timed(process, ".look-dialog [data-option=tuft]"))  # Kit (Sky column) already has antennae
    tab(process, "Colors")
    took.append(timed(process, ".look-colors[aria-label='Body color'] [aria-label='Mint']"))
    ok = [t for t in took if t is not None and t >= 0]
    check(len(ok) == len(took) and max(ok) < 100, f"Each change shows on the preview within 100ms ({', '.join(f'{t:.0f}ms' for t in ok)}; {len(took) - len(ok)} never)")
    # Colors: one solid color, an accent and a marking only if picked, each part its own color (or any color)
    marks = lambda: js(process, "!!document.querySelector(\".look-colors[aria-label='Marking color']\")")
    click(process, ".look-colors[aria-label='Accent'] .is-none")
    time.sleep(.3)
    solid = js(process, "document.querySelector(\".look-colors[aria-label='Accent'] .is-none\").getAttribute('aria-checked')") == "true" and not marks()
    click(process, ".look-dialog [data-option=belly]")
    time.sleep(.3)
    shown = marks()
    click(process, ".look-colors[aria-label='Marking color'] [aria-label='Charcoal']")
    click(process, ".look-colors[aria-label='Accent'] [aria-label='Snow']")
    time.sleep(.3)
    picks = js(process, "[...document.querySelectorAll('.look-colors')].map(g => g.getAttribute('aria-label') + '=' + (g.querySelector('[aria-checked=true]')?.getAttribute('aria-label') ?? 'own')).join()")
    anyc = js(process, "document.querySelectorAll('.look-colors .look-custom input[type=color]').length")
    rpc(process, "capture", name="colors-picked.png")
    check(solid and shown and picks == "Body color=Mint,Accent=Snow,Marking color=Charcoal" and anyc == 3,
          f"Colors: one solid color with No accent and no marking; the marking's color shows once a marking is picked; body, accent and marking each pick their own, or any color ({solid}, {shown}, {picks}, {anyc} pickers)")
    click_text(process, ".look-locks button", "Body")
    forms = set()
    for _ in range(6):
        click_text(process, ".look-surprise button", "Surprise me")
        tab(process, "Body")
        forms.add(picked(process, "Body"))
    check(forms == {"Block"}, f"Surprise me keeps the locked body ({forms})")
    click_text(process, ".look-foot button", "Reset")
    time.sleep(.3)
    check(picked(process, "Body") == "Column", "Reset goes back to the look it opened with")
    close(process)
    time.sleep(.8)
    check(look_of("Kit") == V2["starts"][1][1], "Cancel leaves the saved look untouched")

    # Start from a team look: one change before it saves
    editor(process, "Mate0")
    tab(process, "Start")
    click(process, ".look-dialog [data-team=sales]")
    time.sleep(.3)
    held = js(process, "document.querySelector('.look-save').disabled") and "Change one thing" in (js(process, "document.querySelector('.look-foot')?.innerText") or "")
    tab(process, "Face")
    click(process, ".look-dialog [data-option=sleepy]")
    time.sleep(.3)
    check(held and not js(process, "document.querySelector('.look-save').disabled"), "A team look needs one change before it saves")
    close(process, "Save look")
    until(lambda: json.loads(look_of("Mate0") or "{}").get("color") == "#ff8a4c", 5)
    mate = json.loads(look_of("Mate0") or "{}")
    check(mate.get("color") == "#ff8a4c" and mate.get("eye") == "sleepy", f"The team look saves as your own ({mate})")

    # Six companions: three from the starts, three from team looks, at 280px and in the editor (360, and the strip)
    shots = 0
    for i in range(6):
        if editor(process, f"Mate{i}"):
            time.sleep(1.5)
            rpc(process, "capture", name=f"mate{i}.png")
            shots += 1
            png = picture(process, look_of(f"Mate{i}"), 280, "full")
            if png:
                (OUT / f"mate{i}-280.png").write_bytes(png)
        close(process)
    for f in PROFILE.glob("*.png"):
        (OUT / f.name).write_bytes(f.read_bytes())
    check(shots == 6, f"Six companions shot at 280px and in the editor at 360, 40, 24 and 18px, light and dark ({OUT})")


process = window()
try:
    engine(process)
    goldens(process, "--goldens" in sys.argv)
    if "--goldens" not in sys.argv:
        new_style(process)
        edit(process)
finally:
    quit(process)

print(("PASSED " if all(RESULT) else "FAILED ") + f"{sum(RESULT)}/{len(RESULT)} -> {OUT}")
