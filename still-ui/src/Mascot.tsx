import { useEffect, useId, useRef, useState, useSyncExternalStore, type CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { AGENT_LOOKS, BLANK, DEFAULT_LOOK, RIGS, ROLE_LOOKS, lookKey, type Look } from "./look"

// The companion, as a soft 3D blob (companion3d.ts). Every <Mascot> is a small 2D canvas: one hidden WebGL canvas
// renders each visible companion in turn and copies it in, so they layer, clip and scroll like any other element.
// Small idle ones (the toolbar, tab markers, lists) are still pictures rendered from the same model and kept in
// localStorage, so a plain window never loads three.js for them. Big or busy ones are live. The engine waits until a
// live one has stayed a second (not the home page flashing by at startup). With WebGL off or reduced motion on,
// every companion is a still picture.
export const STATES = ["idle", "listening", "thinking", "working", "needs", "done", "error", "talking", "pointing"] as const
export type MascotState = (typeof STATES)[number]
export type Frame = "full" | "bust" | "icon" | "portrait"

export type Slot = { id: string; look: Look; state: MascotState; follow: boolean; gesture: string; gestureAt: number; frame: Frame; canvas: HTMLCanvasElement; visible: boolean }
export const slots = new Map<string, Slot>()
// Tests freeze time and skip blinks and crossfades, so a pose is exact: <html data-mascot-freeze="0.35">. They can hold a
// blink too, seconds into it: data-mascot-blink="0.1".
export const clock = { get frozen() { const f = document.documentElement.dataset.mascotFreeze; return f ? +f : null }, get still() { return !!document.documentElement.dataset.mascotFreeze },
 get blink() { const b = document.documentElement.dataset.mascotBlink; return b ? +b : null } }
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
/// Gestures a companion plays by name (the gesture prop), besides the states. pitch is "pick me", hired a happy bounce,
/// yes a short "yes!" (each Blender companion's own clip, at chat sizes its strip; any other look the hired bounce).
export const GESTURES = ["idle", "happy", "thinking", "working", "pointing", "needs-you", "done", "sad", "talking", "wave", "admire", "pop", "wake", "drop", "pitch", "hired", "yes"] as const
export function loadEngine() {
 return loading ??= import("./companion3d").then(async m => { await m.load(); m.start(); engine = m; m.onRigReady(() => { changed(); drain() }); changed(); drain(); return m })
  .catch(e => { console.error("The companion couldn't load", e); return null })
}

// ---------------------------------------------------------------- still pictures

const bundled = import.meta.glob("./assets/companion/*.webp", { eager: true, import: "default" }) as Record<string, string>
const PRESETS = Object.entries({ default: DEFAULT_LOOK, blank: BLANK, ...AGENT_LOOKS }).map(([k, l]) => [k, lookKey(l)] as const)
const pictureState = (s: MascotState): MascotState => s === "listening" || s === "talking" ? "idle" : s
const hash = (s: string) => { let h = 5381; for (let i = 0; i < s.length; i++) h = (h * 33 ^ s.charCodeAt(i)) >>> 0; return h.toString(36) }
const memo = new Map<string, string>()
const wanted = new Map<string, { look: Look; state: MascotState; px: number; frame: Frame; flat: boolean }>()
const STORE = "still.picture4." // 4: real props (3: bigger faces); pictures kept from before are dropped
try { for (const k of Object.keys(localStorage)) if (k.startsWith("still.picture") && !k.startsWith(STORE)) localStorage.removeItem(k) } catch { /* no storage */ }

function drain() {
 if (!engine || !wanted.size) return
 for (const [key, w] of wanted) {
  try {
   const url = engine.picture(w.look, w.state, w.px, w.frame, w.flat)
   if (!url) continue // its model is still loading: drawn when it's in
   wanted.delete(key); memo.set(key, url)
   try {
    if (localStorage.length > 400) for (const k of Object.keys(localStorage)) if (k.startsWith(STORE)) localStorage.removeItem(k)
    localStorage.setItem(STORE + key, url)
   } catch { /* storage full or off: the picture lives until the window closes */ }
  } catch (e) { wanted.delete(key); console.error(e) }
 }
 changed()
}

/// A still picture of a look in a state: rendered once (loading the engine if it must), then kept. flat: drawn 2D.
export function pictureOf(look: Look, state: MascotState, px: number, frame: Frame, render = true, flat = false): string | undefined {
 state = pictureState(state)
 const lk = lookKey(look), key = `${px}${frame[0]}${flat ? "f" : ""}-${state}-${hash(lk)}`, head = frame === "icon" || frame === "portrait"
 const preset = PRESETS.find(p => p[1] === lk)?.[0]
 const shipped = preset && bundled[`./assets/companion/${preset}-${head ? frame : flat ? "flat" : frame}-${state}.webp`] // the default look's idle, 2D and its heads too
 if (shipped) return shipped
 let url = memo.get(key)
 if (!url) try { url = localStorage.getItem(STORE + key) ?? undefined; if (url) memo.set(key, url) } catch { /* no storage */ }
 if (url || !render || !webgl) return url ?? (head ? undefined : bundled[`./assets/companion/default-${flat ? "flat" : frame}-idle.webp`]) // no WebGL: the default look, drawn ahead (a head: its initial)
 if (!wanted.has(key)) { wanted.set(key, { look, state, px, frame, flat }); if (engine) queueMicrotask(drain); else void loadEngine() }
 return undefined
}

// Chat sizes (48px and under: chat turns, mentions, handoff cards, tabs, the companion switcher, headers, menus) are 2D:
// the same model drawn flat, each part in its own color, with a bold outline, so the face reads at 32px. Each role's
// look and Make your own's are rendered so in Blender (rig/anim.py "flat"): avatars at 96 and 144px, and strips of its
// clips (96px, 15 fps), one per state, played by CSS. Any other look is drawn flat from the 3D model. Bigger is 3D.
export const FLAT = 48
const avatarFiles = import.meta.glob("./assets/avatar/*.png", { eager: true, import: "default" }) as Record<string, string>
const AVATAR = new Map(RIGS.map(([l, f]) => [lookKey(l), [avatarFiles[`./assets/avatar/${f}-96.png`], avatarFiles[`./assets/avatar/${f}-144.png`]]]))
const strips = import.meta.glob("./assets/sprite/*/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>
const sheets = import.meta.glob("./assets/sprite/*/*.json", { eager: true, import: "default" }) as Record<string, Record<string, { frames: number; fps: number; rows?: number }>>
const RIG = new Map(RIGS.map(([l, f]) => [lookKey(l), f]))

// Small sizes show the head, not the whole body, so the face reads: up to ICON px a simplified icon (one tone, a bolder
// outline, eyes a quarter bigger, no props), up to PORTRAIT px a head portrait in the chat look; from 40px the whole
// companion. Each is framed on the rest pose's head and circled, nothing at the box's edge. The Blender companions ship
// theirs at 1x, 2x and 3x (rig/anim.py "heads", packed to assets/head); any other look is rendered once and kept.
export type Tier = "icon" | "portrait" | "full"
export const ICON = 20, PORTRAIT = 39
export const tierOf = (size: number): Tier => size <= ICON ? "icon" : size <= PORTRAIT ? "portrait" : "full"
const headFiles = import.meta.glob("./assets/head/*.png", { eager: true, import: "default" }) as Record<string, string>
const HEAD_PX = { icon: [16, 20, 32, 40, 48, 60], portrait: [40, 80, 120] } // 16 and 32 so 16px gets a file drawn for it
/// A look's head at a tier: the shipped files as a srcset, or one picture rendered at 3x the tier's largest size.
export function headOf(look: Look, tier: "icon" | "portrait", render = true): { src: string; srcSet?: string } | undefined {
 const id = RIG.get(lookKey(look)), files = id ? HEAD_PX[tier].map(px => headFiles[`./assets/head/${id}-${tier}-${px}.png`]) : undefined
 if (files?.every(Boolean)) return { src: files[0], srcSet: files.map((f, i) => `${f} ${HEAD_PX[tier][i]}w`).join(", ") }
 const src = pictureOf(look, "idle", HEAD_PX[tier].at(-1)!, tier, render, true)
 return src ? { src } : undefined
}
/// A look's face as one picture for an <img> drawn at size px (a mention in the message box): the tier's sharpest file.
export function avatarOf(look: Look, size: number) {
 const tier = tierOf(size)
 if (tier === "full") return AVATAR.get(lookKey(look))?.[0] ?? pictureOf(look, "idle", 96, "full", true, true)
 const h = headOf(look, tier)
 return h?.srcSet ? h.srcSet.split(", ").at(-1)!.split(" ")[0] : h?.src
}
// Dark or light letters on a companion's color, whichever reads (the initial when a head picture can't be had).
const inkOn = (hex: string) => { const n = parseInt(hex.slice(1), 16), l = (c: number) => { c /= 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4 }
 return .2126 * l(n >> 16 & 255) + .7152 * l(n >> 8 & 255) + .0722 * l(n & 255) > .18 ? "#1d1b19" : "#ffffff" }
const STRIP: Partial<Record<MascotState, string>> = { working: "working", thinking: "thinking", done: "nod", error: "shrug", needs: "wave" } // the rest idle
function strip(look: Look, state: MascotState, gesture = "") {
 const id = RIG.get(lookKey(look)), clip = gesture === "yes" ? "yes" : STRIP[state] ?? "idle_a", url = strips[`./assets/sprite/${id}/${id}-${clip}.webp`], info = sheets[`./assets/sprite/${id}/${id}.json`]?.[clip]
 return url && info ? { url, clip, ...info, once: clip === "yes" || state === "done" || state === "error" } : undefined // a nod or a shrug plays once and holds
}

// ---------------------------------------------------------------- the component

export function Mascot({ look, state = "idle", size, tier: want, name = "", follow = false, gesture = "", gestureAt = 0, className, style }: {
 look: Look; state?: MascotState; size: number; tier?: Tier; name?: string; follow?: boolean; gesture?: string; gestureAt?: number; className?: string; style?: CSSProperties
}) {
 useVersion()
 const tier = want ?? tierOf(size), [broken, setBroken] = useState("")
 const head = tier !== "full" ? headOf(look, tier) : undefined
 if (tier !== "full") return <span className={cn("mascot is-head", className)} data-state={state} data-tier={tier} data-rig={RIG.get(lookKey(look))} style={{ "--s": `${size}px`, ...style } as CSSProperties} aria-hidden>
  {head && broken !== head.src ? <img src={head.src} srcSet={head.srcSet} sizes={head.srcSet && `${size}px`} alt="" draggable={false} onError={() => setBroken(head.src)} />
   : <i className="mascot-initial" style={{ background: look.color, color: inkOn(look.color) }}>{name.trim().charAt(0).toUpperCase()}</i>}
 </span>
 return <Body look={look} state={state} size={size} follow={follow} gesture={gesture} gestureAt={gestureAt} className={className} style={style} />
}

/// The whole companion (40px and up): 2D at chat sizes, live 3D when bigger.
function Body({ look, state, size, follow, gesture, gestureAt, className, style }: {
 look: Look; state: MascotState; size: number; follow: boolean; gesture: string; gestureAt: number; className?: string; style?: CSSProperties
}) {
 const id = useId()
 const ref = useRef<HTMLCanvasElement>(null)
 const reduced = useReduced()
 const flat = size <= FLAT
 const [played, setPlayed] = useState(0) // the gestureAt whose "yes" strip has played: then back to the state's
 const avatar = flat ? AVATAR.get(lookKey(look)) : undefined, sprite = avatar && strip(look, state, gestureAt !== played ? gesture : "")
 const live = webgl && !reduced && (!flat || !!gesture) && !avatar
 const frame: Frame = "full" // the whole body at every size, never a crop
 const px = Math.min(768, Math.round(size * Math.min(devicePixelRatio || 1, 2)))
 const picture = avatar ? undefined : pictureOf(look, state, flat ? 96 : 384, frame, !live, flat)
 useEffect(() => {
  const canvas = ref.current
  if (!live || !canvas) return
  slots.set(id, { id, look, state, follow, gesture, gestureAt, frame, canvas, visible: false })
  seen.observe(canvas)
  changed()
  return () => { seen.unobserve(canvas); slots.delete(id); delete canvas.dataset.live; changed() }
 }, [live, id]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { const s = slots.get(id); if (s) Object.assign(s, { look, state, follow, gesture, gestureAt, frame }) }, [id, look, state, follow, gesture, gestureAt, frame])
 return <span className={cn("mascot", avatar && "is-avatar", flat && "is-flat", className)} data-state={state} data-rig={RIG.get(lookKey(look))} style={{ "--s": `${size}px`, ...style } as CSSProperties} aria-hidden>
  {sprite ? <span key={sprite.url + (sprite.clip === "yes" ? gestureAt : "")} onAnimationEnd={sprite.clip === "yes" ? () => setPlayed(gestureAt) : undefined} className={cn("mascot-sprite", sprite.once && "is-once", sprite.rows && "is-rows")} style={{ backgroundImage: `url(${sprite.url})`, "--n": sprite.frames, "--d": `${sprite.frames / sprite.fps}s`, "--r": sprite.rows, "--c": sprite.rows && sprite.frames / sprite.rows } as CSSProperties} />
   : avatar && <img src={avatar[0]} srcSet={`${avatar[0]} 96w, ${avatar[1]} 144w`} sizes={`${size}px`} alt="" draggable={false} />}
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
