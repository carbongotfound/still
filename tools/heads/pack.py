"""Stage 11: Blender's head renders (480 px, anim.py "heads") -> the head icon and portrait at 1x, 2x and 3x.

Icons at 16, 20, 32, 40, 48 and 60 px, portraits at 40, 80 and 120. Each is masked to a circle 88% of the box, with a line in the outline's color along the cut (where the body goes on
past the circle), so it reads as one shape and nothing touches the box edge.
Run: python tools/heads/pack.py <renders: <rig>/out/{icon,portrait}.png> still-ui/src/assets/head [sheet.png]
The renders come from the mascot rigs on the Mac (Blender, the "heads" pass of rig/anim.py: an orthographic camera on the
rest-pose head bounds, 480px, flat shading; the icon one-tone with a doubled outline and eyes, lids and brows x1.25).
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
NAMES = {"zest": "jonah", "bloom": "talia", "noon": "nora", "fizz": "leo", "rivet": "ivan", "glint": "maya", "ruth": "ruth", "custom": "custom"}
SIZES = {"icon": (16, 20, 32, 40, 48, 60), "portrait": (40, 80, 120)}  # icons at 16 too, so 16px shows a file drawn for it
RIM = {"icon": 26, "portrait": 13}  # the outline's width at 480 px: 2.6 px per 96, doubled for the icon
CIRCLE = .88
FILL = .87  # the drawn head's longer side, as a share of the box (85 to 90%)


def disc(n, d, ss=4):
    m = Image.new("L", (n * ss, n * ss), 0)
    r, c = d * n * ss / 2, n * ss / 2
    ImageDraw.Draw(m).ellipse((c - r, c - r, c + r - 1, c + r - 1), fill=255)  # PIL's box is inclusive
    return m.resize((n, n), Image.BOX)  # area coverage: no ringing past the edge


def ink(im):
    """The outline's color: the median of the body's outermost pixels."""
    a = im.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    return tuple(int(v) for v in ImageStat.Stat(im.convert("RGB"), ImageChops.subtract(a, a.filter(ImageFilter.MinFilter(7)))).median)


def head(im, rim):
    n = im.width
    outer, inner = disc(n, CIRCLE), disc(n, CIRCLE - 2 * rim / n)
    a = im.getchannel("A")
    solid = a.point(lambda v: 255 if v > 0 else 0)
    past = ImageChops.multiply(solid, ImageChops.invert(outer))  # the body beyond the circle
    near = past.filter(ImageFilter.MaxFilter(2 * rim + 1))
    cut = ImageChops.multiply(ImageChops.multiply(ImageChops.subtract(outer, inner), solid), near.point(lambda v: 255 if v else 0))
    out = Image.composite(Image.new("RGBA", im.size, ink(im) + (255,)), im, cut)
    out.putalpha(ImageChops.multiply(out.getchannel("A"), outer))
    return out


def share(im):
    box = im.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
    return max(box[2] - box[0], box[3] - box[1]) / im.width


def fill(raw, rim):
    """The head masked to the circle, zoomed about the box center first so what's drawn takes FILL of the box: a wide head
    sets its own width (the body under it is cut by the circle), so its share depends on the rig."""
    out = head(raw, rim)
    k = FILL / share(out)
    if abs(k - 1) < .01:
        return out
    n = raw.width
    big = raw.resize((round(n * k), round(n * k)), Image.LANCZOS)
    o = (big.width - n) // 2
    zoomed = big.crop((o, o, o + n, o + n)) if k > 1 else Image.new("RGBA", (n, n))
    if k < 1:
        zoomed.paste(big, (-o, -o))
    return head(zoomed, rim)


def small(im, px):
    out = im.convert("RGBa").resize((px, px), Image.LANCZOS).convert("RGBA")
    out.putalpha(ImageChops.multiply(out.getchannel("A"), disc(px, min(CIRCLE + 2 / px, 1 - 2 / px))))  # no ringing past the circle, a clear pixel round it
    return out


OUT.mkdir(parents=True, exist_ok=True)
made = {}
for rig, name in NAMES.items():
    for tier, sizes in SIZES.items():
        big = fill(Image.open(SRC / rig / "out" / f"{tier}.png").convert("RGBA"), RIM[tier])
        made[name, tier] = big
        for px in sizes:
            small(big, px).save(OUT / f"{name}-{tier}-{px}.png", optimize=True)
print("packed", sum(len(SIZES[t]) for _, t in made), "files into", OUT)

if len(sys.argv) > 3:  # a review sheet: every head at 16 to 34 px (2x), light and dark
    rows = [(16, "icon"), (18, "icon"), (20, "icon"), (22, "portrait"), (24, "portrait"), (28, "portrait"), (32, "portrait"), (34, "portrait")]
    cell, pad = 80, 12
    sheet = Image.new("RGB", (pad + len(NAMES) * cell * 2, pad + len(rows) * cell), "#f6f3ee")
    ImageDraw.Draw(sheet).rectangle((pad + len(NAMES) * cell, 0, sheet.width, sheet.height), fill="#1e1e22")
    for j, (px, tier) in enumerate(rows):
        for k, name in enumerate(NAMES.values()):
            im = small(made[name, tier], px * 2)
            for side in (0, 1):
                x = pad + side * len(NAMES) * cell + k * cell + (cell - px * 2) // 2
                sheet.paste(im, (x, pad + j * cell + (cell - px * 2) // 2), im)
    sheet.save(sys.argv[3])
    print("sheet", sys.argv[3])
