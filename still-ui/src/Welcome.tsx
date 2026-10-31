import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { AnimatePresence, LayoutGroup, motion, useReducedMotion, type TargetAndTransition, type Transition } from "motion/react"
import { ArrowLeft, ArrowUp, Bot, Check, CornerDownLeft, Dices, Download, Globe2, MessageCircle, Monitor, Moon, Palette, Pencil, SkipForward, Sun, Undo2, Volume2, VolumeX, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn, fadeTop, MAC } from "@/lib/utils"
import { AiPicker, type AiState } from "./AiSidebar"
import { lookOf, type Companion } from "./Buddy"
import { CrewCards, INTERESTS, PREMADES, fromPremade, premadeOf, starters, type Premade } from "./crew"
import { IntroLayer } from "./Intro"
import { BLANK, BODY_COLORS, DEFAULT_LOOK, SHAPES, lookKey, surprise, type Look } from "./look"
import { LookEditor, LookThumb } from "./LookEditor"
import { Mascot, type MascotState } from "./Mascot"
import { PluginBelt, PluginGrid, PluginKey, ThirdParty, pluginName } from "./Plugins"
import { play, setSounds, warm } from "./sound"

// First run, full window: a short intro (Intro.tsx), then your companion walks you through setup. Pick any of the crew,
// make your own, or both (setup can't finish with none; with several, you pick the main one), then set Still up yourself
// (Quick setup, no AI) or let the companion ask a few questions and do it for you. The other steps can be skipped, and
// skipping never starts a task. A step that asks for something keeps Continue off until it has an answer, with "Not now"
// to move on without one, so no two buttons ever do the same thing.
type Send = (op: string, data?: Record<string, unknown>) => void
type Step = "hello" | "import" | "ai" | "crew" | "main" | "tools" | "how" | "talk" | "you" | "interests" | "layout" | "charge" | "start"
const QUICK: Step[] = ["you", "interests", "layout", "charge"]
const EASE = [.22, 1, .36, 1] as const
// The companion pops in: squashes as it lands, stretches up, settles.
const POP: Record<"from" | "to" | "rest", TargetAndTransition> & { timing: Transition } = { from: { scaleX: .3, scaleY: .3, y: 60, opacity: 0 }, to: { scaleX: [.3, 1.16, .92, 1.03, 1], scaleY: [.3, .84, 1.1, .98, 1], y: [60, 0, -16, 0, 0], opacity: [0, 1, 1, 1, 1] },
 rest: { scaleX: 1, scaleY: 1, y: 0, opacity: 1 }, timing: { duration: .85, times: [0, .38, .62, .82, 1], ease: "easeOut" } }

const COLORS = BODY_COLORS.slice(0, 12)
const THEMES = [["Light", Sun], ["Dark", Moon], ["System", Monitor]] as const
const newId = () => "c" + Math.random().toString(36).slice(2, 11)
const blank = (): Companion => ({ id: newId(), name: "", face: "", color: "", job: "", mode: "default" })
const seenIntro = () => { try { return !!localStorage.getItem("still.intro") } catch { return false } }
// How far setup got: kept until it finishes, so closing Still partway through picks up at the same step with the same answers.
type Kept = { step: number; how: "quick" | "talk"; picks: string[]; made: Companion[]; main: string; crewIds: Record<string, string>; saved: string[]; look: Look
 you: string; likes: string[]; task: string; typed: string; allowed: "" | "yes" | "no"; tried: boolean; talked: boolean; firstUp: string }
const KEPT = "still.welcome"
const readKept = (): Partial<Kept> => { try { return JSON.parse(localStorage.getItem(KEPT) ?? "{}") ?? {} } catch { return {} } }
// "Nothing right now", "no thanks", "later": a no typed as the first task is a skip, not a task.
const NO = /^(?:no|nope|nah|nothing|none|not yet|not really|not (?:right )?now|later|maybe later|skip(?: it)?|pass|all good|i'?m (?:good|fine|ok(?:ay)?)|n ?a)(?: (?:thanks?|thank you|for now|right now|now|yet))*$/
export const isNo = (text: string) => NO.test(text.toLowerCase().replace(/[^a-z' ]/g, " ").replace(/\s+/g, " ").trim())

// A new line below the fold scrolls up into view, like a chat.
const reveal = (line?: Element | null) => {
 const talk = line?.closest(".ob-talk"), below = line && talk ? line.getBoundingClientRect().bottom + 12 - talk.getBoundingClientRect().bottom : 0
 if (below > 0) talk!.scrollBy({ top: below, behavior: "smooth" })
}
// Bubbles come in one after another; `from` holds them back while the companion pops in.
function Bubbles({ lines, from = 0 }: { lines: ReactNode[]; from?: number }) {
 const reduce = useReducedMotion()
 const box = useRef<HTMLDivElement>(null)
 return <div className="ob-bubbles" ref={box}>{lines.map((l, i) => <motion.p key={i} className="ob-bubble" initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
  transition={{ delay: reduce ? 0 : from + .12 + i * .38, duration: reduce ? .01 : .28, ease: EASE }} onAnimationComplete={() => reveal(box.current?.children[i])}>{l}</motion.p>)}</div>
}
function Reveal({ after = 0, from = 0, children }: { after?: number; from?: number; children: ReactNode }) {
 const reduce = useReducedMotion()
 return <motion.div className="ob-answer" initial={{ opacity: 0, y: reduce ? 0 : 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduce ? 0 : from + .2 + after * .38, duration: reduce ? .01 : .3, ease: EASE }}>{children}</motion.div>
}

function useWindowSize() {
 const [size, setSize] = useState([innerWidth, innerHeight])
 useEffect(() => { const on = () => setSize([innerWidth, innerHeight]); addEventListener("resize", on); return () => removeEventListener("resize", on) }, [])
 return size
}

/// A live miniature of Still's own window: the same few tabs slide between the top and the side.
function LayoutPreview({ modern }: { modern: boolean }) {
 const spring = { type: "spring", stiffness: 380, damping: 34 } as const
 return <div className={cn("ob-mini", modern && "is-side")} aria-hidden><LayoutGroup id="ob-mini">
  <motion.div layout className="ob-mini-tabs" transition={spring}>
   <motion.span layout className="ob-mini-dots" transition={spring}><i /><i /><i /></motion.span>
   {[["#e5876a", "Dinner ideas"], ["#8fb8e8", "Flights to Lisbon"], ["#7fb39b", "Weekend plan"]].map(([color, title], i) =>
    <motion.span layout key={title} className={cn("ob-mini-tab", i === 1 && "is-on")} transition={spring}><i style={{ background: color }} /><motion.b layout="position" transition={spring}>{title}</motion.b></motion.span>)}
  </motion.div>
  <motion.div layout className="ob-mini-main" transition={spring}>
   <motion.span layout className="ob-mini-bar" transition={spring}><i /><b>flights.example.com</b></motion.span>
   <motion.div layout className="ob-mini-page" transition={spring}><i /><i /><i /><i /></motion.div>
  </motion.div>
 </LayoutGroup></div>
}

type Change = { key: string; label: string; value: string; undone: boolean; editable?: boolean }
type Setup = { busy: boolean; error: string; done: boolean; turns: { role: string; text: string; options?: string[] }[]; changes: Change[] } | null
const SKIP = "(skip)", ENOUGH = "That's enough, set me up with what you know."
/// "Set it up with <name>": the companion gets to know the user, one follow-up at a time, until they say that's enough;
/// any question can be skipped. Then what it set up, in groups, each with an undo, and the wording ones editable.
/// Still's library goes along, so it can add the companions that fit their work.
function Interview({ who, send, onQuick, onDone }: { who: Companion; send: Send; onQuick: () => void; onDone: (done: boolean, first: string) => void }) {
 const [s, setS] = useState<Setup>(null)
 const [text, setText] = useState("")
 const [editing, setEditing] = useState<[string, string] | null>(null) // the change being reworded: key, text
 const log = useRef<HTMLDivElement>(null)
 useEffect(() => {
  const got = (e: MessageEvent) => { if (e.data?.kind === "setup") setS(e.data.data) }
  window.chrome?.webview?.addEventListener("message", got)
  send("setupStart", { companion: who.id, library: PREMADES.map(p => ({ ...fromPremade(p), role: p.role, area: p.area })) })
  return () => window.chrome?.webview?.removeEventListener("message", got)
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }) }, [s?.turns.length, s?.busy, s?.done])
 const first = s?.changes.find(c => c.key === "first" && !c.undone)?.value ?? ""
 useEffect(() => onDone(!!s?.done, first), [s?.done, first]) // eslint-disable-line react-hooks/exhaustive-deps
 const waiting = !s || s.busy
 const last = s?.turns.at(-1)
 const answer = (t: string) => { if (!t.trim() || waiting) return; send("setupAnswer", { text: t.trim() }); setText("") }
 const say = (placeholder: string) => <form className="ob-say" onSubmit={e => { e.preventDefault(); answer(text) }}>
  <input aria-label={placeholder} placeholder={placeholder} maxLength={2000} value={text} onChange={e => setText(e.target.value)} />
  <Button type="submit" size="icon-sm" aria-label="Send" disabled={!text.trim() || waiting}><ArrowUp /></Button>
 </form>
 const row = (c: Change) => <li key={c.key} className={cn(c.undone && "is-undone")}>
  {editing?.[0] === c.key ? <form className="ob-edit" onSubmit={e => { e.preventDefault(); if (editing[1].trim()) send("setupEdit", { key: c.key, value: editing[1].trim() }); setEditing(null) }}>
   <b>{c.label}</b>
   <textarea autoFocus aria-label={c.label} rows={Math.min(6, Math.max(2, editing[1].split("\n").length + 1))} maxLength={1000} value={editing[1]} onChange={e => setEditing([c.key, e.target.value])} />
   <div><Button type="submit" size="sm" disabled={!editing[1].trim()}>Save</Button><Button type="button" variant="ghost" size="sm" onClick={() => setEditing(null)}>Cancel</Button></div>
  </form> : <>
   <span><b>{c.label}</b><small>{c.value}</small></span>
   {c.undone ? <em>Undone</em> : <>
    {c.editable && <button onClick={() => setEditing([c.key, c.value])}><Pencil />Edit</button>}
    <button onClick={() => send("setupUndo", { key: c.key })}><Undo2 />Undo</button>
   </>}
  </>}
 </li>
 const groups = s ? ([["Your team", (k: string) => /^(hire|focus|memory|routine)\b/.test(k)], ["Your Still", (k: string) => !/^(hire|focus|memory|routine|first)\b/.test(k)], ["First up", (k: string) => k === "first"]] as const)
  .map(([title, has]) => [title, s.changes.filter(c => has(c.key))] as const).filter(([, list]) => list.length) : []
 return <div className={cn("ob-interview", s?.done && "is-done")}>
  <div className="ob-chat" ref={log} aria-live="polite" onScroll={fadeTop}>
   {s?.turns.map((t, i) => <motion.p key={i} className={cn("ob-bubble", t.role === "user" && "is-you", t.text === SKIP && "is-skip")} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, ease: EASE }}>
    {t.role === "user" && t.text === SKIP ? "Skipped" : t.role === "user" && t.text === ENOUGH ? "That's enough" : t.text}</motion.p>)}
   {waiting && !s?.error && <p className="ob-bubble is-typing" aria-label={`${who.name} is typing`}><i /><i /><i /></p>}
  </div>
  {s?.error ? <div className="ob-fallback"><p>{s.error} No problem, the quick setup takes a minute.</p><Button size="sm" onClick={onQuick}><Zap />Do the quick setup</Button></div>
   : s?.done ? <motion.div className="ob-summary" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .3, ease: EASE }}>
    <h3>Here's what I set up for you</h3>
    {groups.length ? groups.map(([title, list]) => <section key={title}><h4>{title}</h4><ul>{list.map(row)}</ul></section>)
     : <p className="ob-note">Nothing needed changing, so everything stays as it was.</p>}
    <div className="ob-summary-foot">{s.changes.some(c => !c.undone) && <Button variant="ghost" size="sm" onClick={() => send("setupUndo", { key: "" })}><Undo2 />Undo everything</Button>}
     <small>You can change any of it later in each companion's profile and in Settings.</small></div>
    {say(`Tell ${who.name} what to change`)}
   </motion.div>
   : <>
    {last?.role !== "user" && !!last?.options?.length && <div className="ob-chips">{last.options.map(o => <button key={o} disabled={waiting} onClick={() => answer(o)}>{o}</button>)}</div>}
    {say("Type your answer")}
    {!!s?.turns.length && <div className="ob-interview-foot">
     <button disabled={waiting} onClick={() => answer(SKIP)}><SkipForward />Skip this one</button>
     <button disabled={waiting || s.turns.length < 2} onClick={() => answer(ENOUGH)}><Check />That's enough, set me up</button>
    </div>}
   </>}
 </div>
}

export function Welcome({ isDefault, agents, layout, theme, talk, ai, noAi, hidden, sounds = true, soundsBlocked = "", send, onImport }: { isDefault?: boolean; agents: boolean; layout?: string; theme?: string; talk?: boolean; ai?: AiState; noAi?: boolean; hidden?: boolean; sounds?: boolean; soundsBlocked?: string; send: Send; onImport: () => void }) {
 const reduce = useReducedMotion()
 const [again] = useState(!!talk) // "set me up again": straight into the interview
 const [kept] = useState(() => again ? {} : readKept())
 // The companion the user had before setup (null until the AI state arrives). Not the live list: picks made here land in it.
 const had = useRef<Companion | undefined | null>(null)
 if (had.current === null && ai) had.current = ai.companions?.[0]
 const first = had.current ?? undefined
 const [how, setHow] = useState<"quick" | "talk">(again ? "talk" : kept.how ?? "quick")
 // The companions picked here: crew ids and the ids of ones made here, in the order picked. A crew pick keeps its id
 // if it's unpicked and picked again; whatever was saved and then unpicked is deleted when the step is left again.
 const [picks, setPicks] = useState<string[]>(kept.picks ?? [])
 const [made, setMade] = useState<Companion[]>(kept.made ?? [])
 const [main, setMain] = useState(kept.main ?? "")
 const crewIds = useRef<Record<string, string>>(kept.crewIds ?? {})
 const saved = useRef(new Set<string>(kept.saved))
 const chosen = useMemo(() => picks.flatMap(k => {
  const own = made.find(m => m.id === k), p = PREMADES.find(p => p.id === k)
  return own ? [own] : p ? [fromPremade(p, crewIds.current[k] ??= newId())] : []
 }), [picks, made])
 const flow: Step[] = again ? (how === "talk" ? ["talk"] : QUICK) : noAi || !ai ? ["hello", "import", "layout", "charge"]
  : ["hello", "import", "ai", "crew", ...(chosen.length > 1 ? ["main"] as Step[] : []), "tools", "how", ...(how === "talk" ? ["talk"] as Step[] : QUICK), "start"]
 const [step, setStep] = useState(kept.step ?? 0)
 const [draft, setDraft] = useState<Companion>(blank) // "Make your own" while it's being made
 const [look, setLook] = useState<Look>(() => kept.look ?? (first ? lookOf(first) : DEFAULT_LOOK)) // what the big companion wears: a friendly face until one is picked; BLANK is for making your own
 const [making, setMaking] = useState(false) // "Make your own": it grows a color, a face and a name
 const [grown, setGrown] = useState(0)
 const [styling, setStyling] = useState(false)
 const [needOne, setNeedOne] = useState(false) // "Skip setup" before there's a companion
 const [you, setYou] = useState(kept.you ?? "")
 const [likes, setLikes] = useState<string[]>(kept.likes ?? [])
 const [task, setTask] = useState(kept.task ?? "")
 const [typed, setTyped] = useState(kept.typed ?? "")
 const [allowed, setAllowed] = useState<"" | "yes" | "no">(kept.allowed ?? "")
 const [tried, setTried] = useState(kept.tried ?? false) // brought their stuff over, or made Still open their links
 const [talked, setTalked] = useState(kept.talked ?? false) // the interview is done
 const [firstUp, setFirstUp] = useState(kept.firstUp ?? "") // what the interview heard they want help with first
 const [hadIntro] = useState(() => !again && !seenIntro()) // once, on the first run; About can replay it
 const [introOn, setIntroOn] = useState(hadIntro)
 const [introAt, setIntroAt] = useState<{ x: number; y: number }>()
 const [woke, setWoke] = useState(false)
 const [gesture, setGesture] = useState<[string, number]>(() => hadIntro ? ["wake", 1] : ["", 0])
 const [talking, setTalking] = useState(true)
 const [peek, setPeek] = useState<string | null>(null)
 const [leaving, setLeaving] = useState<{ x: number; y: number; scale: number; opacity: number } | null>(null)
 const mascotRef = useRef<HTMLDivElement>(null)
 const [width, height] = useWindowSize()
 const at = flow[Math.min(step, flow.length - 1)]
 // The main companion: the one picked as main, the only one picked, or the one the user had. It runs the rest of setup.
 const lead = chosen.find(x => x.id === main) ?? (chosen.length === 1 ? chosen[0] : undefined)
 const c = making ? draft : lead ?? first ?? draft
 const picked = !!(lead ?? first)
 const intro = !again && step === 0 && !reduce ? hadIntro ? .45 : .75 : 0 // the hello waits for the companion to pop in, or to glide in after the intro
 const name = c.name.trim() || "your companion"
 const wide = at === "crew" && !making
 const size = Math.round(Math.min(520, Math.max(200, Math.min(height / 2.3, width / 4))) * (wide ? .6 : 1))
 const tasks = useMemo(() => starters(likes, picked ? c : undefined, 3), [likes, picked, c])
 const harness = ai?.harnesses.find(h => h.id === (c.ai || ai.harness))
 const aiReady = !!harness?.installed && !["missing", "signedOut"].includes(harness.status)
 // Connect your tools: the team that was just hired, and which of them cheers when an app it works in gets connected.
 const team = chosen.length ? chosen : first ? [first] : []
 const plugins = ai?.plugins, linked = plugins?.connected.map(x => x.slug).join() ?? ""
 const [cheer, setCheer] = useState<[string, string, number]>(["", "", 0])
 const seen = useRef<string | null>(null)
 useEffect(() => {
  const now = linked ? linked.split(",") : [], before = seen.current === null ? now : seen.current.split(",")
  seen.current = linked
  const fresh = now.find(s => !before.includes(s))
  const who = fresh && (team.find(x => premadeOf(x)?.uses.includes(fresh)) ?? lead ?? team[0])
  if (fresh && who && at === "tools") { setCheer([who.id, fresh, Date.now()]); if (team.length < 2) setGesture(["happy", Date.now()]) } // on its own, the big one cheers
 }, [linked]) // eslint-disable-line react-hooks/exhaustive-deps
 const blocked = at === "crew" && (making ? !draft.name.trim() : !chosen.length && !first) || at === "main" && !lead || at === "how" // "how" goes on from its two options
 // Steps that ask for something: Continue waits for an answer, and until then "Not now" moves on without one.
 const answered = at === "tools" ? !!plugins?.connected.length : at === "import" ? tried : at === "ai" ? aiReady : at === "talk" ? talked : at === "you" ? !!you.trim() : at === "interests" ? likes.length > 0 : at === "start" ? !!(task || typed.trim()) : true
 useEffect(() => { if (introOn) return; setTalking(true); const t = setTimeout(() => setTalking(false), 1700); return () => clearTimeout(t) }, [at, introOn])
 useEffect(() => {
  warm("jingle")
  if (hadIntro) return
  const t = setTimeout(() => setGesture(["wave", Date.now()]), again || reduce ? 0 : 650); return () => clearTimeout(t)
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 // While the intro plays, the companion stands in the middle of the window, then glides to its place.
 useLayoutEffect(() => {
  const r = hadIntro && mascotRef.current?.getBoundingClientRect()
  if (r) setIntroAt({ x: innerWidth / 2 - (r.left + r.width / 2), y: innerHeight / 2 - 30 - (r.top + r.height / 2) })
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => {
  if (again || leaving) return
  const keep: Kept = { step, how, picks, made, main, crewIds: crewIds.current, saved: [...saved.current], look, you, likes, task, typed, allowed, tried, talked, firstUp }
  try { localStorage.setItem(KEPT, JSON.stringify(keep)) } catch { /* no storage: setup starts over next time */ }
 }, [again, leaving, step, how, picks, made, main, look, you, likes, task, typed, allowed, tried, talked, firstUp])
 const react = (g: string) => setGesture([g, Date.now()])
 const endIntro = (skipped: boolean) => {
  setIntroOn(false)
  try { localStorage.setItem("still.intro", "1") } catch { /* no storage: it may play again */ }
  if (skipped) react("wave")
 }
 const sound = (on: boolean) => { setSounds(on && !soundsBlocked); send("preference", { key: "sounds", value: String(on) }) }

 // The end: the companion flies to its place in the browser (the new tab page, or the chat it just started) while
 // everything else fades away.
 const finish = (firstTask?: string) => {
  if (leaving) return
  try { localStorage.removeItem(KEPT) } catch { /* no storage */ }
  send("setupEnd")
  if (firstTask) send("aiSend", { text: firstTask, home: true, companion: c.id })
  else if (!again) send("aiKickoff", { companion: c.id }) // no first task: the companion starts its first chat itself
  try { localStorage.setItem("still.tour", "1") } catch { /* no storage: no tour */ }
  if (reduce) { send("welcomeDone"); return }
  play("jingle")
  setLeaving({ x: 0, y: 0, scale: 1, opacity: 1 })
  setTimeout(() => {
   const spot = document.querySelector<HTMLElement>(".home-face, .chat-hello-face"), from = mascotRef.current?.getBoundingClientRect(), to = spot?.getBoundingClientRect()
   if (!from) return
   if (spot) { spot.style.visibility = "hidden"; setTimeout(() => spot.style.visibility = "", 880) } // one companion: the flying one lands in its place
   setLeaving(to && to.width ? { x: to.left + to.width / 2 - (from.left + from.width / 2), y: to.top + to.height / 2 - (from.top + from.height / 2), scale: to.width / from.width, opacity: 1 }
    : { x: -from.left - from.width / 2 + 40, y: -from.top - from.height / 2 + 40, scale: .12, opacity: 0 })
  }, 120)
  setTimeout(() => send("welcomeDone"), 1000)
 }
 const lookOfKey = (k?: string) => { const own = made.find(m => m.id === k), p = PREMADES.find(p => p.id === k); return own ? lookOf(own) : p ? p.look : first ? lookOf(first) : DEFAULT_LOOK }
 const toggle = (key: string) => {
  const on = !picks.includes(key), next = on ? [...picks, key] : picks.filter(k => k !== key)
  setPicks(next); setNeedOne(false); setLook(lookOfKey(on ? key : next.at(-1)))
  if (!on && main === key) setMain("")
  if (on) react("hired")
 }
 // "Make your own" ends with "Hire <name>", back on the crew with it picked.
 const addOwn = () => {
  const final = look
  const own = { ...draft, name: draft.name.trim(), look: lookKey(final) }
  setMade(m => [...m, own]); setPicks(p => [...p, own.id]); setLook(final); setMaking(false); setNeedOne(false); react("happy")
 }
 // Leaving the companion step: the picks are saved, any picked earlier and dropped since are deleted (after, so there's
 // always one), and the main one goes first in the list, so new chats start with it.
 const commit = () => {
  for (const x of chosen) { send("companionSave", x); saved.current.add(x.id) }
  for (const id of [...saved.current]) if (!chosen.some(x => x.id === id)) { send("companionDelete", { id }); saved.current.delete(id) }
  if (chosen.length) send("companionMain", { id: (lead ?? chosen[0]).id })
 }
 // Onboarding answers are the first memories of every companion picked here, and the interests pick the ideas it offers.
 const remember = () => {
  const ids = chosen.length ? chosen.map(x => x.id) : first ? [first.id] : []
  for (const id of ids) {
   if (at === "you" && you.trim()) send("memoryAdd", { companion: id, text: `Likes to be called ${you.trim()}.`, kind: "fact", key: "name" })
   if (at === "interests" && likes.length) send("memoryAdd", { companion: id, text: `Works on ${likes.join(", ").toLowerCase()}.`, kind: "preference", key: "interests" })
  }
  if (at === "interests" && likes.length) send("interests", { list: likes })
 }
 const go = (to: number) => { setStep(to); if (flow[to] === "ai") send("aiCheck") }
 const next = () => {
  if (blocked || !answered) return
  if (at === "crew" && making) { addOwn(); return }
  if (at === "crew") commit()
  if (at === "main") send("companionMain", { id: lead!.id })
  if (at === "you" || at === "interests") remember()
  if (at === "start") { const text = typed.trim() || task; finish(text && !isNo(text) ? text : undefined); return }
  if (step >= flow.length - 1) { finish(at === "talk" && firstUp || undefined); return }
  if (at === "talk" && firstUp && !task && !typed.trim()) setTyped(firstUp)
  go(step + 1)
 }
 const skip = () => { if (step >= flow.length - 1) finish(); else go(step + 1) }
 // Skip setup: fine once there's a companion (or no AI to have one with); before that, it goes to the crew.
 const skipAll = () => {
  if (noAi || !ai || first || saved.current.size) { finish(); return }
  if (at === "crew" && !making && chosen.length) { commit(); finish(); return }
  setNeedOne(true); setMaking(false); go(flow.indexOf("crew"))
 }

 const mood: MascotState = introOn ? "idle" : at === "charge" && !allowed ? "needs" : talking ? "talking" : "idle"
 const pickColor = (hex: string) => { setLook(l => ({ ...l, color: hex })); setGrown(g => Math.max(g, 1)); react("admire") }
 const pickShape = (shape: string) => { setLook(l => ({ ...l, shape })); setGrown(g => Math.max(g, 2)); react("happy") }
 const startOwn = () => { setMaking(true); setDraft(blank()); setLook(BLANK); setGrown(0) }
 const shown = peek ?? layout ?? "Classic"
 const slide = reduce ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } } : { initial: { opacity: 0, x: 24 }, animate: { opacity: 1, x: 0 }, exit: { opacity: 0, x: -18 } }
 const soundOn = sounds && !soundsBlocked

 return <div className={cn("welcome ob", hidden && "is-hidden", leaving && "is-leaving", introOn && "is-intro")} role="dialog" aria-modal="true" aria-label="Set up Still">
  <header className="ob-top">
   <span className="still-mark is-small" aria-hidden><i /><i /></span>
   <div className="ob-dots" role="progressbar" aria-valuemin={1} aria-valuemax={flow.length} aria-valuenow={step + 1} aria-label={`Step ${step + 1} of ${flow.length}`}>{flow.map((s, i) => <i key={s} className={cn(i === step && "is-on", i < step && "is-done")} />)}</div>
   <button className="ob-sound" aria-pressed={!soundOn} aria-label="Mute" title={soundsBlocked || (soundOn ? "Mute" : "Unmute")} disabled={!!soundsBlocked} onClick={() => sound(!sounds)}>{soundOn ? <Volume2 /> : <VolumeX />}</button>
   <div className="ob-theme" role="radiogroup" aria-label="Theme">{THEMES.map(([k, Icon]) => <button key={k} role="radio" aria-checked={(theme ?? "System") === k} aria-label={k} title={k === "System" ? (MAC ? "Match your Mac" : "Match Windows") : k} onClick={() => send("preference", { key: "theme", value: k })}><Icon /></button>)}</div>
   {step < flow.length - 1 ? <button className="ob-skip-all" onClick={skipAll}>Skip setup</button> : <button className="ob-skip-all" style={{ visibility: "hidden" }} tabIndex={-1} aria-hidden>Skip setup</button>}
  </header>
  <main className={cn("ob-stage", wide && "is-wide")} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !(e.target as HTMLElement).closest("button,textarea,form")) { e.preventDefault(); next() } }}>
   <motion.div ref={mascotRef} className="ob-companion" style={{ "--hue": look.color } as CSSProperties} animate={leaving ?? (introOn && introAt ? { ...introAt, scale: 1, opacity: 1 } : { x: 0, y: 0, scale: 1, opacity: 1 })}
    transition={introOn ? { duration: 0 } : { duration: .8, ease: [.6, 0, .2, 1] }}>
    <motion.div className="ob-pop" initial={intro && !hadIntro ? POP.from : false} animate={intro && !hadIntro ? POP.to : POP.rest} transition={POP.timing}>
     <Mascot look={look} size={size} state={mood} follow={!introOn} gesture={gesture[0]} gestureAt={gesture[1]} className={cn(introOn && "intro-body", woke && "is-on")} />
    </motion.div>
    {(making || picked) && (at === "crew" || at === "how") && c.name.trim() && <motion.b className="ob-name" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>{c.name.trim()}</motion.b>}
   </motion.div>
   <AnimatePresence mode="wait" initial={false}>
    <motion.section key={at + (making ? "-own" : "") + (introOn ? "-held" : "")} className="ob-talk" onScroll={fadeTop} {...slide} transition={{ duration: reduce ? .01 : .26, ease: EASE }}>
     {introOn ? null : <>
     {at === "hello" && <Bubbles from={intro} lines={noAi || !ai ? ["Hi! Welcome to Still.", "Still is an open-source browser that AI apps on this computer can work in, right next to your own tabs.", "Let's set a few things up. You can skip any step."]
      : ["Hi! Welcome to Still.", first ? `I'm ${first.name}. I'll get you set up.` : "I'll get you set up. In a minute you'll pick who you work with.", "Still is an open-source browser with AI built in. It runs on the AI you already pay for, like Claude, ChatGPT or Grok, through their own apps. No API keys, no credits, no extra plan.", "Everything stays on your computer. It takes a couple of minutes, and you can skip most steps."]} />}
     {at === "import" && <>
      <Bubbles lines={["Coming from Chrome, Edge or another browser?", "I can copy over your bookmarks, history, passwords and sign-ins. It all stays on this computer."]} />
      <Reveal after={2}><div className="ob-options">
       <button className="ob-option" onClick={() => { setTried(true); onImport() }}><Download /><span><strong>Bring my stuff over</strong><small>{MAC ? "Chrome, Safari, Firefox, Edge, Brave" : "Chrome, Edge, Firefox, Brave, Opera GX"} or a saved export. You check it before anything is copied.</small></span></button>
       <button className="ob-option" disabled={isDefault} onClick={() => { setTried(true); send("defaultBrowser") }}><Globe2 /><span><strong>{isDefault ? "Still opens your links" : "Open my links in Still"}</strong><small>{isDefault ? "Links from other apps open here" : `${MAC ? "macOS" : "Windows"} asks you to confirm`}</small></span>{isDefault && <Check />}</button>
      </div></Reveal>
     </>}
     {at === "ai" && ai && <>
      <Bubbles lines={["Which AI should I think with?", "Pick the one you already use. I go through its own app on this computer, so the plan you have covers everything.", "You can switch any time, even halfway through a task."]} />
      <Reveal after={3}><AiPicker ai={ai} send={send} onPick={id => send("aiHarness", { harness: id })} /></Reveal>
     </>}
     {at === "crew" && !making && <>
      <Bubbles lines={first ? ["Want to keep me, or grow the team?", "Each of these owns a part of your work. Hire one or a few, or make your own."]
       : ["Who do you want on your team?", "Each of these owns a part of your work. Hire one or a few, or make your own. You can change anything about them later."]} />
      <Reveal after={2}>
       {first && <button className="ob-option ob-keep" onClick={() => { setPicks([]); setMain(""); setLook(lookOf(first)); go(step + 1) }}><Check /><span><strong>Keep {first.name}</strong><small>Carry on with the companion you have.</small></span></button>}
       {needOne && <p className="ob-note is-warn" role="alert">Hire at least one companion first. Then you can skip the rest.</p>}
       <CrewCards picked={picks} made={made} onPick={(p: Premade) => toggle(p.id)} onMade={toggle} onOwn={startOwn} />
      </Reveal>
     </>}
     {at === "crew" && making && <>
      <Bubbles lines={["Let's make one that's all yours.", "Pick a color and a shape, give me a name, and tell me what I'm here to do."]} />
      <Reveal after={2}><div className="ob-build">
       <div className="ob-row"><span>Color</span><div className="ob-colors" role="radiogroup" aria-label="Color">{COLORS.map(([hex, label]) => <button key={hex} role="radio" aria-checked={look.color === hex} aria-label={label} title={label} style={{ "--swatch": hex } as CSSProperties} onClick={() => pickColor(hex)} />)}</div></div>
       {grown >= 1 && <motion.div className="ob-row" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}><span>Shape</span><div className="ob-faces" role="radiogroup" aria-label="Shape">{SHAPES.map(([k, label]) => <button key={k} role="radio" aria-checked={look.shape === k} aria-label={label} title={label} onClick={() => pickShape(k)}><LookThumb look={{ ...look, shape: k }} /></button>)}</div></motion.div>}
       {grown >= 2 && <motion.div className="ob-row" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}><span>Name</span>
        <div className="ob-name-box"><input aria-label="Name your companion" placeholder="Their name" maxLength={24} value={draft.name} onChange={e => { setDraft({ ...draft, name: e.target.value }); setGrown(3) }} /></div>
       </motion.div>}
       {grown >= 3 && <motion.div className="ob-row" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}><span>Job</span>
        <div className="ob-name-box"><textarea aria-label="What should I do for you?" placeholder="What should I do for you? You can skip this." rows={2} maxLength={400} value={draft.job} onChange={e => setDraft({ ...draft, job: e.target.value })} /></div>
       </motion.div>}
       <div className="ob-build-actions">
        <Button variant="outline" size="sm" onClick={() => { setLook(surprise()); setGrown(3); react("pop") }}><Dices />Surprise me</Button>
        <Button variant="ghost" size="sm" onClick={() => setStyling(true)}><Palette />Customize</Button>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => { setMaking(false); setLook(lookOfKey(picks.at(-1))) }}>Back to the team</Button>
       </div>
      </div></Reveal>
      {styling && <LookEditor companion={{ ...draft, look: lookKey(look) }} onClose={() => setStyling(false)} onSave={k => { const l = lookOf({ ...draft, look: k }); setLook(l); setGrown(g => Math.max(g, 2)); setStyling(false); react("happy") }} />}
     </>}
     {at === "main" && <>
      <Bubbles lines={["Great team! Who should lead?", "Your lead finishes setting up with you, takes your first task and starts your new chats. The rest of the team is a click away in any chat."]} />
      <Reveal after={2}><div className="ob-layouts ob-mains" role="radiogroup" aria-label="Who leads">{chosen.map(x => <button key={x.id} role="radio" aria-checked={main === x.id} style={{ "--hue": lookOf(x).color } as CSSProperties} onClick={() => { setMain(x.id); setLook(lookOf(x)); react("happy") }}>
       <span className="ob-mains-face"><Mascot look={lookOf(x)} size={56} /></span><strong>{x.name}</strong><small>{premadeOf(x)?.role ?? "Made by you"}</small><span className="ob-check" aria-hidden><Check /></span></button>)}</div></Reveal>
     </>}
     {at === "tools" && <>
      <Bubbles lines={[team.length > 1 ? "Want the team to work in your apps?" : "Want me to work in your apps?", "Connect Gmail, Calendar, Slack and more through Composio. Reading is free. Anything that sends, posts or changes something still asks you first."]} />
      <Reveal after={2}>
       {team.length > 1 ? <div className="ob-team">{team.map(x => <span key={x.id} className="ob-team-mate" title={x.name}>
        <Mascot look={lookOf(x)} size={52} gesture={cheer[0] === x.id ? "happy" : ""} gestureAt={cheer[0] === x.id ? cheer[2] : 0} />
        {cheer[0] === x.id && <span key={cheer[2]} className="ob-team-line" role="status">Now I can work in {pluginName(cheer[1])}</span>}</span>)}</div>
        : cheer[0] && <p key={cheer[2]} className="ob-bubble ob-cheer" role="status">Now I can work in {pluginName(cheer[1])}</p>}
       {plugins?.key && plugins.status === "ok" ? <PluginGrid plugins={plugins} send={send} /> : <PluginBelt />}
       {!(plugins?.key && plugins.status === "ok") && <PluginKey plugins={plugins} send={send} />}
       <ThirdParty />
       {!plugins?.key && <p className="ob-note">No key? Skip this. You can turn plugins on any time in Skills & plugins.</p>}
      </Reveal>
     </>}
     {at === "how" && <>
      <Bubbles lines={[`Hi, I'm ${name}.`, "How do you want to set things up?"]} />
      <Reveal after={2}><div className="ob-options">
       <button className="ob-option is-big" disabled={!aiReady} onClick={() => { setHow("talk"); go(step + 1) }}><MessageCircle /><span><strong>Set it up with {name}</strong>
        <small>I get to know you: your work, goals, tools, schedule and how you like answers. Then I set Still up around you: the right companions, what each one focuses on and remembers, routines to try and your settings. Skip any question, stop when you like, and check every change.</small>
        <small className="ob-usage">Uses a little of your {harness?.name ?? "AI"} plan, about as much as one short chat (a dozen quick messages or so).</small></span></button>
       <button className="ob-option is-big" onClick={() => { setHow("quick"); go(step + 1) }}><Zap /><span><strong>Quick setup</strong><small>Tap through a few choices yourself. Uses no AI at all.</small></span></button>
      </div>{!aiReady && <p className="ob-note">Connect your AI on the earlier step to set things up with {name}.</p>}</Reveal>
     </>}
     {at === "talk" && <Interview who={c} send={send} onQuick={() => { setHow("quick"); if (again) setStep(0) }} onDone={(done, first) => { setTalked(done); setFirstUp(first) }} />}
     {at === "you" && <>
      <Bubbles lines={["First, a little about you.", "What should I call you?"]} />
      <Reveal after={2}><div className="ob-name-box"><input autoFocus aria-label="Your name" placeholder="Your first name" maxLength={40} value={you} onChange={e => setYou(e.target.value)} /></div>
       <p className="ob-note">{chosen.length > 1 ? "We keep this in our memories on this computer, so nobody asks twice." : "I keep this in my memory on this computer, so I don't ask twice."}</p></Reveal>
     </>}
     {at === "interests" && <>
      <Bubbles lines={[you.trim() ? `Thanks, ${you.trim()}. What does your work involve?` : "What does your work involve?", "Pick a few. I'll remember them, so what I suggest fits your work."]} />
      <Reveal after={2}><div className="ob-chips is-big" role="group" aria-label="Your work">{INTERESTS.map(k => { const on = likes.includes(k); return <button key={k} aria-pressed={on} onClick={() => setLikes(l => l.includes(k) ? l.filter(x => x !== k) : [...l, k])}>{on && <Check />}{k}</button> })}</div></Reveal>
     </>}
     {at === "layout" && <>
      <Bubbles lines={["Where do you like your tabs?", "You can change this later in Settings."]} />
      <Reveal after={2}>
       <LayoutPreview modern={shown === "Modern"} />
       <div className="ob-layouts" role="radiogroup" aria-label="Tab layout" onMouseLeave={() => setPeek(null)}>
        {([["Classic", "Tabs across the top, like most browsers"], ["Modern", "Tabs down the side, next to your chats"]] as const).map(([k, sub]) =>
         <button key={k} role="radio" aria-checked={(layout ?? "Classic") === k} onMouseEnter={() => setPeek(k)} onFocus={() => setPeek(k)} onBlur={() => setPeek(null)} onClick={() => send("preference", { key: "tabLayout", value: k })}>
          <strong>{k}{k === "Classic" && <small> · default</small>}</strong><small>{sub}</small><span className="ob-check" aria-hidden><Check /></span></button>)}
       </div>
      </Reveal>
     </>}
     {at === "charge" && <>
      <Bubbles lines={noAi || !ai ? ["You're in charge.", "AI apps ask before they start, and you can stop them or take over any page."] : ["You're in charge.", "I ask before anything that matters, like buying, sending or deleting. Try it:"]} />
      {!noAi && ai && <Reveal after={2}><div className="ob-ask">
       <p><b>{name}</b> wants to place an order for <b>$24.90</b> on a shop's checkout page.</p>
       {allowed ? <p className="ob-ask-done"><Check />{allowed === "yes" ? "Done. I only go ahead when you say so." : "No problem. I'll stop and wait for you."}</p>
        : <div><Button size="sm" onClick={() => { setAllowed("yes"); react("done") }}>Allow once</Button><Button size="sm" variant="ghost" onClick={() => { setAllowed("no"); react("happy") }}>Not now</Button></div>}
       <small>While I work, a bar at the bottom lets you take over or stop me at any moment.</small>
      </div></Reveal>}
      <Reveal after={3}><button className="ob-option ob-switch" role="switch" aria-checked={agents} onClick={() => send("preference", { key: "agents", value: agents ? "false" : "true" })}>
       <Bot /><span><strong>Let other AI apps use Still</strong><small>Apps like Claude Code or Cursor can open and read pages here. Each one asks you first, and never sees private tabs or passwords.</small></span><i aria-hidden /></button></Reveal>
     </>}
     {at === "start" && <>
      <Bubbles lines={["All set. Want to start with something?", "Pick one, or tell me in your own words. You'll see me work, and you can jump in any time."]} />
      <Reveal after={2}>
       <div className="ob-tasks" role="radiogroup" aria-label="First task">{tasks.map(([label, prompt]) => <button key={label} role="radio" aria-checked={task === prompt} onClick={() => { setTask(task === prompt ? "" : prompt); setTyped("") }}><i />{label}</button>)}</div>
       <div className="ob-name-box"><textarea aria-label="Your own task" rows={2} placeholder="Or type your own" value={typed} onChange={e => { setTyped(e.target.value); setTask("") }} /></div>
      </Reveal>
     </>}
     </>}
    </motion.section>
   </AnimatePresence>
  </main>
  <motion.footer className="ob-foot" initial={intro ? { opacity: 0, y: 18 } : false} animate={introOn ? { opacity: 0, y: 18 } : { opacity: 1, y: 0 }} transition={{ delay: introOn ? 0 : intro ? intro + 1.7 : 0, duration: .35, ease: EASE }}>
   {step > 0 ? <Button variant="ghost" onClick={() => go(step - 1)}><ArrowLeft />Back</Button> : <span />}
   <span className="flex-1" />
   {!answered && <button className="ob-not-now" onClick={skip}>{at === "tools" ? "Skip" : "Not now"}</button>}
   {at !== "how" && <Button className="ob-next" disabled={blocked || !answered} onClick={next}>{at === "start" ? (!task && isNo(typed) ? "Finish" : "Let's go") : at === "hello" ? "Let's start" : at === "talk" ? (again ? "Done" : "Looks good")
    : at === "crew" && making ? (draft.name.trim() ? `Hire ${draft.name.trim()}` : "Hire them") : "Continue"}<CornerDownLeft /></Button>}
  </motion.footer>
  {introOn && <IntroLayer at={{ x: innerWidth / 2, y: innerHeight / 2 - 30, r: size / 2 }} hue={look.color} reduced={!!reduce} sound={soundOn} onSound={sound}
   live={() => !!mascotRef.current?.querySelector("canvas[data-live]")} onStart={() => setWoke(true)} onEnd={endIntro} />}
 </div>
}
