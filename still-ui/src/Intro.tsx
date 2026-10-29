import { useEffect, useRef, useState, type CSSProperties } from "react"
import { Volume2, VolumeX } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Look } from "./look"
import { loadEngine, Mascot } from "./Mascot"
import { play, type Playing } from "./sound"

// Still's intro, about five seconds, in step with sounds/intro.ogg and the companion's "wake" clip (tools/mascot): the
// window is dark and the companion asleep; a spark drifts in and lands in its chest at 1.0 s; it wakes, stretches and
// gives a little shake; from 3.0 s light blooms out of it and fills the window with the theme's own background; Still's
// name comes into focus below it, and it turns to wave at you. Plain CSS on one clock (App.css, "The intro"), no video.
// Reduced motion gets a short fade and no sound. A click, Space, Enter or Escape skips it.
const LENGTH = 5100, REDUCED = 1400, WAIT = 2500

export type IntroAt = { x: number; y: number; r: number } // the companion's middle and half its size, on screen

/// The dark layer and everything on it. The companion sits just above it (the welcome's own, or IntroReplay's): `live`
/// says when it's ready to wake (its engine can take a moment; the intro waits up to 2.5 s), `onStart` wakes it, and
/// `onEnd` hands back, `skipped` when it was cut short.
export function IntroLayer({ at, hue, reduced, sound, onSound, live, onStart, onEnd }: {
 at: IntroAt; hue: string; reduced: boolean; sound: boolean; onSound: (on: boolean) => void; live: () => boolean; onStart: () => void; onEnd: (skipped: boolean) => void
}) {
 const [phase, setPhase] = useState<"wait" | "on" | "out">("wait")
 const audio = useRef<Playing>(undefined)
 const ended = useRef(false)
 const end = (skipped: boolean) => {
  if (ended.current) return
  ended.current = true; audio.current?.stop(.3); setPhase("out")
  setTimeout(() => onEnd(skipped), skipped ? 350 : 0)
 }
 useEffect(() => {
  let frame = 0, timer = 0
  const asked = performance.now()
  const go = () => { setPhase("on"); onStart(); if (!reduced) audio.current = play("intro"); timer = window.setTimeout(() => end(false), reduced ? REDUCED : LENGTH) }
  const wait = () => { if (reduced || live() || performance.now() - asked > WAIT) go(); else frame = requestAnimationFrame(wait) }
  if (!reduced) void loadEngine()
  wait()
  const key = (e: KeyboardEvent) => { if (e.key === " " || e.key === "Enter" || e.key === "Escape") { e.preventDefault(); e.stopPropagation(); end(true) } }
  addEventListener("keydown", key, true)
  return () => { cancelAnimationFrame(frame); clearTimeout(timer); removeEventListener("keydown", key, true); audio.current?.stop(.1) }
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 const far = Math.hypot(Math.max(at.x, innerWidth - at.x), Math.max(at.y, innerHeight - at.y)) + 80
 const sx = at.x - Math.min(innerWidth * .3, 380), sy = at.y - Math.min(innerHeight * .34, 300) // the spark comes in from the upper left
 const path = `path("M ${sx} ${sy} Q ${at.x + at.r * 1.1} ${sy - 40} ${at.x} ${at.y + at.r * .12}")`
 return <div className={cn("intro", phase !== "wait" && "is-on", phase === "out" && "is-out", reduced && "is-reduced")} onClick={() => end(true)}
  style={{ "--x": `${at.x}px`, "--y": `${at.y}px`, "--r": `${at.r}px`, "--far": `${far}px`, "--hue": hue, "--path": path } as CSSProperties}>
  <div className="intro-dark" />
  <i className="intro-glow" /><i className="intro-ring" />
  {!reduced && [0, 1, 2].map(i => <i key={i} className="intro-spark" style={{ "--n": i } as CSSProperties} />)}
  <div className="intro-mark" aria-hidden><span className="still-mark"><i /><i /></span><b>{[..."Still"].map((ch, i) => <span key={i} style={{ "--n": i } as CSSProperties}>{ch}</span>)}</b></div>
  <button className="intro-sound" aria-pressed={!sound} aria-label="Mute" title={sound ? "Mute" : "Unmute"} onClick={e => { e.stopPropagation(); if (sound) audio.current?.stop(.2); onSound(!sound) }}>{sound ? <Volume2 /> : <VolumeX />}</button>
  <button className="intro-skip" autoFocus onClick={e => { e.stopPropagation(); end(true) }}>Skip <kbd>Space</kbd></button>
 </div>
}

/// About's "Replay the intro": the same intro over the app with your main companion, which then fades away.
export function IntroReplay({ look, sound, onSound, onDone }: { look: Look; sound: boolean; onSound: (on: boolean) => void; onDone: () => void }) {
 const [reduced] = useState(() => matchMedia("(prefers-reduced-motion: reduce)").matches)
 const [awake, setAwake] = useState(false), [leaving, setLeaving] = useState(false)
 const [gesture, setGesture] = useState<[string, number]>(["wake", Date.now()])
 const body = useRef<HTMLDivElement>(null)
 const [size] = useState(() => Math.round(Math.min(460, Math.max(200, innerHeight / 2.3))))
 const [at] = useState(() => ({ x: innerWidth / 2, y: innerHeight / 2 - 30, r: size / 2 }))
 return <div className={cn("intro-replay", leaving && "is-leaving")}>
  <IntroLayer at={at} hue={look.color} reduced={reduced} sound={sound} onSound={onSound} live={() => !!body.current?.querySelector("canvas[data-live]")} onStart={() => setAwake(true)}
   onEnd={skipped => { if (skipped) setGesture(["wave", Date.now()]); setLeaving(true); setTimeout(onDone, skipped ? 1000 : 1200) }} />
  <div ref={body} className="intro-replay-body" style={{ left: at.x - size / 2, top: at.y - size / 2, "--hue": look.color } as CSSProperties}>
   <Mascot look={look} size={size} gesture={gesture[0]} gestureAt={gesture[1]} className={cn("intro-body", awake && "is-on")} />
  </div>
 </div>
}
