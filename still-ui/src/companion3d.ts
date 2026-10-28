import * as THREE from "three"
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js"
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js"
import { clone as cloneRig } from "three/addons/utils/SkeletonUtils.js"
import { drawFace, type FacePose } from "./face"
import { lookKey, type Look } from "./look"
import { clock, pointer, slots, type Frame, type MascotState, type Slot } from "./Mascot"

// The companion in 3D: one rigged, Draco-compressed model built in Blender (tools/mascot), tinted, shaped and dressed
// per look, its face drawn onto a canvas texture. Loaded lazily; one hidden WebGL canvas renders every visible
// companion in turn and copies it into that companion's own canvas, at most 30 times a second (60 for a big one
// that's moving), and not at all while the window is hidden.

type Fit = { shapes: Record<string, { lift: number; sx: number; sy: number }> }
const CLIP: Record<MascotState, string> = { idle: "idle", listening: "idle", thinking: "think", working: "work", needs: "needs", done: "done", error: "sad", talking: "talk", pointing: "point" }
const ONCE = new Set(["done", "happy", "point", "wave", "admire", "pop"])
const HEAD = new THREE.Vector3(0, .655, 0) // hats and hair scale around the head's middle
const HAT_COLORS: Record<string, [string, string]> = {
 beanie: ["#d1495b", "#f4efe6"], cap: ["#3e7cb1", "#2d3142"], tophat: ["#2b2d42", "#c8553d"], party: ["#5aa9e6", "#ffd166"], beret: ["#c8553d", "#2d3142"],
 bucket: ["#e9c46a", "#6c8a5a"], crown: ["#f2c14e", "#b8862f"], headphones: ["#e8e4dc", "#3a3a46"], flower: ["#f7a1c4", "#ffd166"], bow: ["#e05a6d", "#b23a48"],
}

let template: THREE.Object3D, clips: THREE.AnimationClip[], fit: Fit
export async function load() {
 const draco = new DRACOLoader().setDecoderConfig({ type: "wasm" }) // three bundles its own decoder next to this file
 const [gltf, f] = await Promise.all([new GLTFLoader().setDRACOLoader(draco).loadAsync("companion/companion.glb"), fetch("companion/fit.json").then(r => r.json())])
 draco.dispose()
 template = gltf.scene; clips = gltf.animations; fit = f
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
const shadowTexture = (() => {
 const c = document.createElement("canvas"); c.width = c.height = 128
 const g = c.getContext("2d")!, r = g.createRadialGradient(64, 64, 0, 64, 64, 64)
 r.addColorStop(0, "rgba(38,30,26,.55)"); r.addColorStop(.45, "rgba(38,30,26,.26)"); r.addColorStop(1, "rgba(38,30,26,0)")
 g.fillStyle = r; g.fillRect(0, 0, 128, 128)
 return new THREE.CanvasTexture(c)
})()

type Bones = Record<"root" | "head" | "lidL" | "lidR" | "browL" | "browR" | "mouth" | "look", THREE.Bone>
export class Companion {
 group = new THREE.Group()
 rig: THREE.Object3D
 body: THREE.SkinnedMesh
 parts = new Map<string, THREE.SkinnedMesh>()
 bones: Bones
 headRest: THREE.Quaternion
 mixer: THREE.AnimationMixer
 actions: Record<string, THREE.AnimationAction> = {}
 current?: THREE.AnimationAction
 base = "idle"
 face: { canvas: HTMLCanvasElement; g: CanvasRenderingContext2D; texture: THREE.CanvasTexture; key: string }
 hairMat = felt(null); hatMat = felt(null); bodyMat: ReturnType<typeof felt>
 shadow: THREE.Mesh
 look?: Look; lookKey = ""
 state: MascotState = "idle"; gestureAt = 0
 // the little things nobody animates by hand: blinks, glances, following the pointer
 blinkAt = 1 + Math.random() * 3; blinkEnd = 0; glanceAt = 2 + Math.random() * 4; glanceEnd = 0; glance = [0, 0]; gaze = [0, 0]; turn = [0, 0]

 constructor() {
  this.rig = cloneRig(template)
  this.group.add(this.rig)
  const canvas = document.createElement("canvas"); canvas.width = canvas.height = 1024
  const texture = new THREE.CanvasTexture(canvas); texture.flipY = false; texture.colorSpace = THREE.SRGBColorSpace; texture.anisotropy = 4
  this.face = { canvas, g: canvas.getContext("2d")!, texture, key: "" }
  this.bodyMat = felt(texture)
  this.body = this.rig.getObjectByName("Companion") as THREE.SkinnedMesh
  this.rig.traverse(o => {
   if (!(o as THREE.SkinnedMesh).isSkinnedMesh) return
   const mesh = o as THREE.SkinnedMesh
   const g = mesh.geometry = mesh.geometry.clone() // each companion bakes its own head shape and fit
   g.setAttribute("mask", g.getAttribute("color")); g.setAttribute("faceUv", g.getAttribute("uv") ?? g.getAttribute("position"))
   mesh.frustumCulled = false
   if (mesh !== this.body) { this.parts.set(mesh.name, mesh); mesh.visible = false; mesh.material = mesh.name.startsWith("hat") ? this.hatMat.m : this.hairMat.m }
  })
  this.body.material = this.bodyMat.m
  const bone = (n: string) => this.rig.getObjectByName(n) as THREE.Bone
  this.headRest = bone("head").quaternion.clone()
  this.bones = { root: bone("root"), head: bone("head"), lidL: bone("lidL"), lidR: bone("lidR"), browL: bone("browL"), browR: bone("browR"), mouth: bone("mouth"), look: bone("look") }
  this.mixer = new THREE.AnimationMixer(this.rig)
  for (const c of clips) this.actions[c.name] = this.mixer.clipAction(c)
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
  if (!before || before.shape !== look.shape || before.ears !== look.ears) this.bake(look)
  const color = new THREE.Color(look.color)
  this.bodyMat.u.uColor.value.copy(color); this.bodyMat.u.uBelly.value.copy(color).lerp(new THREE.Color("#ffffff"), .38)
  this.bodyMat.m.sheenColor.copy(color).lerp(new THREE.Color("#ffffff"), .6)
  const hair = new THREE.Color(look.hairColor)
  this.hairMat.u.uColor.value.copy(hair); this.hairMat.u.uBelly.value.copy(hair); this.hairMat.m.sheenColor.copy(hair).lerp(new THREE.Color("#ffffff"), .5)
  const [hat, second] = HAT_COLORS[look.hat] ?? ["#888888", "#888888"]
  this.hatMat.u.uColor.value.set(hat); this.hatMat.u.uBelly.value.set(hat); this.hatMat.u.uSecond.value.set(second); this.hatMat.u.uSecondOn.value = 1
  this.hatMat.m.sheenColor.set(hat).lerp(new THREE.Color("#ffffff"), .5)
  for (const [name, mesh] of this.parts) mesh.visible = name === "hair" + look.hair || name === "hat" + look.hat
 }

 /// Bakes the head shape and ear height into the body, and fits hair and hats to that head.
 bake(look: Look) {
  const src = (template.getObjectByName("Companion") as THREE.SkinnedMesh).geometry
  const base = src.getAttribute("position").array as Float32Array, out = new Float32Array(base)
  const names = (template.getObjectByName("Companion") as THREE.SkinnedMesh).morphTargetDictionary ?? {}
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
  const f = fit.shapes[look.shape] ?? { lift: 0, sx: 1, sy: 1 }
  for (const [name, mesh] of this.parts) {
   const p = ((template.getObjectByName(name) as THREE.Mesh).geometry.getAttribute("position").array as Float32Array), q = new Float32Array(p)
   for (let k = 0; k < q.length; k += 3) {
    q[k] = HEAD.x + (p[k] - HEAD.x) * f.sx; q[k + 1] = p[k + 1] + f.lift; q[k + 2] = HEAD.z + (p[k + 2] - HEAD.z) * f.sy
   }
   mesh.geometry.setAttribute("position", new THREE.BufferAttribute(q, 3))
  }
 }

 setState(state: MascotState, gesture: string, gestureAt: number) {
  this.base = CLIP[state] === "done" ? "idle" : CLIP[state]
  if (gestureAt !== this.gestureAt && gesture) { this.gestureAt = gestureAt; this.play(gesture) }
  else if (state !== this.state) this.play(CLIP[state])
  this.state = state
 }

 /// Moves time on, then layers blinks, glances and the pointer over the clip, and redraws the face if it changed.
 update(dt: number, t: number, follow: { x: number; y: number } | null) {
  const b = this.bones, still = clock.still, frozen = clock.frozen
  b.head.quaternion.copy(this.headRest); b.head.scale.set(1, 1, 1) // a clip may leave the head's channels out
  if (frozen !== null && this.current) { this.current.time = Math.min(frozen, this.current.getClip().duration - .01); this.mixer.update(0) }
  else this.mixer.update(dt)
  if (!still && t > this.blinkAt) { this.blinkEnd = t + .14; this.blinkAt = t + 2 + Math.random() * 4; if (Math.random() < .15) this.blinkAt = t + .3 }
  if (!still && t > this.glanceAt) { this.glance = [(Math.random() * 2 - 1) * .8, (Math.random() * 2 - 1) * .35]; this.glanceEnd = t + .7 + Math.random() * .9; this.glanceAt = t + 3 + Math.random() * 5 }
  const want = follow ?? (t < this.glanceEnd ? { x: this.glance[0], y: this.glance[1] } : { x: 0, y: 0 })
  const k = still ? 1 : 1 - Math.exp(-dt * (follow ? 9 : 6))
  this.gaze[0] += (want.x - this.gaze[0]) * k; this.gaze[1] += (want.y - this.gaze[1]) * k
  const turn = follow ?? { x: 0, y: 0 }
  this.turn[0] += (turn.x - this.turn[0]) * k; this.turn[1] += (turn.y - this.turn[1]) * k
  if (Math.abs(this.turn[0]) + Math.abs(this.turn[1]) > .001)
   b.head.quaternion.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(this.turn[1] * .22, this.turn[0] * .38, 0)))
  if (this.look && this.look.head !== 1) b.head.scale.multiplyScalar(this.look.head)
  if (this.state === "listening") b.head.quaternion.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(.06, 0, .1)))
  // the shadow shrinks and fades as the companion leaves the ground
  const lift = Math.max(0, b.root.position.y)
  this.shadow.scale.setScalar(Math.max(.55, 1 - lift * 2.2) * (this.look?.head ?? 1)); (this.shadow.material as THREE.MeshBasicMaterial).opacity = Math.max(.35, 1 - lift * 3)
  const blink = !still && t < this.blinkEnd ? .05 : 1
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

 dispose() {
  this.rig.traverse(o => { if ((o as THREE.Mesh).isMesh) (o as THREE.Mesh).geometry.dispose() })
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

function aim(frame: Frame, az = .16) {
 const f = FRAMES[frame], d = f.span / 2 / Math.tan(THREE.MathUtils.degToRad(11))
 camera.position.set(Math.sin(az) * d, f.y + d * .07, Math.cos(az) * d); camera.lookAt(0, f.y, 0)
}

/// Draws one companion into the top-left w x w of the shared canvas.
function draw(c: Companion, w: number, frame: Frame) {
 if (renderer.domElement.width < w) renderer.setSize(Math.min(768, w), Math.min(768, w), false)
 const H = renderer.domElement.height
 for (const o of instances.values()) o.group.visible = o === c
 if (!c.group.parent) scene.add(c.group)
 c.group.visible = true
 aim(frame)
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
  let c = instances.get(s.id)
  if (!c) instances.set(s.id, c = new Companion())
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
/// A still picture of a look, for small places and for reduced motion.
export function picture(look: Look, state: MascotState, px: number, frame: Frame) {
 start()
 const c = new Companion()
 c.setLook(look); c.state = state; c.play(CLIP[state])
 if (c.current) { c.current.time = Math.min(STILL_AT[state] ?? .4, c.current.getClip().duration - .01); c.mixer.update(0) }
 c.blinkAt = c.glanceAt = Infinity
 c.update(0, 0, null)
 instances.set("__picture", c)
 draw(c, px, frame)
 const out = document.createElement("canvas"); out.width = out.height = px
 out.getContext("2d")!.drawImage(renderer.domElement, 0, 0, px, px, 0, 0, px, px)
 scene.remove(c.group); instances.delete("__picture"); c.dispose()
 return out.toDataURL("image/webp", .9)
}
