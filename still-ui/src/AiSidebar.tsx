import { useEffect, useRef, useState, type ReactNode } from "react"
import { ArrowLeft, ArrowUp, Check, ExternalLink, Gauge, History, LockKeyhole, MessageSquarePlus, Settings2, ShieldCheck, Square, Trash2, Wrench, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Buddy } from "./Buddy"
import { Markdown } from "./Markdown"

type Harness = { id: string; name: string; app: string; maker: string; installed: boolean; status: string; installer: string; site: string }
export type AiState = {
 open: boolean; harness: string; busy: boolean; error: string; profile: string; harnesses: Harness[]
 setup: { line: string; url: string; code: string }; pending: boolean
 models?: { id: string; name: string; efforts: string[] }[]; model: string; effort: string; usage: string
 chatId?: string; chatHarness?: string; messages: { role: string; text: string }[]; chats: { id: string; title: string; harness: string; updated: string }[]
}
type Send = (op: string, payload?: Record<string, unknown>) => void

const IDEAS = [
 ["📝", "Sum up this page", "Summarize this page in a few short bullet points."],
 ["🏷️", "Find it cheaper", "Find what's on this page cheaper somewhere else, and show me where."],
 ["🧳", "Plan a trip", "Help me plan a weekend trip. Ask me where I'm starting from and what I like first."],
 ["💡", "Explain it simply", "Explain this page simply, like I'm new to the topic."],
]
const WORKING = ["On it", "Looking around", "Reading carefully", "Connecting the dots", "Almost there"]
const COLORS: Record<string, string> = { claude: "#d97757", codex: "#10a37f", grok: "#52525b" }
const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url } }
const settingUp = (s?: string) => s === "installing" || s === "signingIn"
// "" = not checked yet, which never blocks a chat
const statusOf = (h?: Harness) => !h ? "" : h.status || (h.installed ? "" : "missing")
const ago = (iso: string) => {
 const s = (Date.now() - new Date(iso).getTime()) / 1000
 return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : new Date(iso).toLocaleDateString()
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
 return <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={label} disabled={disabled} onClick={onClick}>{children}</Button></TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>
}

function StatusChip({ h }: { h: Harness }) {
 const s = statusOf(h)
 if (settingUp(s)) return <span className="ai-chip"><Spinner />{s === "installing" ? "Installing" : "Signing in"}</span>
 if (s === "ready") return <span className="ai-chip is-ready"><i />Ready</span>
 if (s === "signedOut") return <span className="ai-chip is-signin"><i />Sign in</span>
 if (s === "missing") return <span className="ai-chip">Get it</span>
 return null
}

// The AIs Still works with and whether each is ready. Picking one signs it in, or offers to install it.
export function AiPicker({ ai, onPick }: { ai: AiState; onPick: (id: string) => void }) {
 return <div className="ai-picker">{ai.harnesses.map(h => <button key={h.id} className="ai-pick-card" data-chosen={ai.harness === h.id || undefined} onClick={() => onPick(h.id)}>
  <span className="ai-avatar" style={{ background: COLORS[h.id] }}>{h.name[0]}</span>
  <span className="ai-pick-name"><strong>{h.name}</strong><small>by {h.maker}</small></span>
  <StatusChip h={h} />
  {ai.harness === h.id && <Check className="ai-pick-check" />}
 </button>)}</div>
}

// Chat with the user's own Claude Code, Codex or Grok Build. It reads and drives this profile's tabs through Still's MCP server.
export function AiSidebar({ ai, send }: { ai: AiState; send: Send }) {
 const [view, setView] = useState<"chat" | "history" | "settings">("chat")
 const [text, setText] = useState("")
 const [cheer, setCheer] = useState(false)
 const [tick, setTick] = useState(0)
 const log = useRef<HTMLDivElement>(null)
 const current = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const status = statusOf(current)
 const openLink = (url: string) => send("new", { url })
 useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }) }, [ai.messages.length, ai.busy, view])
 useEffect(() => { if (!ai.busy) return; const t = setInterval(() => setTick(n => n + 1), 2600); return () => clearInterval(t) }, [ai.busy])
 // Just finished installing or signing in: a little celebration.
 const wasSettingUp = useRef(false)
 useEffect(() => {
  if (settingUp(status)) { wasSettingUp.current = true; return }
  if (!status) return
  const done = wasSettingUp.current && status === "ready"; wasSettingUp.current = false
  if (done) { setCheer(true); const t = setTimeout(() => setCheer(false), 6000); return () => clearTimeout(t) }
 }, [status])
 const submit = (value = text) => { if (value.trim() && !ai.busy) { send("aiSend", { text: value }); setText(""); setCheer(false) } }
 const setup = !ai.harness && !ai.chatId
 const pending = ai.pending && <p className="ai-fine">Your question runs as soon as {current?.name ?? "your AI"} is ready.</p>

 // Consecutive tool steps collapse into one "Used the browser" group.
 const items: ({ role: string; text: string } | { role: "steps"; steps: string[] })[] = []
 for (const m of ai.messages) {
  const prev = items[items.length - 1]
  if (m.role === "tool") { if (prev && "steps" in prev) prev.steps.push(m.text); else items.push({ role: "steps", steps: [m.text] }) }
  else items.push(m)
 }
 const last = ai.messages[ai.messages.length - 1]

 const header = <div className="ai-head">
  {view !== "chat" ? <IconButton label="Back" onClick={() => setView("chat")}><ArrowLeft /></IconButton> : <Buddy size={20} mood={ai.busy ? "think" : "idle"} className="ai-head-buddy" />}
  <div className="ai-title">
   <strong>{view === "history" ? "Conversations" : view === "settings" ? "Settings" : setup ? "Ask AI" : current?.name ?? "AI"}</strong>
  </div>
  {view === "chat" && !setup && <>
   <IconButton label="Conversations" onClick={() => setView("history")}><History /></IconButton>
   <IconButton label="New chat" disabled={ai.busy || !ai.chatId} onClick={() => send("aiNew")}><MessageSquarePlus /></IconButton>
  </>}
  {view === "chat" && <IconButton label="AI settings" onClick={() => setView("settings")}><Settings2 /></IconButton>}
  <IconButton label="Close Ask AI" onClick={() => send("aiToggle")}><X /></IconButton>
 </div>

 let body: ReactNode
 if (view === "settings") body = <div className="ai-pane">
  <section><h4>Your AI</h4><p>Ask AI runs it on this PC, signed in to your own account.</p>
   <AiPicker ai={ai} onPick={id => { send("aiHarness", { harness: id }); setView("chat") }} /></section>
  <Separator />
  <section><h4>What it can see</h4><p>Only your <strong>{ai.profile}</strong> profile and its tabs. Never private tabs, saved passwords or cookies.</p></section>
  <Separator />
  <section><h4>Conversations</h4><p>{ai.chats.length ? `${ai.chats.length} saved on this PC.` : "None saved yet."}</p>
   <Button variant="outline" size="sm" disabled={!ai.chats.length || ai.busy} onClick={() => send("aiDeleteAll")}><Trash2 />Delete all conversations</Button></section>
 </div>
 else if (view === "history") body = <div className="ai-pane ai-history">
  {!ai.chats.length ? <Empty><EmptyHeader><EmptyMedia variant="icon"><History /></EmptyMedia><EmptyTitle>No conversations yet</EmptyTitle><EmptyDescription>Your chats are saved here.</EmptyDescription></EmptyHeader></Empty>
   : ai.chats.map(c => <div key={c.id} className="ai-chat-row" data-active={c.id === ai.chatId || undefined}>
    <button className="ai-chat-open" disabled={ai.busy} onClick={() => { send("aiOpenChat", { id: c.id }); setView("chat") }}>
     <span>{c.title || "Untitled"}</span><small>{ai.harnesses.find(h => h.id === c.harness)?.name ?? c.harness} · {ago(c.updated)}</small>
    </button>
    <IconButton label="Delete conversation" disabled={ai.busy && c.id === ai.chatId} onClick={() => send("aiDeleteChat", { id: c.id })}><Trash2 /></IconButton>
   </div>)}
 </div>
 else if (setup) body = <div className="ai-pane ai-center">
  <Buddy size={64} />
  <h3>Pick your AI</h3>
  <p>Still works with the AI you already use. It runs on this PC with your own account, so there's nothing new to pay for.</p>
  <AiPicker ai={ai} onPick={id => send("aiHarness", { harness: id })} />
  {pending}
 </div>
 else if (current && (status === "missing" || status === "installing")) body = <div className="ai-pane ai-center">
  <Buddy size={64} mood={status === "installing" ? "think" : "idle"} />
  {status === "installing" ? <>
   <h3>Installing {current.app}…</h3>
   <p>This usually takes about a minute.</p>
   {ai.setup.line && <code className="ai-setup-line" title={ai.setup.line}>{ai.setup.line}</code>}
   <Button variant="ghost" size="sm" onClick={() => send("aiSetupCancel")}>Cancel</Button>
  </> : <>
   <h3>Let's get {current.name}</h3>
   <p>{current.name} needs the {current.app} app from {current.maker}. Still can install it for you, then you sign in with your {current.maker} account.</p>
   <Button className="ai-go" onClick={() => send("aiInstall")}>Install {current.app}</Button>
   <div className="ai-trust"><ShieldCheck /><span>Uses {current.maker}'s official installer from <b title={current.installer}>{host(current.installer)}</b>. It installs just for you and needs no admin rights.</span></div>
   <div className="ai-row"><Button variant="link" size="sm" onClick={() => send("aiCheck")}>I already installed it</Button><Button variant="link" size="sm" onClick={() => setView("settings")}>Pick another AI</Button></div>
  </>}
  {pending}
 </div>
 else if (current && (status === "signedOut" || status === "signingIn")) body = <div className="ai-pane ai-center">
  <Buddy size={64} mood={status === "signingIn" ? "think" : "idle"} />
  {status === "signingIn" ? <>
   <h3>{ai.setup.url ? "Approve it in the new tab" : `Opening ${current.maker}'s sign-in…`}</h3>
   {ai.setup.url && <p>Sign in on {current.maker}'s page and approve. This panel moves on by itself.</p>}
   {ai.setup.code && <div className="ai-code"><small>The page should show this code</small><strong>{ai.setup.code}</strong></div>}
   {ai.setup.url && <div className="ai-trust"><LockKeyhole /><span>You're signing in on <b>{host(ai.setup.url)}</b>, {current.maker}'s own site. Still never sees your password.</span></div>}
   <div className="ai-row">
    {ai.setup.url && <Button variant="link" size="sm" onClick={() => openLink(ai.setup.url)}><ExternalLink />Open the page again</Button>}
    <Button variant="link" size="sm" onClick={() => send("aiSetupCancel")}>Cancel</Button>
   </div>
  </> : <>
   <h3>Sign in to {current.name}</h3>
   <p>{current.name} uses your own {current.maker} account. Sign in once and you're set.</p>
   <Button className="ai-go" onClick={() => send("aiLogin")}>Sign in with {current.maker}</Button>
   <div className="ai-trust"><LockKeyhole /><span>You sign in on {current.maker}'s own website, in a tab here. Still never sees your password.</span></div>
   <Button variant="link" size="sm" onClick={() => setView("settings")}>Pick another AI</Button>
  </>}
  {pending}
 </div>
 else body = <div className="ai-log" ref={log}>
  {!items.length && <div className="ai-hello">
   <Buddy size={64} mood={cheer ? "happy" : "idle"} />
   <h3>{cheer ? "You're all set!" : `Hi! I'm ${current?.name}.`}</h3>
   <p>{cheer ? "What should we do first?" : "Tell me what you need. I can read this page, search, compare and click around in my own tabs."}</p>
   <div className="ai-ideas">{IDEAS.map(([icon, label, prompt]) => <button key={label} className="ai-idea" onClick={() => submit(prompt)}><span>{icon}</span>{label}</button>)}</div>
   <p className="ai-fine"><LockKeyhole />Never sees private tabs, passwords or cookies.</p>
  </div>}
  {items.map((m, i) => "steps" in m
   ? <details key={i} className="ai-steps-group"><summary><Wrench />Used the browser · {m.steps.length} step{m.steps.length === 1 ? "" : "s"}</summary><ul>{m.steps.map((s, j) => <li key={j}>{s}</li>)}</ul></details>
   : m.role === "user" ? <div key={i} className="ai-msg is-user">{m.text}</div>
   : m.role === "assistant" ? <div key={i} className="ai-msg is-assistant"><Markdown text={m.text} onLink={openLink} /></div>
   : <div key={i} className="ai-msg is-note">{m.text}</div>)}
  {ai.busy && <div className="ai-working"><Buddy size={26} mood="think" /><span><strong className="ai-shimmer">{WORKING[tick % WORKING.length]}…</strong>{last?.role === "tool" && <small>{last.text}</small>}</span></div>}
 </div>

 const canChat = view === "chat" && !setup && !!current?.installed && !["missing", "installing", "signedOut", "signingIn"].includes(status)
 const model = ai.models?.find(m => m.id === ai.model)
 return <aside className="ai-sidebar" aria-label="Ask AI">
  {header}
  {body}
  {ai.error && <Alert variant="destructive" className="ai-error"><AlertDescription>{ai.error}</AlertDescription></Alert>}
  {canChat && <div className="ai-compose"><InputGroup>
   <InputGroupTextarea aria-label="Message" placeholder={`Ask ${current.name} to do anything…`} rows={2} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }} />
   <InputGroupAddon align="block-end">
    {ai.models && <>
     <Select value={ai.model || "default"} onValueChange={v => send("aiModel", { model: v === "default" ? "" : v, effort: ai.effort })}>
      <SelectTrigger size="sm" className="ai-pick" aria-label="Model"><SelectValue /></SelectTrigger>
      <SelectContent>{ai.models.map(m => <SelectItem key={m.id || "default"} value={m.id || "default"}>{m.name}</SelectItem>)}</SelectContent></Select>
     {!!model?.efforts.length && <Select value={ai.effort || "default"} onValueChange={v => send("aiModel", { model: ai.model, effort: v === "default" ? "" : v })}>
      <SelectTrigger size="sm" className="ai-pick" aria-label="Effort"><SelectValue /></SelectTrigger>
      <SelectContent><SelectItem value="default">Default effort</SelectItem>{model.efforts.map(e => <SelectItem key={e} value={e}>{e === "xhigh" ? "Extra high" : e[0].toUpperCase() + e.slice(1)} effort</SelectItem>)}</SelectContent></Select>}
    </>}
    {ai.busy ? <InputGroupButton className="ml-auto ai-send" size="icon-xs" variant="default" aria-label="Stop" onClick={() => send("aiStop")}><Square /></InputGroupButton>
     : <InputGroupButton className="ml-auto rounded-full ai-send" size="icon-xs" variant="default" aria-label="Send" disabled={!text.trim()} onClick={() => submit()}><ArrowUp /></InputGroupButton>}
   </InputGroupAddon>
  </InputGroup>
  {ai.usage && <p className="ai-usage"><Gauge />{ai.usage}</p>}</div>}
 </aside>
}
