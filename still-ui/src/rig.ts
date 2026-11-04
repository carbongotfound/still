import * as THREE from "three"
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js"
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js"
import { clone } from "three/addons/utils/SkeletonUtils.js"
import { EYE_REST, MOUTH_REST, RIGS, isV2, lookKey, type Look } from "./look"
import { clock, type MascotState } from "./Mascot"

// The eight companions as Blender made them (crew/): a skeleton, face shapes and every clip, one glb each. Nothing
// here moves them by code. A state loops its clip, a gesture plays its clip once and crossfades back, and the eyes and
// body steer toward the pointer through held poses laid on top (pose.look.*, pose.turn*). The idle (idle_a) is one 12 s
// performance that blinks and moves its eyes itself; over anything else, Blender's blink (blink_once) comes every 2-4 s
// and the eyes dart. Blinks and talking set the lid and mouth shapes after the clips, so they only ever add to what a
// clip does. Any other bean look wears Make your own's model in its own color. A look v2 wears its foundation (f-<form>,
// rig/fb.sh), colored by zone, with its face's rest under the clips and its top feature and accessory on the head.

const GLB = import.meta.glob("./assets/rig/*.glb", { query: "?url", import: "default", eager: true }) as Record<string, string>
const BY_LOOK = new Map(RIGS.map(([l, id]) => [lookKey(l), id]))
const failed = new Set<string>()
const url = (id: string) => GLB[`./assets/rig/${id}.glb`]
/// The model a look wears, or null for the drawn blobs (no model shipped, or it didn't load).
export function rigFor(look: Look) {
 const id = isV2(look) ? "f-" + look.form : BY_LOOK.get(lookKey(look)) ?? (look.shape === "bean" && !look.prop && !look.accessory ? "custom" : "")
 return id && url(id) && !failed.has(id) ? id : null
}

const LOOP: Record<MascotState, string> = { idle: "idle_a", listening: "idle_a", thinking: "thinking", working: "working", needs: "idle_a", done: "idle_a", error: "idle_a", talking: "idle_a", pointing: "idle_a" }
// What a state does as it starts, once (needs waves again every few seconds).
const ENTER: Partial<Record<MascotState, string[]>> = { done: ["nod", "celebrate"], error: ["shrug", "surprised"], needs: ["wave"] }
// The app's gestures (Mascot GESTURES) as clips: pitch is the hire picker's hover, hired and happy celebrate, pop spins.
const MOVE: Record<string, string> = { wave: "wave", "needs-you": "wave", wake: "wake", drop: "drop_in", pitch: "hover", hired: "celebrate", happy: "celebrate", done: "nod", admire: "nod", sad: "shrug", pop: "spin" }
// Idle, now and then.
const FIDGET = ["look_around", "look_around", "blink", "wink.L", "wink.R"]
// These start somewhere else (in the air, asleep), so they cut in instead of fading in.
const CUT = new Set(["drop_in", "wake"])
const STEER = ["look.x+", "look.x-", "look.z+", "look.z-", "turn+", "turn-"]

type Model = { id: string; scene: THREE.Object3D; clips: Map<string, THREE.AnimationClip>; blink: number[]; box?: THREE.Box3 }
const models = new Map<string, Model | Promise<unknown>>()
const ready = new Set<() => void>()
/// Calls back each time a model finishes loading.
export const onRigReady = (f: () => void) => { ready.add(f) }
let loader: GLTFLoader | null = null

/// The model, once loaded; until then null, and it starts loading.
export function model(id: string): Model | null {
 const m = models.get(id)
 if (m && !(m instanceof Promise)) return m
 if (!m) {
  loader ??= new GLTFLoader().setDRACOLoader(new DRACOLoader().setDecoderConfig({ type: "wasm" }))
  models.set(id, loader.loadAsync(url(id)).then(g => { models.set(id, prepare(id, g)) }, e => { failed.add(id); console.error(`The companion ${id} couldn't load`, e) })
   .then(() => ready.forEach(f => f())))
 }
 return null
}

function prepare(id: string, g: GLTF): Model {
 const clips = new Map(g.animations.map(c => [c.name, c]))
 const rest = clips.get("pose.rest")
 for (const n of STEER) { const c = clips.get("pose." + n); if (c && rest) clips.set("add." + n, THREE.AnimationUtils.makeClipAdditive(c.clone(), 0, rest)) }
 // The blink: how shut its lids are, 60 times a second until they're open again, and the rest of it (the eye squash, the
 // brow dip, the little nod) as a layer over any clip
 const once = clips.get("blink_once"), blink: number[] = []
 let lid: THREE.Mesh | undefined
 g.scene.traverse(o => {
  const mesh = o as THREE.Mesh, mat = mesh.material as THREE.MeshPhysicalMaterial | undefined
  o.frustumCulled = false
  if (mesh.morphTargetDictionary?.["blink.1"] !== undefined) lid ??= mesh
  // The eye caps are clear glass in Blender, there for the shine. three.js glass draws the lid colour over the top of the
  // eye (the lids look half shut), so the caps keep only their shine, added over the eye
  if (mat?.name === "cap" && mat.transmission) Object.assign(mat, { transmission: 0, color: new THREE.Color(0), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })
  // Matte clay, as in the Cycles renders: the room's light only fills the shadow side a little, so the form reads
  if (mat && ["vinyl", "brow", "lid"].includes(mat.name)) Object.assign(mat, { roughness: .86, envMapIntensity: .18 })
 })
 const track = lid && once?.tracks.find(k => k.name === `${lid!.name}.morphTargetInfluences`)
 if (once && lid && track) {
  const at = new THREE.LinearInterpolant(track.times, track.values, track.getValueSize()), d = lid.morphTargetDictionary!
  for (let x = 0; x <= once.duration; x += 1 / 60) { const v = at.evaluate(x); let s = 0; for (let i = 1; i <= 8; i++) s += v[d[`blink.${i}`]]; blink.push(s / 8) }
  while (blink.length && blink[blink.length - 1] < .001) blink.pop()
  const body = once.tracks.filter(k => !k.name.endsWith(".morphTargetInfluences")).map(k => k.clone())
  clips.set("add.blink", THREE.AnimationUtils.makeClipAdditive(new THREE.AnimationClip("add.blink", once.duration, body)))
 }
 return { id, scene: g.scene, clips, blink }
}

/// Everything a model can reach: every clip, every steering pose at full weight, but the drop only from where it lands
/// (it falls in from out of frame on purpose). Shipped in the glb (scene extras bounds.all), or swept here from a sample
/// of the vertices.
export function bounds(m: Model) {
 if (m.box) return m.box
 const all = (m.scene.userData.bounds as { all?: { min: number[]; max: number[] } } | undefined)?.all
 if (all) return m.box = new THREE.Box3(new THREE.Vector3().fromArray(all.min), new THREE.Vector3().fromArray(all.max))
 const r = new Rigged(m), box = new THREE.Box3(), v = new THREE.Vector3(), meshes: THREE.Mesh[] = []
 r.root.traverse(o => { if ((o as THREE.Mesh).isMesh) meshes.push(o as THREE.Mesh) })
 for (const [name, clip] of m.clips) {
  if (name.startsWith("add.") || name === "drop_in") continue
  for (let t = 0; t <= clip.duration; t += 1 / 6) {
   r.only(name, t); r.root.updateMatrixWorld(true)
   for (const mesh of meshes) for (let i = 0, n = mesh.geometry.getAttribute("position").count; i < n; i += 5) box.expandByPoint(mesh.getVertexPosition(i, v).applyMatrix4(mesh.matrixWorld))
  }
 }
 r.dispose()
 return m.box = box
}

// ---------------------------------------------------------------- look v2's colors

// By zone (rig/zdef.py zones, in the glb as COLOR_1 and COLOR_2: the feet in the first channel of one, the hands in the
// first of the other; the other channels are empty since Stage 17 took the markings out): the main color, a light tint of
// it on the hands and the accent on the feet (the main color without one). The painted face (the blush, the
// mouth) still multiplies over it. glow: a flat copy's own light (companion3d flatten).
export type Zones = { uMain: { value: THREE.Color }; uHand: { value: THREE.Color }; uSecond: { value: THREE.Color }; uGlow: { value: number } }
export function zoned(m: THREE.Material, u: Zones) {
 m.onBeforeCompile = s => {
  Object.assign(s.uniforms, u)
  s.vertexShader = "attribute vec4 color_1;\nattribute vec4 color_2;\nvarying vec4 vZ1;\nvarying vec4 vZ2;\n" + s.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\nvZ1 = color_1; vZ2 = color_2;")
  s.fragmentShader = "uniform vec3 uMain;\nuniform vec3 uHand;\nuniform vec3 uSecond;\nuniform float uGlow;\nvarying vec4 vZ1;\nvarying vec4 vZ2;\n" + s.fragmentShader.replace("#include <color_fragment>", `{
 vec3 z = mix(mix(uMain, uHand, vZ2.x), uSecond, clamp(vZ1.x, 0., 1.));
 diffuseColor.rgb = z; totalEmissiveRadiance += z * uGlow;
}
#include <color_fragment>`)
 }
 m.customProgramCacheKey = () => "zones"
 m.userData.zones = u
}
const WHITE = new THREE.Color(1, 1, 1)
const node = (root: THREE.Object3D, name: string) => root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name))

type Layer = { clip: string; start: number; loop: boolean }
const ease = (x: number) => x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x)
const rnd = (k: number) => (Math.random() * 2 - 1) * k
const clamp = (v: number, k: number) => Math.max(-k, Math.min(k, v))

export class Rigged {
 group = new THREE.Group() // on the ground: holds the shadow
 root: THREE.Object3D
 mixer: THREE.AnimationMixer
 acts = new Map<string, THREE.AnimationAction>()
 lids: THREE.Mesh[] = []; face: THREE.Mesh | null = null; joint: THREE.Object3D | null = null
 tints = new Map<string, THREE.MeshStandardMaterial>()
 look?: Look; key = ""
 state: MascotState = "idle"; gestureAt = 0
 move = ""; moveStart = 0
 from: Layer | null = null; fromAt = -9
 live = true; phase = Math.random() * 12
 fidgetNext = -1; waveAt = 0 // timers start on the first live frame (the clock is the page's)
 blinkNext = 0; blinkStart = -9; glanceNext = 0; glance = [0, 0]; gaze = [0, 0]; turn = 0
 undo: [number[], number, number][] = [] // the shapes after() set, and what the clips had there
 scaled: [THREE.Object3D, THREE.Vector3][] = [] // the eyes after() sized, and their size before
 rest: { lid: number; scale: number; wide: number; mouth: [string, number] } | null = null // a v2 look's face at rest
 worn: THREE.Object3D[] = [] // a v2 look's top feature and accessory
 /// A v2 look's top feature and accessory, each made pointing up and sized for a blob 1 tall, with the way from the middle
 /// of the head to where it sits (companion3d makes them: it has the parts).
 static decor: ((look: Look) => [THREE.Object3D, THREE.Vector3][]) | null = null
 static held: ((prop: string) => THREE.Object3D | null) | null = null // companion3d.ts: a kept prop, as held

 m: Model; shadow?: THREE.Mesh
 constructor(m: Model, shadow?: THREE.Mesh) {
  this.m = m; this.shadow = shadow
  this.root = clone(m.scene)
  this.group.add(this.root)
  if (shadow) this.group.add(shadow)
  this.mixer = new THREE.AnimationMixer(this.root)
  this.root.traverse(o => {
   const d = (o as THREE.Mesh).morphTargetDictionary
   if (d?.["blink.1"] !== undefined) this.lids.push(o as THREE.Mesh)
   if (d?.["mouth.open"] !== undefined) this.face = o as THREE.Mesh
   if (o.name === "root" && !this.joint) this.joint = o
  })
 }
 get id() { return this.m.id }
 get height() { return bounds(this.m).max.y }
 has(name: string) { return name in MOVE || this.m.clips.has(name) }

 setLook(look: Look) {
  const key = lookKey(look)
  if (key === this.key) return
  this.look = look; this.key = key
  if (isV2(look)) return this.dress(look)
  if (BY_LOOK.get(key) === this.id) return
  // Make your own's model in another color, the lids too (a blink is the body's color)
  this.root.traverse(o => {
   const mesh = o as THREE.Mesh, mat = mesh.material as THREE.MeshStandardMaterial
   if (!mesh.isMesh || mat?.name !== "vinyl" && mat?.name !== "lid") return
   let t = this.tints.get(mat.name)
   if (!t) { t = mat.clone(); t.userData.base = mat.color.clone(); this.tints.set(mat.name, t) }
   t.color.copy(t.userData.base).multiply(new THREE.Color(look.color)); mesh.material = t
  })
 }

 /// A v2 look on its foundation: the zones' colors, the lids in the main color, the brows a
 /// darker main, the finish, the face's rest, and the top feature and accessory on the head.
 dress(look: Look) {
  const main = new THREE.Color(look.color), second = new THREE.Color(look.second ?? look.color), gloss = look.finish === "gloss"
  this.root.traverse(o => {
   const mesh = o as THREE.Mesh, mat = mesh.material as THREE.MeshStandardMaterial
   if (!mesh.isMesh || !["vinyl", "lid", "brow"].includes(mat?.name)) return
   let t = this.tints.get(mat.name)
   if (!t) {
    t = mat.clone(); t.userData.base = mat.color.clone(); this.tints.set(mat.name, t)
    if (mat.name === "vinyl") zoned(t, { uMain: { value: new THREE.Color() }, uHand: { value: new THREE.Color() }, uSecond: { value: new THREE.Color() }, uGlow: { value: 0 } })
   }
   const u = t.userData.zones as Zones | undefined
   if (u) { u.uMain.value.copy(main); u.uHand.value.copy(main).lerp(WHITE, .3); u.uSecond.value.copy(second) }
   else t.color.copy(t.userData.base).multiply(main)
   Object.assign(t, { roughness: gloss ? .38 : .86, envMapIntensity: gloss ? .3 : .18 })
   mesh.material = t
  })
  this.rest = { ...(EYE_REST[look.eye!] ?? EYE_REST.round), mouth: MOUTH_REST[look.mouth!] ?? MOUTH_REST.smile }
  for (const n of this.worn) { n.removeFromParent(); n.traverse(o => (o as THREE.Mesh).geometry?.dispose()) }
  this.worn = []
  const head = node(this.root, "head"), body = this.body()
  if (head && body && Rigged.decor) for (const [part, dir] of Rigged.decor(look)) { this.wear(body, head, part, dir); this.worn.push(part) }
  const hand = node(this.root, "hand.R"), held = look.prop ? Rigged.held?.(look.prop) : null
  if (hand && body && held) { this.hold(body, hand, held); this.worn.push(held) }
 }
 /// A kept prop in the right mitten, turned as the classic blob held it (to the body, not the hand), sized like wear's
 /// parts; found in the bind pose, so it rides the hand through every clip. ponytail: two-handed props sit in one hand.
 hold(body: THREE.SkinnedMesh, hand: THREE.Object3D, part: THREE.Object3D) {
  const sk = body.skeleton, i = sk.bones.indexOf(hand as THREE.Bone), pos = body.geometry.getAttribute("position"), v = new THREE.Vector3()
  if (i < 0) return
  let top = 0, half = 0
  for (let k = 0; k < pos.count; k++) { v.fromBufferAttribute(pos, k); top = Math.max(top, v.y); half = Math.max(half, Math.abs(v.x)) }
  const at = new THREE.Vector3().setFromMatrixPosition(sk.boneInverses[i].clone().invert()).applyMatrix4(body.bindMatrix.clone().invert())
  const local = new THREE.Matrix4().compose(at, part.quaternion, part.scale.clone().multiplyScalar((top + half / .4) / 2))
  sk.boneInverses[i].clone().multiply(body.bindMatrix).multiply(local).decompose(part.position, part.quaternion, part.scale)
  hand.add(part)
 }
 /// The body (the skinned mesh in vinyl).
 body() { let b: THREE.SkinnedMesh | undefined; this.root.traverse(o => { if ((o as THREE.SkinnedMesh).isSkinnedMesh && ((o as THREE.Mesh).material as THREE.Material)?.name === "vinyl") b ??= o as THREE.SkinnedMesh }); return b }
 /// Puts a part on the head where the body's surface is furthest along dir from the middle of the head (between the eyes),
 /// facing out along the surface there, sized by how big this body is against a blob 1 tall. Found in the bind pose, so it
 /// rides on the head bone through every clip.
 wear(body: THREE.SkinnedMesh, head: THREE.Object3D, part: THREE.Object3D, dir: THREE.Vector3) {
  const sk = body.skeleton, bones = sk.bones, bind = (o: THREE.Object3D) => sk.boneInverses[bones.indexOf(o as THREE.Bone)].clone().invert()
  const eyes = ["eye.L", "eye.R"].map(n => node(this.root, n)).filter(e => e && bones.includes(e as THREE.Bone)).map(e => new THREE.Vector3().setFromMatrixPosition(bind(e!)))
  const pos = body.geometry.getAttribute("position"), nor = body.geometry.getAttribute("normal"), v = new THREE.Vector3(), d = dir.clone().normalize()
  const mid = eyes.length ? eyes.reduce((s, e) => s.add(e), new THREE.Vector3()).divideScalar(eyes.length).setX(0).setZ(0) : new THREE.Vector3(0, .6, 0)
  let best = -2, bi = 0, top = 0, half = 0
  for (let i = 0; i < pos.count; i++) {
   v.fromBufferAttribute(pos, i).applyMatrix4(body.bindMatrix)
   top = Math.max(top, v.y); half = Math.max(half, Math.abs(v.x))
   const s = v.sub(mid).normalize().dot(d)
   if (s > best) { best = s; bi = i }
  }
  const toHead = sk.boneInverses[bones.indexOf(head as THREE.Bone)].clone().multiply(body.bindMatrix)
  const p = new THREE.Vector3().fromBufferAttribute(pos, bi).applyMatrix4(toHead), n = new THREE.Vector3().fromBufferAttribute(nor, bi).applyMatrix3(new THREE.Matrix3().getNormalMatrix(toHead)).normalize()
  const s = new THREE.Vector3(); bind(head).decompose(new THREE.Vector3(), new THREE.Quaternion(), s)
  part.position.copy(p).addScaledVector(n, -.004)
  part.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), n)
  part.scale.setScalar((top + half / .4) / 2 / s.x)
  head.add(part)
 }

 setState(state: MascotState, name: string, gestureAt: number, t: number) {
  if (gestureAt !== this.gestureAt && name) { this.gestureAt = gestureAt; if (this.has(name)) this.begin(name, t) }
  if (state === this.state) return
  this.from = this.base(); this.fromAt = t; this.state = state
  const enter = ENTER[state]
  if (enter && !this.move) { this.begin(clock.still ? enter[0] : enter[Math.floor(Math.random() * enter.length)], t); this.waveAt = t }
 }
 begin(name: string, t: number) {
  const clip = MOVE[name] ?? name
  if (!this.m.clips.has(clip)) return
  this.from = this.move ? { clip: this.move, start: this.moveStart, loop: false } : this.base(); this.fromAt = CUT.has(clip) ? -9 : t
  this.move = clip; this.moveStart = t
 }
 base(): Layer { return { clip: LOOP[this.state], start: this.live ? -this.phase : 0, loop: true } }
 still() { this.from = null }

 /// Moves time on to t and poses everything.
 update(dt: number, t: number, follow: { x: number; y: number } | null) {
  if (this.live && !clock.still) {
   if (this.fidgetNext < 0) { this.fidgetNext = t + 10 + Math.random() * 10; this.blinkNext = t + 1 + Math.random() * 3; this.glanceNext = t + 1; this.waveAt = t }
   if (!this.move && this.state === "idle" && t > this.fidgetNext) { this.begin(FIDGET[Math.floor(Math.random() * FIDGET.length)], t); this.fidgetNext = t + 14 + Math.random() * 16 }
   if (!this.move && this.state === "needs" && t - this.waveAt > 6) { this.begin("wave", t); this.waveAt = t }
   const own = !this.move && LOOP[this.state] === "idle_a" // the idle blinks and looks about on its own
   if (t > this.blinkNext) { if (!own) this.blinkStart = t; this.blinkNext = t + (Math.random() < .14 ? this.m.blink.length / 60 : 2 + Math.random() * 2) }
   if (t > this.glanceNext) { this.glance = Math.random() < .4 ? [0, 0] : [clamp(this.glance[0] + rnd(.5), .6), clamp(this.glance[1] + rnd(.2), .3)]; this.glanceNext = t + .5 + Math.random() * 2 }
   // working looks toward the page it works on (left of the chat)
   const want = follow ?? (this.state === "working" ? { x: -.55, y: .15 } : own ? { x: 0, y: 0 } : { x: this.glance[0], y: this.glance[1] }), k = 1 - Math.exp(-dt * (follow ? 10 : 6))
   const dart = follow ? k : 1 - Math.exp(-dt * 40) // eyes jump to what they look at (about 0.08 s), then hold
   this.gaze[0] += (want.x - this.gaze[0]) * dart; this.gaze[1] += (want.y - this.gaze[1]) * dart
   this.turn += ((follow?.x ?? (this.state === "working" ? -.4 : 0)) - this.turn) * k
  }
  this.pose(t)
 }

 /// The clips at time t: the state's loop, the move over it, the last of what came before fading out, the steering on top.
 pose(t: number) {
  // three.js writes a shape only when its clip value changes, so a lid the clip holds still would keep the last blink
  for (const [inf, i, v] of this.undo) inf[i] = v
  this.undo.length = 0
  for (const [o, s] of this.scaled) o.scale.copy(s)
  this.scaled.length = 0
  for (const a of this.acts.values()) a.weight = 0
  let mw = 0
  if (this.move) {
   const g = t - this.moveStart, d = this.m.clips.get(this.move)!.duration
   if (g >= d) { this.from = { clip: this.move, start: this.moveStart, loop: false }; this.fromAt = t; this.move = "" }
   else mw = Math.min(CUT.has(this.move) ? 1 : ease(g / .2), ease((d - g) / .35))
  }
  const fw = this.from && t - this.fromAt < .3 ? 1 - ease((t - this.fromAt) / .3) : 0
  if (!fw) this.from = null
  if (this.from) this.layer(this.from, t, fw)
  if (this.move) this.layer({ clip: this.move, start: this.moveStart, loop: false }, t, (1 - fw) * mw)
  this.layer(this.base(), t, (1 - fw) * (1 - mw))
  const k = 1 - mw, [gx, gy] = this.gaze, steer: [string, number][] = [["look.x+", gx], ["look.x-", -gx], ["look.z+", -gy], ["look.z-", gy], ["turn+", this.turn], ["turn-", -this.turn]]
  for (const [n, w] of steer) if (w > 0 && this.m.clips.has("add." + n)) this.act("add." + n).weight = w * k
  const bx = this.blinking(t)
  if (bx >= 0 && bx < (this.m.clips.get("add.blink")?.duration ?? 0)) this.layer({ clip: "add.blink", start: t - bx, loop: false }, t, 1)
  this.mixer.update(0)
  this.after(t)
 }
 /// Seconds into the blink at t, or -1.
 blinking(t: number) { return clock.blink ?? (this.live && !clock.still ? t - this.blinkStart : -1) }
 /// One clip alone at full weight, for sweeping bounds.
 only(clip: string, t: number) {
  for (const a of this.acts.values()) a.weight = 0
  this.layer({ clip, start: 0, loop: false }, t, 1); this.mixer.update(0)
 }
 layer(l: Layer, t: number, w: number) {
  if (w <= 0) return
  const a = this.act(l.clip), d = a.getClip().duration
  a.time = l.loop ? ((t - l.start) % d + d) % d : Math.min(Math.max(0, t - l.start), d - 1e-4)
  a.weight += w
 }
 act(clip: string) {
  let a = this.acts.get(clip)
  if (!a) { a = this.mixer.clipAction(this.m.clips.get(clip)!); a.play(); a.weight = 0; this.acts.set(clip, a) }
  return a
 }

 /// Blinks and talking, over whatever the clips set (they key every lid and mouth shape each frame). A v2 look's face
 /// rest goes under them: the lids that much shut (a blink closes the rest of the way), the lid's wide shape, the eyes'
 /// size and the mouth's shape (less of it while a clip moves the mouth).
 after(t: number) {
  const b = this.m.blink[Math.round(this.blinking(t) * 60)] ?? 0, r = this.rest
  if (b > 0 || r) for (const lid of this.lids) {
   const inf = lid.morphTargetInfluences!, d = lid.morphTargetDictionary!
   let now = 0
   for (let i = 1; i <= 8; i++) now += inf[d[`blink.${i}`]]
   const want = r ? r.lid + (1 - r.lid) * Math.max(b, now / 8) : b
   if (want * 8 > now + 1e-3) for (let i = 1; i <= 8; i++) { const w = Math.max(0, Math.min(1, 8 * want - (i - 1))); this.set(inf, d[`blink.${i}`], w); this.set(inf, d[`blink.${i}.arc`], 4 * w * (1 - w)) }
   if (r?.wide && d.wide !== undefined) this.set(inf, d.wide, Math.max(inf[d.wide], r.wide * (1 - want)))
  }
  if (r && r.scale !== 1) for (const n of ["eye.L", "eye.R"]) { const e = node(this.root, n); if (e) { this.scaled.push([e, e.scale.clone()]); e.scale.multiplyScalar(r.scale) } }
  if (r && this.face) {
   const inf = this.face.morphTargetInfluences!, d = this.face.morphTargetDictionary!, [name, w] = r.mouth, i = d[name]
   let moving = 0
   for (const m of ["mouth.smile", "mouth.grin", "mouth.hmm", "mouth.o", "mouth.open"]) if (m !== name && d[m] !== undefined) moving += inf[d[m]]
   if (i !== undefined) this.set(inf, i, Math.max(inf[i], w * Math.max(0, 1 - 2 * moving)))
  }
  if (this.state === "talking" && this.face) { // syllables: the jaw opens and closes about six times a second, rounder now and then
   const inf = this.face.morphTargetInfluences!, d = this.face.morphTargetDictionary!, s = .5 + .5 * Math.sin(t * 12.6), k = .5 + .5 * Math.sin(t * 5.3 + 1)
   this.set(inf, d["mouth.open"], Math.max(inf[d["mouth.open"]], s * (.3 + .45 * k)))
   if (d["mouth.o"] !== undefined) this.set(inf, d["mouth.o"], Math.max(inf[d["mouth.o"]], (1 - s) * .35 * k))
  }
  // the shadow shrinks and fades as the companion leaves the ground
  if (this.shadow && this.joint) {
   const w = bounds(this.m), lift = Math.max(0, this.joint.getWorldPosition(new THREE.Vector3()).y), k = Math.max(.45, 1 - lift * 1.6), s = (w.max.x - w.min.x) * 1.15 * k
   this.shadow.scale.set(s, s * .75, 1); (this.shadow.material as THREE.MeshBasicMaterial).opacity = Math.max(.3, 1 - lift * 2)
  }
 }
 set(inf: number[], i: number, v: number) { if (i === undefined) return; this.undo.push([inf, i, inf[i]]); inf[i] = v }
 occluders(_view?: THREE.Matrix4) { /* the blobs' soft shadows from their nubs: the models carry their own */ }

 dispose() {
  this.mixer.stopAllAction(); this.mixer.uncacheRoot(this.root); this.tints.forEach(t => t.dispose())
  for (const n of this.worn) n.traverse(o => (o as THREE.Mesh).geometry?.dispose())
  if (this.shadow) { this.shadow.geometry.dispose(); (this.shadow.material as THREE.Material).dispose() }
 }
}
