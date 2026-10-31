import { Fragment, useEffect, useState, type CSSProperties, type ReactNode } from "react"
import { Check, ChevronDown, Loader2, Plug, Search, Unplug } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import type { AiState } from "./AiSidebar"
import type { Companion } from "./Buddy"
import { BODY_COLORS } from "./look"

// Plugins: the user's apps through Composio, a third-party service, with their own project API key (MainWindow.Plugins.cs
// and Plugins.swift). The key goes in here once and never comes back: the shell only hears that there is one, and its
// last four characters. Composio's catalog (every app, its categories and how it signs in) and the logos come on their
// own messages, not with the state, and stay here for the session.
type Send = (op: string, payload?: Record<string, unknown>) => void
export type PluginsState = {
 key: boolean; keyEnd?: string; status: "off" | "ok" | "bad" | "down"; checking?: boolean; problem?: "" | "kind" | "bad" | "down"
 connecting: string; failed?: string; error?: string; connected: { id: string; slug: string; name: string }[]
}
export type PluginApp = { slug: string; name: string; cats: string[]; auth: "managed" | "none" | "custom" }
// The apps people connect most (Composio toolkit slugs), for setup's belt and the Hire cards, and the page until Composio's catalog comes in.
export const POPULAR: [string, string][] = [
 ["gmail", "Gmail"], ["googlecalendar", "Google Calendar"], ["slack", "Slack"], ["notion", "Notion"], ["github", "GitHub"], ["googledrive", "Google Drive"],
 ["linear", "Linear"], ["hubspot", "HubSpot"], ["googlesheets", "Google Sheets"], ["googledocs", "Google Docs"], ["outlook", "Outlook"], ["jira", "Jira"],
 ["asana", "Asana"], ["trello", "Trello"], ["airtable", "Airtable"], ["salesforce", "Salesforce"], ["zoom", "Zoom"], ["figma", "Figma"],
 ["dropbox", "Dropbox"], ["calendly", "Calendly"], ["zendesk", "Zendesk"], ["intercom", "Intercom"], ["linkedin", "LinkedIn"], ["stripe", "Stripe"],
]
export const pluginName = (slug: string) => catalog.find(a => a.slug === slug)?.name ?? POPULAR.find(p => p[0] === slug)?.[1] ?? slug.charAt(0).toUpperCase() + slug.slice(1)
export const andList = (names: string[]) => names.length < 2 ? names.join("") : names.slice(0, -1).join(", ") + " and " + names.at(-1)

// Composio's long category names, short enough for a chip: "Collaboration & Communication" is Communication.
const SHORT: Record<string, string> = { "collaboration & communication": "Communication", "developer tools & devops": "Code", "document & file management": "Files", "analytics & data": "Data",
 "data & analytics": "Data", "advertising & marketing": "Marketing", "marketing & social media": "Marketing", "sales & customer support": "Sales", "ai & machine learning": "AI" }
const shortCat = (c: string) => SHORT[c.toLowerCase()] ?? c.split(" & ")[0]
let catalog: PluginApp[] = [], logos: Record<string, string> = {}, sender: Send | null = null
const asked = new Set<string>(), wanted = new Set<string>(), heard = new Set<() => void>()
const changed = () => heard.forEach(f => f())
addEventListener("still-pluginCatalog", e => { catalog = ((e as CustomEvent).detail ?? []).map((a: PluginApp) => ({ ...a, cats: [...new Set(a.cats.map(shortCat))] })); asked.clear(); changed() }) // a new catalog may know logos an older one didn't
addEventListener("still-pluginLogos", e => { logos = { ...logos, ...(e as CustomEvent).detail }; changed() })
/// Re-renders when the catalog or a logo comes in.
export function usePluginData(send?: Send) {
 const [, tick] = useState(0)
 useEffect(() => { if (send) sender = send; const f = () => tick(n => n + 1); heard.add(f); return () => { heard.delete(f) } }, [send])
 return catalog
}
/// Asks for a logo once; the asks of one render go out together.
function wantLogo(slug: string) {
 if (logos[slug] || asked.has(slug) || !sender) return
 asked.add(slug); wanted.add(slug)
 if (wanted.size === 1) setTimeout(() => { sender?.("pluginLogos", { slugs: [...wanted] }); wanted.clear() }, 60)
}

export const plugColor = (slug: string) => BODY_COLORS[[...slug].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) % 997, 7) % BODY_COLORS.length][0]
const plugHue = (slug: string) => ({ "--hue": plugColor(slug) }) as CSSProperties
/// The logo's address once it's in (asking for it if it isn't).
export const logoOf = (slug: string): string | undefined => { wantLogo(slug); return logos[slug] }
/// An app's logo from Composio's catalog, or its initial on a soft tile until there is one.
export function PluginLogo({ slug, name, className }: { slug: string; name: string; className?: string }) {
 useEffect(() => wantLogo(slug), [slug])
 return logos[slug] ? <i className={cn("plug-logo is-image", className)} aria-hidden><img src={logos[slug]} alt="" /></i>
  : <i className={cn("plug-logo", className)} aria-hidden style={plugHue(slug)}>{name.charAt(0)}</i>
}
/// A clean name chip: the app's logo, then its name.
export function PluginChip({ slug, name, hidden }: { slug: string; name: string; hidden?: boolean }) {
 return <span className="plug-chip" aria-hidden={hidden}><PluginLogo slug={slug} name={name} />{name}</span>
}

/// Connected apps as overlapping logos (up to four, or three and +N), a plug when there are none.
function Stack({ on }: { on: PluginsState["connected"] }) {
 const shown = on.slice(0, on.length > 4 ? 3 : 4)
 return <span className={cn("plug-stack", !on.length && "is-empty")} aria-hidden>{on.length ? <>{shown.map(c => <PluginLogo key={c.id} slug={c.slug} name={c.name} />)}
  {on.length > shown.length && <i className="is-more">+{on.length - shown.length}</i>}</> : <i><Plug /></i>}</span>
}
/// The home row's Plugins button.
export function PluginStack({ plugins, send, onOpen }: { plugins?: PluginsState; send: Send; onOpen: () => void }) {
 usePluginData(send)
 const on = plugins?.key ? plugins.connected : []
 return <button className="home-plugins" onClick={onOpen} aria-label={on.length ? `Plugins: ${andList(on.map(c => c.name))} connected` : "Plugins: none connected yet"}><Stack on={on} />Plugins</button>
}

/// Setup's belt: two rows of apps gliding opposite ways, paused under the pointer. Reduced motion gets a still grid (App.css).
export function PluginBelt() {
 return <div className="plug-belt" aria-label="Apps you can connect">{[POPULAR.slice(0, 12), POPULAR.slice(12)].map((row, i) =>
  <div key={i} className={cn("plug-row", i === 1 && "is-reverse")}><div className="plug-track">
   {[...row, ...row].map(([slug, name], j) => <PluginChip key={j} slug={slug} name={name} hidden={j >= row.length} />)}
  </div></div>)}</div>
}

/// With a key: the same apps as a grid to pick from. A tap connects it; connected ones have a check.
export function PluginGrid({ plugins, send }: { plugins: PluginsState; send: Send }) {
 return <div className="plug-grid" role="group" aria-label="Connect an app">{POPULAR.map(([slug, name]) => {
  const on = plugins.connected.some(c => c.slug === slug), busy = plugins.connecting === slug
  return <button key={slug} className={cn("plug-pick", on && "is-on")} aria-pressed={on} aria-label={on ? `${name} is connected` : `Connect ${name}`} disabled={on || !!plugins.connecting}
   onClick={() => send("pluginConnect", { slug })}><PluginChip slug={slug} name={name} />{busy ? <Loader2 className="animate-spin" /> : on ? <Check /> : null}</button>
 })}</div>
}

/// Where the key comes from, then paste it once. Composio checks it before it's kept (a bad one never replaces a good
/// one), it's kept like saved passwords, and the field empties right away. Composio's For You page shows a Connect key
/// (ck_…) that its API refuses: the steps point past it.
export function PluginKey({ plugins, send, label = "Turn on plugins", steps = true }: { plugins?: PluginsState; send: Send; label?: string; steps?: boolean }) {
 const [key, setKey] = useState("")
 const checking = !!plugins?.checking, problem = plugins?.problem
 return <form className="plug-key" onSubmit={e => { e.preventDefault(); if (key.trim().length >= 8) { send("pluginKey", { key: key.trim() }); setKey("") } }}>
  {steps && <ol className="plug-steps">
   <li><a href="#" onClick={e => { e.preventDefault(); send("pluginLink", { to: "key" }) }}>Get a key</a>: Composio opens in a new window.</li>
   <li>There, switch to <b>Platform</b> and open <b>Settings → Project Settings → API Keys</b>.</li>
   <li>Copy the project API key, which starts with <code>ak_</code>, and paste it here.</li>
  </ol>}
  <div className="plug-key-row">
   <Input type="password" autoComplete="off" spellCheck={false} aria-label="Composio API key" placeholder="Paste your Composio API key" value={key} onChange={e => setKey(e.target.value)} />
   <Button type="submit" size="sm" disabled={key.trim().length < 8 || checking}>{checking && <Loader2 className="animate-spin" />}{label}</Button>
  </div>
  {problem === "bad" && <p className="plug-error" role="alert">Composio didn't accept that key. Check it and paste it again: Still needs the project API key that starts with ak_.</p>}
  {problem === "kind" && <p className="plug-error" role="alert">That's a Composio Connect key (ck_…) or a personal key (uak_…), and Composio only lets apps like Still in with a project API key. Paste the one that starts with ak_, from Platform → Settings → Project Settings.</p>}
  {problem === "down" && <p className="plug-error" role="alert">Composio isn't answering right now, so Still couldn't check that key. Try again in a little while.</p>}
  <p className="plug-note">Your key is encrypted on this computer, like your passwords, and AI never sees it.</p>
 </form>
}

export function ThirdParty() {
 return <p className="plug-note">Composio is a third-party service. Still only talks to it with your key, when you connect or use an app, and keeps its app list and logos on this computer.</p>
}

/// Settings → Skills & plugins: the key, shown only as set with its last four characters. Change it (the new one is
/// checked before it replaces the old one) or delete it, which turns plugins off.
export function PluginKeySetting({ plugins, send }: { plugins?: PluginsState; send: Send }) {
 const [changing, setChanging] = useState(false), [deleting, setDeleting] = useState(false)
 const end = plugins?.key ? plugins.keyEnd ?? "" : ""
 useEffect(() => { if (!plugins?.checking && !plugins?.problem) setChanging(false) }, [plugins?.checking]) // eslint-disable-line react-hooks/exhaustive-deps
 if (!plugins?.key) return <div className="setting-row is-stacked" id="set-composio"><div><strong>Composio API key</strong><p>Not set. Plugins stay off until you add your own project API key.</p></div>
  <PluginKey plugins={plugins} send={send} /></div>
 return <div className="setting-row is-stacked" id="set-composio">
  <div className="plug-keyline"><div><strong>Composio API key</strong><p>Set, ending in <code className="plug-end">{end}</code>. Still never shows the rest of it, here or anywhere else.</p></div>
   {!changing && !deleting && <div className="plug-keyacts"><Button size="sm" variant="outline" onClick={() => setChanging(true)}>Change</Button><Button size="sm" variant="outline" onClick={() => setDeleting(true)}>Delete</Button></div>}</div>
  {changing && <><PluginKey plugins={plugins} send={send} label="Save new key" steps={false} /><Button size="sm" variant="ghost" className="plug-cancel" onClick={() => setChanging(false)}>Cancel</Button></>}
  {deleting && <div className="plug-confirm" role="alert"><p>Delete the key? Plugins turn off and companions lose your apps. Your apps stay connected in your Composio account, ready if you add a key again.</p>
   <Button size="sm" variant="ghost" onClick={() => setDeleting(false)}>Cancel</Button><Button size="sm" variant="destructive" onClick={() => { send("pluginKeyRemove"); setDeleting(false) }}>Delete key</Button></div>}
 </div>
}

/// Which companions can use something: a chip each, on or off.
export function Who({ what, companions, on, onToggle }: { what: string; companions: Companion[]; on: (m: Companion) => boolean; onToggle: (m: Companion, on: boolean) => void }) {
 return !companions.length ? null : <div className="plug-who" role="group" aria-label={`Who can use ${what}`}>{companions.map(m => {
  const yes = on(m)
  return <button key={m.id} aria-pressed={yes} title={yes ? `${m.name} can use ${what}` : `${m.name} can't use ${what}`} onClick={() => onToggle(m, !yes)}>{yes && <Check />}{m.name}</button>
 })}</div>
}

// Categories people look for first, in this order when Composio has them; the rest follow by size.
const FIRST = ["productivity", "communication", "design", "code", "developer", "finance", "marketing", "sales", "crm"]
const OTHER = "Other"
const catsOf = (a: PluginApp) => a.cats.length ? a.cats : [OTHER]
function categories(apps: PluginApp[]) {
 const size = new Map<string, number>()
 for (const a of apps) for (const c of catsOf(a)) size.set(c, (size.get(c) ?? 0) + 1)
 const rank = (c: string) => { const i = FIRST.findIndex(f => c.toLowerCase().startsWith(f)); return c === OTHER ? 1e6 : i < 0 ? 100 : i }
 return [...size.keys()].sort((a, b) => rank(a) - rank(b) || size.get(b)! - size.get(a)! || a.localeCompare(b))
}

/// One app: its logo and name, with Connect on the right, or a Connected check that opens who can use it.
function AppTile({ app, p, send, open, onOpen }: { app: PluginApp; p?: PluginsState; send: Send; open: boolean; onOpen: () => void }) {
 const on = p?.key && p.connected.some(c => c.slug === app.slug), busy = p?.connecting === app.slug, failed = !busy && p?.failed === app.slug
 const connect = () => {
  if (p?.key) { send("pluginConnect", { slug: app.slug }); return }
  const field = document.querySelector<HTMLInputElement>(".plug-page input[aria-label='Composio API key']")
  field?.scrollIntoView({ block: "center", behavior: "smooth" }); field?.focus()
 }
 return <li className={cn("plug-tile", on && "is-on")} data-slug={app.slug}>
  <PluginLogo slug={app.slug} name={app.name} /><span className="plug-name">{app.name}</span>
  {on ? <button className="plug-done" aria-expanded={open} aria-label={`${app.name} is connected: who can use it`} onClick={onOpen}><Check />Connected</button>
   : <Button size="sm" variant="secondary" className="plug-go" aria-label={`Connect ${app.name}`} disabled={!!p?.connecting} onClick={connect}>{busy && <Loader2 className="animate-spin" />}{busy ? "Connecting…" : failed ? "Try again" : "Connect"}</Button>}
 </li>
}

/// A grid of apps, two across. A connected app's row opens under it: who can use it, and Disconnect.
function Tiles({ apps, ai, send }: { apps: PluginApp[]; ai: AiState; send: Send }) {
 const [open, setOpen] = useState("")
 const p = ai.plugins, account = p?.connected.find(c => c.slug === open)
 const at = apps.findIndex(a => a.slug === open), end = at < 0 ? -1 : Math.min(at | 1, apps.length - 1) // the end of its row
 return <ul className="plug-tiles">{apps.map((a, i) => <Fragment key={a.slug}>
  <AppTile app={a} p={p} send={send} open={open === a.slug} onOpen={() => setOpen(open === a.slug ? "" : a.slug)} />
  {i === end && account && <li className="plug-manage" aria-label={`${account.name}: who can use it`}>
   <Who what={account.name} companions={ai.companions ?? []} on={m => !m.pluginsOff?.includes(account.slug)} onToggle={(m, on) => send("pluginToggle", { companion: m.id, slug: account.slug, on })} />
   <Button size="sm" variant="ghost" onClick={() => { send("pluginDisconnect", { id: account.id }); setOpen("") }}><Unplug />Disconnect</Button></li>}
 </Fragment>)}</ul>
}

function Group({ title, count, onAll, children }: { title: string; count?: number; onAll?: () => void; children: ReactNode }) {
 return <section className="plug-group" aria-label={title}><div className="plug-group-head"><h2>{title}</h2>{onAll && <button className="plug-all" onClick={onAll}>View all{count ? ` ${count}` : ""}</button>}</div>{children}</section>
}

/// The Plugins page (Home.tsx's Skills & plugins): the title with connected apps, one search for apps and skills,
/// category chips (the long tail under More), then Recommended and a section per category. `skills` is the page's
/// skills list, shown with the apps.
export function PluginsPage({ ai, send, skills, onNewSkill }: { ai: AiState; send: Send; skills: (q: string) => ReactNode; onNewSkill: () => void }) {
 const p = ai.plugins, apps = usePluginData(send)
 const [find, setFind] = useState(""), [cat, setCat] = useState(""), [more, setMore] = useState(false)
 useEffect(() => { send("pluginRefresh") }, []) // eslint-disable-line react-hooks/exhaustive-deps
 const known: PluginApp[] = apps.length ? apps : POPULAR.map(([slug, name]) => ({ slug, name, cats: [], auth: "managed" }))
 const cats = apps.length ? categories(apps) : [], shown = 6
 const on = p?.key ? p.connected : [], q = find.trim().toLowerCase()
 const pick = (c: string) => { setCat(c); setFind(""); document.querySelector(".plug-page")?.scrollIntoView({ block: "start" }) }
 const chip = (c: string, label = c) => <button key={c} className="history-chip" aria-pressed={cat === c} onClick={() => pick(c)}>{label}</button>
 const inCat = (c: string) => known.filter(a => catsOf(a).includes(c))
 const hits = q ? known.filter(a => `${a.name} ${a.slug} ${a.cats.join(" ")}`.toLowerCase().includes(q)) : []
 const mine = known.filter(a => on.some(c => c.slug === a.slug)).concat(on.filter(c => !known.some(a => a.slug === c.slug)).map(c => ({ slug: c.slug, name: c.name, cats: [], auth: "managed" as const })))
 return <section className="home-page plug-page" aria-label="Skills & plugins">
  <header className="home-page-head"><h1>Plugins</h1>
   <button className="plug-count" aria-pressed={cat === "connected"} onClick={() => pick(cat === "connected" ? "" : "connected")} aria-label={`${on.length} connected: show them`}><Stack on={on} />{on.length ? `${on.length} connected` : "None connected"}</button>
  </header>
  <label className="history-find"><Search /><input aria-label="Search apps and skills" placeholder="Search apps and skills..." value={find} onChange={e => setFind(e.target.value)} /></label>
  <div className="history-chips" role="group" aria-label="Categories">{chip("", "All")}{cats.slice(0, shown).map(c => chip(c))}
   {cats.indexOf(cat) >= shown && !more && chip(cat)}
   {cats.length > shown && <button className="history-chip" aria-expanded={more} onClick={() => setMore(!more)}>More<ChevronDown className={cn(more && "rotate-180")} /></button>}
   {more && cats.slice(shown).map(c => chip(c))}</div>

  {!p?.key && <div className="plug-connect"><h3>Turn on plugins with your Composio key</h3>
   <p className="plug-note">Companions work in your apps through Composio, with your own project API key. Reading is free. Anything that sends, posts, deletes, pays or changes data asks you first.</p>
   <PluginKey plugins={p} send={send} /><ThirdParty /></div>}
  {p?.key && p.status === "down" && <div className="plug-down" role="alert"><p>Composio isn't answering, so plugins are unavailable right now. Everything else in Still works as usual.</p><Button size="sm" variant="outline" onClick={() => send("pluginRefresh", { force: true })}>Try again</Button></div>}
  {p?.key && p.status === "bad" && <div className="plug-down" role="alert"><p className="plug-error">Composio doesn't accept your key any more. Paste a new project API key (ak_…) in Settings.</p><Button size="sm" variant="outline" onClick={() => send("openPanel", { name: "settings", value: "skills" })}>Change key</Button></div>}
  {p?.error && <p className="plug-error" role="alert">{p.error}</p>}

  {q ? <>
   {skills(q)}
   <Group title="Apps">{hits.length ? <Tiles apps={hits.slice(0, 60)} ai={ai} send={send} /> : <p className="plug-note">No apps match “{find.trim()}”.{!apps.length && " Once your key is in, you can search every app Composio connects."}</p>}
    {hits.length > 60 && <p className="plug-note">Showing 60 of {hits.length}. Keep typing to narrow it down.</p>}</Group>
  </> : cat === "connected" ? <Group title="Connected">{mine.length ? <Tiles apps={mine} ai={ai} send={send} /> : <p className="plug-note">Nothing connected yet. Pick an app and press Connect.</p>}</Group>
  : cat ? <Group title={cat}><Tiles apps={inCat(cat)} ai={ai} send={send} /></Group>
  : <>
   <Group title={apps.length ? "Recommended" : "Apps you can connect"}><Tiles apps={apps.length ? known.filter(a => a.auth !== "custom").slice(0, 8) : known} ai={ai} send={send} /></Group>
   <section className="plug-group" aria-label="Skills"><div className="plug-group-head"><h2>Skills</h2><button className="plug-all" onClick={onNewSkill}>New skill</button></div>{skills("")}</section>
   {cats.map(c => { const all = inCat(c); return <Group key={c} title={c} count={all.length} onAll={all.length > 4 ? () => pick(c) : undefined}><Tiles apps={all.slice(0, 4)} ai={ai} send={send} /></Group> })}
  </>}

  {p?.key && <p className="plug-note plug-foot">Composio key ending in <code className="plug-end">{p.keyEnd}</code>. <a href="#" onClick={e => { e.preventDefault(); send("openPanel", { name: "settings", value: "skills" }) }}>Change or delete it in Settings</a>.</p>}
  {p?.key && <ThirdParty />}
 </section>
}
