import { Suspense, lazy, useEffect, useId, useRef, useState, useSyncExternalStore, type CSSProperties } from "react"
import { cn } from "@/lib/utils"

// Still's mascots: one original 3D character per AI provider, built from code in mascot3d.tsx.
// Every <Mascot> is a small 2D canvas. One hidden WebGL canvas renders each visible mascot in turn and copies it in,
// so mascots layer, clip and scroll like any other element. Until that loads, or with WebGL off or reduced motion on,
// a still picture rendered from the same model shows instead.
export const KINDS = ["claude", "chatgpt", "grok"] as const
export type Kind = (typeof KINDS)[number]
export const STATES = ["idle", "listening", "thinking", "working", "needs", "done", "error"] as const
export type MascotState = (typeof STATES)[number]
export const MASCOT_NAMES: Record<Kind, string> = { claude: "Clay", chatgpt: "Mo", grok: "Vex" }
export const isKind = (k: unknown): k is Kind => KINDS.includes(k as Kind)

const pictures = import.meta.glob("./assets/mascots/*.webp", { eager: true, import: "default" }) as Record<string, string>
const picture = (kind: Kind, state: MascotState) => pictures[`./assets/mascots/${kind}-${state}.webp`] ?? pictures[`./assets/mascots/${kind}-idle.webp`]

export type Slot = { id: string; kind: Kind; state: MascotState; look: boolean; canvas: HTMLCanvasElement; visible: boolean; group?: unknown }
export const slots = new Map<string, Slot>()
// Tests and the picture generator freeze time and skip springs, so a pose is exact: <html data-mascot-freeze="0.35">.
export const clock = { get frozen() { const f = document.documentElement.dataset.mascotFreeze; return f ? +f : null }, get still() { return !!document.documentElement.dataset.mascotFreeze } }
export const pointer = { x: -1, y: -1 }

let version = 0
const listeners = new Set<() => void>()
const changed = () => { version++; listeners.forEach(l => l()) }
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
export const useSlots = () => { useSyncExternalStore(subscribe, () => version); return [...slots.values()] }

const seen = new IntersectionObserver(entries => { for (const e of entries) for (const s of slots.values()) if (s.canvas === e.target) s.visible = e.isIntersecting })
addEventListener("pointermove", e => { pointer.x = e.clientX; pointer.y = e.clientY }, { passive: true })

const webgl = (() => { try { return !!document.createElement("canvas").getContext("webgl2") } catch { return false } })()
const calm = matchMedia("(prefers-reduced-motion: reduce)")
function useLive() {
 const reduced = useSyncExternalStore(l => { calm.addEventListener("change", l); return () => calm.removeEventListener("change", l) }, () => calm.matches)
 return webgl && !reduced
}

export function Mascot({ kind, state = "idle", size, look = false, className, style }: { kind: Kind; state?: MascotState; size: number; look?: boolean; className?: string; style?: CSSProperties }) {
 const id = useId()
 const ref = useRef<HTMLCanvasElement>(null)
 const live = useLive()
 const px = Math.min(512, Math.round(size * Math.min(devicePixelRatio || 1, 2)))
 useEffect(() => {
  const canvas = ref.current
  if (!live || !canvas) return
  slots.set(id, { id, kind, state, look, canvas, visible: false })
  seen.observe(canvas)
  changed()
  return () => { seen.unobserve(canvas); slots.delete(id); delete canvas.dataset.live; changed() }
 }, [live, id]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => {
  const s = slots.get(id)
  if (!s) return
  const kindChanged = s.kind !== kind
  Object.assign(s, { kind, state, look })
  if (kindChanged) changed()
 }, [id, kind, state, look])
 return <span className={cn("mascot", className)} data-kind={kind} data-state={state} style={{ "--s": `${size}px`, ...style } as CSSProperties} aria-hidden>
  <img src={picture(kind, state)} alt="" draggable={false} />
  {live && <canvas ref={ref} width={px} height={px} />}
 </span>
}

const Stage = lazy(() => import("./mascot3d"))
/// Mounted once at the root. Loads three.js the first time a mascot can render live, and keeps it after.
export function MascotStage() {
 const live = useLive()
 const [used, setUsed] = useState(false)
 const count = useSlots().length
 useEffect(() => { if (count) setUsed(true) }, [count])
 return live && used ? <Suspense fallback={null}><Stage /></Suspense> : null
}

/// Every mascot in every state, for screenshots and for rendering the still pictures (see main.tsx).
export function MascotSheet() {
 return <div className="mascot-sheet">
  {KINDS.map(k => <section key={k}><h3>{MASCOT_NAMES[k]} <small>{k}</small></h3>
   <div>{STATES.map(s => <figure key={s}><Mascot kind={k} state={s} size={128} look={s === "idle"} /><figcaption>{s}</figcaption></figure>)}</div></section>)}
 </div>
}
