import { createContext, useContext, useMemo } from "react"
import { Mascot, type MascotState } from "./Mascot"
import { AGENT_LOOKS, DEFAULT_LOOK, ROLE_LOOKS, isOld, parseLook, type Look } from "./look"

// The old companion hues: a companion saved before looks existed keeps its color.
export const HUES: Record<string, string> = { sage: "#8fbf8a", lavender: "#a99be0", apricot: "#f4c2a8", mint: "#9ed8c6", blush: "#f3b7c1", periwinkle: "#b8c4f0", berry: "#e58fa8", ocean: "#8fb8e8" }
const BEFORE: Record<string, string> = { sky: "ocean", peach: "apricot", lilac: "lavender", sand: "sage", rose: "blush", lemon: "apricot", slate: "periwinkle" }

export type Mode = "efficient" | "default" | "expert"
export type Companion = { id: string; name: string; face: string; color: string; job: string; ai?: string; mode?: Mode; skills?: string[]; memory?: Fact[]; tone?: string; folder?: string; look?: string
 crew?: string // the crew member it was picked from (crew.tsx)
 askName?: boolean } // it still has a name Still used to hand out: ask once whether to keep it
/// One thing a companion remembers about the user. A "chat" is a past chat it learned from.
export type Fact = { id: string; text: string; kind: string; at: string; chat: string; key?: string; chatTitle?: string | null }
export type Mood = MascotState | "sleep"
export const FALLBACK: Companion = { id: "", name: "Still", face: "", color: "", job: "" }
// The companion the user is working with, for faces that don't name one.
export const CompanionContext = createContext<Companion | undefined>(undefined)

// Another AI app working in Still wears its maker's look, when there is one.
export const agentFace = (name = "") => /claude/i.test(name) ? "claude" : /gpt|openai|codex/i.test(name) ? "chatgpt" : /grok/i.test(name) ? "grok" : ""
export function lookOf(c?: Companion): Look {
 if (!c) return DEFAULT_LOOK
 if (c.look) { // a role's companion saved before the blobs gets the role's own look
  const role = c.crew && ROLE_LOOKS[c.crew]
  if (role) try { if (isOld(JSON.parse(c.look))) return role } catch { /* not JSON: parseLook falls back */ }
  return parseLook(c.look)
 }
 if (c.crew && ROLE_LOOKS[c.crew]) return ROLE_LOOKS[c.crew]
 if (!c.id && AGENT_LOOKS[c.face]) return AGENT_LOOKS[c.face]
 const hue = HUES[c.color] ?? HUES[BEFORE[c.color]]
 return hue ? { ...DEFAULT_LOOK, color: hue } : DEFAULT_LOOK
}
/// The companion's color, used as its accent while you work with it.
export const hueOf = (c?: Companion) => lookOf(c).color

export function Face({ companion, mood = "idle", size = 56, follow, gesture, gestureAt, className }: { companion?: Companion; mood?: Mood; size?: number; follow?: boolean; gesture?: string; gestureAt?: number; className?: string }) {
 const fallback = useContext(CompanionContext)
 const c = companion ?? fallback
 const look = useMemo(() => lookOf(c), [c?.look, c?.color, c?.face, c?.id]) // eslint-disable-line react-hooks/exhaustive-deps
 return <Mascot look={look} state={mood === "sleep" ? "idle" : mood} size={size} follow={follow} gesture={gesture} gestureAt={gestureAt}
  className={className} style={mood === "sleep" ? { filter: "saturate(.4)", opacity: .85 } : undefined} />
}
export const Buddy = Face
