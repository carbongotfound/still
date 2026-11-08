import { createContext, useContext, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { motion } from "motion/react"
import { Mascot, pictureOf, useMascotVersion, type MascotState, type Tier } from "./Mascot"
import { AGENT_LOOKS, DEFAULT_LOOK, ROLE_LOOKS, ROLE_PROPS, isOld, parseLook, type Look } from "./look"

// The old companion hues: a companion saved before looks existed keeps its color.
export const HUES: Record<string, string> = { sage: "#8fbf8a", lavender: "#a99be0", apricot: "#f4c2a8", mint: "#9ed8c6", blush: "#f3b7c1", periwinkle: "#b8c4f0", berry: "#e58fa8", ocean: "#8fb8e8" }
const BEFORE: Record<string, string> = { sky: "ocean", peach: "apricot", lilac: "lavender", sand: "sage", rose: "blush", lemon: "apricot", slate: "periwinkle" }

export type Mode = "efficient" | "default" | "expert"
export type Companion = { id: string; name: string; face: string; color: string; job: string; ai?: string; mode?: Mode; skills?: string[]; memory?: Fact[]; summaries?: ChatSummary[]; knowledge?: Note[]; setup?: "pending" | "done"; capture?: boolean; joinSection?: boolean; tone?: string; role?: string; personality?: Personality; length?: ReplyLength; folder?: string; look?: string; pluginsOff?: string[]; routines?: Routine[]
 crew?: string // the crew member it was picked from (crew.tsx)
 askName?: boolean } // it still has a name Still used to hand out: ask once whether to keep it
/// A companion's personality preset ("" = only its Tone in the user's words) and how long its replies are.
export type Personality = "" | "direct" | "warm" | "playful" | "formal"
export type ReplyLength = "short" | "balanced" | "detailed"
/// Something a companion does on a schedule, in a new chat: days are 0 (Sunday) to 6, time is HH:MM on this PC's clock.
export type Routine = { id: string; text: string; time: string; days: number[]; on: boolean }
/// One of a companion's knowledge files (still/Assets/roles/<role>/knowledge): the working notes of its job, filled in as it works.
export type Note = { id: string; name: string; about: string; text: string; version?: string; updated?: string; revisions?: number }
/// One thing a companion remembers about the user, with where it came from. A superseded one is an earlier version.
export type Fact = { id: string; text: string; kind: string; at: string; chat: string; msg?: number; key?: string; chatTitle?: string | null; guessed?: boolean
 source?: string; sourceText?: string; subject?: string; status?: "active" | "superseded"; supersedes?: string }
/// A past chat's summary in a companion's memory. legacy: a line from before 2.10, never checked against the chat.
export type ChatSummary = { chat: string; title: string; at: string; legacy?: boolean; text: string; exists?: boolean }
export type Mood = MascotState | "sleep"
export const FALLBACK: Companion = { id: "", name: "Still", face: "", color: "", job: "" }
// The companion the user is working with, for faces that don't name one.
export const CompanionContext = createContext<Companion | undefined>(undefined)

// Another AI app working in Still wears its maker's look, when there is one.
export const agentFace = (name = "") => /claude/i.test(name) ? "claude" : /gpt|openai|codex/i.test(name) ? "chatgpt" : /grok/i.test(name) ? "grok" : ""
const own = <T,>(table: Record<string, T>, key?: string) => key != null && Object.hasOwn(table, key) ? table[key] : undefined // a pasted "constructor" isn't a look
export function lookOf(c?: Companion): Look {
 if (!c) return DEFAULT_LOOK
 if (c.look) { // a role's companion saved before the blobs, or holding the prop its role had, gets the role's own look
  const role = own(ROLE_LOOKS, c.crew)
  if (role) try {
   const o = JSON.parse(c.look)
   if (isOld(o)) return role
   if (o.color === role.color && o.shape === role.shape && o.prop === ROLE_PROPS[c.crew!]) return parseLook({ ...o, prop: "" })
  } catch { /* not JSON: parseLook falls back */ }
  return parseLook(c.look)
 }
 const look = own(ROLE_LOOKS, c.crew) ?? (c.id ? undefined : own(AGENT_LOOKS, c.face))
 if (look) return look
 const hue = own(HUES, c.color) ?? own(HUES, own(BEFORE, c.color))
 return hue ? { ...DEFAULT_LOOK, color: hue } : DEFAULT_LOOK
}
/// The companion's color, used as its accent while you work with it.
export const hueOf = (c?: Companion) => lookOf(c).color

export function Face({ companion, mood = "idle", size = 56, tier, follow, gesture, gestureAt, className }: { companion?: Companion; mood?: Mood; size?: number; tier?: Tier; follow?: boolean; gesture?: string; gestureAt?: number; className?: string }) {
 const fallback = useContext(CompanionContext)
 const c = companion ?? fallback
 const look = useMemo(() => lookOf(c), [c?.look, c?.color, c?.face, c?.id]) // eslint-disable-line react-hooks/exhaustive-deps
 return <Mascot look={look} state={mood === "sleep" ? "idle" : mood} size={size} tier={tier} name={c?.name} follow={follow} gesture={gesture} gestureAt={gestureAt}
  className={className} style={mood === "sleep" ? { filter: "saturate(.4)", opacity: .85 } : undefined} />
}
export const Buddy = Face

/// Home's space: the companion you work with, live (its body about a fifth of the view's height, 120 to 192px), and the rest of the
/// team behind it, smaller, as still pictures; a teammate picks it. The view is the scrolling page it stands in.
const FILL = .6 // a body's share of its canvas: the frame clears every clip's reach and hop
// Picking a teammate swaps places: it grows into the middle while the last one shrinks back into the row.
const SWAP = { duration: .5, ease: [.22, 1, .36, 1] as const }
export function Space({ companion, team = [], mood, onOpen, onPick }: { companion: Companion; team?: Companion[]; mood: Mood; onOpen: () => void; onPick: (id: string) => void }) {
 const ref = useRef<HTMLDivElement>(null), [view, setView] = useState(innerHeight - 100)
 useEffect(() => {
  const page = ref.current?.closest(".home-main"); if (!page) return
  const o = new ResizeObserver(() => setView(page.clientHeight)); o.observe(page); return () => o.disconnect()
 }, [])
 useMascotVersion()
 const size = Math.round(Math.min(320, Math.max(200, view * .2 / FILL))), rest = team.filter(c => c.id !== companion.id).slice(0, 4)
 return <div ref={ref} className="space" style={{ "--s": `${size}px` } as CSSProperties}>
  {rest.map((c, i) => { const url = pictureOf(lookOf(c), "idle", 384, "full"); return <motion.button key={c.id} layoutId={"space-" + c.id} transition={SWAP} type="button" className="space-mate" data-at={i} title={c.name} aria-label={`Work with ${c.name}`} onClick={() => onPick(c.id)}>{url && <img src={url} alt="" draggable={false} />}</motion.button> })}
  <motion.button key={companion.id} layoutId={"space-" + companion.id} transition={SWAP} type="button" className="profile-open home-face" aria-label={`${companion.name}'s profile`} onClick={onOpen}><Face companion={companion} size={size} follow mood={mood} /></motion.button>
 </div>
}
/// Opens a companion's profile (App listens), from any of its mascots.
/// A companion's profile, from anywhere: on its General tab, or "model" for their AI settings.
export const showProfile = (c?: Companion, tab = "general") => { if (c?.id) dispatchEvent(new CustomEvent("still-profile", { detail: { id: c.id, tab } })) }
