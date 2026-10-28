import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { ArrowLeft, ArrowUp, BookOpen, Check, ChevronDown, CircleCheck, Copy, Diamond, ExternalLink, FileText, Gauge, Globe, Lightbulb, LockKeyhole, Luggage, Plus, Star, Tag, Zap, Maximize2, MessageSquarePlus, Settings2, ShieldCheck, Square, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group"
import { Select, SelectContent, SelectGroup, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { AiLogo } from "./AiLogo"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Switch } from "@/components/ui/switch"
import { Face, hueOf, type Companion, type Mode, type Mood } from "./Buddy"
import { Markdown } from "./Markdown"

type Harness = { id: string; name: string; app: string; maker: string; installed: boolean; status: string; installer: string; installCommand: string; site: string; secondary?: boolean }
export type AiState = {
 open: boolean; harness: string; busy: boolean; running?: string; error: string; profile: string; harnesses: Harness[]
 setup: { line: string; url: string; code: string }; pending: boolean
 models?: { harness: string; id: string; name: string; efforts: string[] }[]; model: string; effort: string; usage: string
 chatId?: string; chatHarness?: string; chatCompanion?: string; messages: { role: string; text: string }[]
 question?: { text: string; options: string[] } | null; companions?: Companion[]
 chats: { id: string; title: string; harness: string; updated: string; companion?: string; unread?: boolean; archived?: boolean }[]
 advanced?: boolean; memory?: string; skills?: Skill[]
}
export type Skill = { id: string; name: string; description: string; when: string; body: string }
type Send = (op: string, payload?: Record<string, unknown>) => void
type TabRef = { id: string; title: string; url: string; inChat?: string; chatId?: string; isPrivate?: boolean }

const IDEAS = [
 [FileText, "Sum up this page", "Summarize this page in a few short bullet points."],
 [Tag, "Find it cheaper", "Find what's on this page cheaper somewhere else, and show me where."],
 [Luggage, "Plan a trip", "Help me plan a weekend trip. Ask me where I'm starting from and what I like first."],
 [Lightbulb, "Explain it simply", "Explain this page simply, like I'm new to the topic."],
] as const
const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url } }
const settingUp = (s?: string) => s === "installing" || s === "signingIn"
// "" = not checked yet, which never blocks a chat
const statusOf = (h?: Harness) => !h ? "" : h.status || (h.installed ? "" : "missing")
const ready = (h: Harness) => h.installed && !["missing", "signedOut"].includes(statusOf(h))
const clock = (s: number) => s < 60 ? s + "s" : Math.floor(s / 60) + "m " + String(s % 60).padStart(2, "0") + "s"
// Next steps the AI offers end its answer, one per line starting with ">> ".
const nextSteps = (text: string) => { const next: string[] = []; const body = text.replace(/^>>\s*(.+)$/gm, (_, s: string) => { next.push(s.trim()); return "" }).trim(); return { body, next } }
export const companionOf = (ai: AiState | undefined, id?: string) => ai?.companions?.find(c => c.id === id) ?? ai?.companions?.[0]

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
 return <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={label} disabled={disabled} onClick={onClick}>{children}</Button></TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>
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
   <SelectContent><SelectItem value="default">Default effort</SelectItem>{model.efforts.map(e => <SelectItem key={e} value={e}>{e === "xhigh" ? "Extra high" : e[0].toUpperCase() + e.slice(1)} effort</SelectItem>)}</SelectContent></Select>}
 </>
}

// Who you work with and how hard they think: Expert (the strongest model, thinking hard), Default (the AI app's own
// defaults) or Efficient (the quickest). Advanced swaps the modes for the model and effort pickers.
const MODES: [Mode, string, typeof Star, string, number, number][] = [
 ["expert", "Expert", Star, "The strongest model, thinking hard. For tricky research and long jobs.", 100, 38],
 ["default", "Default", Diamond, "Balanced thinking for everyday work.", 74, 62],
 ["efficient", "Efficient", Zap, "Quick and light on your plan. For small, simple jobs.", 46, 100],
]
function ModeMenu({ ai, send, companion, onCompanion, disabled }: { ai: AiState; send: Send; companion?: Companion; onCompanion?: (id: string) => void; disabled?: boolean }) {
 const [find, setFind] = useState("")
 const [hover, setHover] = useState<Mode>()
 const mode = companion?.mode ?? "default"
 const shown = MODES.find(m => m[0] === (hover ?? mode)) ?? MODES[1]
 const mates = (ai.companions ?? []).filter(c => c.name.toLowerCase().includes(find.trim().toLowerCase()))
 return <DropdownMenu onOpenChange={o => { if (!o) { setFind(""); setHover(undefined) } }}>
  <DropdownMenuTrigger asChild disabled={disabled}><button type="button" className="mode-chip" aria-label="Companion and mode"><Face companion={companion} size={20} /><span>{ai.advanced ? "Advanced" : MODES.find(m => m[0] === mode)?.[1]}</span><ChevronDown /></button></DropdownMenuTrigger>
  <DropdownMenuContent side="top" align="end" sideOffset={8} className="mode-menu">
   {onCompanion && <>
    <input className="mode-find" aria-label="Search companions" placeholder="Search companions..." value={find} onChange={e => setFind(e.target.value)} onKeyDown={e => e.stopPropagation()} />
    {mates.map(c => <DropdownMenuItem key={c.id} onSelect={() => onCompanion(c.id)}><Face companion={c} size={22} />{c.name}{c.id === companion?.id && <CircleCheck className="mode-check" />}</DropdownMenuItem>)}
    {!mates.length && <p className="mode-none">No one by that name.</p>}
    <DropdownMenuSeparator />
   </>}
   {MODES.map(([id, label, Icon]) => <DropdownMenuItem key={id} disabled={!companion} onMouseEnter={() => setHover(id)} onFocus={() => setHover(id)} onSelect={() => { if (companion) send("companionMode", { id: companion.id, mode: id }); if (ai.advanced) send("aiAdvanced", { on: false }) }}>
    <Icon className="mode-icon" />{label}{!ai.advanced && mode === id && <CircleCheck className="mode-check" />}</DropdownMenuItem>)}
   <DropdownMenuLabel className="mode-advanced"><span>Advanced</span><Switch checked={!!ai.advanced} aria-label="Pick the model and effort yourself" onCheckedChange={on => send("aiAdvanced", { on })} /></DropdownMenuLabel>
   <div className="mode-card" aria-hidden><b>{shown[1]} Mode</b><p>{shown[3]}</p><i style={{ "--w": shown[4] + "%" } as CSSProperties}><Star /></i><i style={{ "--w": shown[5] + "%" } as CSSProperties}><Zap /></i></div>
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
 const busy = !!ai?.busy && ai.running === ai.chatId
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
 if (ai?.question) return "needs"
 if (busy) return ai?.messages.at(-1)?.role === "tool" ? "working" : "thinking"
 if (ai?.error) return "error"
 if (done) return "done"
 return typing ? "listening" : "idle"
}

export function Composer({ ai, send, placeholder, onSubmit, onStop, disabled, autoFocus, onTyping, companion, onCompanion, tabs }: { ai: AiState; send: Send; placeholder: string; onSubmit: (text: string) => void; onStop?: () => void; disabled?: boolean; autoFocus?: boolean; onTyping?: (typing: boolean) => void; companion?: Companion; onCompanion?: (id: string) => void; tabs?: TabRef[] }) {
 const [text, setTextState] = useState("")
 const [pick, setPick] = useState(0)
 const box = useRef<HTMLTextAreaElement>(null)
 const setText = (v: string) => { setTextState(v); setPick(0); onTyping?.(!!v.trim()) }
 const submit = () => { if (!text.trim() || disabled) return; onSubmit(text.trim()); setText("") }
 const skills = ai.skills ?? []
 const typed = /(^|\s)\/([\w-]*)$/.exec(text)?.[2].toLowerCase()
 const matches = typed === undefined ? [] : skills.filter(k => k.id.startsWith(typed) || k.name.toLowerCase().includes(typed)).slice(0, 6)
 const used = skills.filter(k => skillToken(k.id).test(text))
 const useSkill = (k: Skill) => { setText(typed === undefined ? `/${k.id} ${text}` : text.replace(/(^|\s)\/[\w-]*$/, `$1/${k.id} `)); box.current?.focus() }
 const pages = (tabs ?? []).filter(t => t.url && !t.isPrivate && !t.chatId && !t.inChat).slice(0, 6)
 return <InputGroup className="composer" style={{ "--hue": hueOf(companion) } as CSSProperties}>
  {matches.length > 0 && <div className="skill-menu" role="listbox" aria-label="Skills">{matches.map((k, i) => <button type="button" key={k.id} role="option" aria-selected={i === pick % matches.length} onMouseDown={e => { e.preventDefault(); useSkill(k) }}><BookOpen /><b>/{k.id}</b><span>{k.description || k.name}</span></button>)}</div>}
  {used.length > 0 && <InputGroupAddon align="block-start" className="skill-chips">{used.map(k => <span key={k.id} className="skill-chip"><BookOpen />{k.name}<button type="button" aria-label={"Don't use " + k.name} onClick={() => setText(text.replace(skillToken(k.id), "$1").trim())}><X /></button></span>)}</InputGroupAddon>}
  <InputGroupTextarea ref={box} aria-label="Message" placeholder={placeholder} rows={2} autoFocus={autoFocus} disabled={disabled} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => {
   if (matches.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); setPick(pick + (e.key === "ArrowDown" ? 1 : matches.length - 1)); return }
   if (matches.length && (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey))) { e.preventDefault(); useSkill(matches[pick % matches.length]); return }
   if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }} />
  <InputGroupAddon align="block-end">
   <DropdownMenu><DropdownMenuTrigger asChild disabled={disabled}><InputGroupButton className="composer-add" size="icon-xs" variant="ghost" aria-label="Add a skill or a tab"><Plus /></InputGroupButton></DropdownMenuTrigger>
    <DropdownMenuContent side="top" align="start" sideOffset={8} className="w-72">
     <DropdownMenuLabel>Skills</DropdownMenuLabel>
     {skills.slice(0, 8).map(k => <DropdownMenuItem key={k.id} onSelect={() => useSkill(k)}><BookOpen />{k.name}</DropdownMenuItem>)}
     {!skills.length && <p className="mode-none">No skills yet. Make one on the new tab page, under Skills.</p>}
     {pages.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>Add a tab</DropdownMenuLabel>
      {pages.map(t => <DropdownMenuItem key={t.id} onSelect={() => { setText(`${text}${text && !text.endsWith(" ") ? " " : ""}[${t.title || host(t.url)}](${t.url}) `); box.current?.focus() }}><Globe /><span className="truncate">{t.title || host(t.url)}</span></DropdownMenuItem>)}</>}
    </DropdownMenuContent></DropdownMenu>
   <span className="composer-gap" />
   <ModeMenu ai={ai} send={send} companion={companion} onCompanion={onCompanion} disabled={!!onStop || disabled} />
   {ai.advanced && <ModelPicker ai={ai} send={send} disabled={!!onStop || disabled} />}
   {onStop && !text.trim() ? <InputGroupButton className="ai-send is-stop" size="icon-xs" variant="default" aria-label="Stop" onClick={onStop}><Square /></InputGroupButton>
    : <InputGroupButton className="ai-send" size="icon-xs" variant="default" aria-label="Send" disabled={!text.trim() || disabled} onClick={submit}><ArrowUp /></InputGroupButton>}
  </InputGroupAddon>
 </InputGroup>
}

// The AI asked something with ask_user: pick an option, write an answer, or skip.
function QuestionCard({ q, companion, send }: { q: { text: string; options: string[] }; companion?: Companion; send: Send }) {
 const [own, setOwn] = useState("")
 useEffect(() => { // 1-9 picks an option, unless the user is typing
  const key = (e: KeyboardEvent) => { const n = Number(e.key); if (n >= 1 && n <= q.options.length && !(e.target as HTMLElement).closest("input,textarea,[contenteditable]")) send("aiAnswer", { text: q.options[n - 1] }) }
  addEventListener("keydown", key); return () => removeEventListener("keydown", key)
 }, [q, send])
 return <div className="ask-card" role="group" aria-label="Question from your AI">
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
  <p>Still uses the plan you already pay for. No API keys, and nothing leaves your PC except your chats with your AI provider.</p>
  <AiPicker ai={ai} send={send} onPick={id => send("aiHarness", { harness: id })} />
  {pending}
 </div>
 if (status === "missing" || status === "installing") return <div className="ai-pane ai-center">
  <Face size={64} mood={status === "installing" ? "working" : "idle"} />
  {status === "installing" ? <>
   <h3>Installing {current.app}…</h3>
   <p>This usually takes about a minute.</p>
   {ai.setup.line && <code className="ai-setup-line" title={ai.setup.line}>{ai.setup.line}</code>}
   <Button variant="ghost" size="sm" onClick={() => send("aiSetupCancel")}>Cancel</Button>
  </> : <>
   <h3>Let's get {current.name}</h3>
   <p>{current.name} needs {current.maker}'s app on this PC. Run this in PowerShell, then sign in with your plan.</p>
   <code className="byo-cmd">{current.installCommand}</code>
   {current.installer && <>
    <Button className="ai-go" onClick={() => send("aiInstall")}>Install it for me</Button>
    <div className="ai-trust"><ShieldCheck /><span>Uses {current.maker}'s official installer from <b title={current.installer}>{host(current.installer)}</b>. It installs just for you and needs no admin rights.</span></div>
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
export function ChatView({ ai, send, mode, tabs = [], activeTab, onSettings }: { ai: AiState; send: Send; mode: "tab" | "panel"; tabs?: TabRef[]; activeTab?: TabRef; onSettings: () => void }) {
 const [tick, setTick] = useState(0)
 const provider = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const [worked, setWorked] = useState(0)
 const ticks = useRef(0)
 const [queued, setQueued] = useState("")
 const log = useRef<HTMLDivElement>(null)
 const [picked, setPicked] = useState<string>() // who a new chat in the sidebar is with
 const fresh = !ai.messages.length
 const companion = companionOf(ai, fresh && picked ? picked : ai.chatCompanion)
 const name = companion?.name ?? "your AI"
 const busy = ai.busy && ai.running === ai.chatId
 const elsewhere = ai.busy && !busy
 const [typing, setTyping] = useState(false)
 const mood = useRunMood(ai, typing)
 useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }) }, [ai.messages.length, busy, !!ai.question])
 useEffect(() => { if (!busy) return; ticks.current = 0; setTick(0); setWorked(0); const t = setInterval(() => setTick(++ticks.current), 1000); return () => { clearInterval(t); setWorked(ticks.current) } }, [busy])
 useEffect(() => { if (!ai.busy && queued && !ai.error) { send("aiSend", { text: queued }); setQueued("") } }, [ai.busy]) // eslint-disable-line react-hooks/exhaustive-deps
 const submit = (value: string) => { if (busy) setQueued(value); else send("aiSend", { text: value, companion: companion?.id }) }

 // Consecutive steps collapse into one row. A question waiting in its card isn't repeated in the log.
 const messages = ai.question && ai.messages.at(-1)?.text === ai.question.text ? ai.messages.slice(0, -1) : ai.messages
 const items: ({ role: string; text: string } | { role: "steps"; steps: string[] })[] = []
 for (const m of messages) {
  const prev = items[items.length - 1]
  if (m.role === "tool") { if (prev && "steps" in prev) prev.steps.push(m.text); else items.push({ role: "steps", steps: [m.text] }) }
  else items.push(m)
 }
 const fromAi = (i: number) => items[i]?.role === "assistant" || items[i]?.role === "steps"
 // The companion's face starts each of its turns.
 const face = (i: number) => fromAi(i - 1) ? null : <Face className="ai-turn-face" companion={companion} size={24} mood={i >= items.length - 1 ? mood : "idle"} />
 const setup = Setup({ ai, send, onSettings })
 const pages = tabs.filter(t => t.inChat && t.inChat === ai.chatId)
 const openLink = (url: string) => send("new", { url })

 return <section className="chat-view" data-mode={mode} aria-label={"Chat with " + name}>
  {setup ?? <div className="ai-log" ref={log}><div className="chat-column">
   {!items.length && (mode === "tab" ? <div className="chat-hello">
    <Face companion={companion} size={72} />
    <h3>Work with {name}</h3>
    {companion?.job && <p>{companion.job}</p>}
   </div> : <div className="ai-hello">
    <Face companion={companion} size={64} />
    <h3>What should we do?</h3>
    <p>I can read this page, search, compare and click around in my own pages.</p>
    <div className="ai-ideas">{IDEAS.map(([Icon, label, prompt]) => <button key={label} className="ai-idea" onClick={() => submit(prompt)}><span><Icon aria-hidden /></span>{label}</button>)}</div>
    <p className="ai-fine"><LockKeyhole />Never sees private tabs, passwords or cookies.</p>
   </div>)}
   {items.map((m, i) => {
    if ("steps" in m) return <div key={i} className="ai-turn">{face(i)}<details className="ai-steps-group"><summary><span className="ai-steps-icon"><Globe /></span><span className="ai-steps-text"><b>{m.steps[m.steps.length - 1]}</b>{m.steps.length > 1 && <small> (and {m.steps.length - 1} more action{m.steps.length === 2 ? "" : "s"})</small>}</span><ChevronDown className="ai-steps-chevron" /></summary><ol>{m.steps.map((s, j) => <li key={j}>{s}</li>)}</ol></details></div>
    if (m.role === "user") return <div key={i} className="ai-msg is-user"><SkillText text={m.text} skills={ai.skills} /></div>
    if (m.role !== "assistant") return <div key={i} className="ai-msg is-note">{m.text}</div>
    const { body, next } = nextSteps(m.text)
    const last = i === items.length - 1 && !busy
    return <div key={i} className="ai-turn">{face(i)}
     <div className="ai-msg is-assistant"><Markdown text={body} onLink={openLink} /></div>
     {next.length > 0 && <div className="ai-next">{next.map(s => <button key={s} className="ai-next-step" disabled={!last} onClick={() => submit(s)}><Lightbulb /><span>{s}</span></button>)}</div>}
     {last && <>{worked > 0 && <p className="ai-timer">Worked for {clock(worked)}</p>}
      <div className="ai-actions"><IconButton label="Copy" onClick={() => send("copyText", { text: body })}><Copy /></IconButton></div></>}
    </div>
   })}
   {busy && !ai.question && <div className="ai-turn">{face(items.length)}<p className="ai-timer">Working for {clock(tick)}</p></div>}
  </div></div>}
  {ai.error && <Alert variant="destructive" className="ai-error"><AlertDescription>{ai.error}</AlertDescription></Alert>}
  {!setup && <div className="ai-compose"><div className="chat-column">
   {mode === "panel" && pages.length > 0 && <button className="chat-chip is-pages" onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 />{name} has {pages.length === 1 ? "a page" : pages.length + " pages"} open<b>Show</b></button>}
   {mode === "panel" && activeTab?.url && !activeTab.inChat && <span className="chat-chip" title={activeTab.url}><Globe />{activeTab.title || host(activeTab.url)}</span>}
   {ai.question && <QuestionCard q={ai.question} companion={companion} send={send} />}
   {queued && <div className="ai-queued"><span>Up next</span><p>{queued}</p><button aria-label="Don't send" onClick={() => setQueued("")}><X /></button></div>}
   {elsewhere ? <div className="chat-elsewhere"><Face companion={companionOf(ai, ai.chats.find(c => c.id === ai.running)?.companion)} size={20} mood="working" /><span>Busy in another chat</span><Button variant="link" size="sm" onClick={() => send("chatOpen", { id: ai.running })}>Go to it</Button><Button variant="link" size="sm" onClick={() => send("aiStop")}>Stop it</Button></div>
    : <Composer ai={ai} send={send} onSubmit={submit} onTyping={setTyping} onStop={busy ? () => send("aiStop") : undefined} companion={companion} onCompanion={fresh && mode === "panel" ? setPicked : undefined} tabs={tabs}
     placeholder={busy ? (queued ? "Change what's up next…" : "Queue a follow-up…") : items.length ? "Ask a follow-up…" : mode === "tab" ? `Work with ${name}…` : "Ask anything, or tell me what to do…"} />}
   {mode === "panel" && provider && <p className="ai-usage"><Gauge />{["Your " + provider.name + " plan", ai.usage].filter(Boolean).join(" · ")}</p>}
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
   <Button variant="outline" size="sm" disabled={!ai.chats.length || ai.busy} onClick={() => send("aiDeleteAll")}><Trash2 />Delete all chats</Button></section>
 </div>
}

// The chat panel beside an ordinary page (the Chat button), or the AI settings.
export function AiPanel({ ai, send, view, setView, tabs, activeTab }: { ai: AiState; send: Send; view: "chat" | "settings"; setView: (v: "chat" | "settings") => void; tabs: TabRef[]; activeTab?: TabRef }) {
 const companion = companionOf(ai, ai.chatCompanion)
 const mood = useRunMood(ai)
 return <aside className="ai-sidebar" aria-label="Chat">
  <div className="ai-head">
   {view !== "chat" ? <IconButton label="Back" onClick={() => setView("chat")}><ArrowLeft /></IconButton> : <Face companion={companion} size={22} mood={mood} className="ai-head-buddy" />}
   <div className="ai-title"><strong>{view === "settings" ? "AI settings" : ai.chats.find(c => c.id === ai.chatId)?.title || companion?.name || "Chat"}</strong></div>
   {view === "chat" && <>
    <IconButton label="Open as a tab" disabled={!ai.chatId} onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 /></IconButton>
    <IconButton label="New chat" disabled={ai.busy || !ai.chatId} onClick={() => send("aiNew")}><MessageSquarePlus /></IconButton>
    <IconButton label="AI settings" onClick={() => setView("settings")}><Settings2 /></IconButton>
   </>}
   <IconButton label="Close chat" onClick={() => { setView("chat"); send("aiToggle") }}><X /></IconButton>
  </div>
  {view === "settings" ? <AiSettings ai={ai} send={send} done={() => setView("chat")} /> : <ChatView ai={ai} send={send} mode="panel" tabs={tabs} activeTab={activeTab} onSettings={() => setView("settings")} />}
 </aside>
}

