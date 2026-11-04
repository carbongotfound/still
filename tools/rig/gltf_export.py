"""The app's copy: the rig, its meshes and every clip as one glb, one animation per clip, Draco.
blender -b CLIPS.blend -P gltf_export.py -- OUT.glb [ARMATURE]"""
import json, os, struct, sys
import bpy

if os.environ.get("GLTF_ALL_COLORS"):
    # Blender 5.2's exporter, with every color attribute on, marks each one in turn as the one all materials use, so only
    # the last keeps its data and every earlier one (the face paint, the zones) is written as white. Keep them all.
    import inspect, textwrap
    from io_scene_gltf2.blender.exp import primitive_extract as PE
    _f = PE.PrimitiveCreator._PrimitiveCreator__manage_color_attributes
    _src = textwrap.dedent(inspect.getsource(_f)).replace("def __manage_color_attributes", "def _keep_colors").replace("self.__", "self._PrimitiveCreator__")  # compiled outside the class: no name mangling
    _bad = "if self.material_idxs_using_vc.get(material_idx) == vc['gltf_name']:"
    assert _src.count(_bad) == 1, "the exporter changed: check the vertex color fix"
    _ns = {}
    exec(_src.replace(_bad, "if True:  # every material uses every color attribute"), PE.__dict__, _ns)
    PE.PrimitiveCreator._PrimitiveCreator__manage_color_attributes = _ns["_keep_colors"]

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]; ARM = bpy.data.objects[argv[1] if len(argv) > 1 else "zest_rig"]

# Only the rig and what hangs off it: no lamps, catchlights, floor or camera.
keep = {ARM} | {o for o in bpy.data.objects if o.parent == ARM}
for o in list(bpy.data.objects):
    if o not in keep: bpy.data.objects.remove(o)

# Each clip was keyed as one action per holder ("clip|holder"): lay them on NLA tracks named after the clip,
# and the exporter merges tracks of one name into one animation.
holders = {ARM.name: ARM}
holders.update({o.data.shape_keys.name: o.data.shape_keys for o in keep if o.type == "MESH" and o.data.shape_keys})
for act in bpy.data.actions:
    if "|" not in act.name: continue
    clip, who = act.name.split("|", 1); h = holders.get(who)
    if h is None: continue
    ad = h.animation_data_create(); ad.action = None
    tr = ad.nla_tracks.get(clip) or ad.nla_tracks.new(); tr.name = clip
    st = tr.strips.new(clip, int(act.frame_range[0]), act)
    if act.slots: st.action_slot = act.slots[0]
for h in holders.values():
    if h.animation_data: h.animation_data.action = None
for pb in ARM.pose.bones: pb.matrix_basis.identity()

bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", export_apply=False, export_yup=True,
    export_vertex_color="ACTIVE", export_materials="EXPORT", **({"export_all_vertex_colors": True} if os.environ.get("GLTF_ALL_COLORS") else {}), export_lights=False, export_cameras=False, export_extras=False,
    export_skins=True, export_influence_nb=4, export_def_bones=False,
    export_morph=True, export_morph_normal=True, export_try_sparse_sk=True,
    export_animations=True, export_animation_mode="ACTIONS", export_merge_animation="NLA_TRACK",
    export_force_sampling=True, export_frame_step=1, export_anim_slide_to_zero=True,
    export_optimize_animation_size=True, export_optimize_animation_keep_anim_armature=True,
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
    export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_color_quantization=10)

b = open(OUT, "rb").read(); n = struct.unpack("<I", b[12:16])[0]; j = json.loads(b[20:20 + n])
acc = j["accessors"]
print("SIZE", len(b), "json", n, "ext", j.get("extensionsUsed"))
for m in j["meshes"]: print("MESH", m["name"], len(m["primitives"]), (m.get("extras") or {}).get("targetNames"))
for a in j["animations"]:
    t = max(acc[a["samplers"][c["sampler"]]["input"]]["max"][0] for c in a["channels"])
    print("ANIM", a["name"], len(a["channels"]), "channels", round(t, 3), "s")
print("JOINTS", [j["nodes"][i]["name"] for i in j["skins"][0]["joints"]])
