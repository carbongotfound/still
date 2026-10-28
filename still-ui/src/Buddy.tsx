import { createContext, useContext, type CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { KINDS, Mascot, isKind, type Kind, type MascotState } from "./Mascot"

// Companion faces are Still's own 3D mascots (see Mascot.tsx), on a soft color when small.
export const FACE_NAMES: string[] = [...KINDS]
export const COLORS = ["sky", "mint", "peach", "lilac", "sand", "rose", "lemon", "slate"]
export const NAMES = ["Pip", "Hazel", "Rio", "Juno", "Milo", "Wren", "Otis", "Nova", "Bea", "Kit", "Moss", "Sol", "Fern", "Ivo", "Lumi", "Tate", "Ada", "Bo"]

export type Companion = { id: string; name: string; face: string; color: string; job: string }
export type Mood = MascotState | "sleep"
export const FALLBACK: Companion = { id: "pip", name: "Pip", face: "", color: "sky", job: "" }
// The companion the user is working with, for faces that don't name one.
export const CompanionContext = createContext<Companion | undefined>(undefined)
// The AI the chat in view runs on: a companion without a mascot of its own wears that AI's.
export const ProviderContext = createContext<Kind>("claude")

// Another AI app working in Still wears its maker's mascot, when there is one.
export const agentFace = (name = "") => /claude/i.test(name) ? "claude" : /gpt|openai|codex/i.test(name) ? "chatgpt" : /grok/i.test(name) ? "grok" : ""

export function Face({ companion, mood = "idle", size = 56, look, className }: { companion?: Companion; mood?: Mood; size?: number; look?: boolean; className?: string }) {
 const fallback = useContext(CompanionContext), provider = useContext(ProviderContext)
 const c = companion ?? fallback ?? FALLBACK
 return <span className={cn("face", className)} data-mood={mood} data-big={size >= 48 || undefined} data-color={COLORS.includes(c.color) ? c.color : "sky"} style={{ "--s": `${size}px` } as CSSProperties} aria-hidden>
  <Mascot kind={isKind(c.face) ? c.face : provider} state={mood === "sleep" ? "idle" : mood} size={size} look={look} />
 </span>
}
export const Buddy = Face
