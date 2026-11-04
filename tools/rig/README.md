# Rig export

`gltf_export.py` makes the glb the app loads for a companion's body: the rig and its meshes, with every clip as its own animation, Draco compressed. It runs inside Blender and was used with Blender 5.2 on the Mac:

```
GLTF_ALL_COLORS=1 blender -b <name>_clips.blend -P tools/rig/gltf_export.py -- <name>.raw.glb <name>_rig
```

- The last argument is the armature. Left out, it's `zest_rig`.
- Only the armature and what hangs off it are exported: no lamps, floor or camera.
- Each clip is keyed as one action per holder, named `clip|holder`. The script lays them on NLA tracks named after the clip, so each clip comes out as one animation.
- `GLTF_ALL_COLORS=1` exports every color attribute: the face paint and the zones (COLOR_1 and COLOR_2). Blender 5.2's exporter has a bug here: it marks each color attribute in turn as the one every material uses, so only the last keeps its data, and the face paint and the zones come out white. With the variable set, the script patches the exporter in memory, for that run only, so every material uses every color attribute. If a newer Blender changes that code, an assert stops the export instead of writing white zones.
- Without the variable, only the active color attribute is exported.
- At the end it prints the glb's size, meshes, animations and joints, to check by eye.

The rest of the pipeline is on the Mac in `~/still-ruth/rig`, not in this repo: `fb.sh` builds the rig (`build.py`), keys and checks the clips (`anim.py`), runs this export, and `glb_post.py` writes the finished glb. The app loads the finished bodies from `still-ui/src/assets/rig/`.
