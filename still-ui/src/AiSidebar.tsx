import { createElement, Fragment, useEffect, useId, useLayoutEffect, useRef, useState, type ClipboardEvent as PasteEvent, type CSSProperties, type ReactElement, type ReactNode } from "react"
import { ArrowDownRight, ArrowLeft, ArrowRight, ArrowUp, ArrowUpRight, Ban, BookOpen, Paperclip, Brain, Camera, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, ClipboardPaste, Coffee, Copy, ExternalLink, Eye, FileText, Gauge, Globe, History, Keyboard, Lightbulb, ListTodo, LockKeyhole, Luggage, MousePointer2, MoveVertical, Pencil, Plus, Rabbit, RotateCcw, Save, Search, Tag, Maximize2, MessageSquarePlus, Settings2, ShieldCheck, SlidersHorizontal, Square, X, Scale, Zap, type LucideIcon, Download, Ellipsis, RefreshCw, Share, Trash2, FolderOpen, FolderX, Pause, Play } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { InputGroup, InputGroupAddon, InputGroupButton } from "@/components/ui/input-group"
import { Dialog, DialogContent, DialogFooter, DialogTitle } from "@/components/ui/dialog"
import { createPortal } from "react-dom"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { CollisionBoundary } from "@/components/ui/collision"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
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
import { Approvals, AUTONOMY, levelOf, type Approval, type Autonomy, type AuditEntry, type Rule } from "./Permissions"
import { PluginLogo, usePluginData, type PluginsState } from "./Plugins"
import { useMascotVersion } from "./Mascot"
import { ApiForm, PRESETS as API_PRESETS, type ApiState } from "./ApiProviders"
import { MessageText, caretAt, dress, html, live, markup, mentions, read, shareable, textOf, units, type Known, type Mention, type Part } from "./Mention"
import { adopt, appliers, caretIn, keepDraft, readDraft, rekey, sending, useDraft } from "./drafts"

type Harness = { id: string; name: string; app: string; maker: string; installed: boolean; status: string; installer: string; installCommand: string; site: string; secondary?: boolean; compatible?: boolean; forgets?: boolean; gaps?: string[]; terminalSignIn?: string; api?: boolean; billing?: string }
type ChatRow = { id: string; title: string; harness: string; updated: string; companion?: string; from?: string | null; unread?: boolean; archived?: boolean; noMemory?: boolean; profile?: string }
/// A chat by id: a saved one, or one of this incognito window's own.
export const chatOf = (ai: AiState | undefined, id?: string | null) => id ? ai?.chats.find(c => c.id === id) ?? ai?.privateChats?.find(c => c.id === id) : undefined
export type AiState = {
 open: boolean; harness: string; busy: boolean; error: string; profile: string; harnesses: Harness[]
 checked?: boolean // the first status check is done, so an empty status means the app can't say
 runs?: Run[]; interrupted?: { id: string; title: string; unsure: boolean }[]; task?: { state: string; reason: string; pending: string; steps: number; unsure: number } | null; queued?: { text: string; files?: { name: string; size: number }[] }[]; files?: LibFile[]; worked?: number
 setup: { line: string; url: string; code: string }; pending: boolean
 models?: { harness: string; id: string; name: string; efforts: string[] }[]; model: string; effort: string; usage: string
 chatId?: string; chatHarness?: string; chatCompanion?: string; chatFolder?: string | null; nextFolder?: string | null; messages: Message[]
 messagesFrom?: number // the host sends a long chat's last 300 messages: where they start in the whole chat
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
export type Message = { role: string; text: string; who?: string | null; to?: string | null; status?: string | null; reply?: string | null; chat?: string | null; title?: string | null; files?: Attached[] | null; answer?: boolean; took?: number | null; model?: string | null; effort?: string | null }
export type Skill = { id: string; name: string; description: string; when: string; body: string; stock?: boolean; edited?: boolean; source?: string; plugin?: boolean; only?: string[] } // stock: one Still ships (Reset puts it back); source: where an added one came from; plugin: it came with programs
// A chat at work. Any number run at once. root: the user's chat a child task (a teammate asked it) started from.
export type Run = { id: string; root?: string | null; started: string; question?: string | null; options?: string[] | null; tool?: string; target?: string; asks?: { id: string; what: string; site: string; action?: string; why?: string }[] }
/// What a companion is doing right now, in the present tense: from the tool it's running and its target (a site, a
/// search, a teammate), as the host sends them. Between tools it's thinking.
const DOING: Record<string, string> = {
 web_search: "Searching for “$”", read_url: "Reading $", open_tab: "Opening $", navigate: "Going to $", read_page: "Reading $", find: "Looking through $",
 click: "Clicking on $", type: "Typing on $", press_key: "Pressing a key on $", scroll: "Scrolling $", wait_for: "Waiting for $", screenshot: "Looking at $",
 go_back: "Going back", go_forward: "Going forward", reload: "Reloading $", switch_tab: "Switching to $", close_tab: "Closing a tab", save_file: "Saving $",
 upload_file: "Attaching a file", handle_dialog: "Answering a dialog on $", ask_user: "Waiting for your answer", ask_companion: "Asking $", tell_companion: "Handing work to $",
 remember: "Saving to memory", recall: "Checking memory", forget: "Updating memory", read_knowledge: "Reading notes", update_knowledge: "Updating notes", load_skill: "Getting ready",
 read_attachment: "Reading your file", list_tabs: "Checking the tabs", offer_routine: "Suggesting a routine", list_companions: "Checking the team", list_profiles: "Checking profiles",
 run_plugin_action: "Using $", get_plugin_tools: "Opening $", find_plugins: "Looking for an app", list_connected_plugins: "Checking your apps", open_memory_source: "Opening a source",
 list_files: "Looking in $", read_file: "Reading $", write_file: "Writing $", edit_file: "Editing $", delete_file: "Deleting $", request_folder: "Asking for a folder",
}
const ALONE: Record<string, string> = { web_search: "Searching the web", ask_companion: "Asking a teammate", tell_companion: "Handing work to a teammate", run_plugin_action: "Using an app", get_plugin_tools: "Opening an app", save_file: "Saving a file", wait_for: "Waiting for the page", list_files: "Looking through the folder" }
export const doing = (tool = "", target = "") => !tool ? "Thinking about the next step" : !target && ALONE[tool] ? ALONE[tool] : (DOING[tool] ?? "Working on $").replace("$", target || "the page")
/// A value that changes at most every ms (the step line: fast tools would flicker), always ending on the latest.
export function useSettled<T>(value: T, ms: number) {
 const [shown, setShown] = useState(value), at = useRef(0)
 useEffect(() => {
  const wait = at.current + ms - Date.now()
  const go = () => { at.current = Date.now(); setShown(value) }
  if (wait <= 0) { go(); return }
  const t = setTimeout(go, wait); return () => clearTimeout(t)
 }, [value, ms])
 return shown
}
export const isRunning = (ai: AiState | undefined, id?: string) => !!id && !!ai?.runs?.some(r => r.id === id)
const waits = (r: Run) => !!r.question || !!r.asks?.length
export const needsYou = (ai: AiState | undefined, id?: string) => !!id && !!ai?.runs?.some(r => (r.id === id || r.root === id) && waits(r))
type Send = (op: string, payload?: Record<string, unknown>) => void
/// How long ago, short: 5m, 3h, 2d.
export const ago = (iso: string) => { const m = (Date.now() - Date.parse(iso)) / 6e4; return m < 60 ? Math.max(1, Math.round(m)) + "m" : m < 1440 ? Math.round(m / 60) + "h" : Math.round(m / 1440) + "d" }
const dayOf = (iso: string) => { const d = new Date(iso), now = new Date(); const days = Math.round((new Date(now.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 864e5); return days <= 0 ? "Today" : days === 1 ? "Yesterday" : days < 7 ? "This week" : "Earlier" }
/// Chats in a row of day groups (Today, Yesterday, This week, Earlier), in the order they come.
export const byDay = <T extends { updated: string }>(chats: T[]) => chats.reduce<[string, T[]][]>((all, c) => { const day = dayOf(c.updated); if (all.at(-1)?.[0] === day) all.at(-1)![1].push(c); else all.push([day, [c]]); return all }, [])
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
// Each step's icon, from how its label starts: while it runs, once it's done, or if it didn't happen.
const STEP_ICONS: [RegExp, LucideIcon][] = [[/^(Didn't|Nothing|Stopped) /, Ban], [/^(Used|Loaded) skill/, BookOpen], [/^(Search|Ran \d+ search)/, Search], [/^Think/, Lightbulb], [/^(Read|Look)/, Eye], [/^Click/, MousePointer2], [/^Typ/, Keyboard],
 [/^Scroll/, MoveVertical], [/^Sav/, Save], [/^(Wrot|Writ|Edit)/, Pencil], [/^Delet/, Trash2], [/^(Took|Taking) a screenshot/, Camera], [/^(Open|Went|Going|Reload|Switch|Clos|Wait)/, Globe]]
const stepIcon = (step: string) => STEP_ICONS.find(([re]) => re.test(step))?.[1] ?? ListTodo
const StepIcon = ({ step }: { step: string }) => <span className="ai-step-icon">{createElement(stepIcon(step))}</span>
// The work view: a turn's steps as a light timeline, a small icon each on a thin line, in muted words. Addresses,
// searches and file names are monospace. Repeats in a row fold into one line ("Ran 3 searches") that opens to each.
// While the turn runs its steps are all in view and the one running shimmers; once it ends two or more fold under
// "Worked for 1m 03s" and the tick joins only when every step worked (a step with a status didn't, or never said).
const short = (url: string) => { const s = url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""); return s.length > 48 ? s.slice(0, 47) + "…" : s }
const MONO = /(https?:\/\/\S+|\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?(?:\/\S*)?|(?=[\w.-]*[a-z])[\w-]+(?:\.[\w-]+)+(?::\d+)?(?:\/\S*)?)/i // an address, a site or a file name
function Words({ step }: { step: string }) {
 return <span className="ai-step-line">{step.split(MONO).map((p, i) => i % 2 ? <code key={i} className="ai-mono" title={p}>{short(p)}</code> : p)}</span>
}
const FOLDS: Record<string, (n: number) => string> = { search: n => `Ran ${n} searches`, Read: n => `Read ${n} pages`, file: n => `Read ${n} files`, Opened: n => `Opened ${n} pages`,
 Went: n => `Went to ${n} pages`, Clicked: n => `Clicked ${n} times`, Typed: n => `Typed ${n} times`, Scrolled: n => `Scrolled ${n} times`, Saved: n => `Saved ${n} files`, Pressed: n => `Pressed ${n} keys` }
// Which steps fold together: one still going, or one that didn't work, stays on its own line.
const FILE = /^Read \S.*\.(pdf|txt|csv|tsv|md|json|docx?|xlsx?|pptx?|png|jpe?g|gif|webp|html?|xml|zip)$/i // read_attachment names the file
const foldOf = (m: Message) => m.role === "search" ? "search" : m.role === "read" ? "Read" : m.status ? "" : FILE.test(m.text) ? "file" : m.text.split(" ")[0]
function Look({ m, onLink }: { m: Message; onLink: (url: string) => void }) {
 let data: { q?: string; url?: string; title?: string; results?: { title: string; url: string; snippet: string }[] } = {}
 try { data = JSON.parse(m.text) } catch { return null }
 const link = (url: string, label: ReactNode) => <Tip label={url}><a href={url} onClick={e => { e.preventDefault(); onLink(url) }}>{label}</a></Tip>
 if (m.role === "read") return <li className="ai-work-row ai-look"><span className="ai-step-icon"><Globe /></span><span className="ai-step-text">Read {link(data.url ?? "", <code className="ai-mono">{short(data.url ?? "")}</code>)}{data.title && <small> · {data.title}</small>}</span></li>
 const results = data.results ?? []
 return <li><details className="ai-look"><summary className="ai-work-row"><span className="ai-step-icon"><Search /></span><span className="ai-step-text">Searched <code className="ai-mono">{data.q}</code><small> · {results.length} result{results.length === 1 ? "" : "s"}</small></span><ChevronDown className="ai-steps-chevron" /></summary>
  <ol className="ai-look-results">{results.map(r => <li key={r.url}>{link(r.url, r.title || host(r.url))}<small>{host(r.url)}</small>{r.snippet && <p>{r.snippet}</p>}</li>)}</ol></details></li>
}
const PICTURE = /^Read \S.*\.(png|jpe?g|gif|webp)$/i // a picture it read, from its folder or your files: it opens big on a click
const picturesOf = (messages: Message[]) => [...new Set(messages.filter(m => m.role === "tool" && !m.status && PICTURE.test(m.text)).map(m => m.text))]
function WorkStep({ m, onLink, onPicture }: { m: Message; onLink: (url: string) => void; onPicture?: (step: string) => void }) {
 if (m.role === "search" || m.role === "read") return <Look m={m} onLink={onLink} />
 const words = <Words step={m.text} />
 return <li className={"ai-work-row" + (m.status === "working" ? " is-live" : m.status === "failed" ? " is-failed" : "")}><StepIcon step={m.text} />{onPicture && !m.status && PICTURE.test(m.text)
  ? <button type="button" className="ai-step-text ai-step-picture" onClick={() => onPicture(m.text)}>{words}</button> : <span className="ai-step-text">{words}</span>}</li>
}
// A picture a companion read, big. Left and Right (or the arrows under it) step through the others it read in this chat.
function StepPictures({ chat, step, all, onStep }: { chat: string; step: string; all: string[]; onStep: (step: string | null) => void }) {
 useLift(true)
 const at = all.indexOf(step), go = (by: number) => { if (all[at + by]) onStep(all[at + by]) }, id = "step:" + chat + ":" + step
 return <Dialog open onOpenChange={open => { if (!open) onStep(null) }}><DialogContent className="app-dialog file-preview" aria-describedby={undefined}
  onKeyDown={e => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); go(e.key === "ArrowLeft" ? -1 : 1) } }}>
  <DialogTitle>{step.slice(5).split(/[\\/]/).pop()}{all.length > 1 && at >= 0 && <small> · {at + 1} of {all.length}</small>}</DialogTitle>
  <Picture id={id} name={step.slice(5)} ask={{ op: "aiPicture", id, chat, step }} />
  {all.length > 1 && <DialogFooter className="picture-steps"><Button variant="ghost" size="icon" aria-label="Previous picture" disabled={at <= 0} onClick={() => go(-1)}><ChevronLeft /></Button>
   <Button variant="ghost" size="icon" aria-label="Next picture" disabled={at < 0 || at >= all.length - 1} onClick={() => go(1)}><ChevronRight /></Button></DialogFooter>}
 </DialogContent></Dialog>
}
function Work({ steps, live, took, onLink, onPicture }: { steps: Message[]; live: boolean; took?: number; onLink: (url: string) => void; onPicture?: (step: string) => void }) {
 const rows: { fold: string; steps: Message[] }[] = []
 for (const m of steps) { const fold = foldOf(m), last = rows[rows.length - 1]; if (fold && FOLDS[fold] && last?.fold === fold) last.steps.push(m); else rows.push({ fold, steps: [m] }) }
 const list = <ol className="ai-work-rows">{rows.map((r, i) => {
  if (r.steps.length === 1) return <WorkStep key={i} m={r.steps[0]} onLink={onLink} onPicture={onPicture} />
  return <li key={i}><details className="ai-work-fold"><summary className="ai-work-row"><StepIcon step={r.fold === "search" ? "Search" : r.fold === "Read" ? "Opened" : r.steps[0].text} /><span className="ai-step-text">{FOLDS[r.fold](r.steps.length)}</span><ChevronDown className="ai-steps-chevron" /></summary>
   <ol>{r.steps.map((m, j) => <WorkStep key={j} m={m} onLink={onLink} onPicture={onPicture} />)}</ol></details></li>
 })}</ol>
 if (live) return <div className="ai-work is-live">{list}</div>
 const state = steps.some(s => s.status === "failed") ? <X className="ai-steps-state is-failed" aria-label="Didn't finish" /> : !steps.some(s => s.status) && <Check className="ai-steps-state is-done" aria-label="Done" />
 if (steps.length === 1) return <div className="ai-work is-single">{list}{state}</div> // one step needs no fold
 return <details className="ai-work"><summary className="ai-work-head">{took ? "Worked for " + clock(took) : steps.length + " steps"}{state}<ChevronDown className="ai-steps-chevron" /></summary>{list}</details>
}

// Under a turn's final answer (once a turn, not under the lines between its steps): copy it as plain text, share it, run your message again (the last answer only), and more: copy as Markdown, save as a file.
const plainOf = (md: string) => md.replace(/^\s*```.*$/gm, "").replace(/^#{1,6}\s+/gm, "").replace(/!?\[([^\]]*)\]\(([^)\s]+)\)/g, (_, t: string, u: string) => t && t !== u ? `${t} (${u})` : u)
 .replace(/\*\*|__|`/g, "").replace(/(^|[^\w*])\*(?=\S)([^*\n]+?)\*(?![\w*])/g, "$1$2").replace(/\n{3,}/g, "\n\n").trim()
// used: the reply that ends its run, which says the model and effort it ran on.
function ReplyActions({ body, title, again, used, send }: { body: string; title: string; again?: Message; used?: Message; send: Send }) {
 const [asking, setAsking] = useState(false)
 const copy = (text: string) => { send("copyText", { text }); toast("Copied") }
 const share = async () => {
  const text = plainOf(body)
  try { if (navigator.share) return await navigator.share({ title, text }) } catch (e) { if ((e as Error).name === "AbortError") return }
  copy(text) // no share sheet here: copied, to paste where it goes
 }
 if (asking && again) return <div className="ai-actions is-asking"><span>Forget this reply and run your message again?</span><Button size="sm" variant="ghost" onClick={() => setAsking(false)}>Cancel</Button>
  <Button size="sm" onClick={() => { send("aiEdit", { was: again.text, text: again.text }); setAsking(false) }}>Regenerate</Button></div>
 return <div className="ai-actions">
  <IconButton label="Copy" onClick={() => copy(plainOf(body))}><Copy /></IconButton>
  <IconButton label="Share" onClick={share}><Share /></IconButton>
  {again && <IconButton label="Regenerate" onClick={() => setAsking(true)}><RefreshCw /></IconButton>}
  <DropdownMenu><Tip label="More"><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="More"><Ellipsis /></Button></DropdownMenuTrigger></Tip>
   <DropdownMenuContent align="start"><DropdownMenuItem onSelect={() => copy(body)}><Copy />Copy as Markdown</DropdownMenuItem>
    <DropdownMenuItem onSelect={() => send("saveText", { name: title, text: body })}><Download />Save as file</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
  {used?.model && <span className="ai-used">{used.model} · {used.effort ? effortName(used.effort) + " effort" : "Default effort"}</span>}
 </div>
}

// Before setup makes one there's no companion: Still itself talks, with the default look.
export const companionOf = (ai: AiState | undefined, id?: string) => ai?.companions?.find(c => c.id === id) ?? ai?.companions?.[0] ?? (ai ? FALLBACK : undefined)

// A tooltip that flips and slides to stay inside the window and the chat panel, where a native title can't.
function Tip({ label, children }: { label: ReactNode; children: ReactElement }) {
 return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>
}

function IconButton({ label, onClick, disabled, pressed, expanded, children }: { label: string; onClick: () => void; disabled?: boolean; pressed?: boolean; expanded?: boolean; children: ReactNode }) {
 return <Tip label={label}><Button variant="ghost" size="icon-sm" aria-label={label} aria-pressed={pressed} aria-expanded={expanded} aria-haspopup={expanded === undefined ? undefined : "dialog"} disabled={disabled} onClick={onClick}>{children}</Button></Tip>
}

// "Your models": every agent app Still supports, with its logo and its state on this computer, read from the app itself
// and never by signing in. Add shows how to install one. Set up picks an app that signs in in the browser and goes to its
// sign-in card (onSetUp leaves Settings for it); for one signed in from a terminal it shows the command. With send, the
// Compatible API presets too, each added right here. Picking a row makes it the model for new chats. Nothing is installed unless the user asks.
export function AiPicker({ ai, onPick, send, onSetUp }: { ai: AiState; onPick: (id: string) => void; send?: Send; onSetUp?: () => void }) {
 const [howTo, setHowTo] = useState("")
 const [adding, setAdding] = useState<string | null>(null) // the API preset whose form is open ("": any other)
 useEffect(() => { send?.("aiStatus") }, [send]) // a fresh look at what's installed and logged in (at most every 30 s)
 const toggle = (id: string) => setHowTo(howTo === id ? "" : id)
 const row = (h: Harness) => {
  const s = statusOf(h), chosen = ai.harness === h.id, open = howTo === h.id
  // Signed out, or installed with no way to tell (GitHub Copilot) and signed in from a terminal.
  const setUp = s === "signedOut" || (s === "" && !!h.terminalSignIn)
  const state = settingUp(s) ? <><Spinner />{s === "installing" ? "Installing…" : "Signing in…"}</>
   : s === "ready" ? <><span className="byo-ok">{h.api ? (ai.apis?.providers.find(p => p.id === h.id)?.noKey ? "Compatible API, no key" : "Uses your API key") : h.billing ? "Ready" : "Logged in"}</span><Check aria-hidden /></>
   : s === "needsKey" ? "API provider · Needs a key"
   : s === "badKey" ? "API provider · Key not accepted"
   : s === "missing" ? "Not installed"
   : s === "signedOut" && !send ? "Installed · Sign in" : "Installed"
  return <div key={h.id} className="byo-row" data-chosen={chosen || undefined} data-status={s || undefined}>
   <button className="byo-main" onClick={() => onPick(h.id)} aria-pressed={chosen}>
    <span className="byo-tile" aria-hidden><AiLogo id={h.api ? h.name : h.id} size={22} /></span>
    <span className="byo-name"><strong>{h.name}{h.compatible && <> <Badge variant="outline" className="byo-tag" title="Built from its docs, not yet tested with the real app">Compatible</Badge></>}</strong><small>{state}</small></span>
    {chosen && <Check className="ai-pick-check" aria-label="Chosen" />}
   </button>
   {setUp && h.terminalSignIn && <Button size="sm" variant="outline" className="byo-act" aria-expanded={open} onClick={() => toggle(h.id)}>Set up<ChevronDown /></Button>}
   {setUp && !h.terminalSignIn && send && <Button size="sm" variant="outline" className="byo-act" onClick={() => { send("aiHarness", { harness: h.id, waitToSignIn: true }); onSetUp?.() }}>Set up</Button>}
   {(s === "needsKey" || s === "badKey") && send && <Button size="sm" variant="outline" className="byo-act" onClick={() => { const keys = document.getElementById("set-apis"); if (keys) keys.scrollIntoView({ behavior: "smooth", block: "start" }); else openModelSettings(send) }}>{s === "badKey" ? "Replace key" : "Add key"}</Button>}
   {s === "missing" && <Button size="sm" variant="outline" className="byo-act" aria-expanded={open} onClick={() => toggle(h.id)}>Add<ChevronDown /></Button>}
   {open && setUp && h.terminalSignIn && <div className="byo-how">
    <p>{h.app} signs in from a terminal. Run this in {SHELL}, finish signing in in the browser it opens, then come back:</p>
    <code className="byo-cmd">{h.terminalSignIn}</code>
    <div className="ai-row">
     <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(h.terminalSignIn ?? "")}><Copy />Copy</Button>
     {send && <Button size="sm" variant="ghost" onClick={() => send("aiCheck")}>I signed in</Button>}
    </div>
   </div>}
   {!!h.billing && <p className="byo-gaps byo-billing">{h.billing}</p>}
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
 ["efficient", "Quick", Rabbit, "Fast answers that use less"],
 ["default", "Everyday", Coffee, "Your AI app's usual setup, right for most things"],
 ["expert", "Thorough", Brain, "Its strongest model, taking its time on hard jobs"],
]
const AUTONOMY_ICON: Record<Autonomy, LucideIcon> = { ask: ShieldCheck, balanced: Scale, keepgoing: Zap }
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
// The mode menu opens above the whole box with a small gap, its right edge on its pill's, kept 8 px inside the chat panel
// or the page column (so never over the tabs or the address bar). It never flips down: with no room it scrolls inside.
const MODE_MENU_W = 280
function useOverPill() {
 const ref = useRef<HTMLButtonElement>(null)
 const [at, setAt] = useState<{ boundary?: Element; offset: number; lift: number; width: number }>({ offset: 0, lift: 0, width: MODE_MENU_W })
 const measure = (open: boolean) => {
  const pill = ref.current?.getBoundingClientRect(), box = ref.current?.closest(".composer")?.getBoundingClientRect()
  const boundary = ref.current?.closest(".ai-sidebar, .page-column") ?? undefined, r = boundary?.getBoundingClientRect()
  if (!open || !pill || !box || !boundary || !r) return
  const b = { left: r.left + boundary.clientLeft, right: r.left + boundary.clientLeft + boundary.clientWidth } // inside its border, as the menu's own fit is
  const width = Math.min(MODE_MENU_W, b.right - b.left - 16), right = Math.max(Math.min(pill.right, b.right - 8), b.left + 8 + width)
  setAt({ boundary, offset: pill.right - right, lift: pill.top - box.top, width })
 }
 return { ref, measure, props: { side: "top" as const, align: "end" as const, alignOffset: at.offset, sideOffset: 8 + at.lift, avoidCollisions: false, collisionBoundary: at.boundary, style: { width: at.width } } }
}
function ModeMenu({ ai, send, companion, onCompanion, onOpen, disabled }: { ai: AiState; send: Send; companion?: Companion; onCompanion?: (id: string) => void; onOpen?: (open: boolean) => void; disabled?: boolean }) {
 const [find, setFind] = useState("")
 const over = useOverPill()
 // Advanced flipped from its switch leaves the switch where it was: the modes above it come or go, so the menu scrolls
 // by the difference, and what scrolling can't cover it takes off its own top (the rows below then scroll) until it
 // closes. The menu sits on its bottom edge, so the switch's place is worked out from there (the menu's own move to it
 // lands a frame later).
 const flip = useRef<{ sw: HTMLElement; y: number; bottom: number } | null>(null), cut = useRef(0)
 useLayoutEffect(() => {
  const f = flip.current, m = f?.sw.closest<HTMLElement>(".mode-menu")
  flip.current = null
  if (!f || !m) return
  const off = () => f.bottom - m.offsetHeight + f.sw.getBoundingClientRect().top - m.getBoundingClientRect().top - f.y
  const shorten = (v: number) => { cut.current = Math.max(0, v); m.style.maxHeight = `calc(var(--radix-dropdown-menu-content-available-height) - ${cut.current}px)` }
  let d = off()
  if (d > 0 && cut.current) { const back = Math.min(cut.current, d); shorten(cut.current - back); d = off() }
  if (d) { m.scrollTop += d; d = off() }
  if (d < -.5) shorten(cut.current + parseFloat(getComputedStyle(m).maxHeight) - (m.offsetHeight + d))
 }, [ai.advanced])
 const mode = companion?.mode ?? "default", autonomy = levelOf(companion)
 const mates = (ai.companions ?? []).filter(c => c.name.toLowerCase().includes(find.trim().toLowerCase()))
 return <DropdownMenu onOpenChange={o => { over.measure(o); onOpen?.(o); cut.current = 0; if (!o) setFind("") }}>
  <DropdownMenuTrigger asChild disabled={disabled}><button type="button" ref={over.ref} className="mode-chip" aria-label="Companion and mode"><Face companion={companion} size={20} /><span>{ai.advanced ? "Advanced" : MODES.find(m => m[0] === mode)?.[1]}</span><ChevronDown /></button></DropdownMenuTrigger>
  <DropdownMenuContent {...over.props} className="mode-menu">
   {onCompanion && <>
    <label className="mode-find-row"><Search className="mode-icon" /><input className="mode-find" aria-label="Find a companion" placeholder="Find a companion…" value={find} onChange={e => setFind(e.target.value)} onKeyDown={e => e.stopPropagation()} /></label>
    <div className="mode-mates">{mates.map(c => <DropdownMenuItem key={c.id} onSelect={() => onCompanion(c.id)}><Face companion={c} size={22} />{c.name}{c.id === companion?.id && <CircleCheck className="mode-check" />}</DropdownMenuItem>)}</div>
    {!mates.length && <p className="mode-none">No one by that name.</p>}
    <DropdownMenuSeparator />
   </>}
   <DropdownMenuLabel className="mode-label">Mode</DropdownMenuLabel>
   {!ai.advanced && MODES.map(([id, label, Icon, about]) => <DropdownMenuItem key={id} className="mode-item" disabled={!companion} onSelect={() => { if (companion) send("companionMode", { id: companion.id, mode: id }) }}>
    <Icon className="mode-icon" /><span className="mode-text">{label}<small>{about}</small></span>{mode === id && <CircleCheck className="mode-check" />}</DropdownMenuItem>)}
   <DropdownMenuLabel className="mode-advanced"><Settings2 className="mode-icon" /><span className="mode-text">Advanced<small>Pick the model and effort yourself</small></span><Switch checked={!!ai.advanced} aria-label="Pick the model and effort yourself" onClick={e => { const sw = e.currentTarget, m = sw.closest(".mode-menu"); if (m) flip.current = { sw, y: sw.getBoundingClientRect().top, bottom: m.getBoundingClientRect().bottom } }} onCheckedChange={on => send("aiAdvanced", { on })} /></DropdownMenuLabel>
   <DropdownMenuSeparator />
   <DropdownMenuLabel className="mode-label">{companion ? "Autonomy for " + companion.name : "Autonomy"}</DropdownMenuLabel>
   {(Object.keys(AUTONOMY) as Autonomy[]).map(id => { const Icon = AUTONOMY_ICON[id]; return <DropdownMenuItem key={id} className="mode-item" disabled={!companion} onSelect={() => { if (companion) send("companionAutonomy", { id: companion.id, level: id }) }}>
    <Icon className="mode-icon" /><span className="mode-text">{AUTONOMY[id].name}<small>{AUTONOMY[id].short}</small></span>{companion && autonomy === id && <CircleCheck className="mode-check" />}</DropdownMenuItem> })}
   <div className="mode-foot"><DropdownMenuSeparator />
    <DropdownMenuItem className="mode-settings" onSelect={() => openModelSettings(send)}><SlidersHorizontal className="mode-icon" />Model settings…</DropdownMenuItem></div>
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
      {tier.failed && <small className="tier-failed">Not available on your account, so chats ran on the default model.</small>}
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

// A dialog of the chat lifts Still above the page while it's open, like App's own (the side panel sits beside a page).
const useLift = (open: boolean) => useEffect(() => {
 if (!open) return
 const tell = (n: number) => { dispatchEvent(new CustomEvent("still-dialog", { detail: n })) }
 tell(1); return () => tell(-1)
}, [open])
// An attached file: a picture of it if it's an image (else its kind's icon), its name and size. A picture opens big on a click.
function FileChip({ file, onRemove }: { file: Attached; onRemove?: () => void }) {
 const thumb = useThumb(file), [open, setOpen] = useState(false)
 useLift(open)
 const body = <>{thumb ? <img className="file-thumb" src={thumb} alt="" /> : <FileIcon path={file.name} />}<span>{file.name}</span><small>{sizeText(file.size)}</small></>
 return <span className="skill-chip file-chip" title={file.name}>
  {thumb ? <button type="button" className="file-open" aria-label={"Preview " + file.name} onClick={() => setOpen(true)}>{body}</button> : body}
  {onRemove && <button type="button" className="file-x" aria-label={"Remove " + file.name} onClick={onRemove}><X /></button>}
  {open && <Dialog open onOpenChange={setOpen}><DialogContent className="app-dialog file-preview" aria-describedby={undefined}><DialogTitle>{file.name}</DialogTitle><Picture id={file.id} name={file.name} /></DialogContent></Dialog>}</span>
}
// The whole picture, asked for when it opens (the chip keeps only a small copy); ask: another way to get it. The last one
// stays up while the next comes, so stepping through doesn't flash.
function Picture({ id, name, ask }: { id: string; name: string; ask?: Record<string, unknown> }) {
 const [src, setSrc] = useState<string | null>(null)
 useEffect(() => {
  const got = (e: Event) => { const d = (e as CustomEvent).detail; if (d.id === id) setSrc(String(d.data ?? "")) }
  addEventListener("still-thumb", got); window.chrome?.webview?.postMessage(ask ?? { op: "aiThumb", id })
  return () => removeEventListener("still-thumb", got)
 }, [id]) // eslint-disable-line react-hooks/exhaustive-deps -- id names what ask asks for
 return src ? <img src={src} alt={name} /> : src === "" ? <p className="picture-gone">This picture isn't there any more.</p> : <Spinner />
}
// A long paste in the box: its first line. It opens to all of it, and in the box it can go back into the message as text.
function PasteChip({ text, onRemove, onInline }: { text: string; onRemove?: () => void; onInline?: () => void }) {
 const [open, setOpen] = useState(false), inlined = useRef(false)
 useLift(open)
 return <span className="skill-chip file-chip paste-chip" title="Pasted text">
  <button type="button" className="file-open" aria-label="Open pasted text" onClick={() => setOpen(true)}><ClipboardPaste /><span>{text.trim().split("\n")[0]}</span><small>Pasted text</small></button>
  {onRemove && <button type="button" className="file-x" aria-label="Remove pasted text" onClick={onRemove}><X /></button>}
  {open && <Dialog open onOpenChange={setOpen}><DialogContent className="app-dialog paste-dialog" aria-describedby={undefined} onCloseAutoFocus={e => { if (inlined.current) { e.preventDefault(); onInline?.() } }}><DialogTitle>Pasted text</DialogTitle><pre>{text}</pre>
   {onInline && <DialogFooter><Button variant="outline" onClick={() => { inlined.current = true; setOpen(false) }}>Put it in the message</Button></DialogFooter>}</DialogContent></Dialog>}</span>
}
// Long pastes go to the AI in the message, each between these marks, and a sent message shows each as a pill again.
const PASTED = /\n*<pasted-text>\n([\s\S]*?)\n<\/pasted-text>/g
const pasted = (t: string) => `<pasted-text>\n${t}\n</pasted-text>`
const unpaste = (text: string) => { const pastes: string[] = []; return { rest: text.replace(PASTED, (_, t: string) => { pastes.push(t); return "" }), pastes } }
// Still hands a kept image back as a data URL (aiThumb; the page's rules allow only those) and the chip keeps a 64-pixel copy,
// so each file is asked for once. "" means there's no picture: the chip shows the icon.
const thumbs = new Map<string, string>()
const shrink = (src: string) => new Promise<string>(done => {
 const img = new Image()
 img.onload = () => {
  try {
   const k = Math.min(1, 64 / Math.max(1, Math.min(img.naturalWidth, img.naturalHeight))), c = document.createElement("canvas")
   c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k))
   c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height); done(c.toDataURL("image/png"))
  } catch { done(src) }
 }
 img.onerror = () => done(""); img.src = src
})
function useThumb(file: Attached) {
 const [src, setSrc] = useState(thumbs.get(file.id))
 useEffect(() => {
  if (src !== undefined || !IMAGE.test(file.name) || file.size > 5 * 1048576) return // the AI apps take pictures up to 5 MB, so Still shows those
  const got = (e: Event) => {
   const d = (e as CustomEvent).detail; if (d.id !== file.id) return
   if (thumbs.has(d.id)) setSrc(thumbs.get(d.id)); else shrink(String(d.data ?? "")).then(s => { thumbs.set(d.id, s); setSrc(s) })
  }
  addEventListener("still-thumb", got); window.chrome?.webview?.postMessage({ op: "aiThumb", id: file.id })
  return () => removeEventListener("still-thumb", got)
 }, [file.id, file.name, file.size, src])
 return src
}
const IMAGE = /\.(png|jpe?g|gif|webp)$/i, LONG_PASTE = 2000, PASTE_FILE = 25 * 1024 // a paste of 2,000 characters or more is a pill, and over 25 KB a file
// Any number of files, of any kind, up to 500 MB each (the host checks too: MainWindow.Ai.cs AttachPiece). A file goes to Still 4 MB at a time.
const MAX_FILE = 500 * 1048576, PIECE = 4 * 1048576
const tooBig = (f: File) => f.size > MAX_FILE ? `${f.name} is ${sizeText(f.size)}. Files can be up to 500 MB.` : ""
const base64 = (b: Blob) => new Promise<string>((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).slice(String(r.result).indexOf(",") + 1)); r.onerror = () => no(r.error); r.readAsDataURL(b) })
const newKey = () => [...crypto.getRandomValues(new Uint8Array(8))].map(b => b.toString(16).padStart(2, "0")).join("")
type Coming = { key: string; name: string; size: number; done: number } // a file on its way in, and how much of it is in

// The message box. / picks a skill, # an open tab (never a private one) or a connected app, and @ a companion: each goes
// into the text where it was typed, as a mention (Mention.tsx). Arrows, Enter or Tab and Esc work the pickers.
// Files come from + > Add files, a drop on the box or a paste; Still keeps them and the AI reads them with read_attachment.
const KEPT = "application/x-still-message" // a copy from the box: its text and mentions, so a paste keeps them whole
// One of your messages: Copy on any, Edit and Reset on the latest. Either one forgets what came after it and runs it again.
// An edit not sent yet is a draft under the chat's edit key, with its caret and whether the box was open: it's back,
// open, after switching tabs or chats, closing the panel, a reload or a restart. Cancel keeps the text for the next Edit,
// and so does Send until the chat shows the new message (Still can refuse it). It goes once the chat shows the message it
// was sent as, or another message is the latest.
function MyMessage({ m, known, send, latest, draft }: { m: Message; known: Known; send: Send; latest: boolean; draft?: string }) {
 const key = latest ? draft : undefined, kept = readDraft(key), mine = kept?.was === m.text ? kept : null
 const [editing, setEditing] = useState<string | null>(mine?.open ? mine.text : null), [resetting, setResetting] = useState(false)
 const box = useDraft<HTMLTextAreaElement>(editing === null ? undefined : key)
 useEffect(() => { if (key && kept && (!mine || !mine.open && mine.text === m.text)) keepDraft(key, null) }, [key, m.text]) // eslint-disable-line react-hooks/exhaustive-deps
 const open = () => { const text = mine?.text ?? m.text; setEditing(text); keepDraft(key, { ...mine, text, was: m.text, open: true, sel: mine?.sel ?? [text.length, text.length] }) }
 const shut = (text: string) => { keepDraft(key, { ...readDraft(key), text, was: m.text, open: false }); setEditing(null) }
 const close = () => { if (editing !== null && editing !== m.text) shut(editing); else { box.done(); setEditing(null) } }
 const again = (text: string) => { send("aiEdit", { was: m.text, text }); setResetting(false); if (editing !== null) shut(editing) }
 if (editing !== null && latest) return <div className="ai-msg is-user is-editing">
  <textarea ref={box.ref} {...box.props} className="ai-edit-box" aria-label="Edit your message" autoFocus rows={Math.min(8, editing.split("\n").length + 1)} value={editing} onChange={e => setEditing(e.target.value)}
   onKeyDown={e => { if (e.key === "Escape") close(); else if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (editing.trim()) again(editing.trim()) } }} />
  <p className="ai-edit-note">Sending replaces the reply below and stops anything still running. What it already did on websites stays done.</p>
  <div className="ai-edit-actions"><Button size="sm" variant="ghost" onClick={close}>Cancel</Button><Button size="sm" disabled={!editing.trim()} onClick={() => again(editing.trim())}>Send</Button></div>
 </div>
 const { rest, pastes } = unpaste(m.text)
 return <div className={"ai-msg is-user" + (resetting ? " is-resetting" : "")}><MessageText text={rest} known={known} />{!!(m.files?.length || pastes.length) && <div className="msg-files">{pastes.map((t, i) => <PasteChip key={i} text={t} />)}{m.files?.map(f => <FileChip key={f.id} file={f} />)}</div>}
  <div className="ai-msg-actions">{resetting && latest
   ? <><span>Forget the reply and run this again?</span><Button size="sm" variant="ghost" onClick={() => setResetting(false)}>Cancel</Button><Button size="sm" onClick={() => again(m.text)}>Reset</Button></>
   : <><Tip label="Copy"><button type="button" aria-label="Copy message" onClick={() => navigator.clipboard?.writeText(m.text).then(() => toast("Copied."), () => toast("Couldn't copy that."))}><Copy /></button></Tip>
    {latest && <Tip label="Edit"><button type="button" aria-label="Edit message" onClick={open}><Pencil /></button></Tip>}
    {latest && <Tip label="Reset: forget the reply and run this again"><button type="button" aria-label="Reset message" onClick={() => setResetting(true)}><RotateCcw /></button></Tip>}</>}
  </div>
 </div>
}
export function Composer({ ai, send, placeholder, onSubmit, onStop, disabled, autoFocus, onTyping, companion, onCompanion, tabs, chat, draft: draftKey }: { chat?: string; draft?: string; ai: AiState; send: Send; placeholder: string; onSubmit: (text: string, tabs: string[], files: string[], draft?: string) => void; onStop?: () => void; disabled?: boolean; autoFocus?: boolean; onTyping?: (typing: boolean) => void; companion?: Companion; onCompanion?: (id: string) => void; tabs?: TabRef[] }) {
 const draft = draftKey && (ai.incognito ? "private." + draftKey : draftKey)
 const drafted = useRef(draft)
 const [parts, setParts] = useState<Part[]>([])
 const [before, setBefore] = useState("") // the text just before the caret: what the pickers look at
 const [pick, setPick] = useState(0)
 const [shut, setShut] = useState<string | null>(null) // Esc closed the picker for this text
 const [files, setFiles] = useState<Attached[]>([])
 const [held, setHeld] = useState<boolean | null>(null) // Advanced as it was when the mode menu opened: its pill stays put under the open menu
 const [coming, setComing] = useState<Coming[]>([])
 const acks = useRef(new Map<string, (done: number) => void>()), stopped = useRef(new Set<string>()), queue = useRef(Promise.resolve())
 const [dropping, setDropping] = useState(false)
 const [pastes, setPastes] = useState<string[]>([]) // long pastes, a pill each
 const group = useRef<HTMLDivElement>(null), [zone, setZone] = useState<HTMLElement | null>(null) // where files drop in: the whole chat, or the box on the new tab page
 const me = useId()
 // The folder this chat works in: its own or its companion's; before it starts, the one picked for it.
 const folder = ai.incognito ? "" : (chat ? ai.chatFolder : ai.nextFolder ?? companion?.folder) ?? "", folderName = folder.split(/[\\/]/).filter(Boolean).pop() ?? folder
 const pickFolder = () => send("chatFolder", { chat })
 const partsRef = useRef(parts), filesRef = useRef(files), pastesRef = useRef(pastes), takeRef = useRef<(list: FileList) => void>(() => {}), offRef = useRef(disabled)
 useLayoutEffect(() => { partsRef.current = parts; filesRef.current = files; pastesRef.current = pastes; offRef.current = disabled })
 useEffect(() => { // files dragged over the chat light it up, and a drop anywhere on it adds them
  const el = group.current?.closest<HTMLElement>(".chat-view") ?? group.current; if (!el) return
  setZone(el) // eslint-disable-line react-hooks/set-state-in-effect
  let depth = 0 // dragenter and dragleave come for each element inside, so the light goes once the drag has left them all
  const has = (e: DragEvent) => !!e.dataTransfer?.types.includes("Files")
  const over = (e: DragEvent) => { if (!has(e)) return; e.preventDefault(); e.dataTransfer!.dropEffect = offRef.current ? "none" : "copy"; if (!offRef.current) setDropping(true) }
  const enter = (e: DragEvent) => { if (has(e)) depth++ }
  const leave = (e: DragEvent) => { if (has(e) && --depth <= 0) { depth = 0; setDropping(false) } }
  const drop = (e: DragEvent) => { if (!has(e)) return; e.preventDefault(); depth = 0; setDropping(false); if (!offRef.current) takeRef.current(e.dataTransfer!.files) }
  el.addEventListener("dragenter", enter); el.addEventListener("dragover", over); el.addEventListener("dragleave", leave); el.addEventListener("drop", drop)
  return () => { el.removeEventListener("dragenter", enter); el.removeEventListener("dragover", over); el.removeEventListener("dragleave", leave); el.removeEventListener("drop", drop) }
 }, [])
 useEffect(() => { // Ctrl+V (Cmd+V on the Mac) with no box in focus: a copied picture lands in the box on show
  const key = (e: KeyboardEvent) => {
   if (e.key.toLowerCase() !== "v" || !(MAC ? e.metaKey : e.ctrlKey) || e.shiftKey || e.altKey || e.defaultPrevented || disabled || !box.current?.checkVisibility()) return
   if ((e.target as Element | null)?.closest?.("input, textarea, select, [contenteditable=true], [role=textbox], [role=dialog]")) return
   e.preventDefault(); send("aiPasteImage", { to: me, quiet: true })
  }
  document.addEventListener("keydown", key); return () => document.removeEventListener("keydown", key)
 })
 const pending = useRef<(() => void) | null>(null), timer = useRef(0)
 const caret = useRef<number | undefined>(undefined), restore = useRef<number | undefined>(undefined) // where the caret is, and where it goes on the next focus
 const sel = () => caret.current === undefined ? {} : { sel: [caret.current, caret.current] as [number, number] }
 const flush = () => { clearTimeout(timer.current); pending.current?.(); pending.current = null }
 const later = (run: () => void) => { pending.current = run; clearTimeout(timer.current); timer.current = window.setTimeout(flush, 500) }
 const save = (p: Part[], f: Attached[], t = pastesRef.current) => { // a moment after the last change, and right away on leaving the box or Still
  const key = draft, d = { text: textOf(p), parts: mentions(p).length ? p : undefined, files: f.length ? f : undefined, pastes: t.length ? t : undefined }
  later(() => keepDraft(key, { ...d, ...sel() }))
 }
 const setP = (t: string[]) => { pastesRef.current = t; setPastes(t); save(partsRef.current, filesRef.current, t) }
 // Only the caret moved: kept too, while the box still shows the draft (not once Send emptied it, or sent() would keep it).
 const moved = (el: HTMLElement) => {
  const c = caretIn(el), key = drafted.current, d = readDraft(key); caret.current = c
  if (!pending.current && key && d && c !== undefined && d.sel?.[1] !== c && d.text === textOf(partsRef.current))
   later(() => { const now = readDraft(key); if (now?.text === d.text) keepDraft(key, { ...now, ...sel() }) })
 }
 const unsent = useRef<Attached[]>([]), unpasted = useRef<string[]>([]) // the files and pastes of the message being sent, back in the box if Still couldn't send it
 useEffect(() => { addEventListener("beforeunload", flush); return () => { removeEventListener("beforeunload", flush); flush() } }, [draft]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { // what Still kept from a pick, drop or paste in this box
  const got = (e: Event) => { // added now, or (.kept) a draft's that are still there
   const d = (e as CustomEvent).detail; if (d.to !== me && d.to !== me + ".kept") return
   if (d.key) { acks.current.get(d.key)?.(-1); acks.current.delete(d.key); setComing(l => l.filter(x => x.key !== d.key)); if (stopped.current.has(d.key)) return }
   if (d.files?.length) { const all = [...filesRef.current, ...d.files]; setFiles(all); if (d.to === me) save(partsRef.current, all) }
   if (d.error) toast(d.error)
  }
  const going = (e: Event) => { // a picked file being copied in
   const d = (e as CustomEvent).detail; if (d.to !== me || stopped.current.has(d.key)) return
   setComing(l => l.some(x => x.key === d.key) ? l.map(x => x.key === d.key ? { ...x, done: d.done } : x) : [...l, { key: d.key, name: d.name, size: d.size, done: d.done }])
  }
  const acked = (e: Event) => { const d = (e as CustomEvent).detail; acks.current.get(d.key)?.(d.done); acks.current.delete(d.key) }
  const back = (e: Event) => {
   if ((e as CustomEvent).detail !== draft || !unsent.current.length && !unpasted.current.length) return
   const f = unsent.current, t = unpasted.current; unsent.current = []; unpasted.current = []
   setFiles(f); pastesRef.current = t; setPastes(t); save(partsRef.current, f, t)
  }
  addEventListener("still-attached", got); addEventListener("still-unsent", back); addEventListener("still-attaching", going); addEventListener("still-attach-ack", acked)
  return () => { removeEventListener("still-attached", got); removeEventListener("still-unsent", back); removeEventListener("still-attaching", going); removeEventListener("still-attach-ack", acked) }
 }, [me, draft]) // eslint-disable-line react-hooks/exhaustive-deps
 const take = (list: FileList | File[]) => {
  for (const f of [...list]) {
   if (tooBig(f)) { toast(tooBig(f)); continue }
   const key = newKey(), name = f.name || "pasted-image.png"
   setComing(l => [...l, { key, name, size: f.size, done: 0 }])
   queue.current = queue.current.then(() => upload(f, key, name))
  }
 }
 // One file at a time, a piece at a time, each acknowledged before the next; the last comes back as still-attached.
 const upload = async (f: File, key: string, name: string) => {
  try {
   for (let at = 0; at === 0 || at < f.size; at += PIECE) {
    const data = await base64(f.slice(at, at + PIECE))
    if (stopped.current.has(key)) return
    const done = await new Promise<number>(ok => { acks.current.set(key, ok); send("aiAttach", { to: me, key, name, size: f.size, offset: at, data }) })
    if (done < 0) return
    setComing(l => l.map(x => x.key === key ? { ...x, done } : x))
   }
  } catch { toast(`Couldn't add ${name}.`); stopAdding(key) }
 }
 const stopAdding = (key: string) => {
  stopped.current.add(key); acks.current.get(key)?.(-1); acks.current.delete(key)
  setComing(l => l.filter(x => x.key !== key)); send("aiAttachCancel", { key })
 }
 useLayoutEffect(() => { takeRef.current = take })
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
  if (was && draft && was !== draft && /(^|\.)chat\.new$/.test(was) && (textOf(partsRef.current).trim() || filesRef.current.length || pastesRef.current.length)) {
   keepDraft(was, null); rekey(was, draft); keepDraft(draft, { text: textOf(partsRef.current), parts: mentions(partsRef.current).length ? partsRef.current : undefined, files: filesRef.current.length ? filesRef.current : undefined, pastes: pastesRef.current.length ? pastesRef.current : undefined })
   return // the new chat got its id: what's in the box stays, now under it, with its undo steps
  }
  const kept = readDraft(draft)
  const p: Part[] = kept?.parts ? shown(kept.parts) : [kept?.text ?? ""]
  if (el) el.innerHTML = markup(p, knownRef.current)
  if (el && draft) adopt(draft, el, kept)
  setParts(read(el ?? document.createElement("div"))) // eslint-disable-line react-hooks/set-state-in-effect
  setFiles([]); pastesRef.current = kept?.pastes ?? []; setPastes(pastesRef.current)
  if (kept?.files?.length) send("aiReattach", { to: me + ".kept", ids: kept.files.map(f => f.id) })
  caret.current = restore.current = kept?.sel?.[1] // back where it was, or at the end
  if (kept && el && (autoFocus || document.activeElement === el)) { el.focus(); caretAt(el, kept.sel?.[1] ?? Infinity) }
  else if (kept?.sel && el && !document.hasFocus() && document.activeElement === document.body) caretAt(el, kept.sel[1]) // no focus event comes while the window isn't focused: the caret waits in the box
 }, [draft]) // eslint-disable-line react-hooks/exhaustive-deps
 // The caret at the end of the box (it isn't in the box yet).
 const end = () => { const el = box.current, s = getSelection(); if (!el || !s) return; el.focus(); s.selectAllChildren(el); s.collapseToEnd() }
 useEffect(() => { if (autoFocus && document.activeElement !== box.current) end() }, []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => {
  const el = box.current; if (!el) return
  const where = () => { const s = getSelection(), n = s?.anchorNode; if (n && el.contains(n)) { setBefore(n.nodeType === Node.TEXT_NODE ? n.textContent!.slice(0, s.anchorOffset) : ""); moved(el) } }
  const plain = (e: InputEvent) => { if (e.inputType.startsWith("format")) e.preventDefault() } // no bold or italics in a message
  document.addEventListener("selectionchange", where); el.addEventListener("beforeinput", plain)
  return () => { document.removeEventListener("selectionchange", where); el.removeEventListener("beforeinput", plain) }
 }, [])
 const text = textOf(parts)
 const sync = () => {
  const el = box.current; if (!el) return
  dress(el, known)
  const p = read(el), t = textOf(p)
  setParts(p); save(p, files); setPick(0); setShut(null); onTyping?.(!!t.trim())
 }
 const attached = mentions(parts).flatMap(m => m.kind === "tab" ? [m.id] : [])
 const lead = text.trim() || (files.length ? `Take a look at ${files.length === 1 ? "this file" : "these files"}.` : pastes.length ? "Take a look at what I pasted." : "")
 const message = [lead, ...pastes.map(pasted)].filter(Boolean).join("\n\n")
 // The draft stays until Still says it took the message: if it couldn't, the text comes back (drafts.tsx sent).
 const submit = () => {
  if (!message || disabled) return
  if (coming.length) { toast("Your files are still being added."); return }
  flush(); sending(draft); unsent.current = files; unpasted.current = pastes
  onSubmit(message, attached, files.map(f => f.id), draft)
  if (box.current) box.current.innerHTML = ""
  setParts([]); setBefore(""); setFiles([]); pastesRef.current = []; setPastes([]); onTyping?.(false)
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
  else if (e.clipboardData.getData("text/plain").length >= LONG_PASTE) { const t = e.clipboardData.getData("text/plain"); if (new Blob([t]).size > PASTE_FILE) take([new File([t], "Pasted text.txt", { type: "text/plain" })]); else setP([...pastes, t]) }
  else if (e.clipboardData.getData("text/plain")) document.execCommand("insertText", false, e.clipboardData.getData("text/plain"))
  else send("aiPasteImage", { to: me, quiet: true }) // a picture the box can't read here: Still reads the clipboard itself
 }
 const dragging = (e: { dataTransfer: DataTransfer }) => e.dataTransfer.types.includes("Files")
 const wide = !!zone?.classList.contains("chat-view")
 return <InputGroup ref={group} className={"composer" + (dropping && !wide ? " is-drop" : "")} style={{ "--hue": hueOf(companion) } as CSSProperties}>
  {dropping && zone && createPortal(<div className="composer-drop" aria-hidden style={{ "--hue": hueOf(companion) } as CSSProperties}><Paperclip />Drop to attach</div>, zone)}
  {items.length > 0 && <div className="skill-menu" role="listbox" aria-label={menuLabel}>{items.map((it, i) => <button type="button" key={it.key} role="option" aria-selected={i === pick % items.length} onMouseDown={e => { e.preventDefault(); it.run() }}>{it.icon}<b>{it.label}</b><span>{it.sub}</span></button>)}</div>}
  {files.length + coming.length + pastes.length > 0 && <InputGroupAddon align="block-start" className="skill-chips">
   {files.map(f => <FileChip key={f.id} file={f} onRemove={() => { const left = files.filter(x => x !== f); setFiles(left); save(parts, left) }} />)}
   {coming.map(c => { const pct = Math.floor(100 * c.done / (c.size || 1)); return <span key={c.key} className="skill-chip file-chip is-loading" title={c.name}><FileIcon path={c.name} /><span>{c.name}</span><small>{pct}%</small>
    <i className="file-progress" role="progressbar" aria-label={"Adding " + c.name} aria-valuenow={pct} style={{ width: pct + "%" }} />
    <button type="button" className="file-x" aria-label={"Stop adding " + c.name} onClick={() => stopAdding(c.key)}><X /></button></span> })}
   {pastes.map((t, i) => <PasteChip key={i} text={t} onRemove={() => setP(pastes.filter((_, j) => j !== i))} onInline={() => { setP(pastes.filter((_, j) => j !== i)); end(); document.execCommand("insertText", false, t) }} />)}
  </InputGroupAddon>}
  <div ref={box} data-history={draft} role="textbox" aria-multiline aria-label="Message" aria-placeholder={placeholder} aria-disabled={disabled || undefined} data-empty={!text.trim() || undefined}
   contentEditable={!disabled} data-slot="input-group-control" className="composer-input" spellCheck
   onInput={sync} onBlur={flush} onPointerDown={() => { restore.current = undefined }} onFocus={() => { const n = restore.current; restore.current = undefined; if (n !== undefined && box.current) caretAt(box.current, n) }} onCopy={e => copy(e, false)} onCut={e => copy(e, true)} onPaste={paste} onDragStart={e => e.preventDefault()}
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
    if (e.key === "Backspace" && pastes.length && atStart()) { e.preventDefault(); setP(pastes.slice(0, -1)); return }
    if (e.key === "Backspace" && files.length && atStart()) { e.preventDefault(); setFiles(files.slice(0, -1)); save(parts, files.slice(0, -1)); return }
    if (e.key === "Enter") { e.preventDefault(); if (e.shiftKey) document.execCommand("insertLineBreak"); else submit() } }} />
  <InputGroupAddon align="block-end">
   <DropdownMenu onOpenChange={add.measure}><DropdownMenuTrigger asChild disabled={disabled}><InputGroupButton ref={add.ref} className="composer-add" size="icon-xs" variant="ghost" aria-label="Add files, a skill or a tab"><Plus /></InputGroupButton></DropdownMenuTrigger>
    <DropdownMenuContent {...add.props} className="w-72" onCloseAutoFocus={e => e.preventDefault()}>
     <DropdownMenuItem onSelect={() => send("aiPickFiles", { to: me })}><Paperclip />Add files<span className="menu-hint">or drop them here</span></DropdownMenuItem>
     <DropdownMenuItem onSelect={() => send("aiPasteImage", { to: me })}><ClipboardPaste />Paste copied image<span className="menu-hint">or {MAC ? "⌘V" : "Ctrl+V"}</span></DropdownMenuItem>
     {!ai.incognito && <DropdownMenuItem onSelect={pickFolder}><FolderOpen />{folder ? "Change folder…" : "Work in a folder…"}</DropdownMenuItem>}
     {folder && <DropdownMenuItem onSelect={() => send("chatFolder", { chat, remove: true })}><FolderX />Remove folder from {chat ? "this chat" : "the new chat"}</DropdownMenuItem>}
     <DropdownMenuSeparator />
     <DropdownMenuLabel>Skills</DropdownMenuLabel>
     {skills.slice(0, 8).map(k => <DropdownMenuItem key={k.id} onSelect={() => pickSkill(k)}><BookOpen />{k.name}</DropdownMenuItem>)}
     {!skills.length && <p className="mode-none">No skills yet. Make one on the new tab page, under Skills.</p>}
     {pages.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>Add a tab</DropdownMenuLabel>
      {pages.map(t => <DropdownMenuItem key={t.id} onSelect={() => putTab(t)}><TabIcon tab={t} /><span className="truncate">{t.title || host(t.url)}</span></DropdownMenuItem>)}</>}
    </DropdownMenuContent></DropdownMenu>
   {folder && <Tip label={folder}><button type="button" className="folder-chip" aria-label={`Working folder: ${folderName}. Change it`} disabled={disabled} onClick={pickFolder}><FolderOpen /><span>{folderName}</span></button></Tip>}
   <span className="composer-gap" />
   <ModeMenu ai={ai} send={send} companion={companion} onCompanion={onCompanion} onOpen={o => setHeld(o ? !!ai.advanced : null)} disabled={!!onStop || disabled} />
   {(held ?? ai.advanced) && <ModelPicker ai={ai} send={send} disabled={!!onStop || disabled} />}
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
  <p>Still works through an AI app on this computer, or an API you add. Your chats go only to your AI provider.</p>
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
   <p>{current.name} needs {current.maker}'s app on this {MAC ? "Mac" : "PC"}. Run this in {SHELL}, then sign in.</p>
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
 const queued = ai.queued ?? [], upNext = queued.map(q => unpaste(q.text).rest).filter(Boolean).join(" · "), upFiles = queued.flatMap(q => q.files ?? [])
 const log = useRef<HTMLDivElement>(null)
 const [picked, setPicked] = useState<string>() // who a new chat in the sidebar is with
 const [picture, setPicture] = useState<string | null>(null) // the step of a picture open big
 const known: Known = { companions: ai.companions ?? [], tabs, plugins: ai.plugins?.key ? ai.plugins.connected : [], skills: ai.skills ?? [] }
 const fresh = !ai.messages.length
 const companion = companionOf(ai, fresh && picked ? picked : ai.chatCompanion)
 const name = companion?.name ?? "your AI"
 const busy = ai.busy
 const run = ai.runs?.find(r => r.id === ai.chatId), started = run?.started
 const now = useSettled(doing(run?.tool, run?.target), 600) // what it's doing right now, as the page pill says it
 const [typing, setTyping] = useState(false)
 const mood = useRunMood(ai, typing)
 const pinned = useRef(true), lastTop = useRef(0) // the user is at the bottom of the chat (scrolling down, as a smooth scroll there does, keeps it so)
 const anchor = useRef<{ row: Element; top: number } | undefined>(undefined) // the row the user is reading, and where it sits in the view
 // Opening a chat (the side panel keeps one view from chat to chat): where the user scrolled up to in it, or else its
 // end, where a running chat's live step is. Then the end stays in view as it grows, unless the user reads further up.
 const opened = useRef<string | undefined>(undefined)
 useLayoutEffect(() => {
  const el = log.current; if (!el) return
  if (opened.current !== (ai.chatId ?? "")) {
   // An empty chat isn't the one it had open: back to that one (a tab's side panel shows its own chat, a new tab's starts
   // empty), it opens where the user left it again, not where the empty view's scrolling left this view.
   if (!ai.messages.length) { opened.current = undefined; return }
   const back = ai.chatId ? scrolls.get(ai.chatId) : undefined
   opened.current = ai.chatId ?? ""; anchor.current = undefined
   el.scrollTop = back ?? el.scrollHeight; pinned.current = back == null; lastTop.current = el.scrollTop
  }
  else if (pinned.current || (ai.messages.at(-1)?.role === "user" && !ai.messages.at(-1)?.who)) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }) // not while the user reads further up, unless they just sent
 }, [ai.chatId, (ai.messagesFrom ?? 0) + ai.messages.length, busy, !!ai.question])
 const keepScroll = (e: { currentTarget: HTMLDivElement }) => {
  fadeTop(e); const el = e.currentTarget
  // At the end, or following it: only 8 px up from the furthest it got unpins it, so the few pixels WebKit's layout nudges
  // it back as a run starts (rows above it change) don't count as the user reading further up.
  const near = el.scrollHeight - el.scrollTop - el.clientHeight < 8
  pinned.current = near || (pinned.current && el.scrollTop >= lastTop.current - 8)
  lastTop.current = near || !pinned.current ? el.scrollTop : Math.max(lastTop.current, el.scrollTop)
  const view = el.getBoundingClientRect().top, row = [...el.firstElementChild?.children ?? []].find(r => r.getBoundingClientRect().bottom > view)
  // The same row a pixel or less from where it was keeps where it was, so the parts of a pixel left over each time the
  // view is put back (or the browser anchors it) don't add up into a drift.
  const top = row && row.getBoundingClientRect().top - view, was = anchor.current
  anchor.current = row && (was?.row === row && Math.abs(was.top - top!) <= 1 ? was : { row, top: top! })
  // Kept only where the user scrolled up to: the chat's own scrolling (to its end, smooth or not) never leaves it unpinned.
  if (ai.chatId && opened.current === ai.chatId) { if (pinned.current) scrolls.delete(ai.chatId); else scrolls.set(ai.chatId, el.scrollTop) }
 }
 // Reading further up while steps come in, the row being read stays put though rows above it change (a long chat drops
 // its oldest ones): WebKit doesn't do this by itself, and where the browser already did, there's nothing left to move.
 useLayoutEffect(() => {
  const el = log.current, a = anchor.current; if (!el || !a || pinned.current || !a.row.isConnected) return
  const moved = a.row.getBoundingClientRect().top - el.getBoundingClientRect().top - a.top
  if (Math.abs(moved) > 1) el.scrollTop += moved
 })
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
 // Each row is keyed by where its first message sits in the whole chat, so a new step updates the chat in place: no row
 // is redrawn (or fades in again, or folds up) because a long chat's window moved on by one.
 const items: (Message | { role: "steps"; steps: Message[]; who?: string | null })[] = [], keys: number[] = []
 messages.forEach((m, n) => {
  const prev = items[items.length - 1]
  if ((m.role === "tool" || m.role === "search" || m.role === "read") && prev && "steps" in prev && prev.who == m.who) prev.steps.push(m)
  else { items.push(m.role === "tool" || m.role === "search" || m.role === "read" ? { role: "steps", steps: [m], who: m.who } : m); keys.push((ai.messagesFrom ?? 0) + n) }
 })
 const latestPrompt = messages.findLast(m => m.role === "user" && !m.who && !m.answer)
 const turnAt = busy ? items.findLastIndex(m => m === latestPrompt) : items.length // while it works, every step since the latest message stays in view
 const last = items[items.length - 1], working = !!last && "steps" in last && last.steps[last.steps.length - 1].status === "working"
 const stopped = !busy && !chat?.from && !!last && "text" in last && last.role === "note" && last.text === "Stopped." // the user stopped the last reply
 const thinking = busy && !working && !(last && !("steps" in last) && last.role === "assistant")
 // A turn's time (its run's last step keeps it) shows on the turn's first block of two or more steps, wherever that last step is.
 const tookAt = new Map<number, number>()
 for (let i = 0, first = -1, took = 0; i <= items.length; i++) {
  const m = items[i]
  if (!m || (!("steps" in m) && m.role === "user")) { if (first >= 0 && took) tookAt.set(first, took); first = -1; took = 0 }
  else if ("steps" in m) { took = Math.max(took, ...m.steps.map(s => s.took ?? 0)); if (first < 0 && m.steps.length > 1) first = i }
 }
 // A turn's actions go once, under its final reply: the last answer before your next message, and none while it still works.
 const finals = new Set<number>()
 let reply = -1
 items.forEach((m, i) => { if ("steps" in m) return; if (m.role === "user") { if (reply >= 0) finals.add(reply); reply = -1 } else if (m.role === "assistant") reply = i })
 if (reply >= 0 && !busy) finals.add(reply)
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
 const openLink = (url: string) => url.startsWith("still:settings/") ? send("openPanel", { name: "settings", value: url }) : send("new", { url })

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
    if ("steps" in m) return <div key={keys[i]} className={turn(i)}>{face(i)}<Work steps={m.steps} live={busy && i > turnAt} took={tookAt.get(i)} onLink={openLink} onPicture={setPicture} /></div>
    if (m.role === "file") return <div key={keys[i]} className={turn(i)}>{face(i)}<FileCard path={m.text} send={send} onOpen={onFile} /></div>
    if (m.role === "user" && m.who) { const asker = companionOf(ai, m.who); return <div key={keys[i]} className="ai-msg is-user is-teammate" style={{ "--hue": hueOf(asker) } as CSSProperties}>
     <span className="ai-asker"><Face companion={asker} size={20} />{asker?.name ?? "A teammate"} asked</span><MessageText text={m.text} known={known} /></div> }
    if (m.role === "user") return <MyMessage key={(ai.chatId ?? "new") + "." + keys[i]} m={m} known={known} send={send} latest={m === latestPrompt} draft={(ai.incognito ? "private." : "") + "edit." + (ai.chatId ?? "new")} />
    if (m.role === "ask" || m.role === "tell") return <div key={keys[i]} className={turn(i)}>{face(i)}<DelegationRow m={m} ai={ai} send={send} mode={mode} onLink={openLink} /></div>
    if (m.role === "note" && m.text === "Stopped.") return <div key={keys[i]} className="ai-stopped" role="note"><Pause aria-hidden />You stopped it here
     {stopped && i === items.length - 1 && <button type="button" onClick={() => send("aiContinue", { id: ai.chatId })}><Play aria-hidden />Continue</button>}</div>
    if (m.role !== "assistant") return <div key={keys[i]} className="ai-msg is-note">{m.text}</div>
    const { body, choice, next } = choicesOf(m.text)
    const after = items[i + 1], answer = after && !("steps" in after) && after.role === "user" ? after.text : undefined, last = i === items.length - 1 && !busy
    return <div key={keys[i]} className={turn(i)}>{face(i)}
     <div className="ai-msg is-assistant"><Markdown text={body} onLink={openLink} onCopy={text => { send("copyText", { text }); toast("Copied") }} /></div>
     {choice && <ChoiceCard choice={choice} answer={answer} live={last} onPick={text => submit(text)} />}
     {!!next?.length && <div className="ai-next">{next.map(s => <button key={s} className="ai-next-step" disabled={!last} onClick={() => submit(s)}><ArrowDownRight /><span>{s}</span></button>)}</div>}
     {finals.has(i) && <ReplyActions body={body} title={chatOf(ai, ai.chatId)?.title || name} again={last && latestPrompt && latestPrompt.text.length <= 100000 ? latestPrompt : undefined} used={m} send={send} />}
    </div>
   })}
   {busy && !ai.question && <div className={turn(items.length)}>{face(items.length)}<div className="ai-live">
    {thinking && <div className="ai-work-row is-live"><StepIcon step={now} /><span className="ai-step-text">{now}</span></div>}
    <p className="ai-timer"><span className="still-mark is-small is-live" aria-hidden><i /><i /></span>Working for {clock(tick)}</p></div></div>}
  </div></div>}
  {!busy && ai.chatId && ai.task?.state === "interrupted" && <Alert className="task-bar"><AlertDescription>{ai.task.unsure
    ? `Stopped: Still closed while ${name} was mid-task, and one step may not have finished. ${name} checks it first and asks you again.`
    : `Stopped: Still closed while ${name} was mid-task.`}</AlertDescription><Button size="sm" onClick={() => send("aiResume", { id: ai.chatId })}><Play aria-hidden />Continue</Button></Alert>}
  {!busy && ai.chatId && ai.task?.state === "waiting" && ai.task.reason === "signin" && <Alert className="task-bar"><AlertDescription>{name} is waiting: sign in to carry on.</AlertDescription>
   <Button size="sm" variant="outline" onClick={() => send("aiResume", { id: ai.chatId })}>Resume</Button><Button size="sm" onClick={() => send("aiLogin")}>Sign in</Button></Alert>}
  {ai.error && <Alert variant="destructive" className="ai-error"><AlertDescription>{ai.error}</AlertDescription><Button size="sm" variant="outline" className="ai-error-copy" onClick={() => { send("copyText", { text: ai.error }); toast("Details copied") }}><Copy />Copy details</Button>
   {!busy && ai.chatId && ai.task?.state === "failed" && !chat?.from && <Button size="sm" onClick={() => send("aiContinue", { id: ai.chatId })}><Play aria-hidden />Continue</Button>}</Alert>}
  {!setup && <div className="ai-compose"><div className="chat-column">
   {mode === "panel" && pages.length > 0 && <button className="chat-chip is-pages" onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 />{name} has {pages.length === 1 ? "a page" : pages.length + " pages"} open<b>Show</b></button>}
   {mode === "panel" && activeTab?.url && !activeTab.inChat && <Tip label={activeTab.url}><span className="chat-chip"><Globe />{activeTab.title || host(activeTab.url)}</span></Tip>}
   {picture && ai.chatId && <StepPictures chat={ai.chatId} step={picture} all={picturesOf(ai.messages)} onStep={setPicture} />}
   {ai.question && <QuestionCard q={ai.question} companion={companion} send={send} draft={"answer." + (ai.chatId ?? "new")} />}
   {!!ai.approvals?.length && <Approvals list={ai.approvals} companion={companion} companions={ai.companions} send={send} incognito={ai.incognito} />}
   {queued.length > 0 && <div className="ai-queued"><span className="ai-queued-label">Up next</span>
    <div className="ai-queued-what" title={queued.map(q => q.text).join("\n\n")}>{upNext && <p>{upNext}</p>}{upFiles.map((f, i) => <span key={i} className="ai-queued-file"><FileIcon path={f.name} /><span>{f.name}</span></span>)}</div>
    <Button variant="outline" size="sm" onClick={() => send("aiNow")}>Send now</Button><Tip label="Don't send"><button className="ai-queued-x" aria-label="Don't send" onClick={() => send("aiUnqueue")}><X /></button></Tip></div>}
   {!chat?.from && <><Composer chat={chat?.id} draft={"chat." + (ai.chatId ?? "new")} ai={ai} send={send} onSubmit={submit} onTyping={setTyping} onStop={busy ? () => send("aiStop") : undefined} companion={companion} onCompanion={fresh && mode === "panel" ? setPicked : undefined} tabs={tabs}
    placeholder={busy ? (queued.length ? "Add to what's up next…" : "Add a next step…") : stopped ? "Type a correction to pick up from here…" : items.length ? `Reply to ${name}…` : mode === "tab" ? `Work with ${name}…` : "Ask anything, or tell me what to do…"} />
   <div className="chat-under">
    {ai.incognito ? <p className="chat-incognito"><LockKeyhole />Incognito chat: Still keeps nothing from it and deletes it when you close this window. {provider?.name ?? "Your model"} and the sites {name} visits still get what's sent to them, {provider?.api ? "and Still writes none of it to disk." : provider?.forgets ? `and ${provider.app || provider.name} is told not to save it on this computer.` : `and ${provider?.app || provider?.name || "its app"} may keep its own record.`} Connected apps are off in incognito windows. Memory: read only.</p>
    : companion && <Tip label={forget ? `${name} won't remember anything from this chat` : `${name} remembers useful things from this chat`}><label className="chat-memory"><Switch size="sm" aria-label="Don't remember this chat" checked={forget} onCheckedChange={on => chat ? send("chatNoMemory", { id: chat.id, on }) : setOffRecord(on)} />Don't remember this chat</label></Tip>}
    {!ai.incognito && chat && <ProfileChip chat={chat} busy={busy} send={send} />}
    {mode === "panel" && provider && (provider.maker || ai.usage) && <p className="ai-usage"><Gauge />{[provider.billing || (provider.maker && !provider.api && "Your " + provider.name + " plan"), ai.usage].filter(Boolean).join(" · ")}</p>}
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

/// The side panel's Chat history: recent chats to search and pick, as on the Chat History page. Arrows and Enter pick,
/// Esc or a click outside closes. A pick opens the chat in this tab's side panel.
function ChatPicker({ ai, send, onClose }: { ai: AiState; send: Send; onClose: (back?: boolean) => void }) {
 const [find, setFind] = useState("")
 const box = useRef<HTMLDivElement>(null)
 useEffect(() => {
  const out = (e: PointerEvent) => { const t = e.target as Node; if (!box.current?.contains(t) && !box.current?.parentElement?.querySelector("[aria-expanded=true]")?.contains(t)) onClose() }
  const away = () => onClose() // a click in the page, which is another view: the interface loses focus
  addEventListener("pointerdown", out, true); addEventListener("blur", away)
  return () => { removeEventListener("pointerdown", out, true); removeEventListener("blur", away) }
 }, [onClose])
 const groups = byDay(ai.chats.filter(c => !c.from && !c.archived && c.title.toLowerCase().includes(find.trim().toLowerCase())))
 return <div ref={box} className="chat-picker" role="dialog" aria-label="Chat history" onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onClose(true) } }}>
  <Command shouldFilter={false} loop>
   <CommandInput autoFocus aria-label="Search chats" placeholder="Search chats..." value={find} onValueChange={setFind} />
   <CommandList>
    <CommandEmpty>{find ? "No chats match." : "Your chats show up here."}</CommandEmpty>
    {groups.map(([day, list]) => <CommandGroup key={day} heading={day}>
     {list.map(c => <CommandItem key={c.id} value={c.id} data-chat={c.id} data-checked={c.id === ai.chatId || undefined} onSelect={() => { send("aiOpenChat", { id: c.id }); onClose(true) }}>
      <Face companion={companionOf(ai, c.companion)} size={24} mood={isRunning(ai, c.id) ? "working" : "idle"} /><b>{c.title}</b>
      {needsYou(ai, c.id) ? <span className="history-needs">Needs input</span> : isRunning(ai, c.id) ? <Spinner aria-label="Working" /> : c.unread ? <i className="is-unread" aria-label="Unread" /> : <small>{ago(c.updated)}</small>}
     </CommandItem>)}
    </CommandGroup>)}
   </CommandList>
  </Command>
 </div>
}

// The chat panel beside an ordinary page (the Chat button). Its gear opens Settings, Models.
export function AiPanel({ ai, send, tabs, activeTab, onFile }: { ai: AiState; send: Send; tabs: TabRef[]; activeTab?: TabRef; onFile: (path: string) => void }) {
 const companion = companionOf(ai, ai.chatCompanion)
 const mood = useRunMood(ai)
 const [panel, setPanel] = useState<HTMLElement | null>(null)
 const [history, setHistory] = useState(false)
 const head = useRef<HTMLDivElement>(null)
 const closeHistory = (back?: boolean) => { setHistory(false); if (back) head.current?.querySelector<HTMLElement>("[aria-haspopup=dialog]")?.focus() }
 return <aside className="ai-sidebar" aria-label="Chat" ref={setPanel}><CollisionBoundary.Provider value={panel}>
  <div className="ai-head" ref={head}>
   <button type="button" className="profile-open ai-head-buddy" title={companion?.name} aria-label={`${companion?.name ?? "Companion"}'s profile`} onClick={() => showProfile(companion)}><Face companion={companion} size={22} mood={mood} /></button>
   <div className="ai-title"><strong>{chatOf(ai, ai.chatId)?.title || companion?.name || "Chat"}</strong></div>
   <IconButton label="Open as a tab" disabled={!ai.chatId} onClick={() => send("chatOpen", { id: ai.chatId })}><Maximize2 /></IconButton>
   <IconButton label="Chat history" expanded={history} onClick={() => setHistory(!history)}><History /></IconButton>
   <IconButton label="New chat" disabled={!ai.chatId} onClick={() => send("aiNew")}><MessageSquarePlus /></IconButton>
   <IconButton label="Model settings" onClick={() => openModelSettings(send)}><Settings2 /></IconButton>
   <IconButton label="Close chat" onClick={() => send("aiToggle")}><X /></IconButton>
   {history && <ChatPicker ai={ai} send={send} onClose={closeHistory} />}
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
    {r.asks?.map(a => <div key={a.id} className="tasks-ask"><p>{a.what} <small>on {a.site}{a.why ? " · " + a.why : ""}</small></p>
     {a.action === "sensitive" || a.action === "plugin"
      ? <button onClick={() => send("chatOpen", { id: r.id })}>Open to decide</button>
      : <><button onClick={() => send("permAnswer", { run: r.id, id: a.id, answer: "once" })}>Allow</button><button onClick={() => send("permAnswer", { run: r.id, id: a.id, answer: "deny" })}>Not now</button></>}</div>)}
   </div> })}
   {apps.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>Other AI apps' tabs</DropdownMenuLabel>
    {apps.map(t => <div key={t.id} className="tasks-page is-app">{t.favicon ? <img src={t.favicon} alt="" /> : <Globe />}<span title={t.url}>{t.agent ? t.agent + ": " : ""}{t.title || host(t.url)}</span><button onClick={() => send("tabMine", { id: t.id })}>Move to my tabs</button></div>)}</>}
   {unread.length > 0 && <><DropdownMenuSeparator /><DropdownMenuLabel>New replies</DropdownMenuLabel>
    {unread.map(c => <DropdownMenuItem key={c.id} onSelect={() => send("chatOpen", { id: c.id })}><Face companion={companionOf(ai, c.companion)} size={22} /><span className="tasks-title">{c.title}</span><i className="is-unread" aria-hidden /></DropdownMenuItem>)}</>}
  </DropdownMenuContent>
 </DropdownMenu>
}
