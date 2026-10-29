import { useState, type CSSProperties } from "react"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { BLANK, DEFAULT_LOOK, lookKey, type Look } from "./look"
import { Mascot } from "./Mascot"
import { lookOf, type Companion } from "./Buddy"

// Still's own companions, ready to pick: coworkers with a job for the AI and a way of talking. Picking one makes a
// companion like any other, which the user can then change.
// placeholder until the worker models land: the looks below borrow the current bodies (look.ts BODIES).
export type Premade = { id: string; name: string; role: string; pitch: string; job: string; tone: string; good: string[]; starters: string[]; look: Look }
const look = (l: Partial<Look>): Look => ({ ...DEFAULT_LOOK, blush: true, ...l })

export const PREMADES: Premade[] = [
 { id: "nadia", name: "Nadia", role: "Research",
  pitch: "Digs into any question, reads the sources so you don't have to, and hands you a short brief with links.",
  job: "A researcher. Finds solid sources on any topic, compares what they say, and writes a short brief with the key facts and a link for each. Says plainly when something is uncertain.",
  tone: "Clear and direct. Leads with the answer, then the evidence, and flags weak sources instead of glossing over them.",
  good: ["One-page briefs on any topic", "Comparing tools, products or vendors", "Checking whether a claim holds up"],
  starters: ["Give me a one-page brief on how passkeys work", "Compare the top three project management tools for a team of ten", "Is this claim true? Check the sources"],
  look: look({ body: "hazel", color: "#83cbc4", eyes: "iris", pupil: .2, brows: "straight", mouth: "smile", glasses: "round", hair: "bob", hairColor: "#2c2f3a" }) },
 { id: "kenji", name: "Kenji", role: "Inbox",
  pitch: "Sorts your inbox, drafts replies in your voice and keeps track of what's waiting on you. Never sends a thing without asking.",
  job: "An inbox manager. Goes through the user's mail when asked, sorts out what needs a reply, drafts answers in the user's voice, and keeps a short list of follow-ups. Always asks before sending anything.",
  tone: "Brisk and friendly. Keeps drafts short, and always shows them before anything goes out.",
  good: ["Inbox triage in five minutes", "Replies that sound like you", "Follow-ups you'd otherwise forget"],
  starters: ["Go through my inbox and tell me what needs a reply", "Draft a polite reply turning down this meeting", "What am I still waiting to hear back on?"],
  look: look({ body: "juno", color: "#7aa3dc", eyes: "bean", brows: "thick", mouth: "smile", hair: "swoop", hairColor: "#3b2f2a" }) },
 { id: "marcus", name: "Marcus", role: "Pipeline",
  pitch: "Builds lead lists from public info, researches each company before your call and keeps your pipeline tidy.",
  job: "A sales researcher. Finds companies and people who fit what the user sells, using public information only, researches them before a call, and keeps a clean table of leads and next steps.",
  tone: "Upbeat and to the point. Talks in next steps, and never makes up a number.",
  good: ["Lead lists from public sources", "A company brief before a call", "A tidy table of who's next"],
  starters: ["Find 20 companies that might need what I sell", "Research this company before my call tomorrow", "Write a short, friendly first email to a lead"],
  look: look({ body: "rio", color: "#f2c66b", eyes: "sparkle", brows: "soft", mouth: "grin", hat: "cap" }) },
 { id: "amara", name: "Amara", role: "Hiring",
  pitch: "Writes job posts, screens resumes against a fair scorecard and preps your interview questions.",
  job: "A recruiter. Writes clear job posts, builds a fair scorecard for each role, compares candidates against it using only what they shared, and drafts interview questions. Leaves every decision to the user.",
  tone: "Warm and fair-minded. Sticks to the scorecard, and points out bias when it creeps in.",
  good: ["Job posts people actually read", "A fair scorecard for each role", "Interview questions that get real answers"],
  starters: ["Write a job post for a junior designer", "Make a scorecard for this role", "Give me five interview questions for a product manager"],
  look: look({ color: "#f0a989", eyes: "lashes", brows: "arch", mouth: "smile", hair: "curls", hairColor: "#3b2f2a" }) },
 { id: "jonah", name: "Jonah", role: "Words",
  pitch: "Drafts posts, emails and pages in your voice, then cuts every word that doesn't pull its weight.",
  job: "A writer and editor. Drafts emails, posts, landing pages and newsletters in the user's voice, offers a couple of options, and trims every sentence that doesn't earn its place.",
  tone: "Friendly and honest. Says what isn't working, and always offers a better line.",
  good: ["Posts and newsletters", "Landing page copy", "Editing for clarity"],
  starters: ["Write a launch post for my new feature", "Make this paragraph shorter and clearer", "Give me five subject lines for this email"],
  look: look({ body: "bram", color: "#a6cf98", eyes: "dot", brows: "fluffy", mouth: "smirk", hat: "beanie" }) },
 { id: "priya", name: "Priya", role: "Code & docs",
  pitch: "Reads the docs, explains code, writes the README you keep putting off and checks a fix before you ship it.",
  job: "A developer. Reads documentation and code, explains how things work, writes and reviews small pieces of code, and writes clear docs. Shows the code, and says what couldn't be tested.",
  tone: "Precise and patient. Explains with a short example, and says plainly when unsure.",
  good: ["Explaining code or an API", "READMEs and docs", "Reviewing a small change"],
  starters: ["Explain what this code does", "Write a README for my project", "How do I use this API? Show me an example"],
  look: look({ color: "#c4a8e6", eyes: "ring", brows: "thin", mouth: "smile", glasses: "square", hair: "ponytail", hairColor: "#2c2f3a" }) },
 { id: "lena", name: "Lena", role: "Ops",
  pitch: "Turns projects, busy weeks and events into clear plans with owners, dates and a checklist.",
  job: "An operations lead. Breaks projects into steps with owners and dates, compares options in one table, writes checklists and processes, and keeps track of what's next.",
  tone: "Organized and warm. Likes tables, timelines and a clear next step.",
  good: ["Project plans with dates", "Checklists and processes", "Comparing options in one table"],
  starters: ["Plan a team offsite for 12 people", "Turn this project into a checklist with dates", "Compare these three tools in a table"],
  look: look({ body: "juno", color: "#7fb39b", eyes: "almond", brows: "soft", mouth: "smile", hair: "bun", hairColor: "#a8714a" }) },
]
/// The crew member a companion was picked from, if any (its `crew`). Renaming or changing it keeps the link.
export const premadeOf = (c?: { crew?: string }) => c?.crew ? PREMADES.find(p => p.id === c.crew) : undefined

export const INTERESTS = ["Cooking", "Travel", "Deals and shopping", "News", "Sports", "Music", "Movies and shows", "Games", "Coding", "Design", "Health and fitness", "Money", "Learning", "Home and garden"]
// Things to start with, the ones that match what the user is into first: [interest, label, prompt].
export const TASKS: [string, string, string][] = [
 ["Cooking", "Find a dinner I can make tonight", "Find me three easy, well-reviewed dinner recipes I can make tonight with normal pantry stuff. Show them as a short table."],
 ["Travel", "Plan a weekend away", "Help me plan a weekend away. Ask me where I'm starting from and my budget, then suggest three places with a rough plan for each."],
 ["Deals and shopping", "Find the best price for something", "Help me find the best price for something. Ask me what I'm shopping for, then compare a few stores in a table."],
 ["News", "Catch me up on today's news", "Catch me up on today's top news in a few short bullet points, each with a link."],
 ["Sports", "Catch me up on my team", "Ask me which team I follow, then tell me how their last game went and when they play next."],
 ["Music", "Find new music I'd like", "Ask me for two artists I love, then find five newer artists I might like, with a song to start with for each."],
 ["Movies and shows", "Pick something to watch tonight", "Help me pick something to watch tonight. Ask what I'm in the mood for, then suggest three options with where to stream them."],
 ["Games", "Find a game to play next", "Ask me what games I've enjoyed lately, then suggest three I might like, with prices."],
 ["Coding", "Explain a tech topic simply", "Ask me which tech topic I've been meaning to understand, then explain it simply with one good link to read next."],
 ["Design", "Find inspiration for a project", "Ask me what I'm designing, then find five great examples for inspiration, with links."],
 ["Health and fitness", "Make a simple workout plan", "Ask me how much time I have and what equipment I've got, then make a simple one-week workout plan."],
 ["Money", "Compare a few savings accounts", "Compare a few well-known savings accounts available where I live. Ask me my country first, then show rates in a table."],
 ["Learning", "Find a free course to start", "Ask me what I want to learn, then find three good free courses or guides to start with."],
 ["Home and garden", "Fix something around the house", "Ask me what needs fixing at home, then find a clear step-by-step guide and the tools I need."],
 ["", "Sum up a page for me", "Ask me for a link, then open it and sum it up in five bullet points."],
]
/// Starters for an empty chat or a first task: what the user said they're into first (set up by setup's
/// interview or picked by hand, matched loosely), then the companion's own, then the rest.
export function starters(interests: string[] = [], companion?: { crew?: string }, count = 4): [string, string][] {
 const into = interests.map(i => i.toLowerCase())
 const mine = TASKS.filter(t => t[0] && into.some(i => t[0].toLowerCase().includes(i) || i.includes(t[0].toLowerCase().split(" ")[0])))
 const own = premadeOf(companion)?.starters.map(s => [s, s] as [string, string]) ?? []
 const all: [string, string][] = [...mine.map(t => [t[1], t[2]] as [string, string]), ...own, ...TASKS.filter(t => !mine.includes(t)).map(t => [t[1], t[2]] as [string, string])]
 return all.filter((t, i) => all.findIndex(x => x[0] === t[0]) === i).slice(0, count)
}

/// A new companion made from a crew member: same name, job, way of talking and look, then it's the user's to change.
export const fromPremade = (p: Premade, id = ""): Companion => ({ id, name: p.name, face: "", color: "", job: p.job, tone: p.tone, mode: "default", look: lookKey(p.look), crew: p.id })
const SILHOUETTE: Look = { ...BLANK, color: "#c4c4ca" }

/// The crew as profile cards, round portrait first, then "Make your own". Ones the user already has say hi instead.
/// In setup (`picked` given) every card toggles, and the ones you made show beside the crew.
export function CrewCards({ have = [], picked, made = [], onPick, onMade, onOwn, onChat }: {
 have?: Companion[]; picked?: string[]; made?: Companion[]; onPick: (p: Premade) => void; onMade?: (id: string) => void; onOwn: () => void; onChat?: (id: string) => void
}) {
 const [more, setMore] = useState<Premade | null>(null)
 const mine = (p: Premade) => onChat && have.find(c => premadeOf(c) === p)
 const act = (p: Premade) => { const c = mine(p); setMore(null); if (c) onChat!(c.id); else onPick(p) }
 const on = (key: string) => !!picked?.includes(key)
 const pick = (key: string, name: string, toggle: () => void) => <button className="crew-pick" aria-pressed={picked ? on(key) : undefined} onClick={toggle}>{on(key) ? <><Check />Picked</> : `Pick ${name}`}</button>
 return <div className="crew-grid">
  {PREMADES.map(p => <article key={p.id} className={cn("crew-card", on(p.id) && "is-picked")} style={{ "--hue": p.look.color } as CSSProperties}>
   <div className="crew-portrait"><Mascot look={p.look} size={118} follow /></div>
   <div className="crew-info">
    <h3>{p.name}</h3><span className="crew-role">{p.role}</span>
    <p>{p.pitch}</p>
    <div className="crew-actions">{mine(p) ? <button className="crew-pick" onClick={() => act(p)}>Say hi</button> : pick(p.id, p.name, () => act(p))}<button className="crew-more" onClick={() => setMore(p)}>About {p.name}</button></div>
   </div>
  </article>)}
  {made.map(c => <article key={c.id} className={cn("crew-card", on(c.id) && "is-picked")} style={{ "--hue": lookOf(c).color } as CSSProperties}>
   <div className="crew-portrait"><Mascot look={lookOf(c)} size={118} follow /></div>
   <div className="crew-info">
    <h3>{c.name}</h3><span className="crew-role">Made by you</span>
    <p>All yours. Give them a job any time on the Companions page.</p>
    <div className="crew-actions">{pick(c.id, c.name, () => onMade?.(c.id))}</div>
   </div>
  </article>)}
  <article className="crew-card is-own">
   <div className="crew-portrait"><Mascot look={SILHOUETTE} size={118} /></div>
   <div className="crew-info">
    <h3>Make your own</h3>
    <p>Pick a body, a face, a name and a job, and make them all yours.</p>
    <div className="crew-actions"><button className="crew-pick" onClick={onOwn}>Start from scratch</button></div>
   </div>
  </article>
  {more && <Dialog open onOpenChange={o => { if (!o) setMore(null) }}>
   <DialogContent className="app-dialog crew-dialog" style={{ "--hue": more.look.color } as CSSProperties}>
    <div className="crew-dialog-hero"><Mascot look={more.look} size={150} follow gesture="signature" gestureAt={1} /></div>
    <DialogHeader><DialogTitle>{more.name}<span className="crew-role">{more.role}</span></DialogTitle><DialogDescription>{more.pitch}</DialogDescription></DialogHeader>
    <div className="crew-dialog-body">
     <section><h4>Good at</h4><ul>{more.good.map(g => <li key={g}>{g}</li>)}</ul></section>
     <section><h4>How {more.name} talks</h4><p>{more.tone}</p></section>
     <section><h4>Try asking</h4><ul className="crew-asks">{more.starters.map(s => <li key={s}>{s}</li>)}</ul></section>
    </div>
    <Button className="crew-dialog-pick" onClick={() => act(more)}>{mine(more) ? `Say hi to ${more.name}` : on(more.id) ? `Unpick ${more.name}` : `Pick ${more.name}`}</Button>
   </DialogContent>
  </Dialog>}
 </div>
}
