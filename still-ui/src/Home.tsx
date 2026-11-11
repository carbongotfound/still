import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { Archive, ArchiveRestore, ArrowDownUp, Blocks, BookOpen, Brain, ChevronDown, Copy, ExternalLink, Folder, FolderOpen, MessageSquare, MoreHorizontal, Pencil, Plus, RotateCcw, Search, Settings2, SquarePen, Trash2, UserX, Users } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from "@/components/ui/context-menu"
import { AiLogo } from "./AiLogo"
import { Face, hueOf, type Companion } from "./Buddy"
import { lookKey, surprise } from "./look"
import { companionOf, isRunning, needsYou, type AiState, type Skill } from "./AiSidebar"
import { FileIcon, nameOf } from "./Files"
import { CrewCards, KIT_SKILLS, SharedReview, fromPremade, fromShared } from "./crew"
import { deleteAllChats, deleteChat, destroy, fire } from "./Undo"
import { PluginsPage, andList } from "./Plugins"
import { toast } from "sonner"

// The new tab page is Still's home: a slim rail on the left switches between the chat home and these pages. "library"
// is the Files page (saved files; it was called Library before Skills and Plugins got pages of their own).
export type HomeView = "home" | "chats" | "companions" | "skills" | "plugins" | "library"
const SETUP_ID = "setup"
type Send = (op: string, payload?: Record<string, unknown>) => void
/// A new companion: a surprise look, and the user names them.
export const randomCompanion = (): Companion => ({ id: "", name: "", face: "", color: "", job: "", mode: "default", look: lookKey(surprise()) })

export function HomeRail({ view, setView, profile, onSettings }: { view: HomeView; setView: (v: HomeView) => void; profile: string; onSettings: () => void }) {
 const item = (v: HomeView, label: string, Icon: typeof Users) => <button className="home-rail-item" aria-label={label} title={label} aria-current={view === v ? "page" : undefined} onClick={() => setView(v)}><Icon /></button>
 return <nav className="home-rail" aria-label="Home">
  <span className="still-mark is-small" aria-hidden><i /><i /></span>
  {item("home", "New chat", SquarePen)}
  {item("chats", "Chats", MessageSquare)}
  {item("skills", "Skills", BookOpen)}
  {item("plugins", "Plugins", Blocks)}
  {item("library", "Files", Folder)}
  <span className="home-rail-gap" />
  <button className="home-rail-item" aria-label="Settings" title="Settings" onClick={onSettings}><Settings2 /></button>
  <span className="chat-side-avatar" title={profile}>{(profile[0] ?? "S").toUpperCase()}</span>
 </nav>
}

/// Top center of the home: who you're working with, every other companion as a small face, and a way to add one. When
/// they don't all fit, the row scrolls sideways and keeps the one you're with in view.
export function CompanionSwitch({ ai, companion, onPick, onEdit }: { ai: AiState; companion: Companion; onPick: (id: string) => void; onEdit: (c: Companion) => void }) {
 const row = useRef<HTMLDivElement>(null)
 useEffect(() => { row.current?.querySelector(".mate-switch-on")?.scrollIntoView({ block: "nearest", inline: "nearest" }) }, [companion.id])
 // In the team's order, so a pick opens into the name pill where it stands and the last one closes (App.css)
 const shown = [...ai.companions ?? []]
 if (!shown.includes(companion)) shown.unshift(companion)
 return <div ref={row} className="mate-switch" role="radiogroup" aria-label="Who to work with">
  {shown.map(c => c === companion
   ? <button key={c.id} role="radio" aria-checked className="mate-switch-face mate-switch-on" title={"Edit " + c.name} onClick={() => onEdit(c)}><Face companion={c} size={24} /><b><span>{c.name}</span></b></button>
   : <button key={c.id} role="radio" aria-checked={false} className="mate-switch-face" title={c.name} aria-label={c.name} onClick={() => onPick(c.id)}><Face companion={c} size={24} /><b aria-hidden><span>{c.name}</span></b></button>)}
  <button className="mate-switch-more" aria-label="Hire a companion" title="Hire a companion" onClick={() => onEdit(randomCompanion())}><Plus /></button>
 </div>
}

const ago = (iso: string) => { const m = (Date.now() - Date.parse(iso)) / 6e4; return m < 60 ? Math.max(1, Math.round(m)) + "m" : m < 1440 ? Math.round(m / 60) + "h" : Math.round(m / 1440) + "d" }
const dayOf = (iso: string) => { const d = new Date(iso), now = new Date(); const days = Math.round((new Date(now.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 864e5); return days <= 0 ? "Today" : days === 1 ? "Yesterday" : days < 7 ? "This week" : "Earlier" }

/// A chat in a list: a click opens it in this Still tab; a middle click or the menu's Open in new tab opens it in a tab of its own.
export function ChatLink({ id, send, className, title, children }: { id: string; send: Send; className: string; title?: string; children: ReactNode }) {
 const own = () => send("chatOpen", { id, newTab: true })
 return <ContextMenu><ContextMenuTrigger asChild>
  <button className={className} title={title} onClick={() => send("chatOpen", { id })} onMouseDown={e => { if (e.button === 1) e.preventDefault() }} onAuxClick={e => { if (e.button === 1) own() }}>{children}</button>
 </ContextMenuTrigger><ContextMenuContent><ContextMenuItem onSelect={own}><ExternalLink />Open in new tab</ContextMenuItem></ContextMenuContent></ContextMenu>
}

export function ChatHistory({ ai, send, onNew }: { ai: AiState; send: Send; onNew: () => void }) {
 const [find, setFind] = useState("")
 const [only, setOnly] = useState<"" | "unread" | "needs" | "archived">("")
 const [who, setWho] = useState("")
 const [oldest, setOldest] = useState(false)
 const needs = (id: string) => needsYou(ai, id)
 const first = ai.companions?.[0]?.id
 const chats = ai.chats.filter(c => !c.from && (only === "archived") === !!c.archived && (only !== "unread" || c.unread) && (only !== "needs" || needs(c.id))
  && (!who || (c.companion || first) === who) && c.title.toLowerCase().includes(find.trim().toLowerCase()))
 if (oldest) chats.reverse()
 const groups = chats.reduce<[string, typeof chats][]>((all, c) => { const day = dayOf(c.updated); if (all.at(-1)?.[0] === day) all.at(-1)![1].push(c); else all.push([day, [c]]); return all }, [])
 const chip = (key: typeof only, label: string, dot?: string) => <button className="history-chip" aria-pressed={only === key} onClick={() => setOnly(only === key ? "" : key)}>{label}{dot && <i className={dot} />}</button>
 const mate = companionOf(ai, who)
 return <section className="home-page" aria-label="Chat History">
  <header className="home-page-head"><h1>Chat History</h1>
   {!ai.incognito && <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="More"><MoreHorizontal /></Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end"><DropdownMenuItem disabled={!ai.chats.length || !!ai.runs?.length} onSelect={() => deleteAllChats(send, ai.chats.length)} className="text-destructive"><Trash2 />Delete all chats</DropdownMenuItem></DropdownMenuContent></DropdownMenu>}
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
    <ChatLink id={c.id} send={send} className="history-open"><Face companion={companionOf(ai, c.companion)} size={30} mood={isRunning(ai, c.id) ? "working" : "idle"} /><b>{c.title}</b>
     {needs(c.id) ? <span className="history-needs">Needs input</span> : c.unread ? <i className="is-unread" aria-label="Unread" /> : isRunning(ai, c.id) ? <small>Working</small> : <small>{ago(c.updated)}</small>}</ChatLink>
    <button className="history-act" aria-label={c.archived ? "Unarchive " + c.title : "Archive " + c.title} title={c.archived ? "Unarchive" : "Archive"} onClick={() => send("chatArchive", { id: c.id, on: !c.archived })}>{c.archived ? <ArchiveRestore /> : <Archive />}</button>
    <button className="history-act" disabled={isRunning(ai, c.id)} aria-label={"Delete " + c.title} title="Delete" onClick={() => deleteChat(send, c)}><Trash2 /></button>
   </div>)}
  </div>)}
 </section>
}

/// The AI a companion runs on, for its badge: its own pick, or the one picked for chats.
const aiOf = (ai: AiState, c: Companion) => ai.harnesses.find(h => h.id === (c.ai || ai.harness))

export function CompanionsPage({ ai, send, onEdit, onMake, onChat, onHire, onMemory }: { ai: AiState; send: Send; onEdit: (c: Companion) => void; onMake: () => void; onChat: (id: string) => void; onHire: (c: Companion) => void; onMemory: (id: string) => void }) {
 const [shared, setShared] = useState<Companion | null>(null)
 useEffect(() => { // a companion someone shared (ProfilePanel's Share), pasted anywhere on the page
  const paste = (e: ClipboardEvent) => {
   const c = !(e.target as HTMLElement).closest?.("input, textarea") && fromShared(e.clipboardData?.getData("text") ?? "")
   if (c) setShared(c)
  }
  addEventListener("paste", paste); return () => removeEventListener("paste", paste)
 }, [send])
 return <section className="home-page" aria-label="Companions">
  {shared && <SharedReview companion={shared} onClose={() => setShared(null)} onHire={() => { send("companionSave", shared); toast(`Hired ${shared.name}. They start fresh: they don't know anything about you yet.`); setShared(null) }} />}
  <header className="home-page-head"><h1>Companions</h1><Button className="home-new" onClick={() => onEdit(randomCompanion())}><Plus />Hire a companion</Button></header>
  <p className="home-page-lead">Who you work with. Each one has a job, a way of talking, skills and a memory of you. Got one someone shared? Paste it here.</p>
  <div className="mate-grid">
   {ai.companions?.map(c => { const h = aiOf(ai, c); return <article key={c.id} className="mate-card" style={{ "--hue": hueOf(c) } as CSSProperties}>
    <button className="mate-portrait" aria-label={"Edit " + c.name} onClick={() => onEdit(c)}><Face companion={c} size={112} follow /><Pencil className="mate-edit" /></button>
    <div className="mate-info">
    <h3>{c.name}</h3>
    <p>{c.job || "No job yet. Tell them what they're good at."}</p>
    <span className="mate-badge">{h ? <><AiLogo id={h.id} size={14} />{h.name}{h.maker && !h.billing && ` · Your ${h.name} plan`}</> : "Pick your AI"}</span>
    {(() => { const known = c.memory?.filter(f => f.kind !== "chat").length ?? 0; return <button className="mate-memory" onClick={() => onMemory(c.id)}><Brain />{known ? `Remembers ${known} ${known === 1 ? "thing" : "things"}` : "What they remember"}</button> })()}
    <div className="mate-acts"><button className="mate-chat" onClick={() => onChat(c.id)}>Say hi</button>
     <button className="mate-fire" aria-label={`Fire ${c.name}`} onClick={() => fire(send, c, (ai.companions?.length ?? 0) <= 1)}><UserX />Fire</button></div>
    </div>
   </article> })}
  </div>
  <h2 className="home-page-sub">Hire for a role</h2>
  <p className="home-page-lead">Each one owns a part of your work and gets sharper as it learns about you. Hire one, then change anything you like.</p>
  <CrewCards have={ai.companions} onChat={onChat} onOwn={onMake} onPick={p => onHire(fromPremade(p))} />
 </section>
}

/// Reset a skill Still ships to its own version: the user's changes to it go.
export const resetSkill = (send: Send, k: Skill) => destroy({ key: "skill-reset:" + k.id, title: `Reset ${k.name}?`, body: `Your changes to ${k.name} go, and it's back to the version Still ships.`,
 action: "Reset skill", done: `${k.name} reset`, run: () => send("skillReset", { id: k.id }) })

/// Plugins: the apps page (Plugins.tsx), and adding a plugin from a link.
export function PluginsView({ ai, send }: { ai: AiState; send: Send }) {
 const [adding, setAdding] = useState(false)
 return <>
  <PluginsPage ai={ai} send={send} onAddPlugin={() => setAdding(true)} />
  {adding && <SkillImport send={send} onClose={() => setAdding(false)} />}
 </>
}

// Every skill Still ships, by role kit, for the Built-in tab (the kit files themselves, so it's every one, added or not).
const BUILT_IN = Object.entries(KIT_SKILLS).flatMap(([role, list]) => list.map(k => ({ id: k.id, role, name: k.name, description: k.line })))
const kitName = (role: string) => role.charAt(0).toUpperCase() + role.slice(1) + " kit"

/// Skills: My skills, grouped under the companion whose kit brought them, then the rest under All companions; and
/// Built-in, every skill Still ships. Every companion can use every skill and picks one by its description; the ⋯ menu
/// can limit one to some companions. Run skill starts a new chat with /its-id in the box.
export function SkillsPage({ ai, send, onRun }: { ai: AiState; send: Send; onRun: (k: Skill) => void }) {
 const [tab, setTab] = useState<"mine" | "built">("mine")
 const [find, setFind] = useState("")
 const [editing, setEditing] = useState<Skill | null>(null)
 const [limiting, setLimiting] = useState<Skill | null>(null)
 const q = find.trim().toLowerCase(), team = ai.companions ?? []
 const hit = (k: { id: string; name: string; description: string }) => `${k.name} ${k.id} ${k.description}`.toLowerCase().includes(q)
 const have = new Map((ai.skills ?? []).map(k => [k.id, k]))
 const roleOf = new Map(BUILT_IN.map(k => [k.id, k.role]))
 const makerOf = (k: Skill) => k.stock ? team.find(c => !!c.crew && c.crew === roleOf.get(k.id)) : undefined
 const nameOf = (id: string) => team.find(c => c.id === id)?.name
 const muted = (k: Skill) => [k.id === SETUP_ID ? "Every companion, on their first chat" : k.source ? "From " + k.source + (k.plugin ? ", with its programs" : "") : k.stock ? (k.edited ? "Built in, edited" : "Built in") : "Made by you",
  k.only?.length ? "Only " + andList(k.only.map(nameOf).filter((n): n is string => !!n)) : ""].filter(Boolean).join(" · ")
 const remove = (k: Skill) => destroy({ key: "skill:" + k.id, title: `Delete ${k.name}?`, action: "Delete skill", done: `Deleted ${k.name}`,
  body: "The skill goes, and no companion can use it anymore.", run: () => send("skillDelete", { id: k.id }) })
 const card = (k: Skill, foot: string, added = true) => <article key={k.id} className="skill-card" aria-label={k.name}>
  <div className="skill-card-head"><span className="skill-icon" aria-hidden><BookOpen /></span><h3>{k.name}</h3>
   <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="skill-more" aria-label={"More for " + k.name}><MoreHorizontal /></Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-52">
     {!added ? <DropdownMenuItem onSelect={() => send("skillAdd", { id: k.id })}><Plus />Add to my skills</DropdownMenuItem> : <>
      <DropdownMenuItem onSelect={() => setEditing(k)}><Pencil />Edit</DropdownMenuItem>
      {k.id !== SETUP_ID && <DropdownMenuItem onSelect={() => setLimiting(k)}><Users />Limit to companions…</DropdownMenuItem>}
      {k.id !== SETUP_ID && <DropdownMenuItem onSelect={() => { send("skillSave", { id: "", name: (k.name.slice(0, 55) + " copy").trim(), description: k.description, when: k.when, body: k.body }); toast(`Made a copy of ${k.name}.`) }}><Copy />Duplicate</DropdownMenuItem>}
      {k.stock && k.edited && <DropdownMenuItem onSelect={() => resetSkill(send, k)}><RotateCcw />Reset to Still's version</DropdownMenuItem>}
      {k.id !== SETUP_ID && <><DropdownMenuSeparator /><DropdownMenuItem className="text-destructive" onSelect={() => remove(k)}><Trash2 />Delete</DropdownMenuItem></>}
     </>}
    </DropdownMenuContent></DropdownMenu></div>
  <p className="skill-card-text">{k.description || "No description yet. Add one so companions know when to use it."}</p>
  <div className="skill-card-foot"><small>{foot}</small>{k.id !== SETUP_ID && <Button size="sm" variant="secondary" className="skill-run" onClick={() => { if (!added) send("skillAdd", { id: k.id }); onRun(k) }}>Run skill</Button>}</div>
 </article>
 const mine = (ai.skills ?? []).filter(k => k.id !== SETUP_ID && hit(k)).sort((a, b) => a.name.localeCompare(b.name))
 const groups: [Companion | null, Skill[]][] = [...team.map(c => [c, mine.filter(k => makerOf(k) === c)] as [Companion, Skill[]]), [null, mine.filter(k => !makerOf(k))]]
 const setup = have.get(SETUP_ID)
 const built = [...(setup && hit(setup) ? [setup] : []), ...BUILT_IN.filter(hit).map(b => have.get(b.id) ?? { ...b, when: "", body: "", stock: true })]
 return <section className="home-page skills-page" aria-label="Skills">
  <header className="home-page-head"><h1>Skills</h1><Button className="home-new" onClick={() => setEditing({ id: "", name: "", description: "", when: "", body: "" })}><Plus />New skill</Button></header>
  <p className="home-page-lead">Reusable instructions your companions can use.</p>
  <div className="skills-bar">
   <div className="skills-tabs" role="tablist" aria-label="Skills">
    <button role="tab" aria-selected={tab === "mine"} onClick={() => setTab("mine")}>My skills</button>
    <button role="tab" aria-selected={tab === "built"} onClick={() => setTab("built")}>Built-in</button>
   </div>
   <label className="skills-find"><Search /><input aria-label="Search skills" placeholder="Search skills..." value={find} onChange={e => setFind(e.target.value)} /></label>
  </div>
  {tab === "mine" ? <>
   {!mine.length && <p className="home-empty">{q ? `No skills match “${find.trim()}”.` : "No skills yet. Write one with New skill, or add one of Still's from Built-in."}</p>}
   {groups.filter(([, list]) => list.length).map(([c, list]) => <section key={c?.id ?? "all"} className="skill-group" aria-label={c ? c.name : "All companions"}>
    <h2>{c ? <Face companion={c} size={22} /> : <span className="skill-group-all" aria-hidden><Users /></span>}{c ? c.name : "All companions"}</h2>
    <div className="skill-grid">{list.map(k => card(k, muted(k)))}</div>
   </section>)}
  </> : <>
   {!built.length && <p className="home-empty">No skills match “{find.trim()}”.</p>}
   <div className="skill-grid">{built.map(k => { const role = roleOf.get(k.id), added = have.has(k.id)
    return card(k, k.id === SETUP_ID ? muted(k) : [role ? kitName(role) : "", added ? "In your skills" : ""].filter(Boolean).join(" · "), added) })}</div>
  </>}
  {editing && <SkillEditor skill={editing} onClose={() => setEditing(null)} onSave={k => { send("skillSave", k); setEditing(null) }} />}
  {limiting && <SkillLimit skill={limiting} team={team} onClose={() => setLimiting(null)} onSave={only => { send("skillLimit", { id: limiting.id, only }); setLimiting(null) }} />}
 </section>
}

/// Who can use a skill: every companion (the default), or only the ones ticked.
function SkillLimit({ skill, team, onClose, onSave }: { skill: Skill; team: Companion[]; onClose: () => void; onSave: (only: string[]) => void }) {
 const [some, setSome] = useState(!!skill.only?.length)
 const [on, setOn] = useState<string[]>(skill.only?.length ? skill.only : team.map(c => c.id))
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog skill-limit">
   <DialogHeader><DialogTitle>Who can use {skill.name}?</DialogTitle><DialogDescription>Every companion can use every skill, and picks one by its description. Limit this one if it's only for some of them.</DialogDescription></DialogHeader>
   <div className="skill-limit-pick" role="radiogroup" aria-label={"Who can use " + skill.name}>
    <label><input type="radio" name="skill-limit" checked={!some} onChange={() => setSome(false)} />Every companion</label>
    <label><input type="radio" name="skill-limit" checked={some} onChange={() => setSome(true)} />Only some companions</label>
   </div>
   {some && <ul className="skill-limit-list" aria-label="Companions">{team.map(c => <li key={c.id}><label>
    <input type="checkbox" aria-label={c.name} checked={on.includes(c.id)} onChange={e => setOn(e.target.checked ? [...on, c.id] : on.filter(x => x !== c.id))} /><Face companion={c} size={22} />{c.name}</label></li>)}</ul>}
   <div className="companion-actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="button" disabled={some && !on.length} onClick={() => onSave(some ? on : [])}>Save</Button></div>
  </DialogContent>
 </Dialog>
}

type FoundSkill = { key: number; name: string; description: string; body: string; notes: string[]; added: boolean }
// A plugin or skills from a GitHub repository or an npm package: Still looks first, shows each SKILL.md it found with what
// comes with it, and adds only the ones you tick, with a plugin's programs (MainWindow.SkillImport.cs, Mac SkillImport.swift).
export function SkillImport({ send, onClose }: { send: Send; onClose: () => void }) {
 const [link, setLink] = useState("")
 const [busy, setBusy] = useState(false)
 const [found, setFound] = useState<{ source?: string; skills?: FoundSkill[]; error?: string } | null>(null)
 const [picked, setPicked] = useState<number[]>([])
 const [shown, setShown] = useState<number | null>(null)
 useEffect(() => {
  const listener = (e: MessageEvent) => {
   const m = e.data
   if (m?.kind !== "skillImport") return
   setBusy(false); setFound(m); setShown(null)
   setPicked(((m.skills ?? []) as FoundSkill[]).filter(k => !k.added).map(k => k.key))
  }
  window.chrome?.webview?.addEventListener("message", listener)
  return () => window.chrome?.webview?.removeEventListener("message", listener)
 }, [])
 const look = () => { if (!link.trim() || busy) return; setBusy(true); setFound(null); send("skillImportLook", { link: link.trim() }) }
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog skill-dialog">
   <DialogHeader><DialogTitle>Add a plugin from a link</DialogTitle><DialogDescription>Paste a GitHub repository or an npm package: a plugin, or skills. Still shows what's in it, and you choose what to add.</DialogDescription></DialogHeader>
   <form className="companion-form" onSubmit={e => { e.preventDefault(); look() }}>
    <label><span>Link</span><Input autoFocus aria-label="Plugin link" placeholder="github.com/owner/repo or npm:package" value={link} onChange={e => { setLink(e.target.value); setFound(null) }} /></label>
    {busy && <p className="skill-import-note">Looking…</p>}
    {found?.error && <p className="skill-import-note is-error" role="alert">{found.error}</p>}
    {found?.skills && <div className="skill-import-list" aria-label="Skills found">
     <p className="skill-import-note">From {found.source}. A skill is instructions your companions follow, so add only ones from people you trust.</p>
     {found.skills.map(k => <div key={k.key} className="skill-import-row">
      <label className="skill-import-pick"><input type="checkbox" aria-label={"Add " + k.name} checked={picked.includes(k.key)} onChange={e => setPicked(p => e.target.checked ? [...p, k.key] : p.filter(x => x !== k.key))} /><b>{k.name}</b></label>
      {k.description && <small>{k.description}</small>}
      {k.notes.map(n => <small key={n} className="skill-import-warn">{n}</small>)}
      <button type="button" className="plug-all" onClick={() => setShown(shown === k.key ? null : k.key)}>{shown === k.key ? "Hide steps" : "Show steps"}</button>
      {shown === k.key && <pre className="skill-import-body">{k.body}</pre>}
     </div>)}
    </div>}
    <div className="companion-actions">
     <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
     {found?.skills ? <Button type="button" disabled={!picked.length} onClick={() => { send("skillImportAdd", { keys: picked }); onClose() }}>{picked.length > 1 ? `Add ${picked.length} skills` : "Add skill"}</Button>
      : <Button type="submit" disabled={!link.trim() || busy}>Look</Button>}
    </div>
   </form>
  </DialogContent>
 </Dialog>
}

export function SkillEditor({ skill, onClose, onSave }: { skill: Skill; onClose: () => void; onSave: (k: Skill) => void }) {
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
 return <section className="home-page" aria-label="Files">
  <header className="home-page-head"><h1>Files</h1></header>
  {!ai.files?.length ? <div className="home-empty is-big"><Folder /><p>Nothing here yet. Ask a companion for a table or notes, and the file lands here.</p></div> : <>
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
    <button className="history-act" aria-label={"Delete " + f.name} title="Delete" onClick={() => destroy({ key: "file:" + f.path, title: `Delete ${nameOf(f.path)}?`, body: "The file is deleted from this computer, not moved to the trash.", action: "Delete file", done: "File deleted", run: () => send("fileDelete", { path: f.path }) })}><Trash2 /></button>
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

