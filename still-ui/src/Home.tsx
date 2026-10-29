import { useEffect, useState, type CSSProperties } from "react"
import { Archive, ArchiveRestore, ArrowDownUp, BookOpen, Brain, ChevronDown, Dices, FolderOpen, Library, MessageSquare, MoreHorizontal, Palette, Pencil, Plus, Search, Settings2, SquarePen, Trash2, Users, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import { AiLogo } from "./AiLogo"
import { Face, hueOf, type Companion, type Mode } from "./Buddy"
import { lookKey, surprise } from "./look"
import { LookEditor } from "./LookEditor"
import { companionOf, isRunning, needsYou, type AiState, type Skill } from "./AiSidebar"
import { FileIcon, nameOf } from "./Files"
import { CrewCards, fromPremade, fromShared } from "./crew"
import { toast } from "sonner"

// The new tab page is Still's home: a slim rail on the left switches between the chat home and these pages.
export type HomeView = "home" | "chats" | "companions" | "skills" | "library"
type Send = (op: string, payload?: Record<string, unknown>) => void
/// A new companion: a surprise look, and the user names them.
export const randomCompanion = (): Companion => ({ id: "", name: "", face: "", color: "", job: "", mode: "default", look: lookKey(surprise()) })

export function HomeRail({ view, setView, profile, onSettings }: { view: HomeView; setView: (v: HomeView) => void; profile: string; onSettings: () => void }) {
 const item = (v: HomeView, label: string, Icon: typeof Users) => <button className="home-rail-item" aria-label={label} title={label} aria-current={view === v ? "page" : undefined} onClick={() => setView(v)}><Icon /></button>
 return <nav className="home-rail" aria-label="Home">
  <span className="still-mark is-small" aria-hidden><i /><i /></span>
  {item("home", "New chat", SquarePen)}
  {item("chats", "Chats", MessageSquare)}
  {item("library", "Library", Library)}
  {item("companions", "Companions", Users)}
  {item("skills", "Skills", BookOpen)}
  <span className="home-rail-gap" />
  <button className="home-rail-item" aria-label="Settings" title="Settings" onClick={onSettings}><Settings2 /></button>
  <span className="chat-side-avatar" title={profile}>{(profile[0] ?? "S").toUpperCase()}</span>
 </nav>
}

/// Top center of the home: who you're working with, the others as small faces, and a way to add one.
export function CompanionSwitch({ ai, companion, onPick, onEdit, onManage }: { ai: AiState; companion: Companion; onPick: (id: string) => void; onEdit: (c: Companion) => void; onManage: () => void }) {
 return <div className="mate-switch" role="radiogroup" aria-label="Who to work with">
  <button role="radio" aria-checked className="mate-switch-on" title={"Edit " + companion.name} onClick={() => onEdit(companion)}><Face companion={companion} size={24} /><b>{companion.name}</b></button>
  {ai.companions?.filter(c => c.id !== companion.id).slice(0, 5).map(c => <button key={c.id} role="radio" aria-checked={false} className="mate-switch-face" title={c.name} aria-label={c.name} onClick={() => onPick(c.id)}><Face companion={c} size={24} /></button>)}
  <DropdownMenu><DropdownMenuTrigger asChild><button className="mate-switch-more" aria-label="All companions"><ChevronDown /></button></DropdownMenuTrigger>
   <DropdownMenuContent align="center" className="w-56">
    {ai.companions?.map(c => <DropdownMenuItem key={c.id} onSelect={() => onPick(c.id)}><Face companion={c} size={20} />{c.name}</DropdownMenuItem>)}
    <DropdownMenuSeparator /><DropdownMenuItem onSelect={onManage}><Users />Manage companions</DropdownMenuItem>
   </DropdownMenuContent></DropdownMenu>
  <button className="mate-switch-more" aria-label="New companion" title="New companion" onClick={() => onEdit(randomCompanion())}><Plus /></button>
 </div>
}

const ago = (iso: string) => { const m = (Date.now() - Date.parse(iso)) / 6e4; return m < 60 ? Math.max(1, Math.round(m)) + "m" : m < 1440 ? Math.round(m / 60) + "h" : Math.round(m / 1440) + "d" }
const dayOf = (iso: string) => { const d = new Date(iso), now = new Date(); const days = Math.round((new Date(now.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 864e5); return days <= 0 ? "Today" : days === 1 ? "Yesterday" : days < 7 ? "This week" : "Earlier" }

export function ChatHistory({ ai, send, onNew }: { ai: AiState; send: Send; onNew: () => void }) {
 const [find, setFind] = useState("")
 const [only, setOnly] = useState<"" | "unread" | "needs" | "archived">("")
 const [who, setWho] = useState("")
 const [oldest, setOldest] = useState(false)
 const [wipe, setWipe] = useState(false)
 const needs = (id: string) => needsYou(ai, id)
 const first = ai.companions?.[0]?.id
 const chats = ai.chats.filter(c => (only === "archived") === !!c.archived && (only !== "unread" || c.unread) && (only !== "needs" || needs(c.id))
  && (!who || (c.companion || first) === who) && c.title.toLowerCase().includes(find.trim().toLowerCase()))
 if (oldest) chats.reverse()
 const groups = chats.reduce<[string, typeof chats][]>((all, c) => { const day = dayOf(c.updated); if (all.at(-1)?.[0] === day) all.at(-1)![1].push(c); else all.push([day, [c]]); return all }, [])
 const chip = (key: typeof only, label: string, dot?: string) => <button className="history-chip" aria-pressed={only === key} onClick={() => setOnly(only === key ? "" : key)}>{label}{dot && <i className={dot} />}</button>
 const mate = companionOf(ai, who)
 return <section className="home-page" aria-label="Chat History">
  <header className="home-page-head"><h1>Chat History</h1>
   <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="More"><MoreHorizontal /></Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end"><DropdownMenuItem disabled={!ai.chats.length || !!ai.runs?.length} onSelect={() => setWipe(true)} className="text-destructive"><Trash2 />Delete all chats</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
   <Button className="home-new" onClick={onNew}><Plus />New chat</Button>
  </header>
  <label className="history-find"><Search /><input aria-label="Search chats" placeholder="Search chats..." value={find} onChange={e => setFind(e.target.value)} /></label>
  <div className="history-chips">
   {chip("unread", "Unread", "is-unread")}{chip("needs", "Needs input", "is-needs")}{chip("archived", "Archived")}
   <DropdownMenu><DropdownMenuTrigger asChild><button className="history-chip" aria-pressed={!!who}>{who && mate ? <><Face companion={mate} size={16} />{mate.name}</> : "Companion"}<ChevronDown /></button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="w-52">
     <DropdownMenuItem onSelect={() => setWho("")}>Everyone</DropdownMenuItem>
     {ai.companions?.map(c => <DropdownMenuItem key={c.id} onSelect={() => setWho(c.id)}><Face companion={c} size={18} />{c.name}</DropdownMenuItem>)}
    </DropdownMenuContent></DropdownMenu>
   <button className="history-sort" onClick={() => setOldest(!oldest)}><ArrowDownUp />{oldest ? "Oldest first" : "Most recent"}</button>
  </div>
  {!chats.length && <p className="home-empty">{find || only || who ? "No chats match." : "Your chats show up here. Start one from the new tab page."}</p>}
  {groups.map(([day, list]) => <div key={day} className="history-group"><h2>{day}</h2>
   {list.map(c => <div key={c.id} className="history-row">
    <button className="history-open" onClick={() => send("chatOpen", { id: c.id })}><Face companion={companionOf(ai, c.companion)} size={30} mood={isRunning(ai, c.id) ? "working" : "idle"} /><b>{c.title}</b>
     {needs(c.id) ? <span className="history-needs">Needs input</span> : c.unread ? <i className="is-unread" aria-label="Unread" /> : isRunning(ai, c.id) ? <small>Working</small> : <small>{ago(c.updated)}</small>}</button>
    <button className="history-act" aria-label={c.archived ? "Unarchive " + c.title : "Archive " + c.title} title={c.archived ? "Unarchive" : "Archive"} onClick={() => send("chatArchive", { id: c.id, on: !c.archived })}>{c.archived ? <ArchiveRestore /> : <Archive />}</button>
    <button className="history-act" disabled={isRunning(ai, c.id)} aria-label={"Delete " + c.title} title="Delete" onClick={() => send("aiDeleteChat", { id: c.id })}><Trash2 /></button>
   </div>)}
  </div>)}
  <AlertDialog open={wipe} onOpenChange={setWipe}><AlertDialogContent>
   <AlertDialogHeader><AlertDialogTitle>Delete all chats?</AlertDialogTitle><AlertDialogDescription>Every chat in this profile goes away. Your AI app may keep its own copy.</AlertDialogDescription></AlertDialogHeader>
   <AlertDialogFooter><AlertDialogCancel>Keep them</AlertDialogCancel><AlertDialogAction onClick={() => send("aiDeleteAll")}>Delete all</AlertDialogAction></AlertDialogFooter>
  </AlertDialogContent></AlertDialog>
 </section>
}

/// The AI a companion runs on, for its badge: its own pick, or the one picked for chats.
const aiOf = (ai: AiState, c: Companion) => ai.harnesses.find(h => h.id === (c.ai || ai.harness))

export function CompanionsPage({ ai, send, onEdit, onMake, onChat, onMemory }: { ai: AiState; send: Send; onEdit: (c: Companion) => void; onMake: () => void; onChat: (id: string) => void; onMemory: (id: string) => void }) {
 useEffect(() => { // a companion someone shared (ProfilePanel's Share), pasted anywhere on the page
  const paste = (e: ClipboardEvent) => {
   const c = !(e.target as HTMLElement).closest?.("input, textarea") && fromShared(e.clipboardData?.getData("text") ?? "")
   if (!c) return
   send("companionSave", c)
   toast(`Added ${c.name}. They start fresh: they don't know anything about you yet.`)
  }
  addEventListener("paste", paste); return () => removeEventListener("paste", paste)
 }, [send])
 return <section className="home-page" aria-label="Companions">
  <header className="home-page-head"><h1>Companions</h1><Button className="home-new" onClick={() => onEdit(randomCompanion())}><Plus />New companion</Button></header>
  <p className="home-page-lead">Who you work with. Each one has a job, a way of talking, skills and a memory of you, on top of your own AI plan. Got one someone shared? Paste it here.</p>
  <div className="mate-grid">
   {ai.companions?.map(c => { const h = aiOf(ai, c); return <article key={c.id} className="mate-card" style={{ "--hue": hueOf(c) } as CSSProperties}>
    <button className="mate-portrait" aria-label={"Edit " + c.name} onClick={() => onEdit(c)}><Face companion={c} size={118} follow /><Pencil className="mate-edit" /></button>
    <div className="mate-info">
    <h3>{c.name}</h3>
    <p>{c.job || "No job yet. Tell them what they're good at."}</p>
    <span className="mate-badge">{h ? <><AiLogo id={h.id} size={14} />{h.name} · Your {h.name} plan</> : "Pick your AI"}</span>
    {(() => { const known = c.memory?.filter(f => f.kind !== "chat").length ?? 0; return <button className="mate-memory" onClick={() => onMemory(c.id)}><Brain />{known ? `Remembers ${known} ${known === 1 ? "thing" : "things"}` : "What they remember"}</button> })()}
    <button className="mate-chat" onClick={() => onChat(c.id)}>Say hi</button>
    </div>
   </article> })}
  </div>
  <h2 className="home-page-sub">Hire for a role</h2>
  <p className="home-page-lead">Each one owns a part of your work and gets sharper as it learns about you. Hire one, then change anything you like.</p>
  <CrewCards have={ai.companions} onChat={onChat} onOwn={onMake} onPick={p => send("companionSave", fromPremade(p))} />
 </section>
}

export function SkillsPage({ ai, send }: { ai: AiState; send: Send }) {
 const [editing, setEditing] = useState<Skill | null>(null)
 const skills = ai.skills ?? []
 return <section className="home-page" aria-label="Skills">
  <header className="home-page-head"><h1>Skills</h1><Button className="home-new" onClick={() => setEditing({ id: "", name: "", description: "", when: "", body: "" })}><Plus />New skill</Button></header>
  <p className="home-page-lead">A skill is a short how-to your companions follow, like how you like a trip plan laid out. Type / in a message to use one, or give it to a companion so they always have it.</p>
  {!skills.length && <p className="home-empty">No skills yet. Make your first one.</p>}
  <div className="skill-list">{skills.map(k => <div key={k.id} className="skill-row">
   <span className="skill-icon"><BookOpen /></span>
   <button className="skill-open" onClick={() => setEditing(k)}><b>{k.name}</b><small>/{k.id}{k.description && " · " + k.description}</small></button>
   <button className="history-act" aria-label={"Delete " + k.name} title="Delete" onClick={() => send("skillDelete", { id: k.id })}><Trash2 /></button>
  </div>)}</div>
  {editing && <SkillEditor skill={editing} onClose={() => setEditing(null)} onSave={k => { send("skillSave", k); setEditing(null) }} />}
 </section>
}

function SkillEditor({ skill, onClose, onSave }: { skill: Skill; onClose: () => void; onSave: (k: Skill) => void }) {
 const [k, setK] = useState(skill)
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog skill-dialog">
   <DialogHeader><DialogTitle>{skill.id ? "Edit " + skill.name : "New skill"}</DialogTitle><DialogDescription>Write it like a note to a helpful friend.</DialogDescription></DialogHeader>
   <form className="companion-form" onSubmit={e => { e.preventDefault(); if (k.name.trim()) onSave(k) }}>
    <label><span>Name</span><Input required maxLength={60} placeholder="Trip plan" value={k.name} onChange={e => setK({ ...k, name: e.target.value })} /></label>
    <label><span>What it does</span><Input maxLength={300} placeholder="Lays out a trip day by day, with costs" value={k.description} onChange={e => setK({ ...k, description: e.target.value })} /></label>
    <label><span>When to use it</span><Input maxLength={300} placeholder="Planning any trip" value={k.when} onChange={e => setK({ ...k, when: e.target.value })} /></label>
    <label><span>Steps</span><textarea className="companion-job" rows={8} maxLength={20000} placeholder={"1. Ask where I'm starting from.\n2. Plan each day: morning, afternoon, evening.\n3. End with a table of costs."} value={k.body} onChange={e => setK({ ...k, body: e.target.value })} /></label>
    <div className="companion-actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={!k.name.trim()}>Save</Button></div>
   </form>
  </DialogContent>
 </Dialog>
}

// Every file an AI saved, newest first, with the chat it came from.
export function LibraryPage({ ai, send, onOpen }: { ai: AiState; send: Send; onOpen: (path: string) => void }) {
 const [find, setFind] = useState("")
 const [who, setWho] = useState("")
 const first = ai.companions?.[0]?.id, mate = companionOf(ai, who)
 const chatOf = (id: string) => ai.chats.find(c => c.id === id)
 const files = (ai.files ?? []).filter(f => f.name.toLowerCase().includes(find.trim().toLowerCase()) && (!who || (chatOf(f.chat)?.companion || first) === who && !!chatOf(f.chat)))
 return <section className="home-page" aria-label="Library">
  <header className="home-page-head"><h1>Library</h1></header>
  {!ai.files?.length ? <div className="home-empty is-big"><Library /><p>Nothing here yet. Ask a companion for a table or notes, and the file lands here.</p></div> : <>
   <label className="history-find"><Search /><input aria-label="Search files" placeholder="Search files..." value={find} onChange={e => setFind(e.target.value)} /></label>
   <div className="history-chips">
    <DropdownMenu><DropdownMenuTrigger asChild><button className="history-chip" aria-pressed={!!who}>{who && mate ? <><Face companion={mate} size={16} />{mate.name}</> : "Companion"}<ChevronDown /></button></DropdownMenuTrigger>
     <DropdownMenuContent align="start" className="w-52">
      <DropdownMenuItem onSelect={() => setWho("")}>Everyone</DropdownMenuItem>
      {ai.companions?.map(c => <DropdownMenuItem key={c.id} onSelect={() => setWho(c.id)}><Face companion={c} size={18} />{c.name}</DropdownMenuItem>)}
     </DropdownMenuContent></DropdownMenu>
   </div>
   {!files.length && <p className="home-empty">No files match.</p>}
   <div className="library-list">{files.map(f => { const chat = chatOf(f.chat); return <div key={f.path} className="history-row">
    <button className="history-open" onClick={() => onOpen(f.path)}><FileIcon path={f.path} /><b>{nameOf(f.path)}</b><small>{chat ? chat.title + " · " : ""}{ago(f.saved)}</small></button>
    {chat && <button className="history-act" aria-label={"Open the chat for " + f.name} title="Open chat" onClick={() => send("chatOpen", { id: chat.id })}><MessageSquare /></button>}
    <button className="history-act" aria-label={"Show " + f.name + " in its folder"} title="Show in folder" onClick={() => send("fileShow", { path: f.path })}><FolderOpen /></button>
    <button className="history-act" aria-label={"Delete " + f.name} title="Delete" onClick={() => send("fileDelete", { path: f.path })}><Trash2 /></button>
   </div> })}</div>
  </>}
 </section>
}

/// Once after an update: a companion that still has a name Still used to hand out asks whether to keep it.
export function RenameAsk({ companion, onSave }: { companion: Companion; onSave: (c: Companion) => void }) {
 const [name, setName] = useState("")
 const keep = () => onSave(companion)
 return <Dialog open onOpenChange={o => { if (!o) keep() }}>
  <DialogContent className="app-dialog rename-dialog" style={{ "--hue": hueOf(companion) } as CSSProperties}>
   <DialogHeader><DialogTitle>Give {companion.name} a new name?</DialogTitle>
    <DialogDescription>Still picked the name {companion.name} in an earlier version. You can choose your own, or keep it.</DialogDescription></DialogHeader>
   <form className="companion-form" onSubmit={e => { e.preventDefault(); if (name.trim()) onSave({ ...companion, name: name.trim() }) }}>
    <div className="companion-preview"><Face companion={companion} size={96} follow /></div>
    <label><span>New name</span><Input autoFocus maxLength={24} value={name} onChange={e => setName(e.target.value)} /></label>
    <div className="companion-actions"><Button type="button" variant="ghost" className="rename-keep" onClick={keep}>Keep {companion.name}</Button><Button type="submit" className="rename-save" disabled={!name.trim()}>Rename</Button></div>
   </form>
  </DialogContent>
 </Dialog>
}

// Create or edit a companion: their look, name, job and way of talking, the AI they run on and how hard they think, their skills.
const MODE_NAMES: [Mode, string][] = [["efficient", "Quick"], ["default", "Everyday"], ["expert", "Thorough"]]
/// `only`: it's the last companion, and Still always keeps one, so Delete explains instead.
export function CompanionEditor({ ai, companion, canDelete, only, onClose, onSave, onDelete }: { ai: AiState; companion: Companion; canDelete: boolean; only?: boolean; onClose: () => void; onSave: (c: Companion) => void; onDelete: () => void }) {
 const [c, setC] = useState<Companion>({ mode: "default", skills: [], tone: "", ai: "", ...companion })
 const [lastOne, setLastOne] = useState(false)
 const [styling, setStyling] = useState(false)
 const skills = ai.skills ?? []
 useEffect(() => { // the folder picked in Windows' own dialog
  const got = (e: MessageEvent) => { if (e.data?.kind === "folder") setC(old => ({ ...old, folder: e.data.data.path })) }
  window.chrome?.webview?.addEventListener("message", got); return () => window.chrome?.webview?.removeEventListener("message", got)
 }, [])
 const state = (id: string) => { const h = ai.harnesses.find(x => x.id === id); return !h ? "" : !h.installed || h.status === "missing" ? "Not installed" : h.status === "signedOut" ? "Sign in first" : "" }
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog companion-dialog" style={{ "--hue": hueOf(c) } as CSSProperties}>
   <DialogHeader><DialogTitle>{companion.id ? "Edit " + companion.name : "New companion"}</DialogTitle><DialogDescription>Who you work with in a chat. Their job tells your AI how to help.</DialogDescription></DialogHeader>
   <form className="companion-form" onSubmit={e => { e.preventDefault(); if (c.name.trim()) onSave({ ...c, name: c.name.trim() }) }}>
    <div className="companion-preview"><Face companion={c} size={120} follow />
     <div className="companion-look">
      <Button type="button" variant="outline" size="sm" onClick={() => setStyling(true)}><Palette />Customize</Button>
      <Button type="button" variant="ghost" size="sm" className="companion-random" onClick={() => setC({ ...c, look: lookKey(surprise()) })}><Dices />Surprise me</Button>
     </div>
    </div>
    {styling && <LookEditor companion={c} onClose={() => setStyling(false)} onSave={look => { setC({ ...c, look }); setStyling(false) }} />}
    <label><span>Name</span><Input required maxLength={24} value={c.name} onChange={e => setC({ ...c, name: e.target.value })} /></label>
    <label><span>What should they do?</span><textarea className="companion-job" rows={3} maxLength={1000} placeholder="For example: a careful researcher who checks sources and cites them." value={c.job} onChange={e => setC({ ...c, job: e.target.value })} /></label>
    <div className="companion-row">
     <label><span>Runs on</span><select className="companion-select" value={c.ai} onChange={e => setC({ ...c, ai: e.target.value })}>
      <option value="">Your AI{ai.harnesses.find(h => h.id === ai.harness) ? " (" + ai.harnesses.find(h => h.id === ai.harness)!.name + ")" : ""}</option>
      {ai.harnesses.filter(h => !h.secondary || h.id === c.ai).map(h => <option key={h.id} value={h.id}>{h.name}{state(h.id) && " · " + state(h.id)}</option>)}
     </select></label>
     <div className="companion-field"><span>Thinking</span><div className="companion-modes" role="radiogroup" aria-label="Thinking">{MODE_NAMES.map(([m, label]) => <button type="button" key={m} role="radio" aria-checked={c.mode === m} onClick={() => setC({ ...c, mode: m })}>{label}</button>)}</div></div>
    </div>
    {c.ai && state(c.ai) && <p className="companion-note">{ai.harnesses.find(h => h.id === c.ai)?.name} isn't ready yet. Set it up from the chat sidebar, and {c.name || "they"} can start.</p>}
    <div className="companion-field"><span>Skills they always use</span>
     {skills.length ? <div className="companion-skills">{skills.map(k => { const on = c.skills?.includes(k.id); return <button type="button" key={k.id} aria-pressed={on} title={k.description} onClick={() => setC({ ...c, skills: on ? c.skills?.filter(x => x !== k.id) : [...(c.skills ?? []), k.id] })}><BookOpen />{k.name}{on && <X />}</button> })}</div>
      : <p className="companion-note">No skills yet. Make some on the Skills page, then give them to {c.name || "your companion"} here.</p>}</div>
    <div className="companion-field"><span>Working folder</span>
     <div className="companion-folder"><code title={c.folder}>{c.folder || "None, so they can't touch your files."}</code>
      <Button type="button" variant="outline" size="sm" onClick={() => window.chrome?.webview?.postMessage({ op: "pickFolder" })}><FolderOpen />{c.folder ? "Change" : "Pick a folder"}</Button>
      {c.folder && <Button type="button" variant="ghost" size="sm" onClick={() => setC({ ...c, folder: "" })}>Remove</Button>}</div>
     {c.folder && (c.ai || ai.harness) !== "claude" && <p className="companion-note">Only Claude can work in a folder for now. Others still help in the browser.</p>}</div>
    <label><span>How should {c.name.trim() || "they"} talk?</span><textarea className="companion-job" rows={2} maxLength={600} placeholder="For example: upbeat and quick, with short answers and a joke now and then." value={c.tone} onChange={e => setC({ ...c, tone: e.target.value })} /></label>
    {lastOne && <p className="companion-note is-warn" role="alert">{companion.name} is your only companion, and Still needs at least one. Add another before you delete {companion.name}.</p>}
    <div className="companion-actions">
     {canDelete && <Button type="button" variant="ghost" className="mr-auto text-destructive" onClick={() => only ? setLastOne(true) : onDelete()}><Trash2 />Delete</Button>}
     <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
     <Button type="submit" className="companion-save" disabled={!c.name.trim()}>Save</Button>
    </div>
   </form>
  </DialogContent>
 </Dialog>
}
