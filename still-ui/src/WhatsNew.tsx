import { useEffect, useRef, useState, type PointerEvent } from "react"
import { AnimatePresence, motion } from "motion/react"
import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import NOTES from "./whatsnew.json"

// What's New: a few highlights of this release, once after an update, and again from About. Each release adds its
// entries to whatsnew.json and its screenshots to public/whatsnew/<release>/; nothing else changes.
type Note = { title: string; text: string; image: string }
const ALL = NOTES as Record<string, Note[]>
export const FEATURES_URL = "https://github.com/carbongotfound/still/blob/main/FEATURES.md"
/// "2.10" for 2.10.3, the key in whatsnew.json.
export const releaseOf = (version?: string) => (version ?? "").split(".").slice(0, 2).join(".")
export const notesFor = (version?: string) => ALL[releaseOf(version)]

type Shown = { version?: string; seenVersion?: string; welcome?: boolean; secondary?: boolean; incognito?: boolean }
export function WhatsNew({ state, open, setOpen, send }: { state: Shown; open: boolean; setOpen: (v: boolean) => void; send: (op: string, payload?: Record<string, unknown>) => void }) {
 const release = releaseOf(state.version), notes = ALL[release]
 const due = !!notes?.length && state.seenVersion !== undefined && state.seenVersion !== release && !state.welcome && !state.secondary && !state.incognito
 const [at, setAt] = useState(0), [dir, setDir] = useState(1)
 const [tilt, setTilt] = useState({ x: 0, y: 0 })
 const down = useRef<number | null>(null)
 useEffect(() => { if (due) { setAt(0); setOpen(true) } }, [due, setOpen])
 if (!notes?.length) return null
 const go = (d: number) => { const n = Math.max(0, Math.min(notes.length - 1, at + d)); if (n !== at) { setDir(d); setAt(n) } }
 const close = () => { setOpen(false); if (due) send("whatsNewSeen") }
 const note = notes[at]
 const lean = (e: PointerEvent<HTMLDivElement>) => { const r = e.currentTarget.getBoundingClientRect(); setTilt({ x: (e.clientX - r.left) / r.width - .5, y: (e.clientY - r.top) / r.height - .5 }) }
 return <Dialog open={open} onOpenChange={o => { if (!o) close() }}>
  <DialogContent className="whatsnew" showCloseButton={false} onKeyDown={e => { if (e.key === "ArrowRight") go(1); if (e.key === "ArrowLeft") go(-1) }}>
   <p className="whatsnew-kicker">What's new in Still {release}</p>
   <div className="whatsnew-stage" onPointerMove={lean} onPointerLeave={() => setTilt({ x: 0, y: 0 })}
    onPointerDown={e => { down.current = e.clientX }} onPointerUp={e => { if (down.current !== null && Math.abs(e.clientX - down.current) > 40) go(e.clientX < down.current ? 1 : -1); down.current = null }}>
    <AnimatePresence mode="popLayout" initial={false} custom={dir}>
     <motion.figure key={at} className="whatsnew-card" custom={dir}
      initial={{ opacity: 0, rotateY: dir * 28, x: dir * 60 }} animate={{ opacity: 1, rotateY: tilt.x * 10, rotateX: -tilt.y * 8, x: 0 }} exit={{ opacity: 0, rotateY: dir * -28, x: dir * -60 }}
      transition={{ type: "spring", stiffness: 260, damping: 28 }}>
      <img src={"./whatsnew/" + note.image} alt={note.title} draggable={false} />
     </motion.figure>
    </AnimatePresence>
   </div>
   <DialogTitle className="whatsnew-title">{note.title}</DialogTitle>
   <DialogDescription className="whatsnew-text">{note.text}</DialogDescription>
   <div className="whatsnew-nav">
    <Button variant="ghost" size="icon-sm" aria-label="Previous" disabled={at === 0} onClick={() => go(-1)}><ChevronLeft /></Button>
    <div className="whatsnew-dots" role="tablist" aria-label="Highlights">{notes.map((n, i) =>
     <button key={n.title} role="tab" aria-selected={i === at} aria-label={n.title} onClick={() => { setDir(i > at ? 1 : -1); setAt(i) }} />)}</div>
    <Button variant="ghost" size="icon-sm" aria-label="Next" disabled={at === notes.length - 1} onClick={() => go(1)}><ChevronRight /></Button>
   </div>
   <div className="whatsnew-foot">
    <Button variant="ghost" size="sm" onClick={() => { send("new", { url: FEATURES_URL }); close() }}>See everything<ExternalLink /></Button>
    <Button size="sm" onClick={close}>Close</Button>
   </div>
  </DialogContent>
 </Dialog>
}
