import { useState, type CSSProperties, type ReactNode } from "react"
import { Ban, Dices } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { lookOf, type Companion } from "./Buddy"
import { ACCESSORIES, BODY_COLORS, PROPS, SHAPES, lookKey, surprise, type Look } from "./look"
import { Mascot, pictureOf, useMascotVersion, type Frame } from "./Mascot"

// Customize: a big live preview that reacts to each change, and the blob's color, shape, prop and a small extra in tabs.
// The props are shown as themselves, big, as Blender drew them (rig/props.py).
const PROP_ART = import.meta.glob("./assets/prop/*.webp", { eager: true, import: "default" }) as Record<string, string>
const TABS = [["color", "Color"], ["shape", "Shape"], ["prop", "Prop"], ["extra", "Extras"]] as const
type Tab = (typeof TABS)[number][0]

/// The color swatches, as a radio group.
export function Swatches({ value, onPick, label = "Body color", list = BODY_COLORS, small }: { value: string; onPick: (hex: string) => void; label?: string; list?: [string, string][]; small?: boolean }) {
 return <div className={cn("look-colors", small && "is-small")} role="radiogroup" aria-label={label}>{list.map(([hex, name]) =>
  <button type="button" key={hex} role="radio" aria-checked={value === hex} aria-label={name} title={name} style={{ "--swatch": hex } as CSSProperties} className={cn(value === hex && "is-picked")} onClick={() => onPick(hex)} />)}</div>
}

/// A still picture of the look with one part changed, or a spinner while it's drawn.
export function LookThumb({ look, frame = "full" }: { look: Look; frame?: Frame }) {
 useMascotVersion()
 const url = pictureOf(look, "idle", 96, frame)
 return url ? <img src={url} alt="" draggable={false} /> : <i className="look-loading" />
}

export function LookEditor({ companion, onClose, onSave }: { companion: Companion; onClose: () => void; onSave: (look: string) => void }) {
 const [look, setLook] = useState(() => lookOf(companion))
 const [tab, setTab] = useState<Tab>("color")
 const [nudge, setNudge] = useState(0)
 const set = (patch: Partial<Look>) => { setLook(l => ({ ...l, ...patch })); setNudge(n => n + 1) }
 const grid = (label: string, list: [string, string][], key: keyof Look, frame: Frame = "full") =>
  <div className="look-grid is-3d" role="radiogroup" aria-label={label}>{list.map(([k, name]) =>
   <button type="button" key={k || "none"} role="radio" aria-checked={look[key] === k} aria-label={name} title={name} className={cn("look-option", look[key] === k && "is-picked")} onClick={() => set({ [key]: k })}>
    <LookThumb look={{ ...look, [key]: k }} frame={frame} /><small>{name}</small></button>)}</div>
 const body: Record<Tab, ReactNode> = {
  color: <Swatches value={look.color} onPick={hex => set({ color: hex })} />,
  shape: grid("Shape", SHAPES, "shape"),
  prop: <div className="look-grid is-props" role="radiogroup" aria-label="Prop">{PROPS.map(([k, name]) =>
   <button type="button" key={k || "none"} role="radio" aria-checked={look.prop === k} aria-label={name} title={name} className={cn("look-option", look.prop === k && "is-picked")} onClick={() => set({ prop: k })}>
    {k ? <img src={PROP_ART[`./assets/prop/${k}.webp`]} alt="" draggable={false} /> : <Ban className="look-none" />}<small>{name}</small></button>)}</div>,
  extra: grid("Extras", ACCESSORIES, "accessory", "bust"),
 }
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog look-dialog" style={{ "--hue": look.color } as CSSProperties}>
   <DialogHeader className="sr-only"><DialogTitle>Customize {companion.name || "your companion"}</DialogTitle><DialogDescription>Pick a color, a shape, something to hold and a small extra.</DialogDescription></DialogHeader>
   <div className="look-stage">
    <Mascot look={look} size={280} follow gesture={nudge ? "admire" : ""} gestureAt={nudge} />
    <b>{companion.name || "Your companion"}</b>
    <Button type="button" variant="outline" size="sm" onClick={() => set(surprise())}><Dices />Surprise me</Button>
   </div>
   <div className="look-panel">
    <div className="look-tabs" role="tablist">{TABS.map(([k, label]) => <button type="button" key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>)}</div>
    <div className="look-body" role="tabpanel" aria-label={TABS.find(t => t[0] === tab)![1]}>{body[tab]}</div>
    <div className="look-foot"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="button" className="look-save" onClick={() => onSave(lookKey(look))}>Save look</Button></div>
   </div>
  </DialogContent>
 </Dialog>
}
