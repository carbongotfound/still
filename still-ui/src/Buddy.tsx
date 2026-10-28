import { createContext, useContext, type CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { KINDS, Mascot, isKind, type Kind, type MascotState } from "./Mascot"

// Companion faces are Still's own 3D mascots (see Mascot.tsx), on a soft tint of the companion's hue when small.
export const FACE_NAMES: string[] = [...KINDS]
// The eight companion hues. A companion's hue tints its face and is the accent while you work with it.
export const HUES: Record<string, string> = { sage: "#5c7a76", lavender: "#8f80aa", apricot: "#e8a76c", mint: "#8fcbbc", blush: "#f2a487", periwinkle: "#bbadea", berry: "#ed5a31", ocean: "#4f7cf0" }
export const COLORS = Object.keys(HUES)
const BEFORE: Record<string, string> = { sky: "ocean", peach: "apricot", lilac: "lavender", sand: "sage", rose: "blush", lemon: "apricot", slate: "periwinkle" } // the old color names
export const hueOf = (c?: { color: string }) => HUES[c?.color ?? ""] ?? HUES[BEFORE[c?.color ?? ""]] ?? HUES.ocean
export const NAMES = ["Pip", "Hazel", "Rio", "Juno", "Milo", "Wren", "Otis", "Nova", "Bea", "Kit", "Moss", "Sol", "Fern", "Ivo", "Lumi", "Tate", "Ada", "Bo"]

export type Mode = "efficient" | "default" | "expert"
export type Companion = { id: string; name: string; face: string; color: string; job: string; ai?: string; mode?: Mode; skills?: string[]; memory?: string; folder?: string }
export type Mood = MascotState | "sleep"
export const FALLBACK: Companion = { id: "pip", name: "Pip", face: "", color: "ocean", job: "" }
// The companion the user is working with, for faces that don't name one.
export const CompanionContext = createContext<Companion | undefined>(undefined)
// The AI the chat in view runs on: a companion without a mascot of its own wears that AI's.
export const ProviderContext = createContext<Kind>("claude")

// Another AI app working in Still wears its maker's mascot, when there is one.
export const agentFace = (name = "") => /claude/i.test(name) ? "claude" : /gpt|openai|codex/i.test(name) ? "chatgpt" : /grok/i.test(name) ? "grok" : ""

export function Face({ companion, mood = "idle", size = 56, look, className }: { companion?: Companion; mood?: Mood; size?: number; look?: boolean; className?: string }) {
 const fallback = useContext(CompanionContext), provider = useContext(ProviderContext)
 const c = companion ?? fallback ?? FALLBACK
 return <span className={cn("face", className)} data-mood={mood} data-big={size >= 48 || undefined} style={{ "--s": `${size}px`, "--hue": hueOf(c) } as CSSProperties} aria-hidden>
  <Mascot kind={isKind(c.face) ? c.face : provider} state={mood === "sleep" ? "idle" : mood} size={size} look={look} />
 </span>
}
export const Buddy = Face
