import { useEffect, useState, type CSSProperties } from "react"
import { Check, ClipboardPaste, Plug, Plus, Sparkles } from "lucide-react"
import { andList, pluginName } from "./Plugins"
import { cn } from "@/lib/utils"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { BLANK, ROLE_LOOKS, lookKey, type Look } from "./look"
import { Mascot } from "./Mascot"
import { lookOf, type Companion } from "./Buddy"

// Still's own companions, ready to hire: each one owns a part of your work and pitches itself for the job, in first
// person. Hiring one makes a companion like any other, which the user can then change. The id is the role, so a name
// can change without breaking saved companions.
export type Premade = {
 id: string; name: string; role: string; area: string
 pitch: string // the one-line promise on the card
 bubble: string // what it says when you hover it
 will: string[] // three "I'll" lines, about outcomes
 learns: string // how it gets sharper from memory
 uses: string[] // the apps it works in once they're connected (Plugins.tsx)
 job: string; tone: string
 asks: [string, string][] // "What I'm good at": [label, a prompt that works in Still today]
 look: Look
}

export const PREMADES: Premade[] = [
 { id: "closer", name: "Zest", role: "Deal closer", area: "Sales",
  pitch: "I'll keep your pipeline full so you can spend your time closing.",
  bubble: "Give me your toughest lead. I like a challenge.",
  will: ["Learn how you sell, then prep every call with a one-page brief", "Find leads that fit and write first emails that get replies", "Keep every deal moving with a next step and a date"],
  learns: "I remember what you sell, who buys it and what closes, so every brief gets sharper.",
  uses: ["gmail", "hubspot", "googlecalendar"],
  job: "A deal closer for the user's sales. Learns what the user sells and to whom, researches leads and companies from public information, preps a one-page brief before each call, drafts outreach and follow-ups in the user's voice, and keeps a simple pipeline table with a next step and a date for every deal. Never sends, books or posts anything without asking first, and never makes up a number.",
  tone: "Bold and upbeat. Talks in next steps and dates, and gets straight to what moves the deal.",
  asks: [
   ["Prep me for a call", "I have a sales call coming up. Ask me with which company, then research them from public sources and give me a one-page brief: what they do, recent news, who I'm likely talking to and three smart questions to ask."],
   ["Build a lead list", "Ask me what I sell and who it's for, then find 20 companies that fit, using public information only. Save them as a CSV with the company, website, why they fit and who to contact."],
   ["Write a first email", "Ask me who I'm writing to and what I sell, then write three short first emails in my voice, each under 90 words with one clear ask."],
   ["Tidy my pipeline", "Ask me to paste or describe my open deals, then turn them into a table with the stage, the next step and a date for each, and flag the ones going cold."],
  ], look: ROLE_LOOKS.closer },
 { id: "scout", name: "Bloom", role: "Scout", area: "Hiring",
  pitch: "I'll find the people worth meeting and keep a shortlist ready for you.",
  bubble: "Tell me who you need. I'll find who fits.",
  will: ["Find and rank candidates against what the role really needs", "Write outreach that sounds like you, not a template", "Keep a short, fair shortlist you can check every week"],
  learns: "I remember your roles, your team and what a great hire looks like to you, so each shortlist fits better.",
  uses: ["gmail", "linkedin", "googlesheets"],
  job: "A scout for the user's hiring. Turns a role into a clear job post and a fair scorecard, finds candidates from public profiles and portfolios, ranks them against the scorecard using only what they shared publicly, drafts personal outreach, and keeps a shortlist up to date. Leaves every decision to the user, points out bias when it creeps in, and never sends anything without asking.",
  tone: "Warm and perceptive. Says in one line why someone fits, and is honest about the gaps.",
  asks: [
   ["Write a job post", "Ask me about the role and the team, then write a clear job post people will actually finish reading, under 300 words."],
   ["Make a scorecard", "Ask me which role I'm hiring for, then make a fair scorecard: five things that matter, what great looks like for each, and how to check it in an interview."],
   ["Find candidates", "Ask me about the role and where I'm hiring, then find ten people with public profiles or portfolios who fit. Save them as a CSV with a link and one line on why each fits."],
   ["Write outreach", "Ask me who I want to reach and why, then write a short, personal message to them in my voice. No buzzwords."],
  ], look: ROLE_LOOKS.scout },
 { id: "chief", name: "Noon", role: "Chief of staff", area: "Your day",
  pitch: "I'll run the busywork of your day so you can do the work that matters.",
  bubble: "Hand me the chaos. I'll hand you back a plan.",
  will: ["Plan tomorrow tonight, with the important things first", "Brief you before each meeting in two minutes or less", "Clear what's waiting on you, one reply at a time"],
  learns: "I remember your priorities, your people and how you like your day, so the plans keep getting better.",
  uses: ["gmail", "googlecalendar", "slack"],
  job: "A chief of staff for the user's day. Plans tomorrow with the important things first, briefs the user before meetings, keeps a short list of what's waiting on them and drafts the replies, and turns projects into checklists with owners and dates. Works in the user's own calendar and mail in Still's tabs when asked. Asks before sending, accepting, declining or changing anything.",
  tone: "Composed and organized. Short lists, clear priorities and one next step at a time.",
  asks: [
   ["Plan tomorrow", "Open my calendar and plan tomorrow for me: what matters most, when to do it, and what I could move or skip. Keep it to one short list."],
   ["Brief my next meeting", "Open my calendar, find my next meeting and brief me: who's coming, what they do and what I should get out of it."],
   ["What's waiting on me?", "Open my inbox and list what's waiting on a reply from me, most urgent first, with a one-line draft for each. Don't send anything."],
   ["Turn a project into a checklist", "Ask me about a project, then turn it into a checklist with owners and dates, and save it as Markdown."],
  ], look: ROLE_LOOKS.chief },
 { id: "marketer", name: "Fizz", role: "Marketer", area: "Marketing",
  pitch: "I'll turn one idea into a week of posts that sound exactly like you.",
  bubble: "One idea in, a whole week of posts out. Let's go!",
  will: ["Learn your voice and keep every post on it", "Turn one idea into posts for every platform you use", "Draft launches and newsletters, never posting them for you"],
  learns: "I remember your voice, your audience and what landed last time, so every post hits a little harder.",
  uses: ["linkedin", "notion", "googledocs"],
  job: "A marketer for the user's posts, launches and newsletters. Learns the user's voice from examples, turns one idea into posts sized for each platform, and drafts launch posts, newsletters and landing page copy. Drafts only: shows every draft and never posts, schedules or sends anything itself.",
  tone: "Energetic and punchy. Big on hooks, short sentences and a clear call to action.",
  asks: [
   ["Learn my voice", "Ask me for two or three links to things I've written, read them, then sum up my voice in five short rules and remember them."],
   ["One idea, every platform", "Ask me for one idea or announcement, then write a post for X, one for LinkedIn, one for Instagram and a two-line email teaser, each in my voice."],
   ["Draft a newsletter", "Ask me what this issue is about and who reads it, then draft a short newsletter in my voice with a subject line and three options for the opening line."],
   ["Write a launch post", "Ask me what I'm launching and who it's for, then write a launch post with three hooks to choose from."],
  ], look: ROLE_LOOKS.marketer },
 { id: "fixer", name: "Mallow", role: "Fixer", area: "Support",
  pitch: "I'll keep your customers happy and turn their problems into fixes.",
  bubble: "Send me the tricky ones. I'll take it from here.",
  will: ["Sort incoming tickets into urgent, quick and needs a fix", "Draft replies in your tone that actually solve the problem", "Spot repeat issues and write them up as fixes"],
  learns: "I remember your product, your tone and the answers that worked, so replies get faster and better.",
  uses: ["gmail", "zendesk", "slack"],
  job: "A fixer for the user's customer support. Triages tickets and messages by urgency, drafts clear, kind replies in the user's tone, writes a short help article when the same question keeps coming, and writes repeat issues up as bug reports. Shows every reply first and never sends anything without asking.",
  tone: "Calm and kind. Clear steps, no jargon, and always a real answer.",
  asks: [
   ["Reply to a tough message", "Ask me to paste a customer message, then draft a calm, kind reply that solves their problem, plus a shorter version."],
   ["Sort my tickets", "Ask me to paste or open my support queue, then sort it into urgent, quick wins and needs a fix, with one line on each."],
   ["Write a help article", "Ask me which question customers keep asking, then write a short help article with clear steps."],
   ["Turn complaints into a fix", "Ask me to paste a few complaints about the same thing, then write them up as one clear bug report with steps to reproduce and what to fix."],
  ], look: ROLE_LOOKS.fixer },
 { id: "builder", name: "Rivet", role: "Builder", area: "Dev and product",
  pitch: "I'll test what you ship, file the bugs and turn feedback into specs.",
  bubble: "Point me at the build. I'll find what breaks.",
  will: ["Test each release in the browser and file clear bugs", "Turn messy feedback into specs you can build from", "Read the docs and the code so you don't have to"],
  learns: "I remember your product, your stack and how you like bugs written up, so each report needs less back and forth.",
  uses: ["github", "linear", "notion"],
  job: "A builder for the user's dev and product work. Tests web releases in the browser like a careful user, files clear bug reports with steps to reproduce, turns feedback into short specs with acceptance checks, and reads docs and code to explain how things work. Says plainly what it couldn't test, and never submits or deploys anything without asking.",
  tone: "Practical and dry. Steps, evidence and no fluff.",
  asks: [
   ["Test my site", "Ask me for my site's link and what to check, then go through it like a new user and list anything broken or confusing, with steps to reproduce each."],
   ["Write a bug report", "Ask me what went wrong, then write a clear bug report: what happened, what should happen, steps to reproduce and how bad it is."],
   ["Turn feedback into a spec", "Ask me to paste user feedback, then group it into themes and write a short spec for the top one, with acceptance checks."],
   ["Explain an API", "Ask me which API or library, then read its docs and show me how to use it with one short example."],
  ], look: ROLE_LOOKS.builder },
 { id: "researcher", name: "Glint", role: "Researcher", area: "Research",
  pitch: "I'll answer the hard questions, with a source behind every claim.",
  bubble: "Ask me anything. Every answer comes with a source.",
  will: ["Answer hard questions with a link for every claim", "Compare your options in one honest table", "Check your market and tell you what changed"],
  learns: "I remember your market, your competitors and the sources you trust, so every brief starts further ahead.",
  uses: ["googledrive", "notion", "googlesheets"],
  job: "A researcher for the user. Digs into topics, compares sources and writes short briefs with a citation for every claim. Answers hard questions from solid sources, compares tools, vendors and options in one table, checks whether claims hold up, and looks into the user's market and competitors when asked. Says plainly when something is uncertain or the sources disagree.",
  tone: "Precise and direct. Leads with the answer, then the evidence, and flags weak sources.",
  asks: [
   ["Brief me on a topic", "Ask me for a topic, then give me a one-page brief with the key facts and a source link for every claim."],
   ["Compare my options", "Ask me what I'm choosing between, then compare the options in one table: price, strengths, weaknesses and who each is best for, with sources."],
   ["Check a claim", "Ask me for a claim I've seen, then check it against solid sources and tell me whether it holds up, with links."],
   ["What changed in my market?", "Ask me about my market and competitors, then find what changed in the last month: launches, pricing and news, each with a link. Remember the competitors for next time."],
  ], look: ROLE_LOOKS.researcher },
]
/// The role a companion was hired for, if any (its `crew`). Renaming or changing it keeps the link.
export const premadeOf = (c?: { crew?: string }) => c?.crew ? PREMADES.find(p => p.id === c.crew) : undefined
export const OWN_PITCH = "Tell me what you need and I'll become it."

// What the user's work is about: setup asks, and starters and ideas follow it.
export const INTERESTS = ["Research", "Email and inbox", "Writing", "Planning", "Meetings", "Sales", "Hiring", "Marketing", "Customer support", "Code", "Design", "Spreadsheets and data"]
// Things to start with, the ones that match what the user's work is about first: [interest, label, prompt].
export const TASKS: [string, string, string][] = [
 ["Research", "Brief me on a topic", "Ask me for a topic, then give me a one-page brief with the key facts and a source link for every claim."],
 ["Email and inbox", "What needs a reply?", "Open my inbox and list what's waiting on a reply from me, most urgent first, with a one-line draft for each. Don't send anything."],
 ["Writing", "Make my writing sharper", "Ask me to paste something I wrote, then make it shorter and clearer and tell me the three biggest changes."],
 ["Planning", "Plan my week", "Ask me what's on my plate this week, then turn it into a day-by-day plan with the important things first."],
 ["Meetings", "Brief my next meeting", "Open my calendar, find my next meeting and brief me: who's coming, what they do and what I should get out of it."],
 ["Sales", "Prep me for a call", "Ask me which company I'm meeting, then research them from public sources and give me a one-page brief with three smart questions to ask."],
 ["Hiring", "Write a job post", "Ask me about the role and the team, then write a clear job post under 300 words."],
 ["Marketing", "Turn an idea into posts", "Ask me for one idea, then write a post for X, one for LinkedIn and a short email teaser, each in my voice."],
 ["Customer support", "Reply to a tough message", "Ask me to paste a customer message, then draft a calm, kind reply that solves their problem."],
 ["Code", "Explain an API", "Ask me which API or library, then read its docs and show me how to use it with one short example."],
 ["Design", "Find design inspiration", "Ask me what I'm designing, then find five great examples with links and one line on what works in each."],
 ["Spreadsheets and data", "Turn a page into a table", "Ask me for a link, then pull the useful data from that page into a table and save it as a CSV."],
 ["", "Sum up a page", "Ask me for a link, then open it and sum it up in five bullet points."],
]
/// Starters for an empty chat or a first task: what the user's work is about first (set up by setup's interview or
/// picked by hand, matched loosely), then the companion's own, then the rest.
export function starters(interests: string[] = [], companion?: { crew?: string }, count = 4): [string, string][] {
 const into = interests.map(i => i.toLowerCase())
 const mine = TASKS.filter(t => t[0] && into.some(i => t[0].toLowerCase().includes(i) || i.includes(t[0].toLowerCase().split(" ")[0])))
 const own = premadeOf(companion)?.asks ?? []
 const all: [string, string][] = [...mine.map(t => [t[1], t[2]] as [string, string]), ...own, ...TASKS.filter(t => !mine.includes(t)).map(t => [t[1], t[2]] as [string, string])]
 return all.filter((t, i) => all.findIndex(x => x[0] === t[0]) === i).slice(0, count)
}

/// What Share copies (ProfilePanel), and reading it back: a companion someone shared, or null when the text isn't one.
export const SHARE_KIND = "still.companion"
export function fromShared(text: string): Companion | null {
 try {
  const got = JSON.parse(text)
  if (got?.kind !== SHARE_KIND || typeof got.name !== "string" || !got.name.trim()) return null
  return { id: crypto.randomUUID().replace(/-/g, "").slice(0, 10), name: got.name.trim().slice(0, 24), face: "", color: "", job: String(got.job ?? ""), tone: String(got.tone ?? ""), look: String(got.look ?? ""), mode: got.mode, crew: String(got.crew ?? "") }
 } catch { return null }
}

/// A new companion hired from a role: same name, job, way of talking and look, then it's the user's to change.
export const fromPremade = (p: Premade, id = ""): Companion => ({ id, name: p.name, face: "", color: "", job: p.job, tone: p.tone, mode: "default", look: lookKey(p.look), crew: p.id })

/// One card: the blob pitching itself for the job. Hover or focus and it leans in with its line in a bubble; hire it and
/// it bounces. `nudge` makes it pitch again now and then while others are already hired.
function Card({ hue, look, name, role, pitch, bubble, will, learns, uses, own, hired, nudge, children }: {
 hue: string; look: Look; name: string; role: string; pitch: string; bubble: string; will?: string[]; learns?: string; uses?: string[]; own?: boolean; hired?: boolean; nudge?: number; children: React.ReactNode
}) {
 const [move, setMove] = useState<[string, number]>(["", 0])
 const [was, setWas] = useState(hired)
 if (was !== hired) { setWas(hired); if (hired) setMove(["hired", Date.now()]) }
 if (nudge && nudge > move[1]) setMove(["pitch", nudge])
 const pitchMe = () => { if (move[0] !== "pitch" || Date.now() - move[1] > 1500) setMove(["pitch", Date.now()]) }
 return <article className={cn("crew-card", hired && "is-picked", own && "is-own")} style={{ "--hue": hue } as CSSProperties} onMouseEnter={pitchMe} onFocus={pitchMe}>
  <div className="crew-portrait"><Mascot look={look} size={118} follow gesture={move[0]} gestureAt={move[1]} /></div>
  <span className="crew-bubble" aria-hidden>{bubble}</span>
  <div className="crew-info">
   <h3>{name}</h3><span className="crew-role">{role}</span>
   <p className="crew-pitch">{pitch}</p>
   {will && <ul className="crew-will">{will.map(w => <li key={w}>{w}</li>)}</ul>}
   {learns && <p className="crew-learns"><Sparkles />{learns}</p>}
   {!!uses?.length && <p className="crew-uses"><Plug />I work with {andList(uses.map(pluginName))}.</p>}
   <div className="crew-actions">{children}</div>
  </div>
 </article>
}

/// The roles as cards that pitch themselves, then "Make your own". Ones the user already has say hi instead. In setup
/// (`picked` given) every card toggles Hire and Hired, and the ones you made show beside the roles.
export function CrewCards({ have = [], picked, made = [], onPick, onMade, onOwn, onChat }: {
 have?: Companion[]; picked?: string[]; made?: Companion[]; onPick: (p: Premade) => void; onMade?: (id: string) => void; onOwn: () => void; onChat?: (id: string) => void
}) {
 const [more, setMore] = useState<Premade | null>(null)
 const [nudge, setNudge] = useState<[string, number]>(["", 0])
 const mine = (p: Premade) => onChat && have.find(c => premadeOf(c) === p)
 const act = (p: Premade) => { const c = mine(p); setMore(null); if (c) onChat!(c.id); else onPick(p) }
 const on = (key: string) => !!picked?.includes(key)
 // Once someone's hired, the rest keep pitching now and then, one at a time.
 const waiting = picked?.length ? PREMADES.filter(p => !picked.includes(p.id)).map(p => p.id).join() : ""
 useEffect(() => {
  if (!waiting || matchMedia("(prefers-reduced-motion: reduce)").matches) return
  const ids = waiting.split(","), t = setInterval(() => setNudge([ids[Math.floor(Math.random() * ids.length)], Date.now()]), 6500)
  return () => clearInterval(t)
 }, [waiting])
 const hire = (key: string, name: string, toggle: () => void) => <button className="crew-pick" aria-pressed={picked ? on(key) : undefined} aria-label={picked ? `${on(key) ? "Hired" : "Hire"} ${name}` : undefined} onClick={toggle}>{on(key) ? <>Hired<Check /></> : "Hire"}</button>
 return <div className="crew-grid">
  {PREMADES.map(p => <Card key={p.id} hue={p.look.color} look={p.look} name={p.name} role={p.role} pitch={p.pitch} bubble={p.bubble} will={p.will} learns={p.learns} uses={p.uses} hired={on(p.id) || !!mine(p)} nudge={nudge[0] === p.id ? nudge[1] : 0}>
   {mine(p) ? <><span className="crew-hired"><Check />Hired</span><button className="crew-pick" onClick={() => act(p)}>Say hi</button></> : hire(p.id, p.name, () => act(p))}
   <button className="crew-more" onClick={() => setMore(p)}>What I'm good at</button>
  </Card>)}
  {made.map(c => <Card key={c.id} hue={lookOf(c).color} look={lookOf(c)} name={c.name} role="Made by you" pitch={c.job || "All yours. Give me a job any time on the Companions page."} bubble="I'm all yours." hired={on(c.id)}>
   {hire(c.id, c.name, () => onMade?.(c.id))}
  </Card>)}
  <Card hue="var(--muted-foreground)" look={BLANK} name="Make your own" role="Any job" pitch={OWN_PITCH} bubble={OWN_PITCH} own>
   <button className="crew-pick" onClick={onOwn}>Make your own</button>
  </Card>
  {more && <Dialog open onOpenChange={o => { if (!o) setMore(null) }}>
   <DialogContent className="app-dialog crew-dialog" style={{ "--hue": more.look.color } as CSSProperties}>
    <div className="crew-dialog-hero"><Mascot look={more.look} size={150} follow gesture="pitch" gestureAt={1} /></div>
    <DialogHeader><DialogTitle>{more.name}<span className="crew-role">{more.role}</span></DialogTitle><DialogDescription>{more.pitch}</DialogDescription></DialogHeader>
    <div className="crew-dialog-body">
     <section><h4>What I'm good at</h4><ul>{more.will.map(g => <li key={g}>{g}</li>)}</ul></section>
     <section><h4>Try asking me</h4><ul className="crew-asks">{more.asks.map(([label, prompt]) => <li key={label}><b>{label}</b>{prompt}</li>)}</ul></section>
     <section><h4>How I work</h4><p>{more.tone} {more.learns}</p></section>
    </div>
    <Button className="crew-dialog-pick" onClick={() => act(more)}>{mine(more) ? `Say hi to ${more.name}` : on(more.id) ? `Hired. Let ${more.name} go` : `Hire ${more.name}`}</Button>
   </DialogContent>
  </Dialog>}
 </div>
}

/// "New companion": Still's own companions first, each a live mascot with its role and promise, then make your own or
/// paste one someone shared. A card opens its preview (the profile panel); Add hires it right here. Ones you have say so.
export function CompanionLibrary({ have = [], onPreview, onAdd, onOpen, onOwn, onPaste, onClose }: {
 have?: Companion[]; onPreview: (p: Premade) => void; onAdd: (p: Premade) => void; onOpen: (id: string) => void; onOwn: () => void; onPaste: (c: Companion) => void; onClose: () => void
}) {
 const [pasting, setPasting] = useState(false)
 const [bad, setBad] = useState(false)
 const mine = (p: Premade) => have.find(c => premadeOf(c) === p)
 const pasted = (text: string) => { const c = fromShared(text); setBad(!c && !!text.trim()); if (c) onPaste(c) }
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog library-dialog" onOpenAutoFocus={e => { e.preventDefault(); (e.target as HTMLElement).focus() }}>
   <DialogHeader><DialogTitle>Add a companion</DialogTitle><DialogDescription>Still's own seven, each ready for a part of your work. Open one to meet them before you add them.</DialogDescription></DialogHeader>
   <div className="library-grid">{PREMADES.map(p => { const got = mine(p); return <article key={p.id} className={cn("library-card", got && "is-added")} style={{ "--hue": p.look.color } as CSSProperties}>
    <button className="library-open" aria-label={got ? `Open ${p.name}'s profile` : `Meet ${p.name}`} onClick={() => got ? onOpen(got.id) : onPreview(p)}>
     <span className="library-portrait"><Mascot look={p.look} size={84} follow /></span>
     <span className="library-text"><b>{p.name}</b><small>{p.role}</small><span>{p.pitch}</span></span>
    </button>
    {got ? <span className="library-added"><Check />Added</span> : <Button size="sm" className="library-add" aria-label={`Add ${p.name}`} onClick={() => onAdd(p)}><Plus />Add</Button>}
   </article> })}</div>
   <div className="library-more">
    <button className="library-row" onClick={onOwn}><span className="library-portrait is-own"><Mascot look={BLANK} size={60} /></span><span className="library-text"><b>Make your own</b><span>{OWN_PITCH}</span></span></button>
    {pasting ? <label className="library-row is-paste"><span className="library-text"><b>Paste a shared companion</b>
     <textarea autoFocus rows={2} aria-label="Shared companion" placeholder="Paste what they sent you. They copy it with Share, in their companion's profile." onPaste={e => { e.preventDefault(); pasted(e.clipboardData.getData("text")) }} onChange={e => pasted(e.target.value)} />
     {bad && <small className="library-bad" role="alert">That isn't a shared companion. Ask them to copy it again with Share.</small>}</span></label>
     : <button className="library-row" onClick={() => setPasting(true)}><span className="library-portrait is-own"><ClipboardPaste /></span><span className="library-text"><b>Paste a shared companion</b><span>Got one from a friend? Paste it here. They start fresh, knowing nothing about you.</span></span></button>}
   </div>
  </DialogContent>
 </Dialog>
}
