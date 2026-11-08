import { useEffect, useState } from "react"
import { KeyRound, Plus, Copy, LogIn, Trash2, RotateCw, Eye, EyeOff, Pencil, Import, Upload, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MAC, cn } from "@/lib/utils"
import type { ToolData } from "./BrowserTools"
import { destroy, isGone, useGone } from "./Undo"
import "./passwords.css"
type Send = (op: string, payload?: Record<string, unknown>) => void
type Ask = (title: string, body: string, run: () => void) => void
export type LoginOffer = { id: string; origin: string; username: string; password?: string; update: boolean }
const host = (origin: string) => { try { return new URL(origin).host } catch { return origin } }

function Secret({ id, value, onChange, label }: { id?: string; value: string; onChange: (v: string) => void; label: string }) {
 const [visible, setVisible] = useState(false)
 return <div className="password-input"><Input id={id} aria-label={label} type={visible ? "text" : "password"} autoComplete="new-password" spellCheck={false} value={value} maxLength={8192} onChange={e => onChange(e.target.value)} />
  <Button type="button" variant="ghost" size="icon" aria-label={visible ? "Hide password" : "Show password"} onClick={() => setVisible(!visible)}>{visible ? <EyeOff /> : <Eye />}</Button></div>
}

/// The bar under the toolbar after you sign in or make an account: check the details, then save.
export function SaveLoginBar({ offer, send }: { offer?: LoginOffer; send: Send }) {
 const [shown, setShown] = useState(offer)
 const [username, setUsername] = useState(offer?.username ?? "")
 const [password, setPassword] = useState(offer?.password ?? "")
 if (offer && offer.id !== shown?.id) { setShown(offer); setUsername(offer.username); setPassword(offer.password ?? "") } // a new offer: no frame with the old one
 useEffect(() => { // once the bar has slid away it holds nothing, and the keyboard can't reach it
  if (offer) return
  const later = setTimeout(() => { setShown(undefined); setUsername(""); setPassword("") }, 400)
  return () => clearTimeout(later)
 }, [offer])
 const site = shown ? host(shown.origin) : ""
 return <div className={cn("permission-wrap", offer && "is-open")} inert={!offer}><form className="permission-bar save-login" role="alertdialog" aria-label={shown?.update ? "Update password" : "Save password"} aria-hidden={!offer}
  onSubmit={e => { e.preventDefault(); if (offer) send("loginAccept", { id: offer.id, username, password }) }}>
  <KeyRound /><span>{shown?.update ? <>Update your password for <b>{site}</b>?</> : <>Save your password for <b>{site}</b>?</>}</span>
  <Input aria-label="Username" placeholder="Username" className="save-login-user" value={username} maxLength={1024} disabled={!offer} onChange={e => setUsername(e.target.value)} />
  <Secret label="Password" value={password} onChange={setPassword} />
  {!shown?.update && <Button type="button" variant="ghost" size="sm" disabled={!offer} onClick={() => offer && send("loginNever", { id: offer.id })}>Never for this site</Button>}
  <Button type="button" variant="ghost" size="sm" disabled={!offer} onClick={() => send("loginDismiss")}>Not now</Button>
  <Button type="submit" size="sm" disabled={!offer || !password}>{shown?.update ? "Update" : "Save"}</Button>
 </form></div>
}

type Entry = NonNullable<ToolData["vault"]>[number]
type Draft = { id: string; origin: string; username: string; password: string }
/// Settings → Passwords. Showing, copying, editing or exporting a password asks for Windows Hello or Touch ID first.
export function PasswordsPane({ data, send, ask, url }: { data: ToolData; send: Send; ask: Ask; url: string }) {
 const [filter, setFilter] = useState("")
 const [draft, setDraft] = useState<Draft | null>(null)
 const [revealed, setRevealed] = useState<Record<string, string>>({})
 const currentOrigin = (() => { try { return new URL(url).origin } catch { return "" } })()
 useEffect(() => {
  const listener = (e: MessageEvent) => {
   const m = e.data
   if (m.kind === "vaultGenerated") setDraft(d => d && { ...d, password: m.password })
   if (m.kind === "vaultSaved") setDraft(null)
   if (m.kind === "vaultRevealed") setRevealed(r => ({ ...r, [m.id]: m.password }))
   if (m.kind === "vaultEditing") setDraft({ id: m.id, origin: m.origin, username: m.username, password: m.password })
  }
  window.chrome?.webview?.addEventListener("message", listener)
  return () => window.chrome?.webview?.removeEventListener("message", listener)
 }, [])
 const options = data.passwordOptions
 const toggle = (feature: "save" | "fill", enabled: boolean) => enabled && feature === "fill"
  ? ask("Turn on auto sign-in?", "When a site has one saved login, Still fills it the first time you click its sign-in field. You still press Sign in yourself.", () => send("passwordPermission", { feature, enabled }))
  : send("passwordPermission", { feature, enabled })
 const words = filter.trim().toLowerCase()
 useGone()
 const shown = (data.vault ?? []).filter(v => !isGone("login:" + v.id) && (v.origin + " " + v.username).toLowerCase().includes(words))
 if (draft) return <form className="vault-form" onSubmit={e => { e.preventDefault(); send("vaultSave", draft) }}>
  <label htmlFor="login-site">Website</label><Input id="login-site" type="url" required placeholder="https://example.com" value={draft.origin} onChange={e => setDraft({ ...draft, origin: e.target.value })} />
  <label htmlFor="login-user">Username or email</label><Input id="login-user" autoComplete="off" value={draft.username} onChange={e => setDraft({ ...draft, username: e.target.value })} />
  <label htmlFor="login-password">Password</label><Secret id="login-password" label="Password" value={draft.password} onChange={password => setDraft({ ...draft, password })} />
  <div className="tool-toolbar"><Button type="button" variant="ghost" onClick={() => send("vaultGenerate")}><RotateCw />Suggest a strong one</Button><span /><Button type="button" variant="ghost" onClick={() => setDraft(null)}>Cancel</Button><Button type="submit">Save</Button></div>
 </form>
 return <>
  <div className="tool-intro"><KeyRound /><p>{MAC ? "Kept in your Mac's Keychain." : "Encrypted by Windows for your account."} Still fills a login only on the site you saved it for, and AIs never see your passwords.</p></div>
  {data.offer && <LoginReview key={data.offer.id} offer={data.offer} send={send} />}
  <div className="password-options">
   <div className="setting-row"><div><strong>Offer to save passwords</strong><p>Still asks after you sign in, make an account or change a password.</p></div><Switch aria-label="Offer to save passwords" checked={!!options?.save} onCheckedChange={v => toggle("save", v)} /></div>
   <div className="setting-row"><div><strong>Auto sign-in</strong><p>Fills your login at your first click in the field when a site has just one saved.</p></div><Switch aria-label="Auto sign-in" checked={!!options?.fill} onCheckedChange={v => toggle("fill", v)} /></div>
  </div>
  <div className="tool-toolbar"><Input aria-label="Search passwords" placeholder="Search passwords" value={filter} onChange={e => setFilter(e.target.value)} />
   <Button variant="outline" onClick={() => setDraft({ id: "", origin: currentOrigin, username: "", password: "" })}><Plus />Add</Button>
   <Button variant="ghost" size="icon-sm" aria-label="Import passwords" title="Import passwords" onClick={() => send("openPanel", { name: "import" })}><Import /></Button>
   <Button variant="ghost" size="icon-sm" aria-label="Export passwords" title="Export passwords" disabled={!data.vault?.length} onClick={() => ask("Export your passwords?", "Still saves them in a CSV file that anyone who opens it can read. Keep it somewhere safe and delete it when you're done.", () => send("vaultExport"))}><Upload /></Button>
  </div>
  <ScrollArea className="tools-list passwords-list">
   {shown.map(v => <Row key={v.id} entry={v} password={revealed[v.id]} here={currentOrigin === v.origin} send={send} hide={() => setRevealed(r => { const { [v.id]: _, ...rest } = r; return rest })} />)}
   {data.vault?.length === 0 && <p className="empty-state">Passwords you save or import show up here.</p>}
   {!!data.vault?.length && shown.length === 0 && <p className="empty-state">No passwords match “{filter}”.</p>}
   {!!data.never?.length && <>
    <div className="tool-section-label">Never saved</div>
    {data.never.map(origin => <div className="tool-row" key={origin}><div className="tool-copy"><strong>{host(origin)}</strong><small>Still won't offer to save passwords here.</small></div><Button variant="ghost" size="icon-sm" aria-label={"Offer again on " + host(origin)} title="Offer again" onClick={() => send("neverRemove", { origin })}><X /></Button></div>)}
   </>}
  </ScrollArea>
 </>
}

function Row({ entry: v, password, here, send, hide }: { entry: Entry; password?: string; here: boolean; send: Send; hide: () => void }) {
 return <div className="tool-row password-row">
  <KeyRound />
  <div className="tool-copy"><strong>{host(v.origin)}</strong><small>{v.username || "No username"}</small>
   {password !== undefined && <code className="password-shown">{password}</code>}
   {(v.weak || v.reused) && <span className="password-flags">{v.weak && <Badge variant="destructive" title="Short or easy to guess. Change it on the site, then update it here.">Weak</Badge>}{v.reused && <Badge variant="secondary" title="You use this password on more than one site. If one leaks, the others are at risk.">Reused</Badge>}</span>}
  </div>
  <Button variant="ghost" size="icon-sm" aria-label={(password !== undefined ? "Hide" : "Show") + " password for " + host(v.origin)} onClick={() => password !== undefined ? hide() : send("vaultReveal", { id: v.id })}>{password !== undefined ? <EyeOff /> : <Eye />}</Button>
  <Button variant="ghost" size="icon-sm" aria-label={"Copy password for " + host(v.origin)} onClick={() => send("vaultCopy", { id: v.id })}><Copy /></Button>
  <Button variant="ghost" size="icon-sm" aria-label={"Edit login for " + host(v.origin)} onClick={() => send("vaultEdit", { id: v.id })}><Pencil /></Button>
  {here && <Button variant="ghost" size="icon-sm" aria-label={"Fill login for " + host(v.origin)} onClick={() => send("vaultFill", { id: v.id })}><LogIn /></Button>}
  <Button variant="ghost" size="icon-sm" aria-label={"Delete login for " + host(v.origin)} onClick={() => destroy({ key: "login:" + v.id, title: "Delete this login?", body: (v.username || "The login") + " on " + host(v.origin) + " is removed from Still, with its saved password.", action: "Delete login", done: "Login deleted", run: () => send("vaultDelete", { id: v.id }) })}><Trash2 /></Button>
 </div>
}

function LoginReview({ offer, send }: { offer: LoginOffer; send: Send }) {
 const [username, setUsername] = useState(offer.username)
 const [password, setPassword] = useState(offer.password ?? "")
 return <form className="extension-review login-review" onSubmit={e => { e.preventDefault(); send("loginAccept", { id: offer.id, username, password }) }}>
  <strong>{offer.update ? "Update your saved password?" : "Save this login?"}</strong><p>{host(offer.origin)}</p>
  <div className="vault-form"><Input aria-label="Username" value={username} maxLength={1024} onChange={e => setUsername(e.target.value)} /><Secret label="Password" value={password} onChange={setPassword} /></div>
  <div className="tool-toolbar">{!offer.update && <Button type="button" variant="ghost" onClick={() => send("loginNever", { id: offer.id })}>Never for this site</Button>}<span /><Button type="button" variant="ghost" onClick={() => send("loginDismiss")}>Not now</Button><Button type="submit" disabled={!password}>{offer.update ? "Update" : "Save"}</Button></div>
 </form>
}
