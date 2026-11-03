import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { Dices, Lock, LockOpen, Redo2, RotateCcw, Sparkles, Undo2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { lookOf, type Companion } from "./Buddy"
import { PREMADES } from "./crew"
import {
 BODY_COLORS, EXTRAS, HOLD, EYE_SHAPES, FINISHES, FORMS, MARKINGS, MOUTHS, PROPS, SOLIDS, STARTS, TEAM_LOOKS, TOPS,
 change, hasAccent, history, isV2, lookKey, markColor, newStyle, redo, reset, surprise, undo, v2, type History, type Locks, type Look,
} from "./look"
import { Mascot, loadEngine, pictureOf, useMascotVersion, type Frame } from "./Mascot"

// Customize: a big live preview that changes with each pick, the companion at the sizes it's seen at (40, 24 and 18px,
// light and dark), and its look in tabs: where to start (curated looks, or a team look to make your own), the body,
// colors (a solid body, an optional accent, a marking only if picked, each in any color), the face, and a top feature and
// accessory. Every pick can be undone; Reset goes back to the look
// it opened with; Cancel keeps the saved look as it was. A look from before the new style is shown as it is, with Try
// the new style: nothing changes until then.
const TABS = [["start", "Start"], ["body", "Body"], ["colors", "Colors"], ["face", "Face"], ["extras", "Extras"]] as const
type Tab = (typeof TABS)[number][0]
const LOCKS: [keyof Locks, string][] = [["body", "Body"], ["colors", "Colors"], ["face", "Face"], ["feature", "Feature"]]

/// The color swatches, as a radio group: none first (its label) when the color is optional, and any color last (the
/// system's picker, its picks live while it's dragged).
export function Swatches({ value, onPick, label = "Body color", list = BODY_COLORS, small, none, custom }: { value: string; onPick: (hex: string, live?: boolean) => void; label?: string; list?: [string, string][]; small?: boolean; none?: string; custom?: boolean }) {
 const own = !!value && !list.some(([hex]) => hex === value)
 return <div className={cn("look-colors", small && "is-small")} role="radiogroup" aria-label={label}>
  {none && <button type="button" role="radio" aria-checked={!value} aria-label={none} title={none} className={cn("is-none", !value && "is-picked")} onClick={() => onPick("")} />}
  {list.map(([hex, name]) =>
  <button type="button" key={hex} role="radio" aria-checked={value === hex} aria-label={name} title={name} style={{ "--swatch": hex } as CSSProperties} className={cn(value === hex && "is-picked")} onClick={() => onPick(hex)} />)}
  {custom && <label className={cn("look-custom", own && "is-picked")} title="Any color" style={own ? { "--swatch": value } as CSSProperties : undefined}>
   <input type="color" aria-label={`${label}: any color`} value={value || "#ffffff"} onChange={e => onPick(e.target.value, true)} /></label>}
 </div>
}

/// A still picture of the look with one part changed, or a spinner while it's drawn.
export function LookThumb({ look, frame = "full" }: { look: Look; frame?: Frame }) {
 useMascotVersion()
 const url = pictureOf(look, "idle", 96, frame)
 return url ? <img src={url} alt="" draggable={false} /> : <i className="look-loading" />
}

/// The value, once it has stayed the same for ms: the option pictures and the small sizes wait for the picks to settle, so
/// the preview shows each pick at once.
function useSettled<T>(value: T, ms: number) {
 const [v, setV] = useState(value)
 useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
 return v
}

export function LookEditor({ companion, onClose, onSave }: { companion: Companion; onClose: () => void; onSave: (look: string) => void }) {
 const [saved] = useState(() => lookOf(companion))
 const [h, setH] = useState<History>(() => history(saved))
 const look = h.now, fresh = isV2(look)
 const [tab, setTab] = useState<Tab>(isV2(saved) ? "body" : "start")
 const [locks, setLocks] = useState<Locks>({})
 const [team, setTeam] = useState("") // the team look it started from: one change makes it theirs
 const [nudge, setNudge] = useState(0)
 const settled = useSettled(look, 220)
 const hadProp = !isV2(saved) && saved.prop
 useEffect(() => { void loadEngine().then(m => FORMS.forEach(([f]) => m?.preload("f-" + f))) }, []) // the five bodies load as the editor opens: a pick shows at once
 const live = useRef({ from: "", at: 0 }) // the color picker being dragged: its picks a second apart or less are one change
 const go = (next: Look, wave = true, from = "") => {
  const merge = !!from && live.current.from === from && Date.now() - live.current.at < 1000
  live.current = { from, at: Date.now() }
  setH(x => merge ? { ...x, now: next, future: [] } : change(x, next)); if (wave) setNudge(n => n + 1)
 }
 const set = (patch: Partial<Look>, from: string | false = "") => go(v2({ ...(look as Required<Look>), ...patch }), !from, from || "")
 const startFrom = (l: Look, from = "") => { go(l); setTeam(from && lookKey(l)); setTab("body") }
 const step = (f: (h: History) => History) => setH(x => f(x))
 useEffect(() => {
  const key = (e: KeyboardEvent) => {
   if (!(e.ctrlKey || e.metaKey) || (e.target as HTMLElement).closest("input, textarea")) return
   const k = e.key.toLowerCase()
   if (k === "z" && !e.shiftKey) { e.preventDefault(); step(undo) } else if (k === "y" || k === "z" && e.shiftKey) { e.preventDefault(); step(redo) }
  }
  addEventListener("keydown", key)
  return () => removeEventListener("keydown", key)
 }, [])
 const unchangedTeam = !!team && lookKey(look) === team
 const tiles = (label: string, list: [string, string][], pick: (k: string) => Look, now: string, frame: Frame = "full", className = "") =>
  <div className={cn("look-grid is-3d", className)} role="radiogroup" aria-label={label}>{list.map(([k, name]) =>
   <button type="button" key={k || "none"} role="radio" aria-checked={now === k} aria-label={name} title={name} className={cn("look-option", now === k && "is-picked")} data-option={k || "none"} onClick={() => go(pick(k))}>
    <LookThumb look={pick(k)} frame={frame} /><small>{name}</small></button>)}</div>
 const part = (key: keyof Look) => (k: string) => v2({ ...(settled.v === 2 ? settled : look) as Required<Look>, [key]: k })
 const lock = <div className="look-locks" role="group" aria-label="Keep these when you surprise">{LOCKS.map(([k, label]) =>
  <button type="button" key={k} aria-pressed={!!locks[k]} title={(locks[k] ? "Kept: " : "Keep ") + label.toLowerCase()} onClick={() => setLocks(l => ({ ...l, [k]: !l[k] }))}>{locks[k] ? <Lock /> : <LockOpen />}{label}</button>)}</div>
 const body: Record<Tab, ReactNode> = {
  start: <>
   {tiles("Starting looks", STARTS.map(([n], i) => [String(i), n]), i => STARTS[+i][1], STARTS.findIndex(([, l]) => lookKey(l) === lookKey(look)).toString())}
   <h4 className="look-heading">Start from a team look</h4>
   <p className="look-hint">A teammate's look to make your own. Change one thing, then save.</p>
   <div className="look-grid is-3d" role="radiogroup" aria-label="Team looks">{TEAM_LOOKS.map(([role, l]) => {
    const p = PREMADES.find(p => p.id === role), name = p ? `${p.role} ${p.name}` : role
    return <button type="button" key={role} role="radio" aria-checked={team === lookKey(l)} aria-label={name} title={name} className={cn("look-option", team === lookKey(l) && "is-picked")} data-team={role} onClick={() => startFrom(l, role)}>
     <LookThumb look={l} /><small>{name}</small></button>
   })}</div>
  </>,
  body: tiles("Body", FORMS, part("form"), look.form ?? ""),
  colors: <>
   <h4 className="look-heading">Body color</h4>
   <Swatches small custom list={SOLIDS} value={look.color} onPick={(c, live) => set({ color: c, second: hasAccent(look) ? look.second : c }, live && "body")} />
   <h4 className="look-heading">Accent</h4>
   <p className="look-hint">Optional. A second color for the feet and anything on top.</p>
   <Swatches small custom none="No accent" label="Accent" list={SOLIDS} value={hasAccent(look) ? look.second! : ""} onPick={(c, live) => set({ second: c || look.color }, live && "accent")} />
   <h4 className="look-heading">Marking</h4>
   {tiles("Marking", MARKINGS, part("marking"), look.marking ?? "")}
   {look.marking && look.marking !== "none" && <Swatches small custom label="Marking color" list={SOLIDS} value={markColor(look)} onPick={(c, live) => set({ mark: c }, live && "mark")} />}
   <div className="look-row" role="radiogroup" aria-label="Finish"><span>Finish</span>{FINISHES.map(([k, name]) =>
    <button type="button" key={k} role="radio" aria-checked={look.finish === k} className={cn(look.finish === k && "is-picked")} onClick={() => set({ finish: k })}>{name}</button>)}</div>
  </>,
  face: <>
   <h4 className="look-heading">Eyes</h4>
   {tiles("Eyes", EYE_SHAPES, part("eye"), look.eye ?? "", "bust", "is-face")}
   <h4 className="look-heading">Mouth</h4>
   {tiles("Mouth", MOUTHS, part("mouth"), look.mouth ?? "", "bust", "is-face")}
  </>,
  extras: <>
   <h4 className="look-heading">On top</h4>
   {tiles("On top", TOPS, part("top"), look.top ?? "", "bust", "is-face")}
   <h4 className="look-heading">Accessory</h4>
   {tiles("Accessory", EXTRAS, part("accessory"), look.accessory ?? "", "bust", "is-face")}
   {hadProp && <label className="look-check"><input type="checkbox" checked={!!look.prop} disabled={HOLD[saved.prop] === "worn"} onChange={e => set({ prop: e.target.checked ? saved.prop : "" })} />
    Keep the {(PROPS.find(([k]) => k === saved.prop)?.[1] ?? saved.prop).toLowerCase()}{HOLD[saved.prop] === "worn" ? " (stays with the classic look)" : ""}</label>}
  </>,
 }
 const sizes = (dark: boolean) => <div className={cn("look-sizes", dark && "dark")}>{[40, 24, 18].map(s => <Mascot key={s} look={settled} size={s} name={companion.name} />)}</div>
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog look-dialog" style={{ "--hue": look.color } as CSSProperties}>
   <DialogHeader className="sr-only"><DialogTitle>Customize {companion.name || "your companion"}</DialogTitle><DialogDescription>Pick where to start, a body, colors, a face, and something on top.</DialogDescription></DialogHeader>
   <div className="look-stage">
    <Mascot look={look} size={360} follow gesture={nudge ? "admire" : ""} gestureAt={nudge} />
    <b>{companion.name || "Your companion"}</b>
    <div className="look-actual" aria-label="At the sizes it's seen at">{sizes(false)}{sizes(true)}</div>
    {fresh ? <div className="look-surprise">
     <Button type="button" variant="outline" size="sm" onClick={() => go(surprise(look, locks))}><Dices />Surprise me</Button>{lock}
    </div> : <div className="look-classic">
     <p>This is the classic look. The new style has more bodies, colors and faces.</p>
     <Button type="button" variant="outline" size="sm" onClick={() => { go(newStyle(look, !!hadProp && HOLD[saved.prop] !== "worn")); setTab("body") }}><Sparkles />Try the new style</Button>
    </div>}
   </div>
   <div className="look-panel">
    <div className="look-tabs" role="tablist">{TABS.map(([k, label]) => <button type="button" key={k} role="tab" aria-selected={tab === k} disabled={!fresh && k !== "start"} onClick={() => setTab(k)}>{label}</button>)}</div>
    <div className="look-body" role="tabpanel" aria-label={TABS.find(t => t[0] === tab)![1]}>{body[tab]}</div>
    <div className="look-foot">
     <Button type="button" variant="ghost" size="icon" aria-label="Undo" title="Undo" disabled={!h.past.length} onClick={() => step(undo)}><Undo2 /></Button>
     <Button type="button" variant="ghost" size="icon" aria-label="Redo" title="Redo" disabled={!h.future.length} onClick={() => step(redo)}><Redo2 /></Button>
     <Button type="button" variant="ghost" size="sm" disabled={lookKey(look) === lookKey(saved)} onClick={() => { step(reset); setTeam("") }}><RotateCcw />Reset</Button>
     {unchangedTeam && <span className="look-hint">Change one thing to make it yours.</span>}
     <span className="ml-auto" />
     <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
     <Button type="button" className="look-save" disabled={unchangedTeam} onClick={() => onSave(lookKey(look))}>Save look</Button>
    </div>
   </div>
  </DialogContent>
 </Dialog>
}
