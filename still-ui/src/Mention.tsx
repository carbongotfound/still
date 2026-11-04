import type { CSSProperties } from "react"
import { hueOf, lookOf, type Companion } from "./Buddy"
import { avatarOf, useMascotVersion } from "./Mascot"
import { logoOf, plugColor, usePluginData } from "./Plugins"

// Mentions, in the message box and in sent messages: a companion (@), an open tab or a connected app (#) and a skill (/)
// sit inline in the text as an icon and a name. A companion's name is in its own color; the rest are plain text on a soft
// highlight. In the box each one is a single piece: the caret steps over it, Backspace deletes it whole, and copy, paste
// and undo keep it whole. What the AI gets is unchanged: @Name and /skill in the text, a tab's id with the message (Still
// links the tab and has the AI read it), and an app by its name.
export type Mention = { kind: "mate" | "tab" | "plugin" | "skill"; id: string; name: string }
export type Part = string | Mention
type Tab = { id: string; title: string; url: string; favicon?: string; isPrivate?: boolean; chatId?: string; inChat?: string }
export type Known = { companions: Companion[]; tabs: Tab[]; plugins: { slug: string; name: string }[]; skills: { id: string; name: string }[] }

export const said = (m: Mention) => m.kind === "mate" ? "@" + m.name : m.kind === "skill" ? "/" + m.id : m.name
export const textOf = (parts: Part[]) => parts.map(p => typeof p === "string" ? p : said(p)).join("")
export const mentions = (parts: Part[]) => parts.filter((p): p is Mention => typeof p !== "string")
export const hostOf = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url } }
/// A tab the AI may be given: a web page, never a private tab or a chat.
export const shareable = (t: Tab) => !!t.url && !t.isPrivate && !t.chatId && !t.inChat

/// The same thing as it stands now (its current name), or null when it's gone: the companion was deleted, the tab closed,
/// the app disconnected. Anything that isn't a mention (a paste from elsewhere) is null too.
export function live(m: unknown, known: Known): Mention | null {
 const { kind, id } = (m ?? {}) as Partial<Mention>
 if (typeof id !== "string") return null
 const name = kind === "mate" ? known.companions.find(c => c.id === id)?.name
  : kind === "tab" ? (t => t && shareable(t) ? t.title || hostOf(t.url) : undefined)(known.tabs.find(t => t.id === id))
  : kind === "plugin" ? known.plugins.find(p => p.slug === id)?.name
  : kind === "skill" ? known.skills.find(k => k.id === id)?.name : undefined
 return name ? { kind: kind!, id, name } : null
}

const esc = (s: string) => s.replace(/[&<>"']/g, c => "&#" + c.charCodeAt(0) + ";")
/// A tab's title in a mention: at most 10 characters, the ellipsis included; the whole title shows on hover.
export const clip = (title: string) => { const c = [...title]; return c.length > 10 ? c.slice(0, 9).join("").trimEnd() + "…" : title }
// A mention's icon: a companion's 2D face, a tab's favicon, an app's logo (its initial on a tile until the logo is in).
// A tab with no favicon and a skill draw theirs in CSS. Tabs in sent messages are known by their address.
function look(m: Mention, known: Known): { inner: string; hue?: string } {
 const icon = (src?: string) => src ? `<img src="${esc(src)}" alt="" draggable="false">` : "<i></i>"
 if (m.kind === "mate") { const c = known.companions.find(c => c.id === m.id); return { inner: icon(c && avatarOf(lookOf(c), 16)) + esc(m.name), hue: c && hueOf(c) } }
 if (m.kind === "tab") return { inner: icon(known.tabs.find(t => t.id === m.id || t.url === m.id)?.favicon) + esc(clip(m.name)) }
 if (m.kind === "plugin") { const logo = logoOf(m.id); return { inner: (logo ? icon(logo) : `<i>${esc(m.name.charAt(0))}</i>`) + esc(m.name), hue: plugColor(m.id) } }
 return { inner: icon() + esc(m.name) }
}
const mark = (m: Mention, known: Known) => { const l = look(m, known); return { ...l, sig: l.inner + (l.hue ?? "") } }

/// A mention as the message box holds it: one piece the caret can't enter.
export function html(m: Mention, known: Known) {
 const l = mark(m, known)
 return `<span class="mention is-${m.kind}" contenteditable="false" data-mention="${esc(JSON.stringify(m))}" data-sig="${esc(l.sig)}"${l.hue ? ` style="--hue:${esc(l.hue)}"` : ""}${m.kind === "tab" && clip(m.name) !== m.name ? ` title="${esc(m.name)}"` : ""}>${l.inner}</span>`
}
export const markup = (parts: Part[], known: Known) => parts.map(p => typeof p === "string" ? esc(p).replace(/\n/g, "<br>") : html(p, known)).join("")

/// Brings the box's mentions up to date: a picture or a logo that came in later, a style the browser dropped.
export function dress(box: HTMLElement, known: Known) {
 for (const e of box.querySelectorAll<HTMLElement>("[data-mention]")) {
  let m: Mention
  try { m = JSON.parse(e.dataset.mention!) } catch { continue }
  const l = mark(m, known)
  if (e.dataset.sig === l.sig && e.isContentEditable === false) continue
  e.contentEditable = "false"; e.className = "mention is-" + m.kind; e.dataset.sig = l.sig; e.innerHTML = l.inner
  if (l.hue) e.style.setProperty("--hue", l.hue)
 }
}

/// What the box (or a piece of it) says: its text and mentions, in order.
export function read(root: Node): Part[] {
 const out: Part[] = []
 const add = (s: string) => { if (!s) return; if (typeof out.at(-1) === "string") out[out.length - 1] += s; else out.push(s) }
 const walk = (node: Node) => node.childNodes.forEach((n, i) => {
  if (n.nodeType === Node.TEXT_NODE) add(n.textContent!.replace(/ /g, " ").replace(/​/g, ""))
  else if (n instanceof HTMLElement && n.dataset.mention) { try { out.push(JSON.parse(n.dataset.mention)) } catch { add(n.textContent ?? "") } }
  else if (n.nodeName === "BR") add("\n")
  else { if (i > 0 && (n.nodeName === "DIV" || n.nodeName === "P")) add("\n"); walk(n) }
 })
 walk(root)
 return out
}

/// How long some parts are, counted the way the caret moves: a character each, a mention as one.
export const units = (parts: Part[]) => parts.reduce((n, p) => n + (typeof p === "string" ? p.length : 1), 0)
/// The caret n units into the box.
export function caretAt(box: HTMLElement, n: number) {
 const r = document.createRange()
 const walk = (node: Node): boolean => {
  for (const c of node.childNodes) {
   if (c.nodeType === Node.TEXT_NODE) { const l = c.textContent!.length; if (n <= l) { r.setStart(c, n); return true } n -= l }
   else if (c instanceof HTMLElement && c.dataset.mention || c.nodeName === "BR") { if (n === 0) { r.setStartBefore(c); return true } n-- }
   else if (walk(c)) return true
  }
  return false
 }
 if (!walk(box)) r.setStart(box, box.childNodes.length)
 r.collapse(true); getSelection()?.removeAllRanges(); getSelection()?.addRange(r)
}

// A sent message: the text as the AI got it, then the tabs Still linked ("[Title](url)" lines). Its mentions are found
// again: @Name of a companion, /id of a skill, a connected app's name, and each linked tab where its title is in the
// text, or at the end.
const LINKS = /\n\n((?:\[[^\]\n]*\]\([^)\s]+\)(?:\n|$))+)$/
const escRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
export function partsOf(text: string, known: Known): Part[] {
 const links = LINKS.exec(text), body = links ? text.slice(0, links.index) : text
 const words = new Map<string, Mention>()
 for (const c of known.companions) words.set("@" + c.name.toLowerCase(), { kind: "mate", id: c.id, name: c.name })
 for (const k of known.skills) words.set("/" + k.id.toLowerCase(), { kind: "skill", id: k.id, name: k.name })
 for (const p of known.plugins) words.set(p.name.toLowerCase(), { kind: "plugin", id: p.slug, name: p.name })
 const keys = [...words.keys()].filter(Boolean).sort((a, b) => b.length - a.length)
 const parts: Part[] = keys.length ? body.split(new RegExp(`(?<![\\w.@/])(${keys.map(escRe).join("|")})(?![\\w-])`, "i"))
  .map((s, i) => { const m = i % 2 ? words.get(s.toLowerCase()) : undefined; return !m || m.kind === "plugin" && s !== m.name ? s : m }) : [body] // an app only by its exact name
 for (const [, title, url] of links ? links[1].matchAll(/\[([^\]\n]*)\]\(([^)\s]+)\)/g) : []) {
  const tab: Mention = { kind: "tab", id: url, name: title || hostOf(url) }
  const at = parts.findIndex(p => typeof p === "string" && p.includes(tab.name))
  if (at < 0) { parts.push(" ", tab); continue }
  const s = parts[at] as string, i = s.indexOf(tab.name)
  parts.splice(at, 1, s.slice(0, i), tab, s.slice(i + tab.name.length))
 }
 return parts.filter(p => p !== "")
}

export function MentionView({ m, known }: { m: Mention; known: Known }) {
 const l = look(m, known)
 return <span className={"mention is-" + m.kind} title={m.kind === "tab" && clip(m.name) !== m.name ? m.name : undefined} style={l.hue ? { "--hue": l.hue } as CSSProperties : undefined} dangerouslySetInnerHTML={{ __html: l.inner }} />
}
export function MessageText({ text, known }: { text: string; known: Known }) {
 useMascotVersion(); usePluginData() // a companion's picture or an app's logo can come in later
 return <>{partsOf(text, known).map((p, i) => typeof p === "string" ? p : <MentionView key={i} m={p} known={known} />)}</>
}
