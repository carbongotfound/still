import { useEffect, useLayoutEffect, useState } from "react"
import { motion } from "motion/react"
import { Button } from "@/components/ui/button"

// After setup: a few coach marks on the new tab page. Steps whose target isn't on screen are left out.
const KEY = "still.tour"
const STEPS: [string, string, (name: string) => string][] = [
 [".home-compose", "Ask here", name => `Type a question or a whole task. ${name} works in background tabs, so yours stay where you left them.`],
 [".mate-switch", "Your helpers", () => "Switch helpers or make another one. Each has its own look, job and memory."],
 [".ai-pill", "Chat about a page", () => "On any website, this opens a chat about what you're looking at."],
 [".address-bar", "Search or go", () => "Search or type an address, like any browser. Ctrl L jumps here."],
 [".home-rail", "Everything else", () => "Your chats, saved files, helpers and skills. Ctrl Shift K shows what's running."],
]
const pending = () => { try { return localStorage.getItem(KEY) === "1" } catch { return false } }
const done = () => { try { localStorage.removeItem(KEY) } catch { /* nothing to forget */ } }

export function Tour({ name, ready }: { name: string; ready: boolean }) {
 const [on, setOn] = useState(pending)
 const [i, setI] = useState(0)
 const [box, setBox] = useState<DOMRect | null>(null)
 const [, settle] = useState(0) // the home page draws after this does, later on a busy computer: look again until it has
 const steps = on && ready ? STEPS.filter(s => document.querySelector(s[0])) : []
 useEffect(() => { if (!on || !ready || steps.length) return; const t = setTimeout(() => settle(n => n + 1), 300); return () => clearTimeout(t) })
 const step = steps[i]
 useLayoutEffect(() => {
  if (!step) return
  const measure = () => setBox(document.querySelector(step[0])?.getBoundingClientRect() ?? null)
  measure(); addEventListener("resize", measure); return () => removeEventListener("resize", measure)
 }, [step?.[0]]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { if (!step) return; const esc = (e: KeyboardEvent) => { if (e.key === "Escape") stop() }; addEventListener("keydown", esc); return () => removeEventListener("keydown", esc) })
 if (!step || !box) return null
 function stop() { done(); setOn(false) }
 const pad = 6, tall = box.height > innerHeight / 2, below = !tall && box.bottom + 190 < innerHeight
 const left = tall ? box.right + 14 : Math.max(16, Math.min(innerWidth - 336, box.left + box.width / 2 - 160))
 const at = tall ? { top: Math.max(16, box.top + box.height / 2 - 80) } : below ? { top: box.bottom + 14 } : { bottom: innerHeight - box.top + 14 }
 return <div className="tour" role="dialog" aria-modal="true" aria-label="Quick tour">
  <motion.div className="tour-ring" initial={false} animate={{ left: box.left - pad, top: box.top - pad, width: box.width + pad * 2, height: box.height + pad * 2 }} transition={{ type: "spring", stiffness: 380, damping: 34 }} />
  <motion.div key={i} className="tour-card" style={{ left, ...at }} initial={{ opacity: 0, y: below ? -6 : 6 }} animate={{ opacity: 1, y: 0 }}>
   <small>{i + 1} of {steps.length}</small>
   <strong>{step[1]}</strong>
   <p>{step[2](name)}</p>
   <div><Button variant="ghost" size="sm" onClick={stop}>Skip tour</Button><span className="flex-1" />
    <Button size="sm" autoFocus onClick={() => i + 1 < steps.length ? setI(i + 1) : stop()}>{i + 1 < steps.length ? "Next" : "Done"}</Button></div>
  </motion.div>
 </div>
}
