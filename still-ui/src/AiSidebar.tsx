import { useEffect, useRef, useState } from "react"
import { ArrowUp, KeyRound, Loader2, RotateCcw, Square, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

export type AiState = { open: boolean; provider: string; busy: boolean; error: string; model: string; models: string[]; providers: { id: string; name: string; hasKey: boolean; keyUrl: string }[]; messages: { role: string; text: string }[] }
type Send = (op: string, payload?: Record<string, unknown>) => void

// Chat with Claude, Codex or Grok on the user's own API key; the model can read and drive the open tabs.
export function AiSidebar({ ai, send }: { ai: AiState; send: Send }) {
 const [key, setKey] = useState("")
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
  {!provider?.hasKey ? <form className="ai-key" onSubmit={e => { e.preventDefault(); if (key.trim()) { send("aiKey", { provider: ai.provider, key: key.trim() }); setKey("") } }}>
   <KeyRound />
   <p>Use {provider?.name} with your own API key. Usage is billed to your {provider?.name} account by its maker; the key is encrypted on this PC and only sent to them.</p>
   <Input type="password" aria-label={`${provider?.name} API key`} placeholder="Paste API key" value={key} onChange={e => setKey(e.target.value)} autoComplete="off" />
   <div className="ai-row"><Button type="button" variant="ghost" size="sm" onClick={() => provider && send("new", { url: provider.keyUrl })}>Get a key</Button><Button type="submit" size="sm" disabled={!key.trim()}>Save key</Button></div>
  </form> : <>
   <div className="ai-model">
    <select aria-label="Model" value={ai.model} disabled={ai.busy || !ai.models.length} onChange={e => send("aiModel", { model: e.target.value })}>
     {!ai.models.length && <option value="">Loading models…</option>}
     {ai.models.map(m => <option key={m} value={m}>{m}</option>)}
    </select>
    <button className="ai-link" disabled={ai.busy} onClick={() => send("aiKey", { provider: ai.provider, key: "" })}>Remove key</button>
   </div>
   <div className="ai-log" ref={log}>
    {ai.messages.length === 0 && <p className="ai-empty">Ask about this page, or tell {provider?.name} what to do: “Find the cheapest flight on this page”, “Fill this form with…”. It never sees private tabs, passwords or cookies.</p>}
    {ai.messages.map((m, i) => <div key={i} className={"ai-msg is-" + m.role}>{m.role === "tool" ? "↳ " + m.text : m.text}</div>)}
    {ai.busy && <div className="ai-msg is-note"><Loader2 className="animate-spin" /> Working…</div>}
   </div>
  </>}
  {ai.error && <p role="alert" className="ai-error">{ai.error}</p>}
  {provider?.hasKey && <div className="ai-compose">
   <textarea aria-label="Message" placeholder={`Message ${provider.name}`} rows={2} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() } }} />
   {ai.busy ? <Button size="icon-sm" aria-label="Stop" onClick={() => send("aiStop")}><Square /></Button> : <Button size="icon-sm" aria-label="Send" disabled={!text.trim() || !ai.model} onClick={submit}><ArrowUp /></Button>}
  </div>}
 </aside>
}
