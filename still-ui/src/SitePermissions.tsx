import { useState } from "react"
import { AppWindow, Bell, Camera, ClipboardPaste, Download, MapPin, Mic, Piano, RotateCcw, RotateCw, ScreenShare, ShieldCheck, SlidersHorizontal, Usb, Volume2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import type { ToolData } from "./BrowserTools"
import { andList } from "./Plugins"

// Each permission a site can ask for, by the engine's name for it (Still's own for pop-ups, screen sharing and USB).
export const SITE_KINDS = [
 ["Camera", "Camera", Camera], ["Microphone", "Microphone", Mic], ["Geolocation", "Location", MapPin], ["Notifications", "Notifications", Bell],
 ["ClipboardRead", "Clipboard", ClipboardPaste], ["Popups", "Pop-ups", AppWindow], ["MultipleAutomaticDownloads", "Automatic downloads", Download],
 ["Autoplay", "Autoplay and sound", Volume2], ["ScreenShare", "Screen sharing", ScreenShare], ["MidiSystemExclusiveMessages", "MIDI devices", Piano], ["Usb", "USB devices", Usb],
] as const
const IN_USE: Record<string, string> = { camera: "Camera", mic: "Microphone", location: "Geolocation" }
const NAME: Record<string, string> = { camera: "camera", mic: "microphone", location: "location" }

/// The toolbar's Permissions button: Allow, Ask or Block for each permission on the active tab's site, applied at once,
/// with a dot while the page has the camera, mic or location on.
export function SitePermissions({ origin, inUse, data, send, onOpenChange, onSettings }: { origin: string; inUse: string; data: ToolData; send: (op: string, data?: Record<string, unknown>) => void; onOpenChange: (open: boolean) => void; onSettings: () => void }) {
 const [changed, setChanged] = useState(false)
 const on = inUse.split(",").filter(n => IN_USE[n])
 const ready = data.origin === origin
 const set = (kind: string, state: string) => { send("sitePermission", { kind, state }); setChanged(true) }
 return <DropdownMenu onOpenChange={o => { onOpenChange(o); if (o) { setChanged(false); send("refreshTools", { name: "site" }) } }}>
  <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="perm-button" aria-label={on.length ? `Permissions: this site is using your ${andList(on.map(n => NAME[n]))}` : "Permissions"} title={on.length ? `Using your ${andList(on.map(n => NAME[n]))}` : "Permissions for this site"}>
   <SlidersHorizontal />{on.length > 0 && <i className="perm-dot" />}
  </Button></DropdownMenuTrigger>
  <DropdownMenuContent align="start" sideOffset={8} className="perm-menu">
   <div className="perm-head"><ShieldCheck /><div><strong>{ready ? data.site : "This site"}</strong><small>{data.isPrivate && ready ? "Private window: forgotten when it closes" : "Saved for this site, and used right away"}</small></div></div>
   {SITE_KINDS.map(([kind, label, Icon]) => {
    const state = ready ? data.states?.[kind] ?? "Ask" : "", off = ready && data.off?.includes(kind)
    return <div className="perm-row" key={kind}>
     <Icon /><span className="perm-label">{label}{on.some(n => IN_USE[n] === kind) && <em>In use</em>}</span>
     {off ? <small className="perm-off">Not available here</small>
      : <div role="radiogroup" aria-label={label} className="perm-seg">{(["Allow", "Ask", "Deny"] as const).map(s =>
       <button key={s} type="button" role="radio" aria-checked={state === s} data-state={s} disabled={!ready} onClick={() => state !== s && set(kind, s)}>{s === "Deny" ? "Block" : s}</button>)}</div>}
    </div>
   })}
   <DropdownMenuSeparator />
   {changed && <DropdownMenuItem onSelect={() => send("reload")}><RotateCw />Reload to apply to this page</DropdownMenuItem>}
   <DropdownMenuItem disabled={!ready} onSelect={e => { e.preventDefault(); send("sitePermissionsReset"); setChanged(true) }}><RotateCcw />Reset permissions</DropdownMenuItem>
   <DropdownMenuItem onSelect={onSettings}><SlidersHorizontal />All site settings</DropdownMenuItem>
  </DropdownMenuContent>
 </DropdownMenu>
}
