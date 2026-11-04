import * as THREE from "three"
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js"
import { mergeVertices } from "three/addons/utils/BufferGeometryUtils.js"
import { HOLD, hasAccent, isV2, lookKey, type Look } from "./look"
import { STATES, clock, pointer, slots, type Frame, type MascotState, type Slot } from "./Mascot"
import { Rigged, bounds, model, rigFor, zoned, type Zones } from "./rig"
export { onRigReady, model as preload } from "./rig"

// The companions as soft blobs, built here from code: no model files. A body is a sphere pushed into a silhouette
// (SHAPE), with two glossy bead eyes, a tiny smile, two nub arms, one job prop and maybe an accessory. Motion is
// procedural: every state and gesture is a pose over time (keyed curves with squash and stretch), and props and
// accessories follow through on a spring. One hidden WebGL canvas renders every visible companion in turn and copies
// it into that companion's own canvas, at most 30 times a second (60 for a big one that's moving), and not at all
// while the window is hidden.

// ---------------------------------------------------------------- shapes

// h: height. w: half width. d: depth over width. top/bot: how square the dome and the base are (2 is round). taper:
// wider at the base (+) or the top (-). n: how square it is seen from above. mid: where it's widest, up from the base.
// lean: the top sits this far to one side. bump: a soft knob on top. eye: eye height over h.
type ShapeDef = { h: number; w: number; d: number; top: number; bot: number; taper: number; n: number; mid: number; lean: number; bump: number; eye: number }
const SHAPE: Record<string, ShapeDef> = {
 bean: { h: 1, w: .4, d: .84, top: 2.2, bot: 3, taper: .06, n: 2, mid: .44, lean: 0, bump: 0, eye: .63 },
 tall: { h: 1.2, w: .39, d: .8, top: 2.6, bot: 3.2, taper: -.05, n: 2.1, mid: .5, lean: 0, bump: 0, eye: .68 },
 gumdrop: { h: .98, w: .46, d: .86, top: 2.05, bot: 3.4, taper: .15, n: 2, mid: .38, lean: 0, bump: 0, eye: .6 },
 block: { h: 1.04, w: .41, d: .8, top: 3.6, bot: 3.8, taper: 0, n: 2.9, mid: .5, lean: 0, bump: 0, eye: .64 },
 round: { h: .84, w: .44, d: .94, top: 2, bot: 2.5, taper: .03, n: 2, mid: .46, lean: 0, bump: 0, eye: .6 },
 squat: { h: .76, w: .51, d: .82, top: 2.7, bot: 3.3, taper: .05, n: 2.3, mid: .45, lean: 0, bump: 0, eye: .6 },
 bump: { h: .92, w: .41, d: .84, top: 2.6, bot: 3, taper: .06, n: 2, mid: .46, lean: 0, bump: .095, eye: .62 },
 lean: { h: 1.12, w: .355, d: .8, top: 2.1, bot: 2.9, taper: .05, n: 2, mid: .42, lean: .1, bump: 0, eye: .66 },
 crest: { h: .98, w: .43, d: .82, top: 2.3, bot: 3, taper: -.18, n: 2, mid: .62, lean: 0, bump: 0, eye: .68 },
}
const pw = (v: number, e: number) => Math.sign(v) * Math.abs(v) ** e

type Hit = { p: THREE.Vector3; n: THREE.Vector3 }
type Built = { def: ShapeDef; geo: THREE.BufferGeometry; eyes: Hit[]; mouth: Hit; shoulders: Hit[]; belly: Hit; top: Hit; hit: (o: THREE.Vector3, d: THREE.Vector3) => Hit }
const built = new Map<string, Built>()
function shape(id: string): Built {
 const have = built.get(id); if (have) return have
 const s = SHAPE[id] ?? SHAPE.bean
 let geo: THREE.BufferGeometry = new THREE.IcosahedronGeometry(1, 28)
 geo.deleteAttribute("normal"); geo.deleteAttribute("uv")
 geo = mergeVertices(geo, 1e-5)
 const pos = geo.getAttribute("position") as THREE.BufferAttribute, v = new THREE.Vector3()
 const below = s.h * s.mid, above = s.h - below
 for (let i = 0; i < pos.count; i++) {
  v.fromBufferAttribute(pos, i).normalize()
  const ring = Math.hypot(v.x, v.z), a = Math.atan2(v.y, ring), e = a > 0 ? s.top : s.bot
  const Y = pw(Math.sin(a), 2 / e), R = Math.abs(Math.cos(a)) ** (2 / e)
  const th = Math.atan2(v.z, v.x), r = R * s.w * (1 - s.taper * Y)
  let x = r * pw(Math.cos(th), 2 / s.n)
  const z = r * s.d * pw(Math.sin(th), 2 / s.n)
  let y = below + Y * (Y > 0 ? above : below)
  x += s.lean * (y / s.h) ** 2
  if (s.bump) { // a round knob on top, blended into the head
   const kr = s.bump, d = Math.hypot(x - .03, z), ky = s.h - kr * .62
   const knob = d < kr ? ky + kr * Math.sqrt(1 - (d / kr) ** 2) : ky - (d - kr) * 3
   y = (y + knob + Math.sqrt((y - knob) ** 2 + .0016)) / 2
  }
  pos.setXYZ(i, x, y, z)
 }
 geo.computeVertexNormals()
 const mesh = new THREE.Mesh(geo), ray = new THREE.Raycaster()
 const hit = (o: THREE.Vector3, d: THREE.Vector3): Hit => {
  ray.set(o, d.clone().normalize())
  const h = ray.intersectObject(mesh)[0]
  return h ? { p: h.point.clone(), n: h.face!.normal.clone() } : { p: o.clone(), n: d.clone().negate() }
 }
 const front = (x: number, y: number) => hit(new THREE.Vector3(x, y, 3), new THREE.Vector3(0, 0, -1))
 const ey = s.eye * s.h, lx = s.lean * (ey / s.h) ** 2, ax = s.lean * (.5) ** 2
 const out: Built = {
  def: s, geo, hit,
  eyes: [-1, 1].map(k => front(lx + k * .118, ey)),
  mouth: front(lx, ey - .075),
  shoulders: [-1, 1].map(k => hit(new THREE.Vector3(ax + k * 3, s.h * .47, .1), new THREE.Vector3(-k, 0, 0))),
  belly: front(ax, s.h * .29),
  top: hit(new THREE.Vector3(s.lean + .02, 3, 0), new THREE.Vector3(0, -1, 0)),
 }
 built.set(id, out)
 return out
}

// ---------------------------------------------------------------- materials

const mats = new Map<string, THREE.Material>()
/// Soft vinyl for props: one material per color, shared.
function soft(color: string, extra: THREE.MeshPhysicalMaterialParameters = {}) {
 const key = color + JSON.stringify(extra)
 let m = mats.get(key)
 if (!m) mats.set(key, m = new THREE.MeshPhysicalMaterial({ color, roughness: .5, metalness: 0, clearcoat: .3, clearcoatRoughness: .5, envMapIntensity: .45, ...extra }))
 return m
}
const INK = () => soft("#1d1a24", { roughness: .25, clearcoat: .6, clearcoatRoughness: .1, envMapIntensity: .55 })
const SHINE = new THREE.MeshBasicMaterial({ color: "#ffffff" })

// The body: matte vinyl with a broad soft highlight, a gentle rim, a little darker where it meets the ground, and
// soft occlusion where an arm or a prop comes close (each a sphere, in view space).
function vinyl(ground: number) {
 const m = new THREE.MeshPhysicalMaterial({ roughness: .52, metalness: 0, clearcoat: .22, clearcoatRoughness: .55, sheen: .1, sheenRoughness: .8, envMapIntensity: .34 })
 const u = { uRim: { value: new THREE.Color() }, uGround: { value: ground }, uOcc: { value: [0, 1, 2, 3].map(() => new THREE.Vector4(0, 0, 0, 0)) } }
 m.onBeforeCompile = s => {
  Object.assign(s.uniforms, u)
  s.vertexShader = "varying float vLocalY;\n" + s.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\nvLocalY = position.y;")
  s.fragmentShader = "uniform vec3 uRim;\nuniform float uGround;\nuniform vec4 uOcc[4];\nvarying float vLocalY;\n" + s.fragmentShader
   .replace("#include <opaque_fragment>", `{
 vec3 P = -vViewPosition; float occ = 0.;
 for (int i = 0; i < 4; i++) { vec3 d = uOcc[i].xyz - P; float l = max(length(d), 1e-3), r = uOcc[i].w; occ += r * r / (l * l) * max(dot(normal, d / l), 0.); }
 float ao = (1. - .5 * clamp(occ, 0., 1.)) * mix(1., mix(.7, 1., smoothstep(0., .2, vLocalY)), uGround);
 outgoingLight *= ao;
 outgoingLight += uRim * pow(1. - saturate(dot(normal, normalize(vViewPosition))), 2.6) * ao;
}
#include <opaque_fragment>`)
 }
 m.customProgramCacheKey = () => "blob"
 return { m, u }
}

const shadowTexture = (() => {
 const c = document.createElement("canvas"); c.width = c.height = 128
 const g = c.getContext("2d")!, r = g.createRadialGradient(64, 64, 0, 64, 64, 64)
 r.addColorStop(0, "rgba(40,32,36,.5)"); r.addColorStop(.35, "rgba(40,32,36,.3)"); r.addColorStop(1, "rgba(40,32,36,0)")
 g.fillStyle = r; g.fillRect(0, 0, 128, 128)
 const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace
 return t
})()

// ---------------------------------------------------------------- props and accessories

function put(g: THREE.Object3D, geo: THREE.BufferGeometry, mat: THREE.Material, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0) {
 const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.rotation.set(rx, ry, rz); g.add(m); return m
}
const tube = (pts: number[][], r: number) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p))), 24, r, 10)
const ball = (r: number) => new THREE.SphereGeometry(r, 20, 14)
function blob(g: THREE.Object3D, mat: THREE.Material, sx: number, sy: number, sz: number, x = 0, y = 0, z = 0) { const m = put(g, ball(1), mat, x, y, z); m.scale.set(sx, sy, sz); return m }

// The props (Blender: rig/props.py): ten real things, at their real sizes, in one glb. Each is cloned from it as it's
// held, and a look with a prop isn't drawn until they're in (make waits, as for a rig). The six roles carry none.
// How each is carried: in both nubs in front of the belly, in the right nub, or worn.
const METERS = 1.5 // the models are in meters; a blob is about 1 tall. Small things are drawn bigger (s), so they read
// Each as it's held: the point of it that sits on the hold point (at, in meters: in the nub, where it's gripped), its
// turn toward the companion (r: x, y, z), its scale (s) and where the eyes go to look at it (gx, gy).
const HELD: Record<string, { at: number[]; r: number[]; s?: number; look: number[] }> = {
 laptop: { at: [0, 0, 0], r: [0, 1, 0], look: [.3, 1] },
 notebook: { at: [0, 0, 0], r: [.6, 0, 0], s: 1.6, look: [0, 1] },
 camera: { at: [0, 0, 0], r: [0, -.3, 0], s: 2.4, look: [.1, .7] },
 mug: { at: [.066, 0, 0], r: [0, .95, 0], s: 2.2, look: [.8, .5] },
 phone: { at: [0, -.045, 0], r: [.3, .5, 0], s: 2.2, look: [.8, .6] },
 magnifier: { at: [0, -.03, 0], r: [0, .8, 0], s: 1.9, look: [.8, .2] },
 wrench: { at: [0, -.06, 0], r: [0, 0, -.25], s: 2.2, look: [.8, .4] },
 paintbrush: { at: [0, -.05, 0], r: [.3, 0, -.3], s: 2.6, look: [.8, .1] },
 briefcase: { at: [0, .03, 0], r: [0, -.8, 0], s: 1.05, look: [.6, 1] },
}
const props = new Map<string, THREE.Group>()
const part = (scene: THREE.Object3D, name: string) => scene.getObjectByName(THREE.PropertyBinding.sanitizeNodeName("prop." + name))!.clone()
/// The prop as it's held (its hold point at the origin, turned toward the companion, at blob scale), or null for none or
/// while the models load.
function prop(id: string, b: Built, top: boolean): THREE.Group | null {
 const m = HOLD[id] ? model("props") : null
 if (!m) return null
 const key = HOLD[id] === "worn" ? id + "|" + b.def.h + b.def.w + (top ? "|back" : "") : id
 let g = props.get(key)
 if (!g) { props.set(key, g = HOLD[id] === "worn" ? headphones(m.scene, b, top ? .45 : 0) : held(m.scene, id)); g.traverse(o => { o.frustumCulled = false }) }
 return g.clone()
}
function held(scene: THREE.Object3D, id: string) {
 const g = new THREE.Group(), turn = new THREE.Group(), n = part(scene, id), h = HELD[id]
 n.position.fromArray(h.at).negate(); turn.rotation.fromArray(h.r as [number, number, number]); turn.add(n); g.add(turn)
 g.scale.setScalar(h.s ?? METERS)
 return g
}
/// Over-ear headphones: the band (made round, radius 1) laid over the top of this head, each point at its own angle and
/// keeping its own thickness, and a cup over each side.
function headphones(scene: THREE.Object3D, b: Built, BACK: number) {
 const g = new THREE.Group(), s = b.def, c = new THREE.Vector3(s.lean * .3, s.eye * s.h + .03, 0), at: Hit[] = [] // the cups a little over the eyes, clear of a raised nub
 // the band over the crown, tipped back (BACK) behind a bow, sprout or flower; the cups at the sides
 const side = new THREE.Vector3(0, Math.sin(BACK), Math.cos(BACK))
 for (let i = 0; i <= 180; i++) { const a = (i - 90) * Math.PI / 180, d = new THREE.Vector3(Math.sin(a), Math.cos(a) * Math.cos(BACK), -Math.cos(a) * Math.sin(BACK)); at.push(b.hit(c.clone().addScaledVector(d, 3), d.negate())) }
 const band = part(scene, "headphones.band"), v = new THREE.Vector3()
 band.traverse(o => {
  const mesh = o as THREE.Mesh
  if (!mesh.isMesh) return
  const geo = mesh.geometry = mesh.geometry.clone(), pos = geo.getAttribute("position") as THREE.BufferAttribute
  for (let i = 0; i < pos.count; i++) {
   v.fromBufferAttribute(pos, i)
   const k = Math.min(179.999, Math.max(0, Math.atan2(v.x, v.y) * 180 / Math.PI + 90)), i0 = Math.floor(k), f = k - i0
   const n = at[i0].n.clone().lerp(at[i0 + 1].n, f).normalize(), q = at[i0].p.clone().lerp(at[i0 + 1].p, f)
   q.addScaledVector(n, .022 + (Math.hypot(v.x, v.y) - 1) * METERS).addScaledVector(side, v.z * METERS)
   pos.setXYZ(i, q.x, q.y, q.z)
  }
  geo.computeVertexNormals(); geo.computeBoundingBox(); geo.computeBoundingSphere()
 })
 g.add(band)
 for (const k of [1, -1]) {
  const h = b.hit(new THREE.Vector3(c.x + k * 3, c.y, 0), new THREE.Vector3(-k, 0, 0)), cup = part(scene, "headphones.cup")
  cup.position.copy(h.p).addScaledVector(h.n, .006); cup.scale.set(k * METERS, METERS, METERS)
  cup.quaternion.setFromUnitVectors(new THREE.Vector3(k, 0, 0), h.n)
  g.add(cup)
 }
 return g
}

const ACCESSORY_AT: Record<string, number> = { bow: .55, sprout: 0, flower: -.5 } // where on the head, as an angle from the top
function accessory(id: string, b: Built): { node: THREE.Group; onFace: boolean } | null {
 const g = new THREE.Group(), s = b.def
 if (id === "glasses") {
  const rim = soft("#3d4250", { roughness: .3 })
  for (const e of b.eyes) { const t = put(g, new THREE.TorusGeometry(.075, .009, 10, 36), rim, e.p.x, e.p.y, e.p.z + .02); t.lookAt(t.position.clone().add(e.n)) }
  put(g, tube([[b.eyes[0].p.x + .072, b.eyes[0].p.y + .012, b.eyes[0].p.z + .024], [0 + (b.eyes[0].p.x + b.eyes[1].p.x) / 2, b.eyes[0].p.y + .028, Math.max(b.eyes[0].p.z, b.mouth.p.z) + .03], [b.eyes[1].p.x - .072, b.eyes[1].p.y + .012, b.eyes[1].p.z + .024]], .008), rim)
  return { node: g, onFace: true }
 }
 if (!(id in ACCESSORY_AT)) return null
 const a = ACCESSORY_AT[id], c = new THREE.Vector3(s.lean * .6, s.h * .6, 0), d = new THREE.Vector3(Math.sin(a), Math.cos(a), .12).normalize()
 const h = b.hit(c.clone().addScaledVector(d, 3), d.clone().negate())
 g.position.copy(h.p); g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), h.n)
 trim(id, g)
 return { node: g, onFace: false }
}
/// A bow, a sprout or a flower, pointing up from the origin, for a blob 1 tall.
function trim(id: string, g: THREE.Group) {
 if (id === "bow") {
  const red = soft("#ef6f7d")
  for (const k of [-1, 1]) { const m = blob(g, red, .055, .034, .022, k * .05, .02, 0); m.rotation.z = k * -.35 }
  blob(g, red, .024, .024, .022, 0, .018, .004)
 } else if (id === "sprout") {
  const leaf = soft("#6cc070")
  put(g, tube([[0, -.01, 0], [0, .04, 0], [.008, .075, 0]], .009), leaf)
  for (const k of [-1, 1]) { const m = blob(g, leaf, .048, .018, .028, k * .045, .085 + (k > 0 ? .008 : 0), 0); m.rotation.z = k * .45 }
 } else {
  const petal = soft("#fffaf2")
  for (let i = 0; i < 5; i++) { const q = i / 5 * Math.PI * 2; blob(g, petal, .03, .012, .03, Math.cos(q) * .036, .018, Math.sin(q) * .036) }
  blob(g, soft("#f6c445"), .02, .014, .02, 0, .028, 0)
 }
}

// A look v2's top feature and accessory (rig.ts wears them on the head): each pointing up from the origin, for a blob 1
// tall, in the look's colors, and the way from the middle of the head to where it sits. Small and clear of the eyes, so
// they read at 18px.
const UP = new THREE.Vector3(0, 1, 0), ASIDE = (a: number) => new THREE.Vector3(Math.sin(a), Math.cos(a), .12)
Rigged.decor = (look: Look) => {
 const out: [THREE.Object3D, THREE.Vector3][] = [], main = soft(look.color)
 const deep = soft(`#${new THREE.Color(look.color).multiplyScalar(.8).getHexString()}`), second = hasAccent(look) ? soft(look.second!) : deep // no accent: a deeper body color
 const g = new THREE.Group()
 if (look.top === "antennae") for (const k of [-1, 1]) { put(g, tube([[k * .03, -.01, 0], [k * .045, .08, 0], [k * .085, .15, 0]], .011), main); blob(g, second, .032, .032, .032, k * .088, .165, 0) }
 else if (look.top === "tuft") for (const [x, h, r] of [[-.035, .07, .35], [0, .095, 0], [.035, .065, -.4]]) { const m = blob(g, deep, .024, h, .024, x, h * .65, 0); m.rotation.z = r }
 else if (look.top === "cap") { const dome = put(g, new THREE.SphereGeometry(.21, 28, 12, 0, TAU, 0, Math.PI / 2), second, 0, -.075, 0); dome.scale.set(1, .6, 1); blob(g, second, .036, .036, .036, 0, .05, 0) }
 else if (look.top === "sprout") trim("sprout", g)
 if (g.children.length) out.push([g, UP])
 if (look.accessory && look.accessory in ACCESSORY_AT) { const a = new THREE.Group(); trim(look.accessory, a); out.push([a, ASIDE(ACCESSORY_AT[look.accessory])]) }
 return out
}
// A kept prop (Keep prop, on a look from before v2 that held one), as the classic blob held it. Worn props stay classic.
Rigged.held = (id: string) => { const m = HOLD[id] && HOLD[id] !== "worn" ? model("props") : null; return m ? held(m.scene, id) : null }

// ---------------------------------------------------------------- motion

// One moment of the body: hop height and squash (sy, volume kept), lean forward (rx), tilt (rz), turn (ry), each arm
// raised (u) and swung forward (f), a held prop lifted, the eyes' openness and squint, the mouth, gaze (and how much of
// it is held on the prop: glances and the pointer don't pull those eyes away) and overall size.
type Pose = { y: number; sy: number; rx: number; rz: number; ry: number; lu: number; lf: number; ru: number; rf: number; lift: number; tilt: number; dx: number; open: number; squint: number; talk: number; gx: number; gy: number; use: number; scale: number }
const REST: Pose = { y: 0, sy: 1, rx: 0, rz: 0, ry: 0, lu: 0, lf: 0, ru: 0, rf: 0, lift: 0, tilt: 0, dx: 0, open: 1, squint: 0, talk: 0, gx: 0, gy: 0, use: 0, scale: 1 }
const FIELDS = Object.keys(REST) as (keyof Pose)[]

/// A smooth curve through [time, value, time, value, ...] keys: a monotone cubic, so it eases into each peak and
/// never overshoots a key. Overshoot and settle are keyed in on purpose.
function K(t: number, k: number[]) {
 const n = k.length / 2
 if (t <= k[0]) return k[1]
 if (t >= k[2 * n - 2]) return k[2 * n - 1]
 let i = 0; while (t > k[2 * i + 2]) i++
 const slope = (a: number) => {
  if (a <= 0 || a >= n - 1) return 0
  const s0 = (k[2 * a + 1] - k[2 * a - 1]) / (k[2 * a] - k[2 * a - 2]), s1 = (k[2 * a + 3] - k[2 * a + 1]) / (k[2 * a + 2] - k[2 * a])
  return s0 * s1 <= 0 ? 0 : 2 / (1 / s0 + 1 / s1)
 }
 const t0 = k[2 * i], h = k[2 * i + 2] - t0, u = (t - t0) / h, u2 = u * u, u3 = u2 * u
 return (2 * u3 - 3 * u2 + 1) * k[2 * i + 1] + (u3 - 2 * u2 + u) * slope(i) * h + (-2 * u3 + 3 * u2) * k[2 * i + 3] + (u3 - u2) * slope(i + 1) * h
}
/// A hop starting at t0: crouch first, leave stretched, land squashed, rebound once and settle. Returns [height, squash].
function hop(t: number, t0: number, height: number, air = .34): [number, number] {
 const u = t - t0, k = Math.min(1.2, height / .1)
 const y = u > 0 && u < air ? height * 4 * (u / air) * (1 - u / air) : 0
 const sy = K(u, [-.2, 1, -.04, .87, .04, 1.13, air * .5, 1.01, air * .9, 1.07, air + .05, .84, air + .17, 1.04, air + .3, .99, air + .42, 1])
 return [y, 1 + (sy - 1) * k]
}
const TAU = Math.PI * 2, LOOP = 4 // every idle repeats in LOOP seconds
const blinkAt = (u: number, at: number, slow = 1) => K(u, [at, 1, at + .06 * slow, .06, at + .12 * slow, .06, at + .24 * slow, 1])

// A prop's way of being: how much bounce its gestures have.
const MOOD: Record<string, string> = { laptop: "practical", notebook: "composed", camera: "warm", mug: "calm", phone: "warm", magnifier: "precise", wrench: "practical", paintbrush: "energetic", briefcase: "bold", headphones: "calm" }
const ENERGY: Record<string, number> = { bold: 1.25, warm: 1, composed: .85, energetic: 1.3, calm: .65, practical: .85, precise: .85, neutral: 1 }

/// Where the arms rest with this prop.
function rest(p: Pose, prop: string) {
 const h = HOLD[prop]
 if (h === "both") { p.lu = p.ru = .05; p.lf = p.rf = .6 }
 else if (h === "hand") { p.lu = .06; p.lf = .2; p.ru = prop === "briefcase" ? .4 : .42; p.rf = prop === "briefcase" ? .3 : .7 }
 else { p.lu = p.ru = .04; p.lf = p.rf = .22 }
 return p
}

const USE = 8 // seconds: a prop's use repeats in USE, eyes on it for 6.4 of them
/// Idle with a prop: using it, eyes on it about 80% of the time, then a 1.6 s glance away (at you, when you're there) and
/// back. Headphones: in the music, eyes softly shut, nodding on the beat.
function using(p: Pose, prop: string, t: number) {
 const u = ((t % USE) + USE) % USE, away = K(u, [6.2, 0, 6.45, 1, 7.75, 1, 8, 0]), on = 1 - away, s = (hz: number, ph = 0) => Math.sin(TAU * hz * t + ph)
 const k = (keys: number[]) => K(u, keys) * on
 p.use = on
 if (prop === "headphones") {
  p.rx += .035 * Math.max(0, s(1.75)) * on; p.sy *= 1 + .012 * s(1.75) * on; p.rz += .03 * s(.875) * on; p.squint = .55 * on
  p.gx = -.3 * away; p.gy = -.1 * away
  return
 }
 const [gx, gy] = HELD[prop].look
 p.gx = gx * on - .3 * away; p.gy = gy * on - .12 * away
 if (HOLD[prop] === "both") p.rx += .06 * on // leans in to look down at it
 else { p.ry += .14 * on; p.rz -= .03 * on } // turns to it
 switch (prop) {
  case "laptop": { const type = k([.4, 0, .7, 1, 5.6, 1, 5.9, 0]); p.lf += .06 * type * s(3.2); p.rf += .06 * type * s(3.2, 2); p.rx += k([2.8, 0, 3, .05, 3.3, 0]); break } // types, a nod
  case "notebook": p.gx += .22 * Math.sin(TAU * u / 1.6) * k([.5, 0, .8, 1, 5.4, 1, 5.8, 0]); p.lift = .1 * k([1, 0, 1.5, 1, 4.8, 1, 5.4, 0]); break // reads, line by line
  case "camera": { const up = k([1.6, 0, 2.1, 1, 3.6, 1, 4, 0]); p.lift = .4 * up; p.squint = Math.max(p.squint, .6 * k([2.6, 0, 2.68, 1, 2.9, 0])); break } // frames a shot, clicks
  case "mug": { const up = k([2, 0, 2.6, 1, 3.6, 1, 4.2, 0]); p.lift = .5 * up; p.squint = .45 * k([2.6, 0, 2.8, 1, 3.4, 1, 3.6, 0]); p.gy -= .3 * up; break } // a sip
  case "phone": p.tilt += .05 * s(.5) * on; p.gx += .1 * Math.sin(TAU * u / 2) * on; break // scrolls
  case "magnifier": { const up = k([.6, 0, 1.05, 1, 3.5, 1, 4, 0]); p.ru += .12 * up; p.lift = up; p.rx = .06 * up; p.gy -= .2 * up; break } // brings it up to an eye, studies
  case "wrench": p.tilt += .22 * k([1, 0, 1.4, 1, 2.6, 1, 3, -1, 4.2, -1, 4.6, 0]); break // turns it over, looks it up and down
  case "paintbrush": p.tilt += .12 * s(2) * k([1.5, 0, 1.8, 1, 3.4, 1, 3.7, 0]); break // little strokes
  case "briefcase": p.tilt += .06 * s(.4) * on; break // it swings
 }
}

/// The loop for a state, at time t (seconds, any value: it repeats every LOOP).
function loop(state: string, t: number, prop: string): Pose {
 const p = rest({ ...REST }, prop), u = ((t % LOOP) + LOOP) % LOOP, hand = HOLD[prop] === "hand"
 const s = (n: number, ph = 0) => Math.sin(TAU * n * t / LOOP + ph)
 const [U, F] = hand ? ["lu", "lf"] as const : ["ru", "rf"] as const // a nub that's holding something doesn't think or wave
 const top = prop === "headphones" ? .62 : 9 // a raised nub stays under the headphones' cups
 p.sy = 1 + .016 * s(2); p.rz = .02 * s(1)
 p.open = blinkAt(u, 3.1)
 if (state === "idle" && HOLD[prop]) using(p, prop, t)
 else if (state === "idle" || state === "listening") p.gx = K(u, [.8, 0, 1, -.4, 1.7, -.4, 1.9, .35, 2.6, .35, 2.8, 0])
 else if (state === "thinking") { p.rz = .08 + .015 * s(1); p.gx = .45; p.gy = -.45; p[U] = .55; p[F] = .9; p.sy = 1 + .01 * s(2) }
 else if (state === "working") { p.gy = .45; p.rx = .05; p.lift = .06 + .04 * Math.abs(s(4)); p.lf += .12 * s(4); p.rf += .12 * s(4, Math.PI); p.sy = 1 + .015 * s(4) }
 else if (state === "needs") { const [y, sy] = hop(u % 2, .3, .05); p.y = y; p.sy *= sy; p[U] = Math.min(top, .9 + .12 * s(4)); p[F] = .2 }
 else if (state === "error") { p.rx = .1; p.sy = .95 + .01 * s(1); p.gy = .5; p.open = Math.min(p.open, .65); p.lu = 0; if (!hand) p.ru = 0; p.lift = -.1 } // a held prop stays held
 else if (state === "talking") { p.talk = Math.max(0, Math.sin(t * 11) * .6 + Math.sin(t * 7.3) * .4); p.rx = .02 * s(4); p.sy = 1 + .012 * s(4) }
 else if (state === "pointing") { p[U] = Math.min(top, .78); p[F] = .55; p.rz = .05; p.gx = hand ? -.4 : .4 }
 if (state === "listening") { p.rx += .06; p.open = Math.max(p.open, .02) }
 return p
}

export const DUR: Record<string, number> = { wave: 2.2, wake: 2.3, drop: 1.6, pitch: 1.9, hired: 1.3, pop: .8, happy: 1.15, admire: 1.3, done: 1.4 }
/// A gesture at time g since it began. Gestures start and end on the state's loop, blended.
function gesture(name: string, g: number, base: Pose, mood: string, prop: string): Pose {
 const p = { ...base }, e = ENERGY[mood] ?? 1, left = HOLD[prop] === "hand" // a nub that's holding something doesn't wave
 const [U, F, OF] = left ? ["lu", "lf", "rf"] as const : ["ru", "rf", "lf"] as const
 switch (name) {
  case "wave": { // crouch a touch, swing a nub up, three waves that fade, bring it down past rest and settle
   const up = K(g, [0, 0, .16, -.08, .42, 1, 1.62, 1, 1.9, -.06, 2.05, .02, 2.2, 0])
   const low = prop === "headphones" // under headphones, a lower wave in front of the cup
   const wv = K(g, [.42, 0, .55, 1, 1.45, 1, 1.62, 0]) * Math.sin((g - .42) * TAU * 2.4) * (low ? .18 : .3)
   const side = left ? -1 : 1
   p[U] = base[U] * (1 - Math.min(1, up)) + up * (low ? .5 : 1.05) + wv; p[F] = base[F] * (1 - Math.min(1, up)) + up * (low ? .45 : .15)
   p.sy *= K(g, [0, 1, .16, .95, .42, 1.04, .7, 1, 1.62, 1, 1.85, .98, 2.05, 1.01, 2.2, 1])
   p.rz += side * K(g, [0, 0, .16, -.03, .45, .07, 1.62, .07, 1.95, -.01, 2.2, 0]) + wv * .15
   p.squint = K(g, [.3, 0, .5, .45, 1.6, .45, 1.9, 0]); p.gx = 0; p.gy = 0
   if (!left) { p.dx = side * -.03 * Math.min(1, up); p.tilt += side * .1 * Math.min(1, up) } // the prop shifts to the other nub
   if (HOLD[prop] === "both") p[OF] += .1 * Math.min(1, up)
   break
  }
  case "wake": { // asleep, a breath in, blinks awake and looks at you
   const awake = K(g, [.7, 0, .95, 1])
   p.open = g < .78 ? .05 : g < 1.3 ? K(g, [.78, .05, .92, 1, 1.12, 1, 1.18, .06, 1.24, .06, 1.34, 1]) : base.open
   p.sy *= K(g, [0, .95, .5, .955, .85, 1.06, 1.1, .98, 1.3, 1.01, 1.5, 1])
   p.rx = K(g, [0, .08, .7, .08, .95, -.03, 1.3, 0])
   p.gy = K(g, [0, .55, .9, .55, 1.4, 0]); p.gx = K(g, [1.25, 0, 1.45, -.2, 1.7, -.2, 1.9, 0])
   p.lift *= awake; p.lu *= .4 + .6 * awake; if (!left) p.ru *= .4 + .6 * awake
   p.squint = K(g, [1.5, 0, 1.7, .4, 2.1, .4, 2.3, 0])
   const [y, sy] = hop(g, 1.6, .02); p.y += y; p.sy *= sy
   break
  }
  case "drop": { // falls in stretched, lands squashed, rebounds and settles
   const fall = .38
   p.y = g < fall ? 1.7 * (1 - (g / fall) ** 2) : K(g, [fall, 0, .5, 0, .6, .045, .72, 0])
   p.sy *= K(g, [0, 1.1, fall - .04, 1.2, fall + .04, .7, .5, .82, .6, 1.08, .72, .95, .86, 1.03, 1, .995, 1.15, 1])
   if (!left) p.ru = K(g, [0, .6, fall, .5, fall + .06, .05, .7, .2, .9, base.ru])
   p.lu = K(g, [0, .6, fall, .5, fall + .06, .05, .7, .2, .9, base.lu])
   p.open = K(g, [0, 1, fall, 1, fall + .04, .2, fall + .16, .2, fall + .3, 1]); p.squint = K(g, [fall, 0, fall + .1, .5, .9, .5, 1.2, 0])
   p.lift = base.lift + K(g, [0, .2, fall, .2, fall + .06, -.12, .66, .05, .86, 0])
   break
  }
  case "pitch": { // "pick me": lean back, lean in with a tiny hop and hold the prop up to you, then settle
   const k = Math.min(1.3, e), hold = K(g, [.16, 0, .45, 1, 1.35, 1, 1.75, 0])
   p.rx = K(g, [0, base.rx, .16, -.05 * k, .45, .15 * k, 1.35, .13 * k, 1.6, -.02, 1.9, base.rx])
   const [y, sy] = hop(g, .32, .05 * k), [y2, sy2] = mood === "energetic" ? hop(g, .9, .04) : [0, 1]
   p.y += y + y2; p.sy *= sy * sy2
   p.lift = base.lift * (1 - hold) + hold; p.tilt += hold * .08 * Math.sin(g * 9) * (mood === "calm" ? .4 : 1)
   if (HOLD[prop] === "hand") { p.ru = base.ru + hold * .4; p.rf = base.rf + hold * .25 }
   else if (HOLD[prop] !== "both") { p.ru = base.ru + hold * .55; p.lu = base.lu + hold * .55; p.lf = p.rf = base.lf + hold * .35 }
   p.squint = hold * .4; p.gx = 0; p.gy = 0; p.ry = hold * (mood === "warm" ? .1 : 0); p.rz += hold * (mood === "warm" ? .06 : mood === "bold" ? -.03 : 0)
   break
  }
  case "hired": case "happy": { // a quick happy bounce, nubs up
   const big = name === "hired" ? 1 : .7, [y, sy] = hop(g, .2, .13 * big, .36), [y2, sy2] = hop(g, .75, .035 * big, .2)
   p.y += y + y2; p.sy *= sy * sy2
   const arms = K(g, [.1, 0, .3, 1, .62, .8, .9, 0])
   p.lu = base.lu + arms * .55; p.ru = base.ru + arms * (HOLD[prop] === "hand" ? .3 : .55); p.lift = base.lift + arms * .5
   p.squint = K(g, [.1, 0, .3, .7, .9, .7, 1.15, 0]); p.gx = 0; p.gy = 0
   break
  }
  case "pop": { // pops in: from nothing to a little too big, then its size
   p.scale = K(g, [0, 0, .22, 1.16, .36, .93, .5, 1.03, .64, 1])
   p.sy *= K(g, [0, 1.2, .22, .9, .36, 1.06, .5, .98, .64, 1])
   p.open = K(g, [.3, 1, .36, .1, .44, .1, .56, 1])
   break
  }
  case "admire": { // a pleased little wiggle
   p.rz += Math.sin(g * TAU * 1.6) * .07 * K(g, [0, 0, .2, 1, 1, 1, 1.3, 0]); p.squint = K(g, [0, 0, .2, .55, 1, .55, 1.3, 0]); p.sy *= 1 + .03 * Math.sin(g * TAU * 3.2) * K(g, [0, 0, .2, 1, 1.1, 0])
   break
  }
  case "done": { // a satisfied nod, then the prop up
   p.rx = base.rx + K(g, [0, 0, .2, .12, .4, -.03, .6, .1, .8, 0]); p.squint = K(g, [0, 0, .25, .5, 1.1, .5, 1.4, 0])
   p.lift = base.lift + K(g, [.5, 0, .75, .6, 1.1, .6, 1.4, 0]); p.ru = base.ru + K(g, [.5, 0, .75, .3, 1.1, .3, 1.4, 0])
   break
  }
 }
 if (prop === "briefcase") { p.ru = base.ru; p.rf = base.rf; p.lift = base.lift; p.tilt = base.tilt } // it hangs at the side through all of them
 return p
}
const GESTURE: Record<string, string> = { yes: "hired", signature: "pitch", point: "pointing", "needs-you": "needs", sad: "error", thinking: "thinking", working: "working", talking: "talking" }
const ONCE = new Set(Object.keys(DUR))
function makeShadow() {
 const s = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false }))
 s.rotation.x = -Math.PI / 2; s.position.y = .002; s.renderOrder = -1
 return s
}

function mixPose(a: Pose, b: Pose, k: number): Pose {
 const out = { ...a }
 for (const f of FIELDS) out[f] = a[f] + (b[f] - a[f]) * k
 return out
}
const ease = (x: number) => x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x)

const rnd = (k: number) => (Math.random() * 2 - 1) * k
const clamp = (v: number, k: number) => Math.max(-k, Math.min(k, v))

export class Companion {
 group = new THREE.Group() // on the ground: holds the shadow
 root = new THREE.Group() // hops
 body = new THREE.Group() // squashes and leans, from the ground up
 face = new THREE.Group()
 eyes: THREE.Group[] = []
 smile: THREE.Mesh; mouth: THREE.Mesh
 arms: THREE.Group[] = []
 held = new THREE.Group()
 prop: THREE.Group | null = null; hand: THREE.Group | null = null; wear: THREE.Group | null = null
 shadow: THREE.Mesh
 skin = vinyl(1); nub = vinyl(0)
 look?: Look; key = ""; shape!: Built
 mood = "neutral"
 state: MascotState = "idle"; gestureAt = 0
 move = ""; moveStart = 0 // the gesture playing, and when it began
 from: Pose | null = null; fromAt = 0
 pose: Pose = { ...REST }
 live = true; phase = Math.random() * LOOP
 // follow-through: a spring the prop and accessories hang on, kicked by the body's movement
 spring = { a: 0, v: 0, y: 0, vy: 0, rx: 0, first: true }
 // the held prop's turn, trailing where its hold point turns (lagged)
 lag = { q: new THREE.Quaternion(), w: new THREE.Vector3(), first: true }
 at = new THREE.Vector3() // a prop held in both nubs: moved so its back clears the belly and its top stays under the mouth
 out = 0 // a prop held in the right nub: how much further out that nub swings so the prop clears the body (outFor)
 // the little things nobody keys: blinks and glances, and following the pointer
 blinkNext = 1 + Math.random() * 3; blinkStart = -9; glanceNext = 1; glance = [0, 0]; gaze = [0, 0]; turn = [0, 0]

 constructor() {
  this.group.add(this.root); this.root.add(this.body)
  this.shadow = makeShadow()
  this.group.add(this.shadow)
  const ink = INK()
  for (let i = 0; i < 2; i++) {
   const e = new THREE.Group(), bead = blob(e, ink, .048, .058, .026)
   bead.position.z = -.008
   blob(e, SHINE, .015, .019, .006, -.019, .024, .02)
   blob(e, SHINE, .007, .007, .004, .016, -.022, .019)
   this.eyes.push(e); this.face.add(e)
  }
  this.smile = new THREE.Mesh(tube([[-.036, .012, 0], [-.018, -.006, .003], [0, -.012, .004], [.018, -.006, .003], [.036, .012, 0]], .0085), ink)
  this.mouth = new THREE.Mesh(ball(1), soft("#3a2430", { roughness: .4 }))
  this.face.add(this.smile, this.mouth)
  for (let i = 0; i < 2; i++) {
   const arm = new THREE.Group(), m = blob(arm, this.nub.m, .09, .14, .095, 0, -.095, 0)
   m.rotation.z = (i ? 1 : -1) * .1
   this.arms.push(arm); this.body.add(arm)
  }
  this.body.add(this.face, this.held)
 }

 setLook(look: Look) {
  const key = lookKey(look)
  if (key === this.key) return
  this.look = look; this.key = key
  this.shape = shape(look.shape)
  const b = this.shape, s = b.def
  this.body.remove(this.body.children.find(o => o.name === "skin") ?? new THREE.Object3D())
  const skin = new THREE.Mesh(b.geo, this.skin.m); skin.name = "skin"; skin.frustumCulled = false; this.body.add(skin)
  const color = new THREE.Color(look.color)
  for (const m of [this.skin, this.nub]) {
   m.m.color.copy(color); m.m.sheenColor.copy(color).lerp(new THREE.Color("#ffffff"), .5)
   m.u.uRim.value.copy(color).lerp(new THREE.Color("#ffffff"), .7).multiplyScalar(.35)
  }
  // the face sits on the surface, a little sunk in
  b.eyes.forEach((h, i) => { this.eyes[i].position.copy(h.p).addScaledVector(h.n, .006); this.eyes[i].quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), h.n) })
  for (const m of [this.smile, this.mouth]) { m.position.copy(b.mouth.p).addScaledVector(b.mouth.n, .006); m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), b.mouth.n) }
  b.shoulders.forEach((h, i) => this.arms[i].position.copy(h.p).addScaledVector(h.n, -.035))
  this.held.position.copy(b.belly.p).add(new THREE.Vector3(0, 0, .09))
  this.shadow.scale.set(s.w * 2.7, s.w * 2.7 * s.d * 1.1, 1)
  for (const n of [this.prop, this.wear]) n?.removeFromParent()
  this.prop = prop(look.prop, b, !!look.accessory && look.accessory !== "glasses"); this.hand = null; this.wear = null; this.lag.first = true; this.at.set(0, 0, 0)
  if (this.prop) {
   const h = HOLD[look.prop], box = new THREE.Box3().setFromObject(this.prop, true)
   if (h === "both") { this.held.add(this.prop); this.at.set(0, Math.min(0, b.mouth.p.y - .06 - b.belly.p.y - box.max.y), Math.max(0, .03 - .09 - box.min.z)) }
   else if (h === "worn") this.body.add(this.prop)
   else { const hand = new THREE.Group(); hand.add(this.prop); this.body.add(hand); this.hand = hand }
  }
  this.out = this.hand ? outFor(look) : 0
  const acc = accessory(look.accessory, b)
  if (acc) { this.wear = acc.node; (acc.onFace ? this.face : this.body).add(acc.node) }
  this.mood = MOOD[look.prop] ?? "neutral"
 }

 setState(state: MascotState, name: string, gestureAt: number, t: number) {
  if (gestureAt !== this.gestureAt && name) {
   this.gestureAt = gestureAt
   const g = GESTURE[name] ?? name
   if (ONCE.has(g)) this.begin(g, t)
   else if (g !== this.state) this.blend(t)
  }
  if (state !== this.state) { if (state === "done" && !this.move) this.begin("done", t); else this.blend(t); this.state = state }
 }
 begin(name: string, t: number) { this.blend(t); this.move = name; this.moveStart = t }
 blend(t: number) { if (this.live) { this.from = { ...this.pose }; this.fromAt = t } }

 /// The pose at time t (the stage's clock, in seconds).
 target(t: number): Pose {
  const prop = this.look?.prop ?? "", st = this.state === "done" ? "idle" : this.state
  const base = loop(st, t + (this.live ? this.phase : 0), prop)
  if (this.move) {
   const g = t - this.moveStart
   if (g < DUR[this.move]) return gesture(this.move, g, base, this.mood, prop)
   this.move = ""; this.blend(t)
  }
  return base
 }

 /// Moves time on to t and poses everything. dt drives the follow-through spring.
 update(dt: number, t: number, follow: { x: number; y: number } | null) {
  let p = this.target(t)
  if (this.from && this.live) { const k = ease((t - this.fromAt) / .28); p = mixPose(this.from, p, k); if (k >= 1) this.from = null }
  if (this.live && !clock.still) {
   // blinks 2.5 to 6 seconds apart, now and then two in a row; glances that rest a while; the pointer, when followed
   if (t > this.blinkNext) { this.blinkStart = t; this.blinkNext = t + (Math.random() < .14 ? .3 : 2.5 + Math.random() * 3.5) }
   p.open = Math.min(p.open, blinkAt(t - this.blinkStart, 0))
   if (t > this.glanceNext) { this.glance = Math.random() < .4 ? [0, 0] : [clamp(this.glance[0] + rnd(.5), .6), clamp(this.glance[1] + rnd(.2), .3)]; this.glanceNext = t + .8 + Math.random() * 2.4 }
   const want = follow ?? { x: this.glance[0], y: this.glance[1] }, k = 1 - Math.exp(-dt * (follow ? 10 : 6))
   this.gaze[0] += (want.x - this.gaze[0]) * k; this.gaze[1] += (want.y - this.gaze[1]) * k
   const turn = follow ?? { x: 0, y: 0 }
   this.turn[0] += (turn.x - this.turn[0]) * k; this.turn[1] += (turn.y - this.turn[1]) * k
   const free = 1 - p.use
   p.gx += this.gaze[0] * (1 - Math.abs(p.gx)) * free; p.gy += this.gaze[1] * .6 * free; p.ry += this.turn[0] * .3 * free; p.rx += this.turn[1] * .08 * free
  }
  this.pose = p
  this.follow(p, dt)
  this.apply(p, dt)
 }

 /// The spring: kicked by the hold point's vertical acceleration and by leaning, a stiff soft bounce that settles.
 follow(p: Pose, dt: number) {
  const s = this.spring, y = (p.y + (p.sy - 1) * .5) * p.scale // as big as it is: popping in from nothing doesn't kick it
  if (s.first || dt <= 0) { s.first = false; s.y = y; s.vy = 0; s.rx = p.rx; return }
  for (let n = Math.max(1, Math.ceil(dt * 120)), h = dt / n, i = 0; i < n; i++) {
   const vy = (y - s.y) / dt, ay = clamp((vy - s.vy) / dt, 60), lean = clamp((p.rx - s.rx) / dt, 4)
   const force = -190 * s.a - 13 * s.v - ay * .055 - lean * 1.1
   s.v += force * h; s.a = clamp(s.a + s.v * h, .45)
   if (i === n - 1) { s.vy = vy; s.y = y; s.rx = p.rx }
  }
 }
 /// Settles the spring at rest: pictures and seeking start from here.
 still() { this.spring = { a: 0, v: 0, y: 0, vy: 0, rx: 0, first: true }; this.lag.first = true }

 apply(p: Pose, dt = 0) {
  const b = this.shape, s = b.def, sx = 1 / Math.sqrt(Math.max(.3, p.sy))
  this.root.position.set(0, p.y, 0); this.root.scale.setScalar(Math.max(.001, p.scale))
  this.body.scale.set(sx, p.sy, sx); this.body.rotation.set(p.rx, p.ry, p.rz)
  // the face slides over the surface to look; blinks squash the eyes shut
  this.face.rotation.set(clamp(p.gy, 1) * .09, clamp(p.gx, 1) * .17, 0)
  const open = Math.max(.07, Math.min(1.15, p.open)) * (1 - .4 * p.squint)
  for (const e of this.eyes) { e.scale.set(1 + .06 * p.squint, open, 1); e.position.y = b.eyes[0].p.y + .006 * b.eyes[0].n.y + .008 * p.squint }
  const talk = Math.max(0, Math.min(1, p.talk))
  this.smile.visible = talk < .15; this.mouth.visible = !this.smile.visible
  this.mouth.scale.set(.024 + .006 * talk, .008 + .02 * talk, .006)
  this.smile.scale.setScalar(1 + .15 * p.squint)
  // arms: up swings a nub out and over, f swings it forward
  this.arms.forEach((a, i) => {
   const side = i ? 1 : -1, up = i ? p.ru + this.out : p.lu, fwd = i ? p.rf : p.lf
   a.children[0].scale.y = .14 * (1 + .28 * Math.min(1, Math.max(0, up - .45) * 2)) // a raised nub reaches
   a.rotation.set(-fwd, -side * Math.max(0, fwd) * 1.1, side * (.1 + up * 2.5), "YXZ") // swung forward, a nub comes in toward the middle
  })
  const sp = this.spring.a
  if (this.prop && HOLD[this.look!.prop] === "both") {
   this.held.position.set(b.belly.p.x + p.dx, b.belly.p.y + p.lift * .16, b.belly.p.z + .09 + p.lift * .06).add(this.at)
   this.held.rotation.set(-.05 - p.lift * .22 + sp, 0, p.tilt)
   this.lagged(this.held, dt)
  }
  if (this.hand) { // in the nub's tip, upright, tipping a little with the nub and the spring
   const a = this.arms[1]; a.updateMatrix(); this.hand.position.set(.005, -.2, .02).applyMatrix4(a.matrix).add(new THREE.Vector3(-.07, .07, .14).multiplyScalar(p.lift)) // lifted: brought up and in, to the face
   this.hand.rotation.set(sp * .8 - .1, -.15, (p.ru - .3) * .25 + Math.max(0, p.ru - .55) * 1.1 + p.tilt * .6) // raised high, it tips out with the nub
   this.lagged(this.hand, dt)
  }
  if (this.wear && this.wear.parent === this.body) this.wear.rotation.z = sp * .6
  // the shadow shrinks and fades as the companion leaves the ground
  const lift = Math.max(0, p.y), k = Math.max(.45, 1 - lift * 1.6) * Math.max(.001, p.scale)
  this.shadow.scale.set(s.w * 2.7 * k * sx, s.w * 2.7 * s.d * 1.1 * k * sx, 1); (this.shadow.material as THREE.MeshBasicMaterial).opacity = Math.max(.3, 1 - lift * 2)
 }

 /// The held prop's turn trails its hold point's (body and all) on a soft spring, about 0.14 s behind with a little
 /// overshoot, pivoting where it's held.
 lagged(o: THREE.Object3D, dt: number) {
  const L = this.lag, want = this.body.quaternion.clone().multiply(o.quaternion)
  if (L.first || dt <= 0) { L.q.copy(want); L.w.set(0, 0, 0); L.first = false }
  else for (let n = Math.max(1, Math.ceil(dt * 120)), h = dt / n, i = 0; i < n; i++) {
   const d = want.clone().multiply(L.q.clone().invert()), sgn = d.w < 0 ? -1 : 1, sin = Math.hypot(d.x, d.y, d.z)
   const e = new THREE.Vector3(d.x, d.y, d.z).multiplyScalar(sin < 1e-7 ? 0 : sgn * 2 * Math.atan2(sin, Math.abs(d.w)) / sin)
   L.w.multiplyScalar(1 - 14 * h).addScaledVector(e, 100 * h)
   const r = L.w.length() * h
   if (r > 1e-9) L.q.premultiply(new THREE.Quaternion().setFromAxisAngle(L.w.clone().normalize(), r))
  }
  o.quaternion.copy(this.body.quaternion.clone().invert().multiply(L.q))
 }

 /// Soft occlusion from the nubs and the prop onto the body, in view space.
 occluders(view: THREE.Matrix4) {
  const at = (o: THREE.Object3D, x: number, y: number, z: number) => new THREE.Vector3(x, y, z).applyMatrix4(o.matrixWorld).applyMatrix4(view)
  const occ = this.skin.u.uOcc.value, r = .085 * this.root.scale.x
  this.arms.forEach((a, i) => { const c = at(a, 0, -.09, 0); occ[i].set(c.x, c.y, c.z, r) })
  const p = this.prop && HOLD[this.look!.prop] === "both" ? at(this.held, 0, .04, -.02) : this.hand ? at(this.hand, 0, .05, 0) : null
  if (p) occ[2].set(p.x, p.y, p.z, .1 * this.root.scale.x); else occ[2].set(0, 0, 0, 0)
  const body = at(this.body, 0, this.shape.def.h * .5, 0)
  this.nub.u.uOcc.value[0].set(body.x, body.y, body.z, this.shape.def.w * .95 * this.root.scale.x)
 }

 dispose() {
  this.skin.m.dispose(); this.nub.m.dispose(); this.shadow.geometry.dispose(); (this.shadow.material as THREE.Material).dispose()
  this.smile.geometry.dispose(); this.mouth.geometry.dispose()
 }
}

/// Whether a point (in the body's own space) is inside the blob: its shape's own surface, the knob on a bump left out.
function inside(s: ShapeDef, q: THREE.Vector3) {
 const below = s.h * s.mid, Y = (q.y - below) / (q.y > below ? s.h - below : below)
 if (Math.abs(Y) >= 1) return false
 const e = Y > 0 ? s.top : s.bot, r = (1 - Math.abs(Y) ** e) ** (1 / e) * s.w * (1 - s.taper * Y)
 return Math.abs((q.x - s.lean * (q.y / s.h) ** 2) / r) ** s.n + Math.abs(q.z / (r * s.d)) ** s.n < 1
}
/// Every state (idle through its prop's use) and every gesture, frame by frame from rest, fps frames a second (the
/// gestures half as many again): fn sees each pose, and the sweep stops (true) when fn says so.
function sweep(c: Companion, fn: (what: string, t: number) => boolean | void, fps = 20) {
 c.live = false
 for (const s of STATES) { c.state = s; c.still(); for (let t = 0; t < (s === "idle" ? USE : LOOP); t += 1 / fps) { c.update(1 / fps, t, null); if (fn(s, t)) return true } }
 c.state = "idle"
 const g = 1 / (fps * 1.5)
 for (const [name, dur] of Object.entries(DUR)) { c.begin(name, 0); c.still(); for (let t = 0; t <= dur; t += g) { c.update(g, t, null); if (fn(name, t)) return true } }
 return false
}
const meshesOf = (o: THREE.Object3D) => { const out: THREE.Mesh[] = []; o.traverse(m => { if ((m as THREE.Mesh).isMesh) out.push(m as THREE.Mesh) }); return out }
/// What of c's prop goes into its body or (nubs) a nub as it stands, from about most of each mesh's points: null for
/// nothing. Touching a nub (inside .95 of it) isn't going in, and the holding nub's fist (its tip end, below -.2 of its
/// height) closes round a hand prop: nothing may go through the rest of it.
function into(c: Companion, meshes: THREE.Mesh[], most: number, nubs = true): string | null {
 c.group.updateMatrixWorld(true)
 if (Math.abs(c.body.matrixWorld.determinant()) < 1e-6) return null // popped in from nothing
 const v = new THREE.Vector3(), w = new THREE.Vector3(), inv = c.body.matrixWorld.clone().invert(), arms = nubs ? c.arms.map(a => a.children[0].matrixWorld.clone().invert()) : []
 for (const mesh of meshes) for (let i = 0, n = mesh.geometry.getAttribute("position").count, k = Math.max(1, Math.floor(n / most)); i < n; i += k) {
  mesh.getVertexPosition(i, v).applyMatrix4(mesh.matrixWorld)
  if (inside(c.shape.def, w.copy(v).applyMatrix4(inv))) return "the body"
  for (const [j, m] of arms.entries()) if (w.copy(v).applyMatrix4(m).length() < .95 && !(c.hand && j === 1 && w.y < -.2)) return "a nub"
 }
 return null
}
/// How much further out the right nub swings so its prop clears the body through every state and gesture: wide and
/// short shapes need it. Found once per look, in steps of .03 (up to .3).
const outs = new Map<string, number>()
function outFor(look: Look) {
 const key = lookKey(look), known = outs.get(key)
 if (known !== undefined) return known
 outs.set(key, 0) // the companion swept here asks too
 const c = new Companion(); c.setLook(look)
 const meshes = meshesOf(c.prop!)
 let k = 0
 while (k < .3 && sweep(c, () => into(c, meshes, 120, false) !== null, 10)) c.out = k = Math.round((k + .03) * 100) / 100
 if (k) k += .03 // a step more than the sweep found: it doesn't see every frame
 c.dispose(); outs.set(key, k)
 return k
}
/// Where a look's prop goes into its body or a nub, swept over every state and gesture as fit is (tests): one line per
/// state or gesture that clashes, empty when none do, null while the props load.
export function clashes(look: Look): string[] | null {
 if (!HOLD[look.prop] || rigFor(look)) return []
 if (!model("props")) return null
 const c = new Companion(), out = new Map<string, string>()
 c.setLook(look)
 const meshes = meshesOf(c.prop!)
 sweep(c, (what, t) => { if (out.has(what)) return; const hit = into(c, meshes, 400); if (hit) out.set(what, `${what} at ${t.toFixed(2)}s: the ${look.prop} goes into ${hit}`) })
 c.dispose()
 return [...out.values()]
}

// ---------------------------------------------------------------- the shared renderer

let renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.PerspectiveCamera
// The eight companions play their Blender models (rig.ts); any other look is a blob drawn here.
type Body = Companion | Rigged
const instances = new Map<string, Body>()
/// A body for a look, or null while its model loads.
function make(look: Look): Body | null {
 const id = rigFor(look), m = id ? model(id) : null
 if (id && !m || HOLD[look.prop] && !model("props")) return null
 const c = m ? new Rigged(m, makeShadow()) : new Companion()
 c.setLook(look)
 return c
}
const kind = (c: Body) => c instanceof Rigged ? c.id : ""
// Each companion is framed from its own bounds, swept over every state and gesture (antennae, tufts, props and all),
// centered with 12% clear on every side, so no hop, stretch or wave reaches the edge. The shadow stays out of the
// bounds, and so does the start of the drop, which falls in from above the frame on purpose.
const fits = new Map<string, { x: number; y: number; span: number }>()
function fit(look: Look) {
 const key = lookKey(look), known = fits.get(key)
 if (known) return known
 const id = rigFor(look), m = id && model(id)
 if (m) return frameOf(key, isV2(look) ? worn(m, look) : bounds(m))
 const c = new Companion(), box = new THREE.Box3()
 c.setLook(look)
 sweep(c, (what, t) => { if (what !== "drop" || t > .38) box.expandByObject(c.root) })
 c.dispose()
 return frameOf(key, box)
}
/// A v2 look's bounds: its foundation's, grown by as much as its top feature and accessory stand out from the body at rest.
function worn(m: NonNullable<ReturnType<typeof model>>, look: Look) {
 const box = bounds(m).clone()
 if (look.top === "none" && !look.accessory && !look.prop) return box
 const r = new Rigged(m)
 r.setLook(look); r.live = false; r.update(0, .3, null); r.root.updateMatrixWorld(true)
 const body = r.body(), b = body ? new THREE.Box3().setFromObject(body) : null, parts = new THREE.Box3()
 for (const p of r.worn) parts.expandByObject(p)
 if (b && !parts.isEmpty()) { box.max.y += Math.max(0, parts.max.y - b.max.y); box.min.x -= Math.max(0, b.min.x - parts.min.x); box.max.x += Math.max(0, parts.max.x - b.max.x) }
 r.dispose()
 return box
}
function frameOf(key: string, box: THREE.Box3) {
 const size = box.getSize(new THREE.Vector3()), mid = box.getCenter(new THREE.Vector3())
 // The camera is close, so the front of a deep body draws bigger than its bounds: grow the frame by that, taken halfway
 // to the front (the widest part of a blob is its middle, not the tip of its belly).
 const span = Math.max(size.x, size.y) / .76, d = span / 2 / Math.tan(THREE.MathUtils.degToRad(10))
 const f = { x: mid.x, y: mid.y, span: span * d / (d - Math.max(0, box.max.z) / 2) }
 fits.set(key, f)
 return f
}

export async function load() { /* nothing to fetch: every blob is built here */ }
function setup() {
 renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, premultipliedAlpha: true, powerPreference: "low-power" })
 renderer.setPixelRatio(1); renderer.setSize(512, 512, false)
 renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = .92
 scene = new THREE.Scene()
 const pmrem = new THREE.PMREMGenerator(renderer)
 scene.environment = pmrem.fromScene(new RoomEnvironment(), .04).texture; pmrem.dispose()
 camera = new THREE.PerspectiveCamera(20, 1, .1, 30)
 // A soft key from the upper left, high and broad, a sky fill, and a faint rim: the Cycles renders' studio
 scene.add(new THREE.HemisphereLight("#fffaf2", "#5e5550", .5))
 const key = new THREE.DirectionalLight("#fff4e8", 1.7); key.position.set(-2.2, 3.2, 2.2); scene.add(key)
 const fill = new THREE.DirectionalLight("#eef2ff", .1); fill.position.set(2.4, .4, 1.6); scene.add(fill)
 const rim = new THREE.DirectionalLight("#ffffff", .45); rim.position.set(1.2, 1.6, -2.6); scene.add(rim)
}

/// Frames the camera on a companion: the whole of it (fit), or the top half for the look editor's extras.
function aim(frame: Frame, c: Body) {
 const f = frame === "full" ? fit(c.look!) : { x: 0, y: Math.max(.7, (c instanceof Rigged ? c.height : c.shape.def.h) * .62), span: 1.1 }
 const d = f.span / 2 / Math.tan(THREE.MathUtils.degToRad(10)), az = .1
 camera.position.set(f.x + Math.sin(az) * d, f.y + d * .06, Math.cos(az) * d); camera.lookAt(f.x, f.y, 0)
}

/// Draws one companion into the top-left w x w of the shared canvas.
function draw(c: Body, w: number, frame: Frame) {
 if (renderer.domElement.width < w) renderer.setSize(Math.min(768, w), Math.min(768, w), false)
 const H = renderer.domElement.height
 for (const o of instances.values()) o.group.visible = o === c
 if (!c.group.parent) scene.add(c.group)
 c.group.visible = true
 aim(frame, c)
 camera.updateMatrixWorld(); c.group.updateMatrixWorld(true)
 c.occluders(camera.matrixWorldInverse)
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

/// Poses a companion at a frozen time t (tests): the state's loop or the gesture at t seconds in, the spring run up to it.
function seek(c: Body, t: number) {
 c.live = false; c.still()
 const start = c.move ? c.moveStart : 0
 for (let x = Math.max(0, t - 2); x < t; x += 1 / 60) c.update(1 / 60, start + x, null)
 c.update(1 / 60, start + t, null)
}

let last = 0, raf = 0
function tick(now: number) {
 raf = requestAnimationFrame(tick)
 if (document.hidden) return
 const visible = [...slots.values()].filter(s => s.visible)
 for (const [id, c] of instances) if (!slots.has(id)) { scene.remove(c.group); c.dispose(); instances.delete(id) }
 if (!visible.length) return
 const busy = visible.some(s => s.canvas.width >= 320 && (s.state !== "idle" || !!instances.get(s.id)?.move))
 if (now - last < 1000 / (busy ? 60 : 30) - 2) return
 const dt = Math.min(.05, last ? (now - last) / 1000 : 1 / 30), frozen = clock.frozen
 last = now
 for (const s of visible) {
  let c = instances.get(s.id)
  if (c && kind(c) !== (rigFor(s.look) ?? "")) { scene.remove(c.group); c.dispose(); instances.delete(s.id); c = undefined }
  if (!c) { const made = make(s.look); if (!made) continue; instances.set(s.id, c = made) }
  c.setLook(s.look)
  if (frozen !== null) { c.setState(s.state, s.gesture, s.gestureAt, 0); if (c.move) c.moveStart = 0; seek(c, frozen) }
  else { c.live = true; c.setState(s.state, s.gesture, s.gestureAt, now / 1000); c.update(dt, now / 1000, pointerFor(s)) }
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
 raf = requestAnimationFrame(tick)
}
export const stop = () => cancelAnimationFrame(raf)

// Where each state's picture is taken, in seconds into its loop.
const STILL_AT: Partial<Record<MascotState, number>> = { idle: .3, working: .3, needs: .55, done: .3, error: .5, thinking: .5, talking: .2, pointing: .3 }
/// A still picture of a look, for small places and for reduced motion.
export function picture(look: Look, state: MascotState, px: number, frame: Frame, flat = false, turn = 0) { // turn: radians about the up axis, for reviews
 if (frame === "icon" || frame === "portrait") return head(look, px, frame)
 start()
 const c = make(look)
 if (!c) return null // its model is loading (onRigReady)
 c.state = state; c.live = false
 c.update(0, STILL_AT[state] ?? .3, null)
 c.group.rotation.y += turn
 const made = flat ? flatten(c, TONES, isV2(look)) : []
 instances.set("__picture", c)
 draw(c, px, frame)
 let out = document.createElement("canvas"); out.width = out.height = px
 out.getContext("2d")!.drawImage(renderer.domElement, 0, 0, px, px, 0, 0, px, px)
 if (flat) out = outline(out, look.color)
 scene.remove(c.group); instances.delete("__picture"); c.dispose(); made.forEach(m => m.dispose())
 return out.toDataURL("image/webp", .9)
}

/// A look's head for the small tiers (Mascot.tsx), as rig/anim.py "heads" makes the Blender ones: the rest pose drawn flat
/// with no prop, the head (from the top down to the shoulders, read off the picture) framed so what's drawn takes 87% of
/// the box across its longer side (85 to 90%, as tools/heads/pack.py fills the shipped ones), circled at 88% with a line
/// in the outline's color where the body goes on past the circle. The icon is one tone, its eyes a quarter bigger and its
/// outline twice as thick.
function head(look: Look, px: number, tier: "icon" | "portrait") {
 start()
 const c = make(look)
 if (!c) return null // its model is loading (onRigReady)
 c.state = "idle"; c.live = false
 if (tier === "icon" && "rest" in c && c.rest) c.rest = { ...c.rest, lid: Math.min(c.rest.lid, .15) } // at 18px half-shut lids hide the pupils
 c.update(0, 0, null)
 if (c instanceof Companion && c.prop && HOLD[look.prop] !== "worn") c.prop.visible = false // held props stay out; worn ones are on the head
 const icon = tier === "icon", made = flatten(c, icon ? ONE_TONE : TONES, isV2(look))
 if (icon) for (const e of c instanceof Companion ? c.eyes : ["eye.L", "eye.R", "brow.L", "brow.R"].map(n => node(c.root, n))) e?.scale.multiplyScalar(1.25)
 instances.set("__picture", c)
 const S = 512
 draw(c, S, "full")
 const raw = document.createElement("canvas"); raw.width = raw.height = S
 const g = raw.getContext("2d", { willReadFrequently: true })!
 g.drawImage(renderer.domElement, 0, 0, S, S, 0, 0, S, S)
 // the eyes on screen: the head goes from its top down past them as far again and a quarter (about the chin), as the
 // Blender heads are framed; below that is the body
 const eyes = (c instanceof Companion ? c.eyes : ["eye.L", "eye.R"].map(n => node(c.root, n))).filter(e => !!e) as THREE.Object3D[]
 const ey = eyes.reduce((s, e) => s + (1 - (e.getWorldPosition(new THREE.Vector3()).project(camera).y + 1) / 2) * S, 0) / Math.max(1, eyes.length)
 scene.remove(c.group); instances.delete("__picture"); c.dispose(); made.forEach(m => m.dispose())
 const a = g.getImageData(0, 0, S, S).data
 let top = -1, left = S, right = -1
 for (let y = 0; y < S && top < 0; y++) for (let x = 0; x < S; x++) if (a[(y * S + x) * 4 + 3] > 8) { top = y; break }
 const low = Math.round(ey + 1.25 * (ey - top))
 if (!eyes.length || top < 0 || low <= top) return null
 for (let y = top; y <= Math.min(low, S - 1); y++) for (let x = 0; x < S; x++) if (a[(y * S + x) * 4 + 3] > 8) { left = Math.min(left, x); right = Math.max(right, x) }
 let side = Math.max(right - left + 1, low - top) / .87
 const cx = (left + right + 1) / 2, cy = (top + low) / 2
 const ink = `#${new THREE.Color(look.color).multiplyScalar(.1).getHexString()}`
 const lined = outline(raw, look.color, side * 2.6 / 96 * (icon ? 2 : 1))
 // Framed, then measured (the outline and the circle change what's drawn: a narrow head is cut by the circle at its
 // shoulders, so it grows slowly), and the frame closed in or opened out by halves until it takes 86 to 89%
 let lo = side * .3, hi = side * 1.3, box = frame(side), s = share(box)
 for (let i = 0; i < 12 && s && (s < .86 || s > .89); i++) {
  if (s < .86) hi = side; else lo = side
  side = (lo + hi) / 2; box = frame(side); s = share(box)
 }
 return box.toDataURL("image/webp", .9)

 // into the box, then circled, with the line along the cut
 function frame(side: number) {
 const box = document.createElement("canvas"); box.width = box.height = px
 const b = box.getContext("2d")!
 b.drawImage(lined, cx - side / 2, cy - side / 2, side, side, 0, 0, px, px)
 const R = px * .44, w = Math.max(1, px * 2.6 / 96 * (icon ? 2 : 1)), disc = (k: CanvasRenderingContext2D, r: number) => { k.beginPath(); k.arc(px / 2, px / 2, r, 0, TAU); k.fill() }
 const past = document.createElement("canvas"), rim = document.createElement("canvas"); past.width = past.height = rim.width = rim.height = px
 const p = past.getContext("2d")!, r = rim.getContext("2d")!
 p.drawImage(box, 0, 0); p.globalCompositeOperation = "destination-out"; disc(p, R) // the body past the circle
 r.lineWidth = w; r.strokeStyle = ink; r.beginPath(); r.arc(px / 2, px / 2, R - w / 2, 0, TAU); r.stroke()
 r.globalCompositeOperation = "destination-in"
 const near = document.createElement("canvas"); near.width = near.height = px
 const n = near.getContext("2d")!
 for (let i = 0; i < 16; i++) n.drawImage(past, Math.cos(i / 16 * TAU) * w * 1.5, Math.sin(i / 16 * TAU) * w * 1.5)
 r.drawImage(near, 0, 0); r.drawImage(box, 0, 0)
 b.globalCompositeOperation = "destination-in"; disc(b, R)
 b.globalCompositeOperation = "source-over"; b.drawImage(rim, 0, 0)
 return box
 }
}
/// A rig's node by its Blender name (three.js drops the dots: "eye.L" is "eyeL").
const node = (root: THREE.Object3D, name: string) => root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name))
/// What's drawn (alpha at half and up) across the longer side, as a share of the box.
function share(c: HTMLCanvasElement) {
 const a = c.getContext("2d", { willReadFrequently: true })!.getImageData(0, 0, c.width, c.height).data
 let l = c.width, t = c.height, r = -1, b = -1
 for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) if (a[(y * c.width + x) * 4 + 3] >= 128) { l = Math.min(l, x); r = Math.max(r, x); t = Math.min(t, y); b = Math.max(b, y) }
 return r < 0 ? 0 : Math.max(r - l + 1, b - t + 1) / c.width
}

// 2D, for chat sizes (Mascot.tsx): every part in its own color in two flat tones, the same face, a bold outline. The
// Blender companions ship theirs (rig/anim.py "flat"); any other look is drawn so from its model.
const toon = (shades: number[]) => { const t = new THREE.DataTexture(new Uint8Array(shades), shades.length, 1, THREE.RedFormat); t.minFilter = t.magFilter = THREE.NearestFilter; t.needsUpdate = true; return t }
const TONES = toon([200, 255]), ONE_TONE = toon([255]) // the head icon: one tone
function flatten(c: Body, tones = TONES, v2 = false) {
 const made: THREE.Material[] = []
 if (c.shadow) c.shadow.visible = false
 c.group.traverse(o => {
  const mesh = o as THREE.Mesh, m = mesh.material as THREE.MeshStandardMaterial
  if (!mesh.isMesh || !m?.isMeshStandardMaterial || m.blending !== THREE.NormalBlending) return // the eye shine stays
  if (v2 && (m as THREE.MeshPhysicalMaterial).transmission > 0) { mesh.visible = false; return } // the foundations' clear eye cap: flat, it would hide the pupil
  // toon takes no environment light: its own color, glowing about half, stands in for it so the body keeps its color
  const t = new THREE.MeshToonMaterial({ color: m.color, emissive: m.color, emissiveIntensity: .5, map: m.map, vertexColors: m.vertexColors, gradientMap: tones, side: m.side, transparent: m.transparent, opacity: m.opacity })
  const z = m.userData.zones as Zones | undefined
  if (z) { t.emissive.set(0); zoned(t, { ...z, uGlow: { value: .5 } }) } // a v2 body: its zones' colors glow, not one
  // A foundation paints its pupils and mouth in vertex colors: the glow takes them too, or it washes them out to grey.
  // Only for v2 looks, so no picture of an older look changes.
  if (v2 && m.vertexColors) {
   const before = t.onBeforeCompile.bind(t)
   t.onBeforeCompile = (s, r) => { before(s, r); s.fragmentShader = s.fragmentShader.replace("#include <emissivemap_fragment>", "#include <emissivemap_fragment>\ntotalEmissiveRadiance *= vColor.rgb;") }
   t.customProgramCacheKey = () => (z ? "zones" : "") + "-painted"
  }
  mesh.material = t; made.push(t)
 })
 return made
}
/// The picture with a dark line in the look's own color round its silhouette, about 2.5% of its width (or r px).
function outline(src: HTMLCanvasElement, color: string, r = Math.max(1, src.width * .025)) {
 const px = src.width, out = document.createElement("canvas"), sil = document.createElement("canvas")
 out.width = out.height = sil.width = sil.height = px
 const s = sil.getContext("2d")!, g = out.getContext("2d")!
 s.drawImage(src, 0, 0); s.globalCompositeOperation = "source-in"; s.fillStyle = `#${new THREE.Color(color).multiplyScalar(.1).getHexString()}`; s.fillRect(0, 0, px, px)
 for (let i = 0; i < 16; i++) g.drawImage(sil, Math.cos(i / 16 * TAU) * r, Math.sin(i / 16 * TAU) * r)
 g.drawImage(src, 0, 0)
 return out
}

/// A gesture (or a state's loop) as frames, for reels and review: PNG data URLs at fps for the given seconds.
export function frames(look: Look, move: string, seconds: number, fps = 30, px = 512, frame: Frame = "full"): string[] | null {
 start()
 const c = make(look), name = GESTURE[move] ?? move
 if (!c) return null // its model is loading
 c.live = false
 if (c instanceof Rigged ? c.has(move) : ONCE.has(name)) c.begin(c instanceof Rigged ? move : name, 0)
 else c.state = (name === "needs-you" ? "needs" : name) as MascotState
 instances.set("__reel", c)
 const out: string[] = [], canvas = document.createElement("canvas"); canvas.width = canvas.height = px
 const g = canvas.getContext("2d")!
 for (let i = 0; i < Math.round(seconds * fps); i++) {
  c.update(i ? 1 / fps : 0, i / fps, null)
  draw(c, px, frame)
  g.clearRect(0, 0, px, px); g.drawImage(renderer.domElement, 0, 0, px, px, 0, 0, px, px)
  out.push(canvas.toDataURL("image/png"))
 }
 scene.remove(c.group); instances.delete("__reel"); c.dispose()
 return out
}
