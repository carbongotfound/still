import { createContext, useContext, type CSSProperties } from "react"
import { cn } from "@/lib/utils"

// Companion faces: Microsoft's Fluent Emoji 3D artwork (MIT license, see Licenses/fluentui-emoji), on a soft color.
const files = import.meta.glob("./assets/faces/*.webp", { eager: true, import: "default" }) as Record<string, string>
export const FACES: Record<string, string> = Object.fromEntries(Object.entries(files).map(([path, url]) => [path.split("/").pop()!.replace(".webp", ""), url]))
export const FACE_NAMES = Object.keys(FACES).sort()
export const COLORS = ["sky", "mint", "peach", "lilac", "sand", "rose", "lemon", "slate"]
export const NAMES = ["Pip", "Hazel", "Rio", "Juno", "Milo", "Wren", "Otis", "Nova", "Bea", "Kit", "Moss", "Sol", "Fern", "Ivo", "Lumi", "Tate", "Ada", "Bo"]

export type Companion = { id: string; name: string; face: string; color: string; job: string }
export type Mood = "idle" | "think" | "happy" | "sleep"
export const FALLBACK: Companion = { id: "pip", name: "Pip", face: "robot", color: "sky", job: "" }
// The companion the user is working with, for faces that don't name one.
export const CompanionContext = createContext<Companion | undefined>(undefined)

export function Face({ companion, mood = "idle", size = 56, className }: { companion?: Companion; mood?: Mood; size?: number; className?: string }) {
 const fallback = useContext(CompanionContext)
 const c = companion ?? fallback ?? FALLBACK
 return <span className={cn("face", className)} data-mood={mood} data-big={size >= 48 || undefined} data-color={COLORS.includes(c.color) ? c.color : "sky"} style={{ "--s": `${size}px` } as CSSProperties} aria-hidden>
  <img src={FACES[c.face] ?? FACES.robot} alt="" draggable={false} />
 </span>
}
export const Buddy = Face
