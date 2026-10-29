import { useEffect, useRef, useState, type CSSProperties, type ReactElement, type ReactNode } from "react"
import { ArrowLeft, ArrowUp, BookOpen, Brain, Camera, Check, ChevronDown, CircleCheck, Coffee, Copy, ExternalLink, Eye, FileText, Gauge, Globe, Keyboard, Lightbulb, ListTodo, LockKeyhole, Luggage, MousePointer2, MoveVertical, Plus, Rabbit, Save, Search, Tag, Maximize2, MessageSquarePlus, Settings2, ShieldCheck, Square, Trash2, X, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group"
import { Select, SelectContent, SelectGroup, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { CollisionBoundary } from "@/components/ui/collision"
import { fadeTop } from "@/lib/utils"
import { AiLogo } from "./AiLogo"
import { toast } from "sonner"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Switch } from "@/components/ui/switch"
import { FALLBACK, Face, hueOf, type Companion, type Mode, type Mood } from "./Buddy"
import { starters } from "./crew"
import { Markdown } from "./Markdown"
import { FileCard, type LibFile } from "./Files"
import { Approvals, type Approval, type AuditEntry, type Rule } from "./Permissions"
import type { PluginsState } from "./Plugins"

type Harness = { id: string; name: string; app: string; maker: string; installed: boolean; status: string; installer: string; installCommand: string; site: string; secondary?: boolean }
export type AiState = {
 open: boolean; harness: string; busy: boolean; error: string; profile: string; harnesses: Harness[]
 runs?: Run[]; interrupted?: string[]; queued?: string[]; files?: LibFile[]; worked?: number
 setup: { line: string; url: string; code: string }; pending: boolean
 models?: { harness: string; id: string; name: string; efforts: string[] }[]; model: string; effort: string; usage: string
 chatId?: string; chatHarness?: string; chatCompanion?: string; messages: { role: string; text: string }[]
 question?: { text: string; options: string[]; page?: string | null } | null; companions?: Companion[]
 chats: { id: string; title: string; harness: string; updated: string; companion?: string; unread?: boolean; archived?: boolean; noMemory?: boolean }[]
 advanced?: boolean; skills?: Skill[]
 approvals?: Approval[]; audit?: AuditEntry[]; permissions?: Rule[]; sensitiveSites?: string[]
 plugins?: PluginsState
}
export type Skill = { id: string; name: string; description: string; when: string; body: string }
// A chat at work. Any number run at once.
export type Run = { id: string; started: string; question?: string | null; options?: string[] | null; asks?: { id: string; what: string; site: string }[] }
export const isRunning = (ai: AiState | undefined, id?: string) => !!id && !!ai?.runs?.some(r => r.id === id)
const waits = (r: Run) => !!r.question || !!r.asks?.length
export const needsYou = (ai: AiState | undefined, id?: string) => !!id && !!ai?.runs?.some(r => r.id === id && waits(r))
type Send = (op: string, payload?: Record<string, unknown>) => void
type TabRef = { id: string; title: string; url: string; inChat?: string; chatId?: string; isPrivate?: boolean }

const IDEAS = [
 [FileText, "Sum up this page", "Summarize this page in a few short bullet points."],
 [Tag, "Find it cheaper", "Find what's on this page cheaper somewhere else, and show me where."],
 [Luggage, "Plan a trip", "Help me plan a weekend trip. Ask me where I'm starting from and what I like first."],
 [Lightbulb, "Explain it simply", "Explain this page simply, like I'm new to the topic."],
] as const
const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url } }
/// What the user likes to be called, from what their companion remembers (setup saves it as the "name" fact).
export const calledBy = (c?: Companion) => c?.memory?.find(f => f.key === "name")?.text.match(/^Likes to be called (.+?)\.?$/)?.[1]
const settingUp = (s?: string) => s === "installing" || s === "signingIn"
// "" = not checked yet, which never blocks a chat
const statusOf = (h?: Harness) => !h ? "" : h.status || (h.installed ? "" : "missing")
const ready = (h: Harness) => h.installed && !["missing", "signedOut"].includes(statusOf(h))
export const clock = (s: number) => s < 60 ? s + "s" : Math.floor(s / 60) + "m " + String(s % 60).padStart(2, "0") + "s"
export const since = (iso?: string) => iso ? Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000)) : 0
// Each step's icon, from how its label starts.
const STEP_ICONS: [RegExp, LucideIcon][] = [[/^Loaded skill/, BookOpen], [/^(Read|Looked)/, Eye], [/^Clicked/, MousePointer2], [/^Typed/, Keyboard],
 [/^Scrolled/, MoveVertical], [/^Saved/, Save], [/^Took a screenshot/, Camera], [/^(Opened|Went|Reloaded|Switched|Closed|Waited)/, Globe]]
const stepIcon = (step: string) => STEP_ICONS.find(([re]) => re.test(step))?.[1] ?? ListTodo
// Next steps the AI offers end its answer, one per line starting with ">> ".
const nextSteps = (text: string) => { const next: string[] = []; const body = text.replace(/^>>\s*(.+)$/gm, (_, s: string) => { next.push(s.trim()); return "" }).trim(); return { body, next } }
// Before setup makes one there's no companion: Still itself talks, with the default look.
export const companionOf = (ai: AiState | undefined, id?: string) => ai?.companions?.find(c => c.id === id) ?? ai?.companions?.[0] ?? (ai ? FALLBACK : undefined)

// A tooltip that flips and slides to stay inside the window and the chat panel, where a native title can't.
function Tip({ label, children }: { label: ReactNode; children: ReactElement }) {
 return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
 return <Tip label={label}><Button variant="ghost" size="icon-sm" aria-label={label} disabled={disabled} onClick={onClick}>{children}</Button></Tip>
}

const MONOGRAM: Record<string, string> = { chatgpt: "Gp", grok: "Gk", claude: "Cl" }
// "Bring your own AI": each agent app on this PC, signed in with the user's own plan. Picking one makes it the AI for
// new chats; a row that isn't ready offers the next step. Nothing is installed unless the user asks.
export function AiPicker({ ai, onPick, send }: { ai: AiState; onPick: (id: string) => void; send?: Send }) {
 const [howTo, setHowTo] = useState("")
 const [more, setMore] = useState(false)
 const row = (h: Harness) => {
  const s = statusOf(h), chosen = ai.harness === h.id
  const state = settingUp(s) ? <><Spinner />{s === "installing" ? "Installing…" : "Signing in…"}</>
   : s === "ready" ? <><span className="byo-ok">Signed in with your plan</span><Check aria-hidden /></>
   : s === "missing" ? "Not installed"
   : s === "signedOut" ? (send ? "Installed" : "Installed · Sign in with your plan")
   : h.installed ? "Installed" : "Checking…"
  return <div key={h.id} className="byo-row" data-chosen={chosen || undefined} data-status={s || undefined}>
   <button className="byo-main" onClick={() => onPick(h.id)} aria-pressed={chosen}>
    <span className="byo-tile" aria-hidden>{MONOGRAM[h.id] ?? h.name.slice(0, 2)}</span>
    <span className="byo-name"><strong>{h.name}</strong><small>{state}</small></span>
    {chosen && <Check className="ai-pick-check" aria-label="Chosen" />}
   </button>
   {s === "signedOut" && send && <Button size="sm" variant="outline" className="byo-act" onClick={() => { onPick(h.id); send("aiLogin") }}>Sign in with your plan</Button>}
   {s === "missing" && <Button size="sm" variant="ghost" className="byo-act" aria-expanded={howTo === h.id} onClick={() => setHowTo(howTo === h.id ? "" : h.id)}>How to install<ChevronDown /></Button>}
   {howTo === h.id && s === "missing" && <div className="byo-how">
    <p>Run this in PowerShell, then come back:</p>
    <code className="byo-cmd">{h.installCommand}</code>
    <div className="ai-row">
     <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(h.installCommand)}><Copy />Copy</Button>
     {h.installer && send && <Button size="sm" variant="ghost" onClick={() => { onPick(h.id); send("aiInstall") }}>Install it for me</Button>}
     {send && <Button size="sm" variant="ghost" onClick={() => send("aiCheck")}>I installed it</Button>}
    </div>
   </div>}
  </div>
 }
 const main = ai.harnesses.filter(h => !h.secondary), others = ai.harnesses.filter(h => h.secondary)
 return <div className="ai-picker byo">
  {main.map(row)}
  {others.length > 0 && <>
   <button className="byo-more" aria-expanded={more} onClick={() => setMore(!more)}>More agents ({others.length})<ChevronDown /></button>
   {more && others.map(row)}
  </>}
 </div>
}

// Every AI in one list: its models when it's ready, or a way to set it up. Picking another AI's model moves the chat to it.
function ModelPicker({ ai, send, disabled }: { ai: AiState; send: Send; disabled?: boolean }) {
 const current = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const modelsOf = (h: Harness) => { const ms = ai.models?.filter(m => m.harness === h.id); return ms?.length ? ms : [{ harness: h.id, id: "", name: "Default", efforts: [] }] }
 const model = ai.models?.find(m => m.harness === current?.id && m.id === ai.model)
 const picked = current ? `${current.id}|${modelsOf(current).some(m => m.id === ai.model) ? ai.model : ""}` : ""
 return <>
  <Select value={picked} disabled={disabled} onValueChange={v => { const [harness, id] = v.split("|"); if (id === "setup" || !current) send("aiHarness", { harness }); else send("aiModel", { harness, model: id, effort: harness === current.id ? ai.effort : "" }) }}>
   <SelectTrigger size="sm" className="ai-pick ai-model" aria-label="Model"><SelectValue placeholder="Pick your AI" /></SelectTrigger>
   <SelectContent position="popper" side="top" align="start">{ai.harnesses.map((h, i) => <SelectGroup key={h.id}>
    {i > 0 && <SelectSeparator />}
    {ready(h) ? modelsOf(h).map(m => <SelectItem key={m.id} value={`${h.id}|${m.id}`}><AiLogo id={h.id} size={16} />{m.id ? m.name : h.name}</SelectItem>)
     : <SelectItem value={`${h.id}|setup`}><AiLogo id={h.id} size={16} />{h.name}<span className="ai-pick-setup">Set up</span></SelectItem>}
   </SelectGroup>)}</SelectContent></Select>
  {!!model?.efforts.length && <Select value={ai.effort || "default"} disabled={disabled} onValueChange={v => send("aiModel", { model: ai.model, effort: v === "default" ? "" : v })}>
   <SelectTrigger size="sm" className="ai-pick" aria-label="Effort"><SelectValue /></SelectTrigger>
   <SelectContent position="popper" side="top" align="start"><SelectItem value="default">Default effort</SelectItem>{model.efforts.map(e => <SelectItem key={e} value={e}>{e === "xhigh" ? "Extra high" : e[0].toUpperCase() + e.slice(1)} effort</SelectItem>)}</SelectContent></Select>}
 </>
}

// Who you work with and how hard they think: Quick (the quickest model, thinking little), Everyday (the AI app's own
// defaults) or Thorough (the strongest model, thinking hard). Advanced swaps the modes for the model and effort pickers.
const MODES: [Mode, string, LucideIcon, string][] = [
 ["efficient", "Quick", Rabbit, "Fast answers that go easy on your plan"],
 ["default", "Everyday", Coffee, "Your AI app's usual setup, right for most things"],
 ["expert", "Thorough", Brain, "Its strongest model, taking its time on hard jobs"],
]
// The message box's menus open above the whole box, lined up with its edge, not over what you're typing. In the chat
// panel they span the box, so nothing behind them peeks out at the sides.
function useOverBox<T extends HTMLElement>(align: "start" | "end") {
 const ref = useRef<T>(null)
 const [at, setAt] = useState({ offset: 0, lift: 0, width: 0 })
 const measure = (open: boolean) => {
  const button = ref.current?.getBoundingClientRect(), box = ref.current?.closest(".composer")?.getBoundingClientRect()
  if (open && button && box) setAt({ offset: align === "end" ? button.right - box.right : box.left - button.left, lift: button.top - box.top, width: ref.current!.closest(".ai-sidebar") ? box.width : 0 })
 }
 return { ref, measure, props: { side: "top" as const, align, alignOffset: at.offset, sideOffset: 8 + at.lift, style: at.width ? { width: at.width } : undefined } }
}
function ModeMenu({ ai, send, companion, onCompanion, disabled }: { ai: AiState; send: Send; companion?: Companion; onCompanion?: (id: string) => void; disabled?: boolean }) {
 const [find, setFind] = useState("")
 const over = useOverBox<HTMLButtonElement>("end")
 const mode = companion?.mode ?? "default"
 const mates = (ai.companions ?? []).filter(c => c.name.toLowerCase().includes(find.trim().toLowerCase()))
 return <DropdownMenu onOpenChange={o => { over.measure(o); if (!o) setFind("") }}>
  <DropdownMenuTrigger asChild disabled={disabled}><button type="button" ref={over.ref} className="mode-chip" aria-label="Companion and mode"><Face companion={companion} size={20} /><span>{ai.advanced ? "Advanced" : MODES.find(m => m[0] === mode)?.[1]}</span><ChevronDown /></button></DropdownMenuTrigger>
  <DropdownMenuContent {...over.props} className="mode-menu">
   {onCompanion && <>
    <input className="mode-find" aria-label="Find a companion" placeholder="Find a companion…" value={find} onChange={e => setFind(e.target.value)} onKeyDown={e => e.stopPropagation()} />
    <div className="mode-mates">{mates.map(c => <DropdownMenuItem key={c.id} onSelect={() => onCompanion(c.id)}><Face companion={c} size={22} />{c.name}{c.id === companion?.id && <CircleCheck className="mode-check" />}</DropdownMenuItem>)}</div>
    {!mates.length && <p className="mode-none">No one by that name.</p>}
    <DropdownMenuSeparator />
   </>}
   {MODES.map(([id, label, Icon, about]) => <DropdownMenuItem key={id} className="mode-item" disabled={!companion} onSelect={() => { if (companion) send("companionMode", { id: companion.id, mode: id }); if (ai.advanced) send("aiAdvanced", { on: false }) }}>
    <Icon className="mode-icon" /><span className="mode-text">{label}<small>{about}</small></span>{!ai.advanced && mode === id && <CircleCheck className="mode-check" />}</DropdownMenuItem>)}
   <DropdownMenuLabel className="mode-advanced"><span>Advanced</span><Switch checked={!!ai.advanced} aria-label="Pick the model and effort yourself" onCheckedChange={on => send("aiAdvanced", { on })} /></DropdownMenuLabel>
  </DropdownMenuContent>
 </DropdownMenu>
}

// "/" in the message box picks a skill. A skill named in the text (/id) shows as a chip above it.
const skillToken = (id: string) => new RegExp(`(^|\\s)/${id}(?=\\s|$)`)
export function SkillText({ text, skills }: { text: string; skills?: Skill[] }) {
 const ids = new Set(skills?.map(k => k.id))
 return <>{text.split(/(?<=^|\s)(\/[a-z0-9-]+)(?=\s|$)/).map((part, i) => part.startsWith("/") && ids.has(part.slice(1)) ? <span key={i} className="skill-chip"><BookOpen />{skills?.find(k => k.id === part.slice(1))?.name}</span> : part)}</>
}

// The message box: the model on the right, then send, or a red stop while the AI works (Enter then queues a follow-up).
// How the companion looks through a run: thinking until its first step, working through steps, waiting on the user's
// answer, a small celebration when it finishes, a droop on an error. Listening while the user types to it.
export function useRunMood(ai: AiState | undefined, typing = false): Mood {
 const busy = !!ai?.busy
 const [done, setDone] = useState(false)
 const was = useRef(busy)
 useEffect(() => {
  const finished = was.current && !busy
  was.current = busy
  if (!finished) return
  setDone(true) // eslint-disable-line react-hooks/set-state-in-effect
  const t = setTimeout(() => setDone(false), 2600)
  return () => clearTimeout(t)
 }, [busy])
 if (ai?.question || ai?.approvals?.some(a => !a.until)) return "needs"
 if (busy) return ai?.messages.at(-1)?.role === "tool" ? "working" : "thinking"
 if (ai?.error) return "error"
 if (done) return "done"
 return typing ? "listening" : "idle"
}

export function Composer({ ai, send, placeholder, onSubmit, onStop, disabled, autoFocus, onTyping, companion, onCompanion, tabs }: { ai: AiState; send: Send; placeholder: string; onSubmit: (text: string) => void; onStop?: () => void; disabled?: boolean; autoFocus?: boolean; onTyping?: (typing: boolean) => void; companion?: Companion; onCompanion?: (id: string) => void; tabs?: TabRef[] }) {
 const [text, setTextState] = useState("")
 const [pick, setPick] = useState(0)
 const box = useRef<HTMLTextAreaElement>(null)
 const add = useOverBox<HTMLButtonElement>("start")
 const setText = (v: string) => { setTextState(v); setPick(0); onTyping?.(!!v.trim()) }
 const submit = () => { if (!text.trim() || disabled) return; onSubmit(text.trim()); setText("") }
 const skills = ai.skills ?? []
 const typed = /(^|\s)\/([\w-]*)$/.exec(text)?.[2].toLowerCase()
 const matches = typed === undefined ? [] : skills.filter(k => k.id.startsWith(typed) || k.name.toLowerCase().includes(typed)).slice(0, 6)
 const used = skills.filter(k => skillToken(k.id).test(text))
 const pickSkill = (k: Skill) => { setText(typed === undefined ? `/${k.id} ${text}` : text.replace(/(^|\s)\/[\w-]*$/, `$1/${k.id} `)); box.current?.focus() }
 const pages = (tabs ?? []).filter(t => t.url && !t.isPrivate && !t.chatId && !t.inChat).slice(0, 6)
 return <InputGroup className="composer" style={{ "--hue": hueOf(companion) } as CSSProperties}>
  {matches.length > 0 && <div className="skill-menu" role="listbox" aria-label="Skills">{matches.map((k, i) => <button type="button" key={k.id} role="option" aria-selected={i === pick % matches.length} onMouseDown={e => { e.preventDefault(); pickSkill(k) }}><BookOpen /><b>/{k.id}</b><span>{k.description || k.name}</span></button>)}</div>}
  {used.length > 0 && <InputGroupAddon align="block-start" className="skill-chips">{used.map(k => <span key={k.id} className="skill-chip"><BookOpen />{k.name}<button type="button" aria-label={"Don't use " + k.name} onClick={() => setText(text.replace(skillToken(k.id), "$1").trim())}><X /></button></span>)}</InputGroupAddon>}
  <InputGroupTextarea ref={box} aria-label="Message" placeholder={placeholder} rows={2} autoFocus={autoFocus} disabled={disabled} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => {
   if (matches.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); setPick(pick + (e.key === "ArrowDown" ? 1 : matches.length - 1)); return }
   if (matches.length && (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey))) { e.preventDefault(); pickSkill(matches[pick % matches.length]); return }
   if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }} />
  <InputGroupAddon align="block-end">
   <DropdownMenu onOpenChange={add.measure}><DropdownMenuTrigger asChild disabled={disabled}><InputGroupButton ref={add.ref} className="composer-add" size="icon-xs" variant="ghost" aria-label="Add a skill or a tab"><Plus /></InputGroupButton></DropdownMenuTrigger>
    <DropdownMenuContent {...add.props} className="w-72">
     <DropdownMenuLabel>Skills</DropdownMenuLabel>
     {skills.slice(0, 8).map(k => <DropdownMenuItem key={k.id} onSelect={() => pickSkill(k)}><BookOpen />{k.name}</DropdownMenuItem>)}
     {!skills.length && <p className="mode-none">No skills yet. Make one on the new tab page, under Skills.</p>}
     {pages.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>Add a tab</DropdownMenuLabel>
      {pages.map(t => <DropdownMenuItem key={t.id} onSelect={() => { setText(`${text}${text && !text.endsWith(" ") ? " " : ""}[${t.title || host(t.url)}](${t.url}) `); box.current?.focus() }}><Globe /><span className="truncate">{t.title || host(t.url)}</span></DropdownMenuItem>)}</>}
    </DropdownMenuContent></DropdownMenu>
   <span className="composer-gap" />
   <ModeMenu ai={ai} send={send} companion={companion} onCompanion={onCompanion} disabled={!!onStop || disabled} />
   {ai.advanced && <ModelPicker ai={ai} send={send} disabled={!!onStop || disabled} />}
   {onStop && !text.trim() ? <Tip label="Stop · Ctrl+."><InputGroupButton className="ai-send is-stop" size="icon-xs" variant="default" aria-label="Stop" onClick={onStop}><Square /></InputGroupButton></Tip>
    : <InputGroupButton className="ai-send" size="icon-xs" variant="default" aria-label="Send" disabled={!text.trim() || disabled} onClick={submit}><ArrowUp /></InputGroupButton>}
  </InputGroupAddon>
 </InputGroup>
}

// The AI asked something with ask_user: pick an option, write an answer, or skip.
function QuestionCard({ q, companion, send }: { q: { text: string; options: string[]; page?: string | null }; companion?: Companion; send: Send }) {
 const [own, setOwn] = useState("")
 useEffect(() => { // 1-9 picks an option, unless the user is typing
  const key = (e: KeyboardEvent) => { const n = Number(e.key); if (n >= 1 && n <= q.options.length && !(e.target as HTMLElement).closest("input,textarea,[contenteditable]")) send("aiAnswer", { text: q.options[n - 1] }) }
  addEventListener("keydown", key); return () => removeEventListener("keydown", key)
 }, [q, send])
 return <div className="ask-card" role="group" aria-label="Question from your AI">
  {q.page && <div className="ask-help"><strong>Help with this page</strong><Button size="sm" variant="outline" onClick={() => send("aiHelpPage", { id: q.page })}>Open the page</Button></div>}
  <div className="ask-q"><Face companion={companion} size={22} /><p>{q.text}</p></div>
  {q.options.length > 0 && <div className="ask-options">{q.options.map((o, i) => <button key={i} className="ask-option" onClick={() => send("aiAnswer", { text: o })}><kbd>{i + 1}</kbd><span>{o}</span></button>)}</div>}
  <form className="ask-own" onSubmit={e => { e.preventDefault(); if (own.trim()) send("aiAnswer", { text: own }) }}>
   <input aria-label="Your answer" placeholder="Or write your own answer…" value={own} onChange={e => setOwn(e.target.value)} />
   <Button type="button" variant="ghost" size="sm" onClick={() => send("aiAnswer", { text: "" })}>Skip</Button>
   <Button type="submit" size="sm" disabled={!own.trim()}>Send</Button>
  </form>
 </div>
}

// Install or sign in to the chat's AI. Null when it's ready to chat.
function Setup({ ai, send, onSettings }: { ai: AiState; send: Send; onSettings: () => void }) {
 const current = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const status = statusOf(current)
 const pending = ai.pending && <p className="ai-fine">Your message runs as soon as {current?.name ?? "your AI"} is ready.</p>
 if (!current) return <div className="ai-pane ai-center">
  <Face size={64} />
  <h3>Bring your own AI</h3>
  <p>Still runs on the AI you already pay for, through its own app on this computer. No API keys, no credits, no extra plan. Your chats go only to your AI provider.</p>
  <AiPicker ai={ai} send={send} onPick={id => send("aiHarness", { harness: id })} />
  {pending}
 </div>
 if (status === "missing" || status === "installing") return <div className="ai-pane ai-center">
  <Face size={64} mood={status === "installing" ? "working" : "idle"} />
  {status === "installing" ? <>
   <h3>Installing {current.app}…</h3>
   <p>This usually takes about a minute.</p>
   {ai.setup.line && <Tip label={ai.setup.line}><code className="ai-setup-line">{ai.setup.line}</code></Tip>}
   <Button variant="ghost" size="sm" onClick={() => send("aiSetupCancel")}>Cancel</Button>
  </> : <>
   <h3>Let's get {current.name}</h3>
   <p>{current.name} needs {current.maker}'s app on this PC. Run this in PowerShell, then sign in with your plan.</p>
   <code className="byo-cmd">{current.installCommand}</code>
   {current.installer && <>
    <Button className="ai-go" onClick={() => send("aiInstall")}>Install it for me</Button>
    <div className="ai-trust"><ShieldCheck /><span>Uses {current.maker}'s official installer from <Tip label={current.installer}><b>{host(current.installer)}</b></Tip>. It installs just for you and needs no admin rights.</span></div>
   </>}
   <div className="ai-row"><Button variant="link" size="sm" onClick={() => send("aiCheck")}>I already installed it</Button><Button variant="link" size="sm" onClick={onSettings}>Pick another AI</Button></div>
  </>}
  {pending}
 </div>
 if (status === "signedOut" || status === "signingIn") return <div className="ai-pane ai-center">
  <Face size={64} mood={status === "signingIn" ? "thinking" : "idle"} />
  {status === "signingIn" ? <>
   <h3>{ai.setup.url ? "Approve it in the new tab" : `Opening ${current.maker}'s sign-in…`}</h3>
   {ai.setup.url && <p>Sign in on {current.maker}'s page and approve. This moves on by itself.</p>}
   {ai.setup.code && <div className="ai-code"><small>The page should show this code</small><strong>{ai.setup.code}</strong></div>}
   {ai.setup.url && <div className="ai-trust"><LockKeyhole /><span>You're signing in on <b>{host(ai.setup.url)}</b>, {current.maker}'s own site. Still never sees your password.</span></div>}
   <div className="ai-row">
    {ai.setup.url && <Button variant="link" size="sm" onClick={() => send("new", { url: ai.setup.url })}><ExternalLink />Open the page again</Button>}
    <Button variant="link" size="sm" onClick={() => send("aiSetupCancel")}>Cancel</Button>
   </div>
  </> : <>
   <h3>Sign in to {current.name}</h3>
   <p>{current.name} uses your own {current.maker} account. Sign in once and you're set.</p>
   <Button className="ai-go" onClick={() => send("aiLogin")}>Sign in with {current.maker}</Button>
   <div className="ai-trust"><LockKeyhole /><span>You sign in on {current.maker}'s own website, in a tab here. Still never sees your password.</span></div>
   <Button variant="link" size="sm" onClick={onSettings}>Pick another AI</Button>
  </>}
  {pending}
 </div>
 return null
}

// A conversation: in its own tab (centered, or beside the AI's page) or in the panel next to a page.
export function ChatView({ ai, send, mode, tabs = [], activeTab, onSettings, onFile, interests }: { ai: AiState; send: Send; mode: "tab" | "panel"; tabs?: TabRef[]; activeTab?: TabRef; onSettings: () => void; onFile: (path: string) => void; interests?: string[] }) {
 const [tick, setTick] = useState(0)
 const provider = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const queued = ai.queued ?? []
 const log = useRef<HTMLDivElement>(null)
 const [picked, setPicked] = useState<string>() // who a new chat in the sidebar is with
 const fresh = !ai.messages.length
 const companion = companionOf(ai, fresh && picked ? picked : ai.chatCompanion)
 const name = companion?.name ?? "your AI"
 const busy = ai.busy
 const started = ai.runs?.find(r => r.id === ai.chatId)?.started
 const [typing, setTyping] = useState(false)
 const mood = useRunMood(ai, typing)
 useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }) }, [ai.messages.length, busy, !!ai.question])
 // Timed from when the run started, so it reads right after switching chats.
 useEffect(() => { if (!busy) return; const count = () => setTick(since(started)); count(); const t = setInterval(count, 1000); return () => clearInterval(t) }, [busy, started])
 // While it works, a message waits as a follow-up (Still queues it) until the run ends or the user sends it now.
 // "Don't remember this chat": a chat that exists flips its own flag, a new one starts off the record.
 const chat = ai.chats.find(c => c.id === ai.chatId)
 const [offRecord, setOffRecord] = useState(false)
 const forget = chat ? !!chat.noMemory : offRecord
 const submit = (value: string) => send("aiSend", { text: value, companion: companion?.id, ...(!chat && offRecord && { noMemory: true }) })
 const you = calledBy(companion)

 // Consecutive steps collapse into one row. A question waiting in its card isn't repeated in the log.
 const messages = ai.question && ai.messages.at(-1)?.text === ai.question.text ? ai.messages.slice(0, -1) : ai.messages
 const items: ({ role: string; text: string } | { role: "steps"; steps: string[] })[] = []
 for (const m of messages) {
  const prev = items[items.length - 1]
  if (m.role === "tool") { if (prev && "steps" in prev) prev.steps.push(m.text); else items.push({ role: "steps", steps: [m.text] }) }
  else items.push(m)
 }
 const fromAi = (i: number) => ["assistant", "steps", "file", "search", "read"].includes(items[i]?.role)
 // The companion's face starts each of its turns.
 const face = (i: number) => fromAi(i - 1) ? null : <Face className="ai-turn-face" companion={companion} size={24} mood={i >= items.length - 1 ? mood : "idle"} />
 const setup = Setup({ ai, send, onSettings })
 const pages = tabs.filter(t => t.inChat && t.inChat === ai.chatId)
 const openLink = (url: string) => send("new", { url })

 return <section className="chat-view" data-mode={mode} aria-label={"Chat with " + name}>
  {setup ?? <div className="ai-log" ref={log} onScroll={fadeTop}><div className="chat-column">
   {!items.length && (mode === "tab" ? <div className="chat-hello">
    <Face companion={companion} size={168} follow gesture="wave" gestureAt={1} className="chat-hello-face" />
    <h3>{you ? `Hi ${you}! What are we working on?` : `Hi, I'm ${name}. What are we working on?`}</h3>
    <p>{companion?.job || "Ask me anything, or hand me a task. I work in my own background tabs while you keep browsing."}</p>
    <div className="chat-starters">{starters(interests, companion, 4).map(([label, prompt]) => <button key={label} onClick={() => submit(prompt)}><Lightbulb aria-hidden />{label}</button>)}</div>
   </div> : <div className="ai-hello">
    <Face companion={companion} size={64} />
    <h3>What should we do?</h3>
    <p>I can read this page, search the web, compare and click around in my own background tabs. Switch AI any time, even mid-task.</p>
    <div className="ai-ideas">{IDEAS.map(([Icon, label, prompt]) => <button key={label} className="ai-idea" onClick={() => submit(prompt)}><span><Icon aria-hidden /></span>{label}</button>)}</div>
    <p className="ai-fine"><LockKeyhole />Never sees private tabs, passwords or cookies.</p>
   </div>)}
   {items.map((m, i) => {
    if ("steps" in m) {
     const live = busy && i === items.length - 1, kinds = [...new Set(m.steps.map(stepIcon))].slice(-3)
     return <div key={i} className="ai-turn">{face(i)}<details className="ai-steps-group"><summary>
      <span className="ai-steps-icons">{kinds.map((Icon, j) => <span key={j} className="ai-steps-icon"><Icon /></span>)}</span>
      <span className="ai-steps-text"><b>{m.steps[m.steps.length - 1]}</b>{m.steps.length > 1 && <small> (and {m.steps.length - 1} more action{m.steps.length === 2 ? "" : "s"})</small>}</span>
      {live ? <Spinner className="ai-steps-state" aria-label="Working" /> : <Check className="ai-steps-state is-done" aria-label="Done" />}
      <ChevronDown className="ai-steps-chevron" /></summary><ol>{m.steps.map((s, j) => { const Icon = stepIcon(s); return <li key={j}><Icon />{s}</li> })}</ol></details></div>
    }
    if (m.role === "file") return <div key={i} className="ai-turn">{face(i)}<FileCard path={m.text} send={send} onOpen={onFile} /></div>
    if (m.role === "search" || m.role === "read") return <div key={i} className="ai-turn">{face(i)}<LookedUp m={m} onLink={openLink} /></div>
    if (m.role === "user") return <div key={i} className="ai-msg is-user"><SkillText text={m.text} skills={ai.skills} /></div>
    if (m.role !== "assistant") return <div key={i} className="ai-msg is-note">{m.text}</div>
    const { body, next } = nextSteps(m.text)
    const last = i === items.length - 1 && !busy
    return <div key={i} className="ai-turn">{face(i)}
     <div className="ai-msg is-assistant"><Markdown text={body} onLink={openLink} onCopy={text => { send("copyText", { text }); toast("Copied") }} /></div>
     {next.length > 0 && <div className="ai-next">{next.map(s => <button key={s} className="ai-next-step" disabled={!last} onClick={() => submit(s)}><Lightbulb /><span>{s}</span></button>)}</div>}
     {last && <>{!!ai.worked && <p className="ai-timer">Took {clock(ai.worked)}</p>}
      <div className="ai-actions"><IconButton label="Copy" onClick={() => send("copyText", { text: body })}><Copy /></IconButton></div></>}
    </div>
   })}
   {busy && !ai.question && <div className="ai-turn">{face(items.length)}<p className="ai-timer">Working · {clock(tick)}</p></div>}
  </div></div>}
  {ai.error && <Alert variant="destructive" className="ai-error"><AlertDescription>{ai.error}</AlertDescription><Button size="sm" variant="outline" className="ai-error-copy" onClick={() => { send("copyText", { text: ai.error }); toast("Details copied") }}><Copy />Copy details</Button></Alert>}
  {!setup && <div className="ai-compose"><div className="chat-column">
   {mode === "panel" && pages.length > 0 && <button className="chat-chip is-pages" onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 />{name} has {pages.length === 1 ? "a page" : pages.length + " pages"} open<b>Show</b></button>}
   {mode === "panel" && activeTab?.url && !activeTab.inChat && <Tip label={activeTab.url}><span className="chat-chip"><Globe />{activeTab.title || host(activeTab.url)}</span></Tip>}
   {ai.question && <QuestionCard q={ai.question} companion={companion} send={send} />}
   {!!ai.approvals?.length && <Approvals list={ai.approvals} companion={companion} send={send} />}
   {queued.length > 0 && <div className="ai-queued"><span>Up next</span><p>{queued.join("\n\n")}</p><Button variant="outline" size="sm" onClick={() => send("aiNow")}>Send now</Button><Tip label="Don't send"><button aria-label="Don't send" onClick={() => send("aiUnqueue")}><X /></button></Tip></div>}
   <Composer ai={ai} send={send} onSubmit={submit} onTyping={setTyping} onStop={busy ? () => send("aiStop") : undefined} companion={companion} onCompanion={fresh && mode === "panel" ? setPicked : undefined} tabs={tabs}
    placeholder={busy ? (queued.length ? "Add to what's up next…" : "Add a next step…") : items.length ? `Reply to ${name}…` : mode === "tab" ? `Work with ${name}…` : "Ask anything, or tell me what to do…"} />
   <div className="chat-under">
    {companion && <Tip label={forget ? `${name} won't remember anything from this chat` : `${name} remembers useful things from this chat`}><label className="chat-memory"><Switch size="sm" aria-label="Don't remember this chat" checked={forget} onCheckedChange={on => chat ? send("chatNoMemory", { id: chat.id, on }) : setOffRecord(on)} />Don't remember this chat</label></Tip>}
    {mode === "panel" && provider && <p className="ai-usage"><Gauge />{["Your " + provider.name + " plan", ai.usage].filter(Boolean).join(" · ")}</p>}
   </div>
  </div></div>}
 </section>
}

// AI apps, what the AI can see, and the saved chats.
function AiSettings({ ai, send, done }: { ai: AiState; send: Send; done: () => void }) {
 return <div className="ai-pane">
  <section><h4>Your AI</h4><p>Each runs on this PC with the plan you already pay for. Switch between them in the model list under the message box.</p>
   <AiPicker ai={ai} send={send} onPick={id => { send("aiHarness", { harness: id }); done() }} /></section>
  <Separator />
  <section><h4>What it can see</h4><p>Only your <strong>{ai.profile}</strong> profile and its tabs. Never private tabs, saved passwords or cookies.</p></section>
  <Separator />
  <section><h4>Chats</h4><p>{ai.chats.length ? `${ai.chats.length} saved on this PC.` : "None saved yet."}</p>
   <Button variant="outline" size="sm" disabled={!ai.chats.length || !!ai.runs?.length} onClick={() => send("aiDeleteAll")}><Trash2 />Delete all chats</Button></section>
 </div>
}

// The chat panel beside an ordinary page (the Chat button), or the AI settings.
export function AiPanel({ ai, send, view, setView, tabs, activeTab, onFile }: { ai: AiState; send: Send; view: "chat" | "settings"; setView: (v: "chat" | "settings") => void; tabs: TabRef[]; activeTab?: TabRef; onFile: (path: string) => void }) {
 const companion = companionOf(ai, ai.chatCompanion)
 const mood = useRunMood(ai)
 const [panel, setPanel] = useState<HTMLElement | null>(null)
 return <aside className="ai-sidebar" aria-label="Chat" ref={setPanel}><CollisionBoundary.Provider value={panel}>
  <div className="ai-head">
   {view !== "chat" ? <IconButton label="Back" onClick={() => setView("chat")}><ArrowLeft /></IconButton> : <Face companion={companion} size={22} mood={mood} className="ai-head-buddy" />}
   <div className="ai-title"><strong>{view === "settings" ? "AI settings" : ai.chats.find(c => c.id === ai.chatId)?.title || companion?.name || "Chat"}</strong></div>
   {view === "chat" && <>
    <IconButton label="Open as a tab" disabled={!ai.chatId} onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 /></IconButton>
    <IconButton label="New chat" disabled={!ai.chatId} onClick={() => send("aiNew")}><MessageSquarePlus /></IconButton>
    <IconButton label="AI settings" onClick={() => setView("settings")}><Settings2 /></IconButton>
   </>}
   <IconButton label="Close chat" onClick={() => { setView("chat"); send("aiToggle") }}><X /></IconButton>
  </div>
  {view === "settings" ? <AiSettings ai={ai} send={send} done={() => setView("chat")} /> : <ChatView ai={ai} send={send} mode="panel" tabs={tabs} activeTab={activeTab} onSettings={() => setView("settings")} onFile={onFile} />}
 </CollisionBoundary.Provider></aside>
}


// Top right: the chats at work (green spinner), the ones waiting on you (amber) and new replies (blue).
// A question can be answered right here.
// Screen readers hear when a chat starts, needs you, or finishes.
export function RunAnnouncer({ ai }: { ai: AiState }) {
 const [say, setSay] = useState("")
 const last = useRef<Record<string, boolean>>({})
 useEffect(() => {
  const runs = ai.runs ?? [], title = (id: string) => ai.chats.find(c => c.id === id)?.title || "Your chat", lines: string[] = []
  const now: Record<string, boolean> = Object.fromEntries(runs.map(r => [r.id, waits(r)]))
  for (const r of runs) if (!(r.id in last.current)) lines.push(title(r.id) + ": working"); else if (now[r.id] && !last.current[r.id]) lines.push(title(r.id) + " needs you")
  for (const id in last.current) if (!(id in now)) lines.push(title(id) + ": done")
  last.current = now
  if (lines.length) setSay(lines.join(". "))
 }, [ai.runs, ai.chats])
 return <div className="sr-only run-announcer" role="status" aria-live="polite">{say}</div>
}

// web_search and read_url: one compact row each ("Searched 'x' · 8 results", "Read example.com") that opens to the results.
function LookedUp({ m, onLink }: { m: { role: string; text: string }; onLink: (url: string) => void }) {
 let data: { q?: string; url?: string; title?: string; results?: { title: string; url: string; snippet: string }[] } = {}
 try { data = JSON.parse(m.text) } catch { return null }
 const link = (url: string, label: ReactNode) => <Tip label={url}><a href={url} onClick={e => { e.preventDefault(); onLink(url) }}>{label}</a></Tip>
 if (m.role === "read") return <div className="ai-look"><div className="ai-look-row"><Globe />{link(data.url ?? "", <b>Read {host(data.url ?? "")}</b>)}{data.title && <small>· {data.title}</small>}</div></div>
 const results = data.results ?? []
 return <details className="ai-look"><summary><Search /><b>Searched “{data.q}”</b><small>· {results.length} result{results.length === 1 ? "" : "s"}</small><ChevronDown className="ai-steps-chevron" /></summary>
  <ol>{results.map(r => <li key={r.url}>{link(r.url, r.title || host(r.url))}<small>{host(r.url)}</small>{r.snippet && <p>{r.snippet}</p>}</li>)}</ol></details>
}

export function RunningTasks({ ai, send, onOpen, tabs }: { ai: AiState; send: Send; onOpen: (open: boolean) => void; tabs: (TabRef & { favicon?: string; agent?: string })[] }) {
 const [open, setOpenState] = useState(false)
 const setOpen = (o: boolean) => { setOpenState(o); onOpen(o) }
 useEffect(() => () => onOpen(false), []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { const flip = () => setOpen(!open); window.addEventListener("still-tasks", flip); return () => window.removeEventListener("still-tasks", flip) }) // Ctrl+Shift+K
 const [, setNow] = useState(0)
 useEffect(() => { if (!open) return; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [open])
 const runs = ai.runs ?? [], unread = ai.chats.filter(c => c.unread && !c.archived && !isRunning(ai, c.id)).slice(0, 6), apps = tabs.filter(t => t.inChat?.startsWith("app:")), empty = !runs.length && !unread.length && !apps.length
 useEffect(() => { if (empty) setOpen(false) }, [empty]) // eslint-disable-line react-hooks/exhaustive-deps
 if (empty) return null
 const waiting = runs.filter(waits).length
 const chat = (id: string) => ai.chats.find(c => c.id === id)
 return <DropdownMenu open={open} onOpenChange={setOpen}>
  <DropdownMenuTrigger asChild><Button variant="ghost" size="sm" className="tasks-button" aria-label={`Running tasks: ${runs.length} running${waiting ? `, ${waiting} need you` : ""}${unread.length ? `, ${unread.length} new` : ""}`} title="Running tasks · Ctrl+Shift+K">
   {runs.length > waiting ? <Spinner className="tasks-spin" /> : <ListTodo />}{runs.length > 0 && <b>{runs.length}</b>}
   {waiting > 0 && <i className="is-needs" />}{unread.length > 0 && <i className="is-unread" />}
  </Button></DropdownMenuTrigger>
  <DropdownMenuContent align="end" sideOffset={6} className="tasks-menu">
   <DropdownMenuLabel>Running tasks</DropdownMenuLabel>
   {runs.map(r => { const c = chat(r.id); return <div key={r.id} className="tasks-item">
    <DropdownMenuItem onSelect={() => send("chatOpen", { id: r.id })}><Face companion={companionOf(ai, c?.companion)} size={22} mood={waits(r) ? "needs" : "working"} />
     <span className="tasks-title">{c?.title ?? "Chat"}<small>{waits(r) ? "Needs you" : "Working · " + clock(since(r.started))}</small></span>
     {waits(r) ? <i className="is-needs" aria-hidden /> : <Spinner className="tasks-spin" aria-hidden />}</DropdownMenuItem>
    {tabs.filter(t => t.inChat === r.id).map(t => <div key={t.id} className="tasks-page">{t.favicon ? <img src={t.favicon} alt="" /> : <Globe />}<span title={t.url}>{t.title || host(t.url)}</span><button onClick={() => send("aiHelpPage", { id: t.id })}>Watch</button><button onClick={() => send("tabMine", { id: t.id })}>Move to my tabs</button></div>)}
    {r.question && <div className="tasks-ask"><p>{r.question}</p>{(r.options ?? []).slice(0, 4).map(o => <button key={o} onClick={() => send("aiAnswer", { id: r.id, text: o })}>{o}</button>)}</div>}
    {r.asks?.map(a => <div key={a.id} className="tasks-ask"><p>{a.what} <small>on {a.site}</small></p>
     <button onClick={() => send("permAnswer", { run: r.id, id: a.id, answer: "once" })}>Allow once</button><button onClick={() => send("permAnswer", { run: r.id, id: a.id, answer: "deny" })}>Deny</button></div>)}
   </div> })}
   {apps.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>Other AI apps' tabs</DropdownMenuLabel>
    {apps.map(t => <div key={t.id} className="tasks-page is-app">{t.favicon ? <img src={t.favicon} alt="" /> : <Globe />}<span title={t.url}>{t.agent ? t.agent + ": " : ""}{t.title || host(t.url)}</span><button onClick={() => send("tabMine", { id: t.id })}>Move to my tabs</button></div>)}</>}
   {unread.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>New replies</DropdownMenuLabel>
    {unread.map(c => <DropdownMenuItem key={c.id} onSelect={() => send("chatOpen", { id: c.id })}><Face companion={companionOf(ai, c.companion)} size={22} /><span className="tasks-title">{c.title}</span><i className="is-unread" aria-hidden /></DropdownMenuItem>)}</>}
  </DropdownMenuContent>
 </DropdownMenu>
}
