import { useState } from "react"
import { Check, KeyRound, Plus, Trash2, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"

type Use = { in: number; out: number; cost: number; calls: number }
type Check = { part: string; ok: boolean; text: string }
export type ApiProvider = {
 id: string; kind: "openai" | "anthropic"; name: string; url: string; models: { id: string; efforts: string[] }[]
 priceIn: number; priceOut: number; limit: number; context: number; noTools: boolean
 hasKey: boolean; keyEnd: string; refused: boolean; month?: Use | null; jobs: Record<string, Use>; paused: boolean
 test?: { model: string; at: string; checks: Check[] } | null
}
export type ApiState = { busy: string; error: string; providers: ApiProvider[] }
type Send = (op: string, payload?: Record<string, unknown>) => void

const KINDS = { openai: "OpenAI-compatible", anthropic: "Anthropic-compatible" }
const JOBS: Record<string, string> = { chats: "chats", titles: "chat titles", setup: "setup", test: "tests" }
const tokens = (n: number) => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1000 ? Math.round(n / 1000) + "k" : String(n)
const money = (n: number) => "$" + (n < 1 ? n.toFixed(4).replace(/0+$/, "").replace(/\.$/, ".00") : n.toFixed(2))
const host = (url: string) => { try { return new URL(url).host } catch { return url } }

// The add and edit form. The key field starts empty: a saved key is never sent back here, only its last four characters.
function Form({ p, send, done }: { p?: ApiProvider; send: Send; done: () => void }) {
 const [kind, setKind] = useState<"openai" | "anthropic">(p?.kind ?? "openai")
 const [name, setName] = useState(p?.name ?? "")
 const [url, setUrl] = useState(p?.url ?? "")
 const [key, setKey] = useState("")
 const [models, setModels] = useState(p?.models.map(m => m.id).join(", ") ?? "")
 const [priceIn, setPriceIn] = useState(p?.priceIn ? String(p.priceIn) : "")
 const [priceOut, setPriceOut] = useState(p?.priceOut ? String(p.priceOut) : "")
 const [limit, setLimit] = useState(p?.limit ? String(p.limit) : "")
 const [context, setContext] = useState(p?.context ? String(p.context) : "")
 const num = (s: string) => { const n = Number(s.trim()); return Number.isFinite(n) && n > 0 ? n : 0 }
 const save = () => {
  send("apiSave", { id: p?.id ?? "", kind, name, url, key, models: models.split(/[\s,]+/).filter(Boolean), priceIn: num(priceIn), priceOut: num(priceOut), limit: num(limit), context: num(context) })
  setKey(""); done()
 }
 return <form className="api-form" onSubmit={e => { e.preventDefault(); save() }}>
  <label><span>Kind</span><Select value={kind} onValueChange={v => setKind(v as "openai" | "anthropic")}><SelectTrigger aria-label="Kind"><SelectValue /></SelectTrigger>
   <SelectContent><SelectItem value="openai">{KINDS.openai} (Chat Completions)</SelectItem><SelectItem value="anthropic">{KINDS.anthropic} (Messages)</SelectItem></SelectContent></Select></label>
  <label><span>Name</span><Input value={name} maxLength={40} placeholder="My provider" onChange={e => setName(e.target.value)} /></label>
  <label><span>Base URL</span><Input value={url} spellCheck={false} placeholder="https://api.example.com/v1" onChange={e => setUrl(e.target.value)} /></label>
  <label><span>API key</span><Input type="password" autoComplete="off" spellCheck={false} value={key} placeholder={p?.hasKey ? `Leave empty to keep the key ending in ${p.keyEnd}` : "Paste your API key"} onChange={e => setKey(e.target.value)} /></label>
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
   <Button size="sm" type="submit" disabled={!name.trim() || !url.trim() || (!p && !key.trim())}>{p ? "Save" : "Add provider"}</Button>
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
 const [sure, setSure] = useState(false)
 if (editing) return <div className="api-card"><Form p={p} send={send} done={() => setEditing(false)} /></div>
 const testing = busy === p.id
 return <div className="api-card">
  <div className="api-head">
   <strong>{p.name}</strong><Badge variant="outline">Compatible</Badge>
   <span className="api-kind">{KINDS[p.kind]} · {host(p.url)}</span>
  </div>
  <div className="api-key"><KeyRound aria-hidden />
   {p.hasKey ? <span>Key ending in <code>{p.keyEnd}</code>{p.refused && <b className="api-bad"> · Not accepted</b>}</span> : <span className="api-bad">No key</span>}
   <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>{p.hasKey ? "Replace" : "Add key"}</Button>
   {p.hasKey && <Button size="sm" variant="ghost" onClick={() => send("apiKeyRemove", { id: p.id })}>Remove</Button>}
  </div>
  <p className="plug-note">{p.models.length ? `${p.models.length} model${p.models.length === 1 ? "" : "s"}: ${p.models.slice(0, 6).map(m => m.id).join(", ")}${p.models.length > 6 ? "…" : ""}` : "No models yet."}
   {p.noTools && " It can chat but can't use your tabs: Test connection found it doesn't call tools."}</p>
  <Spending p={p} />
  <div className="ai-row">
   {p.models.length > 1 && <Select value={model} onValueChange={setModel}><SelectTrigger className="w-48" aria-label="Model to test"><SelectValue /></SelectTrigger>
    <SelectContent>{p.models.map(m => <SelectItem key={m.id} value={m.id}>{m.id}</SelectItem>)}</SelectContent></Select>}
   <Button size="sm" variant="outline" disabled={!!busy || !p.hasKey || !p.models.length} onClick={() => send("apiTest", { id: p.id, model })}>{testing ? <Spinner /> : null}Test connection</Button>
   <Button size="sm" variant="ghost" disabled={!!busy || !p.hasKey} onClick={() => send("apiModels", { id: p.id })}>Load models</Button>
   <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Edit</Button>
   {sure ? <><Button size="sm" variant="destructive" onClick={() => send("apiDelete", { id: p.id })}>Delete {p.name} and its key</Button><Button size="sm" variant="ghost" onClick={() => setSure(false)}>Keep</Button></>
    : <Button size="sm" variant="ghost" aria-label={`Delete ${p.name}`} onClick={() => setSure(true)}><Trash2 /></Button>}
  </div>
  {!testing && p.test && <ul className="api-checks" aria-label={`Test of ${p.test.model}`}>
   {p.test.checks.map(c => <li key={c.part} data-ok={c.ok || undefined}>{c.ok ? <Check aria-label="Passed" /> : <X aria-label="Failed" />}<b>{c.part}</b> {c.text}</li>)}
  </ul>}
 </div>
}

/// Settings → Models → API providers: for people with an API key instead of a plan. Each provider is labelled
/// Compatible: Still checks the formats against its own test server, not against real providers.
export function ApiProviders({ api, send }: { api?: ApiState; send: Send }) {
 const [adding, setAdding] = useState(false)
 const list = api?.providers ?? []
 return <div className="api-providers">
  <p className="plug-note">Use your own API key with a provider that speaks the OpenAI or Anthropic format. It uses your API key and your provider bills you per use. Signing in with a plan doesn't need this. Test connection sends one tiny request, which your provider may bill.</p>
  {api?.error && <p className="api-warn" role="alert">{api.error}</p>}
  {list.map(p => <Provider key={p.id} p={p} busy={api?.busy ?? ""} send={send} />)}
  {adding ? <div className="api-card"><Form send={send} done={() => setAdding(false)} /></div>
   : <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus />Add an API provider</Button>}
 </div>
}
