import { useId, type CSSProperties } from "react"
import { cn } from "@/lib/utils"

export type Mood = "idle" | "think" | "happy" | "sleep"

// Still's face: a smooth little pebble, calm like the name. It blinks, looks around while the AI works,
// beams when it's done and dozes in private tabs. Small faces drop the cheeks and mouth so they stay crisp.
export function Buddy({ mood = "idle", size = 56, className }: { mood?: Mood; size?: number; className?: string }) {
 const id = "buddy" + useId().replace(/[^\w]/g, ""), small = size < 28
 const eyes = mood === "happy" ? <g className="buddy-eyes is-lines"><path d="M19.5 34q4.5-5.5 9 0" /><path d="M35.5 34q4.5-5.5 9 0" /></g>
  : mood === "sleep" ? <g className="buddy-eyes is-lines"><path d="M19.5 32.5q4.5 4 9 0" /><path d="M35.5 32.5q4.5 4 9 0" /></g>
  : <g className="buddy-eyes"><ellipse cx="24" cy="32" rx={small ? 4.2 : 3.7} ry={small ? 5.6 : 5.1} /><ellipse cx="40" cy="32" rx={small ? 4.2 : 3.7} ry={small ? 5.6 : 5.1} />
   {!small && <><circle className="buddy-glint" cx="25.4" cy="29.6" r="1.35" /><circle className="buddy-glint" cx="41.4" cy="29.6" r="1.35" /></>}</g>
 return <svg className={cn("buddy", className)} data-mood={mood} data-small={small || undefined} style={{ "--s": `${size}px` } as CSSProperties} width={size} height={size} viewBox="0 0 64 64" aria-hidden>
  <defs><radialGradient id={id} cx=".34" cy=".28" r=".85"><stop offset="0" style={{ stopColor: "var(--buddy-hi)" }} /><stop offset=".5" style={{ stopColor: "var(--buddy)" }} /><stop offset="1" style={{ stopColor: "var(--buddy-lo)" }} /></radialGradient></defs>
  <g className="buddy-body">
   <path d="M33 7c15 0 26 10 26 26 0 15-11 25-27 25S5 48 5 33C5 17 17 7 33 7z" fill={`url(#${id})`} />
   {!small && <><ellipse className="buddy-cheek" cx="16" cy="40.5" rx="4.4" ry="2.7" /><ellipse className="buddy-cheek" cx="48" cy="40.5" rx="4.4" ry="2.7" /></>}
   {eyes}
   {!small && <path className="buddy-mouth" d={mood === "happy" ? "M26.5 41q5.5 6 11 0" : mood === "think" ? "M30 43.5h4.5" : mood === "sleep" ? "M30.5 43q1.5 1 3 0" : "M28.8 41.6q3.2 2.8 6.4 0"} />}
  </g>
 </svg>
}
