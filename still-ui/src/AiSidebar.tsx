import { Fragment, useEffect, useId, useLayoutEffect, useRef, useState, type ClipboardEvent as PasteEvent, type CSSProperties, type ReactElement, type ReactNode } from "react"
import { ArrowLeft, ArrowRight, ArrowUp, ArrowUpRight, BookOpen, Paperclip, Brain, Camera, Check, ChevronDown, CircleCheck, Coffee, Copy, ExternalLink, Eye, FileText, Gauge, Globe, Keyboard, Lightbulb, ListTodo, LockKeyhole, Luggage, MousePointer2, MoveVertical, Plus, Rabbit, Save, Search, Tag, Maximize2, MessageSquarePlus, Settings2, ShieldCheck, SlidersHorizontal, Square, X, type LucideIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { InputGroup, InputGroupAddon, InputGroupButton } from "@/components/ui/input-group"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { CollisionBoundary } from "@/components/ui/collision"
import { fadeTop, MAC } from "@/lib/utils"
import { AiLogo } from "./AiLogo"
import { destroy } from "./Undo"
import { toast } from "sonner"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Switch } from "@/components/ui/switch"
import { FALLBACK, Face, hueOf, showProfile, type Companion, type Mode, type Mood } from "./Buddy"
import { premadeOf, starters } from "./crew"
import { Markdown } from "./Markdown"
import { choicesOf, type Choice } from "./nextSteps"
import { FileCard, FileIcon, sizeText, type LibFile } from "./Files"
import { Approvals, type Approval, type AuditEntry, type Rule } from "./Permissions"
import { PluginLogo, usePluginData, type PluginsState } from "./Plugins"
import { useMascotVersion } from "./Mascot"
import { ApiForm, PRESETS as API_PRESETS, type ApiState } from "./ApiProviders"
import { MessageText, caretAt, dress, html, live, markup, mentions, read, shareable, textOf, units, type Known, type Mention, type Part } from "./Mention"
import { DraftHint, adopt, appliers, change, keepDraft, readDraft, rekey, sending, useDraft } from "./drafts"

type Harness = { id: string; name: string; app: string; maker: string; installed: boolean; status: string; installer: string; installCommand: string; site: string; secondary?: boolean; compatible?: boolean; forgets?: boolean; gaps?: string[]; terminalSignIn?: string; api?: boolean }
type ChatRow = { id: string; title: string; harness: string; updated: string; companion?: string; from?: string | null; unread?: boolean; archived?: boolean; noMemory?: boolean; profile?: string }
/// A chat by id: a saved one, or one of this incognito window's own.
export const chatOf = (ai: AiState | undefined, id?: string | null) => id ? ai?.chats.find(c => c.id === id) ?? ai?.privateChats?.find(c => c.id === id) : undefined
export type AiState = {
 open: boolean; harness: string; busy: boolean; error: string; profile: string; harnesses: Harness[]
 checked?: boolean // the first status check is done, so an empty status means the app can't say
 runs?: Run[]; interrupted?: { id: string; title: string; unsure: boolean }[]; task?: { state: string; reason: string; pending: string; steps: number; unsure: number } | null; queued?: string[]; files?: LibFile[]; worked?: number
 setup: { line: string; url: string; code: string }; pending: boolean
 models?: { harness: string; id: string; name: string; efforts: string[] }[]; model: string; effort: string; usage: string
 chatId?: string; chatHarness?: string; chatCompanion?: string; messages: Message[]
 question?: { text: string; options: string[]; page?: string | null; kickoff?: boolean } | null; companions?: Companion[]
 chats: ChatRow[]
 incognito?: boolean; privateChats?: ChatRow[] // an incognito window's own chats: only ever listed in that window, never with saved chats
 advanced?: boolean; skills?: Skill[]
 tiers?: Record<string, Record<Mode, { model: string; effort: string; custom: boolean; missing: boolean; failed: boolean }>>
 approvals?: Approval[]; audit?: AuditEntry[]; permissions?: Rule[]; sensitiveSites?: string[]; chatSummaries?: boolean
 plugins?: PluginsState
 apis?: ApiState
}
// who: a teammate's line (old team chats), or the teammate who asked. An ask/tell card: who asked whom for what (title),
// how it's going, the result and the child task (chat) doing it.
export type Attached = { id: string; name: string; size: number }
export type Message = { role: string; text: string; who?: string | null; to?: string | null; status?: string | null; reply?: string | null; chat?: string | null; title?: string | null; files?: Attached[] | null }
export type Skill = { id: string; name: string; description: string; when: string; body: string; stock?: boolean; edited?: boolean } // stock: one Still ships (Reset puts it back)
// A chat at work. Any number run at once. root: the user's chat a child task (a teammate asked it) started from.
export type Run = { id: string; root?: string | null; started: string; question?: string | null; options?: string[] | null; asks?: { id: string; what: string; site: string }[] }
export const isRunning = (ai: AiState | undefined, id?: string) => !!id && !!ai?.runs?.some(r => r.id === id)
const waits = (r: Run) => !!r.question || !!r.asks?.length
export const needsYou = (ai: AiState | undefined, id?: string) => !!id && !!ai?.runs?.some(r => (r.id === id || r.root === id) && waits(r))
type Send = (op: string, payload?: Record<string, unknown>) => void
type TabRef = { id: string; title: string; url: string; inChat?: string; chatId?: string; isPrivate?: boolean; favicon?: string }
const TabIcon = ({ tab }: { tab: TabRef }) => tab.favicon ? <img className="tab-favicon" src={tab.favicon} alt="" /> : <Globe />

const IDEAS = [
 [FileText, "Sum up this page", "Summarize this page in a few short bullet points."],
 [Tag, "Find it cheaper", "Find what's on this page cheaper somewhere else, and show me where."],
 [Luggage, "Plan a trip", "Help me plan a weekend trip. Ask me where I'm starting from and what I like first."],
 [Lightbulb, "Explain it simply", "Explain this page simply, like I'm new to the topic."],
] as const
const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url } }
/// What the user likes to be called, from what their companion remembers (setup saves it as the "name" fact).
export const calledBy = (c?: Companion) => c?.memory?.find(f => f.key === "name")?.text.match(/^Likes to be called (.+?)\.?$/)?.[1]
const SHELL = MAC ? "Terminal" : "PowerShell" // where install and sign-in commands run
const settingUp = (s?: string) => s === "installing" || s === "signingIn"
// "" = not checked yet, which never blocks a chat
const statusOf = (h?: Harness) => !h ? "" : h.status || (h.installed ? "" : "missing")
const ready = (h: Harness) => h.installed && !["missing", "signedOut", "needsKey", "badKey"].includes(statusOf(h))
// Claude, ChatGPT, Grok and Gemini always show, with the API providers the user added. Every other agent, and adding an
// API, waits under More agents, except the one in use, which stays in view.
const MAIN = ["claude", "chatgpt", "grok", "gemini"]
const isMain = (h: Harness) => MAIN.includes(h.id) || !!h.api
export const logoOf = (h: Harness) => h.api ? h.name : h.id
/// Every Model settings link and button opens Settings, Models.
export const openModelSettings = (send: Send) => send("openPanel", { name: "settings", value: "models" })
const MoreAgents = ({ open, count, onClick }: { open: boolean; count?: number; onClick?: () => void }) => <button type="button" className="byo-more" aria-expanded={open} onClick={onClick}>
 <span>More agents</span>{!!count && <small>{count}</small>}<ChevronDown /></button>
export const clock = (s: number) => s < 60 ? s + "s" : Math.floor(s / 60) + "m " + String(s % 60).padStart(2, "0") + "s"
export const since = (iso?: string) => iso ? Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000)) : 0
// Each step's icon, from how its label starts.
const STEP_ICONS: [RegExp, LucideIcon][] = [[/^(Used|Loaded) skill/, BookOpen], [/^(Read|Looked)/, Eye], [/^Clicked/, MousePointer2], [/^Typed/, Keyboard],
 [/^Scrolled/, MoveVertical], [/^Saved/, Save], [/^Took a screenshot/, Camera], [/^(Opened|Went|Reloaded|Switched|Closed|Waited)/, Globe]]
const stepIcon = (step: string) => STEP_ICONS.find(([re]) => re.test(step))?.[1] ?? ListTodo
// A step reads as its verb in bold and what it acted on, muted. An address shows as its site; the full one is on hover.
function Step({ step }: { step: string }) {
 const [verb, ...rest] = step.split(" "), what = rest.join(" "), url = what.match(/https?:\/\/\S+/)?.[0]
 return <span className="ai-step-line" title={url}><b>{verb}</b>{what && <span> {url ? what.replace(url, host(url)) : what}</span>}</span>
}
// Before setup makes one there's no companion: Still itself talks, with the default look.
export const companionOf = (ai: AiState | undefined, id?: string) => ai?.companions?.find(c => c.id === id) ?? ai?.companions?.[0] ?? (ai ? FALLBACK : undefined)

// A tooltip that flips and slides to stay inside the window and the chat panel, where a native title can't.
function Tip({ label, children }: { label: ReactNode; children: ReactElement }) {
 return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
 return <Tip label={label}><Button variant="ghost" size="icon-sm" aria-label={label} disabled={disabled} onClick={onClick}>{children}</Button></Tip>
}

// "Your models": every agent app Still supports, with its logo and its state on this computer, read from the app itself
// and never by signing in. Add shows how to install one, Set up how to sign in or add a key. With send, the Compatible API
// presets too, each added right here. Picking a row makes it the model for new chats. Nothing is installed unless the user asks.
export function AiPicker({ ai, onPick, send }: { ai: AiState; onPick: (id: string) => void; send?: Send }) {
 const [howTo, setHowTo] = useState("")
 const [adding, setAdding] = useState<string | null>(null) // the API preset whose form is open ("": any other)
 useEffect(() => { send?.("aiStatus") }, [send]) // a fresh look at what's installed and logged in (at most every 30 s)
 const toggle = (id: string) => setHowTo(howTo === id ? "" : id)
 const row = (h: Harness) => {
  const s = statusOf(h), chosen = ai.harness === h.id, open = howTo === h.id
  // Signed out, or installed with no way to tell (GitHub Copilot) and signed in from a terminal.
  const setUp = s === "signedOut" || (s === "" && !!h.terminalSignIn)
  const state = settingUp(s) ? <><Spinner />{s === "installing" ? "Installing…" : "Signing in…"}</>
   : s === "ready" ? <><span className="byo-ok">{h.api ? (ai.apis?.providers.find(p => p.id === h.id)?.noKey ? "Compatible API, no key" : "Uses your API key") : "Logged in"}</span><Check aria-hidden /></>
   : s === "needsKey" ? "API provider · Needs a key"
   : s === "badKey" ? "API provider · Key not accepted"
   : s === "missing" ? "Not installed"
   : s === "signedOut" && !send ? "Installed · Sign in with your plan" : "Installed"
  return <div key={h.id} className="byo-row" data-chosen={chosen || undefined} data-status={s || undefined}>
   <button className="byo-main" onClick={() => onPick(h.id)} aria-pressed={chosen}>
    <span className="byo-tile" aria-hidden><AiLogo id={h.api ? h.name : h.id} size={22} /></span>
    <span className="byo-name"><strong>{h.name}{h.compatible && <> <Badge variant="outline" className="byo-tag" title="Built from its docs, not yet tested with the real app">Compatible</Badge></>}</strong><small>{state}</small></span>
    {chosen && <Check className="ai-pick-check" aria-label="Chosen" />}
   </button>
   {setUp && (send || h.terminalSignIn) && <Button size="sm" variant="outline" className="byo-act" aria-expanded={open} onClick={() => toggle(h.id)}>Set up<ChevronDown /></Button>}
   {(s === "needsKey" || s === "badKey") && send && <Button size="sm" variant="outline" className="byo-act" onClick={() => { const keys = document.getElementById("set-apis"); if (keys) keys.scrollIntoView({ behavior: "smooth", block: "start" }); else openModelSettings(send) }}>{s === "badKey" ? "Replace key" : "Add key"}</Button>}
   {s === "missing" && <Button size="sm" variant="outline" className="byo-act" aria-expanded={open} onClick={() => toggle(h.id)}>Add<ChevronDown /></Button>}
   {open && setUp && <div className="byo-how">
    {h.terminalSignIn ? <>
     <p>{h.app} signs in from a terminal. Run this in {SHELL}, sign in with your plan in the browser it opens, then come back:</p>
     <code className="byo-cmd">{h.terminalSignIn}</code>
     <div className="ai-row">
      <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(h.terminalSignIn ?? "")}><Copy />Copy</Button>
      {send && <Button size="sm" variant="ghost" onClick={() => send("aiCheck")}>I signed in</Button>}
     </div>
    </> : send && <>
     <p>{h.app} is installed. Sign in with your {h.maker} plan in the browser it opens, then come back.</p>
     <div className="ai-row"><Button size="sm" variant="outline" onClick={() => { onPick(h.id); send("aiLogin") }}>Sign in with your plan</Button></div>
    </>}
   </div>}
   {!!h.gaps?.length && (s === "ready" || chosen) && <p className="byo-gaps">{h.gaps.join(" ")}</p>}
   {open && s === "missing" && <div className="byo-how">
    <p>Run this in {SHELL}, then come back:</p>
    <code className="byo-cmd">{h.installCommand}</code>
    <div className="ai-row">
     <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(h.installCommand)}><Copy />Copy</Button>
     {h.installer && send && <Button size="sm" variant="ghost" onClick={() => { onPick(h.id); send("aiInstall") }}>Install it for me</Button>}
     {send && <Button size="sm" variant="ghost" onClick={() => send("aiCheck")}>I installed it</Button>}
    </div>
   </div>}
  </div>
 }
 // A preset already added is a row above, under its own name.
 const presets = !send ? [] : [...API_PRESETS.filter(x => !ai.apis?.providers.some(p => p.url === x.url)).map(x => x.name), ""]
 const apiRow = (name: string) => <div key={"api-add:" + name} className="byo-row" data-status="add">
  <div className="byo-main">
   <span className="byo-tile" aria-hidden>{name ? <AiLogo id={name} size={22} /> : <Plus className="size-5" />}</span>
   <span className="byo-name"><strong>{name || "Other compatible API"} <Badge variant="outline" className="byo-tag">Compatible</Badge></strong><small>{name ? "API · Not added" : "Any OpenAI- or Claude-compatible API"}</small></span>
  </div>
  <Button size="sm" variant="outline" className="byo-act" aria-expanded={adding === name} onClick={() => setAdding(adding === name ? null : name)}>Add<ChevronDown /></Button>
  {adding === name && send && <div className="byo-how byo-api"><ApiForm start={name} send={send} done={() => setAdding(null)} /></div>}
 </div>
 const [more, setMore] = useState(false)
 const folded = [...ai.harnesses.filter(h => !isMain(h) && h.id !== ai.harness).map(row), ...presets.map(apiRow)]
 return <div className="ai-picker byo">
  {ai.harnesses.filter(h => isMain(h) || h.id === ai.harness).map(row)}
  {folded.length > 0 && <MoreAgents open={more} count={folded.length} onClick={() => setMore(!more)} />}
  {more && folded}
 </div>
}

// At the bottom of each model menu, always in view.
const ModelSettingsItem = ({ send }: { send: Send }) => <div className="ai-pick-foot"><DropdownMenuSeparator />
 <DropdownMenuItem className="ai-pick-settings" onSelect={() => openModelSettings(send)}><SlidersHorizontal />Model settings…</DropdownMenuItem></div>

// Every AI in one list: its models when it's ready, or a way to set it up. Picking another AI's model moves the chat to it.
// The main agents first; More agents opens the rest in place.
function ModelPicker({ ai, send, disabled }: { ai: AiState; send: Send; disabled?: boolean }) {
 const [more, setMore] = useState(false)
 const current = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const modelsOf = (h: Harness) => { const ms = ai.models?.filter(m => m.harness === h.id); return ms?.length ? ms : [{ harness: h.id, id: "", name: "Default", efforts: [] }] }
 const model = ai.models?.find(m => m.harness === current?.id && m.id === ai.model)
 const on = current && modelsOf(current).some(m => m.id === ai.model) ? ai.model : ""
 const pick = (h: Harness, id: string) => !current || !ready(h) ? send("aiHarness", { harness: h.id }) : send("aiModel", { harness: h.id, model: id, effort: h.id === current.id ? ai.effort : "" })
 const group = (h: Harness, i: number) => <Fragment key={h.id}>{i > 0 && <DropdownMenuSeparator />}
  {ready(h) ? modelsOf(h).map(m => <DropdownMenuItem key={m.id} onSelect={() => pick(h, m.id)}><AiLogo id={logoOf(h)} size={16} /><span className="truncate">{m.id ? m.name : h.name}</span>{h.id === current?.id && m.id === on && <Check className="ai-pick-on" aria-label="In use" />}</DropdownMenuItem>)
   : <DropdownMenuItem onSelect={() => pick(h, "")}><AiLogo id={logoOf(h)} size={16} /><span className="truncate">{h.name}</span><span className="ai-pick-setup">Set up</span></DropdownMenuItem>}
 </Fragment>
 const shown = ai.harnesses.filter(h => isMain(h) || h.id === current?.id), rest = ai.harnesses.filter(h => !shown.includes(h))
 return <>
  <DropdownMenu onOpenChange={o => { if (!o) setMore(false) }}>
   <DropdownMenuTrigger asChild disabled={disabled}><button type="button" className="ai-pick ai-model" aria-label="Model">{current && <AiLogo id={logoOf(current)} size={16} />}<span className="truncate">{!current ? "Pick your model" : model?.id ? model.name : current.name}</span><ChevronDown /></button></DropdownMenuTrigger>
   <DropdownMenuContent side="top" align="start" className="ai-model-menu">
    {shown.map(group)}
    {rest.length > 0 && <><DropdownMenuSeparator /><DropdownMenuItem className="ai-more" aria-expanded={more} onSelect={e => { e.preventDefault(); setMore(!more) }}>More agents<ChevronDown /></DropdownMenuItem>
     {more && rest.map(group)}</>}
    <ModelSettingsItem send={send} />
   </DropdownMenuContent>
  </DropdownMenu>
  {!!model?.efforts.length && <DropdownMenu>
   <DropdownMenuTrigger asChild disabled={disabled}><button type="button" className="ai-pick" aria-label="Effort"><span className="truncate">{ai.effort ? effortName(ai.effort) : "Default"} effort</span><ChevronDown /></button></DropdownMenuTrigger>
   <DropdownMenuContent side="top" align="start" className="ai-model-menu">
    {["", ...model.efforts].map(e => <DropdownMenuItem key={e || "default"} onSelect={() => send("aiModel", { model: ai.model, effort: e })}><span className="truncate">{e ? effortName(e) : "Default"} effort</span>{(ai.effort || "") === e && <Check className="ai-pick-on" aria-label="In use" />}</DropdownMenuItem>)}
    <ModelSettingsItem send={send} />
   </DropdownMenuContent>
  </DropdownMenu>}
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
   {MODES.map(([id, label, Icon, about]) => <DropdownMenuItem key={id} className="mode-item" disabled={!companion || ai.advanced} onSelect={() => { if (companion) send("companionMode", { id: companion.id, mode: id }) }}>
    <Icon className="mode-icon" /><span className="mode-text">{label}<small>{about}</small></span>{!ai.advanced && mode === id && <CircleCheck className="mode-check" />}</DropdownMenuItem>)}
   <DropdownMenuLabel className="mode-advanced"><span>Advanced</span><Switch checked={!!ai.advanced} aria-label="Pick the model and effort yourself" onCheckedChange={on => send("aiAdvanced", { on })} /></DropdownMenuLabel>
   <DropdownMenuSeparator />
   <DropdownMenuItem className="mode-settings" onSelect={() => openModelSettings(send)}><SlidersHorizontal />Model settings…</DropdownMenuItem>
  </DropdownMenuContent>
 </DropdownMenu>
}

const effortName = (e: string) => e === "xhigh" ? "Extra high" : e[0].toUpperCase() + e.slice(1)
// Settings → Models: per set-up AI, the model and effort Quick, Everyday and Thorough use, picked only from its own
// catalog. With Advanced on they're kept but not used, and the table says so.
export function TierSettings({ ai, send, only }: { ai: AiState; send: Send; only?: string }) {
 const list = ai.harnesses.filter(h => ai.tiers?.[h.id] && (!only || h.id === only))
 if (!list.length) return <p className="tiers-note">Set up an AI to pick its models here.</p>
 return <div className="tiers" data-off={ai.advanced || undefined}>
  {ai.advanced && <p className="tiers-note">Advanced is on, so these tiers are not used.</p>}
  {list.map(h => {
   const models = (ai.models ?? []).filter(m => m.harness === h.id), tiers = ai.tiers![h.id]
   return <div key={h.id} className="tier-ai" id={"tiers-" + h.id}>
    <div className="tier-head"><AiLogo id={h.id} size={16} /><span>{h.name}</span>
     <Button variant="ghost" size="sm" disabled={!MODES.some(([t]) => tiers[t]?.custom)} onClick={() => destroy({ key: "tiers:" + h.id, title: `Reset ${h.name}'s models?`, body: "The models and effort you picked for Efficient, Default and Expert go back to Still's picks.", action: "Reset", done: "Models reset", run: () => send("aiTiersReset", { harness: h.id }) })}>Reset to defaults</Button></div>
    {MODES.map(([t, label, Icon]) => {
     const tier = tiers[t], model = models.find(m => m.id === tier.model)
     const effort = model?.efforts.includes(tier.effort) ? tier.effort : "default"
     return <div key={t} className="tier-row" data-tier={t}>
      <span className="tier-name"><Icon />{label}</span>
      <Select value={tier.missing ? "missing" : tier.model || "default"} onValueChange={v => send("aiTier", { harness: h.id, tier: t, model: v === "default" ? "" : v, effort: tier.effort })}>
       <SelectTrigger size="sm" aria-label={`${h.name} ${label} model`}><SelectValue /></SelectTrigger>
       <SelectContent>{tier.missing && <SelectItem value="missing" disabled>Not available</SelectItem>}{models.map(m => <SelectItem key={m.id || "default"} value={m.id || "default"}>{m.name}</SelectItem>)}</SelectContent></Select>
      <Select value={effort} disabled={!model?.efforts.length} onValueChange={v => send("aiTier", { harness: h.id, tier: t, model: tier.model, effort: v === "default" ? "" : v })}>
       <SelectTrigger size="sm" aria-label={`${h.name} ${label} effort`}><SelectValue /></SelectTrigger>
       <SelectContent><SelectItem value="default">Default effort</SelectItem>{model?.efforts.map(e => <SelectItem key={e} value={e}>{effortName(e)} effort</SelectItem>)}</SelectContent></Select>
      {tier.failed && <small className="tier-failed">Not on your plan, so chats ran on the default model.</small>}
     </div>
    })}
   </div>
  })}
 </div>
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

// Where each chat was scrolled to while Still runs; none = at the newest message.
const scrolls = new Map<string, number>()

// An attached file: its kind, name and size.
const FileChip = ({ file, onRemove }: { file: Attached; onRemove?: () => void }) => <span className="skill-chip file-chip" title={file.name}><FileIcon path={file.name} /><span>{file.name}</span><small>{sizeText(file.size)}</small>
 {onRemove && <button type="button" aria-label={"Remove " + file.name} onClick={onRemove}><X /></button>}</span>
// Limits match the host's (MainWindow.Ai.cs Attach): 10 files a message, files up to 10 MB, images up to 5 MB.
const IMAGE = /\.(png|jpe?g|gif|webp)$/i, MAX_FILES = 10
const tooBig = (f: File) => f.size > (IMAGE.test(f.name) ? 5 : 10) * 1048576 ? `${f.name} is ${sizeText(f.size)}. ${IMAGE.test(f.name) ? "Images" : "Files"} can be up to ${IMAGE.test(f.name) ? 5 : 10} MB.` : ""

// The message box. / picks a skill, # an open tab (never a private one) or a connected app, and @ a companion: each goes
// into the text where it was typed, as a mention (Mention.tsx). Arrows, Enter or Tab and Esc work the pickers.
// Files come from + > Add files, a drop on the box or a paste; Still keeps them and the AI reads them with read_attachment.
const KEPT = "application/x-still-message" // a copy from the box: its text and mentions, so a paste keeps them whole
export function Composer({ ai, send, placeholder, onSubmit, onStop, disabled, autoFocus, onTyping, companion, onCompanion, tabs, draft: draftKey }: { draft?: string; ai: AiState; send: Send; placeholder: string; onSubmit: (text: string, tabs: string[], files: string[], draft?: string) => void; onStop?: () => void; disabled?: boolean; autoFocus?: boolean; onTyping?: (typing: boolean) => void; companion?: Companion; onCompanion?: (id: string) => void; tabs?: TabRef[] }) {
 const draft = draftKey && (ai.incognito ? "private." + draftKey : draftKey)
 const drafted = useRef(draft)
 const [parts, setParts] = useState<Part[]>([])
 const [before, setBefore] = useState("") // the text just before the caret: what the pickers look at
 const [pick, setPick] = useState(0)
 const [shut, setShut] = useState<string | null>(null) // Esc closed the picker for this text
 const [files, setFiles] = useState<Attached[]>([])
 const [dropping, setDropping] = useState(false)
 const [restored, setRestored] = useState(false) // the box came back with a draft: Draft restored, with Discard
 const me = useId()
 const partsRef = useRef(parts), filesRef = useRef(files)
 useLayoutEffect(() => { partsRef.current = parts; filesRef.current = files })
 const pending = useRef<(() => void) | null>(null), timer = useRef(0)
 const flush = () => { clearTimeout(timer.current); pending.current?.(); pending.current = null }
 const save = (p: Part[], f: Attached[]) => { // a moment after the last change, and right away on leaving the box or Still
  const key = draft, d = { text: textOf(p), parts: mentions(p).length ? p : undefined, files: f.length ? f : undefined }
  pending.current = () => keepDraft(key, d); clearTimeout(timer.current); timer.current = window.setTimeout(flush, 500)
 }
 const unsent = useRef<Attached[]>([]) // the files of the message being sent, back in the box if Still couldn't send it
 useEffect(() => { addEventListener("beforeunload", flush); return () => { removeEventListener("beforeunload", flush); flush() } }, [draft]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { // what Still kept from a pick, drop or paste in this box
  const got = (e: Event) => { // added now, or (.kept) a draft's that are still there
   const d = (e as CustomEvent).detail; if (d.to !== me && d.to !== me + ".kept") return
   if (d.files?.length) { const all = [...filesRef.current, ...d.files].slice(0, MAX_FILES); setFiles(all); if (d.to === me) save(partsRef.current, all) }
   if (d.error) toast(d.error)
  }
  const back = (e: Event) => { if ((e as CustomEvent).detail === draft && unsent.current.length) { setFiles(unsent.current); save(partsRef.current, unsent.current); unsent.current = [] } }
  addEventListener("still-attached", got); addEventListener("still-unsent", back)
  return () => { removeEventListener("still-attached", got); removeEventListener("still-unsent", back) }
 }, [me, draft]) // eslint-disable-line react-hooks/exhaustive-deps
 const take = (list: FileList | File[]) => {
  const all = [...list], room = MAX_FILES - files.length
  if (all.length > room) toast(`You can attach up to ${MAX_FILES} files to a message.`)
  for (const f of all.slice(0, Math.max(0, room))) {
   if (tooBig(f)) { toast(tooBig(f)); continue }
   const read = new FileReader()
   read.onload = () => send("aiAttach", { to: me, name: f.name || "pasted-image.png", data: String(read.result).slice(String(read.result).indexOf(",") + 1) })
   read.readAsDataURL(f)
  }
 }
 const box = useRef<HTMLDivElement>(null)
 const add = useOverBox<HTMLButtonElement>("start")
 const known: Known = { companions: ai.companions ?? [], tabs: tabs ?? [], plugins: ai.plugins?.key ? ai.plugins.connected : [], skills: ai.skills ?? [] }
 const knownRef = useRef(known)
 useMascotVersion(); usePluginData(send) // a companion's picture, or an app's logo, can come in after it's mentioned
 useEffect(() => { knownRef.current = known; if (box.current) dress(box.current, known) })
 const shown = (p: Part[]) => p.map(x => typeof x === "string" ? x : live(x, knownRef.current) ?? (x as Mention).name ?? "")
 useEffect(() => { // Undo and redo put a step back with its mentions, the caret where it was
  const el = box.current; if (el) appliers.set(el, s => { el.innerHTML = markup(typeof s.v === "string" ? [s.v] : shown(s.v), knownRef.current); if (document.activeElement === el) caretAt(el, s.c) })
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 // The draft: what was typed in this box before, its mentions too while they're still there, and its files if Still
 // still has them. A new chat's goes with it once the chat has an id.
 useLayoutEffect(() => {
  flush() // what was typed under the last key is kept under it
  const was = drafted.current, el = box.current; drafted.current = draft
  if (was && draft && was !== draft && /(^|\.)chat\.new$/.test(was) && (textOf(partsRef.current).trim() || filesRef.current.length)) {
   keepDraft(was, null); rekey(was, draft); keepDraft(draft, { text: textOf(partsRef.current), parts: mentions(partsRef.current).length ? partsRef.current : undefined, files: filesRef.current.length ? filesRef.current : undefined })
   return // the new chat got its id: what's in the box stays, now under it, with its undo steps
  }
  const kept = readDraft(draft)
  const p: Part[] = kept?.parts ? shown(kept.parts) : [kept?.text ?? ""]
  if (el) el.innerHTML = markup(p, knownRef.current)
  if (el && draft) adopt(draft, el, kept)
  setParts(read(el ?? document.createElement("div"))) // eslint-disable-line react-hooks/set-state-in-effect
  setRestored(!!(kept?.text.trim() || kept?.files?.length))
  setFiles([])
  if (kept?.files?.length) send("aiReattach", { to: me + ".kept", ids: kept.files.map(f => f.id) })
  if (kept && el && (autoFocus || document.activeElement === el)) { el.focus(); const s = getSelection(); s?.selectAllChildren(el); s?.collapseToEnd() }
 }, [draft]) // eslint-disable-line react-hooks/exhaustive-deps
 // The caret at the end of the box (it isn't in the box yet).
 const end = () => { const el = box.current, s = getSelection(); if (!el || !s) return; el.focus(); s.selectAllChildren(el); s.collapseToEnd() }
 useEffect(() => { if (autoFocus) end() }, []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => {
  const el = box.current; if (!el) return
  const caret = () => { const s = getSelection(), n = s?.anchorNode; if (n && el.contains(n)) setBefore(n.nodeType === Node.TEXT_NODE ? n.textContent!.slice(0, s.anchorOffset) : "") }
  const plain = (e: InputEvent) => { if (e.inputType.startsWith("format")) e.preventDefault() } // no bold or italics in a message
  document.addEventListener("selectionchange", caret); el.addEventListener("beforeinput", plain)
  return () => { document.removeEventListener("selectionchange", caret); el.removeEventListener("beforeinput", plain) }
 }, [])
 const text = textOf(parts)
 const sync = () => {
  const el = box.current; if (!el) return
  dress(el, known)
  const p = read(el), t = textOf(p)
  setParts(p); save(p, files); setPick(0); setShut(null); setRestored(false); onTyping?.(!!t.trim())
 }
 const attached = mentions(parts).flatMap(m => m.kind === "tab" ? [m.id] : [])
 const message = text.trim() || (files.length ? `Take a look at ${files.length === 1 ? "this file" : "these files"}.` : "")
 // The draft stays until Still says it took the message: if it couldn't, the text comes back (drafts.tsx sent).
 const submit = () => {
  if (!message || disabled) return
  flush(); sending(draft); unsent.current = files
  onSubmit(message, attached, files.map(f => f.id), draft)
  if (box.current) box.current.innerHTML = ""
  setParts([]); setBefore(""); setFiles([]); setRestored(false); onTyping?.(false)
 }
 const discard = () => { // Discard on Draft restored: the box empties, as a step to undo, and the draft goes
  const el = box.current; if (!el) return
  change(el, []); setFiles([]); pending.current = null; clearTimeout(timer.current); keepDraft(draft, null); setRestored(false); el.focus()
 }
 const skills = ai.skills ?? []
 const typed = /(^|\s)\/([\w-]*)$/.exec(before)?.[2].toLowerCase()
 const tabWord = /(^|\s)#([^\s#]*)$/.exec(before)?.[2].toLowerCase()
 const mateWord = /(^|\s)@([\w-]*)$/.exec(before)?.[2].toLowerCase()
 // Markup in place of the selection, as one step to undo, and the caret after it (Chrome would leave it before a mention).
 const insert = (h: string) => {
  const el = box.current!, s = getSelection()!, at = s.getRangeAt(0), rest = document.createRange()
  rest.setStart(at.endContainer, at.endOffset); rest.setEnd(el, el.childNodes.length)
  const after = units(read(rest.cloneContents()))
  document.execCommand("insertHTML", false, h)
  caretAt(el, units(read(el)) - after)
 }
 // A pick goes in where the caret is, in place of what was typed to find it (#lamp), with a space after.
 const put = (m: Mention, token?: RegExp) => {
  const el = box.current, s = getSelection(); if (!el || !s) return
  if (document.activeElement !== el || !s.anchorNode || !el.contains(s.anchorNode)) end()
  const n = s.anchorNode, hit = token && n?.nodeType === Node.TEXT_NODE ? token.exec(n.textContent!.slice(0, s.anchorOffset)) : null
  if (n && hit) s.setBaseAndExtent(n, s.anchorOffset - hit[0].length + hit[1].length, n, s.anchorOffset)
  insert(html(m, known) + " ")
 }
 const pickSkill = (k: Skill) => put({ kind: "skill", id: k.id, name: k.name }, /(^|\s)\/[\w-]*$/)
 const putTab = (t: TabRef) => put({ kind: "tab", id: t.id, name: t.title || host(t.url) }, /(^|\s)#[^\s#]*$/)
 const open = (tabs ?? []).filter(t => shareable(t) && !attached.includes(t.id))
 const pages = open.slice(0, 6)
 const apps = known.plugins.filter(p => !mentions(parts).some(m => m.kind === "plugin" && m.id === p.slug))
 const [menuLabel, items]: [string, { key: string; icon: ReactNode; label: string; sub: string; run: () => void }[]] = shut === text ? ["", []]
  : typed !== undefined ? ["Skills", skills.filter(k => k.id.startsWith(typed) || k.name.toLowerCase().includes(typed)).slice(0, 6).map(k => ({ key: k.id, icon: <BookOpen />, label: "/" + k.id, sub: k.description || k.name, run: () => pickSkill(k) }))]
  : tabWord !== undefined ? [apps.length ? "Tabs and apps" : "Tabs", [...open.filter(t => (t.title + " " + t.url).toLowerCase().includes(tabWord)).slice(0, 6).map(t => ({ key: t.id, icon: <TabIcon tab={t} />, label: t.title || host(t.url), sub: host(t.url), run: () => putTab(t) })),
   ...apps.filter(p => p.name.toLowerCase().includes(tabWord)).slice(0, 4).map(p => ({ key: "app." + p.slug, icon: <PluginLogo slug={p.slug} name={p.name} />, label: p.name, sub: "Connected app", run: () => put({ kind: "plugin", id: p.slug, name: p.name }, /(^|\s)#[^\s#]*$/) }))]]
  : mateWord !== undefined ? ["Companions", (ai.companions ?? []).filter(c => !mentions(parts).some(m => m.kind === "mate" && m.id === c.id) && c.name.toLowerCase().includes(mateWord)).slice(0, 6).map(c => ({ key: c.id, icon: <Face companion={c} size={22} />, label: c.name, sub: premadeOf(c)?.role ?? "Your own companion", run: () => put({ kind: "mate", id: c.id, name: c.name }, /(^|\s)@[\w-]*$/) }))]
  : ["", []]
 // Backspace just after a mention (Delete just before one) takes it out whole, as one step to undo.
 const unmention = (forward: boolean) => {
  const s = getSelection(), n = s?.anchorNode; if (!s?.isCollapsed || !n || !box.current?.contains(n)) return false
  const at = s.anchorOffset, next = n.nodeType === Node.TEXT_NODE ? (forward ? at === n.textContent!.length ? n.nextSibling : null : at === 0 ? n.previousSibling : null) : n.childNodes[forward ? at : at - 1]
  if (!(next instanceof HTMLElement) || !next.dataset.mention) return false
  const r = document.createRange(); r.selectNode(next); s.removeAllRanges(); s.addRange(r)
  return document.execCommand("delete")
 }
 const atStart = () => {
  const s = getSelection(), el = box.current; if (!el || !s?.isCollapsed || !s.anchorNode || !el.contains(s.anchorNode)) return false
  const r = document.createRange(); r.setStart(el, 0); r.setEnd(s.anchorNode, s.anchorOffset)
  return !textOf(read(r.cloneContents()))
 }
 const copy = (e: PasteEvent<HTMLDivElement>, cut: boolean) => {
  const s = getSelection(); if (!s?.rangeCount || s.isCollapsed) return
  const p = read(s.getRangeAt(0).cloneContents())
  e.preventDefault(); e.clipboardData.setData("text/plain", textOf(p)); e.clipboardData.setData(KEPT, JSON.stringify(p))
  if (cut) document.execCommand("delete")
 }
 const paste = (e: PasteEvent<HTMLDivElement>) => {
  e.preventDefault()
  if (e.clipboardData.files.length) { take(e.clipboardData.files); return }
  let p: unknown = null
  try { p = JSON.parse(e.clipboardData.getData(KEPT)) } catch { /* from somewhere else: plain text */ }
  if (Array.isArray(p)) insert(markup(p.map(x => typeof x === "string" ? x : live(x, known) ?? String((x as Mention)?.name ?? "")), known))
  else document.execCommand("insertText", false, e.clipboardData.getData("text/plain"))
 }
 const dragging = (e: { dataTransfer: DataTransfer }) => e.dataTransfer.types.includes("Files")
 return <InputGroup className={"composer" + (dropping ? " is-drop" : "")} style={{ "--hue": hueOf(companion) } as CSSProperties}
  onDragOver={e => { if (!dragging(e) || disabled) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; setDropping(true) }}
  onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDropping(false) }}
  onDrop={e => { if (!dragging(e)) return; e.preventDefault(); setDropping(false); if (!disabled) take(e.dataTransfer.files) }}>
  {dropping && <div className="composer-drop" aria-hidden><Paperclip />Drop to attach</div>}
  {items.length > 0 && <div className="skill-menu" role="listbox" aria-label={menuLabel}>{items.map((it, i) => <button type="button" key={it.key} role="option" aria-selected={i === pick % items.length} onMouseDown={e => { e.preventDefault(); it.run() }}>{it.icon}<b>{it.label}</b><span>{it.sub}</span></button>)}</div>}
  {restored && <InputGroupAddon align="block-start" className="draft-addon"><DraftHint onDiscard={discard} /></InputGroupAddon>}
  {files.length > 0 && <InputGroupAddon align="block-start" className="skill-chips">
   {files.map(f => <FileChip key={f.id} file={f} onRemove={() => { const left = files.filter(x => x !== f); setFiles(left); save(parts, left) }} />)}
  </InputGroupAddon>}
  <div ref={box} data-history={draft} role="textbox" aria-multiline aria-label="Message" aria-placeholder={placeholder} aria-disabled={disabled || undefined} data-empty={!text.trim() || undefined}
   contentEditable={!disabled} data-slot="input-group-control" className="composer-input" spellCheck
   onInput={sync} onBlur={flush} onCopy={e => copy(e, false)} onCut={e => copy(e, true)} onPaste={paste} onDragStart={e => e.preventDefault()}
   onDrop={e => { // text dropped on the box comes in as plain text
    if (dragging(e)) return
    e.preventDefault()
    const at = document.caretRangeFromPoint?.(e.clientX, e.clientY), s = getSelection()
    if (at && s) { s.removeAllRanges(); s.addRange(at) }
    document.execCommand("insertText", false, e.dataTransfer.getData("text/plain"))
   }}
   onKeyDown={e => {
    if (e.nativeEvent.isComposing) return
    if (items.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) { e.preventDefault(); setPick(pick + (e.key === "ArrowDown" ? 1 : items.length - 1)); return }
    if (items.length && (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey))) { e.preventDefault(); items[pick % items.length].run(); return }
    if (items.length && e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setShut(text); return }
    if ((e.key === "Backspace" || e.key === "Delete") && unmention(e.key === "Delete")) { e.preventDefault(); return }
    if (e.key === "Backspace" && files.length && atStart()) { e.preventDefault(); setFiles(files.slice(0, -1)); save(parts, files.slice(0, -1)); return }
    if (e.key === "Enter") { e.preventDefault(); if (e.shiftKey) document.execCommand("insertLineBreak"); else submit() } }} />
  <InputGroupAddon align="block-end">
   <DropdownMenu onOpenChange={add.measure}><DropdownMenuTrigger asChild disabled={disabled}><InputGroupButton ref={add.ref} className="composer-add" size="icon-xs" variant="ghost" aria-label="Add files, a skill or a tab"><Plus /></InputGroupButton></DropdownMenuTrigger>
    <DropdownMenuContent {...add.props} className="w-72" onCloseAutoFocus={e => e.preventDefault()}>
     <DropdownMenuItem onSelect={() => send("aiPickFiles", { to: me })}><Paperclip />Add files<span className="menu-hint">or drop them here</span></DropdownMenuItem>
     <DropdownMenuSeparator />
     <DropdownMenuLabel>Skills</DropdownMenuLabel>
     {skills.slice(0, 8).map(k => <DropdownMenuItem key={k.id} onSelect={() => pickSkill(k)}><BookOpen />{k.name}</DropdownMenuItem>)}
     {!skills.length && <p className="mode-none">No skills yet. Make one on the new tab page, under Skills.</p>}
     {pages.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>Add a tab</DropdownMenuLabel>
      {pages.map(t => <DropdownMenuItem key={t.id} onSelect={() => putTab(t)}><TabIcon tab={t} /><span className="truncate">{t.title || host(t.url)}</span></DropdownMenuItem>)}</>}
    </DropdownMenuContent></DropdownMenu>
   <span className="composer-gap" />
   <ModeMenu ai={ai} send={send} companion={companion} onCompanion={onCompanion} disabled={!!onStop || disabled} />
   {ai.advanced && <ModelPicker ai={ai} send={send} disabled={!!onStop || disabled} />}
   {onStop && !message ? <Tip label="Stop · Ctrl+."><InputGroupButton className="ai-send is-stop" size="icon-xs" variant="default" aria-label="Stop" onClick={onStop}><Square /></InputGroupButton></Tip>
    : <InputGroupButton className="ai-send" size="icon-xs" variant="default" aria-label="Send" disabled={!message || disabled} onClick={submit}><ArrowUp /></InputGroupButton>}
  </InputGroupAddon>
 </InputGroup>
}

// The AI asked something with ask_user: pick an option, write an answer, or skip.
function QuestionCard({ q, companion, send, draft }: { q: { text: string; options: string[]; page?: string | null; kickoff?: boolean }; companion?: Companion; send: Send; draft?: string }) {
 const [own, setOwn] = useState("")
 const kept = useDraft<HTMLInputElement>(draft) // a written answer is kept as a draft until it's sent
 const answer = (text: string) => { kept.done(); send("aiAnswer", { text }) }
 useEffect(() => { // 1-9 picks an option, unless the user is typing
  const key = (e: KeyboardEvent) => { const n = Number(e.key); if (n >= 1 && n <= q.options.length && !(e.target as HTMLElement).closest("input,textarea,[contenteditable]")) answer(q.options[n - 1]) }
  addEventListener("keydown", key); return () => removeEventListener("keydown", key)
 }, [q, send])
 return <div className="ask-card" role="group" aria-label="Question from your AI">
  {q.page && <div className="ask-help"><strong>Help with this page</strong><Button size="sm" variant="outline" onClick={() => send("aiHelpPage", { id: q.page })}>Open the page</Button></div>}
  <div className="ask-q"><Face companion={companion} size={22} /><p>{q.text}</p></div>
  {q.options.length > 0 && <div className="ask-options">{q.options.map((o, i) => <button key={i} className="ask-option" onClick={() => answer(o)}><kbd>{i + 1}</kbd><span>{o}</span></button>)}</div>}
  {kept.hint}
  <form className="ask-own" onSubmit={e => { e.preventDefault(); if (own.trim()) answer(own) }}>
   <input ref={kept.ref} {...kept.props} aria-label="Your answer" placeholder={q.kickoff ? "Or tell me what you're deciding…" : "Or write your own answer…"} value={own} onChange={e => setOwn(e.target.value)} />
   <Button type="button" variant="ghost" size="sm" onClick={() => answer("")}>Skip</Button>
   <Button type="submit" size="sm" disabled={!own.trim()}>Send</Button>
  </form>
 </div>
}

/// Choices a companion offers in its reply (a choices block, see nextSteps.ts): pick one, pick several then Submit, or
/// pick from a dropdown, and type your own when it allows. The pick goes back as your reply, so a card is answered once:
/// after your reply it shows what you picked and takes no more.
function ChoiceCard({ choice, answer, live, onPick }: { choice: Choice; answer?: string; live: boolean; onPick: (text: string) => void }) {
 const [sent, setSent] = useState("")
 const [picked, setPicked] = useState<string[]>([])
 const [own, setOwn] = useState("")
 const done = answer ?? sent, off = !live || !!done
 const go = (text: string) => { if (off || !text.trim()) return; setSent(text.trim()); onPick(text.trim()) }
 const chosen = (o: string) => done ? done.split("\n").includes(o) : picked.includes(o)
 const one = picked[0] ?? ""
 return <div className="ask-card choice-card" role="group" aria-label={choice.question || "Choices"} data-done={done ? "" : undefined}>
  {choice.question && <p className="choice-q">{choice.question}</p>}
  {choice.type === "dropdown" ? <form className="ask-own" onSubmit={e => { e.preventDefault(); go(one) }}>
   <Select value={done && choice.options.includes(done) ? done : one} disabled={off} onValueChange={v => setPicked([v])}>
    <SelectTrigger size="sm" className="choice-select" aria-label="Pick one"><SelectValue placeholder="Pick one…" /></SelectTrigger>
    <SelectContent>{choice.options.map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent></Select>
   <Button type="submit" size="sm" disabled={off || !one}>Send</Button>
  </form> : <div className="ask-options">{choice.options.map(o => choice.type === "multiple"
   ? <button key={o} type="button" role="checkbox" aria-checked={chosen(o)} className="ask-option" disabled={off} onClick={() => setPicked(chosen(o) ? picked.filter(x => x !== o) : [...picked, o])}><span className="choice-box" aria-hidden>{chosen(o) && <Check />}</span><span>{o}</span></button>
   : <button key={o} type="button" className="ask-option" aria-pressed={chosen(o)} disabled={off} onClick={() => go(o)}><span>{o}</span>{chosen(o) && <Check className="choice-picked" aria-hidden />}</button>)}</div>}
  {choice.type === "multiple" && <div className="choice-submit"><Button size="sm" disabled={off || !picked.length} onClick={() => go(choice.options.filter(o => picked.includes(o)).join("\n"))}>Submit</Button></div>}
  {choice.other && <form className="ask-own" onSubmit={e => { e.preventDefault(); go(own) }}>
   <input aria-label="Type your own" placeholder="Or type your own…" value={done && !choice.options.some(chosen) ? done : own} disabled={off} onChange={e => setOwn(e.target.value)} />
   <Button type="submit" size="sm" disabled={off || !own.trim()}>Send</Button>
  </form>}
 </div>
}

// Install or sign in to the chat's AI. Null when it's ready to chat.
function Setup({ ai, send, onSettings }: { ai: AiState; send: Send; onSettings: () => void }) {
 const current = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const status = statusOf(current)
 const pending = ai.pending && <p className="ai-fine">Your message runs as soon as {current?.name ?? "your model"} is ready.</p>
 if (!current) return <div className="ai-pane ai-center">
  <Face size={64} />
  <h3>Pick your model</h3>
  <p>Still runs on the AI you already pay for, through its own app on this computer. No API key needed, no credits, no extra plan. Your chats go only to your AI provider.</p>
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
   <p>{current.name} needs {current.maker}'s app on this {MAC ? "Mac" : "PC"}. Run this in {SHELL}, then sign in with your plan.</p>
   <code className="byo-cmd">{current.installCommand}</code>
   {current.installer && <>
    <Button className="ai-go" onClick={() => send("aiInstall")}>Install it for me</Button>
    <div className="ai-trust"><ShieldCheck /><span>Uses {current.maker}'s official installer from <Tip label={current.installer}><b>{host(current.installer)}</b></Tip>. It installs just for you and needs no admin rights.</span></div>
   </>}
   <div className="ai-row"><Button variant="link" size="sm" onClick={() => send("aiCheck")}>I already installed it</Button><Button variant="link" size="sm" onClick={onSettings}>Pick another model</Button></div>
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
   <Button variant="link" size="sm" onClick={onSettings}>Pick another model</Button>
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
 const known: Known = { companions: ai.companions ?? [], tabs, plugins: ai.plugins?.key ? ai.plugins.connected : [], skills: ai.skills ?? [] }
 const fresh = !ai.messages.length
 const companion = companionOf(ai, fresh && picked ? picked : ai.chatCompanion)
 const name = companion?.name ?? "your AI"
 const busy = ai.busy
 const started = ai.runs?.find(r => r.id === ai.chatId)?.started
 const [typing, setTyping] = useState(false)
 const mood = useRunMood(ai, typing)
 const back = useRef(ai.chatId ? scrolls.get(ai.chatId) : undefined) // coming back to this chat: where the user left it
 useLayoutEffect(() => {
  const el = log.current; if (!el) return
  if (back.current != null) { el.scrollTop = back.current; back.current = undefined } else el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
 }, [ai.messages.length, busy, !!ai.question])
 const pinned = useRef(true) // the user is at the bottom of the chat
 const keepScroll = (e: { currentTarget: HTMLDivElement }) => {
  fadeTop(e); const el = e.currentTarget
  pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 8
  if (ai.chatId) { if (el.scrollHeight - el.scrollTop - el.clientHeight < 8) scrolls.delete(ai.chatId); else scrolls.set(ai.chatId, el.scrollTop) }
 }
 // Timed from when the run started, so it reads right after switching chats.
 useEffect(() => { if (!busy) return; const count = () => setTick(since(started)); count(); const t = setInterval(count, 1000); return () => clearInterval(t) }, [busy, started])
 // While it works, a message waits as a follow-up (Still queues it) until the run ends or the user sends it now.
 // "Don't remember this chat": a chat that exists flips its own flag, a new one starts off the record.
 const chat = chatOf(ai, ai.chatId)
 const [offRecord, setOffRecord] = useState(false)
 const forget = chat ? !!chat.noMemory : offRecord
 const submit = (value: string, tabs: string[] = [], files: string[] = [], draft?: string) => send("aiSend", { text: value, companion: companion?.id, draft, ...(!chat && offRecord && { noMemory: true }), ...(tabs.length && { tabs }), ...(files.length && { files }) })
 const you = calledBy(companion)
 const parent = chat?.from ? chatOf(ai, chat.from) : undefined
 const childStatus = busy ? (needsYou(ai, ai.chatId) ? "needs" : "working") : ai.task?.state === "failed" ? "failed" : ai.task?.reason === "stopped" ? "stopped" : "replied"

 // Consecutive steps collapse into one row. A question waiting in its card isn't repeated in the log.
 const messages = ai.question && ai.messages.at(-1)?.text === ai.question.text ? ai.messages.slice(0, -1) : ai.messages
 const items: (Message | { role: "steps"; steps: string[]; who?: string | null })[] = []
 for (const m of messages) {
  const prev = items[items.length - 1]
  if (m.role === "tool") { if (prev && "steps" in prev && prev.who == m.who) prev.steps.push(m.text); else items.push({ role: "steps", steps: [m.text], who: m.who }) }
  else items.push(m)
 }
 const fromAi = (i: number) => ["assistant", "steps", "file", "search", "read", "ask", "tell"].includes(items[i]?.role)
 // The companion's avatar starts each of its turns, left of the first line, with its name as the tooltip. Everything in
 // the turn lines up right of it, and what follows in the same turn sits closer (is-more). A teammate's line has its face.
 const whoOf = (i: number) => items[i]?.who ?? ai.chatCompanion
 const same = (i: number) => fromAi(i - 1) && whoOf(i - 1) === whoOf(i)
 const face = (i: number) => {
  if (same(i)) return null
  const c = companionOf(ai, whoOf(i)) ?? companion, n = c?.name ?? name
  return <button type="button" className="ai-turn-face profile-open" title={n} aria-label={`${n}'s profile`} onClick={() => showProfile(c)}><Face companion={c} size={40} mood={i >= items.length - 1 ? mood : "idle"} /></button>
 }
 const turn = (i: number) => same(i) ? "ai-turn is-more" : "ai-turn"
 const setup = Setup({ ai, send, onSettings })
 // Text that grows after it's drawn (a table, a card, the next steps) keeps the end of the chat in view while the user is there.
 useEffect(() => {
  const el = log.current; if (!el || typeof ResizeObserver === "undefined") return
  const keep = new ResizeObserver(() => { if (pinned.current) el.scrollTop = el.scrollHeight })
  keep.observe(el); if (el.firstElementChild) keep.observe(el.firstElementChild)
  return () => keep.disconnect()
 }, [ai.chatId, !!setup])
 const pages = tabs.filter(t => t.inChat && t.inChat === ai.chatId)
 const openLink = (url: string) => send("new", { url })

 return <section className="chat-view" data-mode={mode} aria-label={"Chat with " + name}>
  {!setup && chat?.from && <div className="task-head"><div className="chat-column">
   <Button variant="ghost" size="sm" className="task-back" onClick={() => send(mode === "panel" ? "aiOpenChat" : "chatOpen", { id: chat.from })}><ArrowLeft /><span>Back to {parent?.title ?? "the chat"}</span></Button>
   <StatusPill status={childStatus} /><span className="task-profile"><Globe />{chat.profile === "companion" ? "Companion profile" : "Your profile"}</span>{busy && <Button variant="outline" size="xs" onClick={() => send("aiStop", { id: chat.id })}><Square />Stop</Button>}
  </div></div>}
  {setup ?? <div className="ai-log" ref={log} onScroll={keepScroll}><div className="chat-column">
   {!items.length && !ai.question && (mode === "tab" ? <div className="chat-hello">
    <button type="button" className="profile-open chat-hello-face" aria-label={`${name}'s profile`} onClick={() => showProfile(companion)}><Face companion={companion} size={168} follow gesture="wave" gestureAt={1} /></button>
    <h3>{you ? `Hi ${you}! What are we working on?` : `Hi, I'm ${name}. What are we working on?`}</h3>
    <p>{companion?.job || "Ask me anything, or hand me a task. I work in my own background tabs while you keep browsing."}</p>
    <div className="chat-starters">{starters(interests, companion, 4).map(([label, prompt]) => <button key={label} onClick={() => submit(prompt)}><Lightbulb aria-hidden />{label}</button>)}</div>
   </div> : <div className="ai-hello">
    <Face companion={companion} size={64} />
    <h3>What should we do?</h3>
    <p>I can read this page, search the web, compare and click around in my own background tabs. Switch models any time, even mid-task.</p>
    <div className="ai-ideas">{IDEAS.map(([Icon, label, prompt]) => <button key={label} className="ai-idea" onClick={() => submit(prompt)}><span><Icon aria-hidden /></span>{label}</button>)}</div>
    <p className="ai-fine"><LockKeyhole />Never sees private tabs, passwords or cookies.</p>
   </div>)}
   {items.map((m, i) => {
    if ("steps" in m) {
     // One row: the latest step and how many came before it. More than one step opens into the full list.
     const live = busy && i === items.length - 1, latest = m.steps[m.steps.length - 1], Icon = stepIcon(latest), more = m.steps.length - 1
     const row = <><span className="ai-step-icon"><Icon /></span><span className="ai-step-text"><Step step={latest} />{more > 0 && <small>+ {more} more</small>}</span>
      {live ? <Spinner className="ai-steps-state" aria-label="Working" /> : <Check className="ai-steps-state is-done" aria-label="Done" />}</>
     return <div key={i} className={turn(i)}>{face(i)}{more ? <details className="ai-steps-group"><summary>{row}<ChevronDown className="ai-steps-chevron" /></summary>
      <ol>{m.steps.map((s, j) => { const StepIcon = stepIcon(s); return <li key={j}><span className="ai-step-icon"><StepIcon /></span><Step step={s} /></li> })}</ol></details>
      : <div className="ai-steps-group is-single"><div className="ai-steps-row">{row}</div></div>}</div>
    }
    if (m.role === "file") return <div key={i} className={turn(i)}>{face(i)}<FileCard path={m.text} send={send} onOpen={onFile} /></div>
    if (m.role === "search" || m.role === "read") return <div key={i} className={turn(i)}>{face(i)}<LookedUp m={m} onLink={openLink} /></div>
    if (m.role === "user" && m.who) { const asker = companionOf(ai, m.who); return <div key={i} className="ai-msg is-user is-teammate" style={{ "--hue": hueOf(asker) } as CSSProperties}>
     <span className="ai-asker"><Face companion={asker} size={20} />{asker?.name ?? "A teammate"} asked</span><MessageText text={m.text} known={known} /></div> }
    if (m.role === "user") return <div key={i} className="ai-msg is-user"><MessageText text={m.text} known={known} />{!!m.files?.length && <div className="msg-files">{m.files.map(f => <FileChip key={f.id} file={f} />)}</div>}</div>
    if (m.role === "ask" || m.role === "tell") return <div key={i} className={turn(i)}>{face(i)}<DelegationRow m={m} ai={ai} send={send} mode={mode} onLink={openLink} /></div>
    if (m.role !== "assistant") return <div key={i} className="ai-msg is-note">{m.text}</div>
    const { body, choice } = choicesOf(m.text)
    const after = items[i + 1], answer = after && !("steps" in after) && after.role === "user" ? after.text : undefined
    return <div key={i} className={turn(i)}>{face(i)}
     <div className="ai-msg is-assistant"><Markdown text={body} onLink={openLink} onCopy={text => { send("copyText", { text }); toast("Copied") }} /></div>
     {choice && <ChoiceCard choice={choice} answer={answer} live={i === items.length - 1 && !busy} onPick={text => submit(text)} />}
     <div className="ai-actions"><IconButton label="Copy" onClick={() => { send("copyText", { text: body }); toast("Copied") }}><Copy /></IconButton></div>
    </div>
   })}
   {busy && !ai.question && <div className={turn(items.length)}>{face(items.length)}<p className="ai-timer">{items.length ? "Working · " + clock(tick) : `${name} is writing…`}</p></div>}
  </div></div>}
  {!busy && ai.chatId && ai.task?.state === "interrupted" && <Alert className="task-bar"><AlertDescription>{ai.task.unsure
    ? `Still closed while ${name} was mid-task, and one step may not have finished. ${name} checks it first and asks you again.`
    : `Still closed while ${name} was mid-task.`}</AlertDescription><Button size="sm" onClick={() => send("aiResume", { id: ai.chatId })}>Resume</Button></Alert>}
  {!busy && ai.chatId && ai.task?.state === "waiting" && ai.task.reason === "signin" && <Alert className="task-bar"><AlertDescription>{name} is waiting: sign in to carry on.</AlertDescription>
   <Button size="sm" variant="outline" onClick={() => send("aiResume", { id: ai.chatId })}>Resume</Button><Button size="sm" onClick={() => send("aiLogin")}>Sign in</Button></Alert>}
  {ai.error && <Alert variant="destructive" className="ai-error"><AlertDescription>{ai.error}</AlertDescription><Button size="sm" variant="outline" className="ai-error-copy" onClick={() => { send("copyText", { text: ai.error }); toast("Details copied") }}><Copy />Copy details</Button></Alert>}
  {!setup && <div className="ai-compose"><div className="chat-column">
   {mode === "panel" && pages.length > 0 && <button className="chat-chip is-pages" onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 />{name} has {pages.length === 1 ? "a page" : pages.length + " pages"} open<b>Show</b></button>}
   {mode === "panel" && activeTab?.url && !activeTab.inChat && <Tip label={activeTab.url}><span className="chat-chip"><Globe />{activeTab.title || host(activeTab.url)}</span></Tip>}
   {ai.question && <QuestionCard q={ai.question} companion={companion} send={send} draft={"answer." + (ai.chatId ?? "new")} />}
   {!!ai.approvals?.length && <Approvals list={ai.approvals} companion={companion} companions={ai.companions} send={send} incognito={ai.incognito} />}
   {queued.length > 0 && <div className="ai-queued"><span>Up next</span><p>{queued.join("\n\n")}</p><Button variant="outline" size="sm" onClick={() => send("aiNow")}>Send now</Button><Tip label="Don't send"><button aria-label="Don't send" onClick={() => send("aiUnqueue")}><X /></button></Tip></div>}
   {!chat?.from && <><Composer draft={"chat." + (ai.chatId ?? "new")} ai={ai} send={send} onSubmit={submit} onTyping={setTyping} onStop={busy ? () => send("aiStop") : undefined} companion={companion} onCompanion={fresh && mode === "panel" ? setPicked : undefined} tabs={tabs}
    placeholder={busy ? (queued.length ? "Add to what's up next…" : "Add a next step…") : items.length ? `Reply to ${name}…` : mode === "tab" ? `Work with ${name}…` : "Ask anything, or tell me what to do…"} />
   <div className="chat-under">
    {ai.incognito ? <p className="chat-incognito"><LockKeyhole />Incognito chat: Still keeps nothing from it and deletes it when you close this window. {provider?.name ?? "Your model"} and the sites {name} visits still get what's sent to them, {provider?.api ? "and Still writes none of it to disk." : provider?.forgets ? `and ${provider.app || provider.name} is told not to save it on this computer.` : `and ${provider?.app || provider?.name || "its app"} may keep its own record.`} Connected apps are off in incognito windows. Memory: read only.</p>
    : companion && <Tip label={forget ? `${name} won't remember anything from this chat` : `${name} remembers useful things from this chat`}><label className="chat-memory"><Switch size="sm" aria-label="Don't remember this chat" checked={forget} onCheckedChange={on => chat ? send("chatNoMemory", { id: chat.id, on }) : setOffRecord(on)} />Don't remember this chat</label></Tip>}
    {!ai.incognito && chat && <ProfileChip chat={chat} busy={busy} send={send} />}
    {mode === "panel" && provider && (provider.maker || ai.usage) && <p className="ai-usage"><Gauge />{[provider.maker && !provider.api && "Your " + provider.name + " plan", ai.usage].filter(Boolean).join(" · ")}</p>}
   </div></>}
  </div></div>}
 </section>
}

/// Where this chat's pages open (Settings → Where companions browse): the user's own profile, or the companion profile
/// with its own sign-ins. Switching closes the chat's pages and tells its AI before its next step.
function ProfileChip({ chat, busy, send }: { chat: ChatRow; busy: boolean; send: Send }) {
 const companion = chat.profile === "companion"
 const pick = (profile: string) => send("aiChatProfile", { id: chat.id, profile })
 return <DropdownMenu>
  <DropdownMenuTrigger asChild disabled={busy}><button type="button" className="chat-profile" aria-label={`Browses in ${companion ? "the companion profile" : "your profile"}`} title={busy ? "Change it when this chat isn't working" : undefined}><Globe />{companion ? "Companion profile" : "Your profile"}<ChevronDown /></button></DropdownMenuTrigger>
  <DropdownMenuContent align="start" className="chat-profile-menu">
   <DropdownMenuLabel>Where this chat browses</DropdownMenuLabel>
   <DropdownMenuItem onSelect={() => pick("regular")}><span>Your profile<small>Your sign-ins</small></span>{!companion && <Check />}</DropdownMenuItem>
   <DropdownMenuItem onSelect={() => pick("companion")}><span>Companion profile<small>Its own sign-ins, apart from yours</small></span>{companion && <Check />}</DropdownMenuItem>
  </DropdownMenuContent>
 </DropdownMenu>
}

const PILL: Record<string, string> = { working: "Working", needs: "Needs you", replied: "Done", failed: "Failed", stopped: "Stopped" }
const StatusPill = ({ status }: { status: string }) => <span className="delegation-pill" data-status={status}>{status === "working" && <Spinner />}{PILL[status] ?? status}</span>

/// R18: a teammate's help as one row among the steps: who asked whom for what, and how it's going. It opens to what was
/// asked and the result; View opens the child task. Never the prompt Still sent.
function DelegationRow({ m, ai, send, mode, onLink }: { m: Message; ai: AiState; send: Send; mode: "tab" | "panel"; onLink: (url: string) => void }) {
 const [open, setOpen] = useState(false)
 const mate = (id?: string | null) => ai.companions?.find(c => c.id === id)
 const from = mate(m.who), to = mate(m.to), working = (m.status ?? "working") === "working"
 const status = working && needsYou(ai, m.chat ?? "") ? "needs" : m.status ?? "working"
 return <div className="ai-steps-group delegation" data-status={status} data-open={open || undefined}>
  <div className="ai-steps-row">
   <button type="button" className="delegation-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
    <span className="delegation-faces" aria-hidden><Face companion={from} size={20} /><ArrowRight /><Face companion={to} size={20} mood={working ? "working" : "idle"} /></span>
    <span className="ai-step-line"><b>{from?.name ?? "A former teammate"}</b> asked <b>{to?.name ?? "a former teammate"}</b>{m.title ? ` for ${m.title}` : <span>: {m.text}</span>}</span>
    <StatusPill status={status} /><ChevronDown className="ai-steps-chevron" aria-hidden />
   </button>
   {m.chat && <Tip label="View"><Button variant="ghost" size={mode === "panel" ? "icon-xs" : "xs"} className="delegation-view" aria-label={`View ${to?.name ?? "their"} work`} onClick={() => send(mode === "panel" ? "aiOpenChat" : "chatOpen", { id: m.chat })}>{mode === "panel" ? <ArrowUpRight /> : "View"}</Button></Tip>}
  </div>
  {open && <div className="delegation-body">
   <p className="delegation-asked">{m.text}</p>
   {m.reply && <div className="delegation-result"><Markdown text={choicesOf(m.reply).body} onLink={onLink} /></div>}
   {working && m.chat && <Button variant="outline" size="xs" onClick={() => send("aiStop", { id: m.chat })}><Square />Stop</Button>}
  </div>}
 </div>
}

// The chat panel beside an ordinary page (the Chat button). Its gear opens Settings, Models.
export function AiPanel({ ai, send, tabs, activeTab, onFile }: { ai: AiState; send: Send; tabs: TabRef[]; activeTab?: TabRef; onFile: (path: string) => void }) {
 const companion = companionOf(ai, ai.chatCompanion)
 const mood = useRunMood(ai)
 const [panel, setPanel] = useState<HTMLElement | null>(null)
 return <aside className="ai-sidebar" aria-label="Chat" ref={setPanel}><CollisionBoundary.Provider value={panel}>
  <div className="ai-head">
   <button type="button" className="profile-open ai-head-buddy" title={companion?.name} aria-label={`${companion?.name ?? "Companion"}'s profile`} onClick={() => showProfile(companion)}><Face companion={companion} size={22} mood={mood} /></button>
   <div className="ai-title"><strong>{chatOf(ai, ai.chatId)?.title || companion?.name || "Chat"}</strong></div>
   <IconButton label="Open as a tab" disabled={!ai.chatId} onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 /></IconButton>
   <IconButton label="New chat" disabled={!ai.chatId} onClick={() => send("aiNew")}><MessageSquarePlus /></IconButton>
   <IconButton label="Model settings" onClick={() => openModelSettings(send)}><Settings2 /></IconButton>
   <IconButton label="Close chat" onClick={() => send("aiToggle")}><X /></IconButton>
  </div>
  <ChatView ai={ai} send={send} mode="panel" tabs={tabs} activeTab={activeTab} onSettings={() => openModelSettings(send)} onFile={onFile} />
 </CollisionBoundary.Provider></aside>
}


// Top right: the chats at work (green spinner), the ones waiting on you (amber) and new replies (blue).
// A question can be answered right here.
// Screen readers hear when a chat starts, needs you, or finishes.
export function RunAnnouncer({ ai }: { ai: AiState }) {
 const [say, setSay] = useState("")
 const last = useRef<Record<string, boolean>>({})
 useEffect(() => {
  const runs = ai.runs ?? [], title = (id: string) => chatOf(ai, id)?.title || "Your chat", lines: string[] = []
  const now: Record<string, boolean> = Object.fromEntries(runs.map(r => [r.id, waits(r)]))
  for (const r of runs) if (!(r.id in last.current)) lines.push(title(r.id) + ": working"); else if (now[r.id] && !last.current[r.id]) lines.push(title(r.id) + " needs you")
  for (const id in last.current) if (!(id in now)) lines.push(title(id) + ": done")
  last.current = now
  if (lines.length) setSay(lines.join(". "))
 }, [ai.runs, ai.chats, ai.privateChats])
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
 const runs = ai.runs ?? [], unread = ai.chats.filter(c => c.unread && !c.archived && !c.from && !isRunning(ai, c.id)).slice(0, 6), apps = tabs.filter(t => t.inChat?.startsWith("app:")), empty = !runs.length && !unread.length && !apps.length
 useEffect(() => { if (empty) setOpen(false) }, [empty]) // eslint-disable-line react-hooks/exhaustive-deps
 if (empty) return null
 const waiting = runs.filter(waits).length
 const chat = (id: string) => chatOf(ai, id)
 return <DropdownMenu open={open} onOpenChange={setOpen}>
  <DropdownMenuTrigger asChild><Button variant="ghost" size="sm" className="tasks-button" aria-label={`Running tasks: ${runs.length} running${waiting ? `, ${waiting} need you` : ""}${unread.length ? `, ${unread.length} new` : ""}`} title="Running tasks · Ctrl+Shift+K">
   {runs.length > waiting ? <Spinner className="tasks-spin" /> : <ListTodo />}{runs.length > 0 && <b>{runs.length}</b>}
   {waiting > 0 && <i className="is-needs" />}{unread.length > 0 && <i className="is-unread" />}
  </Button></DropdownMenuTrigger>
  <DropdownMenuContent align="end" sideOffset={6} className="tasks-menu">
   <DropdownMenuLabel>Running tasks</DropdownMenuLabel>
   {runs.map(r => { const c = chat(r.id); return <div key={r.id} className="tasks-item">
    <DropdownMenuItem onSelect={() => send("chatOpen", { id: r.id })}><Face companion={companionOf(ai, c?.companion)} size={22} mood={waits(r) ? "needs" : "working"} />
     <span className="tasks-title">{c?.title ?? "Chat"}<small>{(waits(r) ? "Needs you" : "Working · " + clock(since(r.started))) + (c?.profile === "companion" ? " · Companion profile" : "")}</small></span>
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
