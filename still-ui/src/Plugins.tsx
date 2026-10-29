import { useEffect, useState, type CSSProperties } from "react"
import { Check, Loader2, Search, Unplug } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import type { AiState } from "./AiSidebar"
import { BODY_COLORS } from "./look"

// Plugins: the user's apps through Composio, a third-party service, with their own API key (MainWindow.Plugins.cs and
// Plugins.swift). The key goes in here once and never comes back: the shell only hears whether there is one.
type Send = (op: string, payload?: Record<string, unknown>) => void
export type PluginsState = {
 key: boolean; status: "off" | "checking" | "ok" | "bad" | "down"; connecting: string
 found: { slug: string; name: string; about: string }[]; connected: { id: string; slug: string; name: string }[]
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
const KEY_URL = "key", PRICING_URL = "pricing"

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

/// Paste the key once. It's checked with Composio and kept like saved passwords; the field empties right away.
export function PluginKey({ plugins, send }: { plugins?: PluginsState; send: Send }) {
 const [key, setKey] = useState("")
 const checking = plugins?.status === "checking"
 return <form className="plug-key" onSubmit={e => { e.preventDefault(); if (key.trim().length >= 8) { send("pluginKey", { key: key.trim() }); setKey("") } }}>
  <div className="plug-key-row">
   <Input type="password" autoComplete="off" spellCheck={false} aria-label="Composio API key" placeholder="Paste your Composio API key" value={key} onChange={e => setKey(e.target.value)} />
   <Button type="submit" size="sm" disabled={key.trim().length < 8 || checking}>{checking && <Loader2 className="animate-spin" />}Turn on plugins</Button>
  </div>
  {plugins?.status === "bad" && <p className="plug-error" role="alert">Composio didn't accept that key. Check it and paste it again.</p>}
  {plugins?.status === "down" && <p className="plug-error" role="alert">Composio isn't answering right now. Try again in a little while.</p>}
  <p className="plug-note">Your key is encrypted on this computer, like your passwords, and AI never sees it. <a href="#" onClick={e => { e.preventDefault(); send("pluginLink", { to: KEY_URL }) }}>Get a key</a></p>
 </form>
}

export function ThirdParty({ send }: { send: Send }) {
 return <p className="plug-note">Composio is a third-party service with its own <a href="#" onClick={e => { e.preventDefault(); send("pluginLink", { to: PRICING_URL }) }}>pricing and terms</a>. Still only talks to it with your key, when you connect or use an app.</p>
}

/// Settings → Plugins.
export function PluginsSettings({ ai, send }: { ai: AiState; send: Send }) {
 const p = ai.plugins, companions = ai.companions ?? []
 const [query, setQuery] = useState("")
 const ready = !!p?.key && p.status === "ok"
 useEffect(() => { send("pluginRefresh") }, []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { if (!ready) return; const t = setTimeout(() => send("pluginSearch", { query }), query ? 300 : 0); return () => clearTimeout(t) }, [query, ready]) // eslint-disable-line react-hooks/exhaustive-deps
 return <div className="plug-settings">
  <p className="tool-caption">Let your companions work in your apps, like Gmail, Calendar, Slack and Notion. Reading is free. Anything that sends, posts, deletes, pays or changes data asks you first.</p>
  {!p?.key ? <><PluginKey plugins={p} send={send} /><ThirdParty send={send} /></> : <>
   {p.status === "checking" && <p className="plug-note"><Loader2 className="animate-spin" />Checking your key…</p>}
   {p.status === "down" && <div className="plug-down" role="alert"><p>Composio isn't answering, so plugins are unavailable right now. Everything else in Still works as usual.</p><Button size="sm" variant="outline" onClick={() => send("pluginRefresh")}>Try again</Button></div>}
   {p.connected.length > 0 && <section className="plug-section"><h4>Connected</h4>
    <ul className="plug-list">{p.connected.map(c => <li key={c.id}>
     <PluginChip slug={c.slug} name={c.name} />
     {companions.length > 0 && <div className="plug-who" role="group" aria-label={`Who can use ${c.name}`}>{companions.map(m => {
      const on = !m.pluginsOff?.includes(c.slug)
      return <button key={m.id} aria-pressed={on} title={on ? `${m.name} can use ${c.name}` : `${m.name} can't use ${c.name}`} onClick={() => send("pluginToggle", { companion: m.id, slug: c.slug, on: !on })}>{on && <Check />}{m.name}</button>
     })}</div>}
     <Button size="sm" variant="ghost" onClick={() => send("pluginDisconnect", { id: c.id })}><Unplug />Disconnect</Button>
    </li>)}</ul>
   </section>}
   {ready && <section className="plug-section"><h4>Add an app</h4>
    <div className="plug-search"><Search /><Input aria-label="Find an app" placeholder="Find an app" value={query} onChange={e => setQuery(e.target.value)} /></div>
    <ul className="plug-list is-found">{p.found.map(f => {
     const on = p.connected.some(c => c.slug === f.slug), busy = p.connecting === f.slug
     return <li key={f.slug}><PluginChip slug={f.slug} name={f.name} /><small>{f.about}</small>
      {on ? <span className="plug-on"><Check />Connected</span> : <Button size="sm" variant="outline" disabled={!!p.connecting} onClick={() => send("pluginConnect", { slug: f.slug })}>{busy && <Loader2 className="animate-spin" />}{busy ? "Connecting…" : "Connect"}</Button>}
     </li>
    })}</ul>
    {!p.found.length && <p className="plug-note">{query ? `No apps match “${query}”.` : "Loading apps…"}</p>}
   </section>}
   <Separator />
   <div className="setting-row"><div><strong>Composio API key</strong><p>Remove it to turn plugins off. Your apps stay connected in your Composio account.</p></div><Button size="sm" variant="outline" onClick={() => send("pluginKeyRemove")}>Remove key</Button></div>
   <ThirdParty send={send} />
  </>}
 </div>
}
