import { useEffect, useRef, useState, type ReactNode } from "react"
import { ArrowLeft, ArrowUp, Bot, Check, ChevronRight, History, MessageSquarePlus, Settings2, Square, Terminal, Trash2, Wrench, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupText, InputGroupTextarea } from "@/components/ui/input-group"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Markdown } from "./Markdown"

type Harness = { id: string; name: string; app: string; installed: boolean; install: string; login: string }
export type AiState = {
 open: boolean; harness: string; busy: boolean; error: string; profile: string; harnesses: Harness[]
 chatId?: string; chatHarness?: string; messages: { role: string; text: string }[]; chats: { id: string; title: string; harness: string; updated: string }[]
}
type Send = (op: string, payload?: Record<string, unknown>) => void

const SUGGESTIONS = ["Summarize this page", "What are the key points here?", "Find reviews of this elsewhere"]
const ago = (iso: string) => {
 const s = (Date.now() - new Date(iso).getTime()) / 1000
 return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : new Date(iso).toLocaleDateString()
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
 return <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={label} disabled={disabled} onClick={onClick}>{children}</Button></TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>
}

// Chat with the user's own Claude Code, Codex or Grok Build. It reads and drives this profile's tabs through Still's MCP server.
export function AiSidebar({ ai, send }: { ai: AiState; send: Send }) {
 const [view, setView] = useState<"chat" | "history" | "settings">("chat")
 const [text, setText] = useState("")
 const log = useRef<HTMLDivElement>(null)
 const current = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 const openLink = (url: string) => send("new", { url })
 useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }) }, [ai.messages.length, ai.busy, view])
 const submit = (value = text) => { if (value.trim() && !ai.busy) { send("aiSend", { text: value }); setText("") } }
 const setup = !ai.harness && !ai.chatId

 // Consecutive tool steps collapse into one "Used the browser" group.
 const items: ({ role: string; text: string } | { role: "steps"; steps: string[] })[] = []
 for (const m of ai.messages) {
  const prev = items[items.length - 1]
  if (m.role === "tool") { if (prev && "steps" in prev) prev.steps.push(m.text); else items.push({ role: "steps", steps: [m.text] }) }
  else items.push(m)
 }

 const header = <div className="ai-head">
  {view !== "chat" ? <IconButton label="Back" onClick={() => setView("chat")}><ArrowLeft /></IconButton> : <Bot className="ai-head-icon" />}
  <div className="ai-title">
   <strong>{view === "history" ? "Conversations" : view === "settings" ? "AI settings" : current?.name ?? "AI"}</strong>
   {view === "chat" && <Badge variant="secondary">{ai.profile}</Badge>}
  </div>
  {view === "chat" && !setup && <>
   <IconButton label="Conversations" onClick={() => setView("history")}><History /></IconButton>
   <IconButton label="New chat" disabled={ai.busy || !ai.chatId} onClick={() => send("aiNew")}><MessageSquarePlus /></IconButton>
  </>}
  {view === "chat" && <IconButton label="AI settings" onClick={() => setView("settings")}><Settings2 /></IconButton>}
  <IconButton label="Close AI sidebar" onClick={() => send("aiToggle")}><X /></IconButton>
 </div>

 let body: ReactNode
 if (view === "settings") body = <div className="ai-pane">
  <section><h4>AI</h4><p>The sidebar runs this app on your PC, signed in to your own account. Still never sees your login.</p>
   <Select value={ai.harness || "none"} onValueChange={v => send("aiHarness", { harness: v === "none" ? "" : v })}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
    <SelectContent><SelectItem value="none">Not set up</SelectItem>{ai.harnesses.map(h => <SelectItem key={h.id} value={h.id}>{h.name} · {h.app}{h.installed ? "" : " (not installed)"}</SelectItem>)}</SelectContent></Select></section>
  <Separator />
  <section><h4>Profile</h4><p>The sidebar only uses your <strong>{ai.profile}</strong> profile and its tabs. It never sees private tabs, saved passwords or cookies.</p></section>
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
 else if (setup) body = <div className="ai-pane">
  <Empty className="ai-intro"><EmptyHeader><EmptyMedia variant="icon"><Bot /></EmptyMedia><EmptyTitle>Set up the AI sidebar</EmptyTitle>
   <EmptyDescription>Pick the AI you use. It runs from its own app on this PC, signed in to your account, and can read and use your tabs in this profile.</EmptyDescription></EmptyHeader>
   <EmptyContent>
    <div className="ai-harnesses">{ai.harnesses.map(h => <button key={h.id} className="ai-harness" onClick={() => send("aiHarness", { harness: h.id })}>
     <span className="ai-harness-name"><strong>{h.name}</strong><small>{h.app}</small></span>
     {h.installed ? <Badge variant="outline"><Check />Installed</Badge> : <Badge variant="secondary">Not installed</Badge>}
     <ChevronRight className="ai-harness-go" />
    </button>)}</div>
    <p className="ai-fine">You can change this later in settings.</p>
   </EmptyContent></Empty>
 </div>
 else if (current && !current.installed) body = <div className="ai-pane">
  <Empty><EmptyHeader><EmptyMedia variant="icon"><Terminal /></EmptyMedia><EmptyTitle>Install {current.app}</EmptyTitle>
   <EmptyDescription>{current.name} runs from its own app. Install it, then sign in once in a terminal.</EmptyDescription></EmptyHeader>
   <EmptyContent className="ai-steps">
    <ol><li><span>Install</span><code>{current.install}</code></li><li><span>Sign in</span><code>{current.login}</code></li></ol>
    <div className="ai-row"><Button size="sm" onClick={() => send("aiHarness", { harness: ai.harness })}>Check again</Button><Button size="sm" variant="ghost" onClick={() => setView("settings")}>Use another AI</Button></div>
   </EmptyContent></Empty>
 </div>
 else body = <div className="ai-log" ref={log}>
  {!items.length && <Empty className="ai-welcome"><EmptyHeader><EmptyMedia variant="icon"><Bot /></EmptyMedia><EmptyTitle>Ask {current?.name}</EmptyTitle>
   <EmptyDescription>Ask about this page, or tell {current?.name} what to do in your tabs. It never sees private tabs, passwords or cookies.</EmptyDescription></EmptyHeader>
   <EmptyContent className="ai-suggestions">{SUGGESTIONS.map(s => <Button key={s} variant="outline" size="sm" onClick={() => submit(s)}>{s}</Button>)}</EmptyContent></Empty>}
  {items.map((m, i) => "steps" in m
   ? <details key={i} className="ai-steps-group" open={ai.busy && i === items.length - 1}><summary><Wrench />Used the browser · {m.steps.length} step{m.steps.length === 1 ? "" : "s"}</summary><ul>{m.steps.map((s, j) => <li key={j}>{s}</li>)}</ul></details>
   : m.role === "user" ? <div key={i} className="ai-msg is-user">{m.text}</div>
   : m.role === "assistant" ? <div key={i} className="ai-msg is-assistant"><Markdown text={m.text} onLink={openLink} /></div>
   : <div key={i} className="ai-msg is-note">{m.text}</div>)}
  {ai.busy && <div className="ai-msg is-note"><Spinner />{current?.name} is working…</div>}
 </div>

 const canChat = view === "chat" && !setup && !!current?.installed
 return <aside className="ai-sidebar" aria-label="AI sidebar">
  {header}
  {body}
  {ai.error && <Alert variant="destructive" className="ai-error"><AlertDescription>{ai.error}</AlertDescription></Alert>}
  {canChat && <div className="ai-compose"><InputGroup>
   <InputGroupTextarea aria-label="Message" placeholder={`Ask ${current.name} anything…`} rows={2} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }} />
   <InputGroupAddon align="block-end">
    <InputGroupText>{current.app}</InputGroupText>
    {ai.busy ? <InputGroupButton className="ml-auto" size="icon-xs" variant="default" aria-label="Stop" onClick={() => send("aiStop")}><Square /></InputGroupButton>
     : <InputGroupButton className="ml-auto rounded-full" size="icon-xs" variant="default" aria-label="Send" disabled={!text.trim()} onClick={() => submit()}><ArrowUp /></InputGroupButton>}
   </InputGroupAddon>
  </InputGroup></div>}
 </aside>
}
