import { useEffect, useState } from "react"
import { FolderOpen, Plug, ShieldAlert, ShieldCheck, X } from "lucide-react"
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
// Settings set one of two: Allow in this chat is only a card's answer, in that chat. A rule saved as "chat" asks in
// every new chat, so it reads Ask every time.
const MODES: Record<string, string> = { always: "Always allow", ask: "Ask every time" }
// How much a companion does on its own: one pick per companion. Still holds what each level allows (Windows LevelOf, Mac
// levelOf): clicking and typing on any site, new sites after reading the web, plugin programs, and a line in its instructions.
export const AUTONOMY = {
 ask: { name: "Ask more", short: "Checks in on choices and each site" },
 balanced: { name: "Balanced", short: "Asks once a chat on each site" },
 keepgoing: { name: "Keep going", short: "Asks only before risky steps" },
} as const
export type Autonomy = keyof typeof AUTONOMY
export const levelOf = (c?: Companion): Autonomy => c?.autonomy ?? "keepgoing"
export const ALWAYS_ASKS = "At every level, buying, sending, deleting, forms that send data, and password or payment fields ask first, and so do your own computer or network and a long address that carries data to a new site."

// Buttons whose meaning just changed wait a moment before they take a click, so a press meant for the last card can't land on the next.
export function useArmed(key: string) {
 const [armed, setArmed] = useState<string | null>(null)
 useEffect(() => { const t = setTimeout(() => setArmed(key), 500); return () => clearTimeout(t) }, [key])
 return armed === key
}

// A long path cut to its first and last parts, like D:\…\frames; the step under it shows the whole one.
const elide = (path: string) => {
 const sep = path.includes("\\") ? "\\" : "/", parts = path.split(sep).filter(Boolean), lead = path.startsWith(sep) ? sep : ""
 return parts.length > 3 ? lead + parts[0] + sep + "…" + sep + parts[parts.length - 1] : path
}

// The cards above the message box: steps waiting for your OK, and countdowns. The bottom row always acts on one step, the oldest,
// shown right above it, and each button keeps its place; a step that arrives later lands above and can't move anything under the
// cursor. Approve all and Deny all sit at the top, away from that row, and Ctrl+Enter never presses them.
export function Approvals({ list, companion, companions, send, incognito }: { list: Approval[]; companion?: Companion; companions?: Companion[]; send: Send; incognito?: boolean }) {
 const asks = list.filter(a => !a.until), one = asks.length === 1 ? asks[0] : null, active = asks[0]
 const mate = (a?: Approval | null) => companions?.find(c => c.id === a?.who) ?? companion, name = mate(one)?.name ?? "Your AI"
 const ready = useArmed(active?.id ?? ""), readyAll = useArmed(asks.map(a => a.id).join())
 const byId = (id: string) => list.find(a => a.id === id)
 const answer = (id: string, a: string) => send("permAnswer", { id, run: byId(id)?.run, answer: a })
 return <>
  {list.filter(a => a.until).map(a => <Countdown key={a.id} card={a} send={send} />)}
  {asks.length > 0 && <div className="ask-card approve-card" role="group" aria-label={name + " needs your OK"}>
   <div className="ask-q"><Face companion={mate(one)} size={22} mood="needs" /><p>{one?.action === "connect" ? `${name} needs ${one.site} for this.` : one?.action === "folder" ? `Let ${name} work in ${elide(one.site)}?` : one ? `${name} wants to do this. Is that okay?` : `${name} wants to do ${asks.length} things. Are they okay?`}</p></div>
   {!one && <div className="approve-all"><Button size="sm" variant="ghost" disabled={!readyAll} onClick={() => asks.forEach(a => answer(a.id, "deny"))}>Deny all</Button><Button size="sm" variant="outline" disabled={!readyAll} onClick={() => asks.forEach(a => answer(a.id, "once"))}>Approve all ({asks.length})</Button></div>}
   <ul className="approve-steps">{[...asks.slice(1), active].map(a => <li key={a.id} className={cn((a.action === "sensitive" || a.action === "plugin" || a.action === "program") && "is-sensitive", !one && a === active && "is-active")}>
    {a.action === "connect" ? <Plug /> : a.action === "folder" ? <FolderOpen /> : a.action === "sensitive" || a.action === "plugin" || a.action === "program" ? <ShieldAlert /> : <ShieldCheck />}
    <span><b>{a.what}</b><small>{[a.who && a.who !== companion?.id && mate(a)?.name, a.site, a.why].filter(Boolean).join(" · ")}</small></span>
    {!one && a !== active && <button className="approve-no" aria-label={"Don't " + a.what.toLowerCase()} title="Don't do this" onClick={() => answer(a.id, "deny")}><X /></button>}
   </li>)}</ul>
   <div className="approve-actions">{active.action === "folder" // a working folder for this chat: asked every time, on every level
    ? <><Button size="sm" variant="ghost" disabled={!ready} onClick={() => answer(active.id, "deny")}>Not now</Button><Button size="sm" variant="outline" disabled={!ready} onClick={() => answer(active.id, "pick")}>Choose another folder</Button><Button size="sm" data-approve title="Ctrl+Enter" disabled={!ready} onClick={() => answer(active.id, "once")}>Allow</Button></>
    : active.action === "connect"
    ? <><Button size="sm" variant="ghost" disabled={!ready} onClick={() => answer(active.id, "deny")}>Not now</Button><Button size="sm" data-approve title="Ctrl+Enter" disabled={!ready} onClick={() => answer(active.id, "connect")}>{active.what}</Button></>
    : active.action === "program" // a plugin's program: once, or from now on for that plugin
    ? <><Button size="sm" variant="ghost" disabled={!ready} onClick={() => answer(active.id, "deny")}>Deny</Button><Button size="sm" variant="outline" disabled={!ready} onClick={() => answer(active.id, "always")}>Always for this plugin</Button><Button size="sm" data-approve title="Ctrl+Enter" disabled={!ready} onClick={() => answer(active.id, "once")}>Allow once</Button></>
    : active.action === "plugin" // the user's own apps, and a plugin's setup: once at a time, never "always"
    ? <><Button size="sm" variant="ghost" disabled={!ready} onClick={() => answer(active.id, "deny")}>Deny</Button><Button size="sm" data-approve title="Ctrl+Enter" disabled={!ready} onClick={() => answer(active.id, "once")}>Allow once</Button></>
    : <><Button size="sm" variant="ghost" disabled={!ready} onClick={() => answer(active.id, "deny")}>Deny</Button>
     {incognito || !active.site || active.action === "files" ? <span /> : <Button size="sm" variant="outline" disabled={!ready} title={active.action === "sensitive" ? "It still waits 8 seconds next time, so you can cancel" : undefined} onClick={() => answer(active.id, "always")}>Always on this site</Button>}
     {active.action === "sensitive"
      ? <><Button size="sm" variant="outline" disabled={!ready} title="It still waits 8 seconds next time, so you can cancel" onClick={() => answer(active.id, "chat")}>Allow in this chat</Button><Button size="sm" data-approve title="Ctrl+Enter" disabled={!ready} onClick={() => answer(active.id, "once")}>Allow once</Button></>
      : <><Button size="sm" disabled={!ready} onClick={() => answer(active.id, "chat")}>Allow in this chat</Button><Button size="sm" variant="outline" data-approve title="Ctrl+Enter" disabled={!ready} onClick={() => answer(active.id, "once")}>Allow once</Button></>}</>}
   </div>
  </div>}
 </>
}

function Countdown({ card, send }: { card: Approval; send: Send }) {
 const end = Date.parse(card.until ?? "")
 const seconds = () => Math.max(0, Math.ceil((end - Date.now()) / 1000))
 const [left, setLeft] = useState(seconds)
 const [duration] = useState(() => Math.max(0, end - Date.now()))
 const ready = useArmed(card.id) // Cancel takes a click at once; Do it now, a moment later
 useEffect(() => { const t = setInterval(() => setLeft(seconds()), 200), zero = setTimeout(() => setLeft(0), end - Date.now()); return () => { clearInterval(t); clearTimeout(zero) } }, [end]) // eslint-disable-line react-hooks/exhaustive-deps
 return <div className="ask-card countdown-card" role="alert">
  <div className="ask-q"><ShieldAlert /><p>{left ? `Going ahead in ${left}s` : "Going ahead…"}</p></div>
  <ul className="approve-steps"><li className="is-sensitive"><span><b>{card.what}</b><small>{[card.site, card.why].filter(Boolean).join(" · ")}</small></span></li></ul>
  <div className="countdown-bar" aria-hidden><i style={{ animationDuration: duration + "ms" }} /></div>
  <div className="approve-actions"><Button size="sm" variant="outline" disabled={!left} onClick={() => send("permAnswer", { id: card.id, run: card.run, answer: "cancel" })}>Cancel</Button><Button size="sm" disabled={!left || !ready} onClick={() => send("permAnswer", { id: card.id, run: card.run, answer: "now" })}>Do it now</Button></div>
 </div>
}

// What the AI asked to do on sites in this chat, newest first.
export function AuditList({ list }: { list: AuditEntry[] }) {
 return <ol className="audit-list">{list.slice().reverse().map((a, i) => <li key={i} title={a.site}><b>{a.what}</b><small>{a.result} · {new Date(a.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</small></li>)}</ol>
}

function ModeSelect({ value, onChange, label }: { value: string; onChange: (mode: string) => void; label: string }) {
 return <Select value={value === "chat" ? "ask" : value} onValueChange={onChange}><SelectTrigger size="sm" aria-label={label} className="perm-mode"><SelectValue /></SelectTrigger>
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
  <p className="tool-caption">Choose what your companions may do without asking. Sensitive steps are buying, sending, deleting, forms that send data, and password or payment fields. Allowed without asking, a sensitive step still waits 8 seconds so you can cancel it. AI apps you connect from outside Still ask in the bar at the top before a sensitive step, and when a rule for everyone or a sensitive site says to.</p>
  <div className="setting-row"><div><strong>Autonomy</strong><p>How much each companion does before it checks with you. Keep going makes the calls and keeps working. {ALWAYS_ASKS}</p></div></div>
  {companions.map(c => { const level = levelOf(c); return <div key={c.id} className="setting-row perm-level" id={"set-autonomy-" + c.id}><div><strong><Face companion={c} size={20} />{c.name}</strong><p>{AUTONOMY[level].short}</p></div>
   <Select value={level} onValueChange={v => send("companionAutonomy", { id: c.id, level: v })}><SelectTrigger size="sm" aria-label={"Autonomy for " + c.name}><SelectValue /></SelectTrigger>
    <SelectContent>{(Object.keys(AUTONOMY) as Autonomy[]).map(id => <SelectItem key={id} value={id}>{AUTONOMY[id].name}</SelectItem>)}</SelectContent></Select></div> })}
  <Separator />
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
  <div className="setting-row"><div><strong>Reset all</strong><p>Back to the start: your rules and sensitive sites go, reading and opening pages just happen, and sensitive steps ask every time. Each companion keeps its autonomy.</p></div>
   <Button variant="outline" size="sm" onClick={() => destroy({ key: "perm-reset", title: "Reset all permissions?", action: "Reset all", done: "Permissions reset",
    body: `Your ${(ai.permissions ?? []).length} rules and ${(ai.sensitiveSites ?? []).length} sensitive sites go. Each companion keeps its autonomy.`, run: () => send("permReset") })}>Reset all</Button></div>
 </div>
}
