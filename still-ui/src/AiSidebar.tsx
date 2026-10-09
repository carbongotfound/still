import { useEffect, useRef, useState } from "react"
import { ArrowUp, Loader2, RotateCcw, Square, Terminal, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type AiState = { open: boolean; provider: string; busy: boolean; error: string; providers: { id: string; name: string; installed: boolean; install: string }[]; messages: { role: string; text: string }[] }
type Send = (op: string, payload?: Record<string, unknown>) => void

// Chat with the user's own Claude Code, Codex or Grok Build CLI; it reads and drives the open tabs through Still's MCP server.
export function AiSidebar({ ai, send }: { ai: AiState; send: Send }) {
 const [text, setText] = useState("")
 const log = useRef<HTMLDivElement>(null)
 const provider = ai.providers.find(p => p.id === ai.provider)
 useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }) }, [ai.messages.length, ai.busy])
 const submit = () => { if (text.trim() && !ai.busy) { send("aiSend", { text }); setText("") } }
 return <aside className="ai-sidebar" aria-label="AI sidebar">
  <div className="ai-head">
   <div className="ai-providers" role="tablist">{ai.providers.map(p => <button key={p.id} role="tab" aria-selected={p.id === ai.provider} disabled={ai.busy} className={cn(p.id === ai.provider && "is-on")} onClick={() => send("aiProvider", { provider: p.id })}>{p.name}</button>)}</div>
   <Button variant="ghost" size="icon-sm" aria-label="New chat" title="New chat" disabled={ai.busy} onClick={() => send("aiClear")}><RotateCcw /></Button>
   <Button variant="ghost" size="icon-sm" aria-label="Close AI sidebar" onClick={() => send("aiToggle")}><X /></Button>
  </div>
  {!provider?.installed ? <div className="ai-key">
   <Terminal />
   <p>{provider?.name} runs from its own command-line app, signed in to your account. Still never sees your login; usage counts toward your {provider?.name} plan.</p>
   <p>Install it, then sign in once in a terminal:</p>
   <code>{provider?.install}</code>
   <Button size="sm" variant="outline" onClick={() => send("aiProvider", { provider: ai.provider })}>I've installed it</Button>
  </div> : <>
   <div className="ai-log" ref={log}>
    {ai.messages.length === 0 && <p className="ai-empty">Ask about this page, or tell {provider?.name} what to do: “Find the cheapest flight on this page”, “Fill this form with…”. It never sees private tabs, passwords or cookies.</p>}
    {ai.messages.map((m, i) => <div key={i} className={"ai-msg is-" + m.role}>{m.role === "tool" ? "↳ " + m.text : m.text}</div>)}
    {ai.busy && <div className="ai-msg is-note"><Loader2 className="animate-spin" /> Working…</div>}
   </div>
  </>}
  {ai.error && <p role="alert" className="ai-error">{ai.error}</p>}
  {provider?.installed && <div className="ai-compose">
   <textarea aria-label="Message" placeholder={`Message ${provider.name}`} rows={2} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }} />
   {ai.busy ? <Button size="icon-sm" aria-label="Stop" onClick={() => send("aiStop")}><Square /></Button> : <Button size="icon-sm" aria-label="Send" disabled={!text.trim()} onClick={submit}><ArrowUp /></Button>}
  </div>}
 </aside>
}
