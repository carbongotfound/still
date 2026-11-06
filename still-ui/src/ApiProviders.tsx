import { useState } from "react"
import { Check, KeyRound, Trash2, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { AiLogo } from "./AiLogo"
import { destroy } from "./Undo"

type Use = { in: number; out: number; cost: number; calls: number }
type Check = { part: string; ok: boolean; text: string }
export type ApiProvider = {
 id: string; kind: "openai" | "anthropic"; name: string; url: string; models: { id: string; efforts: string[] }[]
 priceIn: number; priceOut: number; limit: number; context: number; noTools: boolean
 hasKey: boolean; noKey?: boolean; keyEnd: string; refused: boolean; month?: Use | null; jobs: Record<string, Use>; paused: boolean
 test?: { model: string; at: string; checks: Check[] } | null
}
export type ApiState = { busy: string; error: string; providers: ApiProvider[] }
type Send = (op: string, payload?: Record<string, unknown>) => void

const KINDS = { openai: "OpenAI-compatible", anthropic: "Claude-compatible" }
// Known providers: their address and models filled in, the key still optional. Compatible like any other provider.
export const PRESETS = [{ name: "DeepSeek", kind: "openai" as const, url: "https://api.deepseek.com", models: ["deepseek-flash", "deepseek-v4-pro"], context: 1000000 }]
const JOBS: Record<string, string> = { chats: "chats", titles: "chat titles", setup: "setup", test: "tests" }
const tokens = (n: number) => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1000 ? Math.round(n / 1000) + "k" : String(n)
const money = (n: number) => "$" + (n < 1 ? n.toFixed(4).replace(/0+$/, "").replace(/\.$/, ".00") : n.toFixed(2))
const host = (url: string) => { try { return new URL(url).host } catch { return url } }

// The add and edit form. The key field starts empty: a saved key is never sent back here, only its last four characters.
// start: from the model list's Add, a preset's name to fill in, or "" for any other API; without it the presets are offered.
export function ApiForm({ p, start, send, done }: { p?: ApiProvider; start?: string; send: Send; done: () => void }) {
 const x = p ? undefined : PRESETS.find(x => x.name === start)
 const [kind, setKind] = useState<"openai" | "anthropic">(p?.kind ?? x?.kind ?? "openai")
 const [name, setName] = useState(p?.name ?? x?.name ?? "")
 const [url, setUrl] = useState(p?.url ?? x?.url ?? "")
 const [key, setKey] = useState("")
 const [models, setModels] = useState(p?.models.map(m => m.id).join(", ") ?? x?.models.join(", ") ?? "")
 const [priceIn, setPriceIn] = useState(p?.priceIn ? String(p.priceIn) : "")
 const [priceOut, setPriceOut] = useState(p?.priceOut ? String(p.priceOut) : "")
 const [limit, setLimit] = useState(p?.limit ? String(p.limit) : "")
 const [context, setContext] = useState(p?.context ? String(p.context) : x ? String(x.context) : "")
 const num = (s: string) => { const n = Number(s.trim()); return Number.isFinite(n) && n > 0 ? n : 0 }
 const save = () => {
  send("apiSave", { id: p?.id ?? "", kind, name, url, key, models: models.split(/[\s,]+/).filter(Boolean), priceIn: num(priceIn), priceOut: num(priceOut), limit: num(limit), context: num(context) })
  setKey(""); done()
 }
 return <form className="api-form" onSubmit={e => { e.preventDefault(); save() }}>
  {!p && start === undefined && <div className="api-presets" role="group" aria-label="Start from"><span>Start from</span>{PRESETS.map(x =>
   <Button key={x.name} size="sm" variant="outline" type="button" onClick={() => { setKind(x.kind); setName(x.name); setUrl(x.url); setModels(x.models.join(", ")); setContext(String(x.context)) }}>
    <AiLogo id={x.name} size={16} />{x.name}</Button>)}</div>}
  <label><span>Kind</span><Select value={kind} onValueChange={v => setKind(v as "openai" | "anthropic")}><SelectTrigger aria-label="Kind"><SelectValue /></SelectTrigger>
   <SelectContent><SelectItem value="openai">{KINDS.openai} (Chat Completions)</SelectItem><SelectItem value="anthropic">{KINDS.anthropic} (Anthropic Messages)</SelectItem></SelectContent></Select></label>
  <label><span>Name</span><Input value={name} maxLength={40} placeholder="My provider" onChange={e => setName(e.target.value)} /></label>
  <label><span>Base URL</span><Input value={url} spellCheck={false} placeholder="https://api.example.com/v1" onChange={e => setUrl(e.target.value)} /></label>
  <label><span>API key</span><Input type="password" autoComplete="off" spellCheck={false} value={key} placeholder={p?.hasKey ? `Leave empty to keep the key ending in ${p.keyEnd}` : "Paste your API key, if it needs one"} onChange={e => setKey(e.target.value)} /></label>
  <label><span>Models</span><Input value={models} spellCheck={false} placeholder="Leave empty to load the provider's list" onChange={e => setModels(e.target.value)} /></label>
  <div className="api-pair">
   <label><span>Input price</span><Input inputMode="decimal" value={priceIn} placeholder="$ per million tokens" onChange={e => setPriceIn(e.target.value)} /></label>
   <label><span>Output price</span><Input inputMode="decimal" value={priceOut} placeholder="$ per million tokens" onChange={e => setPriceOut(e.target.value)} /></label>
  </div>
  <div className="api-pair">
   <label><span>Monthly limit</span><Input inputMode="decimal" value={limit} placeholder="$, optional" onChange={e => setLimit(e.target.value)} /></label>
   <label><span>Context size</span><Input inputMode="numeric" value={context} placeholder="tokens, optional" onChange={e => setContext(e.target.value)} /></label>
  </div>
  <p className="plug-note">Prices are only for Still's estimates: your provider's bill is what counts. Still stops a provider for the month once its estimate reaches the limit.</p>
  <div className="ai-row">
   <Button size="sm" type="submit" disabled={!name.trim() || !url.trim()}>{p ? "Save" : "Add provider"}</Button>
   <Button size="sm" variant="ghost" type="button" onClick={done}>Cancel</Button>
  </div>
 </form>
}

function Spending({ p }: { p: ApiProvider }) {
 const order = Object.keys(JOBS), m = p.month, jobs = Object.entries(p.jobs).sort(([a], [b]) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99)) // the Mac sends them unordered
 if (!m) return <p className="plug-note">Nothing used this month yet.</p>
 const of = p.limit > 0 ? ` of your ${money(p.limit)} limit` : ""
 return <div className="api-spend">
  <p>This month: <b>{tokens(m.in)} in, {tokens(m.out)} out</b>{p.priceIn || p.priceOut ? <>, about <b>{money(m.cost)}</b>{of}</> : " (add prices to see an estimate)"}</p>
  {jobs.length > 1 && <p className="plug-note">{jobs.map(([j, u]) => `${JOBS[j] ?? j} ${p.priceIn || p.priceOut ? money(u.cost) : tokens(u.in + u.out) + " tokens"}`).join(" · ")}</p>}
  {p.paused && <p className="api-warn">Paused for this month: the estimate reached your limit. Raise or remove the limit to keep using it.</p>}
 </div>
}

function Provider({ p, busy, send }: { p: ApiProvider; busy: string; send: Send }) {
 const [editing, setEditing] = useState(false)
 const [model, setModel] = useState(p.test?.model || p.models[0]?.id || "")
 if (editing) return <div className="api-card"><ApiForm p={p} send={send} done={() => setEditing(false)} /></div>
 const testing = busy === p.id
 return <div className="api-card">
  <div className="api-head">
   <AiLogo id={p.name} size={18} /><strong>{p.name}</strong><Badge variant="outline">Compatible</Badge>
   <span className="api-kind">{KINDS[p.kind]} · {host(p.url)}</span>
  </div>
  <div className="api-key"><KeyRound aria-hidden />
   {p.hasKey ? <span>Key ending in <code>{p.keyEnd}</code>{p.refused && <b className="api-bad"> · Not accepted</b>}</span> : p.noKey ? <span>No key needed</span> : <span className="api-bad">No key</span>}
   <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>{p.hasKey ? "Replace" : "Add key"}</Button>
   {p.hasKey && <Button size="sm" variant="ghost" onClick={() => destroy({ key: "api-key:" + p.id, title: `Remove the key for ${p.name}?`, body: `The key ending in ${p.keyEnd} is deleted from this computer. ${p.name} stops working until you add one again.`,
    action: "Remove key", done: "Key removed", run: () => send("apiKeyRemove", { id: p.id }) })}>Remove</Button>}
  </div>
  <p className="plug-note">{p.models.length ? `${p.models.length} model${p.models.length === 1 ? "" : "s"}: ${p.models.slice(0, 6).map(m => m.id).join(", ")}${p.models.length > 6 ? "…" : ""}` : "No models yet."}
   {p.noTools && " It can chat but can't use your tabs: Test connection found it doesn't call tools."}</p>
  <Spending p={p} />
  <div className="ai-row">
   {p.models.length > 1 && <Select value={model} onValueChange={setModel}><SelectTrigger className="w-48" aria-label="Model to test"><SelectValue /></SelectTrigger>
    <SelectContent>{p.models.map(m => <SelectItem key={m.id} value={m.id}>{m.id}</SelectItem>)}</SelectContent></Select>}
   <Button size="sm" variant="outline" disabled={!!busy || (!p.hasKey && !p.noKey) || !p.models.length} onClick={() => send("apiTest", { id: p.id, model })}>{testing ? <Spinner /> : null}Test connection</Button>
   <Button size="sm" variant="ghost" disabled={!!busy || (!p.hasKey && !p.noKey)} onClick={() => send("apiModels", { id: p.id })}>Load models</Button>
   <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Edit</Button>
   <Button size="sm" variant="ghost" aria-label={`Delete ${p.name}`} onClick={() => destroy({ key: "api:" + p.id, title: `Delete ${p.name}?`, action: `Delete ${p.name}`, done: `Deleted ${p.name}`,
    body: `${p.name} goes, with ${p.hasKey ? "its key, " : ""}its models and its spending history. Chats that used it stay.`, run: () => send("apiDelete", { id: p.id }) })}><Trash2 /></Button>
  </div>
  {!testing && p.test && <Checks test={p.test} />}
 </div>
}

function Checks({ test }: { test: NonNullable<ApiProvider["test"]> }) {
 return <ul className="api-checks" aria-label={`Test of ${test.model}`}>
  {test.checks.map(c => <li key={c.part} data-ok={c.ok || undefined}>{c.ok ? <Check aria-label="Passed" /> : <X aria-label="Failed" />}<b>{c.part}</b> {c.text}</li>)}
 </ul>
}

/// Setup's short form: a Compatible API by its base URL, one model and a key if it needs one. Test connection saves it
/// (the key goes to the same store as in Settings, and the field empties for good), picks it as the AI and tests it.
export function QuickApi({ api, send }: { api?: ApiState; send: Send }) {
 const [kind, setKind] = useState<"openai" | "anthropic">("openai")
 const [url, setUrl] = useState("")
 const [model, setModel] = useState("")
 const [key, setKey] = useState("")
 const [before, setBefore] = useState<string[] | null>(null) // the providers before the first test: the new one isn't in it
 const [asked, setAsked] = useState<string | null>(null)       // the result on screen when Test connection was pressed
 const p = before ? api?.providers.find(x => !before.includes(x.id)) : undefined
 // Still saves and rechecks the AI apps before it tests, so the old result goes the moment you press it.
 const testing = (asked !== null && !api?.error && (!p?.test || p.test.at === asked)) || (!!p && api?.busy === p.id)
 const name = p?.name || PRESETS.find(x => x.url === url.trim())?.name || (() => { try { return new URL(url.trim()).hostname.replace(/^api\./, "").slice(0, 40) } catch { return "" } })()
 const test = () => {
  if (!before) setBefore(api?.providers.map(x => x.id) ?? [])
  setAsked(p?.test?.at ?? "")
  send("apiSave", { id: p?.id ?? "", kind, name, url, key, models: [model.trim()], test: true, use: true })
  setKey("")
 }
 return <form className="api-form ob-api-form" onSubmit={e => { e.preventDefault(); test() }}>
  <p className="plug-note">For an API that speaks the OpenAI or Claude format, like a local model server. Your provider bills you per use, if it charges. Test connection sends one tiny request.</p>
  <div className="api-presets" role="group" aria-label="Start from"><span>Start from</span>{PRESETS.map(x =>
   <Button key={x.name} size="sm" variant="outline" type="button" onClick={() => { setKind(x.kind); setUrl(x.url); setModel(x.models[0]) }}><AiLogo id={x.name} size={16} />{x.name}</Button>)}</div>
  <label><span>Kind</span><Select value={kind} onValueChange={v => setKind(v as "openai" | "anthropic")}><SelectTrigger aria-label="Kind"><SelectValue /></SelectTrigger>
   <SelectContent><SelectItem value="openai">{KINDS.openai}</SelectItem><SelectItem value="anthropic">{KINDS.anthropic}</SelectItem></SelectContent></Select></label>
  <label><span>Base URL</span><Input value={url} spellCheck={false} placeholder="https://api.example.com/v1" onChange={e => setUrl(e.target.value)} /></label>
  <label><span>Model</span><Input value={model} spellCheck={false} placeholder="The model's name, as your provider writes it" onChange={e => setModel(e.target.value)} /></label>
  <label><span>API key</span><Input type="password" autoComplete="off" spellCheck={false} value={key} placeholder={p?.hasKey ? "Saved. Leave empty to keep it" : "Optional. Leave empty if it doesn't need one"} onChange={e => setKey(e.target.value)} /></label>
  <div className="ai-row">
   <Button size="sm" type="submit" disabled={testing || !!api?.busy || !name || !model.trim()}>{testing ? <Spinner /> : null}Test connection</Button>
   <Badge variant="outline">Compatible</Badge>
  </div>
  {api?.error && <p className="api-warn" role="alert">{api.error}</p>}
  {p && !testing && p.test && <Checks test={p.test} />}
 </form>
}

/// Settings → Models → API providers: for people with an API key instead of a plan. Each provider is labelled
/// Compatible: Still checks the formats against its own test server, not against real providers.
/// Adding one is in Your models, under More agents (DeepSeek or Other compatible API), so it isn't offered twice.
export function ApiProviders({ api, send }: { api?: ApiState; send: Send }) {
 const list = api?.providers ?? []
 return <div className="api-providers">
  <p className="plug-note">Use your own API key with a provider that speaks the OpenAI or Anthropic format. It uses your API key and your provider bills you per use. An AI app you've signed in to doesn't need this. Test connection sends one tiny request, which your provider may bill.</p>
  {api?.error && <p className="api-warn" role="alert">{api.error}</p>}
  {list.map(p => <Provider key={p.id} p={p} busy={api?.busy ?? ""} send={send} />)}
  {!list.length && <p className="plug-note">None added yet. Add one in Your models, under More agents.</p>}
 </div>
}
