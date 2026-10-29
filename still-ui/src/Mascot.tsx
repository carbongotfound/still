import { useEffect, useId, useRef, useSyncExternalStore, type CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { AGENT_LOOKS, BLANK, DEFAULT_LOOK, ROLE_LOOKS, lookKey, type Look } from "./look"

// The companion, as a soft 3D blob (companion3d.ts). Every <Mascot> is a small 2D canvas: one hidden WebGL canvas
// renders each visible companion in turn and copies it in, so they layer, clip and scroll like any other element.
// Small idle ones (the toolbar, tab markers, lists) are still pictures rendered from the same model and kept in
// localStorage, so a plain window never loads three.js for them. Big or busy ones are live. The engine waits until a
// live one has stayed a second (not the home page flashing by at startup). With WebGL off or reduced motion on,
// every companion is a still picture.
export const STATES = ["idle", "listening", "thinking", "working", "needs", "done", "error", "talking", "pointing"] as const
export type MascotState = (typeof STATES)[number]
export type Frame = "full" | "bust"

export type Slot = { id: string; look: Look; state: MascotState; follow: boolean; gesture: string; gestureAt: number; frame: Frame; canvas: HTMLCanvasElement; visible: boolean }
export const slots = new Map<string, Slot>()
// Tests freeze time and skip blinks and crossfades, so a pose is exact: <html data-mascot-freeze="0.35">.
export const clock = { get frozen() { const f = document.documentElement.dataset.mascotFreeze; return f ? +f : null }, get still() { return !!document.documentElement.dataset.mascotFreeze } }
export const pointer = { x: -1, y: -1 }

let version = 0
const listeners = new Set<() => void>()
const changed = () => { version++; listeners.forEach(l => l()) }
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
const useVersion = () => useSyncExternalStore(subscribe, () => version)
export const useSlots = () => { useVersion(); return [...slots.values()] }
/// Re-renders when a picture finishes or the engine loads.
export const useMascotVersion = useVersion

const seen = new IntersectionObserver(entries => { for (const e of entries) for (const s of slots.values()) if (s.canvas === e.target) s.visible = e.isIntersecting })
addEventListener("pointermove", e => { pointer.x = e.clientX; pointer.y = e.clientY }, { passive: true })

const webgl = (() => { try { return !!document.createElement("canvas").getContext("webgl2") } catch { return false } })()
const reduce = matchMedia("(prefers-reduced-motion: reduce)")
const useReduced = () => useSyncExternalStore(l => { reduce.addEventListener("change", l); return () => reduce.removeEventListener("change", l) }, () => reduce.matches)

type Engine = typeof import("./companion3d")
let engine: Engine | null = null, loading: Promise<Engine | null> | null = null
export const engineReady = () => !!engine
/// Gestures a companion plays by name (the gesture prop), besides the states. pitch is "pick me", hired a happy bounce.
export const GESTURES = ["idle", "happy", "thinking", "working", "pointing", "needs-you", "done", "sad", "talking", "wave", "admire", "pop", "wake", "drop", "pitch", "hired"] as const
export function loadEngine() {
 return loading ??= import("./companion3d").then(async m => { await m.load(); m.start(); engine = m; changed(); drain(); return m })
  .catch(e => { console.error("The companion couldn't load", e); return null })
}

// ---------------------------------------------------------------- still pictures

const bundled = import.meta.glob("./assets/companion/*.webp", { eager: true, import: "default" }) as Record<string, string>
const PRESETS = Object.entries({ default: DEFAULT_LOOK, blank: BLANK, ...AGENT_LOOKS }).map(([k, l]) => [k, lookKey(l)] as const)
const pictureState = (s: MascotState): MascotState => s === "listening" || s === "talking" ? "idle" : s
const hash = (s: string) => { let h = 5381; for (let i = 0; i < s.length; i++) h = (h * 33 ^ s.charCodeAt(i)) >>> 0; return h.toString(36) }
const memo = new Map<string, string>()
const wanted = new Map<string, { look: Look; state: MascotState; px: number; frame: Frame }>()
const STORE = "still.picture2." // 2: every companion framed whole from its own bounds
try { for (const k of Object.keys(localStorage)) if (k.startsWith("still.picture.")) localStorage.removeItem(k) } catch { /* no storage */ }

function drain() {
 if (!engine || !wanted.size) return
 for (const [key, w] of wanted) {
  try {
   const url = engine.picture(w.look, w.state, w.px, w.frame)
   memo.set(key, url)
   try {
    if (localStorage.length > 400) for (const k of Object.keys(localStorage)) if (k.startsWith(STORE)) localStorage.removeItem(k)
    localStorage.setItem(STORE + key, url)
   } catch { /* storage full or off: the picture lives until the window closes */ }
  } catch (e) { console.error(e) }
 }
 wanted.clear(); changed()
}

/// A still picture of a look in a state: rendered once (loading the engine if it must), then kept.
export function pictureOf(look: Look, state: MascotState, px: number, frame: Frame, render = true): string | undefined {
 state = pictureState(state)
 const lk = lookKey(look), key = `${px}${frame[0]}-${state}-${hash(lk)}`
 const preset = PRESETS.find(p => p[1] === lk)?.[0]
 const shipped = preset && bundled[`./assets/companion/${preset}-${frame}-${state}.webp`]
 if (shipped) return shipped
 let url = memo.get(key)
 if (!url) try { url = localStorage.getItem(STORE + key) ?? undefined; if (url) memo.set(key, url) } catch { /* no storage */ }
 if (url || !render || !webgl) return url ?? bundled[`./assets/companion/default-${frame}-idle.webp`] // no WebGL: the default look, drawn ahead
 if (!wanted.has(key)) { wanted.set(key, { look, state, px, frame }); if (engine) queueMicrotask(drain); else void loadEngine() }
 return undefined
}

// Small companions (under 40px: chat turns, headers, tabs, the working pill) are avatars: the whole body, turned a
// little toward the text, with room on every side. Each role's look and Make your own's are rendered in Blender at 96
// and 144px (crew/blob.py, view "avatar"); any other look gets a full-body picture from the 3D model.
const avatarFiles = import.meta.glob("./assets/avatar/*.png", { eager: true, import: "default" }) as Record<string, string>
const AVATAR = new Map(([[ROLE_LOOKS.closer, "zest"], [ROLE_LOOKS.scout, "bloom"], [ROLE_LOOKS.chief, "noon"], [ROLE_LOOKS.marketer, "fizz"],
 [ROLE_LOOKS.fixer, "mallow"], [ROLE_LOOKS.builder, "rivet"], [ROLE_LOOKS.researcher, "glint"], [BLANK, "custom"]] as [Look, string][])
 .map(([l, f]) => [lookKey(l), [avatarFiles[`./assets/avatar/${f}-96.png`], avatarFiles[`./assets/avatar/${f}-144.png`]]]))

// ---------------------------------------------------------------- the component

export function Mascot({ look, state = "idle", size, follow = false, gesture = "", gestureAt = 0, className, style }: {
 look: Look; state?: MascotState; size: number; follow?: boolean; gesture?: string; gestureAt?: number; className?: string; style?: CSSProperties
}) {
 const id = useId()
 const ref = useRef<HTMLCanvasElement>(null)
 useVersion()
 const reduced = useReduced()
 const small = size < 40
 const avatar = small ? AVATAR.get(lookKey(look)) : undefined
 const live = webgl && !reduced && (!small || !!gesture) && !avatar
 const frame: Frame = "full" // the whole body at every size, never a crop
 const px = Math.min(768, Math.round(size * Math.min(devicePixelRatio || 1, 2)))
 const picture = avatar ? undefined : pictureOf(look, state, small ? 96 : 384, frame, !live)
 useEffect(() => {
  const canvas = ref.current
  if (!live || !canvas) return
  slots.set(id, { id, look, state, follow, gesture, gestureAt, frame, canvas, visible: false })
  seen.observe(canvas)
  changed()
  return () => { seen.unobserve(canvas); slots.delete(id); delete canvas.dataset.live; changed() }
 }, [live, id]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { const s = slots.get(id); if (s) Object.assign(s, { look, state, follow, gesture, gestureAt, frame }) }, [id, look, state, follow, gesture, gestureAt, frame])
 return <span className={cn("mascot", avatar && "is-avatar", className)} data-state={state} style={{ "--s": `${size}px`, ...style } as CSSProperties} aria-hidden>
  {avatar && <img src={avatar[0]} srcSet={`${avatar[0]} 96w, ${avatar[1]} 144w`} sizes={`${size}px`} alt="" draggable={false} />}
  {picture && <img src={picture} alt="" draggable={false} />}
  {live && <canvas ref={ref} width={px} height={px} />}
 </span>
}

/// Mounted once at the root. Loads the engine once a live companion has stayed a second.
export function MascotStage() {
 const reduced = useReduced()
 const count = useSlots().length
 useEffect(() => {
  if (!webgl || reduced || !count || engine) return
  const wait = setTimeout(loadEngine, 1000)
  return () => clearTimeout(wait)
 }, [count, reduced])
 return null
}

// Companions in every state, for screenshots and for rendering the shipped pictures (tests/desktop/mascots.py).
export const SHEET_LOOKS: [string, Look][] = [...Object.entries(ROLE_LOOKS), ["blank", BLANK]]
export function MascotSheet() {
 return <div className="mascot-sheet">
  {SHEET_LOOKS.map(([name, look]) => <section key={name}><h3>{name}</h3>
   <div>{STATES.map(s => <figure key={s} data-look={name} data-state={s}><Mascot look={look} state={s} size={128} />
    <figcaption>{s}</figcaption></figure>)}</div></section>)}
 </div>
}
