import { useEffect, useRef, useState, type CSSProperties } from "react"
import { Dices } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { lookOf, type Companion } from "./Buddy"
import { drawFace, REST } from "./face"
import { BODIES, BODY_COLORS, BROWS, EYES, GLASSES, HAIR_COLORS, HAIRS, HATS, MOUTHS, SHAPES, lookKey, surprise, type Look } from "./look"
import { Mascot, pictureOf, useMascotVersion } from "./Mascot"
import { play } from "./sound"

// Customize: a big live preview that reacts to each change, and every part of the look in tabs.
const TABS = [["color", "Color"], ["eyes", "Eyes"], ["brows", "Brows"], ["mouth", "Mouth"], ["head", "Body"], ["hair", "Hair"], ["hat", "Hat"]] as const
type Tab = (typeof TABS)[number][0]

/// The face alone, flat, on a disc of the body color: quick to draw, so every style can show at once.
export function FaceSwatch({ look, size = 64 }: { look: Look; size?: number }) {
 const ref = useRef<HTMLCanvasElement>(null)
 useEffect(() => {
  const c = ref.current; if (!c) return
  const px = size * 2, g = c.getContext("2d")!
  g.clearRect(0, 0, px, px)
  g.save(); g.translate(-px * .3, -px * .32); drawFace(g, px * 1.6, look, REST); g.restore() // close on the face; drawFace clears, so the disc goes under after
  g.globalCompositeOperation = "destination-over"; g.fillStyle = look.color; g.beginPath(); g.arc(px / 2, px / 2, px / 2, 0, Math.PI * 2); g.fill(); g.globalCompositeOperation = "source-over"
 }, [look, size])
 return <canvas ref={ref} width={size * 2} height={size * 2} style={{ width: size, height: size }} aria-hidden />
}

function Slider({ label, value, onChange, min = -1, max = 1 }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number }) {
 return <label className="look-slider"><span>{label}</span>
  <input type="range" min={min} max={max} step={(max - min) / 40} value={value} onChange={e => onChange(+e.target.value)} onDoubleClick={() => onChange((min + max) / 2)} /></label>
}

export function LookEditor({ companion, onClose, onSave }: { companion: Companion; onClose: () => void; onSave: (look: string) => void }) {
 const [look, setLook] = useState(() => lookOf(companion))
 const [tab, setTab] = useState<Tab>("color")
 const [nudge, setNudge] = useState(0)
 useMascotVersion()
 const set = (patch: Partial<Look>, react = true, sound = "swap") => { setLook(l => ({ ...l, ...patch })); if (react) setNudge(n => n + 1); if (!Object.values(patch).every(v => typeof v === "number")) play(sound, { gain: .8 }) } // sliders stay silent
 // the 3D thumbnails wear the current shape and colors, with a plain face, so they stay few and cached
 const thumb = (patch: Partial<Look>) => pictureOf({ ...look, eyes: "dot", eyeGap: 0, eyeY: 0, eyeSize: 0, pupil: 0, brows: "none", mouth: "smile", mouthY: 0, mouthSize: 0, ...patch }, "idle", 96, "bust")
 const option = (picked: boolean, label: string, onClick: () => void, body: React.ReactNode, key: string) =>
  <button type="button" key={key} role="radio" aria-checked={picked} aria-label={label} title={label} className={cn("look-option", picked && "is-picked")} onClick={onClick}>{body}</button>
 const pic = (url: string | undefined) => url ? <img src={url} alt="" draggable={false} /> : <i className="look-loading" />
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog look-dialog" style={{ "--hue": look.color } as CSSProperties}>
   <DialogHeader className="sr-only"><DialogTitle>Customize {companion.name || "your companion"}</DialogTitle><DialogDescription>Pick a color, a face, a head shape and something to wear.</DialogDescription></DialogHeader>
   <div className="look-stage">
    <Mascot look={look} size={280} follow gesture={nudge ? "admire" : ""} gestureAt={nudge} />
    <b>{companion.name || "Your companion"}</b>
    <Button type="button" variant="outline" size="sm" onClick={() => set({ ...surprise(), body: look.body, glasses: look.glasses }, true, "surprise")}><Dices />Surprise me</Button>
   </div>
   <div className="look-panel">
    <div className="look-tabs" role="tablist">{TABS.map(([k, label]) => <button type="button" key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>)}</div>
    <div className="look-body" role="tabpanel" aria-label={TABS.find(t => t[0] === tab)![1]}>
     {tab === "color" && <>
      <div className="look-colors" role="radiogroup" aria-label="Body color">{BODY_COLORS.map(([hex, name]) => <button type="button" key={hex} role="radio" aria-checked={look.color === hex} aria-label={name} title={name} style={{ "--swatch": hex } as CSSProperties} className={cn(look.color === hex && "is-picked")} onClick={() => set({ color: hex })} />)}</div>
      <label className="look-check"><input type="checkbox" checked={look.blush} onChange={e => set({ blush: e.target.checked }, false)} />Rosy cheeks</label>
     </>}
     {tab === "eyes" && <>
      <div className="look-grid" role="radiogroup" aria-label="Eyes">{EYES.map(([k, label]) => option(look.eyes === k, label, () => set({ eyes: k }, false), <FaceSwatch look={{ ...look, eyes: k, brows: "none", mouth: "none", blush: false }} />, k))}</div>
      <Slider label="Spacing" value={look.eyeGap} onChange={v => set({ eyeGap: v }, false)} />
      <Slider label="Height" value={look.eyeY} onChange={v => set({ eyeY: v }, false)} />
      <Slider label="Size" value={look.eyeSize} onChange={v => set({ eyeSize: v }, false)} />
      <Slider label="Pupils" value={look.pupil} onChange={v => set({ pupil: v }, false)} />
      <div className="look-row" role="radiogroup" aria-label="Glasses"><span>Glasses</span>{GLASSES.map(([k, label]) => <button type="button" key={k || "none"} role="radio" aria-checked={look.glasses === k} className={cn(look.glasses === k && "is-picked")} onClick={() => set({ glasses: k }, false)}>{label}</button>)}</div>
     </>}
     {tab === "brows" && <>
      <div className="look-grid" role="radiogroup" aria-label="Brows">{BROWS.map(([k, label]) => option(look.brows === k, label, () => set({ brows: k }, false), <FaceSwatch look={{ ...look, brows: k, mouth: "none", blush: false }} />, k))}</div>
      <Slider label="Spacing" value={look.browGap} onChange={v => set({ browGap: v }, false)} />
      <Slider label="Height" value={look.browY} onChange={v => set({ browY: v }, false)} />
      <Slider label="Size" value={look.browSize} onChange={v => set({ browSize: v }, false)} />
      <Slider label="Tilt" value={look.browTilt} onChange={v => set({ browTilt: v }, false)} />
     </>}
     {tab === "mouth" && <>
      <div className="look-grid" role="radiogroup" aria-label="Mouth">{MOUTHS.map(([k, label]) => option(look.mouth === k, label, () => set({ mouth: k }, false), <FaceSwatch look={{ ...look, mouth: k }} />, k))}</div>
      <Slider label="Height" value={look.mouthY} onChange={v => set({ mouthY: v }, false)} />
      <Slider label="Size" value={look.mouthSize} onChange={v => set({ mouthSize: v }, false)} />
     </>}
     {tab === "head" && <>
      <div className="look-grid is-3d" role="radiogroup" aria-label="Body">{BODIES.map(([k, label]) => option(look.body === k, label, () => set({ body: k }), <>{pic(thumb({ body: k, shape: "round", ears: 0, hair: "", hat: "" }))}<small>{label}</small></>, k || "classic"))}</div>
      {!look.body && <div className="look-grid is-3d" role="radiogroup" aria-label="Head shape">{SHAPES.map(([k, label]) => option(look.shape === k, label, () => set({ shape: k }), <>{pic(thumb({ shape: k, hair: "", hat: "" }))}<small>{label}</small></>, k))}</div>}
      <Slider label="Head size" value={look.head} min={.88} max={1.12} onChange={v => set({ head: v }, false)} />
      {!look.body && <Slider label="Ears" value={look.ears} onChange={v => set({ ears: v }, false)} />}
     </>}
     {tab === "hair" && <>
      <div className="look-grid is-3d" role="radiogroup" aria-label="Hair">{HAIRS.map(([k, label]) => option(look.hair === k, label, () => set({ hair: k }), <>{pic(thumb({ hair: k, hat: "" }))}<small>{label}</small></>, k || "none"))}</div>
      <div className="look-colors is-small" role="radiogroup" aria-label="Hair color">{HAIR_COLORS.map(([hex, name]) => <button type="button" key={hex} role="radio" aria-checked={look.hairColor === hex} aria-label={name} title={name} style={{ "--swatch": hex } as CSSProperties} className={cn(look.hairColor === hex && "is-picked")} onClick={() => set({ hairColor: hex })} />)}</div>
     </>}
     {tab === "hat" && <div className="look-grid is-3d" role="radiogroup" aria-label="Hat">{HATS.map(([k, label]) => option(look.hat === k, label, () => set({ hat: k }), <>{pic(thumb({ hat: k }))}<small>{label}</small></>, k || "none"))}</div>}
    </div>
    <div className="look-foot"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="button" className="look-save" onClick={() => onSave(lookKey(look))}>Save look</Button></div>
   </div>
  </DialogContent>
 </Dialog>
}
