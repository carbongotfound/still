import { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog"
import NOTES from "./whatsnew.json"

// "Still has updated": once, on the first start after an update to a version with news, and again from About. Each
// release adds "x.y.z": { "announce": true, "news": [3 to 5 short lines] } to whatsnew.json; announce false (or no
// entry) stays silent. Versions skipped show together, newest first. The notes ship in the app: no network call.
type Release = { announce?: boolean; news?: string[] }
type Notes = Record<string, Release>
const RELEASES_URL = "https://github.com/carbongotfound/still/releases"
const parts = (v: string) => [...v.split(".").map(Number), 0, 0, 0].slice(0, 3).map(n => n || 0)
const newer = (a: string, b: string) => { const x = parts(a), y = parts(b), i = x.findIndex((n, j) => n !== y[j]); return i >= 0 && x[i] > y[i] }
/// The announced versions after `seen` up to `version`, newest first ("2.10" counts as 2.10.0).
const newsSince = (seen: string, version = "", all: Notes = NOTES) =>
 Object.entries(all).filter(([v, r]) => r.announce && r.news?.length && newer(v, seen) && !newer(v, version)).sort(([a], [b]) => newer(a, b) ? -1 : 1)
/// The latest version with news, for About.
export const latestNews = (version?: string, all?: Notes) => newsSince("", version, all)[0]?.[0]

type Shown = { version?: string; seenVersion?: string; welcome?: boolean; secondary?: boolean; incognito?: boolean; qaNotes?: Notes | null }
export function WhatsNew({ state, open, setOpen, send }: { state: Shown; open: boolean; setOpen: (v: boolean) => void; send: (op: string, payload?: Record<string, unknown>) => void }) {
 const all = state.qaNotes ?? NOTES, missed = state.seenVersion === undefined ? [] : newsSince(state.seenVersion, state.version, all)
 const due = !!missed.length && !state.welcome && !state.secondary && !state.incognito
 useEffect(() => { if (due) setOpen(true) }, [due, setOpen])
 const shown = due ? missed : newsSince("", state.version, all).slice(0, 1)
 if (!shown.length) return null
 // Seen once it has closed (Got it, Esc or a click outside), so it never comes back and doesn't change while it fades.
 return <Dialog open={open} onOpenChange={setOpen}>
  <DialogContent className="app-dialog whatsnew" showCloseButton={false} onCloseAutoFocus={() => { if (due) send("whatsNewSeen") }}>
   <div><DialogTitle>{due ? "Still has updated" : "What's new"}</DialogTitle><DialogDescription>Version {due ? state.version : shown[0][0]}</DialogDescription></div>
   <ul className="whatsnew-news">{shown.flatMap(([v, r]) => (r.news ?? []).map((n, i) => <li key={v + i}>{n}</li>))}</ul>
   <DialogFooter><Button variant="link" size="sm" onClick={() => { send("new", { url: RELEASES_URL }); setOpen(false) }}>See all changes</Button><Button size="sm" onClick={() => setOpen(false)}>Got it</Button></DialogFooter>
  </DialogContent>
 </Dialog>
}
