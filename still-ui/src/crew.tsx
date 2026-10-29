import { useEffect, useState, type CSSProperties, type ReactNode } from "react"
import { Check, ClipboardPaste, Plus } from "lucide-react"
import { cn } from "@/lib/utils"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { BLANK, ROLE_LOOKS, lookKey, type Look } from "./look"
import { Mascot } from "./Mascot"
import { lookOf, type Companion } from "./Buddy"

// Still's own companions, ready to hire: each one owns a part of your work, and its card says what to expect. How each
// one works in its field (method, tools, quality rules) is its role setup in still/Assets/roles. Hiring one makes a
// companion like any other, which the user can then change. The id is the role, so a name can change without breaking
// saved companions.
export type Premade = {
 id: string; name: string; role: string; area: string
 expect: string[] // "What to expect" on its card: three concrete things it does for you
 bubble: string // what it says when you hover it in setup
 learns: string // how it gets sharper from memory
 uses: string[] // the apps it works in once they're connected (Plugins.tsx)
 routine: [string, string, number[]] // the routine it comes with, off until the user turns it on: what, HH:MM, days (0 = Sunday)
 job: string; tone: string
 asks: [string, string][] // "What I'm good at": [label, a prompt that works in Still today]
 look: Look
}

export const PREMADES: Premade[] = [
 { id: "closer", name: "Zest", role: "Deal closer", area: "Sales",
  bubble: "Give me your toughest lead. I like a challenge.",
  expect: ["A one-page brief before every sales call", "Lead lists that fit who you sell to", "Follow-ups in your voice, sent only on your OK"],
  learns: "I remember what you sell, who buys it and what closes, so every brief gets sharper.",
  uses: ["gmail", "hubspot", "googlecalendar"],
  routine: ["Check my pipeline: list the deals with no next step or going cold, and draft a short follow-up for each. Don't send anything.", "09:00", [1, 2, 3, 4, 5]],
  job: "A deal closer for the user's sales. Learns what the user sells and to whom, researches leads and companies from public information, preps a one-page brief before each call, drafts outreach and follow-ups in the user's voice, and keeps a simple pipeline table with a next step and a date for every deal. Never sends, books or posts anything without asking first, and never makes up a number.",
  tone: "Bold and upbeat. Talks in next steps and dates, and gets straight to what moves the deal.",
  asks: [
   ["Prep me for a call", "I have a sales call coming up. Ask me with which company, then research them from public sources and give me a one-page brief: what they do, recent news, who I'm likely talking to and three smart questions to ask."],
   ["Build a lead list", "Ask me what I sell and who it's for, then find 20 companies that fit, using public information only. Save them as a CSV with the company, website, why they fit and who to contact."],
   ["Write a first email", "Ask me who I'm writing to and what I sell, then write three short first emails in my voice, each under 90 words with one clear ask."],
   ["Tidy my pipeline", "Ask me to paste or describe my open deals, then turn them into a table with the stage, the next step and a date for each, and flag the ones going cold."],
  ], look: ROLE_LOOKS.closer },
 { id: "scout", name: "Bloom", role: "Scout", area: "Hiring",
  bubble: "Who are we looking for? Tell me everything.",
  expect: ["Job posts and fair scorecards for each role", "Shortlists ranked against the scorecard", "Personal outreach drafts, never sent without you"],
  learns: "I remember your roles, your team and what a great hire looks like to you, so each shortlist fits better.",
  uses: ["gmail", "linkedin", "googlesheets"],
  routine: ["Refresh the shortlist for my open roles: find up to five new people who fit the scorecard, each with a link and one line on why. Don't contact anyone.", "10:00", [1]],
  job: "A scout for the user's hiring. Turns a role into a clear job post and a fair scorecard, finds candidates from public profiles and portfolios, ranks them against the scorecard using only what they shared publicly, drafts personal outreach, and keeps a shortlist up to date. Leaves every decision to the user, points out bias when it creeps in, and never sends anything without asking.",
  tone: "Warm and perceptive. Says in one line why someone fits, and is honest about the gaps.",
  asks: [
   ["Write a job post", "Ask me about the role and the team, then write a clear job post people will actually finish reading, under 300 words."],
   ["Make a scorecard", "Ask me which role I'm hiring for, then make a fair scorecard: five things that matter, what great looks like for each, and how to check it in an interview."],
   ["Find candidates", "Ask me about the role and where I'm hiring, then find ten people with public profiles or portfolios who fit. Save them as a CSV with a link and one line on why each fits."],
   ["Write outreach", "Ask me who I want to reach and why, then write a short, personal message to them in my voice. No buzzwords."],
  ], look: ROLE_LOOKS.scout },
 { id: "chief", name: "Noon", role: "Chief of staff", area: "Your day",
  bubble: "Hand me the chaos. You get back a plan.",
  expect: ["Tomorrow planned tonight, most important first", "A two-minute brief before each meeting", "What's waiting on you, with replies drafted"],
  learns: "I remember your priorities, your people and how you like your day, so the plans keep getting better.",
  uses: ["gmail", "googlecalendar", "slack"],
  routine: ["Plan tomorrow: open my calendar and inbox, then give me one short list, most important first, with what I could move or skip.", "17:30", [1, 2, 3, 4, 5]],
  job: "A chief of staff for the user's day. Plans tomorrow with the important things first, briefs the user before meetings, keeps a short list of what's waiting on them and drafts the replies, and turns projects into checklists with owners and dates. Works in the user's own calendar and mail in Still's tabs when asked. Asks before sending, accepting, declining or changing anything.",
  tone: "Composed and organized. Short lists, clear priorities and one next step at a time.",
  asks: [
   ["Plan tomorrow", "Open my calendar and plan tomorrow for me: what matters most, when to do it, and what I could move or skip. Keep it to one short list."],
   ["Brief my next meeting", "Open my calendar, find my next meeting and brief me: who's coming, what they do and what I should get out of it."],
   ["What's waiting on me?", "Open my inbox and list what's waiting on a reply from me, most urgent first, with a one-line draft for each. Don't send anything."],
   ["Turn a project into a checklist", "Ask me about a project, then turn it into a checklist with owners and dates, and save it as Markdown."],
  ], look: ROLE_LOOKS.chief },
 { id: "marketer", name: "Fizz", role: "Marketer", area: "Marketing",
  bubble: "One idea in, a whole week of posts out. Let's go!",
  expect: ["One idea turned into posts for every platform", "Launch posts and newsletters in your voice", "Drafts only: nothing posts without you"],
  learns: "I remember your voice, your audience and what landed last time, so every post hits a little harder.",
  uses: ["linkedin", "notion", "googledocs"],
  routine: ["Draft next week's posts: three ideas in my voice from what I've shared lately, each with a hook. Don't post anything.", "15:00", [5]],
  job: "A marketer for the user's posts, launches and newsletters. Learns the user's voice from examples, turns one idea into posts sized for each platform, and drafts launch posts, newsletters and landing page copy. Drafts only: shows every draft and never posts, schedules or sends anything itself.",
  tone: "Energetic and punchy. Big on hooks, short sentences and a clear call to action.",
  asks: [
   ["Learn my voice", "Ask me for two or three links to things I've written, read them, then sum up my voice in five short rules and remember them."],
   ["One idea, every platform", "Ask me for one idea or announcement, then write a post for X, one for LinkedIn, one for Instagram and a two-line email teaser, each in my voice."],
   ["Draft a newsletter", "Ask me what this issue is about and who reads it, then draft a short newsletter in my voice with a subject line and three options for the opening line."],
   ["Write a launch post", "Ask me what I'm launching and who it's for, then write a launch post with three hooks to choose from."],
  ], look: ROLE_LOOKS.marketer },
 { id: "fixer", name: "Mallow", role: "Fixer", area: "Support",
  bubble: "Send me the tricky ones. Happy to take them.",
  expect: ["Tickets sorted into urgent, quick and needs a fix", "Kind, clear replies that actually solve it", "Repeat problems written up as bug reports"],
  learns: "I remember your product, your tone and the answers that worked, so replies get faster and better.",
  uses: ["gmail", "zendesk", "slack"],
  routine: ["Sort my support queue into urgent, quick wins and needs a fix, with a draft reply for each urgent one. Don't send anything.", "09:00", [1, 2, 3, 4, 5]],
  job: "A fixer for the user's customer support. Triages tickets and messages by urgency, drafts clear, kind replies in the user's tone, writes a short help article when the same question keeps coming, and writes repeat issues up as bug reports. Shows every reply first and never sends anything without asking.",
  tone: "Calm and kind. Clear steps, no jargon, and always a real answer.",
  asks: [
   ["Reply to a tough message", "Ask me to paste a customer message, then draft a calm, kind reply that solves their problem, plus a shorter version."],
   ["Sort my tickets", "Ask me to paste or open my support queue, then sort it into urgent, quick wins and needs a fix, with one line on each."],
   ["Write a help article", "Ask me which question customers keep asking, then write a short help article with clear steps."],
   ["Turn complaints into a fix", "Ask me to paste a few complaints about the same thing, then write them up as one clear bug report with steps to reproduce and what to fix."],
  ], look: ROLE_LOOKS.fixer },
 { id: "builder", name: "Rivet", role: "Builder", area: "Dev and product",
  bubble: "Point me at the build. Let's see what breaks.",
  expect: ["Small tools and pages, built and tested in Still", "Bug reports with steps to reproduce", "Specs with acceptance checks from messy feedback"],
  learns: "I remember your product, your stack and how you like bugs written up, so each report needs less back and forth.",
  uses: ["github", "linear", "notion"],
  routine: ["Smoke-test my site (recall its link, or ask me for it): open the main pages, try the main paths and list anything broken, with steps to reproduce.", "09:30", [1]],
  job: "A builder for the user's dev and product work. Builds small web tools and pages in the working folder and runs them in a tab to test them, tests web releases like a careful user, files clear bug reports with steps to reproduce, turns feedback into short specs with acceptance checks, and reads docs and code to explain how things work. Never says something works before running it, and never submits or deploys anything without asking.",
  tone: "Practical and dry. Steps, evidence and no fluff.",
  asks: [
   ["Test my site", "Ask me for my site's link and what to check, then go through it like a new user and list anything broken or confusing, with steps to reproduce each."],
   ["Write a bug report", "Ask me what went wrong, then write a clear bug report: what happened, what should happen, steps to reproduce and how bad it is."],
   ["Turn feedback into a spec", "Ask me to paste user feedback, then group it into themes and write a short spec for the top one, with acceptance checks."],
   ["Explain an API", "Ask me which API or library, then read its docs and show me how to use it with one short example."],
  ], look: ROLE_LOOKS.builder },
 { id: "researcher", name: "Glint", role: "Researcher", area: "Research",
  bubble: "Ask me anything. Every answer comes with a source.",
  expect: ["Deep research with cited sources", "Compares options side by side", "Fact-checks claims before you share them"],
  learns: "I remember your market, your competitors and the sources you trust, so every brief starts further ahead.",
  uses: ["googledrive", "notion", "googlesheets"],
  routine: ["What changed in my market this week: launches, pricing and news from my competitors, each with a link. Recall who they are first.", "09:00", [1]],
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
export const OWN_EXPECT = ["Any job you describe, in your words", "Your pick of color, shape and name", "Its own memory, skills and routines"]

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
export const fromPremade = (p: Premade, id = ""): Companion => ({ id, name: p.name, face: "", color: "", job: p.job, tone: p.tone, mode: "default", look: lookKey(p.look), crew: p.id,
 routines: [{ id: p.id, text: p.routine[0], time: p.routine[1], days: p.routine[2], on: false }] })

/// One of Still's companions as a card, the same in setup and the library: a tint of its color, its mascot on a soft glow
/// (it waves when you point at it, and bounces when hired), its name and role, and what to expect. open: the mascot and
/// name open its details. children: its buttons; below: anything under the list.
function RoleCard({ hue, look, icon, name, role, expect, line, bubble, own, on, nudge, open, label, className, children, below }: {
 hue: string; look?: Look; icon?: ReactNode; name: string; role: string; expect?: string[]; line?: string; bubble?: string; own?: boolean; on?: boolean; nudge?: number
 open?: () => void; label?: string; className?: string; children?: ReactNode; below?: ReactNode
}) {
 const [move, setMove] = useState<[string, number]>(["", 0])
 const [was, setWas] = useState(on)
 if (was !== on) { setWas(on); if (on) setMove(["hired", Date.now()]) }
 if (nudge && nudge > move[1]) setMove(["pitch", nudge])
 const wave = () => { if (Date.now() - move[1] > 1500) setMove(["wave", Date.now()]) }
 const head = <><span className="role-glow">{look ? <Mascot look={look} size={72} follow gesture={move[0]} gestureAt={move[1]} /> : icon}</span>
  <span className="role-name"><b className="role-title">{name}</b><span className="role-tag">{role}</span></span></>
 return <article className={cn("role-card", on && "is-on", own && "is-own", className)} style={{ "--hue": hue } as CSSProperties} onMouseEnter={wave} onFocus={wave}>
  {open ? <button type="button" className="role-head" aria-label={label} onClick={open}>{head}</button> : <div className="role-head">{head}</div>}
  {bubble && <span className="role-bubble" aria-hidden>{bubble}</span>}
  {children && <div className="role-act">{children}</div>}
  <div className="role-expect">{expect ? <><h4>What to expect</h4><ul>{expect.map(e => <li key={e}>{e}</li>)}</ul></> : line && <p>{line}</p>}{below}</div>
 </article>
}

/// The roles as cards, then "Make your own". Ones the user already has say hi instead. In setup (`picked` given) every
/// card toggles Hire and Hired, and the ones you made show beside the roles. A card's mascot or name opens its details.
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
 const hire = (key: string, name: string, toggle: () => void) => <button className="role-btn crew-pick" aria-pressed={picked ? on(key) : undefined} aria-label={picked ? `${on(key) ? "Hired" : "Hire"} ${name}` : undefined} onClick={toggle}>{on(key) ? <><Check />Hired</> : <><Plus />Hire</>}</button>
 return <div className="role-grid crew-grid">
  {PREMADES.map(p => <RoleCard key={p.id} className={cn("crew-card", (on(p.id) || !!mine(p)) && "is-picked")} hue={p.look.color} look={p.look} name={p.name} role={p.role} expect={p.expect} bubble={p.bubble}
   on={on(p.id) || !!mine(p)} nudge={nudge[0] === p.id ? nudge[1] : 0} open={() => setMore(p)} label={`More about ${p.name}`}>
   {mine(p) ? <><span className="role-done crew-hired"><Check />Hired</span><button className="role-btn crew-pick" onClick={() => act(p)}>Say hi</button></> : hire(p.id, p.name, () => act(p))}
  </RoleCard>)}
  {made.map(c => <RoleCard key={c.id} className={cn("crew-card", on(c.id) && "is-picked")} hue={lookOf(c).color} look={lookOf(c)} name={c.name} role="Made by you" line={c.job || "All yours. Give them a job any time on the Companions page."} on={on(c.id)}>
   {hire(c.id, c.name, () => onMade?.(c.id))}
  </RoleCard>)}
  <RoleCard className="crew-card" own hue="var(--muted-foreground)" look={BLANK} name="Make your own" role="Any job" expect={OWN_EXPECT} open={onOwn} label="Make your own">
   <button className="role-btn crew-pick" onClick={onOwn}><Plus />Make</button>
  </RoleCard>
  {more && <Dialog open onOpenChange={o => { if (!o) setMore(null) }}>
   <DialogContent className="app-dialog crew-dialog" style={{ "--hue": more.look.color } as CSSProperties}>
    <div className="crew-dialog-hero"><Mascot look={more.look} size={150} follow gesture="wave" gestureAt={1} /></div>
    <DialogHeader><DialogTitle>{more.name}<span className="role-tag">{more.role}</span></DialogTitle><DialogDescription>{more.tone}</DialogDescription></DialogHeader>
    <div className="crew-dialog-body">
     <section><h4>What to expect</h4><ul>{more.expect.map(g => <li key={g}>{g}</li>)}</ul></section>
     <section><h4>Try asking</h4><ul className="crew-asks">{more.asks.map(([label, prompt]) => <li key={label}><b>{label}</b>{prompt}</li>)}</ul></section>
     <section><h4>How it gets better</h4><p>{more.learns}</p></section>
    </div>
    <Button className="crew-dialog-pick" onClick={() => act(more)}>{mine(more) ? `Say hi to ${more.name}` : on(more.id) ? `Hired. Let ${more.name} go` : `Hire ${more.name}`}</Button>
   </DialogContent>
  </Dialog>}
 </div>
}

/// "New companion": Still's own companions first, each a live mascot with its role and what to expect, then make your
/// own or paste one someone shared. A card's mascot or name opens its preview (the profile panel); Add hires it right
/// here. Ones you have say so.
export function CompanionLibrary({ have = [], onPreview, onAdd, onOpen, onOwn, onPaste, onClose }: {
 have?: Companion[]; onPreview: (p: Premade) => void; onAdd: (p: Premade) => void; onOpen: (id: string) => void; onOwn: () => void; onPaste: (c: Companion) => void; onClose: () => void
}) {
 const [pasting, setPasting] = useState(false)
 const [bad, setBad] = useState(false)
 const mine = (p: Premade) => have.find(c => premadeOf(c) === p)
 const pasted = (text: string) => { const c = fromShared(text); setBad(!c && !!text.trim()); if (c) onPaste(c) }
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog companion-library" onOpenAutoFocus={e => { e.preventDefault(); (e.target as HTMLElement).focus() }}>
   <DialogHeader><DialogTitle>Add a companion</DialogTitle><DialogDescription>Seven ready-made companions, each built for one part of your work.</DialogDescription></DialogHeader>
   <div className="role-grid library-grid">{PREMADES.map(p => { const got = mine(p); return <RoleCard key={p.id} className={cn("library-card", got && "is-added")} hue={p.look.color} look={p.look} name={p.name} role={p.role} expect={p.expect} on={!!got}
    open={() => got ? onOpen(got.id) : onPreview(p)} label={got ? `Open ${p.name}'s profile` : `Meet ${p.name}`}>
    {got ? <span className="role-done library-added"><Check />Added</span> : <button className="role-btn library-add" aria-label={`Add ${p.name}`} onClick={() => onAdd(p)}><Plus />Add</button>}
   </RoleCard> })}</div>
   <div className="role-grid library-more">
    <RoleCard className="library-own" own hue="var(--muted-foreground)" look={BLANK} name="Make your own" role="Any job" expect={OWN_EXPECT} open={onOwn} label="Make your own" />
    <RoleCard className="library-paste" hue="var(--muted-foreground)" icon={<ClipboardPaste />} name="Paste a shared companion" role="From a friend" open={() => setPasting(true)} label="Paste a shared companion"
     expect={pasting ? undefined : ["Their name, look, job and way of talking", "Starts fresh, knowing nothing about you", "Never brings their memory or files"]}
     below={pasting && <>
      <textarea autoFocus rows={2} aria-label="Shared companion" placeholder="Paste what they sent you. They copy it with Share, in their companion's profile." onPaste={e => { e.preventDefault(); pasted(e.clipboardData.getData("text")) }} onChange={e => pasted(e.target.value)} />
      {bad && <small className="library-bad" role="alert">That isn't a shared companion. Ask them to copy it again with Share.</small>}</>} />
   </div>
  </DialogContent>
 </Dialog>
}
