"""Preview renders of the companion from companion.blend (EEVEE). These are for checking the model; the app draws its own.

blender -b out/companion.blend -P render.py -- <out dir> <what: hero|shapes|acc|clips> [color hex]
"""
import bpy, math, os, sys
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
OUT, WHAT = args[0], args[1]
COLOR = args[2] if len(args) > 2 else "8fb8e8"
os.makedirs(OUT, exist_ok=True)

def hexrgb(h, a=1.0):
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x ** 2.2 for x in c] + [a]

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 48
if hasattr(scene.eevee, "use_raytracing"): scene.eevee.use_raytracing = True
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX"

world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = hexrgb("f7f4ef")
world.node_tree.nodes["Background"].inputs[1].default_value = 0.55

def light(name, loc, power, size, color="ffffff"):
    l = bpy.data.lights.new(name, "AREA"); l.energy = power; l.size = size; l.color = hexrgb(color)[:3]
    o = bpy.data.objects.new(name, l); scene.collection.objects.link(o); o.location = loc
    d = Vector((0, 0, 0.5)) - Vector(loc); o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
light("key", (-1.6, -2.2, 2.6), 95, 2.4, "fff6ec")
light("fill", (2.2, -1.4, 1.0), 22, 2.5, "eef2ff")
light("rim", (0.8, 2.4, 1.8), 70, 1.2)

bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
floor = bpy.context.active_object
fm = bpy.data.materials.new("floor"); fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = hexrgb("f7f4ef")
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
floor.data.materials.append(fm)

target = bpy.data.objects.new("target", None); scene.collection.objects.link(target); target.location = (0, 0, 0.5)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = 85
def aim(az=24, el=7, dist=3.3, h=0.5):
    a, e = math.radians(az), math.radians(el)
    target.location = (0, 0, h)
    cam.location = (dist * math.sin(a) * math.cos(e), -dist * math.cos(a) * math.cos(e), h + dist * math.sin(e))
    c = cam.constraints.get("t") or cam.constraints.new("TRACK_TO"); c.name = "t"; c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"

# A plain face for previews (the app draws the real one).
N = 512
v, u = np.mgrid[0:N, 0:N] / N
img = np.zeros((N, N, 4))
def ellipse(cu, cv, ru, rv): return ((u - cu) / ru) ** 2 + ((v - cv) / rv) ** 2 < 1
for s in (-1, 1):
    cu = 0.5 + s * 0.105 / 0.58; cv = 0.52
    eye = ellipse(cu, cv, 0.052, 0.068); img[eye] = (0.07, 0.06, 0.08, 1)
    img[ellipse(cu - 0.015, cv + 0.025, 0.017, 0.017)] = (1, 1, 1, 1)
    img[ellipse(cu + 0.018, cv - 0.02, 0.008, 0.008)] = (1, 1, 1, 1)
r = np.hypot(u - 0.5, (v - 0.33) * 1.3)
img[(np.abs(r - 0.05) < 0.007) & (v < 0.325)] = (0.12, 0.08, 0.1, 1)
for s in (-1, 1):
    blush = ellipse(0.5 + s * 0.31, 0.43, 0.06, 0.035); img[blush] = img[blush] * 0 + (0.95, 0.55, 0.55, 0.35)
face = bpy.data.images.new("face", N, N, alpha=True); face.pixels.foreach_set(img.astype(np.float32).ravel())

def mix(nt, kind, fac, a, b):
    m = nt.nodes.new("ShaderNodeMix"); m.data_type = "RGBA"; m.blend_type = kind
    for i, x in ((0, fac), (6, a), (7, b)):
        if isinstance(x, (int, float)): m.inputs[i].default_value = x
        elif isinstance(x, (list, tuple)): m.inputs[i].default_value = x
        else: nt.links.new(x, m.inputs[i])
    return m.outputs[2]

def felt(mat, color, second=None, with_face=False):
    mat.use_nodes = True; nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
    att = nt.nodes.new("ShaderNodeAttribute"); att.attribute_name = "Col"; att.attribute_type = "GEOMETRY"
    sep = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(att.outputs["Color"], sep.inputs[0])
    base = hexrgb(color)
    col = mix(nt, "MIX", 0.0, base, base)
    if second:
        col = mix(nt, "MIX", sep.outputs[1], base, hexrgb(second))
    else:
        light_ = [min(1, c * 0.55 + 0.45) for c in base[:3]] + [1]
        bl = nt.nodes.new("ShaderNodeMath"); bl.operation = "MULTIPLY"; bl.inputs[1].default_value = 0.55
        nt.links.new(sep.outputs[2], bl.inputs[0]); col = mix(nt, "MIX", bl.outputs[0], base, light_)
    aof = nt.nodes.new("ShaderNodeMapRange"); nt.links.new(sep.outputs[0], aof.inputs[0])
    aof.inputs[3].default_value = 0.5; aof.inputs[4].default_value = 1.0
    col = mix(nt, "MULTIPLY", 1.0, col, aof.outputs[0])
    if with_face:
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = face; tex.interpolation = "Cubic"
        uv = nt.nodes.new("ShaderNodeUVMap"); nt.links.new(uv.outputs[0], tex.inputs[0])
        f = nt.nodes.new("ShaderNodeMath"); f.operation = "MULTIPLY"
        nt.links.new(tex.outputs["Alpha"], f.inputs[0]); nt.links.new(sep.outputs[1], f.inputs[1])
        col = mix(nt, "MIX", f.outputs[0], col, tex.outputs["Color"])
    nt.links.new(col, bsdf.inputs["Base Color"])
    for k, x in (("Roughness", 0.72), ("Sheen Weight", 0.6), ("Sheen Roughness", 0.45), ("Specular IOR Level", 0.22)):
        if k in bsdf.inputs: bsdf.inputs[k].default_value = x

body = bpy.data.objects["Companion"]; rig = bpy.data.objects["Rig"]
felt(body.data.materials[0], COLOR, with_face=True)
dark = "".join(f"{int(int(COLOR[i:i + 2], 16) * 0.62):02x}" for i in (0, 2, 4))
accs = [o for o in bpy.data.objects if o.name.startswith(("hair.", "hat."))]
SECOND = {"hat.beanie": "f4efe6", "hat.cap": "2d3142", "hat.tophat": "c8553d", "hat.party": "ffd166", "hat.beret": "2d3142",
          "hat.bucket": "6c8a5a", "hat.crown": "b8862f", "hat.headphones": "3a3a46", "hat.flower": "ffd166", "hat.bow": "b23a48"}
HATCOL = {"hat.beanie": "d1495b", "hat.cap": "3e7cb1", "hat.tophat": "2b2d42", "hat.party": "5aa9e6", "hat.beret": "c8553d",
          "hat.bucket": "e9c46a", "hat.crown": "f2c14e", "hat.headphones": "e8e4dc", "hat.flower": "f7a1c4", "hat.bow": "e05a6d"}
for o in accs:
    m = bpy.data.materials.new(o.name); o.data.materials.clear(); o.data.materials.append(m)
    felt(m, HATCOL.get(o.name, dark), SECOND.get(o.name))
    o.hide_render = True

def shot(path, w=700, h=700):
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.filepath = path; bpy.ops.render.render(write_still=True)

def shape(name):
    for kb in body.data.shape_keys.key_blocks[1:]: kb.value = 1.0 if kb.name == name else 0.0

def pose(action, frame):
    rig.animation_data.action = bpy.data.actions[action]
    if rig.animation_data.action_slot is None and len(bpy.data.actions[action].slots):
        rig.animation_data.action_slot = bpy.data.actions[action].slots[0]
    scene.frame_set(frame)

pose("idle", 1)
if WHAT == "hero":
    aim(0, 5); shot(os.path.join(OUT, "hero_front.png"), 900, 900)
    aim(28, 7); shot(os.path.join(OUT, "hero_34.png"), 900, 900)
    aim(90, 4); shot(os.path.join(OUT, "hero_side.png"), 900, 900)
    aim(160, 8); shot(os.path.join(OUT, "hero_back.png"), 900, 900)
elif WHAT == "shapes":
    aim(22, 6)
    for kb in ["round"] + [k.name for k in body.data.shape_keys.key_blocks[1:]]:
        shape(kb if kb != "round" else ""); shot(os.path.join(OUT, f"shape_{kb}.png"), 500, 500)
    shape("")
elif WHAT == "acc":
    aim(24, 10, 3.0, 0.6)
    for o in accs:
        o.hide_render = False; shot(os.path.join(OUT, f"acc_{o.name}.png"), 420, 420); o.hide_render = True
elif WHAT.startswith("clips"):  # clips, or clips:happy,done
    aim(18, 6, 3.6, 0.55)
    only = WHAT.partition(":")[2].split(",") if ":" in WHAT else None
    for a in bpy.data.actions:
        if only and a.name not in only: continue
        end = int(a.frame_range[1])
        for f in range(1, end + 1, 3):
            pose(a.name, f); shot(os.path.join(OUT, f"clip_{a.name}_{f:03d}.png"), 360, 360)
elif WHAT == "rest":
    body.modifiers["Rig"].show_render = False
    aim(0, 5); shot(os.path.join(OUT, "rest_front.png"), 600, 600)
    aim(90, 4); shot(os.path.join(OUT, "rest_side.png"), 600, 600)
    aim(0, 80, 3.3, 0.6); shot(os.path.join(OUT, "rest_top.png"), 600, 600)
