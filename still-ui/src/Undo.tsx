import { useSyncExternalStore, type ReactNode } from "react"
import { toast } from "sonner"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"

// Destroying anything goes through here: a dialog that names what will be lost, then an Undo toast for 6 seconds. The
// item hides at once, and the real delete is sent only when the toast is gone (timed out or closed). If Still closes
// first, nothing is deleted.
const UNDO_MS = 6000
const gone = new Set<string>()
const subs = new Set<() => void>()
let version = 0, asking: Ask | null = null
const bump = () => { version++; subs.forEach(f => f()) }
const watch = (f: () => void) => { subs.add(f); return () => { subs.delete(f) } }

/// Re-renders when something is hidden, shown again or asked about. Returns a number that changes each time.
export const useGone = () => useSyncExternalStore(watch, () => version)
/// Whether a key is hidden, waiting to be deleted.
export const isGone = (key: string) => gone.has(key)
/// Whether the confirm dialog is open (the page hides under it, like under any dialog).
export const isAsking = () => !!asking

type Ask = { title: string; body: ReactNode; action?: string; cancel?: string; run?: () => void }

/// Hides `key`, shows "`done`" with Undo, and runs `run` once the toast is gone. Undo shows it again and runs `undo`.
export function removeLater(key: string, done: string, run: () => void, undo?: () => void) {
 if (gone.has(key)) return
 gone.add(key); bump()
 let settled = false
 const commit = () => {
  if (settled) return
  settled = true; run()
  setTimeout(() => { gone.delete(key); bump() }, 3000) // by then the deleted item has left Still's own lists
 }
 toast(done, { id: "undo-" + key, duration: UNDO_MS, className: "undo-toast", onAutoClose: commit, onDismiss: commit,
  action: { label: "Undo", onClick: () => { settled = true; gone.delete(key); bump(); undo?.() } } })
}

/// Asks first, naming what goes, then hides it with Undo (removeLater).
export function destroy(o: { key: string; title: string; body: ReactNode; action: string; cancel?: string; done: string; run: () => void; onConfirm?: () => void; undo?: () => void }) {
 asking = { title: o.title, body: o.body, action: o.action, cancel: o.cancel, run: () => { o.onConfirm?.(); removeLater(o.key, o.done, o.run, o.undo) } }
 bump()
}

/// A dialog with only OK, for when something can't be destroyed yet.
export function tell(title: string, body: ReactNode) { asking = { title, body }; bump() }

/// The one confirm dialog, mounted once in App.
export function Confirmer() {
 useGone()
 const a = asking
 const close = () => { asking = null; bump() }
 return <AlertDialog open={!!a} onOpenChange={o => { if (!o) close() }}><AlertDialogContent className="confirm-dialog">
  <AlertDialogHeader><AlertDialogTitle>{a?.title}</AlertDialogTitle><AlertDialogDescription>{a?.body}</AlertDialogDescription></AlertDialogHeader>
  <AlertDialogFooter><AlertDialogCancel>{a?.run ? a.cancel ?? "Cancel" : "OK"}</AlertDialogCancel>
   {a?.run && <AlertDialogAction variant="destructive" onClick={() => { close(); a.run?.() }}>{a.action}</AlertDialogAction>}</AlertDialogFooter>
 </AlertDialogContent></AlertDialog>
}

type Send = (op: string, payload?: Record<string, unknown>) => void

/// Deleting a chat, from any list or its own menu.
export const deleteChat = (send: Send, c: { id: string; title?: string }, onConfirm?: () => void) => destroy({
 key: "chat:" + c.id, title: `Delete "${c.title || "this chat"}"?`, action: "Delete chat", done: "Chat deleted", onConfirm, run: () => send("aiDeleteChat", { id: c.id }),
 body: "The chat goes, with its messages, the tasks it started and the files attached to it. Your AI app may keep its own copy.",
})

export const deleteAllChats = (send: Send, count: number) => destroy({
 key: "chats:all", title: "Delete all chats?", action: "Delete all chats", done: "All chats deleted", run: () => send("aiDeleteAll"),
 body: `All ${count} ${count === 1 ? "chat" : "chats"} in this profile go, with their messages and attached files, and chat tabs close. Your AI app may keep its own copy.`,
})

/// Firing a companion. Still needs one, so the last one can't go.
export function fire(send: Send, c: { id: string; name: string }, only: boolean, onConfirm?: () => void) {
 if (only) return tell(`${c.name} is your only companion`, `Still needs at least one. Hire or make another first, then you can fire ${c.name}.`)
 destroy({ key: "companion:" + c.id, title: `Fire ${c.name}?`, action: `Fire ${c.name}`, cancel: `Keep ${c.name}`, done: `Fired ${c.name}`, onConfirm,
  body: `${c.name} goes, with everything they remember about you and their routines. Your chats with them stay.`, run: () => send("companionDelete", { id: c.id }) })
}
