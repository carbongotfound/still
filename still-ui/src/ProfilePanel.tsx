import { useEffect, useRef, useState, type CSSProperties } from "react"
import { CalendarClock, Check, ChevronDown, Copy, FolderOpen, MoreHorizontal, Palette, Pencil, Plus, RotateCcw, Share2, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import { Face, hueOf, type Companion, type Mode, type Routine } from "./Buddy"
import { LookEditor } from "./LookEditor"
import { MemorySettings } from "./Memory"
import { PluginChip } from "./Plugins"
import { FileCard } from "./Files"
import { SHARE_KIND, fromPremade, premadeOf } from "./crew"
import { cn } from "@/lib/utils"
import type { AiState } from "./AiSidebar"

type Send = (op: string, payload?: Record<string, unknown>) => void
// A companion's profile, opened from its mascot: everything about it on tabs, saved as you change it.
const TABS = [["general", "General"], ["skills", "Skills"], ["routines", "Routines"], ["files", "Files"], ["memory", "Memory"], ["plugins", "Plugins"], ["model", "Model"]] as const
const MODES: [Mode, string, string][] = [["efficient", "Quick", "Short and fast. Good for lookups and small jobs."], ["default", "Everyday", "The right depth for most things."], ["expert", "Thorough", "Takes longer and checks more. For research and big tasks."]]
const DAYS = ["S", "M", "T", "W", "T", "F", "S"], DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
const WEEKDAYS = [1, 2, 3, 4, 5]
const newId = () => crypto.randomUUID().replace(/-/g, "").slice(0, 10)
const when = (r: Routine) => (r.days.length === 7 ? "Every day" : r.days.join() === WEEKDAYS.join() ? "Weekdays" : r.days.join() === "0,6" ? "Weekends" : r.days.map(d => DAY_NAMES[d]).join(", ")) + " at " + r.time
/// What Share copies: the companion without anything personal (no memory, folder, plugins or keys).
const shareOf = (c: Companion) => JSON.stringify({ kind: SHARE_KIND, v: 1, name: c.name, look: c.look ?? "", job: c.job, tone: c.tone ?? "", mode: c.mode ?? "default", crew: c.crew ?? "" })

/// `preview`: a companion from the library, not added yet. Changes stay here until Add, and only the tabs that make
/// sense before hiring show.
const PREVIEW_TABS = ["general", "skills", "routines", "model"]
export function ProfilePanel({ ai, id, preview, send, onPick, onClose, onAdd, onOpenFile, onPlugins, onSkills }: {
 ai: AiState; id: string; preview?: Companion; send: Send; onPick: (id: string) => void; onClose: () => void; onAdd?: (c: Companion) => void; onOpenFile: (path: string) => void; onPlugins: () => void; onSkills: () => void
}) {
 const saved = preview ?? ai.companions?.find(c => c.id === id)
 const [c, setC] = useState(saved)
 const [tab, setTab] = useState("general")
 const [styling, setStyling] = useState(false)
 const [ask, setAsk] = useState<"fire" | "reset" | null>(null)
 const [closing, setClosing] = useState(false)
 const name = useRef<HTMLInputElement>(null), typing = useRef(0)
 useEffect(() => { setC(saved) }, [id, !!saved]) // eslint-disable-line react-hooks/exhaustive-deps
 const close = () => { setClosing(true); setTimeout(onClose, 160) }
 const latest = useRef(c); latest.current = c
 useEffect(() => { // the folder picked in the system's own dialog
  const got = (e: MessageEvent) => { if (e.data?.kind === "folder" && latest.current) { const next = { ...latest.current, folder: e.data.data.path }; setC(next); send("companionSave", next) } }
  window.chrome?.webview?.addEventListener("message", got); return () => window.chrome?.webview?.removeEventListener("message", got)
 }, [send])
 useEffect(() => {
  // Esc closes, unless a menu or a dialog over the panel takes it first
  const key = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector(":is([role=menu],[role=alertdialog],[data-slot=dialog-content])[data-state=open]")) close() }
  addEventListener("keydown", key); return () => removeEventListener("keydown", key)
 }) // eslint-disable-line react-hooks/exhaustive-deps
 if (!saved || !c) return null
 const save = (next: Companion, later = false) => {
  setC(next); clearTimeout(typing.current)
  if (preview) return
  const go = () => send("companionSave", { ...next })
  if (later) typing.current = window.setTimeout(go, 500); else go()
 }
 const premade = premadeOf(c), only = (ai.companions?.length ?? 0) <= 1, label = c.name.trim() || "they"
 const harness = ai.harnesses.find(h => h.id === (c.ai || ai.harness))
 const state = (hid: string) => { const h = ai.harnesses.find(x => x.id === hid); return !h ? "" : !h.installed || h.status === "missing" ? "Not installed" : h.status === "signedOut" ? "Sign in first" : "" }
 const chatsOf = new Set(ai.chats.filter(x => x.companion === c.id).map(x => x.id))
 const files = (ai.files ?? []).filter(f => chatsOf.has(f.chat))
 const plugins = ai.plugins, pluginsReady = !!plugins?.key && plugins.status === "ok"
 const routines = c.routines ?? []
 const duplicate = () => { const copy = { ...c, id: newId(), name: (c.name.slice(0, 21) + " 2").trim(), crew: "", routines: [] }; send("companionSave", copy); onPick(copy.id); toast(`Made ${copy.name}, a copy of ${c.name}.`) }
 const share = () => navigator.clipboard.writeText(shareOf(c)).then(() => toast(`Copied ${c.name}. Paste it on anyone's Companions page in Still to add them. Nothing they remember about you is in it.`), () => toast("Couldn't copy. Try again."))
 return <>
  <div className={cn("profile-scrim", closing && "is-closing")} onClick={close} />
  <aside className={cn("profile-panel", closing && "is-closing", preview && "is-preview")} role="dialog" aria-modal aria-label={preview ? `Meet ${saved.name}` : `${c.name}'s profile`} style={{ "--hue": hueOf(c) } as CSSProperties}>
   <header className="profile-head">
    {preview ? <span className="profile-switch is-static"><Face companion={c} size={28} /><b>{c.name}</b>{premade && <small className="profile-role">{premade.role}</small>}</span> : <>
    <DropdownMenu><DropdownMenuTrigger asChild><button className="profile-switch" aria-label="Switch companion"><Face companion={c} size={28} /><b>{c.name}</b><ChevronDown /></button></DropdownMenuTrigger>
     <DropdownMenuContent align="start" className="w-56">{ai.companions?.map(x => <DropdownMenuItem key={x.id} onSelect={() => onPick(x.id)}><Face companion={x} size={20} />{x.name}{x.id === c.id && <Check className="ml-auto" />}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>
    <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="ml-auto" aria-label="More"><MoreHorizontal /></Button></DropdownMenuTrigger>
     <DropdownMenuContent align="end" className="w-56">
      <DropdownMenuItem onSelect={() => { setTab("general"); setTimeout(() => { name.current?.focus(); name.current?.select() }, 50) }}><Pencil />Rename</DropdownMenuItem>
      <DropdownMenuItem onSelect={duplicate}><Copy />Duplicate</DropdownMenuItem>
      {premade && <DropdownMenuItem onSelect={() => setAsk("reset")}><RotateCcw />Reset to how {premade.name} started</DropdownMenuItem>}
      <DropdownMenuSeparator />
      <DropdownMenuItem variant="destructive" onSelect={() => setAsk("fire")}><Trash2 />{premade ? "Fire" : "Delete"} {c.name}</DropdownMenuItem>
     </DropdownMenuContent></DropdownMenu></>}
    <Button variant="ghost" size="icon-sm" className={preview ? "ml-auto" : undefined} aria-label="Close" onClick={close}><X /></Button>
   </header>
   <Tabs value={tab} onValueChange={setTab} className="profile-tabs">
    <TabsList className="profile-tablist">{TABS.filter(([v]) => !preview || PREVIEW_TABS.includes(v)).map(([v, t]) => <TabsTrigger key={v} value={v}>{t}</TabsTrigger>)}</TabsList>
    <div className="profile-body">
     <TabsContent value="general">
      <div className="profile-stage"><Face companion={c} size={196} follow />
       <div className="profile-stage-actions">
        <Button size="sm" variant="secondary" onClick={() => setStyling(true)}><Palette />Edit look</Button>
        {!preview && <Button size="sm" variant="secondary" onClick={share}><Share2 />Share</Button>}
       </div>
      </div>
      <label className="profile-field"><span>Name</span><Input ref={name} maxLength={24} value={c.name} onChange={e => setC({ ...c, name: e.target.value })} onBlur={() => c.name.trim() ? save({ ...c, name: c.name.trim() }) : setC(saved)} /></label>
      <label className="profile-field"><span>Instructions</span>
       <textarea rows={5} maxLength={1000} value={c.job} placeholder={`What ${c.name || "they"} does for you inside Still. For example: "Find me the best price before I buy anything, and show me where."`} onChange={e => save({ ...c, job: e.target.value }, true)} /></label>
      <label className="profile-field"><span>How {label} talks</span>
       <textarea rows={2} maxLength={600} value={c.tone ?? ""} placeholder="For example: upbeat and quick, with short answers and a joke now and then." onChange={e => save({ ...c, tone: e.target.value }, true)} /></label>
      {preview && premade && <section className="profile-section"><h4>What to expect</h4><ul className="profile-will">{premade.expect.map(w => <li key={w}>{w}</li>)}</ul></section>}
     </TabsContent>
     <TabsContent value="skills">
      <p className="profile-lead">Skills {label} reads at the start of every chat. You can also call any skill with /its-name in a message.</p>
      {(ai.skills ?? []).length ? <ul className="profile-list">{ai.skills!.map(k => { const on = !!c.skills?.includes(k.id); return <li key={k.id}>
       <div><b>{k.name}</b><small>{k.description}</small></div>
       <Switch checked={on} aria-label={`${k.name} for ${c.name}`} onCheckedChange={v => save({ ...c, skills: v ? [...(c.skills ?? []), k.id] : (c.skills ?? []).filter(x => x !== k.id) })} />
      </li> })}</ul> : <Empty text="No skills yet. Write one on the Skills page, then turn it on here." action="Open Skills" onAction={onSkills} />}
     </TabsContent>
     <TabsContent value="routines">
      <p className="profile-lead">Things {label} does on a schedule, each in a new chat, while Still is open. Anything that sends, posts or changes data still asks you first.</p>
      {routines.length > 0 && <ul className="profile-list">{routines.map(r => <li key={r.id}>
       <div><b>{r.text}</b><small><CalendarClock />{when(r)}</small></div>
       <Switch checked={r.on} aria-label={`Turn ${r.on ? "off" : "on"}: ${r.text}`} onCheckedChange={v => save({ ...c, routines: routines.map(x => x.id === r.id ? { ...x, on: v } : x) })} />
       <Button variant="ghost" size="icon-xs" aria-label={"Delete: " + r.text} onClick={() => save({ ...c, routines: routines.filter(x => x.id !== r.id) })}><Trash2 /></Button>
      </li>)}</ul>}
      {routines.length < 20 && <RoutineForm who={c.name} onAdd={r => save({ ...c, routines: [...routines, r] })} />}
     </TabsContent>
     <TabsContent value="files">
      <section className="profile-section"><h4>Working folder</h4>
       <div className="companion-folder"><code title={c.folder}>{c.folder || `None, so ${label} can't touch your files.`}</code>
        <Button type="button" variant="outline" size="sm" onClick={() => window.chrome?.webview?.postMessage({ op: "pickFolder" })}><FolderOpen />{c.folder ? "Change" : "Pick a folder"}</Button>
        {c.folder && <Button type="button" variant="ghost" size="sm" onClick={() => save({ ...c, folder: "" })}>Remove</Button>}</div>
       {c.folder && (c.ai || ai.harness) !== "claude" && <p className="profile-note">Only Claude can work in a folder for now. Others still help in the browser.</p>}
      </section>
      <section className="profile-section"><h4>Made by {c.name}</h4>
       {files.length ? <div className="profile-files">{files.map(f => <FileCard key={f.path} path={f.path} send={send} onOpen={onOpenFile} />)}</div>
        : <p className="profile-note">Nothing yet. Files {label} saves in a chat show up here.</p>}
      </section>
     </TabsContent>
     <TabsContent value="memory"><MemorySettings companions={[saved]} send={send} /></TabsContent>
     <TabsContent value="plugins">
      {!pluginsReady ? <Empty text={`Plugins let ${label} work in your apps, like Gmail, Calendar and Slack. They stay off until you add your own Composio key.`} action="Set up plugins" onAction={onPlugins} />
       : plugins!.connected.length ? <><p className="profile-lead">Apps {label} can use. Reading is free. Anything that sends, posts, deletes, pays or changes data asks you first.</p>
        <ul className="profile-list">{plugins!.connected.map(p => { const on = !saved.pluginsOff?.includes(p.slug); return <li key={p.id}>
         <PluginChip slug={p.slug} name={p.name} />
         <Switch checked={on} aria-label={`${p.name} for ${c.name}`} onCheckedChange={v => send("pluginToggle", { companion: c.id, slug: p.slug, on: v })} />
        </li> })}</ul></>
       : <Empty text="No apps connected yet." action="Connect an app" onAction={onPlugins} />}
     </TabsContent>
     <TabsContent value="model">
      <label className="profile-field"><span>Runs on</span><select className="companion-select" value={c.ai ?? ""} onChange={e => save({ ...c, ai: e.target.value })}>
       <option value="">Your AI{harness && !c.ai ? ` (${harness.name})` : ""}</option>
       {ai.harnesses.filter(h => !h.secondary || h.id === c.ai).map(h => <option key={h.id} value={h.id}>{h.name}{state(h.id) && " · " + state(h.id)}</option>)}
      </select></label>
      {c.ai && state(c.ai) && <p className="profile-note">{ai.harnesses.find(h => h.id === c.ai)?.name} isn't ready yet. Set it up from the chat sidebar, and {label} can start.</p>}
      <div className="profile-field"><span>Thinking</span>
       <div className="profile-modes" role="radiogroup" aria-label="Thinking">{MODES.map(([m, t, d]) => <button key={m} role="radio" aria-checked={(c.mode ?? "default") === m} onClick={() => save({ ...c, mode: m })}><b>{t}</b><small>{d}</small></button>)}</div>
      </div>
     </TabsContent>
    </div>
   </Tabs>
   {preview && <footer className="profile-foot">
    <Button variant="ghost" onClick={close}>Back to the library</Button>
    <Button className="profile-add" onClick={() => onAdd?.({ ...c, name: c.name.trim() || saved.name })}><Plus />Add {c.name.trim() || saved.name}</Button>
   </footer>}
  </aside>
  {styling && <LookEditor companion={c} onClose={() => setStyling(false)} onSave={look => { save({ ...c, look }); setStyling(false) }} />}
  <AlertDialog open={!!ask} onOpenChange={o => { if (!o) setAsk(null) }}>
   <AlertDialogContent>
    {ask === "reset" && premade ? <>
     <AlertDialogHeader><AlertDialogTitle>Reset {c.name}?</AlertDialogTitle><AlertDialogDescription>Their name, look, instructions, way of talking and thinking go back to how {premade.name} started. What they remember about you, their skills and routines stay.</AlertDialogDescription></AlertDialogHeader>
     <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => save({ ...c, ...fromPremade(premade, c.id), skills: c.skills, routines: c.routines, folder: c.folder, ai: c.ai })}>Reset</AlertDialogAction></AlertDialogFooter>
    </> : only ? <>
     <AlertDialogHeader><AlertDialogTitle>{c.name} is your only companion</AlertDialogTitle><AlertDialogDescription>Still needs at least one. Hire or make another first, then you can {premade ? "fire" : "delete"} {c.name}.</AlertDialogDescription></AlertDialogHeader>
     <AlertDialogFooter><AlertDialogCancel>OK</AlertDialogCancel></AlertDialogFooter>
    </> : <>
     <AlertDialogHeader><AlertDialogTitle>{premade ? "Fire" : "Delete"} {c.name}?</AlertDialogTitle><AlertDialogDescription>{c.name} goes, with everything they remember about you and their routines. Your chats with them stay.</AlertDialogDescription></AlertDialogHeader>
     <AlertDialogFooter><AlertDialogCancel>Keep {c.name}</AlertDialogCancel><AlertDialogAction className="bg-destructive text-white hover:bg-destructive/90" onClick={() => { send("companionDelete", { id: c.id }); close() }}>{premade ? "Fire" : "Delete"}</AlertDialogAction></AlertDialogFooter>
    </>}
   </AlertDialogContent>
  </AlertDialog>
 </>
}

function Empty({ text, action, onAction }: { text: string; action: string; onAction: () => void }) {
 return <div className="profile-empty"><p>{text}</p><Button size="sm" variant="outline" onClick={onAction}>{action}</Button></div>
}

function RoutineForm({ who, onAdd }: { who: string; onAdd: (r: Routine) => void }) {
 const [text, setText] = useState(""), [time, setTime] = useState("09:00"), [days, setDays] = useState(WEEKDAYS)
 return <form className="profile-routine" onSubmit={e => { e.preventDefault(); if (!text.trim() || !days.length) return; onAdd({ id: newId(), text: text.trim(), time, days, on: true }); setText("") }}>
  <textarea rows={2} maxLength={2000} aria-label="What to do" placeholder={`What should ${who || "they"} do? For example: "Every morning, sum up my unread email in five bullets."`} value={text} onChange={e => setText(e.target.value)} />
  <div className="profile-routine-row">
   <div className="profile-days" role="group" aria-label="Days">{DAYS.map((d, i) => <button type="button" key={i} aria-pressed={days.includes(i)} aria-label={DAY_NAMES[i]} onClick={() => setDays(days.includes(i) ? days.filter(x => x !== i) : [...days, i].sort())}>{d}</button>)}</div>
   <Input type="time" aria-label="Time" value={time} required onChange={e => setTime(e.target.value)} />
   <Button type="submit" size="sm" disabled={!text.trim() || !days.length}><Plus />Add</Button>
  </div>
 </form>
}
