import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { AnimatePresence, motion, useReducedMotion, type TargetAndTransition, type Transition } from "motion/react"
import { ArrowLeft, ArrowUp, Check, CornerDownLeft, Dices, Download, FileSearch, Globe2, Monitor, Moon, PanelLeft, Palette, Pencil, RotateCw, SkipForward, Sun, Undo2, UserPlus, Volume2, VolumeX, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { cn, fadeTop, MAC } from "@/lib/utils"
import { AiPicker, type AiState } from "./AiSidebar"
import { QuickApi } from "./ApiProviders"
import { lookOf, type Companion, type ReplyLength } from "./Buddy"
import { useDraft } from "./drafts"
import { INTERESTS, JoinedCard, LIBRARY, ROLE_TEXT, SETUP_CREW, fromPremade, starters } from "./crew"
import { generate } from "./generate"
import { IntroLayer } from "./Intro"
import { STARTS, lookKey, surprise, v2, type Look } from "./look"
import { LookEditor, LookThumb } from "./LookEditor"
import { Mascot, type MascotState } from "./Mascot"
import { play, setSounds, warm } from "./sound"

// First run, full window: a short intro (Intro.tsx), then four steps. Welcome, connect the AI app the user already has,
// create their own companion (a name and a look, then with an AI app ready a few plain questions in a chat, and what it
// will do, in plain words, to check before Hire), and a first task in its chat, with a sample page that ships with Still. Just browse for now is on every step
// and never makes a companion. Import, default browser, plugins, layout and more companions come later, from the home
// page and Settings. "Set me up again" (talk) is the interview alone: it suggests companions, and only Hire adds one.
type Send = (op: string, data?: Record<string, unknown>) => void
type Step = "welcome" | "connect" | "create" | "first"
const FLOW: Step[] = ["welcome", "connect", "create", "first"]
const EASE = [.22, 1, .36, 1] as const
// The companion pops in: squashes as it lands, stretches up, settles.
const POP: Record<"from" | "to" | "rest", TargetAndTransition> & { timing: Transition } = { from: { scaleX: .3, scaleY: .3, y: 60, opacity: 0 }, to: { scaleX: [.3, 1.16, .92, 1.03, 1], scaleY: [.3, .84, 1.1, .98, 1], y: [60, 0, -16, 0, 0], opacity: [0, 1, 1, 1, 1] },
 rest: { scaleX: 1, scaleY: 1, y: 0, opacity: 1 }, timing: { duration: .85, times: [0, .38, .62, .82, 1], ease: "easeOut" } }

// The welcome shows one neutral companion, a plain oat bean, until the user picks a look.
const NEUTRAL = v2({ form: "bean", color: "#ddd4c6", second: "#ddd4c6", eye: "round", mouth: "smile", top: "none", finish: "matte" })
const THEMES = [["Light", Sun], ["Dark", Moon], ["System", Monitor]] as const
const LENGTHS: [ReplyLength, string, string][] = [["short", "Short", "A few lines, answer first"], ["balanced", "Balanced", "As long as the task needs"], ["detailed", "Detailed", "Full answers with the reasoning"]]
export const SAMPLE = "https://sample.still.internal/compare.html"
const SAMPLE_TASK = `Open ${SAMPLE} and compare the three backpacks on it for a weekend trip: price, weight and what reviewers say. Tell me which one you'd pick and why. It's a sample page from Still, so there's nothing to buy.`
const newId = () => "c" + Math.random().toString(36).slice(2, 11)
const seenIntro = () => { try { return !!localStorage.getItem("still.intro") } catch { return false } }
const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url } }
// How far the welcome got: kept until it finishes, so closing Still partway through picks up at the same step with the
// same answers. The companion's id is made once and kept, so hiring again after a restart updates it, never a second one.
type Kept = { step: number; id: string; name: string; look: Look; goal: string; length: "" | ReplyLength; reviewing: boolean; job: string; skills: string[]; from: string; hired: boolean; task: string; typed: string; chatted: boolean; plain: string[] }
const KEPT = "still.onboarding" // 2.10; the old welcome's answers ("still.welcome") don't carry over
const readKept = (): Partial<Kept> => { try { return JSON.parse(localStorage.getItem(KEPT) ?? "{}") ?? {} } catch { return {} } }
/// "Create your companion" on the new tab page: the welcome again, from Connect.
export const startCreating = () => { try { localStorage.setItem(KEPT, JSON.stringify({ step: FLOW.indexOf("connect") })) } catch { /* no storage: from the start */ } }
// "Nothing right now", "no thanks", "later": a no typed as the first task is a skip, not a task.
const NO = /^(?:no|nope|nah|nothing|none|not yet|not really|not (?:right )?now|later|maybe later|skip(?: it)?|pass|all good|i'?m (?:good|fine|ok(?:ay)?)|n ?a)(?: (?:thanks?|thank you|for now|right now|now|yet))*$/
export const isNo = (text: string) => NO.test(text.toLowerCase().replace(/[^a-z' ]/g, " ").replace(/\s+/g, " ").trim())
// "" = not checked yet
const statusOf = (h?: AiState["harnesses"][number]) => !h ? "" : h.status || (h.installed ? "" : "missing")

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

/// Connect: the AI app picked in the list, and what it needs next. Nothing installs or signs in until the user asks, and a cancelled
/// or failed install or sign-in stays here with Retry.
function Connect({ ai, send }: { ai: AiState; send: Send }) {
 const h = ai.harnesses.find(x => x.id === ai.harness), s = statusOf(h), maker = h?.maker || h?.app // apps added by hand have no maker
 const cancel = <Button variant="ghost" size="sm" onClick={() => send("aiSetupCancel")}>Cancel</Button>
 // A long list pushes the card below the fold: picking an app, or its state changing, brings the card into view.
 const card = useRef<HTMLDivElement>(null), seen = useRef(`${ai.harness}:${s}`)
 useEffect(() => { if (seen.current !== `${ai.harness}:${s}`) { seen.current = `${ai.harness}:${s}`; reveal(card.current) } }, [ai.harness, s])
 return <>
  <AiPicker ai={ai} onPick={id => send("aiHarness", { harness: id, waitToSignIn: true })} />
  <div className="ob-connect" aria-live="polite" ref={card}>
   {!h ? <p className="ob-note">Pick the AI app you use.</p>
    : s === "installing" ? <div className="ob-status" role="status"><Spinner /><span><b>Installing {h.app}…</b><small>{ai.setup.line || "This usually takes about a minute. Then it opens the sign-in."}</small></span>{cancel}</div>
    : s === "signingIn" ? <div className="ob-status" role="status"><Spinner /><span><b>{ai.setup.url ? "Approve it in the new window" : `Opening ${maker}'s sign-in…`}</b>
      <small>{ai.setup.code ? `The page should show this code: ${ai.setup.code}` : `You sign in on ${maker}'s own site. Still never sees your password.`}</small></span>{cancel}</div>
    : s === "missing" ? <div className="ob-status is-ask"><span><b>Install and sign in</b>
      {h.installer ? <small>{h.name} needs {h.maker}'s app, {h.app}. Still can install it for you with {h.maker}'s official installer from {host(h.installer)}, then open {h.maker}'s sign-in. Or run this in {MAC ? "Terminal" : "PowerShell"} yourself: <code>{h.installCommand}</code></small>
       : <small>{h.app} isn't on this computer yet, and Still can't install it for you. Get it from {host(h.site)}{h.installCommand ? <> or run this in {MAC ? "Terminal" : "PowerShell"}: <code>{h.installCommand}</code></> : ""}, then check again.</small>}</span>
      {h.installer ? <Button size="sm" onClick={() => send("aiInstall")}>Install and sign in</Button> : <Button size="sm" variant="outline" onClick={() => send("aiCheck")}>Check again</Button>}</div>
    : s === "signedOut" ? <div className="ob-status is-ask"><span><b>Sign in</b>
      <small>{h.terminalSignIn ? <>{h.app} signs in from a terminal. Run this in {MAC ? "Terminal" : "PowerShell"}, sign in with your plan, then check again: <code>{h.terminalSignIn}</code></> : h.maker ? `${h.app} is installed. Sign in once with your ${h.maker} plan, on ${h.maker}'s own site.` : `${h.app} is installed. Sign in once with your plan.`}</small></span>
      {h.terminalSignIn ? <Button size="sm" variant="outline" onClick={() => send("aiCheck")}>Check again</Button> : <Button size="sm" onClick={() => send("aiLogin")}>Sign in</Button>}</div>
    : s === "needsKey" || s === "badKey" ? <p className="ob-note">{h.name} uses an API key. Add it in Settings, under Models, after setup, or pick an app you're signed in to.</p>
    : <p className="ob-ready"><Check />{h.name} is ready, {h.api ? (ai.apis?.providers.find(p => p.id === h.id)?.noKey ? "with no key needed" : "with your API key") : "signed in with your plan"}.</p>}
   {ai.error && <div className="ob-status is-error" role="alert"><span><small>{ai.error}</small></span><Button size="sm" variant="outline" onClick={() => send(s === "missing" && h?.installer ? "aiInstall" : s === "signedOut" && !h?.terminalSignIn ? "aiLogin" : "aiCheck")}><RotateCw />Retry</Button></div>}
  </div>
  <details className="ob-api"><summary>Use an API instead</summary><QuickApi api={ai.apis} send={send} /></details>
  <details className="ob-how"><summary>How this works</summary>
   <p>Still runs {h ? h.app : "your AI app"} on this computer and sends it what you ask, with the pages you share.</p>
   <p>It counts toward your {h?.maker || "AI"} plan, the same as using {h ? h.app : "the app"} yourself. Still doesn't add a plan of its own.</p>
   <p>What you send goes to {h?.maker || "your AI provider"}. Still keeps your chats and your companion's memory on this computer.</p>
   <p>Your companion asks you before buying anything, sending messages or posts, or deleting things. Private tabs, passwords and cookies are never available.</p>
  </details>
 </>
}

/// What the welcome leaves for later, on the new tab page until it's dismissed: bring things over from another browser,
/// open links in Still, and where the tabs go.
export function GetStarted({ isDefault, layout, send, onImport }: { isDefault?: boolean; layout?: string; send: Send; onImport: () => void }) {
 const [gone, setGone] = useState(() => { try { return !!localStorage.getItem("still.getStarted") } catch { return false } })
 if (gone) return null
 const close = () => { setGone(true); try { localStorage.setItem("still.getStarted", "1") } catch { /* no storage: back next time */ } }
 return <section className="get-started" aria-label="Get started">
  <b>Get started</b>
  <button onClick={onImport}><Download />Import from another browser</button>
  <button disabled={isDefault} onClick={() => send("defaultBrowser")}>{isDefault ? <><Check />Still opens your links</> : <><Globe2 />Open links in Still</>}</button>
  <button onClick={() => send("preference", { key: "tabLayout", value: layout === "Modern" ? "Classic" : "Modern" })}><PanelLeft />{layout === "Modern" ? "Tabs across the top" : "Tabs down the side"}</button>
  <button className="get-started-x" aria-label="Hide Get started" title="Hide" onClick={close}><X /></button>
 </section>
}

type Change = { key: string; label: string; value: string; undone: boolean; editable?: boolean; hire?: boolean }
// Make mode: what the new companion wrote about itself after the chat.
type Made = { help: string; instructions: string[]; summary: string[]; length: string }
type Setup = { busy: boolean; error: string; done: boolean; turns: { role: string; text: string; options?: string[] }[]; changes: Change[]; made?: Made | null } | null
const sentence = (t: string) => { t = t.trim().replace(/\s+/g, " "); t = t.charAt(0).toUpperCase() + t.slice(1); return !t || /[.!?]$/.test(t) ? t : t + "." }
// Its instructions from the chat, in the same shape as the ones Still writes, ending with the rule that it asks first.
const written = (help: string, lines: string[]) => (sentence(help) + "\n\nHow you work:\n" + [...lines, "Ask me before you send, post, buy or delete anything."].map(l => "- " + l.replace(/^[-*•]\s*/, "")).join("\n")).slice(0, 1000)
const SKIP = "(skip)", ENOUGH = "That's enough, set me up with what you know."
/// "Set me up again": the companion gets to know the user, one follow-up at a time, until they say that's enough; any
/// question can be skipped. Then what it set up, in groups, each with an undo, and the wording ones editable. Still's
/// library goes along, so it can suggest the companions that fit their work: each one joins only on Hire.
/// Making: the Create step's chat. A new companion asks what the user wants help with, in plain words, then writes its
/// own instructions (make.md), which go to `onMade` to check before Hire. Nothing is saved or changed by the chat.
function Interview({ who, send, onClose, onDone, making, onMade }: { who: Companion; send: Send; onClose: () => void; onDone?: (done: boolean, first: string) => void; making?: boolean; onMade?: (made: Made) => void }) {
 const [s, setS] = useState<Setup>(null)
 const [text, setText] = useState("")
 const [editing, setEditing] = useState<[string, string] | null>(null) // the change being reworded: key, text
 const log = useRef<HTMLDivElement>(null)
 useEffect(() => {
  const got = (e: MessageEvent) => { if (e.data?.kind === "setup") setS(e.data.data) }
  window.chrome?.webview?.addEventListener("message", got)
  send("setupStart", making ? { companion: who.id, making: who.name } : { companion: who.id, library: SETUP_CREW.map(p => ({ ...fromPremade(p), role: p.role, area: p.area })) })
  return () => window.chrome?.webview?.removeEventListener("message", got)
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }) }, [s?.turns.length, s?.busy, s?.done])
 const first = s?.changes.find(c => c.key === "first" && !c.undone)?.value ?? ""
 useEffect(() => onDone?.(!!s?.done, first), [s?.done, first]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { if (making && s?.done && s.made) onMade?.(s.made) }, [s?.done]) // eslint-disable-line react-hooks/exhaustive-deps
 const waiting = !s || s.busy
 const last = s?.turns.at(-1)
 const kept = useDraft<HTMLInputElement>("setup." + who.id) // what's typed to them is kept as a draft until it's sent
 const answer = (t: string) => { if (!t.trim() || waiting) return; kept.done(); send("setupAnswer", { text: t.trim() }); setText("") }
 const say = (placeholder: string) => <form className="ob-say" onSubmit={e => { e.preventDefault(); answer(text) }}>
  {kept.hint}
  <input ref={kept.ref} {...kept.props} aria-label={placeholder} placeholder={placeholder} maxLength={2000} value={text} onChange={e => setText(e.target.value)} />
  <Button type="submit" size="icon-sm" aria-label="Send" disabled={!text.trim() || waiting}><ArrowUp /></Button>
 </form>
 const row = (c: Change) => <li key={c.key} className={cn(c.undone && "is-undone")}>
  {editing?.[0] === c.key ? <form className="ob-edit" onSubmit={e => { e.preventDefault(); if (editing[1].trim()) send("setupEdit", { key: c.key, value: editing[1].trim() }); setEditing(null) }}>
   <b>{c.label}</b>
   <textarea autoFocus aria-label={c.label} rows={Math.min(6, Math.max(2, editing[1].split("\n").length + 1))} maxLength={1000} value={editing[1]} onChange={e => setEditing([c.key, e.target.value])} />
   <div><Button type="submit" size="sm" disabled={!editing[1].trim()}>Save</Button><Button type="button" variant="ghost" size="sm" onClick={() => setEditing(null)}>Cancel</Button></div>
  </form> : <>
   <span><b>{c.label}</b><small>{c.value}</small></span>
   {c.undone ? <em>{c.hire ? "Not hired" : "Undone"}</em> : c.hire ? <>
    <button className="is-hire" onClick={() => send("setupHire", { key: c.key })}><UserPlus />Hire</button>
    <button onClick={() => send("setupUndo", { key: c.key })}>No thanks</button>
   </> : <>
    {c.editable && <button onClick={() => setEditing([c.key, c.value])}><Pencil />Edit</button>}
    <button onClick={() => send("setupUndo", { key: c.key })}><Undo2 />Undo</button>
   </>}
  </>}
 </li>
 const team = /^(suggest|hire|focus|memory|routine)\b/
 const groups = s ? ([["Your team", (k: string) => team.test(k)], ["Your Still", (k: string) => !team.test(k) && k !== "first"], ["First up", (k: string) => k === "first"]] as const)
  .map(([title, has]) => [title, s.changes.filter(c => has(c.key))] as const).filter(([, list]) => list.length) : []
 return <div className={cn("ob-interview", s?.done && "is-done")}>
  <div className="ob-chat" ref={log} aria-live="polite" onScroll={fadeTop}>
   {s?.turns.map((t, i) => <motion.p key={i} className={cn("ob-bubble", t.role === "user" && "is-you", t.text === SKIP && "is-skip")} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, ease: EASE }}>
    {t.role === "user" && t.text === SKIP ? "Skipped" : t.role === "user" && t.text === ENOUGH ? "That's enough" : t.text}</motion.p>)}
   {waiting && !s?.error && <p className="ob-bubble is-typing" aria-label={`${who.name} is typing`}><i /><i /><i /></p>}
  </div>
  {s?.error ? <div className="ob-fallback"><p>{s.error}</p><Button size="sm" onClick={onClose}>{making ? "Type it instead" : "Close"}</Button></div>
   : s?.done && !making ? <motion.div className="ob-summary" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .3, ease: EASE }}>
    <h3>Here's what I set up for you</h3>
    {groups.length ? groups.map(([title, list]) => <section key={title}><h4>{title}</h4><ul>{list.map(row)}</ul></section>)
     : <p className="ob-note">Nothing needed changing, so everything stays as it was.</p>}
    <div className="ob-summary-foot">{s.changes.some(c => !c.undone && !c.hire) && <Button variant="ghost" size="sm" onClick={() => send("setupUndo", { key: "" })}><Undo2 />Undo everything</Button>}
     <small>You can change any of it later in each companion's profile and in Settings.</small></div>
    {say(`Tell ${who.name} what to change`)}
   </motion.div>
   : <>
    {last?.role !== "user" && !!last?.options?.length && <div className="ob-chips">{last.options.map(o => <button key={o} disabled={waiting} onClick={() => answer(o)}>{o}</button>)}</div>}
    {say("Type your answer")}
    {!!s?.turns.length && <div className="ob-interview-foot">
     <button disabled={waiting} onClick={() => answer(SKIP)}><SkipForward />Skip this one</button>
     <button disabled={waiting || s.turns.length < 2} onClick={() => answer(ENOUGH)}><Check />{making ? "That's enough" : "That's enough, set me up"}</button>
    </div>}
   </>}
 </div>
}

export function Welcome({ theme, talk, ai, noAi, sounds = true, soundsBlocked = "", send }: { theme?: string; talk?: boolean; ai?: AiState; noAi?: boolean; sounds?: boolean; soundsBlocked?: string; send: Send }) {
 const reduce = useReducedMotion()
 const [again] = useState(!!talk) // "set me up again": the interview alone
 const [kept] = useState(() => again ? {} : readKept())
 // The companion the user had before (null until the AI state arrives): the one "set me up again" talks with.
 const had = useRef<Companion | undefined | null>(null)
 if (had.current === null && ai) had.current = ai.companions?.[0]
 const [step, setStep] = useState(Math.min(kept.step ?? 0, FLOW.length - 1))
 const [id] = useState(() => kept.id ?? newId())
 const [name, setName] = useState(kept.name ?? "")
 const [look, setLook] = useState<Look>(() => kept.look ?? NEUTRAL)
 const [goal, setGoal] = useState(kept.goal ?? "")
 const [length, setLength] = useState<"" | ReplyLength>(kept.length ?? "")
 const [reviewing, setReviewing] = useState(kept.reviewing ?? false)
 const [job, setJob] = useState(kept.job ?? "")
 const [skills, setSkills] = useState<string[]>(kept.skills ?? [])
 const [from, setFrom] = useState(kept.from ?? "") // what the instructions were made from: a changed goal makes them again
 const [chatting, setChatting] = useState(false) // Create's chat is open
 const [chatted, setChatted] = useState(kept.chatted ?? false) // it ran (or couldn't): from then on the goal is typed
 const [plain, setPlain] = useState<string[]>(kept.plain ?? []) // what it will do, in the user's words, from the chat
 const [hired, setHired] = useState(kept.hired ?? false)
 const [joined, setJoined] = useState(false)
 const [task, setTask] = useState(kept.task ?? "")
 const [typed, setTyped] = useState(kept.typed ?? "")
 const [styling, setStyling] = useState(false)
 const [talked, setTalked] = useState(false) // the interview is done
 const [firstUp, setFirstUp] = useState("") // what the interview heard they want help with first
 const [hadIntro] = useState(() => !again && !seenIntro()) // once, on the first run; About can replay it
 const [introOn, setIntroOn] = useState(hadIntro)
 const [introAt, setIntroAt] = useState<{ x: number; y: number }>()
 const [woke, setWoke] = useState(false)
 const [gesture, setGesture] = useState<[string, number]>(() => hadIntro ? ["wake", 1] : ["", 0])
 const [talking, setTalking] = useState(true)
 const [leaving, setLeaving] = useState<{ x: number; y: number; scale: number; opacity: number } | null>(null)
 const mascotRef = useRef<HTMLDivElement>(null)
 const [width, height] = useWindowSize()
 const at = FLOW[step]
 const who = again ? had.current ?? undefined : undefined
 const shown = again ? (who ? lookOf(who) : NEUTRAL) : look
 const named = name.trim()
 const intro = !again && step === 0 && !reduce ? hadIntro ? .45 : .75 : 0 // the hello waits for the companion to pop in, or to glide in after the intro
 const size = Math.round(Math.min(520, Math.max(200, Math.min(height / 2.3, width / 4))))
 const harness = ai?.harnesses.find(h => h.id === ai.harness), status = statusOf(harness)
 const aiReady = !!harness?.installed && !["missing", "signedOut", "needsKey", "badKey", "installing", "signingIn"].includes(status)
 const canAi = !noAi && !!ai
 const companion: Companion = { id, name: named, face: "", color: "", job: job.trim(), skills, look: lookKey(look), mode: "default", ...(length && { length }) }
 const tasks = starters(INTERESTS.filter(i => goal.toLowerCase().includes(i.toLowerCase().split(" ")[0])), undefined, 3)
 const keep = (over: Partial<Kept> = {}) => {
  if (again) return
  try { localStorage.setItem(KEPT, JSON.stringify({ step, id, name, look, goal, length, reviewing, job, skills, from, hired, task, typed, chatted, plain, ...over })) } catch { /* no storage: setup starts over next time */ }
 }
 useEffect(() => { if (!leaving) keep() }, [step, name, look, goal, length, reviewing, job, skills, from, hired, task, typed, chatted, plain]) // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(() => { try { localStorage.removeItem("still.welcome") } catch { /* no storage */ } }, [])
 useEffect(() => { if (introOn) return; setTalking(true); const t = setTimeout(() => setTalking(false), 1700); return () => clearTimeout(t) }, [at, reviewing, introOn])
 useEffect(() => {
  warm("jingle")
  if (at === "connect") send("aiCheck") // picked up after a restart: what's installed may have changed
  if (hadIntro) return
  const t = setTimeout(() => setGesture(["wave", Date.now()]), again || reduce ? 0 : 650); return () => clearTimeout(t)
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 // While the intro plays, the companion stands in the middle of the window, then glides to its place.
 useLayoutEffect(() => {
  const r = hadIntro && mascotRef.current?.getBoundingClientRect()
  if (r) setIntroAt({ x: innerWidth / 2 - (r.left + r.width / 2), y: innerHeight / 2 - 30 - (r.top + r.height / 2) })
 }, []) // eslint-disable-line react-hooks/exhaustive-deps
 const react = (g: string) => setGesture([g, Date.now()])
 const endIntro = (skipped: boolean) => {
  setIntroOn(false)
  try { localStorage.setItem("still.intro", "1") } catch { /* no storage: it may play again */ }
  if (skipped) react("wave")
 }
 const sound = (on: boolean) => { setSounds(on && !soundsBlocked); send("preference", { key: "sounds", value: String(on) }) }

 // The end: with a companion, it flies to its place in the browser (the chat it just started, or the home page) while
 // everything else fades away. Without one, the browser is simply there.
 const finish = (firstTask?: string) => {
  if (leaving) return
  if (!again) try { localStorage.removeItem(KEPT) } catch { /* no storage */ }
  send("setupEnd")
  const lead = again ? who?.id : hired ? id : ""
  if (firstTask && lead) send("aiSend", { text: firstTask, home: true, companion: lead })
  if (!lead || reduce) { send("welcomeDone"); return }
  if (!again) try { localStorage.setItem("still.tour", "1") } catch { /* no storage: no tour */ }
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
 const go = (to: number) => { setStep(to); setReviewing(false); setChatting(false); if (FLOW[to] === "connect") send("aiCheck") }
 // With an AI app ready, the companion asks what to help with in a chat; without one (or once that ran), it's typed.
 const ask = aiReady && !chatted
 const made = (m: Made) => {
  const help = m.help || goal, g = generate(help, "", LIBRARY, ROLE_TEXT)
  setGoal(help); setFrom(help.trim()); setSkills(g.skills); setPlain(m.summary)
  setJob(m.instructions.length ? written(help, m.instructions) : g.job)
  if (m.length) setLength(m.length as ReplyLength)
  setChatted(true); setChatting(false); setReviewing(true); send("setupEnd")
 }
 // Hire: kept as hired before anything is sent, so a restart right after never hires twice (and the same id would only
 // update it anyway). Saving again after going back updates the same companion.
 const hire = () => {
  keep({ hired: true, step: FLOW.indexOf("first"), reviewing: false })
  send("companionSave", companion); send("companionMain", { id })
  if (!hired) { setJoined(true); react("hired") } else go(FLOW.indexOf("first"))
  setHired(true)
 }
 const ready = at === "welcome" ? canAi : at === "connect" ? aiReady : at === "create" ? !!named && !chatting && (!reviewing || !!job.trim()) : aiReady && !!(task || typed.trim() && !isNo(typed))
 const next = () => {
  if (!ready) return
  if (at === "create" && !reviewing && ask) { setChatting(true); return }
  if (at === "create" && !reviewing) {
   if (!job || from !== goal.trim()) { const g = generate(goal, "", LIBRARY, ROLE_TEXT); setJob(g.job); setSkills(g.skills); setFrom(goal.trim()); setPlain([]) }
   setReviewing(true); return
  }
  if (at === "create") { hire(); return }
  if (at === "first") { finish(typed.trim() || task); return }
  go(step + 1)
 }
 const back = () => at === "create" && chatting ? (setChatting(false), send("setupEnd")) : at === "create" && reviewing ? setReviewing(false) : go(step - 1)

 const mood: MascotState = introOn ? "idle" : talking ? "talking" : "idle"
 const slide = reduce ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } } : { initial: { opacity: 0, x: 24 }, animate: { opacity: 1, x: 0 }, exit: { opacity: 0, x: -18 } }
 const soundOn = sounds && !soundsBlocked
 const nameOf = named || "your companion"

 return <div className={cn("welcome ob", leaving && "is-leaving", introOn && "is-intro")} role="dialog" aria-modal="true" aria-label="Set up Still">
  <header className="ob-top">
   <span className="still-mark is-small" aria-hidden><i /><i /></span>
   {!again && <div className="ob-dots" role="progressbar" aria-valuemin={1} aria-valuemax={FLOW.length} aria-valuenow={step + 1} aria-label={`Step ${step + 1} of ${FLOW.length}`}>{FLOW.map((s, i) => <i key={s} className={cn(i === step && "is-on", i < step && "is-done")} />)}</div>}
   <button className="ob-sound" aria-pressed={!soundOn} aria-label="Mute" title={soundsBlocked || (soundOn ? "Mute" : "Unmute")} disabled={!!soundsBlocked} onClick={() => sound(!sounds)}>{soundOn ? <Volume2 /> : <VolumeX />}</button>
   <div className="ob-theme" role="radiogroup" aria-label="Theme">{THEMES.map(([k, Icon]) => <button key={k} role="radio" aria-checked={(theme ?? "System") === k} aria-label={k} title={k === "System" ? (MAC ? "Match your Mac" : "Match Windows") : k} onClick={() => send("preference", { key: "theme", value: k })}><Icon /></button>)}</div>
  </header>
  <main className="ob-stage" onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !again && !(e.target as HTMLElement).closest("button,textarea,form,details")) { e.preventDefault(); next() } }}>
   <motion.div ref={mascotRef} className="ob-companion" style={{ "--hue": shown.color } as CSSProperties} animate={leaving ?? (introOn && introAt ? { ...introAt, scale: 1, opacity: 1 } : { x: 0, y: 0, scale: 1, opacity: 1 })}
    transition={introOn ? { duration: 0 } : { duration: .8, ease: [.6, 0, .2, 1] }}>
    <motion.div className="ob-pop" initial={intro && !hadIntro ? POP.from : false} animate={intro && !hadIntro ? POP.to : POP.rest} transition={POP.timing}>
     <Mascot look={shown} size={size} state={mood} follow={!introOn} gesture={gesture[0]} gestureAt={gesture[1]} className={cn(introOn && "intro-body", woke && "is-on")} />
    </motion.div>
    {!again && (at === "create" || at === "first") && named && <motion.b className="ob-name" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>{named}</motion.b>}
   </motion.div>
   <AnimatePresence mode="wait" initial={false}>
    <motion.section key={(again ? "again" : at + (reviewing ? "-review" : chatting ? "-chat" : "")) + (introOn ? "-held" : "")} className="ob-talk" onScroll={fadeTop} {...slide} transition={{ duration: reduce ? .01 : .26, ease: EASE }}>
     {introOn ? null : again ? (who ? <Interview who={who} send={send} onClose={() => finish()} onDone={(done, first) => { setTalked(done); setFirstUp(first) }} /> : null) : <>
     {at === "welcome" && <>
      <motion.h1 className="ob-headline" initial={{ opacity: 0, y: reduce ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: reduce ? 0 : intro, duration: reduce ? .01 : .35, ease: EASE }}>A little less work. A little more still.</motion.h1>
      <Bubbles from={intro} lines={canAi ? ["Still is a browser with a companion that works in your tabs with you.", "It runs on the AI app you already use, signed in with your own plan. Let's make your companion. It takes a couple of minutes."]
       : ["Still is an open-source browser. AI apps on this computer can work in it, right next to your tabs."]} />
     </>}
     {at === "connect" && ai && <>
      <Bubbles lines={["First, which model should your companion think with?", "Pick the AI app you already use. Still runs it on this computer, signed in with your own plan."]} />
      <Reveal after={2}><Connect ai={ai} send={send} /></Reveal>
     </>}
     {at === "create" && chatting && <Interview making who={{ ...companion, name: nameOf }} send={send} onClose={() => { setChatted(true); setChatting(false) }} onMade={made} />}
     {at === "create" && !reviewing && !chatting && <>
      <Bubbles lines={["Let's make your companion.", ask ? `Give them a name and a look. Then ${named || "they"} will ask what you'd like help with.` : "Give them a name and a look, and tell them what you'd like help with."]} />
      <Reveal after={2}><div className="ob-build">
       <div className="ob-row"><span>Name</span><div className="ob-name-box"><input autoFocus aria-label="Name your companion" placeholder="Their name" maxLength={24} value={name} onChange={e => setName(e.target.value)} /></div></div>
       <div className="ob-row is-top"><span>Look</span><div>
        <div className="ob-faces" role="radiogroup" aria-label="Look">{STARTS.map(([label, l]) => <button key={label} role="radio" aria-checked={lookKey(look) === lookKey(l)} aria-label={label} title={label} onClick={() => { setLook(l); react("happy") }}><LookThumb look={l} /></button>)}</div>
        <div className="ob-build-actions">
         <Button variant="outline" size="sm" onClick={() => { setLook(surprise()); react("pop") }}><Dices />Surprise me</Button>
         <Button variant="ghost" size="sm" onClick={() => setStyling(true)}><Palette />Customize</Button>
        </div>
       </div></div>
       {!ask && <><div className="ob-row is-top"><span>Help with</span><div className="ob-name-box"><textarea aria-label="What should they help with?" placeholder="What should they help you with? For example: keep my inbox under control and plan my week." rows={3} maxLength={600} value={goal} onChange={e => setGoal(e.target.value)} /></div></div>
       <div className="ob-row is-top"><span>Replies</span><div className="ob-chips" role="radiogroup" aria-label="Reply length">{LENGTHS.map(([k, label, sub]) =>
        <button key={k} role="radio" aria-checked={length === k} aria-pressed={length === k} title={sub} onClick={() => setLength(length === k ? "" : k)}>{length === k && <Check />}{label}</button>)}<small className="ob-note">Optional</small></div></div></>}
      </div></Reveal>
      {styling && <LookEditor companion={{ ...companion, name: nameOf }} onClose={() => setStyling(false)} onSave={k => { setLook(lookOf({ ...companion, look: k })); setStyling(false); react("happy") }} />}
     </>}
     {at === "create" && reviewing && <>
      <Bubbles lines={[`Here's what ${nameOf} will do for you.`, "You can change it any time, here or later in their profile."]} />
      <Reveal after={2}><div className="ob-build ob-review">
       {(plain.length > 0 || !!goal.trim()) && <ul className="ob-plain">{(plain.length ? plain : [sentence(goal)]).map(l => <li key={l}><Check />{l}</li>)}</ul>}
       {skills.length > 0 && <div><b>Skills</b><div className="ob-chips is-static">{skills.map(k => <span key={k}>{LIBRARY.find(x => x.id === k)?.name ?? k}</span>)}</div></div>}
       {length && <p className="ob-note">Replies: {LENGTHS.find(([k]) => k === length)?.[1]}</p>}
       <details className="ob-more"><summary>Edit instructions</summary><div className="ob-name-box"><textarea aria-label="Instructions" rows={8} maxLength={1000} value={job} onChange={e => setJob(e.target.value)} /></div></details>
      </div></Reveal>
     </>}
     {at === "first" && <>
      <Bubbles lines={[`${nameOf} is ready. What should we start with?`, "Pick one, try the sample page, or say it in your own words. You'll see the work happen, and you can jump in any time."]} />
      <Reveal after={2}>
       {!aiReady && <div className="ob-preview" role="note"><b>Preview</b>
        <p>{harness ? `${harness.name} isn't connected yet` : "No model is connected yet"}, so {nameOf} can't start. Once it is, {nameOf} opens the page in a tab, reads it and answers in the chat.</p>
        <div><Button size="sm" onClick={() => go(FLOW.indexOf("connect"))}>Connect</Button><Button size="sm" variant="ghost" onClick={() => send("aiCheck")}><RotateCw />Retry</Button></div></div>}
       <div className="ob-tasks" role="radiogroup" aria-label="First task">
        <button role="radio" aria-checked={task === SAMPLE_TASK} onClick={() => { setTask(task === SAMPLE_TASK ? "" : SAMPLE_TASK); setTyped("") }}><i /><span><b>Compare three backpacks</b><small><FileSearch />Sample page from Still. The products are made up.</small></span></button>
        {tasks.map(([label, prompt]) => <button key={label} role="radio" aria-checked={task === prompt} onClick={() => { setTask(task === prompt ? "" : prompt); setTyped("") }}><i />{label}</button>)}
       </div>
       <div className="ob-name-box"><textarea aria-label="Your own task" rows={2} placeholder="Or type your own" value={typed} onChange={e => { setTyped(e.target.value); setTask("") }} /></div>
      </Reveal>
     </>}
     </>}
    </motion.section>
   </AnimatePresence>
  </main>
  <motion.footer className="ob-foot" initial={intro ? { opacity: 0, y: 18 } : false} animate={introOn ? { opacity: 0, y: 18 } : { opacity: 1, y: 0 }} transition={{ delay: introOn ? 0 : intro ? intro + 1.2 : 0, duration: .35, ease: EASE }}>
   {again ? <>
    <span className="flex-1" />
    {!talked && <button className="ob-not-now" onClick={() => finish()}>Not now</button>}
    <Button className="ob-next" disabled={!talked} onClick={() => finish(firstUp || undefined)}>Done<CornerDownLeft /></Button>
   </> : <>
    {step > 0 ? <Button variant="ghost" onClick={back}><ArrowLeft />Back</Button> : <span />}
    <span className="flex-1" />
    <button className="ob-browse" onClick={() => finish()}>{hired ? `Not now, just browse` : "Just browse for now"}</button>
    {at === "connect" && !aiReady && <button className="ob-not-now" onClick={() => go(step + 1)}>Set up later</button>}
    {(at !== "welcome" || canAi) && <Button className="ob-next" disabled={!ready} onClick={next}>{at === "welcome" ? "Create your companion" : at === "create" && reviewing ? (hired ? "Save changes" : `Hire ${nameOf}`) : at === "first" ? "Let's go" : "Continue"}<CornerDownLeft /></Button>}
   </>}
  </motion.footer>
  {joined && <JoinedCard companion={companion} main onStart={() => { setJoined(false); go(FLOW.indexOf("first")) }} onLater={() => { setJoined(false); go(FLOW.indexOf("first")) }} />}
  {introOn && <IntroLayer at={{ x: innerWidth / 2, y: innerHeight / 2 - 30, r: size / 2 }} hue={shown.color} reduced={!!reduce} sound={soundOn} onSound={sound}
   live={() => !!mascotRef.current?.querySelector("canvas[data-live]")} onStart={() => setWoke(true)} onEnd={endIntro} />}
 </div>
}
