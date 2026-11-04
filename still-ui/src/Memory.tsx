import { useState } from "react"
import { History, MessageSquare, Pencil, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { destroy } from "./Undo"
import { Face, type Companion, type Fact } from "./Buddy"

// Settings > Memory: what each companion remembers about the user, kept on this PC (companions\<id>\memory.json and
// summaries.json). The user can see all of it and where each thing came from, fix it, forget a line, a chat or the lot.
type Send = (op: string, payload?: Record<string, unknown>) => void
const KINDS: Record<string, string> = { profile: "About you", fact: "About you", preference: "Likes", habit: "Habit", person: "Someone you know", project: "Project", correction: "Correction" }
const day = (at: string) => new Date(at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: new Date(at).getFullYear() === new Date().getFullYear() ? undefined : "numeric" })
type Ask = "clear" | "knowledge" | "personal" | "all"

export function MemorySettings({ companions, first, send, summaries, onOpenChat }: { companions: Companion[]; first?: string; send: Send; summaries?: boolean; onOpenChat?: (id: string) => void }) {
 const [id, setId] = useState(first || companions[0]?.id || "")
 const [adding, setAdding] = useState("")
 const [editing, setEditing] = useState<{ id: string; text: string } | null>(null)
 const [open, setOpen] = useState<string | null>(null) // the item whose earlier versions show
 const who = companions.find(c => c.id === id) ?? companions[0]
 if (!who) return <p className="data-intro">Make a companion first. What they remember about you shows up here.</p>
 const facts = who.memory ?? [], known = facts.filter(f => (f.status ?? "active") === "active" && f.kind !== "chat"), chats = who.summaries ?? []
 const earlier = (f: Fact) => { const list: Fact[] = []; for (let x = f; x.supersedes;) { const prev = facts.find(p => p.id === x.supersedes); if (!prev || list.includes(prev)) break; list.push(prev); x = prev } return list }
 const row = (f: Fact) => {
  const older = earlier(f)
  return editing?.id === f.id
   ? <form key={f.id} className="memory-row is-editing" onSubmit={e => { e.preventDefault(); if (editing.text.trim()) send("memoryEdit", { companion: who.id, id: f.id, text: editing.text.trim() }); setEditing(null) }}>
     <Input autoFocus aria-label="What to remember" maxLength={300} value={editing.text} onChange={e => setEditing({ ...editing, text: e.target.value })} />
     <Button type="submit" size="sm" disabled={!editing.text.trim()}>Save</Button><Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
    </form>
   : <div key={f.id} className="memory-item"><div className="memory-row" data-kind={f.kind}>
     <div><p>{f.subject ? <b>{f.subject}: </b> : null}{f.text}</p>
      <small>{[KINDS[f.kind] ?? "About you", f.guessed && "Guessed, not confirmed", day(f.at)].filter(Boolean).join(" · ")}</small>
      {f.sourceText && <small className="memory-source">{f.sourceText.charAt(0).toUpperCase() + f.sourceText.slice(1)}</small>}</div>
     {older.length > 0 && <Button variant="ghost" size="icon-xs" aria-label={`Earlier versions: ${f.text}`} aria-expanded={open === f.id} title="Earlier versions" onClick={() => setOpen(open === f.id ? null : f.id)}><History /></Button>}
     <Button variant="ghost" size="icon-xs" aria-label={"Edit: " + f.text} title="Edit" onClick={() => setEditing({ id: f.id, text: f.text })}><Pencil /></Button>
     <Button variant="ghost" size="icon-xs" aria-label={"Forget: " + f.text} title="Forget" onClick={() => destroy({ key: "fact:" + f.id, title: `Forget this?`, body: `${who.name} forgets "${f.text}", and its earlier versions.`, action: "Forget", done: "Forgotten", run: () => send("memoryForget", { companion: who.id, id: f.id }) })}><Trash2 /></Button>
    </div>
    {open === f.id && <ul className="memory-versions" aria-label="Earlier versions">{older.map(o => <li key={o.id}><s>{o.text}</s><small>{day(o.at)}</small></li>)}</ul>}
   </div>
 }
 const confirm: Record<Ask, [string, string, string, string, string]> = {
  clear: [`Clear ${who.name}'s memory?`, `${who.name} forgets all ${known.length} things above and all ${chats.length} chat summaries. Their knowledge files, instructions and chats stay.`, "Clear memory", "memoryClear", "Memory cleared"],
  knowledge: [`Reset ${who.name}'s knowledge files?`, `Each file goes back to empty. You can bring back a file's last version from its profile.`, "Reset files", "knowledgeReset", "Knowledge files reset"],
  personal: [`Clear ${who.name}'s personalization?`, `Their role, personality and reply length go back to the defaults, and what they learned in their first chat is forgotten. Their other memories stay.`, "Clear personalization", "personalizationClear", "Personalization cleared"],
  all: [`Reset everything for ${who.name}?`, `${who.name} forgets all memories, chat summaries and knowledge files, and their next chat starts with Setup again, like the first one. Your chats stay.`, "Reset everything", "memoryResetAll", `Everything reset for ${who.name}`],
 }
 const keys: Record<Ask, string> = { clear: "memory:", knowledge: "knowledge:", personal: "personal:", all: "memory-all:" }
 const setAsk = (k: Ask) => { const [title, body, action, op, done] = confirm[k]; destroy({ key: keys[k] + who.id, title, body, action, done, run: () => send(op, { companion: who.id }) }) }
 return <div className="memory-settings">
  <p className="data-intro">What your companions remember about you, kept on this PC, with where each thing came from. Passwords, codes, what you type into forms and anything from private tabs are never kept.</p>
  {companions.length > 1 && <div className="memory-who" role="radiogroup" aria-label="Companion">{companions.map(c =>
   <button key={c.id} role="radio" aria-checked={c.id === who.id} onClick={() => { setId(c.id); setEditing(null); setOpen(null) }}><Face companion={c} size={26} />{c.name}</button>)}</div>}
  <label className="memory-switch"><div><b>Remember new things</b><small>{who.capture === false ? `Off: ${who.name} uses what's below but keeps nothing new.` : `${who.name} saves what's worth keeping as you chat.`}</small></div>
   <Switch aria-label={`${who.name} remembers new things`} checked={who.capture !== false} onCheckedChange={on => send("memoryCapture", { companion: who.id, on })} /></label>
  {summaries !== undefined && <label className="memory-switch"><div><b>Summarize chats</b><small>For every companion: a chat that's been quiet for 10 minutes gets a short summary here, so they can pick it up later.</small></div>
   <Switch aria-label="Summarize chats" checked={summaries} onCheckedChange={on => send("chatSummaries", { on })} /></label>}
  <form className="memory-add" onSubmit={e => { e.preventDefault(); if (!adding.trim()) return; send("memoryAdd", { companion: who.id, text: adding.trim(), kind: "fact" }); setAdding("") }}>
   <Input aria-label={`Tell ${who.name} something to remember`} placeholder={`Tell ${who.name} something to remember, like "I'm vegetarian"`} maxLength={300} value={adding} onChange={e => setAdding(e.target.value)} />
   <Button type="submit" size="sm" disabled={!adding.trim()}><Plus />Add</Button>
  </form>
  <h4 className="memory-head">What {who.name} knows<span>{known.length}</span></h4>
  {known.length ? known.map(row) : <p className="empty-state">Nothing yet. Chat with {who.name}, or add something above.</p>}
  {chats.length > 0 && <><h4 className="memory-head">Past chats<span>{chats.length}</span></h4>
   {chats.map(s => <div key={s.chat} className="memory-row" data-kind="chat">
    <div><p><b>{s.title || "A chat"}</b></p><small className="memory-summary">{s.text}</small>
     <small>{[day(s.at), s.legacy && "From before this version, not checked against the chat", !s.exists && "Chat deleted"].filter(Boolean).join(" · ")}</small></div>
    {s.exists && onOpenChat && <Button variant="ghost" size="icon-xs" aria-label={"Open chat: " + (s.title || "chat")} title="Open chat" onClick={() => onOpenChat(s.chat)}><MessageSquare /></Button>}
    <Button variant="ghost" size="icon-xs" aria-label={"Forget this chat: " + (s.title || "chat")} title="Forget this chat" onClick={() => destroy({ key: `summary:${who.id}:${s.chat}`, title: "Forget this chat?", body: `${who.name} forgets the summary of "${s.title || "this chat"}". The chat itself stays.`, action: "Forget", done: "Chat summary forgotten", run: () => send("memoryForgetChat", { companion: who.id, chat: s.chat }) })}><Trash2 /></Button>
   </div>)}</>}
  <p className="memory-note"><b>Don't remember this chat</b>, under a chat's message box, keeps that one chat out of memory: nothing from it is saved or summarized. An <b>incognito window</b> goes further: Still keeps nothing from it at all, and memory there is read only.</p>
  <div className="memory-controls">
   <Button variant="ghost" size="sm" className="text-destructive" disabled={!known.length && !chats.length} onClick={() => setAsk("clear")}><Trash2 />Clear memory</Button>
   {!!who.knowledge?.length && <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setAsk("knowledge")}>Reset knowledge files</Button>}
   <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setAsk("personal")}>Clear personalization</Button>
   <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setAsk("all")}>Reset everything</Button>
  </div>
 </div>
}
