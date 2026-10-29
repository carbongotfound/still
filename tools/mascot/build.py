"""Builds Still's companions in Blender: a sculpted body per character on one shared rig, the shared clips, the hair and hats.

Run on the Mac: blender -b --factory-startup -P build.py -- <out dir> <what>
  classic  the classic body with its head shapes, the shared clips and the blink, every hair and hat: companion.glb
  <id>     an official companion (hazel, rio, juno, bram, wren, pip): its body, props, idle and gesture: body-<id>.glb
  fit      fit.json: each head's surface, so hair and hats sit on any of them, and the clip list
Each step also saves a .blend for render.py.

A body is a signed distance field (soft unions of ellipsoids and round cones), meshed with surface nets, remeshed to
clean quads and pulled back onto the field. Weights come from the same parts, so the joins bend like clay. Every body has
the same bones pointing the same ways (only where they start and how long they are changes), so the shared clips play on
all of them. Clips are sampled from code with spring follow-through on the ears, tail and hands. The face isn't modeled:
the app draws it on a texture, and the control bones (lid, brow, mouth, look) carry its expressions, read as scale.

Hair is built from locks: tapered, flattened tubes that follow the head and fall with gravity, over a thin scalp layer
that dives under the skin at the hairline. Its vertex colors carry occlusion (r), a per-lock shade (g) and how freely each
point swings (b, 0 at the scalp); its UVs run along each lock for the strand texture. Hair and hats are plain meshes in
the classic head's space: the app moves them onto any head with the tables in fit.json and binds them to its head bone.
"""
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Matrix, Quaternion, Vector, Euler
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[0] if ARGS else os.path.join(os.path.dirname(__file__), "out")
WHAT = ARGS[1] if len(ARGS) > 1 else "classic"
os.makedirs(OUT, exist_ok=True)
FPS = 30

# ---------------------------------------------------------------- distance field

def ellipsoid(p, c, r, rot=None):
    q = p - np.asarray(c)
    if rot is not None: q = q @ np.asarray(rot)  # rows: world -> local
    r = np.asarray(r, float)
    k0 = np.linalg.norm(q / r, axis=-1); k1 = np.linalg.norm(q / (r * r), axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)

def superellipsoid(p, c, r, e):
    q = np.abs(p - np.asarray(c)) / np.asarray(r)
    return ((q ** e).sum(-1) ** (1 / e) - 1.0) * min(r)

def cone(p, a, b, r1, r2):
    a = np.asarray(a, float); b = np.asarray(b, float); ba = b - a
    pa = p - a; h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
    return np.linalg.norm(pa - h[..., None] * ba, axis=-1) - (r1 + (r2 - r1) * h)

def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0) / k
    return np.minimum(a, b) - h * h * k * 0.25

def smax(a, b, k): return -smin(-a, -b, k)

def rot_y(t):  # local frame rows for a rotation about the front axis
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])

def rot_zy(ty, tz):
    cz, sz = math.cos(tz), math.sin(tz)
    return rot_y(ty) @ np.array([[cz, sz, 0], [-sz, cz, 0], [0, 0, 1]])

def unit(v): v = np.asarray(v, float); return v / np.linalg.norm(v)

def frame(z, up=(0, 0, 1)):
    """Rows of a local frame whose third axis is z (the first lies across, the second along up as far as it can)."""
    z = unit(z); x = np.cross(up, z)
    if np.linalg.norm(x) < 1e-6: x = np.cross((0, 1, 0), z)
    x = unit(x); return np.array([x, np.cross(z, x), z])

def sbox(p, c, r, e, rows=None):
    """A rounded box (superellipsoid) in the frame given by rows (world -> local)."""
    q = p - np.asarray(c)
    if rows is not None: q = q @ np.asarray(rows).T
    r = np.asarray(r, float)
    return ((np.abs(q) / r) ** e).sum(-1) ** (1 / e) * min(r) - min(r)

def torus(p, c, axis, R, r, sy=1.0):
    q = p - np.asarray(c); n = unit(axis); h = q @ n
    flat = q - h[:, None] * n
    return np.sqrt((np.linalg.norm(flat, axis=1) - R) ** 2 + (h / sy) ** 2) - r

def felt(p, amount):
    """Hand-made unevenness: a slow lumpiness, a few tenths of a millimeter on a toy this size."""
    if not amount: return 0.0
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    return amount * (np.sin(13.1 * x + 1.3) * np.sin(11.7 * y + 0.4) * np.sin(12.3 * z + 2.1)
                     + 0.5 * np.sin(29.0 * x + 0.7 * z) * np.sin(31.0 * z - 1.1))

def M(v, s): return (v[0] * s, v[1], v[2])

# ---------------------------------------------------------------- bodies
# Front is -Y, up is Z, feet on z = 0. Sizes are in the classic body's units (about one unit tall).

CLASSIC = dict(
    head=dict(c=(0, 0, 0.655), r=(0.315, 0.275, 0.268), square=0, peak=0),
    cheek=dict(c=(0.172, -0.072, 0.572), r=(0.142, 0.13, 0.118)),
    ear=dict(c=(0.188, 0.025, 0.872), r=(0.074, 0.044, 0.094), tilt=0.40, tip=1.0, scale=1.0),
    sides={1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=0.07, dz=-0.012, s=0.97)},  # the right ear leans out a little more
    body=[((0, 0.012, 0.282), (0.19, 0.166, 0.202), 0), ((0, -0.046, 0.252), (0.15, 0.128, 0.138), 0)],
    arm=dict(a=(0.158, 0.0, 0.392), b=(0.252, -0.024, 0.262), r1=0.057, r2=0.049),
    hand=dict(c=(0.27, -0.03, 0.222), r=(0.066, 0.06, 0.074)),
    leg=dict(a=(0.086, 0.0, 0.17), b=(0.097, -0.004, 0.07), r1=0.071, r2=0.066, foot=(0.101, -0.036, 0.046), foot_r=(0.079, 0.101, 0.056)),
    tail=[((0.012, 0.168, 0.205), (0.058, 0.056, 0.062))],
    hip=0.13, neck=0.43, belly=(0.262, 0.118, 0.128), felt=0.0,
    face=dict(cx=0.0, cz=0.655, su=0.58, sv=0.58),
)

def body_def(**change):
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in CLASSIC.items()}
    for k, v in change.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "sides": out[k] = dict(out[k], **v)
        else: out[k] = v
    return out

BODIES = {
    # cooking: tall and slender, an egg of a head, small ears set high
    "hazel": body_def(
        head=dict(c=(0, 0, 0.80), r=(0.258, 0.24, 0.30)), cheek=dict(c=(0.138, -0.068, 0.715), r=(0.112, 0.102, 0.094)),
        ear=dict(c=(0.152, 0.02, 1.045), r=(0.052, 0.036, 0.068), tilt=0.22),
        sides={1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=0.1, dz=-0.008, s=0.94)},
        body=[((0, 0.01, 0.37), (0.145, 0.13, 0.235), 0), ((0, -0.03, 0.33), (0.112, 0.1, 0.13), 0)],
        arm=dict(a=(0.122, 0.0, 0.53), b=(0.205, -0.02, 0.34), r1=0.045, r2=0.039),
        hand=dict(c=(0.216, -0.025, 0.302), r=(0.052, 0.048, 0.058)),
        leg=dict(a=(0.07, 0.0, 0.2), b=(0.077, -0.004, 0.07), r1=0.052, r2=0.049, foot=(0.081, -0.032, 0.042), foot_r=(0.062, 0.088, 0.045)),
        tail=[], hip=0.18, neck=0.56, belly=(0.34, 0.09, 0.15), felt=0.0016,
        face=dict(cx=0.0, cz=0.785, su=0.48, sv=0.5)),
    # deals: round, chubby and short, head and body nearly one
    "rio": body_def(
        head=dict(c=(0, 0, 0.56), r=(0.335, 0.292, 0.255)), cheek=dict(c=(0.192, -0.08, 0.478), r=(0.162, 0.142, 0.122)),
        ear=dict(c=(0.255, 0.02, 0.748), r=(0.062, 0.04, 0.07), tilt=0.78),
        sides={1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=-0.12, dz=0.01, s=1.04)},
        body=[((0, 0.0, 0.26), (0.252, 0.222, 0.212), 0), ((0, -0.06, 0.24), (0.2, 0.17, 0.152), 0)],
        arm=dict(a=(0.212, 0.0, 0.33), b=(0.3, -0.03, 0.22), r1=0.056, r2=0.05),
        hand=dict(c=(0.316, -0.035, 0.196), r=(0.06, 0.056, 0.066)),
        leg=dict(a=(0.1, 0.0, 0.1), b=(0.106, -0.004, 0.056), r1=0.068, r2=0.066, foot=(0.11, -0.04, 0.038), foot_r=(0.082, 0.102, 0.048)),
        tail=[((0.0, 0.214, 0.2), (0.062, 0.06, 0.062))], hip=0.09, neck=0.36, belly=(0.24, 0.16, 0.14), felt=0.0018,
        face=dict(cx=0.0, cz=0.548, su=0.6, sv=0.6)),
    # planning: a boxy build, square head, square ears, sturdy legs
    "juno": body_def(
        head=dict(c=(0, 0, 0.67), r=(0.3, 0.262, 0.255), square=3.0), cheek=dict(c=(0.165, -0.07, 0.59), r=(0.118, 0.108, 0.098)),
        ear=dict(c=(0.205, 0.02, 0.9), r=(0.07, 0.042, 0.072), tilt=0.28, tip=0.62),
        sides={1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=0.06, dz=-0.006, s=0.98)},
        body=[((0, 0.01, 0.29), (0.192, 0.16, 0.2), 3.0), ((0, -0.04, 0.27), (0.15, 0.12, 0.13), 0)],
        arm=dict(a=(0.16, 0.0, 0.4), b=(0.252, -0.024, 0.27), r1=0.055, r2=0.05),
        hand=dict(c=(0.268, -0.03, 0.23), r=(0.062, 0.058, 0.068)),
        leg=dict(a=(0.09, 0.0, 0.15), b=(0.098, -0.004, 0.07), r1=0.074, r2=0.072, foot=(0.102, -0.036, 0.046), foot_r=(0.084, 0.104, 0.056)),
        tail=[((0.0, 0.172, 0.21), (0.05, 0.05, 0.05))], hip=0.13, neck=0.45, belly=(0.27, 0.11, 0.12), felt=0.0015,
        face=dict(cx=0.0, cz=0.665, su=0.56, sv=0.56)),
    # movies and music: a huge head on a tiny body, long pointed ears
    "bram": body_def(
        head=dict(c=(0, 0, 0.6), r=(0.37, 0.322, 0.315)), cheek=dict(c=(0.2, -0.092, 0.508), r=(0.152, 0.132, 0.12)),
        ear=dict(c=(0.372, 0.03, 0.7), r=(0.062, 0.034, 0.17), tilt=1.18, tip=0.16),
        sides={1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=0.1, dz=-0.015, s=0.96)},
        body=[((0, 0.01, 0.19), (0.13, 0.115, 0.135), 0)],
        arm=dict(a=(0.105, 0.0, 0.25), b=(0.165, -0.02, 0.155), r1=0.04, r2=0.036),
        hand=dict(c=(0.175, -0.022, 0.136), r=(0.045, 0.042, 0.05)),
        leg=dict(a=(0.058, 0.0, 0.1), b=(0.062, -0.004, 0.05), r1=0.046, r2=0.044, foot=(0.066, -0.026, 0.032), foot_r=(0.053, 0.068, 0.034)),
        tail=[], hip=0.08, neck=0.3, belly=(0.18, 0.08, 0.09), felt=0.0016,
        face=dict(cx=0.0, cz=0.57, su=0.66, sv=0.66)),
    # writing: long lop ears, a pear of a body
    "wren": body_def(
        head=dict(c=(0, 0, 0.665), r=(0.3, 0.27, 0.262)), cheek=dict(c=(0.168, -0.07, 0.585), r=(0.135, 0.124, 0.112)),
        ear=dict(c=(0.318, 0.035, 0.6), r=(0.068, 0.04, 0.19), tilt=2.86),
        sides={1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=-0.08, dz=0.018, s=0.95)},
        body=[((0, 0.015, 0.235), (0.222, 0.19, 0.208), 0), ((0, -0.02, 0.36), (0.14, 0.12, 0.12), 0)],
        arm=dict(a=(0.15, 0.0, 0.4), b=(0.242, -0.024, 0.27), r1=0.05, r2=0.045),
        hand=dict(c=(0.258, -0.03, 0.232), r=(0.058, 0.054, 0.064)),
        leg=dict(a=(0.09, 0.0, 0.13), b=(0.098, -0.004, 0.065), r1=0.066, r2=0.062, foot=(0.1, -0.034, 0.042), foot_r=(0.074, 0.096, 0.05)),
        tail=[((0.0, 0.205, 0.2), (0.055, 0.052, 0.055))], hip=0.12, neck=0.43, belly=(0.23, 0.13, 0.14), felt=0.0016,
        face=dict(cx=0.0, cz=0.66, su=0.56, sv=0.56)),
    # news: small, with big round ears and a long tail
    "pip": body_def(
        head=dict(c=(0, 0, 0.54), r=(0.272, 0.24, 0.236)), cheek=dict(c=(0.15, -0.066, 0.468), r=(0.12, 0.11, 0.1)),
        ear=dict(c=(0.258, 0.035, 0.762), r=(0.128, 0.04, 0.128), tilt=0.62),
        sides={1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=0.12, dz=-0.014, s=0.93)},
        body=[((0, 0.01, 0.222), (0.152, 0.13, 0.162), 0), ((0, -0.03, 0.2), (0.12, 0.1, 0.1), 0)],
        arm=dict(a=(0.12, 0.0, 0.31), b=(0.196, -0.02, 0.2), r1=0.044, r2=0.04),
        hand=dict(c=(0.207, -0.024, 0.18), r=(0.05, 0.046, 0.056)),
        leg=dict(a=(0.068, 0.0, 0.11), b=(0.074, -0.004, 0.055), r1=0.052, r2=0.05, foot=(0.077, -0.03, 0.036), foot_r=(0.06, 0.08, 0.04)),
        tail=[((0.0, 0.12, 0.15), (0.0, 0.25, 0.12), 0.024, 0.019), ((0.0, 0.25, 0.12), (0.02, 0.335, 0.23), 0.019, 0.015),
              ((0.02, 0.335, 0.23), (0.0, 0.305, 0.325), 0.015, 0.017)],
        hip=0.09, neck=0.33, belly=(0.21, 0.09, 0.1), felt=0.0016,
        face=dict(cx=0.0, cz=0.53, su=0.5, sv=0.5)),
}

SHAPES = {  # the classic body's head shapes, as changes to it. Names are the app's ids.
    "round": {},
    "mochi": dict(head=dict(c=(0, 0, 0.638), r=(0.35, 0.27, 0.236)), cheek=dict(r=(0.165, 0.14, 0.13)),
                  ear=dict(scale=0.72, c=(0.215, 0.025, 0.84))),
    "bean": dict(head=dict(c=(0, 0, 0.672), r=(0.292, 0.268, 0.3)), cheek=dict(r=(0.12, 0.115, 0.105)), ear=dict(scale=0.12)),
    "kitty": dict(ear=dict(r=(0.07, 0.04, 0.12), tilt=0.32, tip=0.25, c=(0.18, 0.025, 0.885))),
    "fox": dict(ear=dict(r=(0.095, 0.04, 0.13), tilt=0.62, tip=0.3, c=(0.2, 0.03, 0.87)),
                cheek=dict(r=(0.15, 0.13, 0.11), c=(0.182, -0.07, 0.56))),
    "pebble": dict(head=dict(square=3.2, r=(0.3, 0.262, 0.262)), ear=dict(scale=0.62)),
    "droopy": dict(ear=dict(c=(0.3, 0.035, 0.7), r=(0.064, 0.042, 0.125), tilt=2.75)),
    "drop": dict(head=dict(peak=1.0, c=(0, 0, 0.645)), ear=dict(scale=0.12)),
}

def look(shape):
    return body_def(**{part: dict(CLASSIC[part], **change) for part, change in SHAPES[shape].items()})

def ear_frame(L, side, lift=0.0):
    """Where an ear sits: center, radii and the rows that turn world points into its local frame."""
    e = L["ear"]; sd = L["sides"][side]
    c = np.array([e["c"][0] * side, e["c"][1], e["c"][2] + sd["dz"]])
    if lift:  # ear height: swing the ear around the head's center, toward the top or down the side
        hc = np.array(L["head"]["c"]); v = c - hc
        a = -lift * side; ca, sa = math.cos(a), math.sin(a)
        c = hc + np.array([ca * v[0] - sa * v[2], v[1], sa * v[0] + ca * v[2]])
    tilt = (e["tilt"] + sd["tilt"]) * side
    tilt += lift * 0.8 * -side
    r = np.array(e["r"]) * e["scale"] * sd["s"]
    return c, r, rot_zy(tilt, 0.12 * side)

def ear_sdf(p, L, side, lift=0.0):
    c, r, R = ear_frame(L, side, lift)
    e = L["ear"]
    if e["tip"] >= 1: return ellipsoid(p, c, r, R.T)
    q = (p - c) @ R.T  # local: the ear points up its local z
    base = np.array([0, 0, -r[2] * 0.85]); top = np.array([0, 0, r[2] * 1.05])
    flat = q * np.array([1, r[0] / max(r[1], 1e-6), 1])  # flatten front to back
    return cone(flat, base, top, r[0], r[0] * e["tip"])

def head_sdf(p, L):
    h = L["head"]
    d = superellipsoid(p, h["c"], h["r"], h["square"]) if h["square"] else ellipsoid(p, h["c"], h["r"])
    if h["peak"]:
        top = np.array(h["c"]) + np.array([0.0, 0.0, h["r"][2] * 0.8])
        d = smin(d, cone(p, top, top + np.array([0.012, 0.0, 0.17]), 0.13, 0.018), 0.12)
    for s in (1, -1):
        c = L["cheek"]["c"]
        d = smin(d, ellipsoid(p, (c[0] * s, c[1], c[2]), L["cheek"]["r"]), 0.085)
    return d

def parts(p, L, lift=0.0):
    """Each named part's distance. The body is their soft union (see field)."""
    d = {"head": head_sdf(p, L)}
    a, h, g = L["arm"], L["hand"], L["leg"]
    for s, n in ((1, "L"), (-1, "R")):
        d["ear." + n] = ear_sdf(p, L, s, lift)
        d["arm." + n] = cone(p, M(a["a"], s), M(a["b"], s), a["r1"], a["r2"])
        d["hand." + n] = ellipsoid(p, M(h["c"], s), h["r"])
        d["leg." + n] = smin(cone(p, M(g["a"], s), M(g["b"], s), g["r1"], g["r2"]), ellipsoid(p, M(g["foot"], s), g["foot_r"]), 0.035)
    body = None
    for c, r, e in L["body"]:
        x = superellipsoid(p, c, r, e) if e else ellipsoid(p, c, r)
        body = x if body is None else smin(body, x, 0.06)
    d["body"] = body
    tail = np.full(len(p), 1.0)
    for t in L["tail"]:
        x = ellipsoid(p, t[0], t[1]) if len(t) == 2 else cone(p, *t)
        tail = smin(tail, x, 0.02)
    d["tail"] = tail
    return d

def field(p, L, lift=0.0):
    d = parts(p, L, lift)
    f = smin(d["head"], d["ear.L"], 0.05); f = smin(f, d["ear.R"], 0.05)
    f = smin(f, d["body"], 0.075)
    for n in ("L", "R"):
        f = smin(f, smin(d["arm." + n], d["hand." + n], 0.03), 0.04)
        f = smin(f, d["leg." + n], 0.05)
    f = smin(f, d["tail"], 0.035)
    f = f + felt(p, L["felt"])
    return smax(f, -p[..., 2], 0.018)  # flat soles

def gradient(fn, p, e=1e-4):
    g = np.zeros_like(p)
    for i in range(3):
        o = np.zeros(3); o[i] = e
        g[:, i] = (fn(p + o) - fn(p - o)) / (2 * e)
    return g

def project(fn, p, steps=4):
    for _ in range(steps):
        g = gradient(fn, p); p = p - (fn(p) / np.maximum((g * g).sum(1), 1e-9))[:, None] * g
    return p

def bounds(fn, lo=(-0.7, -0.6, -0.03), hi=(0.7, 0.6, 1.4), pad=0.04):
    """The box around everything inside fn, from a coarse look."""
    lo = np.asarray(lo); hi = np.asarray(hi); h = 0.015
    axes = [np.arange(lo[i], hi[i], h) for i in range(3)]
    g = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    inside = g[fn(g) < h]
    return np.maximum(inside.min(0) - pad, lo), np.minimum(inside.max(0) + pad, hi)

# ---------------------------------------------------------------- meshing

def surface_nets(fn, lo, hi, h):
    lo = np.asarray(lo, float); n = np.ceil((np.asarray(hi) - lo) / h).astype(int) + 1
    axes = [lo[i] + np.arange(n[i]) * h for i in range(3)]
    g = np.stack(np.meshgrid(*axes, indexing="ij"), -1)
    F = fn(g.reshape(-1, 3)).reshape(tuple(n))
    F[0], F[-1], F[:, 0], F[:, -1], F[:, :, 0], F[:, :, -1] = 1, 1, 1, 1, 1, 1
    inside = F < 0
    corners = [(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    cs = tuple(n - 1)
    def c(o): return (slice(o[0], o[0] + cs[0]), slice(o[1], o[1] + cs[1]), slice(o[2], o[2] + cs[2]))
    acc = np.zeros(cs + (3,)); cnt = np.zeros(cs)
    for a in range(8):
        for b in range(a + 1, 8):
            oa, ob = corners[a], corners[b]
            if sum(x != y for x, y in zip(oa, ob)) != 1: continue
            fa, fb = F[c(oa)], F[c(ob)]
            m = (fa < 0) != (fb < 0)
            t = np.where(m, fa / np.where(m, fa - fb, 1), 0)
            pa = np.array(oa, float); pb = np.array(ob, float)
            acc += m[..., None] * (pa + t[..., None] * (pb - pa)); cnt += m
    active = cnt > 0
    idx = -np.ones(cs, int); idx[active] = np.arange(active.sum())
    cell = np.argwhere(active)
    verts = lo + (cell + acc[active] / cnt[active][:, None]) * h
    faces = []
    for ax in range(3):
        u, v = [a for a in range(3) if a != ax]
        sl = [slice(None)] * 3; sl[ax] = slice(0, n[ax] - 1)
        a = inside[tuple(sl)]; sl[ax] = slice(1, n[ax]); b = inside[tuple(sl)]
        e = np.argwhere(a != b)
        e = e[(e[:, u] > 0) & (e[:, v] > 0) & (e[:, u] < n[u] - 1) & (e[:, v] < n[v] - 1)]
        flip = a[tuple(e.T)]
        quads = []
        for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
            q = e.copy(); q[:, u] -= 1 - du; q[:, v] -= 1 - dv
            quads.append(idx[tuple(q.T)])
        quads = np.stack(quads, 1)
        quads[flip] = quads[flip][:, ::-1]
        faces.append(quads[(quads >= 0).all(1)])
    return verts, np.concatenate(faces)

def make_mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate(); me.update()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    return ob

def activate(ob):
    for o in bpy.context.view_layer.objects: o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob

def coords(ob):
    a = np.zeros(len(ob.data.vertices) * 3); ob.data.vertices.foreach_get("co", a); return a.reshape(-1, 3)

def set_coords(ob, p):
    ob.data.vertices.foreach_set("co", p.ravel()); ob.data.update()

def neighbors(ob):
    nb = [[] for _ in ob.data.vertices]
    for e in ob.data.edges:
        a, b = e.vertices; nb[a].append(b); nb[b].append(a)
    return nb

def relax(p, nb, fn, rounds=3, mask=None):
    """Evens out the vertices along the surface: average with neighbors, then back onto the field."""
    for _ in range(rounds):
        avg = np.array([p[n].mean(0) if n else p[i] for i, n in enumerate(nb)])
        q = p + (avg - p) * 0.5 if mask is None else p + (avg - p) * 0.5 * mask[:, None]
        p = project(fn, q, 2)
    return p

def remesh(ob, faces, fn, voxel=0.005):
    """Even quads at about the given count: a fine voxel remesh closes the mesh, then a second one sized from its area.
    (QuadriFlow kept refusing these meshes in background mode.)"""
    activate(ob)
    ob.data.remesh_voxel_size = voxel; ob.data.remesh_voxel_adaptivity = 0
    bpy.ops.object.voxel_remesh()
    area = sum(p.area for p in ob.data.polygons)
    ob.data.remesh_voxel_size = math.sqrt(area / faces)
    bpy.ops.object.voxel_remesh()
    p = project(fn, coords(ob)); p = relax(p, neighbors(ob), fn, 10); set_coords(ob, p)
    for poly in ob.data.polygons: poly.use_smooth = True

def blob(name, fn, lo, hi, h, faces):
    v, f = surface_nets(fn, lo, hi, h)
    v = project(fn, v, 3)
    ob = make_mesh(name, v, f)
    remesh(ob, faces, fn)
    return ob

# ---------------------------------------------------------------- the body

def build_body(L, name="Companion", faces=9000):
    fn = lambda p: field(p, L)
    lo, hi = bounds(fn)
    return blob(name, fn, lo, hi, 0.0055, faces)

def part_weights(p, L):
    d = parts(p, L)
    names = list(d)
    D = np.stack([np.maximum(d[n], 0) for n in names], 1)
    W = np.exp(-D / 0.022); W /= W.sum(1, keepdims=True)
    return names, W

def weights(ob, L):
    names, W = part_weights(coords(ob), L)
    return {n: W[:, i] for i, n in enumerate(names)}

def shape_keys(ob, L0, w):
    """Head shapes and ear height as shape keys: move the head's vertices toward each shape, then onto its field."""
    p0 = coords(ob); nb = neighbors(ob)
    headish = np.clip(w["head"] + w["ear.L"] + w["ear.R"], 0, 1)
    headish = np.clip((headish - 0.15) / 0.7, 0, 1)
    ob.shape_key_add(name="Basis")
    def add(name, L, lift=0.0):
        p = p0.copy(); hc0 = np.array(L0["head"]["c"]); hc = np.array(L["head"]["c"])
        sc = np.array(L["head"]["r"]) / np.array(L0["head"]["r"])
        p += (((p0 - hc0) * sc + hc) - p0) * w["head"][:, None]
        for s, n in ((1, "L"), (-1, "R")):
            c0, r0, R0 = ear_frame(L0, s); c1, r1, R1 = ear_frame(L, s, lift)
            local = ((p0 - c0) @ R0.T) / r0
            moved = (local * r1) @ R1 + c1
            p += (moved - p0) * w["ear." + n][:, None]
        fn = lambda q: field(q, L, lift)
        p = p0 + (p - p0) * headish[:, None]
        q = project(fn, p, 4); p = p + (q - p) * headish[:, None]
        p = relax(p, nb, fn, 6, headish)
        k = ob.shape_key_add(name=name, from_mix=False); k.data.foreach_set("co", p.ravel())
        k.value = 0.0  # new keys start at 1 in Blender 5
    for s in SHAPES:
        if s != "round": add(s, look(s))
    add("earsUp", L0, -0.2); add("earsDown", L0, 0.3)

# ---------------------------------------------------------------- face, ao and masks

def ao(ob, rays=48, reach=0.22):
    bm = bmesh.new(); bm.from_mesh(ob.data); bm.normal_update()
    tree = BVHTree.FromBMesh(bm)
    rng = np.random.default_rng(3)
    out = np.zeros(len(bm.verts))
    u = rng.random((rays, 2))
    for v in bm.verts:
        n = v.normal; t = n.orthogonal().normalized(); b = n.cross(t)
        hit = 0.0
        for a, c in u:
            r = math.sqrt(a); phi = 2 * math.pi * c
            d = t * (r * math.cos(phi)) + b * (r * math.sin(phi)) + n * math.sqrt(1 - a)
            loc, _, _, dist = tree.ray_cast(v.co + n * 0.002, d, reach)
            if loc is not None: hit += 1 - dist / reach
        out[v.index] = 1 - hit / rays
    bm.free()
    return out

def smooth_values(x, nb, rounds=3):
    for _ in range(rounds): x = np.array([(x[i] + x[n].mean()) / 2 if n else x[i] for i, n in enumerate(nb)])
    return x

FACE = CLASSIC["face"]  # the square of the head the face texture covers, seen from the front

def face_and_masks(ob, w, L):
    me = ob.data; p = coords(ob); nb = neighbors(ob)
    n = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get("normal", n); n = n.reshape(-1, 3)
    occ = smooth_values(ao(ob), nb, 2)
    front = np.clip((-n[:, 1] + 0.05) / 0.3, 0, 1)
    face = front * np.clip((w["head"] - 0.25) / 0.3, 0, 1) * np.clip((p[:, 2] - L["neck"]) / 0.05, 0, 1)
    face = smooth_values(face, nb, 2)
    bz, bx, bh = L["belly"]
    e = (p[:, 0] / bx) ** 2 + ((p[:, 2] - bz) / bh) ** 2
    belly = np.clip((1 - e) / 0.35, 0, 1) * np.clip((-n[:, 1] - 0.1) / 0.4, 0, 1) * np.clip(w["body"] * 1.6, 0, 1)
    belly = smooth_values(belly, nb, 2)
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    rgba = np.stack([occ, face, belly, np.ones_like(occ)], 1)
    col.data.foreach_set("color", rgba.ravel()); me.color_attributes.active_color = col
    uv = me.uv_layers.new(name="UVMap")
    li = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", li)
    F = L["face"]
    uvs = np.stack([0.5 + (p[li, 0] - F["cx"]) / F["su"], 0.5 + (p[li, 2] - F["cz"]) / F["sv"]], 1)
    uv.data.foreach_set("uv", uvs.ravel())

# ---------------------------------------------------------------- rig

DEFORM = {  # the classic body's bones: (head, tail, parent). Every body's bones point the same ways.
    "root": ((0, 0, 0), (0, 0, 0.1), None),
    "body": ((0, 0.005, 0.13), (0, 0.005, 0.43), "root"),
    "head": ((0, 0, 0.43), (0, 0, 0.92), "body"),
    "ear.L": ((0.17, 0.025, 0.81), (0.215, 0.025, 0.96), "head"),
    "ear.R": ((-0.17, 0.025, 0.81), (-0.215, 0.025, 0.96), "head"),
    "arm.L": ((0.15, 0.0, 0.4), (0.25, -0.024, 0.262), "body"),
    "arm.R": ((-0.15, 0.0, 0.4), (-0.25, -0.024, 0.262), "body"),
    "hand.L": ((0.25, -0.024, 0.262), (0.29, -0.034, 0.17), "arm.L"),
    "hand.R": ((-0.25, -0.024, 0.262), (-0.29, -0.034, 0.17), "arm.R"),
    "leg.L": ((0.088, 0.0, 0.2), (0.1, -0.02, 0.03), "body"),
    "leg.R": ((-0.088, 0.0, 0.2), (-0.1, -0.02, 0.03), "body"),
    "tail": ((0.012, 0.15, 0.205), (0.02, 0.24, 0.19), "body"),
}
DIRS = {n: unit(np.subtract(t, h)) for n, (h, t, _) in DEFORM.items()}
CONTROLS = {  # face controls, read by the app as scale: lid y = open, lid x = happy squint, brow y = raise,
    # brow x = worry (inner ends up), mouth y = open, mouth x = smile, look x/y = gaze (1 = straight ahead)
    "lid.L": (0.1, -0.3, 0.66), "lid.R": (-0.1, -0.3, 0.66), "brow.L": (0.1, -0.3, 0.74), "brow.R": (-0.1, -0.3, 0.74),
    "mouth": (0, -0.3, 0.53), "look": (0, -0.3, 0.62),
}

def bone_layout(L):
    """Where a body's bones start and how long they are; their directions are the classic ones."""
    if L is CLASSIC: return DEFORM
    hs = L["head"]["r"][0] / 0.315
    out = {"root": DEFORM["root"], "body": ((0, 0.005, L["hip"]), (0, 0.005, L["neck"]), "root"),
           "head": ((0, 0, L["neck"]), (0, 0, L["neck"] + 0.49 * hs), "body")}
    def put(name, head, length, parent):
        head = np.asarray(head, float); out[name] = (tuple(head), tuple(head + DIRS[name] * length), parent)
    for s, n in ((1, "L"), (-1, "R")):
        c, r, R = ear_frame(L, s)
        put("ear." + n, c + np.array([0, 0, -0.66 * r[2]]) @ R, 0.157 * r[2] / 0.094, "head")
        a = L["arm"]
        put("arm." + n, np.array(M(a["a"], s)) + np.array([-0.008 * s, 0, 0.008]), 1.06 * np.linalg.norm(np.subtract(a["b"], a["a"])), "body")
        put("hand." + n, out["arm." + n][1], 0.1 * L["hand"]["r"][2] / 0.074, "arm." + n)
        g = L["leg"]; hip = (g["a"][0] * s, 0.0, g["a"][2] + 0.03)
        put("leg." + n, hip, (hip[2] - 0.03) / -DIRS["leg." + n][2], "body")
    t = L["tail"]
    start = np.asarray(t[0][0]) - np.array([0, 0.018, 0]) if t else np.array([0, L["body"][0][1][1] * 0.8, L["hip"] + 0.08])
    put("tail", start, 0.09, "body")
    return out

def build_rig(body, w, L):
    arm = bpy.data.armatures.new("Rig"); rig = bpy.data.objects.new("Rig", arm)
    bpy.context.collection.objects.link(rig); activate(rig)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (h, t, parent) in bone_layout(L).items():
        b = arm.edit_bones.new(name); b.head, b.tail = h, t; b.roll = 0
        if parent: b.parent = arm.edit_bones[parent]
        b.use_connect = False
    dz = L["head"]["c"][2] - CLASSIC["head"]["c"][2]
    for name, h in CONTROLS.items():
        b = arm.edit_bones.new(name); b.head = (h[0], h[1], h[2] + dz); b.tail = (h[0], h[1], h[2] + dz + 0.04)
        b.parent = arm.edit_bones["head"]; b.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    # weights from the parts: legs and feet go to legs, cheeks to the head, the rest by name
    names = ["head", "ear.L", "ear.R", "arm.L", "arm.R", "hand.L", "hand.R", "leg.L", "leg.R", "body", "tail"]
    W = np.stack([w[n] for n in names], 1)
    # a little of the body in the lower head, so the neck bends softly instead of folding
    p = coords(body); neck = np.clip(1 - np.abs(p[:, 2] - (L["neck"] + 0.01)) / 0.07, 0, 1) * W[:, 0]
    W[:, 0] -= neck * 0.35; W[:, 9] += neck * 0.35
    W /= W.sum(1, keepdims=True)
    for i, n in enumerate(names):
        g = body.vertex_groups.new(name=n)
        for v in np.nonzero(W[:, i] > 0.004)[0]: g.add([int(v)], float(W[v, i]), "REPLACE")
    body.parent = rig
    mod = body.modifiers.new("Rig", "ARMATURE"); mod.object = rig
    return rig

def skin_to(ob, rig, bone):
    g = ob.vertex_groups.new(name=bone); g.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
    ob.parent = rig; mod = ob.modifiers.new("Rig", "ARMATURE"); mod.object = rig

# ---------------------------------------------------------------- clips

def ease(x): return x * x * (3 - 2 * x)
def back(x, s=1.7): x -= 1; return x * x * ((s + 1) * x + s) + 1  # overshoots, then settles
def bump(t, a, b):  # 0 -> 1 -> 0 over [a, b]
    if t <= a or t >= b: return 0.0
    return math.sin(math.pi * (t - a) / (b - a))
def ramp(t, a, b): return ease(min(max((t - a) / (b - a), 0), 1))
def wob(t, period, phase=0.0): return math.sin(2 * math.pi * (t / period + phase))

class Spring:
    """Lags a target, overshoots a little and settles: ears, tail and hands follow the body this way."""
    def __init__(s, k=90.0, d=9.0): s.k, s.d, s.x, s.v = k, d, 0.0, 0.0
    def step(s, target, dt):
        s.v += (s.k * (target - s.x) - s.d * s.v) * dt; s.x += s.v * dt; return s.x

def clip_idle(t, T):
    f = wob(t, T); g = wob(t, T, 0.31); sway = wob(t, T / 2, 0.12) * 0.6 + wob(t, T, 0.4) * 0.4
    return dict(root_loc=(0, 0, 0.018 + 0.016 * f), body=(1.6 * g, 0, 2.2 * sway), body_s=(1 - 0.012 * f, 1 + 0.018 * f, 1 - 0.012 * f),
                head=(-1.2 * g, 3 * wob(t, T, 0.6), -2.6 * sway), arm_L=(0, 0, 6 + 3 * g), arm_R=(0, 0, -6 - 3 * wob(t, T, 0.45)),
                leg_L=(0, 0, 0), leg_R=(0, 0, 0))

def clip_talk(t, T):
    base = clip_idle(t, 4.0)
    beat = abs(wob(t, 0.26)) * 0.7 + abs(wob(t, 0.41, 0.2)) * 0.3
    pause = 0.0 if 0.55 < (t % T) / T < 0.68 else 1.0
    base.update(head=(-2 * beat * pause, 4 * wob(t, T, 0.1), -3 * wob(t, T / 2)), mouth=(1 - 0.12 * beat, 1 + 0.9 * beat * pause, 1),
                arm_L=(8 * bump(t % T, 0.1, 0.6), 0, 10 + 12 * bump(t % T, 0.1, 0.6)))
    return base

def clip_think(t, T):
    f = wob(t, T); x = t % T
    return dict(root_loc=(0, 0, 0.02 + 0.01 * f), body=(-2, 0, 3), head=(-9 + 1.5 * f, -8, 8 + 1.5 * wob(t, T, 0.3)),
                arm_R=(-78, 0, 12), hand_R=(-35, 0, 14 + 6 * bump(x, 1.2, 1.9)), arm_L=(0, 0, 4),
                look=(0.62, 1.45, 1), brow_L=(1.25, 1.25, 1), brow_R=(1.0, 1.05, 1), mouth=(0.6, 1, 1),
                lid_L=(1, 0.9, 1), lid_R=(1, 0.9, 1))

def clip_work(t, T):
    a = wob(t, T); b = wob(t, T, 0.5); nod = abs(wob(t, T / 2, 0.1))
    return dict(root_loc=(0, 0, 0.012 + 0.008 * nod), body=(4 + 1.5 * nod, 0, 1.5 * a), body_s=(1 + 0.012 * nod, 1 - 0.02 * nod, 1 + 0.012 * nod),
                head=(7 + 3 * nod, 2 * a, -1.5 * a), arm_L=(-38 + 14 * a, 0, 18), arm_R=(-38 + 14 * b, 0, -18),
                hand_L=(-20 + 10 * a, 0, 0), hand_R=(-20 + 10 * b, 0, 0), look=(1, 0.7, 1), brow_L=(1.0, 0.92, 1),
                brow_R=(1.0, 0.92, 1), mouth=(0.85, 1, 1))

def clip_point(t, T):
    up = back(ramp(t, 0.05, 0.42)); hold = wob(t, 0.9) * (t > 0.5)
    return dict(root_loc=(0, 0, 0.015), body=(0, 14 * up, 2 * up), head=(-2 * up, 20 * up, 3 * up),
                arm_L=(-72 * up + 2 * hold, -10 * up, 40 * up), hand_L=(-8 * up, 0, 0), arm_R=(0, 0, -8),
                look=(1.6, 1.0, 1), brow_L=(1, 1.12, 1), brow_R=(1, 1.12, 1), mouth=(1.05, 1.1, 1))

def clip_needs(t, T):
    x = t % T; hop = max(0.0, wob(t, T / 2)); w = wob(t, 0.4)
    land = 1 - min(hop * 4, 1)
    return dict(root_loc=(0, 0, 0.012 + 0.06 * hop), body=(0, 0, 3 * w), body_s=(1 + 0.05 * land, 1 - 0.07 * land + 0.04 * hop, 1 + 0.05 * land),
                head=(-4, 4 * w, -4 * w), arm_L=(-30, 0, 100 + 14 * w), hand_L=(0, 0, 25 * w), arm_R=(0, 0, -10),
                look=(1, 1.15, 1), brow_L=(1, 1.25, 1), brow_R=(1, 1.25, 1), mouth=(1.15, 1.35, 1))

def jump(t, a, crouch=0.16, air=0.42, land=0.18, height=0.13):
    """Squash before, stretch in the air, squash on landing. Returns (lift, squash) where squash < 0 is squashed."""
    if t < a: return 0.0, 0.0
    x = t - a
    if x < crouch: return 0.0, -0.11 * bump(x, 0, crouch * 2)
    x -= crouch
    if x < air:
        k = x / air; return height * 4 * k * (1 - k), 0.09 * (1 - abs(2 * k - 1))
    x -= air
    if x < land: return 0.0, -0.1 * bump(x, 0, land)
    return 0.0, 0.0

def clip_happy(t, T):
    lift, sq = jump(t, 0.05)
    lift2, sq2 = jump(t, 0.95, 0.1, 0.32, 0.16, 0.07)
    lift += lift2; sq += sq2
    arms = back(ramp(t, 0.1, 0.4)) * (1 - ramp(t, 1.5, 1.9))
    return dict(root_loc=(0, 0, 0.01 + lift), body_s=(1 - sq * 0.6, 1 + sq, 1 - sq * 0.6), body=(0, 0, 4 * wob(t, 0.7)),
                head=(-6 * arms, 0, 6 * wob(t, 0.7, 0.2)), arm_L=(-18 * arms, 0, 88 * arms), arm_R=(-18 * arms, 0, -88 * arms),
                hand_L=(0, 0, 20 * arms), hand_R=(0, 0, -20 * arms), lid_L=(1 + arms, 0.35 + 0.65 * (1 - arms), 1),
                lid_R=(1 + arms, 0.35 + 0.65 * (1 - arms), 1), mouth=(1.25, 1.6 * arms + 1 * (1 - arms), 1),
                brow_L=(1, 1.2, 1), brow_R=(1, 1.2, 1))

def clip_done(t, T):
    lift, sq = jump(t, 0.12, 0.14, 0.4, 0.2, 0.09)
    spin = 360 * ease(min(max((t - 0.27) / 0.45, 0), 1))
    arms = back(ramp(t, 0.15, 0.45)) * (1 - ramp(t, 1.3, 1.8))
    return dict(root_loc=(0, 0, 0.01 + lift), root=(0, 0, 0), root_spin=spin, body_s=(1 - sq * 0.6, 1 + sq, 1 - sq * 0.6),
                arm_L=(-12 * arms, 0, 95 * arms), arm_R=(-12 * arms, 0, -95 * arms), head=(-5 * arms, 0, 0),
                lid_L=(1.8 * arms + 1, 1 - 0.55 * arms, 1), lid_R=(1.8 * arms + 1, 1 - 0.55 * arms, 1), mouth=(1.3, 1.5, 1))

def clip_sad(t, T):
    f = wob(t, T); d = ramp(t, 0, 0.6) if t < T else 1
    return dict(root_loc=(0, 0, 0.004 + 0.004 * f), body=(9 * d, 0, 0), body_s=(1 + 0.03 * d, 1 - 0.05 * d, 1 + 0.03 * d),
                head=(16 * d + 1.5 * f, 0, 4 * d), arm_L=(6 * d, 0, -4 * d), arm_R=(6 * d, 0, 4 * d), ear_L=(0, 0, -28 * d),
                ear_R=(0, 0, 28 * d), lid_L=(1, 1 - 0.38 * d, 1), lid_R=(1, 1 - 0.38 * d, 1), brow_L=(1.45 * d + (1 - d), 0.95, 1),
                brow_R=(1.45 * d + (1 - d), 0.95, 1), mouth=(0.82, 1, 1), look=(1, 0.45, 1))

def clip_wave(t, T):
    up = back(ramp(t, 0.0, 0.3)) * (1 - ramp(t, T - 0.35, T)); w = wob(t, 0.36) * up
    return dict(root_loc=(0, 0, 0.012 + 0.012 * abs(wob(t, 0.72))), body=(0, 0, -4 * up), head=(-3 * up, 0, 6 * up),
                arm_R=(-24 * up, 0, -100 * up - 14 * w), hand_R=(0, 0, -28 * w), arm_L=(0, 0, 8),
                mouth=(1.15, 1.3, 1), brow_L=(1, 1.15, 1), brow_R=(1, 1.15, 1), lid_L=(1 + 0.5 * up, 1, 1), lid_R=(1 + 0.5 * up, 1, 1))

def clip_admire(t, T):
    down = ramp(t, 0.1, 0.5) * (1 - ramp(t, 1.7, 2.1)); turn = wob(t, 1.6) * ramp(t, 0.5, 0.8) * (1 - ramp(t, 1.6, 2.0))
    arm = bump(t, 0.6, 1.7)
    return dict(root_loc=(0, 0, 0.012), body=(5 * down, 18 * turn, 0), head=(24 * down, 12 * turn, 6 * turn),
                arm_L=(-30 * arm, 0, 30 * arm), arm_R=(-30 * arm, 0, -30 * arm), look=(1 - 0.2 * turn, 0.3 * down + (1 - down), 1),
                brow_L=(1, 1.2 * down + (1 - down), 1), brow_R=(1, 1.2 * down + (1 - down), 1), mouth=(0.7 + 0.3 * (1 - down), 1, 1))

def clip_pop(t, T):
    s = back(ramp(t, 0.0, 0.42), 2.4)
    return dict(root_loc=(0, 0, 0.012 + 0.1 * bump(t, 0.0, 0.42)), root_s=(max(s, 0.001),) * 3,
                body_s=(1 + 0.08 * bump(t, 0.36, 0.6), 1 - 0.1 * bump(t, 0.36, 0.6), 1 + 0.08 * bump(t, 0.36, 0.6)),
                arm_L=(0, 0, 40 * bump(t, 0.3, 0.8)), arm_R=(0, 0, -40 * bump(t, 0.3, 0.8)), mouth=(1.1, 1.2, 1))

CLIPS = {  # name: (function, seconds, loops)
    "idle": (clip_idle, 4.2, True), "talk": (clip_talk, 2.4, True), "think": (clip_think, 3.6, True),
    "work": (clip_work, 1.05, True), "point": (clip_point, 1.6, False), "needs": (clip_needs, 1.6, True),
    "happy": (clip_happy, 2.0, False), "done": (clip_done, 2.0, False), "sad": (clip_sad, 3.2, True),
    "wave": (clip_wave, 1.9, False), "admire": (clip_admire, 2.3, False), "pop": (clip_pop, 0.9, False),
}


# Each official companion's own idle and gesture, on the shared bones.

def hazel_idle(t, T):  # whisking at her chest in quick little circles, head tipping now and then to check the recipe
    p = clip_idle(t, T); c = wob(t, 0.6); s = wob(t, 0.6, 0.25); peek = bump(t % T, 2.4, 4.2)
    p.update(arm_R=(-65 + 8 * c, 0, 20 + 8 * s), hand_R=(58 + 8 * s, 0, 15 + 6 * c), body=(2 + 1.5 * c, 0, p["body"][2]),
             head=(5 + 3 * peek + 1.5 * wob(t, T / 2, 0.6), 12 * peek - 2, -9 * peek + 1.5 * c), look=(1 + 0.45 * peek, 0.75 - 0.15 * peek, 1),
             lid_L=(1, 0.93, 1), lid_R=(1, 0.93, 1), brow_L=(1, 1.06 + 0.15 * peek, 1), brow_R=(1, 1.06, 1), mouth=(0.95, 1, 1))
    return p

def hazel_gesture(t, T):  # done: lifts the whisk up beside her face, proud of it, with a little hop
    up = back(ramp(t, 0.1, 0.5)) * (1 - ramp(t, 1.8, 2.3)); lift, sq = jump(t, 0.3, 0.12, 0.3, 0.14, 0.05); w = wob(t, 0.3) * bump(t, 0.6, 1.7)
    p = hazel_idle(t, 4.8)
    p.update(root_loc=(0, 0, 0.018 + lift), body_s=(1 - sq * 0.6, 1 + sq, 1 - sq * 0.6), body=(0, -4 * up, -3 * up),
             arm_R=(-65 - 45 * up, 0, 20 - 20 * up), hand_R=(58 + 12 * up, 0, 15 - 65 * up + 12 * w), head=(-6 * up, 6 * up, -8 * up),
             look=(1 - 0.25 * up, 1 + 0.15 * up, 1), lid_L=(1 + 0.9 * up, 1 - 0.35 * up, 1), lid_R=(1 + 0.9 * up, 1 - 0.35 * up, 1),
             brow_L=(1, 1.06 + 0.25 * up, 1), brow_R=(1, 1.06 + 0.25 * up, 1), mouth=(0.95 + 0.3 * up, 1 + 0.45 * up, 1))
    return p

def rio_idle(t, T):  # can't stand still: a bounce, leaning one way and then the other
    b = abs(wob(t, T / 2)); s = wob(t, T / 2)
    return dict(root_loc=(0.008 * s, 0, 0.014 + 0.022 * b), body=(1.5, 0, 5 * s),
                body_s=(1 + 0.02 * (1 - b), 1 - 0.03 * (1 - b), 1 + 0.02 * (1 - b)), head=(-2, 4 * s, -5 * s),
                arm_L=(-10 * s, 0, 14 + 6 * b), arm_R=(10 * s - 20, 0, -14 - 6 * b), hand_R=(-10, 0, 0),
                mouth=(1.12, 1.05, 1), lid_L=(1.15, 1, 1), lid_R=(1.15, 1, 1), brow_L=(1, 1.1, 1), brow_R=(1, 1.1, 1))

def rio_gesture(t, T):  # found one: the price tag goes up, with a hop
    lift, sq = jump(t, 0.25, 0.12, 0.34, 0.16, 0.08)
    up = back(ramp(t, 0.05, 0.35)) * (1 - ramp(t, 1.35, 1.8))
    return dict(root_loc=(0, 0, 0.012 + lift), body_s=(1 - sq * 0.6, 1 + sq, 1 - sq * 0.6), body=(0, 0, -5 * up),
                arm_R=(-30 * up, 0, -130 * up), hand_R=(0, 0, -20 * up + 12 * wob(t, 0.3) * up), arm_L=(0, 0, 12 + 10 * up),
                head=(-6 * up, -8 * up, 8 * up), look=(1 - 0.4 * up, 1 + 0.3 * up, 1), lid_L=(1 + 0.9 * up, 1 - 0.4 * up, 1),
                lid_R=(1 + 0.9 * up, 1 - 0.4 * up, 1), mouth=(1.3, 1 + 0.7 * up, 1), brow_L=(1, 1.25, 1), brow_R=(1, 1.25, 1))

def juno_idle(t, T):  # clipboard up, pencil tapping while she reads down the list
    p = clip_idle(t, T); x = t % T
    tap = bump(x, 1.0, 1.18) + bump(x, 1.3, 1.48) + bump(x, 3.0, 3.18)
    p.update(arm_L=(-42, 0, -22), hand_L=(-18, 0, -10), arm_R=(-40 + 6 * tap, 0, 8), hand_R=(-30 - 18 * tap, 0, 0),
             head=(6 + 2 * tap, 3 * wob(t, T, 0.6), -2), look=(0.85, 0.65, 1), brow_L=(1, 0.96, 1), brow_R=(1, 1.02, 1), mouth=(0.95, 1, 1))
    return p

def juno_gesture(t, T):  # ticks a box, nods, pleased
    p = juno_idle(t, 4.0)
    tick = bump(t, 0.25, 0.45) - 0.6 * bump(t, 0.45, 0.7); nod = bump(t, 0.7, 1.15); joy = ramp(t, 0.6, 0.8) * (1 - ramp(t, 1.3, 1.6))
    p.update(arm_R=(-46 - 10 * tick, 0, 8 + 30 * tick), hand_R=(-40 - 30 * tick, 0, 20 * tick), head=(6 + 10 * nod, 0, 4 * joy),
             lid_L=(1 + 0.8 * joy, 1 - 0.3 * joy, 1), lid_R=(1 + 0.8 * joy, 1 - 0.3 * joy, 1), mouth=(0.95 + 0.3 * joy, 1 + 0.2 * joy, 1))
    return p

def bram_idle(t, T):  # headphones on, popcorn at his tummy: nodding to the beat, a foot tapping, and now and then a puff
    beat = (t % 0.5) / 0.5; nod = math.exp(-beat * 6); s = wob(t, 1.0); x = t % T
    dip = bump(x, 1.9, 2.45); up = bump(x, 2.35, 2.85); chew = ramp(x, 2.75, 2.9) * (1 - ramp(x, 3.45, 3.75)); bite = abs(wob(x, 0.44)) * chew
    beat_on = 1 - 0.7 * bump(x, 1.85, 3.8)  # he eases off the nodding while he eats
    return dict(root_loc=(0, 0, 0.012 + 0.006 * (1 - nod) * beat_on), body=(2 + 2 * nod * beat_on, 0, 3 * s),
                head=(4 + 7 * nod * beat_on - 9 * up + 3 * dip, 6 * wob(t, T, 0.2), -5 * s), arm_L=(-20, 0, -20), hand_L=(19, 0, 21),  # keeps the bucket upright
                arm_R=(-4 + 4 * s - 46 * dip - 91 * up, 0, -8 - 4 * nod + 113 * dip + 8 * up), hand_R=(10 * dip - 20 * up, 0, 0),
                leg_R=(-10 * nod * beat_on * (int(round(t / 0.5 - beat)) % 2), 0, 0), look=(1 + 0.3 * dip, 1 - 0.5 * dip, 1),
                lid_L=(1 + 0.7 * chew, 0.8 - 0.2 * chew + 0.25 * up, 1), lid_R=(1 + 0.7 * chew, 0.8 - 0.2 * chew + 0.25 * up, 1),
                mouth=(1.08 + 0.15 * chew, 1 + 0.9 * up - 0.25 * bite, 1), brow_L=(1, 1.02 + 0.2 * up, 1), brow_R=(1, 1.02 + 0.2 * up, 1))

def bram_gesture(t, T):  # want some? holds the bucket out to you, head tipped, eyebrows up
    up = back(ramp(t, 0.05, 0.35)) * (1 - ramp(t, 1.15, 1.55)); lift, sq = jump(t, 0.02, 0.08, 0.2, 0.12, 0.03)
    return dict(root_loc=(0, 0.02 * up, 0.012 + lift), body_s=(1 - sq * 0.6, 1 + sq, 1 - sq * 0.6), body=(8 * up, 0, 0),
                arm_L=(-20 - 57 * up, 0, -20 + 12 * up), hand_L=(19 + 58 * up, -2 * up, 21 - 14 * up), arm_R=(-10 * up, 0, -8 - 18 * up),
                head=(-4 * up, 0, -9 * up), look=(1, 1 + 0.1 * up, 1), lid_L=(1 + 0.4 * up, 1 + 0.12 * up, 1), lid_R=(1 + 0.4 * up, 1 + 0.12 * up, 1),
                brow_L=(1, 1 + 0.4 * up, 1), brow_R=(1, 1 + 0.4 * up, 1), mouth=(1.1 + 0.15 * up, 1 + 0.5 * up, 1))

def wren_idle(t, T):  # daydreaming, quill at her cheek, a slow sigh now and then
    p = clip_idle(t, T); s = wob(t, T); sigh = bump(t % T, 2.6, 3.9)
    p.update(head=(-4 + 2 * sigh, 6 + 2 * s, 9 + 3 * s), body=(0, 2 * s, 3 * s), body_s=(1 + 0.02 * sigh, 1 + 0.025 * sigh, 1 + 0.02 * sigh),
             arm_R=(-70, 0, 18), hand_R=(-40, 0, 12), arm_L=(0, 0, 8),
             lid_L=(1, 0.72 - 0.12 * sigh, 1), lid_R=(1, 0.72 - 0.12 * sigh, 1), look=(1.2, 1.25, 1), brow_L=(1.15, 1.05, 1), brow_R=(1.15, 1.05, 1),
             mouth=(0.95, 1, 1))
    return p

def wren_gesture(t, T):  # a flourish: the quill writes a loop in the air
    p = wren_idle(t, 5.0); a = ramp(t, 0.15, 1.45); env = bump(t, 0.1, 1.8); ang = 2 * math.pi * a
    p.update(arm_R=(-70 - 35 * env * math.sin(ang), 0, 18 - 40 * env * (1 - math.cos(ang)) / 2), hand_R=(-40 + 30 * env * math.cos(ang), 0, 12),
             head=(-2, 10 * env * math.sin(ang), 9), lid_L=(1, 0.75 + 0.3 * env, 1), lid_R=(1, 0.75 + 0.3 * env, 1), mouth=(1.1, 1 + 0.3 * env, 1))
    return p

def pip_idle(t, T):  # eager: up on its toes, ears twitching, looking for the next story
    b = abs(wob(t, T / 2)); x = t % T; tw = bump(x, 0.6, 0.72) + bump(x, 1.5, 1.6)
    return dict(root_loc=(0, 0, 0.014 + 0.016 * b), body=(6, 0, 2 * wob(t, T)), head=(-6, 8 * wob(t, T, 0.1), -3 * wob(t, T)),
                arm_L=(-14, 0, 12), arm_R=(-30 + 6 * b, 0, -10), hand_R=(-20, 0, 0), ear_L=(0, 0, 14 * tw), ear_R=(0, 0, -8 * tw),
                look=(1 + 0.3 * wob(t, T, 0.1), 1.1, 1), lid_L=(1, 1.08, 1), lid_R=(1, 1.08, 1), brow_L=(1, 1.15, 1), brow_R=(1, 1.15, 1),
                mouth=(1.05, 1.1, 1))

def pip_gesture(t, T):  # waves the paper over its head
    up = back(ramp(t, 0.05, 0.3)) * (1 - ramp(t, 1.35, 1.8)); w = wob(t, 0.32) * up; lift, sq = jump(t, 0.1, 0.1, 0.3, 0.14, 0.07)
    return dict(root_loc=(0, 0, 0.014 + lift), body_s=(1 - sq * 0.6, 1 + sq, 1 - sq * 0.6), body=(0, 0, -4 * up),
                arm_R=(-28 * up, 0, -120 * up - 14 * w), hand_R=(0, 0, -30 * w), arm_L=(0, 0, 14 * up),
                head=(-6 * up, 0, 6 * up), mouth=(1.2, 1 + 0.9 * up, 1), brow_L=(1, 1.3, 1), brow_R=(1, 1.3, 1), lid_L=(1, 1.1, 1), lid_R=(1, 1.1, 1))

OWN = {  # name: {clip: (function, seconds, loops)}
    "hazel": {"idle": (hazel_idle, 4.8, True), "gesture": (hazel_gesture, 2.4, False)},
    "rio": {"idle": (rio_idle, 3.0, True), "gesture": (rio_gesture, 1.8, False)},
    "juno": {"idle": (juno_idle, 4.0, True), "gesture": (juno_gesture, 1.6, False)},
    "bram": {"idle": (bram_idle, 4.0, True), "gesture": (bram_gesture, 1.6, False)},
    "wren": {"idle": (wren_idle, 5.0, True), "gesture": (wren_gesture, 2.0, False)},
    "pip": {"idle": (pip_idle, 2.0, True), "gesture": (pip_gesture, 1.8, False)},
}

# The blink: shut in 70 ms, easing in; held two frames; open again in 110 ms, easing out. Keyed four times slower than it
# plays, so 30 fps keys still catch its curve; the app plays it back at BLINK_STRETCH times speed.
BLINK = (0.07, 0.05, 0.11)
BLINK_STRETCH = 4

def blink_open(t):
    c, h, o = BLINK
    if t < c: x = t / c; return 1 - x * x
    if t < c + h: return 0.0
    if t < c + h + o: x = (t - c - h) / o; return 1 - (1 - x) * (1 - x)
    return 1.0

def bake(rig, clips):
    pb = rig.pose.bones
    rest = {b.name: b.bone.matrix_local.to_3x3() for b in pb}
    for b in pb: b.rotation_mode = "QUATERNION"
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    rig.animation_data_create()
    def world_rot(name, deg):  # rotation given in the armature's axes (x: nod, y: turn... see below), turned into the bone's
        r = Euler([math.radians(a) for a in deg], "XYZ").to_matrix()
        R = rest[name]; return (R.inverted() @ r @ R).to_quaternion()
    for clip, (fn, T, loops) in clips.items():
        act = bpy.data.actions.new(clip); act.use_fake_user = True
        rig.animation_data.action = act
        frames = int(round(T * FPS)) + 1
        springs = {k: Spring() for k in ("earL", "earR", "tail", "handL", "handR")}
        warm = frames * 2 if loops else 0  # loops run twice first, so the springs start where they end
        prev = None
        for i in range(-warm, frames):
            t = (i % (frames - 1)) / FPS if loops else max(i, 0) / FPS
            pose = fn(t, T)
            lift = pose.get("root_loc", (0, 0, 0))[2]; sway = pose.get("body", (0, 0, 0))[2]
            nod = pose.get("head", (0, 0, 0))[0]
            vel = 0.0 if prev is None else (lift - prev[0]) * FPS
            swv = 0.0 if prev is None else (sway - prev[1])
            prev = (lift, sway)
            kick = lambda g, lim: max(-lim, min(lim, g))
            e = springs["earL"].step(kick(-vel * 60, 30) + swv * 6 - nod * 0.15, 1 / FPS)
            e2 = springs["earR"].step(kick(-vel * 55, 30) - swv * 6 - nod * 0.15, 1 / FPS)
            tl = springs["tail"].step(kick(-vel * 80, 35) + sway * 4, 1 / FPS)
            hl = springs["handL"].step(kick(-vel * 50, 25), 1 / FPS); hr = springs["handR"].step(kick(-vel * 50, 25), 1 / FPS)
            if i < 0: continue
            f = i + 1
            for b in pb:
                b.location = (0, 0, 0); b.rotation_quaternion = (1, 0, 0, 0); b.scale = (1, 1, 1)
            # Pose angles, in degrees: x tips forward (+), y turns toward the character's left (+, the viewer's right),
            # z leans to the character's right (+). For arms x swings them forward (-) or back, and z lifts the left arm out
            # (+) and the right arm out (-). In Blender's axes x stays, the lean is about Y and the turn about Z:
            conv = lambda d: (d[0], -d[2], d[1])
            for bone, key in (("body", "body"), ("head", "head"), ("arm.L", "arm_L"), ("arm.R", "arm_R"), ("hand.L", "hand_L"),
                              ("hand.R", "hand_R"), ("leg.L", "leg_L"), ("leg.R", "leg_R"), ("ear.L", "ear_L"), ("ear.R", "ear_R"), ("tail", "tail")):
                v = pose.get(key, (0, 0, 0))
                extra = {"ear.L": (0, 0, e), "ear.R": (0, 0, -e2), "tail": (tl, 0, 0), "hand.L": (0, 0, -hl), "hand.R": (0, 0, hr)}.get(bone, (0, 0, 0))
                v = [a + b for a, b in zip(v, extra)]
                pb[bone].rotation_quaternion = world_rot(bone, conv(v))
            rl = pose.get("root_loc", (0, 0, 0))
            pb["root"].location = rest["root"].inverted() @ Vector((rl[0], -rl[1], rl[2]))
            if "root_spin" in pose: pb["root"].rotation_quaternion = world_rot("root", (0, 0, pose["root_spin"]))
            if "root_s" in pose: pb["root"].scale = pose["root_s"]
            if "body_s" in pose: pb["body"].scale = pose["body_s"]
            for c in ("lid_L", "lid_R", "brow_L", "brow_R", "mouth", "look"):
                if c in pose:
                    s = pose[c]; pb[c.replace("_", ".")].scale = (s[0], s[1], 1)
            pb["root"].keyframe_insert("location", frame=f)  # only the root moves; every other bone just turns and squashes
            for b in pb:
                b.keyframe_insert("rotation_quaternion", frame=f); b.keyframe_insert("scale", frame=f)
        act.frame_range = (1, frames)
    for b in pb: b.location = (0, 0, 0); b.rotation_quaternion = (1, 0, 0, 0); b.scale = (1, 1, 1)

def bake_blink(rig):
    pb = rig.pose.bones
    act = bpy.data.actions.new("blink"); act.use_fake_user = True; rig.animation_data.action = act
    frames = int(round(sum(BLINK) * BLINK_STRETCH * FPS)) + 2
    for i in range(frames):
        o = blink_open(i / FPS / BLINK_STRETCH)
        for n in ("lid.L", "lid.R"):
            pb[n].scale = (1, o, 1); pb[n].keyframe_insert("scale", frame=i + 1)
    act.frame_range = (1, frames)
    for n in ("lid.L", "lid.R"): pb[n].scale = (1, 1, 1)

# ---------------------------------------------------------------- hair

HC = np.array(CLASSIC["head"]["c"]); HR = np.array(CLASSIC["head"]["r"]); TOP = HC[2] + HR[2]

def head0(p): return head_sdf(p, CLASSIC)  # the round head, cheeks and all

def direction(theta, phi):
    """theta from the top (0) down, phi around from the front (0) toward the character's left (+)."""
    return np.array([math.sin(theta) * math.sin(phi), -math.sin(theta) * math.cos(phi), math.cos(theta)])

def surf_dir(d, out=0.0):
    d = unit(d); lo, hi = 0.0, 0.9
    for _ in range(40):
        m = (lo + hi) / 2
        if head0((HC + d * m)[None])[0] < 0: lo = m
        else: hi = m
    return HC + d * (lo + out)

def surf(theta, phi, out=0.0): return surf_dir(direction(theta, phi), out)

def over(a, b, out0, out1, n=4):
    """Points along the head from a to b (points or (theta, phi) pairs), out0 above the skin at the start and out1 at the end."""
    da = unit((surf(*a) if len(a) == 2 else np.asarray(a)) - HC); db = unit((surf(*b) if len(b) == 2 else np.asarray(b)) - HC)
    return [surf_dir(da * (1 - t) + db * t, out0 + (out1 - out0) * t) for t in np.linspace(0, 1, n)]

def fall(p0, d0, length, n=4, g=0.5):
    """Points from p0 heading along d0 and bending down under gravity."""
    pts = [np.asarray(p0, float)]; d = unit(d0); step = length / n
    for _ in range(n):
        d = unit(d + np.array([0, 0, -g])); pts.append(pts[-1] + d * step)
    return pts

def spline(ctrl, n=5):
    """A Catmull-Rom curve through the control points, n samples per span."""
    P = [np.asarray(c, float) for c in ctrl]; P = [P[0]] + P + [P[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for j in range(n):
            t = j / n
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return np.array(out)

def spread(n, th_max, turn=0.0):
    """About n evenly spread (theta, phi) points over the top of the head, down to th_max."""
    g = math.pi * (3 - math.sqrt(5)); out = []
    for i in range(n):
        th = math.acos(1 - (i + 0.5) / n * (1 - math.cos(th_max))); ph = (i * g + turn) % (2 * math.pi) - math.pi
        out.append((th, ph))
    return out

def frac(x): return x - np.floor(x)

class Lock:
    """A lock of hair: a tube along a smooth path, tapering from r0 to r1 and flattened against the head."""
    k = 0.012
    def __init__(s, ctrl, r0, r1, flat=0.6, n=5, k=None):
        s.pts = spline(ctrl, n); s.r0, s.r1, s.flat = r0, r1, flat
        seg = np.linalg.norm(np.diff(s.pts, axis=0), axis=1); s.cum = np.concatenate([[0], np.cumsum(seg)]); s.len = max(s.cum[-1], 1e-6)
        if k: s.k = k
    def box(s):
        r = max(s.r0, s.r1); return s.pts.min(0) - r, s.pts.max(0) + r
    def eval(s, p, full=False):
        best = np.full(len(p), 9.0); u = v = None
        if full: u = np.zeros(len(p)); v = np.zeros(len(p))
        for i in range(len(s.pts) - 1):
            a, b = s.pts[i], s.pts[i + 1]; L = np.linalg.norm(b - a)
            if L < 1e-7: continue
            t = (b - a) / L
            pa = p - a; h = np.clip(pa @ t / L, 0, 1)
            q = pa - (h * L)[:, None] * t
            n = (a + b) / 2 - HC; n = n - (n @ t) * t
            n = unit(n) if np.linalg.norm(n) > 1e-4 else unit(np.cross(t, (1, 0, 0)))
            side = np.cross(t, n)
            qa, qn, qs = q @ t, q @ n, q @ side
            f = (s.cum[i] + h * L) / s.len
            d = np.sqrt(qa * qa + qs * qs + (qn / s.flat) ** 2) - (s.r0 + (s.r1 - s.r0) * f)
            m = d < best; best = np.where(m, d, best)
            if full: u = np.where(m, np.arctan2(qn, qs) / (2 * math.pi) + 0.5, u); v = np.where(m, f * s.len * 6, v)
        return (best, u, v) if full else best

class Cap:
    """The scalp: a thin layer over the head that thins out and dives under the skin at the hairline.
    line: [(phi, z)] the hairline's height going round from the front (phi 0) to the back (pi)."""
    k = 0.014
    def __init__(s, out, line, dive=0.07): s.out = out; s.line = np.array(line, float); s.dive = dive
    def box(s):
        lo = HC - HR - s.out - 0.05; hi = HC + HR + s.out + 0.03; lo[2] = s.line[:, 1].min() - 0.03; return lo, hi
    def eval(s, p, full=False):
        z0 = np.interp(np.abs(np.arctan2(p[:, 0], -p[:, 1])), s.line[:, 0], s.line[:, 1])
        k = np.clip((p[:, 2] - z0) / s.dive, 0, 1); k = k * k * (3 - 2 * k)
        d = smax(head0(p) - s.out * (k * 1.3 - 0.3), z0 - 0.012 - p[:, 2], 0.01)
        if not full: return d
        q = p - HC; th = np.arccos(np.clip(q[:, 2] / np.linalg.norm(q, axis=1), -1, 1))
        return d, np.arctan2(q[:, 0], -q[:, 1]) / (2 * math.pi) * 16, th * 0.3 * 6

class Blob:
    k = 0.03
    def __init__(s, c, r, k=None):
        s.c = np.asarray(c, float); s.r = np.asarray(r if hasattr(r, "__len__") else (r, r, r), float)
        if k: s.k = k
    def box(s): return s.c - s.r, s.c + s.r
    def eval(s, p, full=False):
        d = ellipsoid(p, s.c, s.r)
        if not full: return d
        q = p - s.c; th = np.arccos(np.clip(q[:, 2] / np.maximum(np.linalg.norm(q, axis=1), 1e-9), -1, 1))
        return d, np.arctan2(q[:, 0], -q[:, 1]) / (2 * math.pi) * 4, th * s.r.mean() * 6

class Raw:
    k = 0.015
    def __init__(s, fn, lo, hi): s.fn = fn; s.lo, s.hi = np.asarray(lo), np.asarray(hi)
    def box(s): return s.lo, s.hi
    def eval(s, p, full=False):
        d = s.fn(p)
        return (d, frac(p[:, 0] * 20), p[:, 2] * 6) if full else d

def style_fn(prims):
    def fn(p):
        d = None
        for pr in prims:
            e = pr.eval(p); d = e if d is None else smin(d, e, pr.k)
        return d
    return fn

def line(front, side, back): return [(0, front), (0.6, front), (1.35, side), (2.3, back), (math.pi, back)]

# The styles. Each has to read at a glance, at 40 pixels as well as 400: big shapes first, locks for texture.

def tuft():
    pr = [Cap(0.016, line(0.8, 0.7, 0.66))]
    for ph, h, lean, r in ((0.0, 0.15, 0.0, 0.05), (0.5, 0.1, 1.0, 0.04), (-0.45, 0.09, -1.0, 0.037)):
        a = surf(0.45, ph, 0.0); b = surf(0.18, ph * 0.5, 0.03)
        c = b + np.array([lean * 0.04, -0.03, h]); d = c + np.array([lean * 0.035, 0.055, 0.012])
        pr.append(Lock([a, b, c, d], r, 0.011, flat=0.78))
    for ph in np.linspace(-2.8, 2.8, 10):  # short combed locks, so the crop isn't a shell
        end = 0.95 if abs(ph) < 0.7 else 1.2
        pr.append(Lock(over((0.12, ph * 0.3), (end, ph), 0.012, 0.004), 0.026, 0.015, flat=0.45))
    return pr

def sprout():
    tip = np.array([0, 0, TOP])
    def fn(p):
        stem = cone(p, tip - np.array([0, 0, 0.03]), tip + np.array([0.0, 0.0, 0.1]), 0.014, 0.011)
        leaf = ellipsoid(p, tip + np.array([0.055, 0.0, 0.125]), (0.062, 0.013, 0.03), rot_y(-0.5).T)
        leaf2 = ellipsoid(p, tip + np.array([-0.04, 0.005, 0.105]), (0.045, 0.012, 0.024), rot_y(0.6).T)
        return smin(smin(stem, leaf, 0.015), leaf2, 0.015)
    return [Raw(fn, tip - np.array([0.15, 0.08, 0.06]), tip + np.array([0.15, 0.08, 0.2]))]

def swoop():
    pr = [Cap(0.02, line(0.82, 0.68, 0.64))]
    part = 0.55  # the parting, over the left eye
    for i, th in enumerate(np.linspace(0.2, 0.6, 6)):  # the fringe sweeps across and flicks out past the right temple
        ctrl = over((th, part), (0.84 + 0.05 * i, -0.95 - 0.13 * i), 0.016, 0.026, 4)
        ctrl.append(ctrl[-1] + unit(ctrl[-1] - HC) * 0.035 + np.array([0, 0, -0.012]))
        pr.append(Lock(ctrl, 0.036, 0.012, flat=0.55))
    for ph in np.linspace(1.25, 5.0, 10):  # the rest falls back from the parting, round the left, the back and the right
        end = ph if ph <= math.pi else ph - 2 * math.pi
        pr.append(Lock(over((0.2, part), (1.2 + 0.25 * math.sin(min(ph, 5.0) / 2) ** 2, end), 0.016, 0.01, 5), 0.032, 0.015, flat=0.5))
    return pr

def curls():
    pr = [Cap(0.014, line(0.82, 0.7, 0.64))]
    rng = np.random.default_rng(5)
    for th, ph in spread(30, 1.35, 0.4):
        if abs(ph) < 0.75 and th > 0.88: continue  # keep the forehead clear
        if th > 1.15 and abs(ph) < 2.0: continue
        c = surf(th, ph, 0.024); n = unit(c - HC)
        t = unit(np.cross(n, rng.normal(size=3))); r = 0.022 + 0.006 * rng.random()
        pts = [c + (t * math.cos(a) + n * math.sin(a)) * r for a in np.linspace(-1.9, 3.2, 7) + rng.random() * 0.5]
        pr.append(Lock(pts, 0.018, 0.013, flat=0.9, n=3, k=0.008))
    return pr

def bob():
    pr = [Cap(0.03, [(0, 0.8), (0.62, 0.79), (1.2, 0.54), (math.pi, 0.5)])]
    for ph in np.linspace(-0.55, 0.55, 6):  # bangs straight across the forehead
        ctrl = over((0.06, ph * 0.3), (0.98, ph), 0.03, 0.032, 4); ctrl.append(ctrl[-1] + np.array([0, -0.012, -0.022]))
        pr.append(Lock(ctrl, 0.036, 0.02, flat=0.55))
    for ph in list(np.linspace(1.0, math.pi, 7)) + list(np.linspace(-1.0, -math.pi + 0.3, 6)):  # the rest falls and turns under
        ctrl = over((0.06, ph * 0.3), (1.6, ph), 0.03, 0.036, 4)
        lo = surf(2.02, ph, 0.042); tip = lo + unit(HC - lo) * 0.032 + np.array([0, 0, -0.008])
        pr.append(Lock(ctrl + [lo, tip], 0.042, 0.022, flat=0.55))
    return pr

def spiky():
    pr = [Cap(0.016, line(0.8, 0.7, 0.66))]
    for th, ph, ln, r in ((0.05, 0, 0.15, 0.05), (0.5, -0.5, 0.13, 0.045), (0.5, 0.45, 0.13, 0.045), (0.64, 0.0, 0.12, 0.045),
                          (0.55, 1.5, 0.13, 0.045), (0.55, -1.5, 0.13, 0.045), (0.62, 2.4, 0.14, 0.045), (0.62, -2.4, 0.14, 0.045),
                          (0.68, math.pi, 0.13, 0.045), (0.3, 0.95, 0.12, 0.042), (0.3, -2.0, 0.13, 0.042)):
        a = surf(th, ph, -0.004); n = unit(a - HC)
        d = unit(n + np.array([0, 0.25, 0.35]))  # swept up and back
        pr.append(Lock([a, a + d * ln * 0.5, a + unit(d + np.array([0, 0.15, 0.1])) * ln], r, 0.008, flat=0.72))
    return pr

def bun():
    pr = [Cap(0.018, line(0.85, 0.72, 0.6))]  # pulled back: the forehead stays clear
    top = surf(0.32, math.pi, 0.0); ax = unit(top - HC + np.array([0, 0, 0.12]))
    for ph in np.linspace(-math.pi, math.pi, 14, endpoint=False):  # everything combed up toward the bun
        th0 = 0.8 if abs(ph) < 0.7 else (1.08 if abs(ph) < 2.0 else 1.28)
        # each lock starts under the scalp, so the cap's edge is the hairline and no lock end hangs past it
        pr.append(Lock(over((th0, ph), top, -0.014, 0.02, 5), 0.03, 0.022, flat=0.5))
    t1 = unit(np.cross(ax, (1, 0, 0))); t2 = np.cross(ax, t1)
    coil = [top + ax * (0.03 + 0.03 * a / (4 * math.pi)) + (t1 * math.cos(a) + t2 * math.sin(a)) * (0.05 - 0.02 * a / (4 * math.pi))
            for a in np.linspace(0, 4 * math.pi, 14)]
    pr.append(Lock(coil, 0.036, 0.026, flat=1.0, n=3, k=0.01))
    pr.append(Blob(top + ax * 0.05, (0.04, 0.04, 0.035)))
    for s in (1, -1):  # two short strands that got loose at the temples
        pr.append(Lock(over((0.86, 0.8 * s), (1.18, 0.9 * s), 0.004, 0.02, 4), 0.016, 0.01, flat=0.7, k=0.008))
    return pr

def ponytail():
    pr = [Cap(0.02, line(0.82, 0.7, 0.6))]
    G = surf(0.95, math.pi, 0.03); out = unit(G - HC)
    for ph in np.linspace(-2.7, 2.7, 11):  # combed back to where it's tied
        a = (0.95 if abs(ph) < 0.6 else 1.15, ph)
        pr.append(Lock(over(a, G, 0.008, 0.03, 5), 0.03, 0.022, flat=0.5))
    pr.append(Blob(G + out * 0.012, (0.045, 0.04, 0.045)))
    for off in (-0.022, 0.0, 0.022):
        p0 = G + out * 0.02 + np.array([off, 0, 0.004])
        pr.append(Lock(fall(p0, out + np.array([off * 4, 0, 0.45]), 0.32, 5, 0.42), 0.036, 0.011, flat=0.75, k=0.012))
    return pr

def pigtails():
    pr = [Cap(0.02, line(0.82, 0.66, 0.58))]
    for s in (1, -1):
        G = surf(1.32, s * 2.0, 0.03); out = unit(G - HC)
        for th, ph in ((0.85, 0.0), (0.45, 0.0), (0.08, 0.0), (0.4, math.pi), (0.8, math.pi), (1.2, math.pi)):  # from the parting
            pr.append(Lock(over((th, ph + s * 0.12), G, 0.01, 0.028, 5), 0.03, 0.022, flat=0.5))
        pr.append(Blob(G + out * 0.01, (0.04, 0.04, 0.04)))
        for off in (-0.016, 0.016):
            p0 = G + out * 0.02 + np.array([0, off, 0])
            pr.append(Lock(fall(p0, out + np.array([s * 0.2, 0, 0.3]), 0.26, 4, 0.5), 0.034, 0.012, flat=0.75))
    return pr

def cloud():
    pr = [Cap(0.045, line(0.83, 0.64, 0.56))]
    rng = np.random.default_rng(11)
    for th, ph in spread(34, 1.5, 0.2):
        if abs(ph) < 0.7 and th > 0.82: continue
        if th > 1.2 and abs(ph) < 1.9: continue
        r = 0.068 + 0.026 * rng.random()
        pr.append(Blob(surf(th, ph, 0.045 + 0.02 * rng.random()), (r, r, r * 0.9)))
    return pr

HAIR = {"tuft": tuft, "sprout": sprout, "swoop": swoop, "curls": curls, "bob": bob, "spiky": spiky, "bun": bun,
        "ponytail": ponytail, "pigtails": pigtails, "cloud": cloud}

def hair_mesh(name, prims, faces=3200):
    fn = style_fn(prims)
    boxes = [pr.box() for pr in prims]
    lo = np.min([b[0] for b in boxes], 0) - 0.02; hi = np.max([b[1] for b in boxes], 0) + 0.02
    v, f = surface_nets(fn, lo, hi, 0.0045)
    if len(v) == 0: raise RuntimeError(name + " is empty")
    ob = make_mesh(name, project(fn, v, 3), f)
    remesh(ob, faces, fn, 0.0035)
    me = ob.data; p = coords(ob); nb = neighbors(ob)
    occ = smooth_values(ao(ob, 24, 0.1), nb, 1)
    D = np.stack([pr.eval(p) for pr in prims], 1); near = D.argmin(1)
    shade = np.random.default_rng(len(prims)).random(len(prims)); shade[0] = 0.5
    var = smooth_values(shade[near], nb, 1)
    flex = smooth_values(np.clip((head0(p) - 0.02) / 0.16, 0, 1) ** 1.3, nb, 1)
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    col.data.foreach_set("color", np.stack([occ, var, flex, np.ones_like(occ)], 1).ravel()); me.color_attributes.active_color = col
    # UVs run along each lock: every face takes them from the part nearest its middle
    li = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", li)
    start = np.zeros(len(me.polygons), int); me.polygons.foreach_get("loop_start", start)
    total = np.zeros(len(me.polygons), int); me.polygons.foreach_get("loop_total", total)
    face_of = np.repeat(np.arange(len(start)), total)
    mid = np.zeros((len(start), 3)); np.add.at(mid, face_of, p[li]); mid /= total[:, None]
    owner = np.stack([pr.eval(mid) for pr in prims], 1).argmin(1)[face_of]
    u = np.zeros(len(li)); w = np.zeros(len(li))
    for j, pr in enumerate(prims):
        k = owner == j
        if k.any(): _, u[k], w[k] = pr.eval(p[li[k]], True)
    u = frac(u)
    span = np.maximum.reduceat(u, start) - np.minimum.reduceat(u, start)
    wrap = (span[face_of] > 0.5) & (u < 0.5); u[wrap] += 1
    uv = me.uv_layers.new(name="UVMap"); uv.data.foreach_set("uv", np.stack([u, w], 1).ravel())
    return ob

# ---------------------------------------------------------------- hats

def on_head(theta, phi, out=0.0):
    """A point on the round head's ellipsoid (without cheeks): theta from the top, phi around from the front."""
    return HC + direction(theta, phi) * (HR + out)

def shell(p, L, out=0.026, below=0.0):
    """The top of the round head, grown outward: most hats start from this cap."""
    h = L["head"]; r = np.array(h["r"]) + out
    d = ellipsoid(p, h["c"], r)
    return smax(d, -(p[:, 2] - (h["c"][2] + below)), 0.03)

def lobes(p, pts, r, k=0.03):
    d = None
    for c in pts:
        center, radii = (c[0], c[1]) if len(c) == 2 else (c[:3], c[3] if len(c) > 3 else (r, r, r))
        e = ellipsoid(p, center, radii)
        d = e if d is None else smin(d, e, k)
    return d

BASE = CLASSIC
# A crown: a hollow band with five sharp points (one in front), a bead on each
CROWN_TIPS = [np.array([math.cos(t), math.sin(t), 0]) / ((abs(math.cos(t)) / 0.121) ** 6 + (abs(math.sin(t)) / 0.111) ** 6) ** (1 / 6) + np.array([0, 0, TOP + 0.098])
              for t in -math.pi / 2 + np.arange(5) * 2 * math.pi / 5]

def crown(p):
    turn = (np.arctan2(p[:, 1], p[:, 0]) + math.pi / 2) * 5 / (2 * math.pi)
    point = 2 * np.abs(turn % 1 - 0.5)  # 1 at each point, 0 halfway between
    band = smax(superellipsoid(p, (0, 0, TOP + 0.03), (0.13, 0.12, 0.07), 6), -superellipsoid(p, (0, 0, TOP + 0.03), (0.112, 0.102, 0.3), 6), 0.004)
    band = smax(band, p[:, 2] - (TOP + 0.035 + 0.055 * point ** 2), 0.004)
    return smin(band, lobes(p, [(t, (0.016,) * 3) for t in CROWN_TIPS], 0.016, 0.004), 0.008)

def newsboy(p):
    crown_ = ellipsoid(p, (0, -0.03, TOP - 0.035), (0.305, 0.3, 0.115))
    crown_ = smax(crown_, -(p[:, 2] - (HC[2] + 0.13)), 0.02)
    brim = ellipsoid(p, (0, -0.25, HC[2] + 0.16), (0.175, 0.11, 0.016), rot_zy(0, 0).T)
    button = ellipsoid(p, (0, -0.03, TOP + 0.075), (0.026, 0.026, 0.016))
    return smin(smin(crown_, brim, 0.03), button, 0.01)

# Parts of a hat in its second color (mask returns 0..1 per point)
HATS = {
    "beanie": (lambda p: smin(shell(p, BASE, 0.04, 0.06), ellipsoid(p, (0, 0, TOP + 0.08), (0.06, 0.06, 0.06)), 0.03),
               lambda p: ((p[:, 2] > TOP + 0.03) | (p[:, 2] < HC[2] + 0.1)).astype(float)),
    "cap": (lambda p: smin(shell(p, BASE, 0.034, 0.1), ellipsoid(p, (0, -0.28, HC[2] + 0.12), (0.2, 0.17, 0.018), rot_zy(0, 0).T), 0.02),
            lambda p: (p[:, 1] < -0.22).astype(float)),
    "newsboy": (newsboy, lambda p: ((p[:, 2] > TOP + 0.05) | (np.abs(p[:, 2] - (HC[2] + 0.165)) < 0.012) & (p[:, 1] > -0.2)).astype(float)),
    "tophat": (lambda p: smin(superellipsoid(p, (0.03, 0, TOP + 0.1), (0.12, 0.11, 0.1), 5), superellipsoid(p, (0.03, 0, TOP + 0.005), (0.19, 0.17, 0.014), 4), 0.01),
               lambda p: ((p[:, 2] > TOP + 0.01) & (p[:, 2] < TOP + 0.045)).astype(float)),
    "party": (lambda p: smin(cone(p, (0.04, 0, TOP - 0.02), (0.08, 0.01, TOP + 0.2), 0.1, 0.012), ellipsoid(p, (0.082, 0.01, TOP + 0.215), (0.03,) * 3), 0.01),
              lambda p: ((p[:, 2] > TOP + 0.19) | (np.sin(p[:, 2] * 70) > 0.6)).astype(float)),
    "beret": (lambda p: smin(ellipsoid(p, (-0.04, 0.01, TOP - 0.015), (0.26, 0.24, 0.06), rot_y(0.22).T), ellipsoid(p, (-0.04, 0.0, TOP + 0.05), (0.015, 0.015, 0.02)), 0.01),
              lambda p: (p[:, 2] > TOP + 0.04).astype(float)),
    "bucket": (lambda p: smin(superellipsoid(p, (0, 0, TOP - 0.01), (0.25, 0.23, 0.09), 3), ellipsoid(p, (0, 0, TOP - 0.07), (0.36, 0.33, 0.02)), 0.03),
               lambda p: (np.abs(p[:, 2] - (TOP - 0.03)) < 0.015).astype(float)),
    "crown": (lambda p: crown(p), lambda p: ((p[:, 2] < TOP + 0.006) | (np.min([np.linalg.norm(p - t, axis=1) for t in CROWN_TIPS], 0) < 0.022)).astype(float)),
    "headphones": (lambda p: smin(smax(smax(np.abs(ellipsoid(p, HC, HR + 0.05)) - 0.014, np.abs(p[:, 1]) - 0.03, 0.01), -(p[:, 2] - HC[2]), 0.01),
                                  lobes(p, [((0.335, 0, HC[2] + 0.02), (0.045, 0.085, 0.09)), ((-0.335, 0, HC[2] + 0.02), (0.045, 0.085, 0.09))], 0.08), 0.02),
                   lambda p: (np.abs(p[:, 0]) > 0.3).astype(float)),
    "flower": (lambda p: smin(lobes(p, [(*(on_head(0.75, 0.9, 0.025) + np.array([math.cos(a) * 0.045, -0.01, math.sin(a) * 0.045])), (0.032, 0.014, 0.032)) for a in np.linspace(0, 2 * math.pi, 6)[:-1]], 0.03, 0.01),
                              ellipsoid(p, on_head(0.75, 0.9, 0.035), (0.022, 0.016, 0.022)), 0.005),
               lambda p: (np.linalg.norm(p - on_head(0.75, 0.9, 0.035), axis=1) < 0.028).astype(float)),
    "bow": (lambda p: lobes(p, [(*(on_head(0.35, 0.7, 0.02) + np.array([0.055, 0, 0.02])), (0.055, 0.025, 0.04)), (*(on_head(0.35, 0.7, 0.02) + np.array([-0.055, 0, -0.01])), (0.055, 0.025, 0.04)),
                                (*on_head(0.35, 0.7, 0.03), (0.024, 0.024, 0.024))], 0.04, 0.012),
            lambda p: (np.linalg.norm(p - on_head(0.35, 0.7, 0.03), axis=1) < 0.03).astype(float)),
}

def accessory(name, fn, mask):
    lo, hi = bounds(fn, (-0.55, -0.55, 0.25), (0.55, 0.55, 1.4), 0.03)
    v, f = surface_nets(fn, lo, hi, 0.006)
    if len(v) == 0: raise RuntimeError(name + " is empty")
    ob = make_mesh(name, project(fn, v, 3), f)
    remesh(ob, 1400, fn, 0.004)
    me = ob.data; p = coords(ob); nb = neighbors(ob)
    occ = smooth_values(ao(ob, 24, 0.12), nb, 1)
    m = smooth_values(mask(p) if mask else np.zeros(len(p)), nb, 1)
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    col.data.foreach_set("color", np.stack([occ, m, np.zeros_like(occ), np.ones_like(occ)], 1).ravel())
    me.color_attributes.active_color = col
    return ob

# ---------------------------------------------------------------- props

def srgb(h):
    c = np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def paint(p, base):
    return np.tile(srgb(base), (len(p), 1))

def cylinder(p, a, b, r):
    a = np.asarray(a, float); ax = np.asarray(b, float) - a; L = np.linalg.norm(ax); ax = ax / L
    h = (p - a) @ ax; radial = np.linalg.norm(p - a - h[:, None] * ax, axis=1)
    return np.maximum(radial - r, np.abs(h - L / 2) - L / 2)

def local(p, c, rows): return (p - np.asarray(c)) @ np.asarray(rows).T

def props(who, L):
    """Each official companion's signature props: (name, field, color, bone[, faces])."""
    hR = np.array(M(L["hand"]["c"], -1)); hL = np.array(M(L["hand"]["c"], 1))
    out = []
    if who == "hazel":  # a balloon whisk: a wooden handle, then four wire loops that cross at the tip
        ax = unit((0.5, -0.75, 0.62)); rows = frame(ax); base = hR + ax * 0.045; H, W = 0.175, 0.056
        def fn(p):
            handle = cone(p, hR - ax * 0.04, base, 0.0135, 0.0125)
            ferrule = cone(p, base - ax * 0.004, base + ax * 0.016, 0.0145, 0.0105)
            q = local(p, base + ax * 0.012, rows); s = np.clip(q[:, 2] / H, 0, 1); wires = None
            for a in np.arange(4) * math.pi / 4:  # each loop an ellipse through the axis, a little wider toward the tip
                v = q[:, 0] * math.cos(a) + q[:, 1] * math.sin(a); off = q[:, 1] * math.cos(a) - q[:, 0] * math.sin(a)
                e = np.stack([q[:, 2] - H / 2, v / (0.7 + 0.5 * s)], 1); r = np.array([H / 2, W])
                k0 = np.linalg.norm(e / r, axis=1); k1 = np.linalg.norm(e / (r * r), axis=1)
                d = np.hypot(k0 * (k0 - 1) / np.maximum(k1, 1e-9), off) - 0.007
                wires = d if wires is None else np.minimum(wires, d)
            return smin(smin(handle, ferrule, 0.003), wires, 0.004)
        def color(p):
            h = (p - hR) @ ax; c = paint(p, "#b7bec8")
            c[h < 0.064] = srgb("#8c939c"); c[h < 0.043] = srgb("#c08a55")
            return c
        out.append(("prop.whisk", fn, color, "hand.R", 6000))
    elif who == "rio":  # a price tag pinched in one hand, a tote bag on the other
        tc = hR + np.array([-0.03, -0.035, 0.085]); rows = frame((0.3, -1, 0), up=(0.2, 0, 1)); hole = tc + rows[1] * 0.046
        def tag(p):
            q = local(p, tc, rows)
            d = sbox(p, tc, (0.048, 0.07, 0.0075), 5, rows)
            d = smax(d, (q[:, 1] + np.abs(q[:, 0]) - 0.092) / math.sqrt(2), 0.004)
            d = smax(d, 0.011 - np.hypot(q[:, 0], q[:, 1] - 0.046), 0.003)
            return smin(d, cone(p, hole + rows[1] * 0.012, hR, 0.0055, 0.0055), 0.004)
        def tag_color(p):
            q = local(p, tc, rows); c = paint(p, "#e9c08a")
            c[np.hypot(q[:, 0], q[:, 1] + 0.012) < 0.022] = srgb("#d1495b")
            c[q[:, 1] > 0.066] = srgb("#d1495b")
            return c
        out.append(("prop.tag", tag, tag_color, "hand.R"))
        bc = hL + np.array([0.012, 0.0, -0.088])
        def tote(p):
            bag = sbox(p, bc, (0.072, 0.03, 0.062), 4)
            return smin(bag, torus(p, hL + np.array([0.012, 0, -0.03]), (0, 1, 0), 0.046, 0.0075), 0.006)
        def tote_color(p):
            c = paint(p, "#f1e9da")
            c[np.abs(p[:, 2] - bc[2]) < 0.013] = srgb("#3e7cb1")
            c[p[:, 2] > bc[2] + 0.064] = srgb("#c8553d")
            return c
        out.append(("prop.tote", tote, tote_color, "hand.L"))
    elif who == "juno":  # a clipboard and a pencil
        bc = hL + np.array([0.012, -0.05, 0.055]); rows = frame((0.45, -1, 0))
        clip = bc + rows[1] * 0.088 + rows[2] * 0.006
        def board(p): return smin(sbox(p, bc, (0.068, 0.092, 0.0065), 6, rows), sbox(p, clip, (0.026, 0.012, 0.009), 4, rows), 0.004)
        def board_color(p):
            q = local(p, bc, rows); c = paint(p, "#b07a4f")
            paper = (q[:, 2] > 0.003) & (np.abs(q[:, 0]) < 0.06) & (np.abs(q[:, 1]) < 0.082)
            c[paper] = srgb("#fbf8f1")
            c[paper & (np.mod(q[:, 1] + 0.08, 0.017) < 0.0028) & (q[:, 1] < 0.06)] = srgb("#9fb4d6")
            c[np.linalg.norm(local(p, clip, rows) / np.array([0.03, 0.016, 0.014]), axis=1) < 1] = srgb("#b9bcc4")
            return c
        out.append(("prop.clipboard", board, board_color, "hand.L"))
        a = hR + np.array([0.002, 0.004, -0.045]); b = hR + np.array([-0.012, -0.035, 0.1]); ax = unit(b - a)
        def pencil(p):
            body = cylinder(p, a, b, 0.0115)
            return smin(smin(body, cone(p, b, b + ax * 0.034, 0.0115, 0.0015), 0.002), cylinder(p, a - ax * 0.022, a, 0.0118), 0.002)
        def pencil_color(p):
            h = (p - a) @ ax; c = paint(p, "#f2c14e")
            c[h > np.linalg.norm(b - a)] = srgb("#ead2ad"); c[h > np.linalg.norm(b - a) + 0.024] = srgb("#3a3a46")
            c[h < 0] = srgb("#b9bcc4"); c[h < -0.01] = srgb("#f3a3b9")
            return c
        out.append(("prop.pencil", pencil, pencil_color, "hand.R"))
    elif who == "bram":  # a popcorn bucket, red and white stripes, heaped over the rim
        bc = hL + np.array([-0.092, -0.105, -0.082]); hgt = 0.145; top = bc + np.array([0, 0, hgt])
        heap = np.array([(0, 0, 0.03), (0.026, 0.01, 0.022), (-0.024, 0.016, 0.022), (0.01, -0.027, 0.022), (-0.02, -0.022, 0.02), (0.04, -0.016, 0.008),
                         (-0.041, -0.004, 0.008), (0.006, 0.04, 0.01), (0.033, 0.03, 0.006), (-0.03, 0.032, 0.006), (0.022, -0.042, 0.004), (-0.012, -0.044, 0.006)]) * 1.25
        rng = np.random.default_rng(5)
        puffs = [(top + c + rng.normal(0, 0.008, 3), (0.014,) * 3) for c in heap for _ in range(3)]  # each puff, three lumps
        def bucket(p):
            cup = smax(cone(p, bc, top, 0.052, 0.07), np.maximum(bc[2] - p[:, 2], p[:, 2] - top[2]), 0.007)
            cup = smin(cup, torus(p, top - np.array([0, 0, 0.005]), (0, 0, 1), 0.07, 0.008), 0.004)
            corn = smin(ellipsoid(p, top + np.array([0, 0, 0.005]), (0.062, 0.062, 0.025)), lobes(p, puffs, 0.014, 0.007), 0.007)
            return smin(cup, corn, 0.004)
        def bucket_color(p):
            q = p - bc; rad = np.hypot(q[:, 0], q[:, 1]); c = paint(p, "#f7f1e6")
            c[np.sin(np.arctan2(q[:, 1], q[:, 0]) * 6) > 0] = srgb("#d8413a")
            c[q[:, 2] > hgt - 0.014] = srgb("#f7f1e6")  # the rolled rim
            corn = (q[:, 2] > hgt + 0.004) | ((q[:, 2] > hgt - 0.025) & (rad < 0.062))
            c[corn] = srgb("#fbf0d2")
            c[corn & (np.sin(p[:, 0] * 250) * np.sin(p[:, 1] * 230) * np.sin(p[:, 2] * 270) > 0.3)] = srgb("#efcb6a")  # butter
            return c
        out.append(("prop.popcorn", bucket, bucket_color, "hand.L", 3000))
    elif who == "wren":  # a quill, and a striped scarf
        a = hR + np.array([0.004, 0.004, -0.06]); b = hR + np.array([-0.02, -0.025, 0.2]); ax = unit(b - a)
        x = unit(np.cross(ax, (0, 1, 0))); rows = np.array([x, np.cross(ax, x), ax]); vc = a + (b - a) * 0.7
        def quill(p):
            shaft = cone(p, a, b, 0.0055, 0.004)
            vane = smin(sbox(p, vc, (0.032, 0.006, 0.095), 2, rows), sbox(p, vc + ax * 0.05 + x * 0.008, (0.021, 0.0055, 0.05), 2, rows), 0.012)
            return smin(smin(shaft, vane, 0.004), cone(p, a, a - ax * 0.026, 0.0055, 0.0012), 0.002)
        def quill_color(p):
            h = (p - a) @ ax; c = paint(p, "#f6efe2")
            c[h > np.linalg.norm(b - a) * 0.86] = srgb("#e58fa8"); c[h < 0.06] = srgb("#e9dcc4"); c[h < 0] = srgb("#2c2f3a")
            return c
        out.append(("prop.quill", quill, quill_color, "hand.R"))
        nz = L["neck"] - 0.005
        def on_body(z, d):  # where a ray out from the middle at height z leaves the body
            o = np.array([[0, 0, z]]); d = np.array([unit(d)]); t0, t1 = 0.0, 0.6
            for _ in range(30):
                t = (t0 + t1) / 2
                if field(o + d * t, L)[0] < 0: t0 = t
                else: t1 = t
            return (o + d * t0)[0]
        knot = on_body(nz - 0.02, (0.42, -1, 0)) + np.array([0.004, -0.024, 0])
        hang = on_body(nz - 0.12, (0.5, -1, 0)) + np.array([0, -0.03, 0])
        def scarf(p):  # a thick band hugging the neck (not the ears), then one end hanging down the front
            pp = parts(p, L); d = smin(pp["head"], pp["body"], 0.06)
            wrap = smax(smax(d - 0.034, -d - 0.012, 0.004), np.abs(p[:, 2] - nz) - 0.036, 0.014)
            end = smin(cone(p, knot, hang, 0.032, 0.03), cone(p, hang, hang + np.array([-0.006, 0.004, -0.075]), 0.03, 0.032), 0.012)
            return smin(wrap, end, 0.02)
        def scarf_color(p):
            c = paint(p, "#e9b04f"); ang = np.arctan2(p[:, 0], -p[:, 1])
            ring = p[:, 2] > nz - 0.045
            c[ring & (np.sin(ang * 7) > 0.55)] = srgb("#c8553d")
            c[~ring & (np.sin(p[:, 2] * 95) > 0.5)] = srgb("#c8553d")
            return c
        out.append(("prop.scarf", scarf, scarf_color, "body"))
    elif who == "pip":  # today's paper, rolled up
        ax = unit((-0.2, -0.35, 1)); a = hR - ax * 0.08; b = hR + ax * 0.14
        def paper(p): return cylinder(p, a, b, 0.034)
        def paper_color(p):
            h = (p - a) @ ax; c = paint(p, "#efe9dc")
            c[np.mod(h, 0.013) < 0.0045] = srgb("#9a968f")
            c[(h > 0.17) & (h < 0.186)] = srgb("#2d3142")
            return c
        out.append(("prop.paper", paper, paper_color, "hand.R"))
    return out

def prop_mesh(name, fn, color, faces=1300):
    lo, hi = bounds(fn, (-0.7, -0.6, -0.03), (0.7, 0.6, 1.4), 0.02)
    v, f = surface_nets(fn, lo, hi, 0.003)
    ob = make_mesh(name, project(fn, v, 3), f)
    remesh(ob, faces, fn, 0.0025)
    me = ob.data; p = coords(ob); nb = neighbors(ob)
    occ = smooth_values(ao(ob, 24, 0.08), nb, 1)
    rgb = color(p) * (0.55 + 0.45 * occ)[:, None]
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    col.data.foreach_set("color", np.concatenate([rgb, np.ones((len(p), 1))], 1).ravel()); me.color_attributes.active_color = col
    return ob

# ---------------------------------------------------------------- fit

WRAP_STEP, WRAP_ROWS, WRAP_COLS = 15, 11, 24  # head radius every 15 degrees, from the top down to 150 degrees

def wrap_dirs():
    return np.array([direction(math.radians(r * WRAP_STEP), math.radians(c * 360 / WRAP_COLS)) for r in range(WRAP_ROWS) for c in range(WRAP_COLS)])

def head_radius(L):
    """How far the head's surface is from its center, along each table direction. Hats sit on the crown, so no peak."""
    L = dict(L, head=dict(L["head"], peak=0)); c = np.array(L["head"]["c"]); dirs = wrap_dirs()
    lo = np.zeros(len(dirs)); hi = np.ones(len(dirs))
    for _ in range(36):
        m = (lo + hi) / 2; inside = head_sdf(c + dirs * m[:, None], L) < 0
        lo = np.where(inside, m, lo); hi = np.where(inside, hi, m)
    return lo

def fit_json():
    base = head_radius(CLASSIC)
    heads = {}
    for key, L in [(s, look(s)) for s in SHAPES] + list(BODIES.items()):
        r = head_radius(L)
        heads[key] = dict(c=[round(float(x), 4) for x in L["head"]["c"]], r=[round(float(x), 4) for x in r], s=round(float(r.mean() / base.mean()), 4))
    clip = lambda d: {k: dict(seconds=v[1], loop=v[2]) for k, v in d.items()}
    return dict(wrap=dict(step=WRAP_STEP, rows=WRAP_ROWS, cols=WRAP_COLS, c=[round(float(x), 4) for x in HC], r=[round(float(x), 4) for x in base], heads=heads),
                shapesOrder=list(SHAPES), clips=clip(CLIPS), blink=dict(seconds=round(sum(BLINK), 3), stretch=BLINK_STRETCH),
                bodies={k: clip(v) for k, v in OWN.items()})

# ---------------------------------------------------------------- go

def material(ob, name):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF"); bsdf.inputs["Roughness"].default_value = 0.8
    ob.data.materials.append(mat)

def export(path):
    for o in bpy.context.view_layer.objects: o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                              export_draco_position_quantization=14, export_draco_normal_quantization=10,
                              export_draco_color_quantization=8, export_draco_texcoord_quantization=12,
                              export_vertex_color="ACTIVE", export_all_vertex_colors=False, export_yup=True,
                              export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True,
                              export_optimize_animation_size=True, export_skins=True, export_morph=True,
                              export_morph_normal=False, export_apply=False)  # the app bakes the head shape and recomputes normals
    print("WROTE", path, os.path.getsize(path))

def main():
    opts = dict(a.split("=", 1) for a in ARGS[2:] if "=" in a)
    skip = set(opts.get("skip", "").split(",")); only = set(filter(None, opts.get("only", "").split(",")))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if WHAT == "fit":
        with open(os.path.join(OUT, "fit.json"), "w") as f: json.dump(fit_json(), f, separators=(",", ":"))
        print("WROTE fit.json"); return
    L = CLASSIC if WHAT == "classic" else BODIES[WHAT]
    body = build_body(L); w = weights(body, L)
    if WHAT == "classic": shape_keys(body, L, w)
    face_and_masks(body, w, L); material(body, "Body")
    rig = build_rig(body, w, L)
    if WHAT == "classic":
        if "clips" not in skip: bake(rig, CLIPS); bake_blink(rig); rig.animation_data.action = bpy.data.actions["idle"]
        if "hair" not in skip:
            for name, make in HAIR.items():
                if not only or name in only: material(hair_mesh("hair." + name, make()), "Hair")
        if "hats" not in skip:
            for name, (fn, mask) in HATS.items():
                if not only or name in only: material(accessory("hat." + name, fn, mask), "Hat")
        name = "companion"
    else:
        for pname, fn, color, bone, *faces in props(WHAT, L):
            ob = prop_mesh(pname, fn, color, *faces); skin_to(ob, rig, bone); material(ob, "Prop")
        if "clips" not in skip: bake(rig, OWN[WHAT]); rig.animation_data.action = bpy.data.actions["idle"]
        name = "body-" + WHAT
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, name + ".blend"))
    if "export" not in skip: export(os.path.join(OUT, name + ".glb"))

main()
