import { useEffect, useState, type CSSProperties } from "react"
import { Check, Loader2, Unplug } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import type { AiState } from "./AiSidebar"
import type { Companion } from "./Buddy"
import { BODY_COLORS } from "./look"

// Plugins: the user's apps through Composio, a third-party service, with their own project API key (MainWindow.Plugins.cs
// and Plugins.swift). The key goes in here once and never comes back: the shell only hears whether there is one.
type Send = (op: string, payload?: Record<string, unknown>) => void
export type PluginsState = {
 key: boolean; status: "off" | "checking" | "ok" | "bad" | "kind" | "down"; connecting: string; failed?: string; error?: string
 found: { slug: string; name: string; about: string }[] | null; connected: { id: string; slug: string; name: string }[]
}
// The apps people connect most (Composio toolkit slugs), for setup's belt and the Hire cards. Names only: no logos.
export const POPULAR: [string, string][] = [
 ["gmail", "Gmail"], ["googlecalendar", "Google Calendar"], ["slack", "Slack"], ["notion", "Notion"], ["github", "GitHub"], ["googledrive", "Google Drive"],
 ["linear", "Linear"], ["hubspot", "HubSpot"], ["googlesheets", "Google Sheets"], ["googledocs", "Google Docs"], ["outlook", "Outlook"], ["jira", "Jira"],
 ["asana", "Asana"], ["trello", "Trello"], ["airtable", "Airtable"], ["salesforce", "Salesforce"], ["zoom", "Zoom"], ["figma", "Figma"],
 ["dropbox", "Dropbox"], ["calendly", "Calendly"], ["zendesk", "Zendesk"], ["intercom", "Intercom"], ["linkedin", "LinkedIn"], ["stripe", "Stripe"],
]
export const pluginName = (slug: string) => POPULAR.find(p => p[0] === slug)?.[1] ?? slug.charAt(0).toUpperCase() + slug.slice(1)
export const andList = (names: string[]) => names.length < 2 ? names.join("") : names.slice(0, -1).join(", ") + " and " + names.at(-1)

/// A clean name chip: the app's initial on a soft tile, then its name.
export function PluginChip({ slug, name, hidden }: { slug: string; name: string; hidden?: boolean }) {
 const hue = BODY_COLORS[[...slug].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) % 997, 7) % BODY_COLORS.length][0]
 return <span className="plug-chip" aria-hidden={hidden} style={{ "--hue": hue } as CSSProperties}><i aria-hidden>{name.charAt(0)}</i>{name}</span>
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

/// Where the key comes from, then paste it once. It's checked with Composio and kept like saved passwords; the field
/// empties right away. Composio's For You page shows a Connect key (ck_…) that its API refuses: the steps point past it.
export function PluginKey({ plugins, send }: { plugins?: PluginsState; send: Send }) {
 const [key, setKey] = useState("")
 const checking = plugins?.status === "checking"
 return <form className="plug-key" onSubmit={e => { e.preventDefault(); if (key.trim().length >= 8) { send("pluginKey", { key: key.trim() }); setKey("") } }}>
  <ol className="plug-steps">
   <li><a href="#" onClick={e => { e.preventDefault(); send("pluginLink", { to: "key" }) }}>Get a key</a>: Composio opens in a new window.</li>
   <li>There, switch to <b>Platform</b> and open <b>Settings → Project Settings → API Keys</b>.</li>
   <li>Copy the project API key, which starts with <code>ak_</code>, and paste it here.</li>
  </ol>
  <div className="plug-key-row">
   <Input type="password" autoComplete="off" spellCheck={false} aria-label="Composio API key" placeholder="Paste your Composio API key" value={key} onChange={e => setKey(e.target.value)} />
   <Button type="submit" size="sm" disabled={key.trim().length < 8 || checking}>{checking && <Loader2 className="animate-spin" />}Turn on plugins</Button>
  </div>
  {plugins?.status === "bad" && <p className="plug-error" role="alert">Composio didn't accept that key. Check it and paste it again: Still needs the project API key that starts with ak_.</p>}
  {plugins?.status === "kind" && <p className="plug-error" role="alert">That's a Composio Connect key (ck_…) or a personal key (uak_…), and Composio only lets apps like Still in with a project API key. Paste the one that starts with ak_, from Platform → Settings → Project Settings.</p>}
  {plugins?.status === "down" && <p className="plug-error" role="alert">Composio isn't answering right now. Try again in a little while.</p>}
  <p className="plug-note">Your key is encrypted on this computer, like your passwords, and AI never sees it.</p>
 </form>
}

export function ThirdParty() {
 return <p className="plug-note">Composio is a third-party service. Still only talks to it with your key, when you connect or use an app.</p>
}

/// Which companions can use something: a chip each, on or off.
export function Who({ what, companions, on, onToggle }: { what: string; companions: Companion[]; on: (m: Companion) => boolean; onToggle: (m: Companion, on: boolean) => void }) {
 return !companions.length ? null : <div className="plug-who" role="group" aria-label={`Who can use ${what}`}>{companions.map(m => {
  const yes = on(m)
  return <button key={m.id} aria-pressed={yes} title={yes ? `${m.name} can use ${what}` : `${m.name} can't use ${what}`} onClick={() => onToggle(m, !yes)}>{yes && <Check />}{m.name}</button>
 })}</div>
}

/// Skills & plugins' plugin half (Home.tsx). No key: the step that turns them on, over the apps it opens up. With one:
/// connected apps with who can use each, then what Composio can sign in to. `query` is the page's search.
export function PluginsSection({ ai, send, query }: { ai: AiState; send: Send; query: string }) {
 const p = ai.plugins, companions = ai.companions ?? []
 const ready = !!p?.key && p.status === "ok", q = query.trim()
 const match = (name: string) => name.toLowerCase().includes(q.toLowerCase())
 useEffect(() => { send("pluginRefresh") }, []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { if (!ready) return; const t = setTimeout(() => send("pluginSearch", { query: q }), q ? 300 : 0); return () => clearTimeout(t) }, [q, ready]) // eslint-disable-line react-hooks/exhaustive-deps
 const connected = (p?.connected ?? []).filter(c => match(c.name)), popular = POPULAR.filter(([, name]) => match(name))
 return <div className="plug-settings">
  {!p?.key ? <>
   <div className="plug-connect"><h3>Turn on plugins with your Composio key</h3>
    <p className="plug-note">Companions work in your apps through Composio, with your own project API key. Reading is free. Anything that sends, posts, deletes, pays or changes data asks you first.</p>
    <PluginKey plugins={p} send={send} /><ThirdParty /></div>
   <section className="plug-section"><h4>Apps you can connect</h4>
    <ul className="plug-list is-preview">{popular.map(([slug, name]) => <li key={slug}><PluginChip slug={slug} name={name} /><span className="plug-on is-off">Needs a key</span></li>)}</ul>
    {!popular.length && <p className="plug-note">No apps match “{q}”. Once your key is in, you can search every app Composio connects.</p>}
   </section>
  </> : <>
   {p.status === "checking" && <p className="plug-note"><Loader2 className="animate-spin" />Checking your key…</p>}
   {p.status === "down" && <div className="plug-down" role="alert"><p>Composio isn't answering, so plugins are unavailable right now. Everything else in Still works as usual.</p><Button size="sm" variant="outline" onClick={() => send("pluginRefresh")}>Try again</Button></div>}
   {p.status === "bad" && <p className="plug-error" role="alert">Composio doesn't accept your key any more. Remove it and paste a new project API key (ak_…).</p>}
   {p.error && <p className="plug-error" role="alert">{p.error}</p>}
   {connected.length > 0 && <section className="plug-section"><h4>Connected</h4>
    <ul className="plug-list">{connected.map(c => <li key={c.id}>
     <PluginChip slug={c.slug} name={c.name} /><span className="plug-on"><Check />Connected</span>
     <Who what={c.name} companions={companions} on={m => !m.pluginsOff?.includes(c.slug)} onToggle={(m, on) => send("pluginToggle", { companion: m.id, slug: c.slug, on })} />
     <Button size="sm" variant="ghost" onClick={() => send("pluginDisconnect", { id: c.id })}><Unplug />Disconnect</Button>
    </li>)}</ul>
   </section>}
   {ready && <section className="plug-section"><h4>Add an app</h4>
    <ul className="plug-list is-found">{(p.found ?? []).map(f => {
     const on = p.connected.some(c => c.slug === f.slug), busy = p.connecting === f.slug, failed = !busy && p.failed === f.slug
     return <li key={f.slug}><PluginChip slug={f.slug} name={f.name} /><small>{f.about}</small>
      {on ? <span className="plug-on"><Check />Connected</span> : <>
       <span className={cn("plug-on", failed ? "is-error" : "is-off")}>{failed ? "Didn't connect" : "Needs sign-in"}</span>
       <Button size="sm" variant="outline" disabled={!!p.connecting} onClick={() => send("pluginConnect", { slug: f.slug })}>{busy && <Loader2 className="animate-spin" />}{busy ? "Connecting…" : failed ? "Try again" : "Connect"}</Button></>}
     </li>
    })}</ul>
    {!p.found?.length && !p.error && <p className="plug-note">{!p.found ? "Loading apps…" : q ? `No apps match “${q}”.` : "Composio didn't list any apps for this key."}</p>}
   </section>}
   <Separator />
   <div className="setting-row"><div><strong>Composio API key</strong><p>Remove it to turn plugins off. Your apps stay connected in your Composio account.</p></div><Button size="sm" variant="outline" onClick={() => send("pluginKeyRemove")}>Remove key</Button></div>
   <ThirdParty />
  </>}
 </div>
}
