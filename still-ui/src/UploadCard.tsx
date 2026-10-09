import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { motion, useReducedMotion } from "motion/react"
import { Check, FileText, FolderOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type Upload = { id: string; multiple: boolean; anchor: number[] | null; files: { id: number; name: string; type: string; copied: boolean; thumb: string | null }[] }
type Send = (op: string, payload?: Record<string, unknown>) => void

// A site's upload button opens this card under it: a bar of recent files the site takes, the copied image first,
// then "Open a file".
export function UploadCard({ upload, send }: { upload: Upload; send: Send }) {
 const reduced = useReducedMotion()
 const ref = useRef<HTMLDivElement>(null)
 const [picked, setPicked] = useState<number[]>([])
 const [place, setPlace] = useState<{ left: number; top: number; below: boolean }>()
 const answer = (extra: Record<string, unknown>) => send("uploadAnswer", { id: upload.id, ...extra })
 useEffect(() => setPicked([]), [upload.id])
 useLayoutEffect(() => {
  const card = ref.current; if (!card) return
  const w = card.offsetWidth, h = card.offsetHeight, gap = 8
  const [x, y, , bh] = upload.anchor ?? [(innerWidth - w) / 2, 96, w, 0]
  const below = y + bh + gap + h <= innerHeight - gap || y - gap - h < gap
  setPlace({ left: Math.min(Math.max(x, gap), innerWidth - w - gap), top: below ? Math.min(y + bh + gap, innerHeight - h - gap) : y - gap - h, below })
 }, [upload.anchor, upload.files.length, upload.id])
 useEffect(() => {
  const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); answer({}) } }
  addEventListener("keydown", key); return () => removeEventListener("keydown", key)
 })
 const pick = (id: number) => upload.multiple ? setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]) : answer({ picked: [id] })
 return <div className="upload-backdrop" onPointerDown={e => { if (e.target === e.currentTarget) answer({}) }}>
  <motion.div ref={ref} role="dialog" aria-label="Choose a file to upload" className="upload-card"
   style={{ left: place?.left ?? -9999, top: place?.top ?? -9999, transformOrigin: place?.below === false ? "bottom left" : "top left" }}
   initial={{ opacity: 0, scale: reduced ? 1 : .96, y: reduced ? 0 : place?.below === false ? 4 : -4 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ duration: reduced ? .01 : .18, ease: [.22, 1, .36, 1] }}>
   <div className="upload-row">
   <div className="upload-bar" onWheel={e => { if (!e.deltaX) e.currentTarget.scrollLeft += e.deltaY }}>
    {upload.files.map(f => <button key={f.id} className={cn("upload-tile", f.thumb && "has-thumb", picked.includes(f.id) && "is-picked")} onClick={() => pick(f.id)} title={f.name} aria-pressed={upload.multiple ? picked.includes(f.id) : undefined}>
     {f.thumb ? <img src={f.thumb} alt="" draggable={false} /> : <span className="upload-file"><FileText /><b>{f.type || "FILE"}</b></span>}
     <span className="upload-name">{f.copied ? "Copied" : f.name}</span>
     {picked.includes(f.id) && <i><Check /></i>}
    </button>)}
   </div>
    <button className="upload-tile is-open" onClick={() => answer({ browse: true })}><span className="upload-file"><FolderOpen /></span><span className="upload-name">Open a file…</span></button>
   </div>
   {upload.multiple && picked.length > 0 && <div className="upload-foot"><Button size="sm" onClick={() => answer({ picked })}>Add {picked.length}</Button></div>}
  </motion.div>
 </div>
}
