"""Builds Still's companion in Blender: one sculpted mesh, its head shapes, the rig, the clips, the hair and hats.

Run on the Mac: blender -b --factory-startup -P build.py -- <out dir>
Writes companion.glb (Draco), fit.json (how hair and hats sit on each head shape) and companion.blend for render.py.

The body is a signed distance field (soft unions of ellipsoids and round cones), meshed with surface nets, remeshed to
clean quads and pulled back onto the field. Weights come from the same parts, so the joins bend like clay. Clips are
sampled from code with spring follow-through on the ears, tail and hands. The face isn't modeled: the app draws it on a
texture, and the control bones (lid, brow, mouth, look) carry its expressions, read as scale (1 = rest).
"""
import bpy, bmesh, json, math, os, sys
import numpy as np
from mathutils import Matrix, Quaternion, Vector, Euler
from mathutils.bvhtree import BVHTree

OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(os.path.dirname(__file__), "out")
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

# The base look. Front is -Y, up is Z, feet on z = 0, about one unit tall.
BASE = dict(
    head=dict(c=(0, 0, 0.655), r=(0.315, 0.275, 0.268), square=0, peak=0),
    cheek=dict(c=(0.172, -0.072, 0.572), r=(0.142, 0.13, 0.118)),
    ear=dict(c=(0.188, 0.025, 0.872), r=(0.074, 0.044, 0.094), tilt=0.40, tip=1.0, scale=1.0),
)
# Hand-tuned unevenness: the right ear leans out a little more and sits a touch lower.
EAR_SIDE = {1: dict(tilt=0.0, dz=0.0, s=1.0), -1: dict(tilt=0.07, dz=-0.012, s=0.97)}

SHAPES = {  # head shapes, as changes to BASE. Names are the app's ids.
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
    out = {k: dict(v) for k, v in BASE.items()}
    for part, change in SHAPES[shape].items(): out[part].update(change)
    return out

def ear_frame(L, side, lift=0.0):
    """Where an ear sits: center, radii and the rows that turn world points into its local frame."""
    e = L["ear"]; sd = EAR_SIDE[side]
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
    for s, n in ((1, "L"), (-1, "R")):
        d["ear." + n] = ear_sdf(p, L, s, lift)
        d["arm." + n] = cone(p, (0.158 * s, 0.0, 0.392), (0.252 * s, -0.024, 0.262), 0.057, 0.049)
        d["hand." + n] = ellipsoid(p, (0.27 * s, -0.03, 0.222), (0.066, 0.06, 0.074))
        d["leg." + n] = smin(cone(p, (0.086 * s, 0.0, 0.17), (0.097 * s, -0.004, 0.07), 0.071, 0.066),
                             ellipsoid(p, (0.101 * s, -0.036, 0.046), (0.079, 0.101, 0.056)), 0.035)
    d["body"] = smin(ellipsoid(p, (0, 0.012, 0.282), (0.19, 0.166, 0.202)),
                     ellipsoid(p, (0, -0.046, 0.252), (0.15, 0.128, 0.138)), 0.06)
    d["tail"] = ellipsoid(p, (0.012, 0.168, 0.205), (0.058, 0.056, 0.062))
    return d

def field(p, L, lift=0.0):
    d = parts(p, L, lift)
    f = smin(d["head"], d["ear.L"], 0.05); f = smin(f, d["ear.R"], 0.05)
    f = smin(f, d["body"], 0.075)
    for n in ("L", "R"):
        f = smin(f, smin(d["arm." + n], d["hand." + n], 0.03), 0.04)
        f = smin(f, d["leg." + n], 0.05)
    f = smin(f, d["tail"], 0.035)
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

def build_body():
    L = look("round")
    fn = lambda p: field(p, L)
    ob = blob("Companion", fn, (-0.44, -0.33, -0.03), (0.44, 0.31, 1.06), 0.0055, 9000)
    return ob, L

def part_weights(p, L):
    d = parts(p, L)
    names = list(d)
    D = np.stack([np.maximum(d[n], 0) for n in names], 1)
    W = np.exp(-D / 0.022); W /= W.sum(1, keepdims=True)
    return names, W

def shape_keys(ob, L0):
    """Head shapes and ear height as shape keys: move the head's vertices toward each shape, then onto its field."""
    p0 = coords(ob); nb = neighbors(ob)
    names, W = part_weights(p0, L0)
    w = {n: W[:, i] for i, n in enumerate(names)}
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
    return w

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

FACE = dict(cx=0.0, cz=0.655, size=0.58)  # the square of the head the face texture covers, seen from the front

def face_and_masks(ob, w):
    me = ob.data; p = coords(ob); nb = neighbors(ob)
    me.calc_normals_split() if hasattr(me, "calc_normals_split") else None
    n = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get("normal", n); n = n.reshape(-1, 3)
    occ = smooth_values(ao(ob), nb, 2)
    front = np.clip((-n[:, 1] + 0.05) / 0.3, 0, 1)
    face = front * np.clip((w["head"] - 0.25) / 0.3, 0, 1) * np.clip((p[:, 2] - 0.43) / 0.05, 0, 1)
    face = smooth_values(face, nb, 2)
    e = (p[:, 0] / 0.118) ** 2 + ((p[:, 2] - 0.262) / 0.128) ** 2
    belly = np.clip((1 - e) / 0.35, 0, 1) * np.clip((-n[:, 1] - 0.1) / 0.4, 0, 1) * np.clip(w["body"] * 1.6, 0, 1)
    belly = smooth_values(belly, nb, 2)
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    rgba = np.stack([occ, face, belly, np.ones_like(occ)], 1)
    col.data.foreach_set("color", rgba.ravel()); me.color_attributes.active_color = col
    uv = me.uv_layers.new(name="UVMap")
    li = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", li)
    s = FACE["size"]
    uvs = np.stack([0.5 + (p[li, 0] - FACE["cx"]) / s, 0.5 + (p[li, 2] - FACE["cz"]) / s], 1)
    uv.data.foreach_set("uv", uvs.ravel())

# ---------------------------------------------------------------- rig

DEFORM = {  # bone: (head, tail, parent)
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
CONTROLS = {  # face controls, read by the app as scale: lid y = open, lid x = happy squint, brow y = raise,
    # brow x = worry (inner ends up), mouth y = open, mouth x = smile, look x/y = gaze (1 = straight ahead)
    "lid.L": (0.1, -0.3, 0.66), "lid.R": (-0.1, -0.3, 0.66), "brow.L": (0.1, -0.3, 0.74), "brow.R": (-0.1, -0.3, 0.74),
    "mouth": (0, -0.3, 0.53), "look": (0, -0.3, 0.62),
}

def build_rig(body, w):
    arm = bpy.data.armatures.new("Rig"); rig = bpy.data.objects.new("Rig", arm)
    bpy.context.collection.objects.link(rig); activate(rig)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (h, t, parent) in DEFORM.items():
        b = arm.edit_bones.new(name); b.head, b.tail = h, t; b.roll = 0
        if parent: b.parent = arm.edit_bones[parent]
        b.use_connect = False
    for name, h in CONTROLS.items():
        b = arm.edit_bones.new(name); b.head = h; b.tail = (h[0], h[1], h[2] + 0.04)
        b.parent = arm.edit_bones["head"]; b.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    # weights from the parts: legs and feet go to legs, cheeks to the head, the rest by name
    names = ["head", "ear.L", "ear.R", "arm.L", "arm.R", "hand.L", "hand.R", "leg.L", "leg.R", "body", "tail"]
    W = np.stack([w[n] for n in names], 1)
    # a little of the body in the lower head, so the neck bends softly instead of folding
    p = coords(body); neck = np.clip(1 - np.abs(p[:, 2] - 0.44) / 0.07, 0, 1) * W[:, 0]
    W[:, 0] -= neck * 0.35; W[:, 9] += neck * 0.35
    W /= W.sum(1, keepdims=True)
    for i, n in enumerate(names):
        g = body.vertex_groups.new(name=n)
        for v in np.nonzero(W[:, i] > 0.004)[0]: g.add([int(v)], float(W[v, i]), "REPLACE")
    body.parent = rig
    mod = body.modifiers.new("Rig", "ARMATURE"); mod.object = rig
    return rig

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

def bake(rig):
    pb = rig.pose.bones
    rest = {b.name: b.bone.matrix_local.to_3x3() for b in pb}
    for b in pb: b.rotation_mode = "QUATERNION"
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    rig.animation_data_create()
    def world_rot(name, deg):  # rotation given in the armature's axes (x: nod, y: turn... see below), turned into the bone's
        r = Euler([math.radians(a) for a in deg], "XYZ").to_matrix()
        R = rest[name]; return (R.inverted() @ r @ R).to_quaternion()
    for clip, (fn, T, loops) in CLIPS.items():
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
            for b in pb:
                b.keyframe_insert("location", frame=f); b.keyframe_insert("rotation_quaternion", frame=f); b.keyframe_insert("scale", frame=f)
        act.frame_range = (1, frames)
    rig.animation_data.action = bpy.data.actions["idle"]
    for b in pb: b.location = (0, 0, 0); b.rotation_quaternion = (1, 0, 0, 0); b.scale = (1, 1, 1)

# ---------------------------------------------------------------- hair and hats

def shell(p, L, out=0.026, below=0.0):
    """The top of the round head, grown outward: most hair starts from this cap."""
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

HC = np.array(BASE["head"]["c"]); HR = np.array(BASE["head"]["r"]); TOP = HC[2] + HR[2]

def on_head(theta, phi, out=0.0):
    """A point on the round head: theta from the top (0) down, phi around from the front (0) toward the left (+)."""
    x = math.sin(theta) * math.sin(phi); y = -math.sin(theta) * math.cos(phi); z = math.cos(theta)
    return HC + np.array([x, y, z]) * (HR + out)

def fringe_cut(p, z0, slope=0.0):
    return -(p[:, 2] - (z0 + slope * p[:, 0]))

HAIR = {
    "tuft": lambda p: smin(shell(p, BASE, 0.012, 0.16), cone(p, on_head(0.05, 0, 0.0), on_head(0.0, 0, 0.0) + np.array([0.05, -0.05, 0.13]), 0.05, 0.012), 0.05),
    "curls": lambda p: smin(shell(p, BASE, 0.014, 0.14), lobes(p, [(*on_head(0.15, a, 0.03), (0.06, 0.06, 0.06)) for a in (-0.8, 0.0, 0.8)], 0.06), 0.03),
    "bowl": lambda p: smax(shell(p, BASE, 0.032, -0.02), -(p[:, 2] - (0.705 - 0.11 * np.clip((p[:, 1] + 0.05) / 0.2, 0, 1))), 0.02),
    "swoop": lambda p: smin(shell(p, BASE, 0.026, 0.08), ellipsoid(p, on_head(0.55, -0.35, 0.02), (0.15, 0.06, 0.07), rot_y(0.5).T), 0.05),
    "spiky": lambda p: smin(shell(p, BASE, 0.016, 0.1), np.min(np.stack([cone(p, on_head(th, ph, -0.02), on_head(th, ph, 0.12), 0.05, 0.008)
                                                                     for th, ph in ((0.0, 0), (0.45, -0.6), (0.45, 0.6), (0.6, 0), (0.55, 3.1), (0.5, 1.8), (0.5, -1.8))]), 0), 0.03),
    "bun": lambda p: smin(shell(p, BASE, 0.02, 0.02), ellipsoid(p, on_head(0.35, 3.14, 0.06), (0.09, 0.09, 0.085)), 0.04),
    "buns": lambda p: smin(shell(p, BASE, 0.02, 0.04), lobes(p, [(*on_head(0.6, 2.4, 0.05), (0.075,) * 3), (*on_head(0.6, -2.4, 0.05), (0.075,) * 3)], 0.07), 0.035),
    "pigtails": lambda p: smin(shell(p, BASE, 0.022, 0.0), np.minimum(cone(p, on_head(1.2, 2.0, 0.0), on_head(1.2, 2.0, 0.0) + np.array([0.09, 0.03, -0.17]), 0.055, 0.04),
                                                                        cone(p, on_head(1.2, -2.0, 0.0), on_head(1.2, -2.0, 0.0) + np.array([-0.09, 0.03, -0.17]), 0.055, 0.04)), 0.04),
    "cloud": lambda p: lobes(p, [(*on_head(th, ph, 0.0), (0.085, 0.085, 0.075)) for th, ph in ((0.0, 0), (0.5, 0.5), (0.5, -0.5), (0.55, 1.6), (0.55, -1.6), (0.6, 2.7), (0.6, -2.7), (0.75, 0.0))], 0.08, 0.05),
    "mohawk": lambda p: smin(shell(p, BASE, 0.008, 0.18), lobes(p, [(*on_head(th, ph, 0.04), (0.035, 0.06, 0.06)) for th, ph in ((0.6, 0), (0.3, 0), (0.0, 0), (0.3, 3.14), (0.6, 3.14))], 0.05, 0.04), 0.03),
    "ponytail": lambda p: smin(shell(p, BASE, 0.022, 0.02), cone(p, on_head(0.45, 3.14, 0.02), on_head(0.45, 3.14, 0.02) + np.array([0.0, 0.16, -0.16]), 0.06, 0.035), 0.05),
    "bob": lambda p: smax(shell(p, BASE, 0.03, -0.15), -(p[:, 2] - (0.71 - 0.26 * np.clip((p[:, 1] + 0.16) / 0.1, 0, 1))), 0.03),
    "sprout": lambda p: smin(cone(p, on_head(0.0, 0, -0.03), on_head(0.0, 0, 0.0) + np.array([0.0, 0.0, 0.11]), 0.014, 0.011),
                             ellipsoid(p, on_head(0.0, 0, 0.0) + np.array([0.05, 0.0, 0.13]), (0.06, 0.012, 0.028), rot_y(-0.5).T), 0.015),
    "part": lambda p: smin(lobes(p, [(*on_head(0.45, 0.45, 0.02), (0.13, 0.08, 0.07)), (*on_head(0.45, -0.45, 0.02), (0.13, 0.08, 0.07))], 0.1, 0.02),
                           shell(p, BASE, 0.022, 0.06), 0.03),
    "wisp": lambda p: smin(shell(p, BASE, 0.01, 0.2), cone(p, on_head(0.1, 0.4, 0.0), on_head(0.1, 0.4, 0.0) + np.array([-0.04, -0.09, 0.1]), 0.03, 0.008), 0.03),
}
# A crown: a hollow band with five sharp points (one in front), a bead on each
CROWN_TIPS = [np.array([math.cos(t), math.sin(t), 0]) / ((abs(math.cos(t)) / 0.121) ** 6 + (abs(math.sin(t)) / 0.111) ** 6) ** (1 / 6) + np.array([0, 0, TOP + 0.098])
              for t in -math.pi / 2 + np.arange(5) * 2 * math.pi / 5]

def crown(p):
    turn = (np.arctan2(p[:, 1], p[:, 0]) + math.pi / 2) * 5 / (2 * math.pi)
    point = 2 * np.abs(turn % 1 - 0.5)  # 1 at each point, 0 halfway between
    band = smax(superellipsoid(p, (0, 0, TOP + 0.03), (0.13, 0.12, 0.07), 6), -superellipsoid(p, (0, 0, TOP + 0.03), (0.112, 0.102, 0.3), 6), 0.004)
    band = smax(band, p[:, 2] - (TOP + 0.035 + 0.055 * point ** 2), 0.004)
    return smin(band, lobes(p, [(t, (0.016,) * 3) for t in CROWN_TIPS], 0.016, 0.004), 0.008)

# Parts of a hat in its second color (mask returns 0..1 per point)
HATS = {
    "beanie": (lambda p: smin(shell(p, BASE, 0.04, 0.06), ellipsoid(p, (0, 0, TOP + 0.08), (0.06, 0.06, 0.06)), 0.03),
               lambda p: ((p[:, 2] > TOP + 0.03) | (p[:, 2] < HC[2] + 0.1)).astype(float)),
    "cap": (lambda p: smin(shell(p, BASE, 0.034, 0.1), ellipsoid(p, (0, -0.28, HC[2] + 0.12), (0.2, 0.17, 0.018), rot_zy(0, 0).T), 0.02),
            lambda p: (p[:, 1] < -0.22).astype(float)),
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

def accessory(name, fn, mask, rig):
    v, f = surface_nets(fn, (-0.45, -0.45, 0.25), (0.45, 0.45, 1.35), 0.006)
    if len(v) == 0: raise RuntimeError(name + " is empty")
    ob = make_mesh(name, project(fn, v, 3), f)
    remesh(ob, 1400, fn, 0.004)
    me = ob.data; p = coords(ob); nb = neighbors(ob)
    occ = smooth_values(ao(ob, 24, 0.12), nb, 1)
    m = smooth_values(mask(p) if mask else np.zeros(len(p)), nb, 1)
    col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    col.data.foreach_set("color", np.stack([occ, m, np.zeros_like(occ), np.ones_like(occ)], 1).ravel())
    me.color_attributes.active_color = col
    g = ob.vertex_groups.new(name="head"); g.add(list(range(len(p))), 1.0, "REPLACE")
    ob.parent = rig; mod = ob.modifiers.new("Rig", "ARMATURE"); mod.object = rig
    return ob

def fit_table():
    """How hair and hats should move and scale on each head shape, measured on the shapes' fields."""
    out = {}
    for s in SHAPES:
        L = look(s); h = L["head"]
        L["head"] = dict(h, peak=0)  # hats sit on the crown; a peak pokes through them
        fn = lambda q: head_sdf(q, L)
        top = project(fn, np.array([[0.0, 0.0, h["c"][2] + 0.5]]), 8)[0, 2]
        top0 = TOP
        side = project(fn, np.array([[0.6, 0.0, HC[2] + 0.06]]), 8)[0, 0]
        front = project(fn, np.array([[0.0, -0.6, HC[2] + 0.06]]), 8)[0, 1]
        side0 = project(lambda q: head_sdf(q, BASE), np.array([[0.6, 0.0, HC[2] + 0.06]]), 8)[0, 0]
        front0 = project(lambda q: head_sdf(q, BASE), np.array([[0.0, -0.6, HC[2] + 0.06]]), 8)[0, 1]
        out[s] = dict(lift=round(float(top - top0), 4), sx=round(float(side / side0), 4), sy=round(float(front / front0), 4),
                      peak=bool(h["peak"]))
    return out

# ---------------------------------------------------------------- go

def material(ob, name):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF"); bsdf.inputs["Roughness"].default_value = 0.8
    ob.data.materials.append(mat)

def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body, L = build_body()
    w = shape_keys(body, L)
    face_and_masks(body, w)
    material(body, "Body")
    rig = build_rig(body, w)
    bake(rig)
    for name, fn in HAIR.items(): material(accessory("hair." + name, fn, None, rig), "Hair")
    for name, (fn, mask) in HATS.items(): material(accessory("hat." + name, fn, mask, rig), "Hat")
    with open(os.path.join(OUT, "fit.json"), "w") as f:
        json.dump(dict(face=FACE, shapes=fit_table(), shapesOrder=list(SHAPES), clips={k: dict(seconds=v[1], loop=v[2]) for k, v in CLIPS.items()}), f, indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "companion.blend"))
    activate(rig)
    for o in bpy.context.view_layer.objects: o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "companion.glb"), export_format="GLB", use_selection=True,
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                              export_draco_position_quantization=14, export_draco_normal_quantization=10,
                              export_draco_color_quantization=8, export_draco_texcoord_quantization=12,
                              export_vertex_color="ACTIVE", export_all_vertex_colors=False, export_yup=True,
                              export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True,
                              export_optimize_animation_size=True, export_skins=True, export_morph=True,
                              export_morph_normal=False, export_apply=False)  # the app bakes the head shape and recomputes normals
    print("WROTE", os.path.join(OUT, "companion.glb"), os.path.getsize(os.path.join(OUT, "companion.glb")))

main()
