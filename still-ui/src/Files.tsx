import { useEffect, useMemo, useState } from "react"
import { ArrowDown, ArrowUp, Braces, Copy, FileText, Film, FolderOpen, Image as ImageIcon, Sheet, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { Markdown } from "./Markdown"

// Files the AI saved with save_file live in the profile's Library, one folder per chat. Paths are relative to it.
export type LibFile = { path: string; name: string; size: number; saved: string; chat: string }
export type FileData = { path: string; text?: string; truncated?: boolean; error?: string }
type Send = (op: string, payload?: Record<string, unknown>) => void

export const extOf = (path: string) => path.slice(path.lastIndexOf(".") + 1).toLowerCase()
export const nameOf = (path: string) => path.slice(path.lastIndexOf("/") + 1)
const KIND: Record<string, string> = { csv: "Spreadsheet", tsv: "Spreadsheet", md: "Notes", json: "Data", txt: "Text" }
const IMAGES = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif", "heic"], VIDEOS = ["mp4", "mov", "m4v", "webm", "mkv", "avi"]
export const sizeText = (b: number) => b < 1024 ? b + " B" : b < 1 << 20 ? (b / 1024).toFixed(b < 10240 ? 1 : 0) + " KB" : (b / 1048576).toFixed(1) + " MB"
export function FileIcon({ path }: { path: string }) {
 const ext = extOf(path), Icon = ext === "csv" || ext === "tsv" ? Sheet : ext === "json" ? Braces : IMAGES.includes(ext) ? ImageIcon : VIDEOS.includes(ext) ? Film : FileText
 return <span className="file-icon" data-ext={ext}><Icon aria-hidden /></span>
}

// What a save_file call left in the chat: open it in the viewer, or find it on disk.
export function FileCard({ path, send, onOpen }: { path: string; send: Send; onOpen: (path: string) => void }) {
 const name = nameOf(path), stem = name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ")
 return <div className="file-card">
  <button className="file-card-open" onClick={() => onOpen(path)} title={"Open " + name}><FileIcon path={path} /><span><b>{stem}</b><small>{KIND[extOf(path)] ?? "File"} · {name}</small></span></button>
  <Button variant="outline" size="sm" onClick={() => send("fileShow", { path })}><FolderOpen />Show in folder</Button>
 </div>
}

// RFC 4180: quoted cells may hold the separator, quotes ("") and line breaks.
export function parseTable(text: string, sep: string) {
 const rows: string[][] = []
 let row: string[] = [], cell = "", quoted = false
 for (let i = 0; i < text.length; i++) {
  const ch = text[i]
  if (quoted) { if (ch !== '"') cell += ch; else if (text[i + 1] === '"') { cell += '"'; i++ } else quoted = false }
  else if (ch === '"' && !cell) quoted = true
  else if (ch === sep) { row.push(cell); cell = "" }
  else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = "" }
  else cell += ch
 }
 if (cell || row.length) { row.push(cell); rows.push(row) }
 return rows.filter(r => r.some(c => c.trim()))
}
const number = (s: string) => { const n = Number(s.replace(/[$€£¥,%\s]/g, "")); return s.trim() && !Number.isNaN(n) ? n : null }

// A sortable grid with a sticky header. Drag a column's right edge to widen it.
function Grid({ rows }: { rows: string[][] }) {
 const [sort, setSort] = useState<[number, 1 | -1] | null>(null)
 const [head, ...body] = rows
 const sorted = useMemo(() => !sort ? body : [...body].sort((a, b) => {
  const [col, dir] = sort, x = a[col] ?? "", y = b[col] ?? "", nx = number(x), ny = number(y)
  return dir * (nx !== null && ny !== null ? nx - ny : x.localeCompare(y, undefined, { numeric: true, sensitivity: "base" }))
 }), [body, sort]) // eslint-disable-line react-hooks/exhaustive-deps
 if (!head) return <p className="file-view-empty">This file is empty.</p>
 return <div className="csv-wrap"><table className="csv-grid">
  <thead><tr><th className="csv-n" aria-label="Row" />{head.map((h, i) => <th key={i} aria-sort={sort?.[0] === i ? (sort[1] > 0 ? "ascending" : "descending") : "none"}>
   <div className="csv-col"><button onClick={() => setSort(sort?.[0] === i && sort[1] > 0 ? [i, -1] : sort?.[0] === i ? null : [i, 1])}>{h}{sort?.[0] === i && (sort[1] > 0 ? <ArrowUp /> : <ArrowDown />)}</button></div>
  </th>)}</tr></thead>
  <tbody>{sorted.map((r, i) => <tr key={i}><td className="csv-n">{i + 1}</td>{head.map((_, j) => <td key={j} className={number(r[j] ?? "") !== null ? "is-num" : undefined}>{r[j] ?? ""}</td>)}</tr>)}</tbody>
 </table></div>
}

// The built-in viewer: a spreadsheet as a grid, notes as formatted text, anything else as it is.
export function FileViewer({ path, data, send, onClose, onLink }: { path: string; data: FileData | null; send: Send; onClose: () => void; onLink: (url: string) => void }) {
 useEffect(() => { send("fileRead", { path }) }, [path, send])
 const got = data?.path === path ? data : null
 const ext = extOf(path), text = got?.text ?? ""
 const rows = useMemo(() => ext === "csv" || ext === "tsv" ? parseTable(text, ext === "tsv" ? "\t" : ",") : null, [text, ext])
 const pretty = useMemo(() => { if (ext !== "json") return text; try { return JSON.stringify(JSON.parse(text), null, 2) } catch { return text } }, [text, ext])
 return <section className="file-view" aria-label={nameOf(path)}>
  <header className="file-view-head">
   <FileIcon path={path} /><b title={path}>{nameOf(path)}</b>{rows && rows.length > 1 && <small>{rows.length - 1} rows</small>}
   <span className="file-view-gap" />
   <Button variant="ghost" size="icon-sm" aria-label="Copy all" title="Copy all" disabled={!text} onClick={() => send("copyText", { text })}><Copy /></Button>
   <Button variant="ghost" size="icon-sm" aria-label="Show in folder" title="Show in folder" onClick={() => send("fileShow", { path })}><FolderOpen /></Button>
   <Button variant="ghost" size="icon-sm" aria-label="Close" title="Close" onClick={onClose}><X /></Button>
  </header>
  <div className="file-view-body">
   {!got ? <Spinner className="file-view-wait" /> : got.error ? <p className="file-view-empty">{got.error}</p>
    : rows ? <Grid rows={rows} /> : ext === "md" ? <div className="file-view-doc"><Markdown text={text} onLink={onLink} /></div> : <pre className="file-view-pre">{pretty}</pre>}
  </div>
  {got?.truncated && <p className="file-view-note">This shows the start of a big file. Show it in its folder to open all of it.</p>}
 </section>
}
