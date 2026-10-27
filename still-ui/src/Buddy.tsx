import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"

export type Mood = "idle" | "think" | "happy" | "sleep"

// Still's face: the two bars of the logo are its eyes. It blinks, looks around while the AI works and hops when it's done.
export function Buddy({ mood = "idle", size = 56, className }: { mood?: Mood; size?: number; className?: string }) {
 return <span className={cn("buddy", className)} data-mood={mood} style={{ "--s": `${size}px` } as CSSProperties} aria-hidden><i /><i /></span>
}
