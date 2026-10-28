import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react"
import { AnimatePresence, motion } from "motion/react"
import { ArrowLeft, Bot, Check, CornerDownLeft, Dices, Download, Globe2, Palette } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AiPicker, type AiState } from "./AiSidebar"
import { NAMES, lookOf, type Companion } from "./Buddy"
import { BLANK, BODY_COLORS, FACES, lookKey, surprise, type Look } from "./look"
import { FaceSwatch, LookEditor } from "./LookEditor"
import { Mascot, type MascotState } from "./Mascot"

// First run, full window: your companion is a plain shape that grows a color, a face and a name while it walks you
// through setup. Every step can be skipped. It ends by starting a first task in a chat.
type Send = (op: string, data?: Record<string, unknown>) => void
const STEPS = ["hello", "import", "ai", "helper", "you", "interests", "layout", "charge", "start"] as const
type Step = (typeof STEPS)[number]

const COLORS = ["#f4c2a8", "#e5876a", "#f3b7c1", "#f2c66b", "#bcd98c", "#7fb39b", "#8ed3c7", "#8fb8e8", "#6f8fd0", "#b9a5e6", "#c9a58a", "#5b6170"].map(hex => BODY_COLORS.find(c => c[0] === hex) ?? [hex, hex])
const INTERESTS = ["Cooking", "Travel", "Deals and shopping", "News", "Sports", "Music", "Movies and shows", "Games", "Coding", "Design", "Health and fitness", "Money", "Learning", "Home and garden"]
// First tasks, the ones that match what you're into first.
const TASKS: [string, string, string][] = [
 ["Cooking", "Find a dinner I can make tonight", "Find me three easy, well-reviewed dinner recipes I can make tonight with normal pantry stuff. Show them as a short table."],
 ["Travel", "Plan a weekend away", "Help me plan a weekend away. Ask me where I'm starting from and my budget, then suggest three places with a rough plan for each."],
 ["Deals and shopping", "Find the best price for something", "Help me find the best price for something. Ask me what I'm shopping for, then compare a few stores in a table."],
 ["News", "Catch me up on today's news", "Catch me up on today's top news in a few short bullet points, each with a link."],
 ["Sports", "Catch me up on my team", "Ask me which team I follow, then tell me how their last game went and when they play next."],
 ["Music", "Find new music I'd like", "Ask me for two artists I love, then find five newer artists I might like, with a song to start with for each."],
 ["Movies and shows", "Pick something to watch tonight", "Help me pick something to watch tonight. Ask what I'm in the mood for, then suggest three options with where to stream them."],
 ["Games", "Find a game to play next", "Ask me what games I've enjoyed lately, then suggest three I might like, with prices."],
 ["Coding", "Explain a tech topic simply", "Ask me which tech topic I've been meaning to understand, then explain it simply with one good link to read next."],
 ["Health and fitness", "Make a simple workout plan", "Ask me how much time I have and what equipment I've got, then make a simple one-week workout plan."],
 ["Money", "Compare a few savings accounts", "Compare a few well-known savings accounts available where I live. Ask me my country first, then show rates in a table."],
 ["Learning", "Find a free course to start", "Ask me what I want to learn, then find three good free courses or guides to start with."],
 ["", "Sum up a page for me", "Ask me for a link, then open it and sum it up in five bullet points."],
]
const rand = <T,>(list: T[]) => list[Math.floor(Math.random() * list.length)]
const newId = () => "c" + Math.random().toString(36).slice(2, 11)

function Bubbles({ lines }: { lines: ReactNode[] }) {
 return <div className="ob-bubbles">{lines.map((l, i) => <motion.p key={i} className="ob-bubble" initial={{ opacity: 0, y: 8, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay: .12 + i * .38, duration: .28, ease: [.22, 1, .36, 1] }}>{l}</motion.p>)}</div>
}
const Reveal = ({ after = 0, children }: { after?: number; children: ReactNode }) =>
 <motion.div className="ob-answer" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .2 + after * .38, duration: .3, ease: [.22, 1, .36, 1] }}>{children}</motion.div>

function useWindowHeight() {
 const [h, setH] = useState(innerHeight)
 useEffect(() => { const on = () => setH(innerHeight); addEventListener("resize", on); return () => removeEventListener("resize", on) }, [])
 return h
}

export function Welcome({ isDefault, agents, layout, ai, noAi, hidden, send, onImport }: { isDefault?: boolean; agents: boolean; layout?: string; ai?: AiState; noAi?: boolean; hidden?: boolean; send: Send; onImport: () => void }) {
 const flow: readonly Step[] = noAi || !ai ? ["hello", "import", "layout", "charge"] : STEPS
 const [step, setStep] = useState(0)
 const first = ai?.companions?.[0]
 const [c, setC] = useState<Companion>(() => first ?? { id: newId(), name: "", face: "", color: "", job: "", mode: "default" })
 const [look, setLook] = useState<Look>(() => first ? lookOf(first) : BLANK)
 const [grown, setGrown] = useState(first ? 3 : 0) // the helper step: 0 shape, 1 colored, 2 has a face, 3 named
 const [styling, setStyling] = useState(false)
 const [you, setYou] = useState("")
 const [likes, setLikes] = useState<string[]>([])
 const [task, setTask] = useState("")
 const [own, setOwn] = useState("")
 const [allowed, setAllowed] = useState<"" | "yes" | "no">("")
 const [gesture, setGesture] = useState<[string, number]>(["wave", 1])
 const [talking, setTalking] = useState(true)
 const height = useWindowHeight()
 const at = flow[step]
 const name = c.name.trim() || "your helper"
 const hasFace = look.eyes !== "none"
 const names = useMemo(() => [...NAMES].sort(() => Math.random() - .5).slice(0, 4), [])
 const tasks = useMemo(() => { const mine = TASKS.filter(t => likes.includes(t[0])); return [...mine, ...TASKS.filter(t => !mine.includes(t))].slice(0, 3) }, [likes])
 useEffect(() => { setTalking(true); const t = setTimeout(() => setTalking(false), 1700); return () => clearTimeout(t) }, [at])
 const react = (g: string) => setGesture([g, Date.now()])

 const finish = () => { send("welcomeDone"); try { localStorage.setItem("still.tour", "1") } catch { /* no storage: no tour */ } }
 const saveHelper = () => {
  const named = c.name.trim() || rand(NAMES), final = hasFace ? look : { ...surprise(), ...(look.color !== BLANK.color && { color: look.color }) }
  const saved = { ...c, name: named, look: lookKey(final) }
  setC(saved); setLook(final); send("companionSave", saved)
 }
 const saveMemory = () => {
  const keep = (ai?.memory ?? "").split("\n").filter(l => !/^(My name is |Things I'm into: )/.test(l))
  const add = [you.trim() && `My name is ${you.trim()}.`, likes.length && `Things I'm into: ${likes.join(", ").toLowerCase()}.`].filter(Boolean) as string[]
  if (add.length) send("memorySave", { text: [...add, ...keep].join("\n").trim() })
 }
 const go = (to: number) => { setStep(to); if (flow[to] === "ai") send("aiCheck") }
 const next = () => {
  if (at === "helper") saveHelper()
  if (at === "interests" || at === "you") saveMemory()
  if (at === "start") { const text = own.trim() || task; if (text) send("aiSend", { text, home: true, companion: c.id }); finish(); return }
  if (step === flow.length - 1) { finish(); return }
  go(step + 1)
 }
 const skip = () => { if (at === "helper" && !first) saveHelper(); if (step === flow.length - 1) finish(); else go(step + 1) }

 const mood: MascotState = at === "charge" && !allowed ? "needs" : talking ? "talking" : "idle"
 const pickColor = (hex: string) => { setLook(l => ({ ...l, color: hex })); setGrown(g => Math.max(g, 1)); react("admire") }
 const pickFace = (f: Partial<Look>) => { setLook(l => ({ ...l, ...BLANK, color: l.color, ...f, blush: true })); setGrown(g => Math.max(g, 2)); react("happy") }

 return <div className={cn("welcome ob", hidden && "is-hidden")} role="dialog" aria-modal="true" aria-label="Set up Still">
  <header className="ob-top">
   <span className="still-mark is-small" aria-hidden><i /><i /></span>
   <div className="ob-dots" role="progressbar" aria-valuemin={1} aria-valuemax={flow.length} aria-valuenow={step + 1} aria-label={`Step ${step + 1} of ${flow.length}`}>{flow.map((s, i) => <i key={s} className={cn(i === step && "is-on", i < step && "is-done")} />)}</div>
   <button className="ob-skip-all" onClick={finish}>Skip setup</button>
  </header>
  <main className="ob-stage" onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !(e.target as HTMLElement).closest("button,textarea")) { e.preventDefault(); next() } }}>
   <div className="ob-companion" style={{ "--size": Math.round(Math.min(440, Math.max(220, height / 2.5))) + "px" } as CSSProperties}>
    <Mascot look={look} size={Math.round(Math.min(440, Math.max(220, height / 2.5)))} state={mood} follow gesture={gesture[0]} gestureAt={gesture[1]} />
    {at === "helper" && grown >= 3 && c.name.trim() && <motion.b className="ob-name" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>{c.name.trim()}</motion.b>}
   </div>
   <AnimatePresence mode="wait" initial={false}>
    <motion.section key={at} className="ob-talk" initial={{ opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: .24, ease: [.3, .7, .2, 1] }}>
     {at === "hello" && <>
      <Bubbles lines={noAi || !ai ? ["Hi! Welcome to Still.", "Still is an open-source browser that AI apps on this computer can work in, right next to your own tabs.", "Let's set a few things up. You can skip any step."]
       : ["Hi! Welcome to Still.", first ? `I'm ${first.name}, your helper.` : "I'm your helper. Or I will be, once you give me a face.", "Still is an open-source browser with AI built in. It runs on the AI you already pay for, like Claude, ChatGPT or Grok, through their own apps. No API keys, no credits, no extra plan.", "Everything stays on your computer. Let's set things up. You can skip any step."]} />
     </>}
     {at === "import" && <>
      <Bubbles lines={["Moving in from another browser?", "I can copy over your bookmarks, history, passwords and sign-ins. It all stays on this computer."]} />
      <Reveal after={2}><div className="ob-options">
       <button className="ob-option" onClick={onImport}><Download /><span><strong>Bring my stuff over</strong><small>Chrome, Edge, Brave, Opera GX or a saved export. You check it before anything is copied.</small></span></button>
       <button className="ob-option" disabled={isDefault} onClick={() => send("defaultBrowser")}><Globe2 /><span><strong>{isDefault ? "Still opens your links" : "Open my links in Still"}</strong><small>{isDefault ? "Links from other apps open here" : "Windows asks you to confirm"}</small></span>{isDefault && <Check />}</button>
      </div></Reveal>
     </>}
     {at === "ai" && ai && <>
      <Bubbles lines={["Which AI should I think with?", "Pick the one you already use. I go through its own app on this computer, so the plan you have covers everything.", "You can switch any time, even halfway through a task."]} />
      <Reveal after={3}><AiPicker ai={ai} send={send} onPick={id => send("aiHarness", { harness: id })} /></Reveal>
     </>}
     {at === "helper" && <>
      <Bubbles lines={first ? ["Want to change how I look?", "Pick a color and a face, or let me surprise you."] : ["This is me before we've met. Just a shape for now.", "Let's fix that. Pick a color first."]} />
      <Reveal after={2}><div className="ob-build">
       <div className="ob-row"><span>Color</span><div className="ob-colors" role="radiogroup" aria-label="Color">{COLORS.map(([hex, label]) => <button key={hex} role="radio" aria-checked={look.color === hex} aria-label={label} title={label} style={{ "--swatch": hex } as CSSProperties} onClick={() => pickColor(hex)} />)}</div></div>
       {grown >= 1 && <motion.div className="ob-row" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}><span>Face</span><div className="ob-faces" role="radiogroup" aria-label="Face">{FACES.map((f, i) => <button key={i} role="radio" aria-checked={look.eyes === f.eyes && look.mouth === f.mouth} aria-label={"Face " + (i + 1)} onClick={() => pickFace(f)}><FaceSwatch look={{ ...look, ...BLANK, color: look.color, ...f }} size={40} /></button>)}</div></motion.div>}
       {grown >= 2 && <motion.div className="ob-row" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}><span>Name</span>
        <div className="ob-name-box"><input aria-label="Name your helper" placeholder="Give me a name" maxLength={24} value={c.name} onChange={e => { setC({ ...c, name: e.target.value }); setGrown(3) }} />
         <div className="ob-chips">{names.map(n => <button key={n} onClick={() => { setC({ ...c, name: n }); setGrown(3); react("happy") }}>{n}</button>)}<button aria-label="Another name" title="Another name" onClick={() => { setC({ ...c, name: rand(NAMES) }); setGrown(3) }}><Dices /></button></div></div>
       </motion.div>}
       <div className="ob-build-actions">
        <Button variant="outline" size="sm" onClick={() => { const s = surprise(); setLook(s); setC(x => ({ ...x, name: x.name.trim() || rand(NAMES) })); setGrown(3); react("pop") }}><Dices />Surprise me</Button>
        <Button variant="ghost" size="sm" onClick={() => setStyling(true)}><Palette />Customize</Button>
       </div>
      </div></Reveal>
      {styling && <LookEditor companion={{ ...c, look: lookKey(look) }} onClose={() => setStyling(false)} onSave={k => { const l = lookOf({ ...c, look: k }); setLook(l); setGrown(g => Math.max(g, 2)); setStyling(false); react("happy") }} />}
     </>}
     {at === "you" && <>
      <Bubbles lines={[`Nice to meet you. I'm ${name}.`, "What should I call you?"]} />
      <Reveal after={2}><div className="ob-name-box"><input autoFocus aria-label="Your name" placeholder="Your first name" maxLength={40} value={you} onChange={e => setYou(e.target.value)} /></div>
       <p className="ob-note">I keep this in my notes on this computer, so I don't ask twice.</p></Reveal>
     </>}
     {at === "interests" && <>
      <Bubbles lines={[you.trim() ? `Thanks, ${you.trim()}. What are you into?` : "What are you into?", "Pick a few. I'll remember them, so my ideas fit you better."]} />
      <Reveal after={2}><div className="ob-chips is-big" role="group" aria-label="Interests">{INTERESTS.map(k => { const on = likes.includes(k); return <button key={k} aria-pressed={on} onClick={() => setLikes(l => l.includes(k) ? l.filter(x => x !== k) : [...l, k])}>{on && <Check />}{k}</button> })}</div></Reveal>
     </>}
     {at === "layout" && <>
      <Bubbles lines={["Where do you like your tabs?", "You can change this later from the menu."]} />
      <Reveal after={2}><div className="ob-layouts" role="radiogroup" aria-label="Tab layout">
       {([["Classic", "Tabs across the top, like most browsers"], ["Modern", "Tabs down the side, next to your chats"]] as const).map(([k, sub]) =>
        <button key={k} role="radio" aria-checked={(layout ?? "Classic") === k} onClick={() => send("preference", { key: "tabLayout", value: k })}>
         <span className={cn("ob-layout-art", k === "Modern" && "is-side")} aria-hidden><i /><b /></span><strong>{k}{k === "Classic" && <small> · default</small>}</strong><small>{sub}</small></button>)}
      </div></Reveal>
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
      <Bubbles lines={["All set. What should we do first?", "Pick one, or tell me in your own words. You'll see me work, and you can jump in any time."]} />
      <Reveal after={2}>
       <div className="ob-tasks" role="radiogroup" aria-label="First task">{tasks.map(([, label, prompt]) => <button key={label} role="radio" aria-checked={task === prompt} onClick={() => { setTask(task === prompt ? "" : prompt); setOwn("") }}><i />{label}</button>)}</div>
       <div className="ob-name-box"><textarea aria-label="Your own task" rows={2} placeholder="Or type your own" value={own} onChange={e => { setOwn(e.target.value); setTask("") }} /></div>
      </Reveal>
     </>}
    </motion.section>
   </AnimatePresence>
  </main>
  <footer className="ob-foot">
   {step > 0 ? <Button variant="ghost" onClick={() => go(step - 1)}><ArrowLeft />Back</Button> : <span />}
   <span className="flex-1" />
   <Button variant="ghost" onClick={skip}>Skip</Button>
   <Button className="ob-next" onClick={next}>{at === "start" ? (task || own.trim() ? "Let's go" : "Finish") : at === "hello" ? "Let's start" : "Continue"}<CornerDownLeft /></Button>
  </footer>
 </div>
}

