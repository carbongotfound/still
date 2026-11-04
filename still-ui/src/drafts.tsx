import { useLayoutEffect, useRef, useState } from "react"
import { MAC } from "@/lib/utils"
import { read, textOf, units, type Part } from "./Mention"
import type { Attached } from "./AiSidebar"

// Drafts: what was typed in a box and not sent, per box (its key: "home", "chat.<id>", "answer.<chat>" and so on).
// Still keeps them in files in the profile (ai/drafts), so they're back after a refresh, a crash or a restart. Never a
// private window's (kept here in memory while it's open), and none at all with Settings > Save drafts off. Another
// window's New Tab box ("window.home") lasts while that window is open. One not touched for 7 days is dropped.
export type Step = { v: Part[] | string; c: number; t?: number; k?: string }
export type Draft = { at?: number; text: string; parts?: Part[]; files?: Attached[]; steps?: Step[]; step?: number }
const WEEK = 7 * 86400000
let saving = true, privateWindow = false
const kept = new Map<string, Draft>()
const post = (op: string, o: object) => window.chrome?.webview?.postMessage({ op, ...o })
const memoryOnly = (key: string) => privateWindow || key.startsWith("private.")
const inWindow = (key: string) => key.startsWith("window.")

export function readDraft(key?: string): Draft | null {
 if (!key || !saving) return null
 let d = kept.get(key) ?? null
 if (!d && inWindow(key)) try { d = JSON.parse(sessionStorage.getItem("still.draft." + key) ?? "null") } catch { /* storage unavailable */ }
 return d && !(d.at && Date.now() - d.at > WEEK) ? d : null
}

/// Keeps what a box holds now, with its undo steps; null forgets it. An empty box keeps only its steps, if it has any.
export function keepDraft(key: string | undefined, d: Draft | null) {
 if (!key || !saving) return
 const h = histories.get(key), empty = !d || !d.text.trim() && !d.files?.length
 const full: Draft | null = !d || empty && (h?.steps.length ?? 0) < 2 ? null : { ...d, at: Date.now(), ...(h && { steps: h.steps, step: h.at }) }
 if (full) kept.set(key, full); else kept.delete(key)
 if (memoryOnly(key)) return
 if (inWindow(key)) { try { if (full) sessionStorage.setItem("still.draft." + key, JSON.stringify(full)); else sessionStorage.removeItem("still.draft." + key) } catch { /* storage unavailable */ } return }
 post("draftSave", { key, draft: full })
}

/// What Still kept, sent when the interface loads. Drafts this interface kept itself before 2.10 move to Still.
export function takeDrafts(data: Record<string, Draft>) {
 kept.clear()
 for (const [k, d] of Object.entries(data ?? {})) if (d && typeof d.text === "string") kept.set(k, d)
 try {
  for (const k of Object.keys(localStorage)) if (k.startsWith("still.draft.")) {
   const key = k.slice(12), raw = localStorage.getItem(k) ?? ""
   localStorage.removeItem(k)
   if (kept.has(key) || !saving || privateWindow) continue
   let d: Draft = { text: raw }
   try { const j = JSON.parse(raw); if (j && typeof j === "object" && !Array.isArray(j)) d = { ...j, text: j.text ?? "" } } catch { /* plain text */ }
   if (d.at && Date.now() - d.at > WEEK) continue
   kept.set(key, d); post("draftSave", { key, draft: d })
  }
 } catch { /* storage unavailable */ }
}

/// Settings > Save drafts, and whether this is a private window. Off forgets every draft here (Still deletes its files).
export function draftSettings(on: boolean, incognito: boolean) {
 privateWindow = incognito
 if (saving && !on) {
  kept.clear()
  try { for (const k of Object.keys(sessionStorage)) if (k.startsWith("still.draft.")) sessionStorage.removeItem(k) } catch { /* storage unavailable */ }
 }
 saving = on
}

// Sending: the draft stays until Still says it took the message, so a send that fails (or a crash before) keeps it.
const inflight = new Map<string, number | undefined>()
export function sending(key: string | undefined) { if (key) inflight.set(key, readDraft(key)?.at) }
/// Still's answer to a send: taken, so the draft goes (unless more was typed since), or not, so the text comes back.
export function sent(key: string, ok: boolean) {
 const at = inflight.get(key); inflight.delete(key)
 if (ok) { if (readDraft(key)?.at === at) { keepDraft(key, null); histories.delete(key) } return }
 const el = document.querySelector<HTMLElement>(`[data-history="${CSS.escape(key)}"]`), v = el && snap(el).v
 if (el && !(typeof v === "string" ? v : textOf(v ?? [])).trim()) move(el, -1) // the box Send emptied: back as it was
 dispatchEvent(new CustomEvent("still-unsent", { detail: key }))
}

// Undo and redo in every text box (Ctrl+Z, Ctrl+Shift+Z, and Ctrl+Y on Windows; Cmd on the Mac), step by step: typing
// runs together until a pause or a new word; a paste, a cut, a drop, a deleted selection, Still filling or emptying the
// box (a draft coming back, Discard, Send) are a step each. A box with a key (data-history) keeps its steps when it goes
// (switching chats or tabs), and with its draft through a restart: the last 50.
type History = { steps: Step[]; at: number }
const histories = new Map<string, History>(), unkeyed = new WeakMap<Element, History>()
/// How a box other than a plain input puts a step back (the message box, with its mentions).
export const appliers = new WeakMap<Element, (s: Step) => void>()
const MAX = 50, SIZE = 400000, MERGE_MS = 1000
let applying = false, next = ""

const isField = (el: Element): el is HTMLInputElement | HTMLTextAreaElement => el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement
function boxOf(t: EventTarget | null) {
 const el = t instanceof Element ? t.closest<HTMLElement>("[data-history], input, textarea") : null
 if (!el || el instanceof HTMLInputElement && (!/^(text|search|url|email|tel)$/.test(el.type) || /password|one-time-code/.test(el.autocomplete))) return null // never a password, even one shown
 return isField(el) || el.isContentEditable ? el : null
}
function snap(el: HTMLElement): Step {
 if (isField(el)) return { v: el.value, c: el.selectionEnd ?? el.value.length }
 const s = getSelection(), r = document.createRange()
 let c = units(read(el))
 if (s?.focusNode && el.contains(s.focusNode)) { r.setStart(el, 0); r.setEnd(s.focusNode, s.focusOffset); c = units(read(r.cloneContents())) }
 return { v: read(el), c }
}
const same = (a: Step, b: Step) => JSON.stringify(a.v) === JSON.stringify(b.v)
const historyOf = (el: HTMLElement) => el.dataset.history ? histories.get(el.dataset.history) : unkeyed.get(el)
function start(el: HTMLElement) {
 let h = historyOf(el)
 if (!h) { h = { steps: [snap(el)], at: 0 }; if (el.dataset.history) histories.set(el.dataset.history, h); else unkeyed.set(el, h) }
 return h
}
function push(h: History, s: Step) {
 h.steps.splice(h.at + 1, Infinity, { ...s, t: Date.now() })
 let size = JSON.stringify(h.steps).length
 while (h.steps.length > 1 && (h.steps.length > MAX + 1 || size > SIZE)) size -= JSON.stringify(h.steps.shift()).length
 h.at = h.steps.length - 1
}
/// Whatever changed the box without typing (Still filled or emptied it) becomes a step before the next one.
export function settle(el: HTMLElement) {
 const h = start(el), now = snap(el)
 if (!same(now, h.steps[h.at])) push(h, { ...now, k: "set" })
 return h
}
function apply(el: HTMLElement, s: Step) {
 applying = true
 try {
  if (isField(el)) {
   Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value")?.set?.call(el, s.v)
   if (document.activeElement === el) el.setSelectionRange(s.c, s.c)
  } else if (appliers.get(el)) appliers.get(el)!(s)
  else el.textContent = typeof s.v === "string" ? s.v : textOf(s.v)
  el.dispatchEvent(new Event("input", { bubbles: true })) // the box's own handlers see the change
 } finally { applying = false }
}
function move(el: HTMLElement, by: number) {
 const h = settle(el), to = h.at + by
 if (to < 0 || to >= h.steps.length) return
 h.at = to; apply(el, h.steps[to])
}
/// Puts new contents in a box as one step to undo (Discard, a draft coming back).
export function change(el: HTMLElement, v: Part[] | string) { settle(el); apply(el, { v, c: typeof v === "string" ? v.length : units(v) }); settle(el) }
/// A new chat's box got the chat's key: its steps go with it.
export function rekey(was: string, now: string) { const h = histories.get(was); if (h) { histories.delete(was); histories.set(now, h) } }
/// A box (data-history) showing what was kept under its key: its steps come back too. The memory of this run wins.
export function adopt(key: string, el: HTMLElement, d: Draft | null) {
 let h = histories.get(key)
 if (!h && d?.steps?.length) h = { steps: d.steps, at: Math.max(0, Math.min(d.step ?? d.steps.length - 1, d.steps.length - 1)) }
 if (!h) return void histories.set(key, { steps: [snap(el)], at: 0 })
 histories.set(key, h)
 const now = snap(el)
 if (same(now, h.steps[h.at])) return
 if (h.at > 0 && same(now, h.steps[h.at - 1])) h.at-- // back where it was a step ago (a send that didn't go)
 else push(h, { ...now, k: "set" })
}

const before = (el: HTMLElement, kind: string) => { if (!applying) { settle(el); next = kind } }
const collapsed = (el: HTMLElement) => isField(el) ? el.selectionStart === el.selectionEnd : getSelection()?.isCollapsed !== false
document.addEventListener("keydown", e => {
 const el = boxOf(e.target); if (!el || e.isComposing) return
 const letter = /^[a-z]$/i.test(e.key) ? e.key.toLowerCase() : e.code.replace(/^Key/, "").toLowerCase()
 const mod = MAC ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey
 if (mod && !e.altKey && (letter === "z" || !MAC && letter === "y" && !e.shiftKey)) { e.preventDefault(); e.stopImmediatePropagation(); move(el, letter === "z" && !e.shiftKey ? -1 : 1); return }
 next = ""
 if (!applying) settle(el)
}, true)
// The Mac's Edit > Undo and Redo (the menu, not Cmd+Z): a step in the focused box, if it's one of these.
;(window as unknown as { __stillHistory?: (by: number) => boolean }).__stillHistory = by => { const el = boxOf(document.activeElement); if (!el) return false; move(el, by); return true }
document.addEventListener("focusin", e => { const el = boxOf(e.target); if (el && !applying) settle(el) }, true)
for (const kind of ["paste", "cut", "drop"]) document.addEventListener(kind, e => { const el = boxOf(e.target); if (el) before(el, kind) }, true)
document.addEventListener("beforeinput", e => {
 const el = boxOf(e.target); if (!el) return
 if (e.inputType === "historyUndo" || e.inputType === "historyRedo") { e.preventDefault(); move(el, e.inputType === "historyUndo" ? -1 : 1); return } // Edit > Undo on the Mac
 const plain = collapsed(el)
 before(el, next || (/^insert(Text|CompositionText)$/.test(e.inputType) && plain ? "type" : /^delete(Content|Word)/.test(e.inputType) && plain ? "delete" : e.inputType))
}, true)
document.addEventListener("input", e => {
 const el = boxOf(e.target); if (!el) return
 if (!applying) {
  const h = start(el), now: Step = { ...snap(el), t: Date.now(), k: next || "set" }, top = h.steps[h.at], word = /^\s/.test((e as InputEvent).data ?? "")
  next = ""
  if (!same(now, top)) {
   if (h.at > 0 && h.at === h.steps.length - 1 && top.k === now.k && (now.k === "type" && !word || now.k === "delete") && now.t! - (top.t ?? 0) < MERGE_MS) h.steps[h.at] = now
   else push(h, now)
  }
 }
 if (el.dataset.draft !== undefined && el.dataset.history) later(el.dataset.history, el)
}, true)

// A plain box's draft (data-draft): saved a moment after the last change, and at once on leaving the box or Still.
const timers = new Map<string, { id: number; run: () => void }>()
function later(key: string, el: HTMLElement) {
 cancel(key)
 const run = () => { timers.delete(key); keepDraft(key, { text: isField(el) ? el.value : textOf(read(el)) }) }
 timers.set(key, { id: window.setTimeout(run, 500), run })
}
function cancel(key: string) { const t = timers.get(key); if (t) clearTimeout(t.id); timers.delete(key) }
const flushAll = () => { for (const t of [...timers.values()]) { clearTimeout(t.id); t.run() } }
addEventListener("beforeunload", flushAll)
document.addEventListener("focusout", e => { const el = boxOf(e.target); const t = el?.dataset.history && timers.get(el.dataset.history); if (t) { clearTimeout(t.id); t.run() } }, true)

/// Shown when a box came back with what was typed before.
export const DraftHint = ({ onDiscard }: { onDiscard: () => void }) => <div className="draft-hint" role="status">Draft restored
 <button type="button" onMouseDown={e => e.preventDefault()} onClick={onDiscard}>Discard</button></div>

/// A plain box (input or textarea) that keeps a draft under `key`: spread `props` on it, show `hint`, call `done` once
/// what's in it is sent. Its draft comes back when it shows, with the Draft restored hint until it's changed.
export function useDraft<T extends HTMLInputElement | HTMLTextAreaElement>(key: string | undefined) {
 const [el, ref] = useState<T | null>(null), base = useRef("") // the box can show later than the hook (a step of setup)
 const [restored, setRestored] = useState(false)
 useLayoutEffect(() => {
  if (!el || !key) return
  const d = readDraft(key)
  base.current = el.value
  if (d?.text && d.text !== el.value) { apply(el, { v: d.text, c: d.text.length }); setRestored(true) } // eslint-disable-line react-hooks/set-state-in-effect
  adopt(key, el, d)
  const hide = () => { if (!applying) setRestored(false) }
  el.addEventListener("input", hide); return () => { el.removeEventListener("input", hide); const t = timers.get(key); if (t) { clearTimeout(t.id); t.run() } }
 }, [key, el])
 const discard = () => { if (!el || !key) return; change(el, base.current); cancel(key); keepDraft(key, null); setRestored(false); el.focus() }
 return { ref, props: key ? { "data-history": key, "data-draft": "" } : {}, hint: restored ? <DraftHint onDiscard={discard} /> : null,
  done: () => { if (key) { cancel(key); keepDraft(key, null) } setRestored(false) } }
}
