import { useEffect, useMemo, useRef, type RefObject } from "react"
import { Canvas, advance, useFrame } from "@react-three/fiber"
import { Outlines } from "@react-three/drei"
import * as THREE from "three"
import { clock, pointer, slots, useSlots, type Kind, type MascotState, type Slot } from "./Mascot"

// The mascots, built from soft primitives. Loaded lazily (three.js is most of this chunk).
// One hidden canvas renders every visible mascot in turn, at most 30 times a second, and copies each into its slot.
const SIZE = 512

// Soft matte toon shading: a smooth ramp, plus a rim term in the shader so silhouettes still read at 20px.
const ramp = new THREE.DataTexture(new Uint8Array([78, 150, 212, 255]), 4, 1, THREE.RedFormat)
ramp.minFilter = ramp.magFilter = THREE.LinearFilter
ramp.needsUpdate = true
const cache = new Map<string, unknown>()
const once = <T,>(key: string, make: () => T) => (cache.get(key) ?? (cache.set(key, make()), cache.get(key))) as T
const toon = (color: string, rim = "#ffffff", strength = .4) => once("toon" + color + rim + strength, () => {
 const m = new THREE.MeshToonMaterial({ color, gradientMap: ramp })
 m.onBeforeCompile = shader => {
  shader.uniforms.uRim = { value: new THREE.Color(rim).multiplyScalar(strength) }
  shader.fragmentShader = "uniform vec3 uRim;\n" + shader.fragmentShader.replace("#include <opaque_fragment>",
   "outgoingLight += uRim * pow(1.0 - saturate(dot(normal, normalize(vViewPosition))), 2.5);\n#include <opaque_fragment>")
 }
 return m
})
const flat = (color: string, opacity = 1) => once("flat" + color + opacity, () => new THREE.MeshBasicMaterial({ color, transparent: opacity < 1, opacity, depthWrite: opacity === 1 }))
const sphere = (r: number) => once("s" + r, () => new THREE.SphereGeometry(r, 32, 24))
const capsule = (r: number, l: number) => once("c" + r + l, () => new THREE.CapsuleGeometry(r, l, 10, 32))
const torus = (r: number, t: number, arc = Math.PI * 2) => once("t" + r + t + arc, () => new THREE.TorusGeometry(r, t, 12, 40, arc))
const cylinder = (r: number, h: number) => once("y" + r + h, () => new THREE.CylinderGeometry(r, r, h, 12))
const cone = (r: number, h: number) => once("k" + r + h, () => new THREE.ConeGeometry(r, h, 20))
const box = (s: number) => once("b" + s, () => new THREE.BoxGeometry(s, s * .5, s * .15))
const lathe = (points: number[][]) => once("l" + points.join(), () => new THREE.LatheGeometry(new THREE.SplineCurve(points.map(([x, y]) => new THREE.Vector2(x, y))).getPoints(40), 48))
const shadowMap = once("shadow", () => {
 const c = document.createElement("canvas"); c.width = c.height = 64
 const g = c.getContext("2d")!, r = g.createRadialGradient(32, 32, 0, 32, 32, 32)
 r.addColorStop(0, "rgba(40,28,20,.5)"); r.addColorStop(.5, "rgba(40,28,20,.22)"); r.addColorStop(1, "rgba(40,28,20,0)")
 g.fillStyle = r; g.fillRect(0, 0, 64, 64)
 return new THREE.CanvasTexture(c)
})

// How each one moves. Clay is warm and bouncy, Mo calm and slow, Vex quick and snappy and always hovering.
type Persona = { stiff: number; damp: number; speed: number; breath: number; hover: number; blink: number; top: number; frame: [number, number]; dot: string }
const PERSONA: Record<Kind, Persona> = {
 claude: { stiff: 260, damp: 20, speed: 1, breath: 1.5, hover: 0, blink: 3.2, top: 1.45, frame: [5.2, .72], dot: "#e8875f" },
 chatgpt: { stiff: 140, damp: 17, speed: .72, breath: 1, hover: 0, blink: 4.6, top: 1.5, frame: [5.2, .74], dot: "#4fc4a8" },
 grok: { stiff: 420, damp: 26, speed: 1.3, breath: .5, hover: .14, blink: 2.4, top: 1.82, frame: [5.9, .94], dot: "#c8ff3d" },
}
const KEYS = ["y", "squash", "lean", "tilt", "turn", "pitch", "eye", "armL", "armR", "dots", "party", "gx", "gy"] as const
type Pose = Record<(typeof KEYS)[number], number>

function target(state: MascotState, t: number, p: Persona, look: { x: number; y: number } | null, glance: number): Pose {
 const s = t * p.speed, hover = p.hover + (p.hover ? Math.sin(s * 2.2) * .035 : 0)
 const base: Pose = { y: hover, squash: 1 + Math.sin(s * 1.85) * .022 * p.breath, lean: 0, tilt: 0, turn: look ? look.x * .55 : glance, pitch: look ? look.y * .22 : 0,
  eye: 1, armL: .18 + Math.sin(s * 1.3) * .05, armR: .18 - Math.sin(s * 1.3) * .05, dots: 0, party: 0, gx: look ? look.x : glance * 1.4, gy: look ? -look.y : 0 }
 switch (state) {
  case "listening": return { ...base, lean: .12, pitch: base.pitch + .05 + Math.sin(s * 3) * .05, eye: 1.15, armL: .45, armR: .45 }
  case "thinking": return { ...base, tilt: .2, pitch: -.14, turn: .15, eye: .9, gx: .6, gy: .8, dots: 1, armR: 1.1 + Math.sin(s * 2) * .06 }
  case "working": { const b = Math.abs(Math.sin(s * 9)); return { ...base, y: hover + b * .04, squash: 1 + (b - .5) * .05, lean: .1, pitch: .12, turn: 0, eye: .85, gx: 0, gy: -.6, armL: .55 + Math.sin(s * 14) * .35, armR: .55 - Math.sin(s * 14) * .35 } }
  case "needs": { const b = Math.abs(Math.sin(s * 5.5)); return { ...base, y: hover + b * .16, squash: .95 + b * .1, tilt: Math.sin(s * 5.5) * .06, turn: 0, eye: 1.2, gx: 0, gy: 0, armL: .25, armR: 2.6 + Math.sin(s * 11) * .35 } }
  case "done": { const b = Math.abs(Math.sin(s * 4.5)); return { ...base, y: hover + b * .2, squash: .94 + b * .12, turn: Math.sin(s * 2) * .3, eye: .5, gx: 0, gy: 0, armL: 2.5 + Math.sin(s * 9) * .15, armR: 2.5 - Math.sin(s * 9) * .15, party: 1 } }
  case "error": return { ...base, y: p.hover * .35, squash: .9, lean: .18, pitch: .12, tilt: .08 + Math.sin(s) * .04, turn: 0, eye: .45, gx: 0, gy: -.8, armL: .04, armR: .04 }
  default: return base
 }
}

type Rig = { root: RefObject<THREE.Group | null>; head: RefObject<THREE.Group | null>; eyes: RefObject<THREE.Group | null>; armL: RefObject<THREE.Group | null>; armR: RefObject<THREE.Group | null>; mouth: RefObject<THREE.Mesh | null> }
const clamp = (v: number) => Math.max(-1, Math.min(1, v))

function Character({ slot }: { slot: Slot }) {
 const kind = slot.kind, p = PERSONA[kind]
 const rig: Rig = { root: useRef(null), head: useRef(null), eyes: useRef(null), armL: useRef(null), armR: useRef(null), mouth: useRef(null) }
 const dots = useRef<THREE.Group>(null), party = useRef<THREE.Group>(null), shadow = useRef<THREE.Mesh>(null)
 const shade = useMemo(() => new THREE.MeshBasicMaterial({ map: shadowMap, transparent: true, depthWrite: false }), [])
 const m = useRef({ pose: null as Pose | null, vel: Object.fromEntries(KEYS.map(k => [k, 0])) as Pose, last: 0, blinkAt: 0, blinkEnd: 0, glance: 0, glanceEnd: 0, glanceNext: 3 }).current
 useFrame(() => {
  if (!slot.visible || !rig.root.current) return
  const now = performance.now() / 1000, t = clock.frozen ?? now, dt = Math.min(.05, m.last ? now - m.last : 1 / 30)
  m.last = now
  if (t > m.glanceNext) { m.glance = (Math.random() * 2 - 1) * .45; m.glanceEnd = t + 1.4; m.glanceNext = t + 5 + Math.random() * 4 }
  let look = null
  if (slot.look && pointer.x >= 0) {
   const r = slot.canvas.getBoundingClientRect()
   look = { x: clamp((pointer.x - r.left - r.width / 2) / (innerWidth * .4)), y: clamp((pointer.y - r.top - r.height * .4) / (innerHeight * .4)) }
  }
  const goal = target(slot.state, t, p, look, t < m.glanceEnd ? m.glance : 0)
  if (!m.pose || clock.still) m.pose = goal
  else for (const k of KEYS) { // a spring per value, so every change of state lands with a little overshoot
   m.vel[k] += (p.stiff * (goal[k] - m.pose[k]) - p.damp * m.vel[k]) * dt
   m.pose[k] += m.vel[k] * dt
  }
  if (!clock.still && t > m.blinkAt) { m.blinkEnd = t + .13; m.blinkAt = t + p.blink * (.7 + Math.random() * .8) }
  const pose = m.pose, blink = t < m.blinkEnd ? .08 : 1, sq = Math.max(.6, pose.squash)
  rig.root.current.position.y = pose.y
  rig.root.current.scale.set(1 / Math.sqrt(sq), sq, 1 / Math.sqrt(sq))
  rig.root.current.rotation.set(pose.lean, 0, pose.tilt)
  rig.head.current?.rotation.set(pose.pitch, pose.turn, 0)
  if (rig.eyes.current) {
   rig.eyes.current.scale.y = Math.max(.06, pose.eye * blink)
   rig.eyes.current.position.set(pose.gx * .03, (rig.eyes.current.userData.y ?? 0) + pose.gy * .025, 0)
  }
  rig.armL.current?.rotation.set(0, 0, -pose.armL)
  rig.armR.current?.rotation.set(0, 0, pose.armR)
  if (rig.mouth.current) rig.mouth.current.rotation.z = slot.state === "error" ? 0 : Math.PI
  if (dots.current) {
   dots.current.visible = pose.dots > .02
   dots.current.children.forEach((d, i) => { const a = t * 2.6 + i * 2.09; d.position.set(Math.cos(a) * .34, p.top + Math.sin(t * 3 + i) * .05, Math.sin(a) * .2); d.scale.setScalar(Math.max(0, pose.dots)) })
  }
  if (party.current) {
   party.current.visible = pose.party > .02
   party.current.children.forEach((c, i) => {
    const a = t * 1.6 + i * 1.047, rise = (t * .55 + i / 6) % 1
    c.position.set(Math.cos(a) * .62, .45 + rise * 1.05, Math.sin(a) * .35)
    c.rotation.set(t * 4 + i, t * 3, i)
    c.scale.setScalar(Math.max(0, pose.party) * (1 - rise * .6))
   })
  }
  if (shadow.current) {
   const lift = Math.max(0, pose.y - p.hover * .6)
   shadow.current.scale.setScalar(Math.max(.55, 1 - lift * 1.4))
   shade.opacity = Math.max(.3, 1 - lift * 2)
  }
 })
 const Model = kind === "grok" ? Vex : kind === "chatgpt" ? Mo : Clay
 return <group ref={g => { slot.group = g ?? undefined }} visible={false}>
  <mesh ref={shadow} geometry={once("plane", () => new THREE.PlaneGeometry(1.25, 1.25))} material={shade} rotation-x={-Math.PI / 2} position-y={.002} />
  <group ref={rig.root}><Model rig={rig} slot={slot} /></group>
  <group ref={dots}>{[0, 1, 2].map(i => <mesh key={i} geometry={sphere(.05)} material={flat(p.dot)} />)}</group>
  <group ref={party}>{["#ff8a65", "#ffd54f", "#81c784", "#64b5f6", "#ba68c8", "#f06292"].map(c => <mesh key={c} geometry={box(.11)} material={flat(c)} />)}</group>
 </group>
}

const Part = ({ geo, mat, ink, ...rest }: { geo: THREE.BufferGeometry; mat: THREE.Material; ink?: string } & Omit<React.ComponentProps<"mesh">, "geometry" | "material">) =>
 <mesh geometry={geo} material={mat} {...rest}>{ink && <Outlines thickness={.018} color={ink} />}</mesh>

/// A head that turns and nods around a pivot, with features placed in body coordinates.
const Head = ({ rig, at, children }: { rig: Rig; at: number; children: React.ReactNode }) =>
 <group ref={rig.head} position-y={at}><group position-y={-at}>{children}</group></group>

const Eyes = ({ rig, y, x, z, r, ink = "#2b1b14", shine = true }: { rig: Rig; y: number; x: number; z: number; r: number; ink?: string; shine?: boolean }) =>
 <group ref={g => { rig.eyes.current = g; if (g) g.userData.y = y }} position-y={y}>
  {[-x, x].map(ex => <group key={ex} position={[ex, 0, z]}>
   <mesh geometry={sphere(r)} material={toon(ink, "#ffffff", .15)} scale={[1, 1.25, .55]} />
   {shine && <mesh geometry={sphere(r * .32)} material={flat("#ffffff")} position={[r * .32, r * .5, r * .45]} />}
  </group>)}
 </group>

// Clay: a warm terracotta gumdrop with a curl of clay on top. (Claude)
function Clay({ rig }: { rig: Rig; slot: Slot }) {
 const body = toon("#da7756", "#ffd9bf", .45), dark = toon("#c25f3e", "#ffd9bf", .35), ink = "#7a3420"
 return <>
  <Part geo={lathe([[0, 0], [.4, .015], [.56, .12], [.6, .32], [.55, .58], [.43, .83], [.26, 1], [.08, 1.075], [0, 1.08]])} mat={body} ink={ink} />
  {[-.21, .21].map(x => <Part key={x} geo={sphere(.14)} mat={dark} ink={ink} position={[x, .04, .12]} scale={[1, .5, 1.25]} />)}
  <group ref={rig.armL} position={[-.5, .48, .05]}><Part geo={capsule(.075, .16)} mat={body} ink={ink} position-y={-.14} /></group>
  <group ref={rig.armR} position={[.5, .48, .05]}><Part geo={capsule(.075, .16)} mat={body} ink={ink} position-y={-.14} /></group>
  <Head rig={rig} at={.55}>
   <Part geo={sphere(.1)} mat={body} ink={ink} position={[0, 1.07, 0]} />
   <Part geo={sphere(.066)} mat={body} ink={ink} position={[.07, 1.16, 0]} />
   <Part geo={sphere(.04)} mat={body} ink={ink} position={[.14, 1.2, 0]} />
   <Eyes rig={rig} y={.66} x={.17} z={.49} r={.075} />
   <mesh ref={rig.mouth} geometry={torus(.055, .014, Math.PI)} material={toon("#5a2a1a", "#000000", 0)} position={[0, .54, .552]} rotation-z={Math.PI} />
   {[-.3, .3].map(x => <mesh key={x} geometry={sphere(.06)} material={flat("#f2a48c")} position={[x, .55, .475]} scale={[1, .6, .35]} rotation-y={x * 1.6} />)}
  </Head>
 </>
}

// Mo: a calm round teal pebble with a two-leaf sprout. (ChatGPT)
function Mo({ rig }: { rig: Rig; slot: Slot }) {
 const body = toon("#48b39b", "#d8fff4", .45), dark = toon("#2f927b", "#d8fff4", .3), leaf = toon("#8ed89a", "#f4ffe8", .4), ink = "#1f6b5b"
 return <>
  <Part geo={sphere(.56)} mat={body} ink={ink} position-y={.56} scale={[1, .95, .96]} />
  <mesh geometry={sphere(.36)} material={toon("#d6f2e8", "#ffffff", .2)} position={[0, .42, .33]} scale={[1, .95, .55]} />
  {[-.2, .2].map(x => <Part key={x} geo={sphere(.12)} mat={dark} ink={ink} position={[x, .05, .16]} scale={[1.1, .55, 1.3]} />)}
  <group ref={rig.armL} position={[-.53, .5, .04]}><Part geo={sphere(.1)} mat={body} ink={ink} position-y={-.1} scale={[.55, 1, .6]} /></group>
  <group ref={rig.armR} position={[.53, .5, .04]}><Part geo={sphere(.1)} mat={body} ink={ink} position-y={-.1} scale={[.55, 1, .6]} /></group>
  <Head rig={rig} at={.56}>
   <Part geo={cylinder(.02, .16)} mat={dark} position-y={1.12} />
   {[-1, 1].map(d => <Part key={d} geo={sphere(.1)} mat={leaf} ink="#3f8a4e" position={[d * .1, 1.21, 0]} scale={[1.5, .35, .75]} rotation-z={-d * .55} />)}
   <Eyes rig={rig} y={.68} x={.19} z={.49} r={.068} ink="#173b33" />
   <mesh ref={rig.mouth} geometry={torus(.05, .013, Math.PI)} material={toon("#173b33", "#000000", 0)} position={[0, .56, .53]} rotation-z={Math.PI} />
   {[-.33, .33].map(x => <mesh key={x} geometry={sphere(.055)} material={flat("#f7b7a3")} position={[x, .56, .42]} scale={[1, .6, .35]} rotation-y={x * 1.5} />)}
  </Head>
 </>
}

// Vex: a sleek graphite capsule with a dark visor, lime eyes and an antenna. It never touches the ground. (Grok)
function Vex({ rig, slot }: { rig: Rig; slot: Slot }) {
 const body = toon("#2c3139", "#a9b8ff", .55), fin = toon("#3a414b", "#a9b8ff", .5), ink = "#0b0d10"
 const lime = useMemo(() => new THREE.MeshBasicMaterial({ color: "#c8ff3d" }), [])
 const tip = useRef<THREE.Mesh>(null), ring = useRef<THREE.Mesh>(null)
 useFrame(() => {
  if (!slot.visible) return
  const t = clock.frozen ?? performance.now() / 1000
  lime.color.set(slot.state === "error" ? "#ff6b5a" : "#c8ff3d")
  tip.current?.scale.setScalar(1 + Math.sin(t * 4) * .15)
  if (ring.current) (ring.current.material as THREE.MeshBasicMaterial).opacity = .35 + Math.sin(t * 2.2) * .15
 })
 return <>
  <mesh ref={ring} geometry={torus(.26, .016)} material={useMemo(() => new THREE.MeshBasicMaterial({ color: "#c8ff3d", transparent: true, opacity: .45, depthWrite: false }), [])} rotation-x={Math.PI / 2} position-y={-.1} />
  <Part geo={capsule(.36, .6)} mat={body} ink={ink} position-y={.66} />
  <mesh geometry={torus(.364, .012)} material={lime} rotation-x={Math.PI / 2} position-y={.48} />
  <group ref={rig.armL} position={[-.5, .72, .05]}><Part geo={sphere(.085)} mat={body} ink={ink} position-y={-.22} /></group>
  <group ref={rig.armR} position={[.5, .72, .05]}><Part geo={sphere(.085)} mat={body} ink={ink} position-y={-.22} /></group>
  <Head rig={rig} at={.95}>
   <group position={[0, .98, .3]} scale={[1, 1, .6]}><Part geo={capsule(.16, .34)} mat={toon("#0a0d12", "#c8ff3d", .25)} ink={ink} rotation-z={Math.PI / 2} /></group>
   <group ref={g => { rig.eyes.current = g; if (g) g.userData.y = .98 }} position-y={.98}>
    {[-.12, .12].map(x => <mesh key={x} geometry={capsule(.04, .05)} material={lime} position={[x, 0, .4]} />)}
   </group>
   <mesh geometry={cylinder(.014, .24)} material={fin} position-y={1.42} />
   <mesh ref={tip} geometry={sphere(.05)} material={lime} position-y={1.57} />
   {[-1, 1].map(d => <Part key={d} geo={cone(.09, .3)} mat={fin} ink={ink} position={[d * .37, 1.04, -.05]} rotation={[-.3, 0, -d * 1.1]} />)}
  </Head>
 </>
}

function Renderer() {
 useFrame(({ gl, scene, camera }) => {
  const H = gl.domElement.height
  gl.setScissorTest(true)
  for (const s of slots.values()) {
   if (!s.visible || !s.group) continue
   const w = Math.min(s.canvas.width, H), [d, h] = PERSONA[s.kind].frame
   for (const o of slots.values()) if (o.group) (o.group as THREE.Object3D).visible = o === s
   camera.position.set(0, h + .35, d); camera.lookAt(0, h, 0)
   gl.setViewport(0, H - w, w, w); gl.setScissor(0, H - w, w, w)
   gl.setClearColor(0, 0); gl.clear()
   gl.render(scene, camera)
   const ctx = s.canvas.getContext("2d")!
   ctx.clearRect(0, 0, s.canvas.width, s.canvas.height)
   ctx.drawImage(gl.domElement, 0, 0, w, w, 0, 0, s.canvas.width, s.canvas.height)
   s.canvas.dataset.live = ""
  }
  gl.setScissorTest(false)
 }, 1)
 return null
}

function Ticker() {
 useEffect(() => {
  let frame = 0, last = 0
  const tick = (now: number) => {
   frame = requestAnimationFrame(tick)
   if (document.hidden || now - last < 1000 / 30 - 2) return // at most 30 frames a second, none while hidden
   for (const s of slots.values()) if (s.visible) { last = now; advance(now); return }
  }
  frame = requestAnimationFrame(tick)
  return () => cancelAnimationFrame(frame)
 }, [])
 return null
}

export default function Stage() {
 const list = useSlots()
 return <Canvas frameloop="never" flat dpr={1} gl={{ antialias: true, alpha: true, powerPreference: "low-power" }} camera={{ fov: 22 }}
  style={{ position: "fixed", left: -10000, top: 0, width: SIZE, height: SIZE, pointerEvents: "none" }} aria-hidden>
  <hemisphereLight args={["#fff6ec", "#9aa4b8", 1.2]} />
  <directionalLight position={[-2.5, 4, 3.5]} intensity={1.7} color="#fffaf2" />
  <directionalLight position={[3, 2.5, -4]} intensity={2.4} color="#dfeaff" />
  {list.map(s => <Character key={s.id + s.kind} slot={s} />)}
  <Renderer />
  <Ticker />
 </Canvas>
}
