import { useEffect, useState } from "react"
import { Plug, ShieldAlert, ShieldCheck, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { Face, type Companion } from "./Buddy"
import type { AiState } from "./AiSidebar"
import { destroy } from "./Undo"

type Send = (op: string, payload?: Record<string, unknown>) => void
// A step waiting for your OK. With until, a sensitive step you allowed without asking, counting down to go ahead.
// run and who: the task asking, a teammate's child task when it isn't this chat's own.
export type Approval = { id: string; run?: string; who?: string; what: string; site: string; action: string; why: string; until?: string | null }
export type Rule = { site: string; action: string; companion: string; mode: string }
export type AuditEntry = { at: string; what: string; site: string; result: string }

const ACTIONS: Record<string, string> = { read: "Read pages", navigate: "Open pages", interact: "Click, type and scroll", sensitive: "Sensitive steps" }
const MODES: Record<string, string> = { always: "Always allow", chat: "Allow in this chat", ask: "Ask every time" }

// The cards above the message box: steps waiting for your OK (Approve all when there are several), and countdowns.
export function Approvals({ list, companion, companions, send, incognito }: { list: Approval[]; companion?: Companion; companions?: Companion[]; send: Send; incognito?: boolean }) {
 const asks = list.filter(a => !a.until), one = asks.length === 1 ? asks[0] : null
 const mate = (a?: Approval | null) => companions?.find(c => c.id === a?.who) ?? companion, name = mate(one)?.name ?? "Your AI"
 const byId = (id: string) => list.find(a => a.id === id)
 const answer = (id: string, a: string) => send("permAnswer", { id, run: byId(id)?.run, answer: a })
 return <>
  {list.filter(a => a.until).map(a => <Countdown key={a.id} card={a} send={send} />)}
  {asks.length > 0 && <div className="ask-card approve-card" role="group" aria-label={name + " needs your OK"}>
   <div className="ask-q"><Face companion={mate(one)} size={22} mood="needs" /><p>{one?.action === "connect" ? `${name} needs ${one.site} for this.` : one ? `${name} wants to do this. Is that okay?` : `${name} wants to do ${asks.length} things. Are they okay?`}</p></div>
   <ul className="approve-steps">{asks.map(a => <li key={a.id} className={cn((a.action === "sensitive" || a.action === "plugin") && "is-sensitive")}>
    {a.action === "connect" ? <Plug /> : a.action === "sensitive" || a.action === "plugin" ? <ShieldAlert /> : <ShieldCheck />}
    <span><b>{a.what}</b><small>{[a.who && a.who !== companion?.id && mate(a)?.name, a.site, a.why].filter(Boolean).join(" · ")}</small></span>
    {!one && <button className="approve-no" aria-label={"Don't " + a.what.toLowerCase()} title="Don't do this" onClick={() => answer(a.id, "deny")}><X /></button>}
   </li>)}</ul>
   <div className="approve-actions">{one?.action === "connect"
    ? <><Button size="sm" variant="ghost" onClick={() => answer(one.id, "deny")}>Not now</Button><Button size="sm" data-approve title="Ctrl+Enter" onClick={() => answer(one.id, "connect")}>{one.what}</Button></>
    : one?.action === "plugin" // the user's own apps: once at a time, never "always"
    ? <><Button size="sm" variant="ghost" onClick={() => answer(one.id, "deny")}>Deny</Button><Button size="sm" data-approve title="Ctrl+Enter" onClick={() => answer(one.id, "once")}>Allow once</Button></>
    : one
    ? <><Button size="sm" variant="ghost" onClick={() => answer(one.id, "deny")}>Deny</Button>
     {!incognito && <Button size="sm" variant="outline" title={one.action === "sensitive" ? "It still waits 8 seconds next time, so you can cancel" : undefined} onClick={() => answer(one.id, "always")}>Always on this site</Button>}
     {one.action === "sensitive"
      ? <><Button size="sm" variant="outline" title="It still waits 8 seconds next time, so you can cancel" onClick={() => answer(one.id, "chat")}>Allow in this chat</Button><Button size="sm" data-approve title="Ctrl+Enter" onClick={() => answer(one.id, "once")}>Allow once</Button></>
      : <><Button size="sm" variant="outline" data-approve title="Ctrl+Enter" onClick={() => answer(one.id, "once")}>Allow once</Button><Button size="sm" onClick={() => answer(one.id, "chat")}>Allow in this chat</Button></>}</>
    : <><Button size="sm" variant="ghost" onClick={() => asks.forEach(a => answer(a.id, "deny"))}>Deny all</Button><Button size="sm" data-approve title="Ctrl+Enter" onClick={() => asks.forEach(a => answer(a.id, "once"))}>Approve all ({asks.length})</Button></>}
   </div>
  </div>}
 </>
}

function Countdown({ card, send }: { card: Approval; send: Send }) {
 const end = Date.parse(card.until ?? "")
 const seconds = () => Math.max(0, Math.ceil((end - Date.now()) / 1000))
 const [left, setLeft] = useState(seconds)
 const [duration] = useState(() => Math.max(0, end - Date.now()))
 useEffect(() => { const t = setInterval(() => setLeft(seconds()), 200); return () => clearInterval(t) }, [end]) // eslint-disable-line react-hooks/exhaustive-deps
 return <div className="ask-card countdown-card" role="alert">
  <div className="ask-q"><ShieldAlert /><p>Going ahead in {left}s</p></div>
  <ul className="approve-steps"><li className="is-sensitive"><span><b>{card.what}</b><small>{[card.site, card.why].filter(Boolean).join(" · ")}</small></span></li></ul>
  <div className="countdown-bar" aria-hidden><i style={{ animationDuration: duration + "ms" }} /></div>
  <div className="approve-actions"><Button size="sm" variant="outline" onClick={() => send("permAnswer", { id: card.id, run: card.run, answer: "cancel" })}>Cancel</Button><Button size="sm" onClick={() => send("permAnswer", { id: card.id, run: card.run, answer: "now" })}>Do it now</Button></div>
 </div>
}

// What the AI asked to do on sites in this chat, newest first.
export function AuditList({ list }: { list: AuditEntry[] }) {
 return <ol className="audit-list">{list.slice().reverse().map((a, i) => <li key={i} title={a.site}><b>{a.what}</b><small>{a.result} · {new Date(a.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</small></li>)}</ol>
}

function ModeSelect({ value, onChange, label }: { value: string; onChange: (mode: string) => void; label: string }) {
 return <Select value={value} onValueChange={onChange}><SelectTrigger size="sm" aria-label={label} className="perm-mode"><SelectValue /></SelectTrigger>
  <SelectContent>{Object.entries(MODES).map(([id, text]) => <SelectItem key={id} value={id}>{text}</SelectItem>)}</SelectContent></Select>
}

// Settings → AI permissions: the defaults, rules per site and companion, sensitive sites, Reset all.
export function PermissionsSettings({ ai, send }: { ai: AiState; send: Send }) {
 const rules = ai.permissions ?? [], companions = ai.companions ?? []
 const [site, setSite] = useState(""), [who, setWho] = useState("all"), [action, setAction] = useState("interact"), [mode, setMode] = useState("always")
 const [marked, setMarked] = useState("")
 const name = (id: string) => id ? companions.find(c => c.id === id)?.name ?? id : "Everyone"
 const where = (r: Rule) => `${ACTIONS[r.action]} on ${r.site || "any site"} for ${name(r.companion)}`
 return <div className="perm-settings">
  <p className="tool-caption">Choose what your companions may do without asking. Sensitive steps are buying, sending, deleting, forms that send data, and password or payment fields. Allowed without asking, a sensitive step still waits 8 seconds so you can cancel it. AI apps you connect from outside Still only ask when a rule for everyone or a sensitive site says to.</p>
  <table className="perm-table"><thead><tr><th>Site</th><th>Who</th><th>Action</th><th>Permission</th><th><span className="sr-only">Remove</span></th></tr></thead>
   <tbody>{rules.map(r => <tr key={r.site + "|" + r.action + "|" + r.companion}>
    <td>{r.site || "Any site"}</td><td>{name(r.companion)}</td><td>{ACTIONS[r.action]}</td>
    <td><ModeSelect value={r.mode} onChange={m => send("permSet", { ...r, mode: m })} label={where(r)} /></td>
    <td>{(r.site || r.companion) && <button className="perm-remove" aria-label={"Remove the rule: " + where(r)} title="Remove" onClick={() => send("permSet", { ...r, mode: "" })}><X /></button>}</td>
   </tr>)}</tbody></table>
  <form className="perm-add" onSubmit={e => { e.preventDefault(); if (!site.trim() && who === "all") return; send("permSet", { site, companion: who === "all" ? "" : who, action, mode }); setSite("") }}>
   <Input aria-label="Site for the new rule" placeholder="Site, like shop.com" value={site} onChange={e => setSite(e.target.value)} />
   <Select value={who} onValueChange={setWho}><SelectTrigger size="sm" aria-label="Who the new rule is for"><SelectValue /></SelectTrigger>
    <SelectContent><SelectItem value="all">Everyone</SelectItem>{companions.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>
   <Select value={action} onValueChange={setAction}><SelectTrigger size="sm" aria-label="Action for the new rule"><SelectValue /></SelectTrigger>
    <SelectContent>{Object.entries(ACTIONS).map(([id, text]) => <SelectItem key={id} value={id}>{text}</SelectItem>)}</SelectContent></Select>
   <ModeSelect value={mode} onChange={setMode} label="Permission for the new rule" />
   <Button type="submit" size="sm" variant="outline" disabled={!site.trim() && who === "all"}>Add</Button>
  </form>
  <Separator />
  <div className="setting-row"><div><strong>Sensitive sites</strong><p>Every click and keystroke on these sites asks you first, like a purchase does.</p></div></div>
  <div className="perm-sites">{(ai.sensitiveSites ?? []).map(s => <span key={s} className="perm-site">{s}<button aria-label={"Remove " + s} title="Remove" onClick={() => send("permSensitive", { site: s, on: false })}><X /></button></span>)}
   <form onSubmit={e => { e.preventDefault(); if (marked.trim()) send("permSensitive", { site: marked, on: true }); setMarked("") }}>
    <Input aria-label="Add a sensitive site" placeholder="Add a site, like mybank.com" value={marked} onChange={e => setMarked(e.target.value)} /><Button type="submit" size="sm" variant="outline" disabled={!marked.trim()}>Add</Button>
   </form></div>
  <Separator />
  <div className="setting-row"><div><strong>Reset all</strong><p>Back to the start: reading and opening pages just happen, clicking and typing ask once per site in each chat, and sensitive steps ask every time.</p></div>
   <Button variant="outline" size="sm" onClick={() => destroy({ key: "perm-reset", title: "Reset all permissions?", action: "Reset all", done: "Permissions reset",
    body: `Your ${(ai.permissions ?? []).length} rules and ${(ai.sensitiveSites ?? []).length} sensitive sites go, and companions ask like the first day.`, run: () => send("permReset") })}>Reset all</Button></div>
 </div>
}
