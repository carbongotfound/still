import { useEffect, useRef, useState, type CSSProperties } from "react"
import { CalendarClock, Check, ChevronDown, ChevronRight, Copy, Dices, Eraser, FileText, FolderOpen, Hand, KeyRound, MessageSquare, MoreHorizontal, Palette, Pencil, Plus, RotateCcw, Share2, SlidersHorizontal, Sparkles, SquareArrowOutUpRight, Trash2, Undo2, UserX, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Face, hueOf, type Companion, type Mode, type Personality, type ReplyLength, type Routine } from "./Buddy"
import { AiLogo } from "./AiLogo"
import { LookEditor } from "./LookEditor"
import { MemorySettings } from "./Memory"
import { PluginChip } from "./Plugins"
import { FileCard } from "./Files"
import { LIBRARY, ROLE_TEXT, SHARE_KIND, fromPremade, premadeOf } from "./crew"
import { SkillEditor, resetSkill } from "./Home"
import { deleteChat, destroy, fire } from "./Undo"
import { generate } from "./generate"
import { lookKey, surprise } from "./look"
import { andList } from "./Plugins"
import { cn } from "@/lib/utils"
import { TierSettings, isRunning, type AiState, type Skill } from "./AiSidebar"

type Send = (op: string, payload?: Record<string, unknown>) => void
// A companion's profile, opened from its mascot: everything about it on tabs, saved as you change it. "Make your own"
// opens the same panel on a draft: nothing is saved until Hire, and the tabs that need a hired companion stay hidden.
const TABS = [["general", "General"], ["skills", "Skills & plugins"], ["routines", "Routines"], ["files", "Files"], ["memory", "Memory"], ["model", "AI"]] as const
const DRAFT_TABS = ["general", "skills", "files", "model"]
const MODES: [Mode, string, string][] = [["efficient", "Quick", "Short and fast. Good for lookups and small jobs."], ["default", "Everyday", "The right depth for most things."], ["expert", "Thorough", "Takes longer and checks more. For research and big tasks."]]
const PERSONALITIES: [Personality, string, string][] = [["direct", "Direct", "Gets to the point"], ["warm", "Warm", "Friendly and encouraging"], ["playful", "Playful", "Light, with a little humor"], ["formal", "Formal", "Polished and courteous"]]
const LENGTHS: [ReplyLength, string, string][] = [["short", "Short", "A few lines, answer first"], ["balanced", "Balanced", "As long as the task needs"], ["detailed", "Detailed", "Full answers with the reasoning"]]
const SETUP = "setup" // every companion's first-chat skill: always on, never removed (the hosts load it)
const DAYS = ["S", "M", "T", "W", "T", "F", "S"], DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
const WEEKDAYS = [1, 2, 3, 4, 5]
const newId = () => crypto.randomUUID().replace(/-/g, "").slice(0, 10)
const when = (r: Routine) => (r.days.length === 7 ? "Every day" : r.days.join() === WEEKDAYS.join() ? "Weekdays" : r.days.join() === "0,6" ? "Weekends" : r.days.map(d => DAY_NAMES[d]).join(", ")) + " at " + r.time
/// What Share copies: the companion without anything personal (no memory, folder, plugins or keys).
const shareOf = (c: Companion) => JSON.stringify({ kind: SHARE_KIND, v: 1, name: c.name, look: c.look ?? "", job: c.job, tone: c.tone ?? "", mode: c.mode ?? "default", crew: c.crew ?? "",
 role: c.role ?? "", personality: c.personality ?? "", length: c.length ?? "balanced" })

export function ProfilePanel({ ai, id, draft, send, onPick, onClose, onOpenFile, onSkills, onHire, onChat, tab: opening = "general" }: {
 ai: AiState; id: string; send: Send; onPick: (id: string) => void; onClose: () => void; onOpenFile: (path: string) => void; onSkills: () => void
 onChat?: (id: string) => void // a new chat with them, when they have none to open
 tab?: string // the tab it opens on ("model": their AI settings)
 draft?: Companion; onHire?: (c: Companion) => void // "Make your own": a companion not hired yet
}) {
 const saved: (Companion & { instructions?: string }) | undefined = draft ?? ai.companions?.find(c => c.id === id)
 const [c, setC] = useState(saved)
 const [tab, setTab] = useState(opening)
 const [styling, setStyling] = useState(false)
 const [made, setMade] = useState<string[] | null>(null) // the skills the generator just picked, to say so
 const [skill, setSkill] = useState<Skill | null>(null) // a skill open in the editor
 const [closing, setClosing] = useState(false)
 const name = useRef<HTMLInputElement>(null), typing = useRef(0)
 useEffect(() => { setC(saved) }, [id, !!saved]) // eslint-disable-line react-hooks/exhaustive-deps
 const close = () => { setClosing(true); setTimeout(onClose, 160) }
 const latest = useRef(c); latest.current = c
 useEffect(() => { // the folder picked in the system's own dialog
  const got = (e: MessageEvent) => { if (e.data?.kind === "folder" && latest.current) { const next = { ...latest.current, folder: e.data.data.path }; setC(next); if (!draft) send("companionSave", next) } }
  window.chrome?.webview?.addEventListener("message", got); return () => window.chrome?.webview?.removeEventListener("message", got)
 }, [send, draft])
 useEffect(() => {
  // Esc closes, unless a menu or a dialog over the panel takes it first
  const key = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector(":is([role=menu],[role=alertdialog],[data-slot=dialog-content])[data-state=open]")) close() }
  addEventListener("keydown", key); return () => removeEventListener("keydown", key)
 }) // eslint-disable-line react-hooks/exhaustive-deps
 if (!saved || !c) return null
 const save = (next: Companion & { instructions?: string }, later = false) => {
  setC(next); clearTimeout(typing.current)
  if (draft) return // saved on Hire
  const go = () => send("companionSave", { ...next })
  if (later) typing.current = window.setTimeout(go, 500); else go()
 }
 const premade = premadeOf(c), only = (ai.companions?.length ?? 0) <= 1, label = c.name.trim() || "they"
 const harness = ai.harnesses.find(h => h.id === (c.ai || ai.harness))
 const state = (hid: string) => { const h = ai.harnesses.find(x => x.id === hid); return !h ? "" : !h.installed || h.status === "missing" ? "Not installed" : h.status === "signedOut" ? "Sign in first" : "" }
 const chatsOf = new Set(ai.chats.filter(x => x.companion === c.id).map(x => x.id))
 // Their chat: the one open in the side chat when it's theirs, or their latest. Clear chat deletes it (with Undo).
 const chat = ai.chats.find(x => x.id === ai.chatId && x.companion === c.id) ?? ai.chats.filter(x => x.companion === c.id && !x.from).sort((a, b) => b.updated.localeCompare(a.updated))[0]
 const tier = harness && ai.tiers?.[harness.id]?.[c.mode ?? "default"], model = ai.models?.find(m => m.harness === harness?.id && m.id === (ai.advanced ? ai.model : tier?.model))
 const runsOn = harness ? [harness.name, model?.id ? model.name : "", ai.advanced ? "" : MODES.find(m => m[0] === (c.mode ?? "default"))?.[1]].filter(Boolean).join(" · ") : "No AI picked yet"
 const api = harness?.api ? ai.apis?.providers.find(p => p.id === harness.id) : undefined
 const aiSettings = () => setTab("model")
 const files = (ai.files ?? []).filter(f => chatsOf.has(f.chat))
 const plugins = ai.plugins, pluginsReady = !!plugins?.key && plugins.status === "ok"
 const routines = c.routines ?? []
 // Skills they can use: Setup first (always on), then the user's skills, and in a draft the library skills it picked.
 const mine = (ai.skills ?? []).filter(k => k.id !== SETUP), setup = ai.skills?.find(k => k.id === SETUP)
 const library = draft ? LIBRARY.filter(k => c.skills?.includes(k.id) && !mine.some(m => m.id === k.id)).map(k => ({ id: k.id, name: k.name, description: k.text, when: "", body: "" })) : []
 const suggest = () => { // the generator: what they wrote becomes starting instructions, and 3 or 4 library skills
  const g = generate(c.job.split("\n\nHow you work:")[0], c.role ?? "", LIBRARY, ROLE_TEXT)
  save({ ...c, job: g.job, skills: g.skills }); setMade(g.skills.map(id => LIBRARY.find(k => k.id === id)?.name ?? id))
 }
 const hire = () => { if (c.name.trim()) onHire?.({ ...c, name: c.name.trim(), role: c.role?.trim() ?? "" }) }
 const duplicate = () => { const copy = { ...c, id: newId(), name: (c.name.slice(0, 21) + " 2").trim(), crew: "", routines: [] }; send("companionSave", copy); onPick(copy.id); toast(`Made ${copy.name}, a copy of ${c.name}.`) }
 const share = () => navigator.clipboard.writeText(shareOf(c)).then(() => toast(`Copied ${c.name}. Paste it on anyone's Companions page in Still to add them. Nothing they remember about you is in it.`), () => toast("Couldn't copy. Try again."))
 return <>
  <div className={cn("profile-scrim", closing && "is-closing")} onClick={close} />
  <aside className={cn("profile-panel", closing && "is-closing")} role="dialog" aria-modal aria-label={draft ? "Make your own companion" : `${c.name}'s profile`} style={{ "--hue": hueOf(c) } as CSSProperties}>
   {draft ? <header className="profile-head"><Face companion={c} size={28} /><b className="profile-draft-title">{c.name.trim() ? `Make ${c.name.trim()}` : "Make your own"}</b>
    <Button variant="ghost" size="icon-sm" className="ml-auto" aria-label="Close" onClick={close}><X /></Button></header> :
   <header className="profile-head">
    <DropdownMenu><DropdownMenuTrigger asChild><button className="profile-switch" aria-label={`${c.name}: AI settings and companions`}><Face companion={c} size={28} /><b>{c.name}</b><ChevronDown /></button></DropdownMenuTrigger>
     <DropdownMenuContent align="start" className="w-64 profile-menu">
      <DropdownMenuItem onSelect={aiSettings}><SlidersHorizontal /><span className="profile-menu-two">AI settings<small>{runsOn}</small></span></DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuLabel>Switch to</DropdownMenuLabel>
      {ai.companions?.map(x => <DropdownMenuItem key={x.id} onSelect={() => onPick(x.id)}><Face companion={x} size={20} />{x.name}{x.id === c.id && <Check className="ml-auto" />}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu>
    <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" className="ml-auto" aria-label="More"><MoreHorizontal /></Button></DropdownMenuTrigger>
     <DropdownMenuContent align="end" className="w-60 profile-menu">
      <DropdownMenuItem onSelect={aiSettings}><SlidersHorizontal />AI settings</DropdownMenuItem>
      <DropdownMenuItem onSelect={() => setStyling(true)}><Palette />Edit look</DropdownMenuItem>
      <DropdownMenuItem onSelect={() => { setTab("general"); setTimeout(() => { name.current?.focus(); name.current?.select() }, 50) }}><Pencil />Rename</DropdownMenuItem>
      <DropdownMenuItem onSelect={duplicate}><Copy />Duplicate</DropdownMenuItem>
      {saved?.setup !== "pending" && <DropdownMenuItem onSelect={() => send("companionSetupAgain", { companion: c.id })}><Hand />Introduce yourself again</DropdownMenuItem>}
      {premade && <DropdownMenuItem onSelect={() => { const before = c; destroy({ key: "reset:" + c.id, title: `Reset ${c.name}?`, action: "Reset", done: `${c.name} reset`,
       body: `Their name, look, instructions, way of talking and thinking go back to how ${premade.name} started. What they remember about you, their skills and routines stay.`,
       onConfirm: () => save({ ...c, ...fromPremade(premade, c.id), skills: c.skills, routines: c.routines, folder: c.folder, ai: c.ai, instructions: "" }), run: () => {}, undo: () => save(before) }) }}><RotateCcw />Reset to how {premade.name} started</DropdownMenuItem>}
      <DropdownMenuSeparator />
      {chat ? <DropdownMenuItem onSelect={() => { send("chatOpen", { id: chat.id, newTab: true }); close() }}><SquareArrowOutUpRight />Open chat in a tab</DropdownMenuItem>
       : onChat && <DropdownMenuItem onSelect={() => { onChat(c.id); close() }}><MessageSquare />Chat with {c.name}</DropdownMenuItem>}
      {chat && <DropdownMenuItem disabled={isRunning(ai, chat.id)} onSelect={() => deleteChat(send, chat)}><Eraser />Clear chat</DropdownMenuItem>}
      <DropdownMenuItem onSelect={close}><X />Close panel</DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem variant="destructive" onSelect={() => fire(send, c, only, close)}><Trash2 />Fire {c.name}</DropdownMenuItem>
     </DropdownMenuContent></DropdownMenu>
    <Button variant="ghost" size="icon-sm" aria-label="Close" onClick={close}><X /></Button>
   </header>}
   <Tabs value={tab} onValueChange={setTab} className="profile-tabs">
    <TabsList className="profile-tablist">{TABS.filter(([v]) => !draft || DRAFT_TABS.includes(v)).map(([v, t]) => <TabsTrigger key={v} value={v}>{t}</TabsTrigger>)}</TabsList>
    <div className="profile-body">
     <TabsContent value="general">
      <div className="profile-stage"><Face companion={c} size={196} follow />
       <div className="profile-stage-actions">
        <Button size="sm" variant="secondary" onClick={() => setStyling(true)}><Palette />Edit look</Button>
        {draft ? <Button size="sm" variant="secondary" onClick={() => save({ ...c, look: lookKey(surprise()) })}><Dices />Surprise me</Button>
         : <Button size="sm" variant="secondary" onClick={share}><Share2 />Share</Button>}
       </div>
      </div>
      <label className="profile-field"><span>Name</span><Input ref={name} autoFocus={!!draft} maxLength={24} value={c.name} onChange={e => setC({ ...c, name: e.target.value })} onBlur={() => c.name.trim() ? save({ ...c, name: c.name.trim() }) : !draft && setC(saved)} /></label>
      <label className="profile-field"><span>Role <small>Optional. Shows before the name, like {(c.role?.trim() || premade?.role || "Researcher") + " " + (c.name.trim() || "Maya")}.</small></span>
       <Input maxLength={30} value={c.role ?? ""} placeholder={premade?.role ?? "For example: Researcher"} onChange={e => save({ ...c, role: e.target.value }, true)} /></label>
      <label className="profile-field"><span>{premade ? `What ${label} does for you` : "Instructions"}</span>
       <textarea rows={premade ? 3 : 6} maxLength={1000} value={c.job} placeholder={`What ${c.name.trim() || "they"} does for you inside Still. For example: "Find me the best price before I buy anything, and show me where."`} onChange={e => { save({ ...c, job: e.target.value }, true); setMade(null) }} /></label>
      {draft && <div className="profile-suggest"><Button size="sm" variant="outline" disabled={!c.job.trim() && !c.role?.trim()} onClick={suggest}><Sparkles />Suggest instructions and skills</Button>
       <p className="profile-note">{made ? `Added ${made.length} skills from Still's library: ${andList(made)}. Change anything before you hire.` : "Write what they're for, then Still drafts how they work and picks skills to match."}</p></div>}
      <div className="profile-field"><span>Personality</span>
       <div className="profile-modes is-row" role="radiogroup" aria-label="Personality">{PERSONALITIES.map(([p, t, d]) => <button key={p} role="radio" aria-checked={c.personality === p} onClick={() => save({ ...c, personality: c.personality === p ? "" : p })}><b>{t}</b><small>{d}</small></button>)}</div>
      </div>
      <label className="profile-field"><span>How {label} talks, in your words</span>
       <textarea rows={2} maxLength={600} value={c.tone ?? ""} placeholder="For example: upbeat and quick, with a joke now and then." onChange={e => save({ ...c, tone: e.target.value }, true)} /></label>
      <div className="profile-field"><span>Reply length</span>
       <div className="profile-modes is-row" role="radiogroup" aria-label="Reply length">{LENGTHS.map(([l, t, d]) => <button key={l} role="radio" aria-checked={(c.length ?? "balanced") === l} onClick={() => save({ ...c, length: l })}><b>{t}</b><small>{d}</small></button>)}</div>
      </div>
      {premade && ROLE_TEXT[premade.id] && <>
       <div className="profile-rows">
        <button type="button" onClick={() => setTab("skills")}><span>Skills</span><b>{c.skills?.length ?? 0}</b><ChevronRight /></button>
        <button type="button" onClick={() => setTab("routines")}><span>Routines</span><b>{routines.length}</b><ChevronRight /></button>
       </div>
       <label className="profile-field is-instructions"><span>Instructions</span>
        <textarea rows={14} maxLength={8000} spellCheck={false} value={c.instructions || ROLE_TEXT[premade.id]} onChange={e => save({ ...c, instructions: e.target.value.trim() === ROLE_TEXT[premade.id] ? "" : e.target.value }, true)} /></label>
       {saved?.joinSection && c.instructions && <JoinSection text={c.instructions} label={label} onApply={apply => send("instructionsJoin", { companion: c.id, apply })} />}
       <div className="profile-instructions-foot"><p className="profile-note">{c.instructions ? "Your edit." : `Still's version for ${premade.role}.`} {label} follows these in every chat.</p>
        {!!c.instructions && <Button size="sm" variant="ghost" onClick={() => save({ ...c, instructions: "" })}><RotateCcw />Reset to Still's version</Button>}</div>
      </>}
      {!draft && <div className="profile-fire"><div><b>Fire {c.name}</b><small>They go, with what they remember about you and their routines. Your chats with them stay.</small></div>
       <Button variant="outline" size="sm" className="team-fire" aria-label={"Fire " + c.name} onClick={() => fire(send, c, only, close)}><UserX />Fire</Button></div>}
     </TabsContent>
     <TabsContent value="skills">
      <section className="profile-section"><h4>Skills they can use</h4>
      <p className="profile-lead">{label} sees this list and loads a skill when a task fits it. You can also use any skill with /its-name in a message.</p>
      <ul className="profile-list">
       {setup && <li><div><b>{setup.name}</b><small>Runs once, on {label}'s first chat. You can edit it, not turn it off.</small></div><SkillActs k={setup} onEdit={setSkill} send={send} /></li>}
       {[...library, ...mine].map(k => { const on = !!c.skills?.includes(k.id); return <li key={k.id}>
        <div><b>{k.name}</b><small>{k.description}</small></div>
        {!library.includes(k) && <SkillActs k={k} onEdit={setSkill} send={send} />}
        <Switch checked={on} aria-label={`${k.name} for ${c.name}`} onCheckedChange={v => save({ ...c, skills: v ? [...(c.skills ?? []), k.id] : (c.skills ?? []).filter(x => x !== k.id) })} />
       </li> })}
      </ul>
      {!mine.length && !library.length && <Empty text="No other skills yet. Write one in Skills & plugins, then turn it on here." action="Open Skills & plugins" onAction={onSkills} />}
      </section>
      {!draft && <section className="profile-section is-plugins"><h4>Plugins</h4>
      {!pluginsReady ? <Empty text={`Plugins let ${label} work in your apps, like Gmail, Calendar and Slack. They stay off until you add your own Composio key.`} action="Set up plugins" onAction={onSkills} />
       : plugins!.connected.length ? <><p className="profile-lead">Apps {label} can use. Reading goes ahead. Anything that sends, posts, deletes, pays or changes data asks you first.</p>
        <ul className="profile-list">{plugins!.connected.map(p => { const on = !saved.pluginsOff?.includes(p.slug); return <li key={p.id}>
         <PluginChip slug={p.slug} name={p.name} />
         <Switch checked={on} aria-label={`${p.name} for ${c.name}`} onCheckedChange={v => send("pluginToggle", { companion: c.id, slug: p.slug, on: v })} />
        </li> })}</ul></>
       : <Empty text="No apps connected yet." action="Connect an app" onAction={onSkills} />}
      </section>}
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
      {!draft && <section className="profile-section"><h4>Made by {c.name}</h4>
       {files.length ? <div className="profile-files">{files.map(f => <FileCard key={f.path} path={f.path} send={send} onOpen={onOpenFile} />)}</div>
        : <p className="profile-note">Nothing yet. Files {label} saves in a chat show up here.</p>}
      </section>}
     </TabsContent>
     <TabsContent value="memory"><MemorySettings companions={[saved]} send={send} />
      {!!saved.knowledge?.length && <section className="profile-section"><h4>Knowledge files</h4>
       <p className="profile-lead">The working notes of {label}'s job, kept on this computer. {label} fills them in as you work together and reads them at the start of every chat.</p>
       <ul className="profile-knowledge">{saved.knowledge.map(n => <li key={n.id}><FileText aria-hidden /><div><b>{n.name}</b><small>{n.about}</small>
        {n.text ? <div className="profile-knowledge-text" tabIndex={0}>{n.text}</div> : <p className="profile-note">Empty so far.</p>}
        {!!n.revisions && <Button size="xs" variant="ghost" onClick={() => send("knowledgeUndo", { companion: saved.id, file: n.id })}><Undo2 />Undo last change</Button>}</div></li>)}</ul></section>}
     </TabsContent>
     <TabsContent value="model">
      <label className="profile-field"><span>Runs on</span><span className="ai-select"><AiLogo id={c.ai || ai.harness} size={20} /><select className="companion-select" value={c.ai ?? ""} onChange={e => save({ ...c, ai: e.target.value })}>
       <option value="">Your AI{harness && !c.ai ? ` (${harness.name})` : ""}</option>
       {ai.harnesses.filter(h => !h.secondary || h.id === c.ai).map(h => <option key={h.id} value={h.id}>{h.name}{state(h.id) && " · " + state(h.id)}</option>)}
      </select></span></label>
      {c.ai && state(c.ai) && <p className="profile-note">{ai.harnesses.find(h => h.id === c.ai)?.name} isn't ready yet. Set it up from the chat sidebar, and {label} can start.</p>}
      {api && <div className="profile-field"><span>API key</span>
       <div className="profile-key"><KeyRound aria-hidden /><span>{api.hasKey ? <>Key ending in <code>{api.keyEnd}</code>{api.refused && " · Not accepted"}</> : api.noKey ? "No key needed" : "No key yet"}</span>
        {!api.noKey && <Button size="sm" variant="outline" onClick={() => { close(); send("openPanel", { name: "settings", value: "models" }) }}>{api.hasKey ? "Change key" : "Add key"}</Button>}</div></div>}
      <div className="profile-field"><span>Default mode <small>How hard {label} thinks in a new chat.</small></span>
       <div className="profile-modes" role="radiogroup" aria-label="Default mode">{MODES.map(([m, t, d]) => <button key={m} role="radio" aria-checked={(c.mode ?? "default") === m} onClick={() => save({ ...c, mode: m })}><b>{t}</b><small>{d}</small></button>)}</div>
      </div>
      {harness && ai.tiers?.[harness.id] && <div className="profile-field"><span>Model and effort for each mode <small>{harness.name}'s picks, the same for every companion on it.</small></span>
       <TierSettings ai={ai} send={send} only={harness.id} /></div>}
     </TabsContent>
    </div>
   </Tabs>
   {draft && <footer className="profile-foot"><Button variant="ghost" onClick={close}>Cancel</Button><Button disabled={!c.name.trim()} onClick={hire}>{c.name.trim() ? `Hire ${c.name.trim()}` : "Hire"}</Button></footer>}
  </aside>
  {skill && <SkillEditor skill={skill} onClose={() => setSkill(null)} onSave={k => { send("skillSave", k); setSkill(null) }} />}
  {styling && <LookEditor companion={c} onClose={() => setStyling(false)} onSave={look => { save({ ...c, look }); setStyling(false) }} />}
 </>
}

/// A skill's Edit, and Reset when it's one Still ships and the user changed it.
function SkillActs({ k, onEdit, send }: { k: Skill; onEdit: (k: Skill) => void; send: Send }) {
 return <>
  {k.stock && k.edited && <Button variant="ghost" size="icon-xs" aria-label={`Reset ${k.name} to Still's version`} title="Reset to Still's version" onClick={() => resetSkill(send, k)}><RotateCcw /></Button>}
  <Button variant="ghost" size="icon-xs" aria-label={"Edit " + k.name} title="Edit" onClick={() => onEdit(k)}><Pencil /></Button>
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

/// The old "When you join the team" section in Instructions the user edited before 2.10: how a companion opens its first
/// chat is the Setup skill's now, so the profile offers to take it out, showing exactly what goes.
function JoinSection({ text, label, onApply }: { text: string; label: string; onApply: (apply: boolean) => void }) {
 const at = text.indexOf("## When you join the team"), end = text.indexOf("\n## ", at + 5)
 if (at < 0) return null
 const gone = text.slice(at, end > 0 ? end + 1 : undefined).trim()
 return <div className="profile-join" role="group" aria-label="Instructions update">
  <p className="profile-note">How {label} opens a first chat is the Setup skill's now, so this section of your instructions isn't needed. Remove it?</p>
  <pre className="profile-diff">{gone.split("\n").map((l, i) => <del key={i}>{"- " + l + "\n"}</del>)}</pre>
  <div><Button size="sm" onClick={() => onApply(true)}>Remove it</Button><Button size="sm" variant="ghost" onClick={() => onApply(false)}>Keep mine</Button></div>
 </div>
}
