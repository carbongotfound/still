import { useState } from "react"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import { Face, type Companion, type Fact } from "./Buddy"

// Settings > Memory: what each companion remembers about the user, kept on this PC (companions\<id>\memory.json).
// The user can see all of it, fix it, forget a line or clear the lot.
type Send = (op: string, payload?: Record<string, unknown>) => void
const KINDS: Record<string, string> = { fact: "About you", preference: "Likes", habit: "Habit", person: "Someone you know", project: "Project" }
const day = (at: string) => new Date(at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: new Date(at).getFullYear() === new Date().getFullYear() ? undefined : "numeric" })

export function MemorySettings({ companions, first, send }: { companions: Companion[]; first?: string; send: Send }) {
 const [id, setId] = useState(first || companions[0]?.id || "")
 const [adding, setAdding] = useState("")
 const [editing, setEditing] = useState<{ id: string; text: string } | null>(null)
 const [clearing, setClearing] = useState(false)
 const who = companions.find(c => c.id === id) ?? companions[0]
 if (!who) return <p className="data-intro">Make a companion first. What they remember about you shows up here.</p>
 const facts = who.memory ?? [], known = facts.filter(f => f.kind !== "chat"), chats = facts.filter(f => f.kind === "chat")
 const row = (f: Fact) => editing?.id === f.id
  ? <form key={f.id} className="memory-row is-editing" onSubmit={e => { e.preventDefault(); if (editing.text.trim()) send("memoryEdit", { companion: who.id, id: f.id, text: editing.text.trim() }); setEditing(null) }}>
    <Input autoFocus aria-label="What to remember" maxLength={300} value={editing.text} onChange={e => setEditing({ ...editing, text: e.target.value })} />
    <Button type="submit" size="sm" disabled={!editing.text.trim()}>Save</Button><Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
   </form>
  : <div key={f.id} className="memory-row" data-kind={f.kind}>
    <div><p>{f.text}</p><small>{[KINDS[f.kind], f.guessed && "Guessed, not confirmed", day(f.at), f.kind !== "chat" && f.chatTitle && `from "${f.chatTitle}"`].filter(Boolean).join(" · ")}</small></div>
    {f.kind !== "chat" && <Button variant="ghost" size="icon-xs" aria-label={"Edit: " + f.text} title="Edit" onClick={() => setEditing({ id: f.id, text: f.text })}><Pencil /></Button>}
    <Button variant="ghost" size="icon-xs" aria-label={"Forget: " + f.text} title="Forget" onClick={() => send("memoryForget", { companion: who.id, id: f.id })}><Trash2 /></Button>
   </div>
 return <div className="memory-settings">
  <p className="data-intro">What your companions remember about you, kept on this PC. They pick things up as you chat. Passwords, what you type into forms and anything from private tabs are never kept.</p>
  {companions.length > 1 && <div className="memory-who" role="radiogroup" aria-label="Companion">{companions.map(c =>
   <button key={c.id} role="radio" aria-checked={c.id === who.id} onClick={() => { setId(c.id); setEditing(null) }}><Face companion={c} size={26} />{c.name}</button>)}</div>}
  <form className="memory-add" onSubmit={e => { e.preventDefault(); if (!adding.trim()) return; send("memoryAdd", { companion: who.id, text: adding.trim(), kind: "fact" }); setAdding("") }}>
   <Input aria-label={`Tell ${who.name} something to remember`} placeholder={`Tell ${who.name} something to remember, like "I'm vegetarian"`} maxLength={300} value={adding} onChange={e => setAdding(e.target.value)} />
   <Button type="submit" size="sm" disabled={!adding.trim()}><Plus />Add</Button>
  </form>
  <h4 className="memory-head">What {who.name} knows<span>{known.length}</span></h4>
  {known.length ? known.map(row) : <p className="empty-state">Nothing yet. Chat with {who.name}, or add something above.</p>}
  {chats.length > 0 && <><h4 className="memory-head">Past chats<span>{chats.length}</span></h4>{chats.map(row)}</>}
  {facts.length > 0 && <Button variant="ghost" className="settings-link text-destructive" onClick={() => setClearing(true)}><Trash2 />Clear everything {who.name} remembers</Button>}
  <AlertDialog open={clearing} onOpenChange={setClearing}><AlertDialogContent>
   <AlertDialogHeader><AlertDialogTitle>Clear {who.name}'s memory?</AlertDialogTitle><AlertDialogDescription>{who.name} forgets all {facts.length} things above. Your chats stay.</AlertDialogDescription></AlertDialogHeader>
   <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => send("memoryClear", { companion: who.id })}>Clear memory</AlertDialogAction></AlertDialogFooter>
  </AlertDialogContent></AlertDialog>
 </div>
}
