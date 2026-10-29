import * as THREE from "three"
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js"
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js"
import { mergeVertices } from "three/addons/utils/BufferGeometryUtils.js"
import { lookKey, type Look } from "./look"
import { clock, pointer, slots, type Frame, type MascotState, type Slot } from "./Mascot"

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

const box = (w: number, h: number, d: number, r: number) => new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2, h / 2, d / 2))
function put(g: THREE.Object3D, geo: THREE.BufferGeometry, mat: THREE.Material, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0) {
 const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.rotation.set(rx, ry, rz); g.add(m); return m
}
const tube = (pts: number[][], r: number) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p))), 24, r, 10)
const ball = (r: number) => new THREE.SphereGeometry(r, 20, 14)
function blob(g: THREE.Object3D, mat: THREE.Material, sx: number, sy: number, sz: number, x = 0, y = 0, z = 0) { const m = put(g, ball(1), mat, x, y, z); m.scale.set(sx, sy, sz); return m }

// How each prop is carried: in both nubs in front of the belly, in the right nub, or worn.
const HOLD: Record<string, "both" | "hand" | "worn"> = { chart: "both", badge: "both", clipboard: "both", laptop: "both", envelope: "both", megaphone: "hand", magnifier: "hand", pencil: "hand", headset: "worn" }
const props = new Map<string, THREE.Group>()
function prop(id: string, b: Built): THREE.Group | null {
 if (!HOLD[id]) return null
 const key = HOLD[id] === "worn" ? id + "|" + b.def.h + b.def.w : id
 let g = props.get(key)
 if (!g) props.set(key, g = makeProp(id, b))
 return g.clone()
}
function makeProp(id: string, b: Built) {
 const g = new THREE.Group()
 switch (id) {
  case "chart": { // a rising bar chart on a little tray, with an arrow going up
   put(g, box(.32, .036, .14, .018), soft("#fbf7ef"))
   ;[[.085, "#a6e3c8"], [.14, "#62c79f"], [.205, "#2fa57d"]].forEach(([h, c], i) => put(g, box(.07, h as number, .08, .026), soft(c as string), -.095 + i * .095, .018 + (h as number) / 2, .005))
   put(g, tube([[-.14, .11, .07], [-.06, .14, .07], [.02, .17, .07], [.09, .23, .07]], .012), soft("#1f8a66"))
   const tip = put(g, new THREE.ConeGeometry(.03, .06, 18), soft("#1f8a66"), .106, .255, .07); tip.rotation.z = -.62
   break
  }
  case "badge": { // a name badge on its lanyard
   put(g, tube([[-.035, .075, -.004], [-.075, .16, -.025], [0, .2, -.04], [.075, .16, -.025], [.035, .075, -.004]], .011), soft("#3f9fa3"))
   put(g, box(.055, .034, .022, .01), soft("#9aa3b2"), 0, .08, .004)
   put(g, box(.22, .16, .026, .03), soft("#3f9fa3"))
   put(g, box(.185, .125, .01, .02), soft("#fffaf2"), 0, -.004, .013)
   put(g, new THREE.CylinderGeometry(.027, .027, .008, 24), soft("#f6c3b0"), -.048, -.004, .018, Math.PI / 2)
   put(g, box(.065, .014, .005, .006), soft("#b9b3aa"), .033, .014, .018)
   put(g, box(.048, .014, .005, .006), soft("#d4cfc6"), .024, -.018, .018)
   break
  }
  case "clipboard": { // a checklist, two ticked
   put(g, box(.24, .3, .026, .03), soft("#7d8fb3"))
   put(g, box(.2, .24, .006, .012), soft("#fffdf8"), 0, -.012, .016)
   put(g, box(.095, .042, .03, .014), soft("#4b5262"), 0, .145, .02)
   for (let i = 0; i < 3; i++) {
    put(g, box(.026, .026, .006, .007), soft(i < 2 ? "#5cc49b" : "#d9d4cc"), -.058, .05 - i * .06, .02)
    put(g, box(.09, .013, .005, .006), soft("#cfc9c0"), .028, .05 - i * .06, .02)
   }
   break
  }
  case "laptop": { // open, turned so you see the code on its screen
   put(g, box(.28, .02, .18, .01), soft("#d6dce4"), 0, 0, -.06)
   const lid = new THREE.Group(); lid.position.set(0, .006, .03); lid.rotation.x = -.14; g.add(lid)
   put(lid, box(.28, .19, .016, .014), soft("#d6dce4"), 0, .095, 0)
   put(lid, box(.25, .158, .004, .01), soft("#2f3644", { roughness: .7, clearcoat: 0, envMapIntensity: .1 }), 0, .1, .009)
   ;[[.12, "#93d6bd", 0], [.08, "#f6d56a", .02], [.13, "#8cc3ee", .02], [.06, "#f2a5c4", .04], [.1, "#93d6bd", 0]].forEach(([w, c, x], i) =>
    put(lid, box(w as number, .012, .003, .005), soft(c as string, { roughness: .4, emissive: c as string, emissiveIntensity: .25 }), -.09 + (x as number) + (w as number) / 2, .155 - i * .026, .012))
   break
  }
  case "envelope": {
   put(g, box(.26, .17, .028, .022), soft("#fbf3e2"))
   for (const k of [-1, 1]) put(g, box(.155, .012, .005, .005), soft("#e3d3b5"), k * .064, .03, .016, 0, 0, k * .6)
   put(g, new THREE.CylinderGeometry(.024, .024, .008, 24), soft("#ef6f7d"), 0, -.006, .018, Math.PI / 2)
   break
  }
  case "megaphone": { // held up, pointing out and up
   const m = new THREE.Group(); g.add(m); m.position.set(0, .03, .06); m.rotation.set(.85, 0, -.5)
   const cone = new THREE.LatheGeometry([[.026, -.02], [.03, .02], [.062, .11], [.1, .2], [.106, .214], [.096, .216], [.06, .14], [.024, .03], [.02, -.02]].map(([r, y]) => new THREE.Vector2(r, y)), 40)
   put(m, cone, soft("#f06f62", { side: THREE.DoubleSide }))
   put(m, new THREE.TorusGeometry(.102, .013, 12, 40), soft("#fffaf2"), 0, .212, 0, Math.PI / 2)
   put(m, new THREE.CircleGeometry(.092, 32), soft("#c9564b"), 0, .17, 0, -Math.PI / 2)
   put(m, box(.036, .085, .04, .016), soft("#4b5262"), 0, .02, .05, .5)
   break
  }
  case "magnifier": { // the handle in the nub, the lens up beside the face
   const m = new THREE.Group(); g.add(m); m.rotation.z = .12
   put(m, new THREE.CapsuleGeometry(.022, .1, 6, 14), soft("#4b5262"), 0, .02, 0)
   put(m, new THREE.CylinderGeometry(.026, .026, .024, 20), soft("#e8b65a"), 0, .085, 0)
   put(m, new THREE.TorusGeometry(.078, .017, 14, 44), soft("#4b5262"), 0, .18, 0)
   put(m, new THREE.CylinderGeometry(.074, .074, .008, 40), new THREE.MeshPhysicalMaterial({ color: "#e4f3ff", roughness: .04, clearcoat: 1, transparent: true, opacity: .42, envMapIntensity: 1.6 }), 0, .18, 0, Math.PI / 2)
   const glint = put(m, tube([[-.045, .21, .006], [-.03, .232, .006], [-.008, .244, .006]], .006), SHINE); glint.renderOrder = 2
   break
  }
  case "pencil": {
   const m = new THREE.Group(); g.add(m); m.position.set(0, .03, .03); m.rotation.set(.3, 0, -.6)
   put(m, new THREE.CylinderGeometry(.024, .024, .19, 6), soft("#f6c445"), 0, .02, 0)
   put(m, new THREE.CylinderGeometry(.006, .024, .05, 6), soft("#f1d3a8"), 0, .14, 0)
   put(m, new THREE.ConeGeometry(.008, .016, 12), soft("#4a4f5c"), 0, .17, 0)
   put(m, new THREE.CylinderGeometry(.025, .025, .028, 16), soft("#c9ced6", { metalness: .2 }), 0, -.088, 0)
   put(m, new THREE.CapsuleGeometry(.023, .018, 6, 14), soft("#f39cb0"), 0, -.112, 0)
   break
  }
  case "headset": { // over the top of the head, cups on the sides, a mic toward the mouth
   const s = b.def, c = new THREE.Vector3(s.lean * .3, s.eye * s.h - .02, 0), dark = soft("#4b5262"), pts: number[][] = []
   for (let a = -1.5; a <= 1.501; a += .1) { const d = new THREE.Vector3(Math.sin(a), Math.cos(a), 0), h = b.hit(c.clone().addScaledVector(d, 3), d.clone().negate()); h.p.addScaledVector(h.n, .022); pts.push(h.p.toArray()) }
   put(g, tube(pts, .022), dark)
   for (const k of [-1, 1]) {
    const h = b.hit(new THREE.Vector3(k * 3, c.y, 0), new THREE.Vector3(-k, 0, 0))
    blob(g, dark, .045, .095, .09, h.p.x + k * .025, h.p.y, h.p.z)
    blob(g, soft("#f39079"), .022, .062, .058, h.p.x + k * .062, h.p.y, h.p.z)
    if (k === 1) {
     const m = b.mouth.p
     put(g, tube([[h.p.x + .04, h.p.y - .03, .03], [h.p.x - .01, m.y - .02, m.z * .7], [m.x + .08, m.y - .02, m.z + .03]], .009), dark)
     blob(g, soft("#f39079"), .024, .024, .024, m.x + .07, m.y - .02, m.z + .035)
    }
   }
   break
  }
 }
 g.traverse(o => { o.frustumCulled = false })
 g.children.forEach(o => o.position.y += LOWER[id] ?? 0)
 return g
}
const LOWER: Record<string, number> = { chart: -.06, laptop: -.075, badge: -.02 } // so a tall prop stays under the face

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
 return { node: g, onFace: false }
}

// ---------------------------------------------------------------- motion

// One moment of the body: hop height and squash (sy, volume kept), lean forward (rx), tilt (rz), turn (ry), each arm
// raised (u) and swung forward (f), a held prop lifted, the eyes' openness and squint, the mouth, gaze and overall size.
type Pose = { y: number; sy: number; rx: number; rz: number; ry: number; lu: number; lf: number; ru: number; rf: number; lift: number; tilt: number; dx: number; open: number; squint: number; talk: number; gx: number; gy: number; scale: number }
const REST: Pose = { y: 0, sy: 1, rx: 0, rz: 0, ry: 0, lu: 0, lf: 0, ru: 0, rf: 0, lift: 0, tilt: 0, dx: 0, open: 1, squint: 0, talk: 0, gx: 0, gy: 0, scale: 1 }
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

// Each role's way of being: from the prop it carries for its job.
const MOOD: Record<string, string> = { chart: "bold", badge: "warm", clipboard: "composed", megaphone: "energetic", headset: "calm", laptop: "practical", magnifier: "precise" }
const ENERGY: Record<string, number> = { bold: 1.25, warm: 1, composed: .85, energetic: 1.3, calm: .65, practical: .85, precise: .85, neutral: 1 }

/// Where the arms rest with this prop.
function rest(p: Pose, prop: string) {
 const h = HOLD[prop]
 if (h === "both") { p.lu = p.ru = .05; p.lf = p.rf = .6 }
 else if (h === "hand") { p.lu = .06; p.lf = .2; p.ru = prop === "magnifier" ? .42 : .5; p.rf = prop === "magnifier" ? .75 : .5 }
 else { p.lu = p.ru = .04; p.lf = p.rf = .22 }
 return p
}

/// The loop for a state, at time t (seconds, any value: it repeats every LOOP).
function loop(state: string, t: number, mood: string, prop: string): Pose {
 const p = rest({ ...REST }, prop), u = ((t % LOOP) + LOOP) % LOOP
 const s = (n: number, ph = 0) => Math.sin(TAU * n * t / LOOP + ph)
 p.sy = 1 + .016 * s(2); p.rz = .02 * s(1)
 p.open = blinkAt(u, 3.1)
 if (state === "idle" || state === "listening") switch (mood) {
  case "bold": { // chest out, a sure little bounce, the chart tipped your way
   const [y, sy] = hop(u, 2, .028)
   p.y = y; p.sy *= sy; p.rx = -.035; p.lift = .12 + .1 * Math.max(0, s(1, -1)); p.tilt = .04 * s(1)
   p.gx = K(u, [.6, 0, .8, -.25, 1.4, -.25, 1.6, 0]); p.gy = K(u, [.6, 0, .8, .35, 1.4, .35, 1.6, 0])
   break
  }
  case "warm": { // looks around, curious, head tilting toward what it sees
   p.gx = K(u, [.5, 0, .75, -.55, 1.5, -.55, 1.8, .5, 2.6, .5, 2.85, 0]); p.rz += .07 * p.gx; p.ry = .14 * p.gx; p.gy = -.1 * Math.abs(p.gx)
   p.lift = .05 + .04 * s(2)
   break
  }
  case "composed": { // upright and tidy: checks the clipboard, taps it twice, nods
   p.sy = 1 + .011 * s(2); p.rz = .012 * s(1)
   p.gy = K(u, [1.1, 0, 1.35, .5, 2.3, .5, 2.55, 0]); p.rx = K(u, [1.1, 0, 1.35, .05, 2.3, .05, 2.5, -.02, 2.75, .03, 3, 0])
   p.rf += K(u, [1.5, 0, 1.6, .22, 1.7, 0, 1.82, .22, 1.92, 0]); p.ru += K(u, [1.5, 0, 1.6, .1, 1.7, 0, 1.82, .1, 1.92, 0])
   p.lift = K(u, [1.1, 0, 1.35, .15, 2.3, .15, 2.55, 0])
   break
  }
  case "energetic": { // can't keep still: two bounces a loop
   const [y1, s1] = hop(u, .6, .06), [y2, s2] = hop(u, 2.6, .045)
   p.y = y1 + y2; p.sy *= s1 * s2; p.rz = .04 * s(1); p.ry = .06 * s(1, 1)
   p.ru += .1 * s(2); p.gx = .25 * s(1)
   break
  }
  case "calm": { // slow, deep breaths and an easy sway
   p.sy = 1 + .022 * s(1, -1.2); p.rz = .022 * s(1, .4); p.rx = .015 * s(1, -1.2)
   p.open = blinkAt(u, 3, 1.6); p.gx = K(u, [1, 0, 1.5, .3, 2.4, .3, 2.9, 0])
   break
  }
  case "practical": { // a look down at the screen, a nod, a dry side-eye
   p.gy = K(u, [.4, 0, .6, .55, 1.6, .55, 1.8, 0]); p.rx = K(u, [.4, 0, .6, .06, 1.6, .06, 1.75, -.02, 1.95, .04, 2.2, 0])
   p.gx = K(u, [2.5, 0, 2.62, .55, 3.25, .55, 3.4, 0]); p.lift = .04 + K(u, [.4, 0, .6, .06, 1.6, .06, 1.8, 0])
   break
  }
  case "precise": { // brings the lens up to an eye, leans in, studies, lowers it
   const up = K(u, [.6, 0, 1.05, 1, 2.5, 1, 3.05, 0])
   p.ru += .12 * up; p.lift = up; p.rx = .06 * up; p.gx = .3 * up; p.gy = -.1 * up; p.rz += -.05 * up
   break
  }
  default: p.gx = K(u, [.8, 0, 1, -.4, 1.7, -.4, 1.9, .35, 2.6, .35, 2.8, 0])
 }
 else if (state === "thinking") { p.rz = .08 + .015 * s(1); p.gx = .45; p.gy = -.45; p.ru = .55; p.rf = .9; p.sy = 1 + .01 * s(2) }
 else if (state === "working") { p.gy = .45; p.rx = .05; p.lift = .06 + .04 * Math.abs(s(4)); p.lf += .12 * s(4); p.rf += .12 * s(4, Math.PI); p.sy = 1 + .015 * s(4) }
 else if (state === "needs") { const [y, sy] = hop(u % 2, .3, .05); p.y = y; p.sy *= sy; p.ru = .9 + .12 * s(4); p.rf = .2 }
 else if (state === "error") { p.rx = .1; p.sy = .95 + .01 * s(1); p.gy = .5; p.open = Math.min(p.open, .65); p.lu = p.ru = 0; p.lift = -.1 }
 else if (state === "talking") { p.talk = Math.max(0, Math.sin(t * 11) * .6 + Math.sin(t * 7.3) * .4); p.rx = .02 * s(4); p.sy = 1 + .012 * s(4) }
 else if (state === "pointing") { p.ru = .78; p.rf = .55; p.rz = .05; p.gx = .4 }
 if (state === "listening") { p.rx += .06; p.open = Math.max(p.open, .02) }
 return p
}

const DUR: Record<string, number> = { wave: 2.2, wake: 2.3, drop: 1.6, pitch: 1.9, hired: 1.3, pop: .8, happy: 1.15, admire: 1.3, done: 1.4 }
/// A gesture at time g since it began. Gestures start and end on the state's loop, blended.
function gesture(name: string, g: number, base: Pose, mood: string, prop: string): Pose {
 const p = { ...base }, e = ENERGY[mood] ?? 1, left = HOLD[prop] === "hand" // a nub that's holding something doesn't wave
 const [U, F, OF] = left ? ["lu", "lf", "rf"] as const : ["ru", "rf", "lf"] as const
 switch (name) {
  case "wave": { // crouch a touch, swing a nub up, three waves that fade, bring it down past rest and settle
   const up = K(g, [0, 0, .16, -.08, .42, 1, 1.62, 1, 1.9, -.06, 2.05, .02, 2.2, 0])
   const wv = K(g, [.42, 0, .55, 1, 1.45, 1, 1.62, 0]) * Math.sin((g - .42) * TAU * 2.4) * .3
   const side = left ? -1 : 1
   p[U] = base[U] * (1 - Math.min(1, up)) + up * 1.05 + wv; p[F] = base[F] * (1 - Math.min(1, up)) + up * .15
   p.sy *= K(g, [0, 1, .16, .95, .42, 1.04, .7, 1, 1.62, 1, 1.85, .98, 2.05, 1.01, 2.2, 1])
   p.rz += side * K(g, [0, 0, .16, -.03, .45, .07, 1.62, .07, 1.95, -.01, 2.2, 0]) + wv * .15
   p.squint = K(g, [.3, 0, .5, .45, 1.6, .45, 1.9, 0]); p.gx = 0; p.gy = 0
   p.dx = side * -.03 * Math.min(1, up); p.tilt += side * .1 * Math.min(1, up) // the prop shifts to the other nub
   if (HOLD[prop] === "both") p[OF] += .1 * Math.min(1, up)
   break
  }
  case "wake": { // asleep, a breath in, blinks awake and looks at you
   const awake = K(g, [.7, 0, .95, 1])
   p.open = g < .78 ? .05 : g < 1.3 ? K(g, [.78, .05, .92, 1, 1.12, 1, 1.18, .06, 1.24, .06, 1.34, 1]) : base.open
   p.sy *= K(g, [0, .95, .5, .955, .85, 1.06, 1.1, .98, 1.3, 1.01, 1.5, 1])
   p.rx = K(g, [0, .08, .7, .08, .95, -.03, 1.3, 0])
   p.gy = K(g, [0, .55, .9, .55, 1.4, 0]); p.gx = K(g, [1.25, 0, 1.45, -.2, 1.7, -.2, 1.9, 0])
   p.lift *= awake; p.lu *= .4 + .6 * awake; p.ru *= .4 + .6 * awake
   p.squint = K(g, [1.5, 0, 1.7, .4, 2.1, .4, 2.3, 0])
   const [y, sy] = hop(g, 1.6, .02); p.y += y; p.sy *= sy
   break
  }
  case "drop": { // falls in stretched, lands squashed, rebounds and settles
   const fall = .38
   p.y = g < fall ? 1.7 * (1 - (g / fall) ** 2) : K(g, [fall, 0, .5, 0, .6, .045, .72, 0])
   p.sy *= K(g, [0, 1.1, fall - .04, 1.2, fall + .04, .7, .5, .82, .6, 1.08, .72, .95, .86, 1.03, 1, .995, 1.15, 1])
   p.ru = K(g, [0, .6, fall, .5, fall + .06, .05, .7, .2, .9, base.ru])
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
   p.lu = base.lu + arms * .55; p.ru = base.ru + arms * .55; p.lift = base.lift + arms * .5
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
 return p
}
const GESTURE: Record<string, string> = { signature: "pitch", point: "pointing", "needs-you": "needs", sad: "error", thinking: "thinking", working: "working", talking: "talking" }
const ONCE = new Set(Object.keys(DUR))

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
 // the little things nobody keys: blinks and glances, and following the pointer
 blinkNext = 1 + Math.random() * 3; blinkStart = -9; glanceNext = 1; glance = [0, 0]; gaze = [0, 0]; turn = [0, 0]

 constructor() {
  this.group.add(this.root); this.root.add(this.body)
  this.shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false }))
  this.shadow.rotation.x = -Math.PI / 2; this.shadow.position.y = .002; this.shadow.renderOrder = -1
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
  this.held.position.copy(b.belly.p).add(new THREE.Vector3(0, 0, .09)); this.held.scale.setScalar(1.42)
  this.shadow.scale.set(s.w * 2.7, s.w * 2.7 * s.d * 1.1, 1)
  for (const n of [this.prop, this.wear]) n?.removeFromParent()
  this.prop = prop(look.prop, b); this.hand = null; this.wear = null
  if (this.prop) {
   const h = HOLD[look.prop]
   if (h === "both") this.held.add(this.prop)
   else if (h === "worn") this.body.add(this.prop)
   else { const hand = new THREE.Group(); hand.scale.setScalar(1.3); hand.add(this.prop); this.body.add(hand); this.hand = hand }
  }
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
  const base = loop(st, t + (this.live ? this.phase : 0), this.mood, prop)
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
   p.gx += this.gaze[0] * (1 - Math.abs(p.gx)); p.gy += this.gaze[1] * .6; p.ry += this.turn[0] * .3; p.rx += this.turn[1] * .08
  }
  this.pose = p
  this.follow(p, dt)
  this.apply(p)
 }

 /// The spring: kicked by the hold point's vertical acceleration and by leaning, a stiff soft bounce that settles.
 follow(p: Pose, dt: number) {
  const s = this.spring, y = p.y + (p.sy - 1) * .5
  if (s.first || dt <= 0) { s.first = false; s.y = y; s.vy = 0; s.rx = p.rx; return }
  for (let n = Math.max(1, Math.ceil(dt * 120)), h = dt / n, i = 0; i < n; i++) {
   const vy = (y - s.y) / dt, ay = clamp((vy - s.vy) / dt, 60), lean = clamp((p.rx - s.rx) / dt, 4)
   const force = -190 * s.a - 13 * s.v - ay * .055 - lean * 1.1
   s.v += force * h; s.a = clamp(s.a + s.v * h, .45)
   if (i === n - 1) { s.vy = vy; s.y = y; s.rx = p.rx }
  }
 }
 /// Settles the spring at rest: pictures and seeking start from here.
 still() { this.spring = { a: 0, v: 0, y: 0, vy: 0, rx: 0, first: true } }

 apply(p: Pose) {
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
   const side = i ? 1 : -1, up = i ? p.ru : p.lu, fwd = i ? p.rf : p.lf
   a.children[0].scale.y = .14 * (1 + .28 * Math.min(1, Math.max(0, up - .45) * 2)) // a raised nub reaches
   a.rotation.set(-fwd, -side * Math.max(0, fwd) * 1.1, side * (.1 + up * 2.5), "YXZ") // swung forward, a nub comes in toward the middle
  })
  const sp = this.spring.a
  if (this.prop && HOLD[this.look!.prop] === "both") {
   this.held.position.set(b.belly.p.x + p.dx, b.belly.p.y + p.lift * .16, b.belly.p.z + .09 + p.lift * .06)
   this.held.rotation.set(-.05 - p.lift * .22 + sp, 0, p.tilt)
  }
  if (this.hand) { // at the nub's tip, upright and facing you, tipping a little with the nub and the spring
   const a = this.arms[1]; a.updateMatrix(); this.hand.position.set(.005, -.15, .03).applyMatrix4(a.matrix).add(new THREE.Vector3(-.1, .07, .1).multiplyScalar(p.lift)) // lifted: brought up and in, to the face
   this.hand.rotation.set(sp * .8 - .1, -.15, (p.ru - .3) * .25 + p.tilt * .6)
  }
  if (this.prop && HOLD[this.look!.prop] === "worn") this.prop.rotation.x = sp * .15
  if (this.wear && this.wear.parent === this.body) this.wear.rotation.z = sp * .6
  // the shadow shrinks and fades as the companion leaves the ground
  const lift = Math.max(0, p.y), k = Math.max(.45, 1 - lift * 1.6) * Math.max(.001, p.scale)
  this.shadow.scale.set(s.w * 2.7 * k * sx, s.w * 2.7 * s.d * 1.1 * k * sx, 1); (this.shadow.material as THREE.MeshBasicMaterial).opacity = Math.max(.3, 1 - lift * 2)
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

// ---------------------------------------------------------------- the shared renderer

let renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.PerspectiveCamera
const instances = new Map<string, Companion>()
// What each framing shows: the whole body with room to hop and wave, the top half, or the face.
const FRAMES = { full: { y: .66, span: 1.8 }, bust: { y: .7, span: 1.1 }, head: { y: 0, span: .72 } }

export async function load() { /* nothing to fetch: every blob is built here */ }
function setup() {
 renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, premultipliedAlpha: true, powerPreference: "low-power" })
 renderer.setPixelRatio(1); renderer.setSize(512, 512, false)
 renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = .92
 scene = new THREE.Scene()
 const pmrem = new THREE.PMREMGenerator(renderer)
 scene.environment = pmrem.fromScene(new RoomEnvironment(), .04).texture; pmrem.dispose()
 camera = new THREE.PerspectiveCamera(20, 1, .1, 30)
 scene.add(new THREE.HemisphereLight("#fffaf2", "#a89c96", .3))
 const key = new THREE.DirectionalLight("#fff4e8", 1.55); key.position.set(-2.6, 2.7, 1.5); scene.add(key)
 const fill = new THREE.DirectionalLight("#eef2ff", .14); fill.position.set(2.4, .4, 1.6); scene.add(fill)
 const rim = new THREE.DirectionalLight("#ffffff", 1.1); rim.position.set(1.2, 1.6, -2.6); scene.add(rim)
}

/// Frames the camera on a companion. The whole body is framed the same for every shape, so heights compare.
function aim(frame: Frame, c: Companion) {
 const f = FRAMES[frame], s = c.shape.def, d = f.span / 2 / Math.tan(THREE.MathUtils.degToRad(10))
 const y = frame === "full" ? f.y : frame === "bust" ? Math.max(f.y, s.h * .62) : s.eye * s.h * (c.pose.sy || 1) + c.pose.y - .03
 const az = .1
 camera.position.set(Math.sin(az) * d, y + d * .06, Math.cos(az) * d); camera.lookAt(0, y, 0)
}

/// Draws one companion into the top-left w x w of the shared canvas.
function draw(c: Companion, w: number, frame: Frame) {
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
function seek(c: Companion, t: number) {
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
  if (!c) instances.set(s.id, c = new Companion())
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
export function picture(look: Look, state: MascotState, px: number, frame: Frame) {
 start()
 const c = new Companion()
 c.setLook(look); c.state = state; c.live = false
 c.update(0, STILL_AT[state] ?? .3, null)
 instances.set("__picture", c)
 draw(c, px, frame)
 const out = document.createElement("canvas"); out.width = out.height = px
 out.getContext("2d")!.drawImage(renderer.domElement, 0, 0, px, px, 0, 0, px, px)
 scene.remove(c.group); instances.delete("__picture"); c.dispose()
 return out.toDataURL("image/webp", .9)
}

/// A gesture (or a state's loop) as frames, for reels and review: PNG data URLs at fps for the given seconds.
export function frames(look: Look, move: string, seconds: number, fps = 30, px = 512, frame: Frame = "full"): string[] {
 start()
 const c = new Companion(), name = GESTURE[move] ?? move
 c.setLook(look); c.live = false
 if (ONCE.has(name)) c.begin(name, 0); else c.state = (name === "needs-you" ? "needs" : name) as MascotState
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
