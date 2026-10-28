import * as THREE from "three"
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js"
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js"
import { clone as cloneRig } from "three/addons/utils/SkeletonUtils.js"
import { drawFace, type FacePose } from "./face"
import { lookKey, type Look } from "./look"
import { clock, pointer, slots, type Frame, type MascotState, type Slot } from "./Mascot"

// The companion in 3D, built in Blender (tools/mascot): the classic body with its head shapes, the shared clips, the
// blink and every hair and hat (companion.glb), and each official companion's own body, props, idle and gesture
// (body-<id>.glb, loaded the first time one shows). All bodies share one rig, so the shared clips play on any of them.
// Hair and hats are modeled on the classic head; fit.json says how far every head's surface is from its middle in each
// direction, so they're stretched onto whichever head wears them and hung on its head bone. Each look is tinted,
// shaped and dressed here, its face drawn onto a canvas texture. One hidden WebGL canvas renders every visible
// companion in turn and copies it into that companion's own canvas, at most 30 times a second (60 for a big one
// that's moving), and not at all while the window is hidden.

type Head = { c: number[]; r: number[]; s: number }
type Fit = { wrap: { step: number; rows: number; cols: number; c: number[]; r: number[]; heads: Record<string, Head> }; blink: { seconds: number; stretch: number } }
type Model = { scene: THREE.Object3D; clips: THREE.AnimationClip[] }
const CLIP: Record<MascotState, string> = { idle: "idle", listening: "idle", thinking: "think", working: "work", needs: "needs", done: "done", error: "sad", talking: "talk", pointing: "point" }
const ONCE = new Set(["done", "happy", "point", "wave", "admire", "pop", "gesture"])
const HAT_COLORS: Record<string, [string, string]> = {
 beanie: ["#d1495b", "#f4efe6"], cap: ["#3e7cb1", "#2d3142"], newsboy: ["#8a7560", "#5a4a3c"], tophat: ["#2b2d42", "#c8553d"], party: ["#5aa9e6", "#ffd166"], beret: ["#c8553d", "#2d3142"],
 bucket: ["#e9c46a", "#6c8a5a"], crown: ["#f2c14e", "#b8862f"], headphones: ["#e8e4dc", "#3a3a46"], flower: ["#f7a1c4", "#ffd166"], bow: ["#e05a6d", "#b23a48"],
}

let classic: Model, fit: Fit, blinkCurve: THREE.Interpolant | undefined
const partNames: string[] = []
const bodies = new Map<string, Model | null>(), loadingBodies = new Map<string, Promise<void>>()

async function gltf(url: string) {
 const draco = new DRACOLoader().setDecoderConfig({ type: "wasm" }) // three bundles its own decoder next to this file
 try { return await new GLTFLoader().setDRACOLoader(draco).loadAsync(url) } finally { draco.dispose() }
}
export async function load() {
 const [g, f] = await Promise.all([gltf("companion/companion.glb"), fetch("companion/fit.json").then(r => r.json())])
 fit = f
 classic = { scene: g.scene, clips: g.animations.filter(c => c.name !== "blink") }
 blinkCurve = g.animations.find(c => c.name === "blink")?.tracks.find(t => t.name === "lidL.scale")?.InterpolantFactoryMethodLinear(new Float32Array(3))
 g.scene.traverse(o => { if ((o as THREE.Mesh).isMesh && /^(hair|hat)/.test(o.name)) partNames.push(o.name) })
}
/// An official companion's body, once it's loaded (or failed to: then the classic body stands in).
export const hasBody = (id: string) => !id || bodies.has(id)
export function loadBody(id: string): Promise<void> {
 if (hasBody(id)) return Promise.resolve()
 let p = loadingBodies.get(id)
 if (!p) loadingBodies.set(id, p = gltf(`companion/body-${id}.glb`).then(g => {
  // The shared clips key every bone's position at the classic body's proportions: only the root's may move.
  const own = new Set(g.animations.map(c => c.name)), keep = (t: THREE.KeyframeTrack) => !t.name.endsWith(".position") || t.name.startsWith("root.")
  bodies.set(id, { scene: g.scene, clips: [...classic.clips.filter(c => !own.has(c.name)).map(c => new THREE.AnimationClip(c.name, c.duration, c.tracks.filter(keep))), ...g.animations] })
 }, e => { console.error("Couldn't load the body " + id, e); bodies.set(id, null) }))
 return p
}

/// Moves hair or a hat from the classic head onto another: each point keeps its direction from the head's middle, and
/// its distance grows or shrinks with the head's surface in that direction, plus a hair's breadth: the tables are
/// coarse, and without it the head pokes through the hairline in spots.
const wrapped = new Map<string, Float32Array>()
function wrapTo(name: string, src: Float32Array, key: string) {
 const w = fit.wrap, head = w.heads[key]
 if (!head || key === "round") return src
 const cached = wrapped.get(name + "|" + key); if (cached) return cached
 const out = new Float32Array(src.length), step = THREE.MathUtils.degToRad(w.step), around = Math.PI * 2 / w.cols
 const at = (r: number[], row: number, col: number) => {
  const r0 = Math.floor(row), r1 = Math.min(w.rows - 1, r0 + 1), fr = row - r0
  const c0 = Math.floor(col) % w.cols, c1 = (c0 + 1) % w.cols, fc = col - Math.floor(col)
  return (r[r0 * w.cols + c0] * (1 - fc) + r[r0 * w.cols + c1] * fc) * (1 - fr) + (r[r1 * w.cols + c0] * (1 - fc) + r[r1 * w.cols + c1] * fc) * fr
 }
 for (let k = 0; k < src.length; k += 3) {
  // three's axes (y up, +z to the front) into Blender's (z up, -y to the front), where the tables were made
  const dx = src[k] - w.c[0], dy = -src[k + 2] - w.c[1], dz = src[k + 1] - w.c[2], len = Math.hypot(dx, dy, dz) || 1e-6
  const row = Math.min(w.rows - 1, Math.acos(Math.max(-1, Math.min(1, dz / len))) / step)
  let phi = Math.atan2(dx, -dy); if (phi < 0) phi += Math.PI * 2
  const s = at(head.r, row, phi / around) / at(w.r, row, phi / around) + .006 / len
  out[k] = head.c[0] + dx * s; out[k + 1] = head.c[2] + dz * s; out[k + 2] = -(head.c[1] + dy * s)
 }
 wrapped.set(name + "|" + key, out)
 return out
}

// Soft felt: the vertex colors carry ambient occlusion (r), the face or a hat's second color (g) and the belly (b).
function felt(face: THREE.Texture | null) {
 const m = new THREE.MeshPhysicalMaterial({ roughness: .78, metalness: 0, sheen: .55, sheenRoughness: .55, specularIntensity: .22 })
 const u = { uColor: { value: new THREE.Color() }, uBelly: { value: new THREE.Color() }, uSecond: { value: new THREE.Color() }, uSecondOn: { value: 0 }, uFace: { value: face }, uRim: { value: new THREE.Color("#fff4ea").multiplyScalar(.32) } }
 m.onBeforeCompile = s => {
  Object.assign(s.uniforms, u)
  s.vertexShader = "attribute vec4 mask;\nattribute vec2 faceUv;\nvarying vec4 vMask;\nvarying vec2 vFaceUv;\n" + s.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\nvMask = mask; vFaceUv = faceUv;")
  s.fragmentShader = "uniform vec3 uColor, uBelly, uSecond, uRim;\nuniform float uSecondOn;\nuniform sampler2D uFace;\nvarying vec4 vMask;\nvarying vec2 vFaceUv;\n" + s.fragmentShader
   .replace("#include <color_fragment>", `vec3 tint = mix(uColor, uBelly, vMask.b);
tint = mix(tint, uSecond, vMask.g * uSecondOn);
float ink = 0.;
${face ? "vec4 drawn = texture2D(uFace, vFaceUv); ink = drawn.a * smoothstep(.05, .55, vMask.g); tint = mix(tint, drawn.rgb, ink);" : ""}
diffuseColor.rgb = tint * mix(.52, 1., vMask.r);`)
   // the drawn face is ink, not felt: no sheen haze or rim over it, so the eyes stay deep and their highlights white
   .replace("#include <opaque_fragment>", "outgoingLight = mix(outgoingLight, diffuseColor.rgb * .96, ink * .62);\noutgoingLight += uRim * (1. - ink) * pow(1. - saturate(dot(normal, normalize(vViewPosition))), 3.);\n#include <opaque_fragment>")
 }
 m.customProgramCacheKey = () => face ? "felt-face" : "felt"
 return { m, u }
}

// Fine strands running along each lock (its UVs: u around the lock, v along it), the same every time.
const strands = (() => {
 const c = document.createElement("canvas"); c.width = 256; c.height = 64
 const g = c.getContext("2d")!
 let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647
 for (let x = 0; x < 256; x++) { const v = Math.round(150 + rnd() * 105); g.fillStyle = `rgb(${v},${v},${v})`; g.fillRect(x, 0, 1, 64) }
 g.globalAlpha = .14
 for (let i = 0; i < 260; i++) { g.fillStyle = rnd() < .5 ? "#000" : "#fff"; g.fillRect(Math.floor(rnd() * 256), rnd() * 64, 1, 5 + rnd() * 12) }
 const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping
 return t
})()
// Hair: the vertex colors carry occlusion (r), each lock's own shade (g) and how freely it swings (b, 0 at the scalp).
function hairMaterial() {
 const m = new THREE.MeshPhysicalMaterial({ roughness: .7, metalness: 0, sheen: .35, sheenRoughness: .45, specularIntensity: .4 })
 const u = { uColor: { value: new THREE.Color() }, uStrands: { value: strands }, uSwing: { value: new THREE.Vector3() } }
 m.onBeforeCompile = s => {
  Object.assign(s.uniforms, u)
  s.vertexShader = "attribute vec4 mask;\nattribute vec2 strandUv;\nuniform vec3 uSwing;\nvarying vec4 vMask;\nvarying vec2 vStrand;\n" + s.vertexShader
   .replace("#include <begin_vertex>", "#include <begin_vertex>\nvMask = mask; vStrand = strandUv;\ntransformed += uSwing * mask.b * mask.b;")
  s.fragmentShader = "uniform vec3 uColor;\nuniform sampler2D uStrands;\nvarying vec4 vMask;\nvarying vec2 vStrand;\n" + s.fragmentShader
   .replace("#include <color_fragment>", `float strand = texture2D(uStrands, vStrand * vec2(3., .5)).r;
diffuseColor.rgb = uColor * mix(.8, 1.12, vMask.g) * mix(.84, 1.08, strand) * mix(.5, 1., vMask.r);`)
   .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = clamp(roughnessFactor + (.5 - strand) * .16, .6, .8);")
 }
 m.customProgramCacheKey = () => "hair"
 return { m, u }
}
const shadowTexture = (() => {
 const c = document.createElement("canvas"); c.width = c.height = 128
 const g = c.getContext("2d")!, r = g.createRadialGradient(64, 64, 0, 64, 64, 64)
 r.addColorStop(0, "rgba(38,30,26,.55)"); r.addColorStop(.45, "rgba(38,30,26,.26)"); r.addColorStop(1, "rgba(38,30,26,0)")
 g.fillStyle = r; g.fillRect(0, 0, 128, 128)
 return new THREE.CanvasTexture(c)
})()

const rnd = (k: number) => (Math.random() * 2 - 1) * k
const clamp = (v: number, k: number) => Math.max(-k, Math.min(k, v))
type Bones = Record<"root" | "head" | "lidL" | "lidR" | "browL" | "browR" | "mouth" | "look", THREE.Bone>
export class Companion {
 group = new THREE.Group()
 rig: THREE.Object3D
 body: THREE.SkinnedMesh
 classic: boolean
 parts = new Map<string, THREE.Mesh>()
 bones: Bones
 headRest: THREE.Quaternion
 headBind: THREE.Matrix4 // from the rest pose into the head bone's space: hair and hats hang on the head with it
 headY = .655
 mixer: THREE.AnimationMixer
 actions: Record<string, THREE.AnimationAction> = {}
 current?: THREE.AnimationAction
 base = "idle"
 face: { canvas: HTMLCanvasElement; g: CanvasRenderingContext2D; texture: THREE.CanvasTexture; key: string }
 hairMat = hairMaterial(); hatMat = felt(null); bodyMat: ReturnType<typeof felt>
 shadow: THREE.Mesh
 look?: Look; lookKey = ""; fitKey = ""
 state: MascotState = "idle"; gestureAt = 0
 // the little things nobody animates by hand: blinks, saccades, following the pointer, hair that lags behind
 blinkAt = 1 + Math.random() * 3; blinkStart = -9; fixAt = .5 + Math.random() * 2; glance = [0, 0]; gaze = [0, 0]; turn = [0, 0]
 swing = new THREE.Vector3(); swingVel = new THREE.Vector3(); headWas: THREE.Vector3 | null = null

 readonly bodyId: string
 constructor(bodyId: string) {
  this.bodyId = bodyId
  const model = (bodyId && bodies.get(bodyId)) || classic
  this.classic = model === classic
  this.rig = cloneRig(model.scene)
  this.group.add(this.rig)
  const canvas = document.createElement("canvas"); canvas.width = canvas.height = 1024
  const texture = new THREE.CanvasTexture(canvas); texture.flipY = false; texture.colorSpace = THREE.SRGBColorSpace; texture.anisotropy = 4
  this.face = { canvas, g: canvas.getContext("2d")!, texture, key: "" }
  this.bodyMat = felt(texture)
  this.body = this.rig.getObjectByName("Companion") as THREE.SkinnedMesh
  const extra: THREE.Object3D[] = []
  this.rig.traverse(o => {
   if (!(o as THREE.Mesh).isMesh) return
   if (/^(hair|hat)/.test(o.name)) { extra.push(o); return } // the classic model's own: every body gets its hair and hats below
   o.frustumCulled = false // props keep the material Blender painted them with
  })
  extra.forEach(o => o.removeFromParent())
  const g = this.body.geometry = this.body.geometry.clone() // each companion bakes its own head shape
  g.setAttribute("mask", g.getAttribute("color")); g.setAttribute("faceUv", g.getAttribute("uv") ?? g.getAttribute("position"))
  this.body.material = this.bodyMat.m
  const bone = (n: string) => this.rig.getObjectByName(n) as THREE.Bone
  this.headRest = bone("head").quaternion.clone()
  this.bones = { root: bone("root"), head: bone("head"), lidL: bone("lidL"), lidR: bone("lidR"), browL: bone("browL"), browR: bone("browR"), mouth: bone("mouth"), look: bone("look") }
  const sk = this.body.skeleton
  this.headBind = sk.boneInverses[sk.bones.indexOf(this.bones.head)]
  this.mixer = new THREE.AnimationMixer(this.rig)
  for (const c of model.clips) this.actions[c.name] = this.mixer.clipAction(c)
  this.mixer.addEventListener("finished", e => { if (e.action === this.current) this.play(this.base) })
  this.shadow = new THREE.Mesh(new THREE.PlaneGeometry(.95, .95), new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false }))
  this.shadow.rotation.x = -Math.PI / 2; this.shadow.position.y = .003; this.shadow.renderOrder = -1
  this.group.add(this.shadow)
  this.play("idle")
 }

 play(name: string) {
  const next = this.actions[name]
  if (!next || next === this.current && !ONCE.has(name)) return
  next.reset(); next.setLoop(ONCE.has(name) ? THREE.LoopOnce : THREE.LoopRepeat, Infinity); next.clampWhenFinished = true
  next.setEffectiveWeight(1).setEffectiveTimeScale(1).play()
  if (clock.still) { for (const a of Object.values(this.actions)) if (a !== next) a.stop() } // tests and pictures want the exact pose
  else if (this.current && this.current !== next) this.current.crossFadeTo(next, .32, false)
  this.current = next
 }

 setLook(look: Look) {
  const key = lookKey(look)
  if (key === this.lookKey) return
  const before = this.look
  this.look = look; this.lookKey = key; this.face.key = ""
  if (this.classic && (!before || before.shape !== look.shape || before.ears !== look.ears)) this.bake(look)
  const color = new THREE.Color(look.color)
  this.bodyMat.u.uColor.value.copy(color); this.bodyMat.u.uBelly.value.copy(color).lerp(new THREE.Color("#ffffff"), .38)
  this.bodyMat.m.sheenColor.copy(color).lerp(new THREE.Color("#ffffff"), .6)
  const hair = new THREE.Color(look.hairColor)
  this.hairMat.u.uColor.value.copy(hair); this.hairMat.m.sheenColor.copy(hair).lerp(new THREE.Color("#ffffff"), .5)
  const [hat, second] = HAT_COLORS[look.hat] ?? ["#888888", "#888888"]
  this.hatMat.u.uColor.value.set(hat); this.hatMat.u.uBelly.value.set(hat); this.hatMat.u.uSecond.value.set(second); this.hatMat.u.uSecondOn.value = 1
  this.hatMat.m.sheenColor.set(hat).lerp(new THREE.Color("#ffffff"), .5)
  const fitKey = this.classic ? look.shape : this.bodyId
  this.headY = fit.wrap.heads[fitKey]?.c[2] ?? .655
  if (fitKey !== this.fitKey) { this.fitKey = fitKey; for (const [name, mesh] of this.parts) this.fitPart(name, mesh) }
  const wear = [look.hair && "hair" + look.hair, look.hat && "hat" + look.hat]
  for (const name of wear) if (name && !this.parts.has(name) && partNames.includes(name)) this.addPart(name)
  for (const [name, mesh] of this.parts) mesh.visible = wear.includes(name)
 }

 /// Hair or a hat, made the first time this companion wears it.
 addPart(name: string) {
  const src = classic.scene.getObjectByName(name) as THREE.Mesh, g = src.geometry.clone()
  g.setAttribute("mask", g.getAttribute("color")); g.setAttribute("strandUv", g.getAttribute("uv") ?? g.getAttribute("position"))
  const mesh = new THREE.Mesh(g, name.startsWith("hat") ? this.hatMat.m : this.hairMat.m)
  mesh.name = name; mesh.frustumCulled = false; mesh.matrixAutoUpdate = false; mesh.matrix.copy(this.headBind)
  this.bones.head.add(mesh); this.parts.set(name, mesh)
  this.fitPart(name, mesh)
 }
 fitPart(name: string, mesh: THREE.Mesh) {
  const src = (classic.scene.getObjectByName(name) as THREE.Mesh).geometry.getAttribute("position").array as Float32Array
  const out = wrapTo(name, src, this.fitKey)
  mesh.geometry.setAttribute("position", new THREE.BufferAttribute(out === src ? new Float32Array(src) : out, 3))
  if (out !== src) mesh.geometry.computeVertexNormals()
 }

 /// Bakes the classic body's head shape and ear height into it.
 bake(look: Look) {
  const tpl = classic.scene.getObjectByName("Companion") as THREE.SkinnedMesh, src = tpl.geometry
  const base = src.getAttribute("position").array as Float32Array, out = new Float32Array(base)
  const names = tpl.morphTargetDictionary ?? {}
  const add = (name: string, w: number) => {
   const i = names[name]; if (i === undefined || !w) return
   const d = src.morphAttributes.position?.[i]?.array; if (!d) return
   for (let k = 0; k < out.length; k++) out[k] += d[k] * w
  }
  if (look.shape !== "round") add(look.shape, 1)
  add(look.ears > 0 ? "earsUp" : "earsDown", Math.abs(look.ears))
  const g = this.body.geometry
  g.morphAttributes = {}; this.body.morphTargetInfluences = undefined; this.body.morphTargetDictionary = undefined
  g.setAttribute("position", new THREE.BufferAttribute(out, 3)); g.computeVertexNormals()
 }

 setState(state: MascotState, gesture: string, gestureAt: number) {
  this.base = CLIP[state] === "done" ? "idle" : CLIP[state]
  if (gestureAt !== this.gestureAt && gesture) { this.gestureAt = gestureAt; this.play(gesture === "signature" ? this.actions.gesture ? "gesture" : "happy" : gesture) }
  else if (state !== this.state) this.play(CLIP[state])
  this.state = state
 }

 /// Moves time on, then layers blinks, glances and the pointer over the clip, swings the hair, and redraws the face if it changed.
 update(dt: number, t: number, follow: { x: number; y: number } | null) {
  const b = this.bones, still = clock.still, frozen = clock.frozen
  b.head.quaternion.copy(this.headRest); b.head.scale.set(1, 1, 1) // a clip may leave the head's channels out
  if (frozen !== null && this.current) { this.current.time = Math.min(frozen, this.current.getClip().duration - .01); this.mixer.update(0) }
  else this.mixer.update(dt)
  // Blinks come 2.5 to 6 seconds apart, now and then two in a row.
  if (!still && t > this.blinkAt) { this.blinkStart = t; this.blinkAt = t + (Math.random() < .14 ? .3 + Math.random() * .1 : 2.5 + Math.random() * 3.5) }
  // Saccades: the eyes jump to a spot and rest there. Mostly small hops, now and then a look around, which often comes with a blink.
  if (!still && t > this.fixAt) {
   const far = Math.random() < .28
   this.glance = Math.random() < .3 ? [0, 0] : far ? [rnd(.75), rnd(.32)] : [clamp(this.glance[0] + rnd(.16), .8), clamp(this.glance[1] + rnd(.08), .4)]
   if (far && t - this.blinkStart > 1 && Math.random() < .4) this.blinkStart = t
   this.fixAt = t + .35 + Math.random() * 2.1
  }
  const want = follow ?? { x: this.glance[0], y: this.glance[1] }
  const jump = still ? 1 : 1 - Math.exp(-dt * (follow ? 14 : 40)), k = still ? 1 : 1 - Math.exp(-dt * (follow ? 9 : 6))
  this.gaze[0] += (want.x - this.gaze[0]) * jump; this.gaze[1] += (want.y - this.gaze[1]) * jump
  const turn = follow ?? { x: 0, y: 0 }
  this.turn[0] += (turn.x - this.turn[0]) * k; this.turn[1] += (turn.y - this.turn[1]) * k
  if (Math.abs(this.turn[0]) + Math.abs(this.turn[1]) > .001)
   b.head.quaternion.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(this.turn[1] * .22, this.turn[0] * .38, 0)))
  if (this.look && this.look.head !== 1) b.head.scale.multiplyScalar(this.look.head)
  if (this.state === "listening") b.head.quaternion.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(.06, 0, .1)))
  // the shadow shrinks and fades as the companion leaves the ground
  const lift = Math.max(0, b.root.position.y)
  this.shadow.scale.setScalar(Math.max(.55, 1 - lift * 2.2) * (this.look?.head ?? 1)); (this.shadow.material as THREE.MeshBasicMaterial).opacity = Math.max(.35, 1 - lift * 3)
  this.swingHair(dt, still)
  const since = t - this.blinkStart, B = fit.blink
  const blink = still || since < 0 || since > B.seconds || !blinkCurve ? 1 : blinkCurve.evaluate(since * B.stretch)[1]
  const pose: FacePose = {
   open: (b.lidL.scale.y + b.lidR.scale.y) / 2 * blink * (this.state === "listening" ? 1.05 : 1),
   squint: Math.min(1, Math.max(0, Math.max(b.lidL.scale.x, b.lidR.scale.x) - 1)),
   raise: (b.browL.scale.y + b.browR.scale.y) / 2 - 1 + (this.state === "listening" ? .15 : 0),
   worry: Math.min(1, Math.max(0, ((b.browL.scale.x + b.browR.scale.x) / 2 - 1) / .45)),
   mouthOpen: Math.max(0, b.mouth.scale.y - 1),
   smile: (b.mouth.scale.x - .85) / .15,
   gx: (b.look.scale.x - 1) / .6 + this.gaze[0], gy: -(b.look.scale.y - 1) / .45 + this.gaze[1],
  }
  const key = this.lookKey + Object.values(pose).map(v => Math.round(v * 40)).join()
  if (key !== this.face.key && this.look) { this.face.key = key; drawFace(this.face.g, 1024, this.look, pose); this.face.texture.needsUpdate = true }
 }

 /// Hair lags behind the head: a stiff, lightly damped spring pulled against the head's movement, so a hop flicks the
 /// ends up, a landing drops them, and they settle after one bounce. Only the ends swing (vertex color b).
 swingHair(dt: number, still: boolean) {
  const hair = [...this.parts.values()].some(m => m.visible && m.name.startsWith("hair"))
  if (still || !hair || dt <= 0) { this.swing.set(0, 0, 0); this.swingVel.set(0, 0, 0); this.headWas = null; this.hairMat.u.uSwing.value.set(0, 0, 0); return }
  this.group.updateMatrixWorld(true)
  const toWorld = new THREE.Matrix4().multiplyMatrices(this.bones.head.matrixWorld, this.headBind)
  const c = fit.wrap.heads[this.fitKey]?.c ?? fit.wrap.c, at = new THREE.Vector3(c[0], c[2], -c[1]).applyMatrix4(toWorld)
  if (this.headWas) {
   const target = at.clone().sub(this.headWas).multiplyScalar(-.045 / dt).clampLength(0, .05)
   const pull = target.sub(this.swing).multiplyScalar(170).addScaledVector(this.swingVel, -11)
   this.swingVel.addScaledVector(pull, dt); this.swing.addScaledVector(this.swingVel, dt)
  }
  this.headWas = at
  this.hairMat.u.uSwing.value.copy(this.swing).applyMatrix3(new THREE.Matrix3().setFromMatrix4(toWorld).invert())
 }

 dispose() {
  this.body.geometry.dispose()
  for (const m of this.parts.values()) m.geometry.dispose()
  for (const m of [this.hairMat, this.hatMat, this.bodyMat]) m.m.dispose()
  this.face.texture.dispose(); this.shadow.geometry.dispose(); (this.shadow.material as THREE.Material).dispose()
  this.mixer.stopAllAction()
 }
}

// ---------------------------------------------------------------- the shared renderer

let renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.PerspectiveCamera
const instances = new Map<string, Companion>()
const FRAMES = { full: { y: .58, span: 1.42 }, bust: { y: .7, span: .98 }, head: { y: .66, span: .7 } }

function setup() {
 renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, premultipliedAlpha: true, powerPreference: "low-power" })
 renderer.setPixelRatio(1); renderer.setSize(512, 512, false)
 renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = 1
 scene = new THREE.Scene()
 camera = new THREE.PerspectiveCamera(22, 1, .1, 20)
 scene.add(new THREE.HemisphereLight("#fff8f0", "#c6bcb2", 1.9))
 const key = new THREE.DirectionalLight("#fff6ec", 2.3); key.position.set(-1.6, 2.6, 2.2); scene.add(key)
 const fill = new THREE.DirectionalLight("#eef2ff", .55); fill.position.set(2.2, 1, 1.4); scene.add(fill)
 const rim = new THREE.DirectionalLight("#ffffff", 2.6); rim.position.set(.9, 1.8, -2.4); scene.add(rim)
}

/// Frames the camera; close-ups follow the head, which sits higher or lower on each body.
function aim(frame: Frame, headY: number, az = .16) {
 const f = FRAMES[frame], d = f.span / 2 / Math.tan(THREE.MathUtils.degToRad(11)), y = f.y + (headY - .655) * (frame === "full" ? .4 : 1)
 camera.position.set(Math.sin(az) * d, y + d * .07, Math.cos(az) * d); camera.lookAt(0, y, 0)
}

/// Draws one companion into the top-left w x w of the shared canvas.
function draw(c: Companion, w: number, frame: Frame) {
 if (renderer.domElement.width < w) renderer.setSize(Math.min(768, w), Math.min(768, w), false)
 const H = renderer.domElement.height
 for (const o of instances.values()) o.group.visible = o === c
 if (!c.group.parent) scene.add(c.group)
 c.group.visible = true
 aim(frame, c.headY)
 renderer.setScissorTest(true)
 renderer.setViewport(0, H - w, w, w); renderer.setScissor(0, H - w, w, w)
 renderer.setClearColor(0, 0); renderer.clear()
 renderer.render(scene, camera)
 renderer.setScissorTest(false)
}

function pointerFor(s: Slot) {
 if (!s.follow || pointer.x < 0) return null
 const r = s.canvas.getBoundingClientRect(), cl = (v: number) => Math.max(-1, Math.min(1, v))
 return { x: cl((pointer.x - r.left - r.width / 2) / (innerWidth * .35)), y: cl((pointer.y - r.top - r.height * .35) / (innerHeight * .4)) }
}

let last = 0, frame = 0
function tick(now: number) {
 frame = requestAnimationFrame(tick)
 if (document.hidden) return
 const visible = [...slots.values()].filter(s => s.visible)
 for (const [id, c] of instances) if (!slots.has(id)) { scene.remove(c.group); c.dispose(); instances.delete(id) }
 if (!visible.length) return
 const busy = visible.some(s => s.canvas.width >= 320 && s.state !== "idle")
 if (now - last < 1000 / (busy ? 60 : 30) - 2) return
 const dt = Math.min(.05, last ? (now - last) / 1000 : 1 / 30), t = clock.frozen ?? now / 1000
 last = now
 for (const s of visible) {
  if (!hasBody(s.look.body)) { void loadBody(s.look.body); continue } // its picture shows until the body is in
  let c = instances.get(s.id)
  if (c && c.bodyId !== s.look.body) { scene.remove(c.group); c.dispose(); c = undefined }
  if (!c) instances.set(s.id, c = new Companion(s.look.body))
  c.setLook(s.look); c.setState(s.state, s.gesture, s.gestureAt)
  c.update(dt, t, pointerFor(s))
  const w = Math.min(s.canvas.width, 768)
  draw(c, w, s.frame)
  const ctx = s.canvas.getContext("2d")!
  ctx.clearRect(0, 0, s.canvas.width, s.canvas.height)
  ctx.drawImage(renderer.domElement, 0, 0, w, w, 0, 0, s.canvas.width, s.canvas.height)
  s.canvas.dataset.live = ""
 }
}

export function start() {
 if (renderer) return
 setup()
 frame = requestAnimationFrame(tick)
}
export const stop = () => cancelAnimationFrame(frame)

// Where each state's picture is taken from its clip, in seconds.
const STILL_AT: Partial<Record<MascotState, number>> = { idle: .4, working: .25, needs: .45, done: .95, error: 2, thinking: 1.6, talking: .3, pointing: 1 }
/// A still picture of a look, for small places and for reduced motion. Its body must be loaded first (loadBody).
export function picture(look: Look, state: MascotState, px: number, frame: Frame) {
 start()
 const c = new Companion(look.body)
 c.setLook(look); c.state = state; c.play(CLIP[state])
 if (c.current) { c.current.time = Math.min(STILL_AT[state] ?? .4, c.current.getClip().duration - .01); c.mixer.update(0) }
 c.blinkAt = c.fixAt = Infinity
 c.update(0, 0, null)
 instances.set("__picture", c)
 draw(c, px, frame)
 const out = document.createElement("canvas"); out.width = out.height = px
 out.getContext("2d")!.drawImage(renderer.domElement, 0, 0, px, px, 0, 0, px, px)
 scene.remove(c.group); instances.delete("__picture"); c.dispose()
 return out.toDataURL("image/webp", .9)
}
