import { useEffect, useState, type CSSProperties, type ReactNode } from "react"
import { BadgeCheck, Braces, Bug, CalendarCheck, CalendarClock, Check, ChevronDown, ClipboardList, ClipboardPaste, FileText, FlaskConical, Funnel, Inbox, LayoutGrid, ListChecks, ListTodo, Mail,
 MousePointerClick, Newspaper, PenLine, Phone, Plus, Radar, Rocket, Scale, Sparkles, Target, TrendingUp, Users, X, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { BLANK, ROLE_LOOKS, lookKey, type Look } from "./look"
import { Mascot } from "./Mascot"
import { lookOf, type Companion } from "./Buddy"
import { PluginChip, andList, pluginName } from "./Plugins"
import type { LibrarySkill } from "./generate"

// Still's own instructions for each official role (still/Assets/roles, the same files the hosts send), by crew id.
export const ROLE_TEXT: Record<string, string> = Object.fromEntries(Object.entries(import.meta.glob<string>("../../still/Assets/roles/*.md", { query: "?raw", import: "default", eager: true }))
 .map(([path, text]) => [path.slice(path.lastIndexOf("/") + 1, -3), text.replace(/\r\n/g, "\n").trim()]))

// What each official role comes with (still/Assets/roles/<role>/): its skills, which Still adds to your skills and turns on
// for it when it's hired, and its knowledge files, which start empty and fill in as it works. Both are Markdown with front
// matter; the profile only needs each one's name and its line.
type KitFile = { id: string; name: string; line: string; when: string }
function kit(files: Record<string, string>, key: string) {
 const out: Record<string, KitFile[]> = {}
 for (const [path, text] of Object.entries(files)) {
  const [role, , file] = path.split("/").slice(-3), id = file.slice(0, -3), head: Record<string, string> = {}
  for (const l of /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)?.[1].split(/\r?\n/) ?? []) { const i = l.indexOf(":"); if (i > 0) head[l.slice(0, i).trim()] = l.slice(i + 1).trim() }
  ;(out[role] ??= []).push({ id, name: head.name || id, line: head[key] ?? "", when: head.when ?? "" })
 }
 return out
}
export const KIT_SKILLS = kit(import.meta.glob<string>("../../still/Assets/roles/*/skills/*.md", { query: "?raw", import: "default", eager: true }), "description")
/// Still's skill library for "Make your own" (generate.ts): every role kit's skills.
export const LIBRARY: LibrarySkill[] = Object.entries(KIT_SKILLS).flatMap(([role, list]) => list.map(k => ({ id: k.id, role, name: k.name, text: k.line + " " + k.when })))
export const KIT_KNOWLEDGE = kit(import.meta.glob<string>("../../still/Assets/roles/*/knowledge/*.md", { query: "?raw", import: "default", eager: true }), "about")
const SKILL_ICONS: Record<string, LucideIcon> = { "call-brief": Phone, "lead-list": Target, "follow-up": Mail, "pipeline-check": ListChecks, "funnel-audit": Funnel, "experiment-plan": FlaskConical,
 "lifecycle-emails": Mail, "weekly-numbers": TrendingUp, "plan-tomorrow": CalendarCheck, "meeting-brief": Users, "reply-queue": Inbox, "project-checklist": ListTodo, "voice-match": PenLine,
 "post-set": LayoutGrid, "launch-post": Rocket, "newsletter": Newspaper, "smoke-test": MousePointerClick, "bug-report": Bug, "feedback-spec": ClipboardList, "api-explainer": Braces,
 "research-brief": FileText, "option-compare": Scale, "claim-check": BadgeCheck, "market-watch": Radar }
const TILES = ["oklch(.62 .16 255)", "oklch(.64 .15 155)", "oklch(.72 .15 70)", "oklch(.64 .19 350)"] // the skill tiles' colors, in turn

// Still's own companions, ready to hire: each one owns a part of your work, and its card says what it does. How each
// one works in its field (method, tools, quality rules) is its role setup in still/Assets/roles. Hiring one makes a
// companion like any other, which the user can then change. The id is the role, so a name can change without breaking
// saved companions.
export type Premade = {
 id: string; name: string; role: string; area: string
 line: string // its card's one line on what it does
 summary: string // a line or two under its name on its profile
 about: string; tips: string[] // its profile's About and tips, in its own voice
 expect: string[] // "What to expect" on its setup card: three concrete things it does for you
 bubble: string // what it says when you hover it in setup
 uses: string[] // the apps it works in once they're connected (Plugins.tsx)
 routine: [string, string, number[], string] // the routine it comes with, off until the user turns it on: what, HH:MM, days (0 = Sunday), the skill it uses
 job: string; tone: string
 asks: [string, string][] // "What I'm good at": [label, a prompt that works in Still today]
 look: Look
}

export const PREMADES: Premade[] = [
 { id: "sales", name: "Jonah", role: "Sales", area: "Deals and leads",
  line: "Briefs you before calls, finds leads and drafts follow-ups.",
  summary: "Preps you for every sales call, finds leads that fit and keeps your deals moving with follow-ups in your voice.",
  about: "Hi, I'm Jonah. I'm here to keep your deals moving. I learn what you sell and who buys it, brief you before calls, find leads that fit and draft every follow-up in your voice. I keep a simple pipeline with a next step and a date for every deal. I won't send, post or change anything without your OK.",
  tips: ["Tell me what you sell and who it's for on day one. Every brief and lead list starts there.", "Paste a deal's last email and I'll draft the next one in your voice.", "Turn on my pipeline check and I'll flag the deals going cold every weekday morning."],
  bubble: "Give me your toughest lead. I like a challenge.",
  expect: ["A one-page brief before every sales call", "Lead lists that fit who you sell to", "Follow-ups in your voice, sent only on your OK"],
  uses: ["gmail", "hubspot", "googlecalendar"],
  routine: ["Check my pipeline: list the deals with no next step or going cold, and draft a short follow-up for each. Don't send anything.", "09:00", [1, 2, 3, 4, 5], "pipeline-check"],
  job: "Sales for the user. Learns what the user sells and to whom, researches leads and companies from public information, preps a one-page brief before each call, drafts outreach and follow-ups in the user's voice, and keeps a simple pipeline table with a next step and a date for every deal. Never sends, books or posts anything without asking first, and never makes up a number.",
  tone: "Bold and upbeat. Talks in next steps and dates, and gets straight to what moves the deal.",
  asks: [
   ["Prep me for a call", "I have a sales call coming up. Ask me with which company, then research them from public sources and give me a one-page brief: what they do, recent news, who I'm likely talking to and three smart questions to ask."],
   ["Build a lead list", "Ask me what I sell and who it's for, then find 20 companies that fit, using public information only. Save them as a CSV with the company, website, why they fit and who to contact."],
   ["Write a first email", "Ask me who I'm writing to and what I sell, then write three short first emails in my voice, each under 90 words with one clear ask."],
   ["Tidy my pipeline", "Ask me to paste or describe my open deals, then turn them into a table with the stage, the next step and a date for each, and flag the ones going cold."],
  ], look: ROLE_LOOKS.sales },
 { id: "growth", name: "Talia", role: "Growth", area: "Signups and retention",
  line: "Finds where people drop off and plans small tests to fix it.",
  summary: "Finds where people drop off on the way to paying, plans small experiments to fix it and tracks what worked.",
  about: "Hi, I'm Talia. I find the leaks between someone visiting and someone paying, and I plan small tests to fix them, one metric each. I write the copy and emails a test needs and keep a record of every result, so we never run the same test twice. I won't send, post or change anything without your OK.",
  tips: ["Give me your site's link first. I'll walk through it like a newcomer and show you where people leave.", "Share your numbers, even rough ones. A baseline makes every test easier to read.", "Turn on my Monday numbers and I'll tell you what moved and what to try next."],
  bubble: "Show me where people drop off. Let's fix the leak.",
  expect: ["The biggest leak in your funnel, with the number", "Small experiments ranked, one metric each", "Ready-to-run copy, launched only on your OK"],
  uses: ["googlesheets", "stripe", "notion"],
  routine: ["Check this week's growth numbers: signups, activation and churn against last week, the biggest change and one experiment to try. Don't change anything.", "09:00", [1], "weekly-numbers"],
  job: "Growth for the user's product. Finds where people drop off between visiting, signing up, getting value and paying, plans small experiments with one metric each, drafts the copy and emails they need, and tracks what worked. Never launches, sends or changes anything live without asking, and never uses tricks that mislead people.",
  tone: "Curious and upbeat. Talks in numbers and bets, and celebrates small wins.",
  asks: [
   ["Find my funnel leak", "Ask me for my site's link, then walk through it like a first-time visitor and tell me the three places people most likely drop off, with a fix for each."],
   ["Plan three experiments", "Ask me what I want more of (signups, activation or paying users), then plan three small experiments, each with a hypothesis, one metric, the effort and when to stop it."],
   ["Write onboarding emails", "Ask me what my product does and what a new user should do first, then write three short onboarding emails that get them there."],
   ["Size up a competitor", "Ask me for a competitor, then read their landing, pricing and signup pages and tell me what they do better than me and one thing to try."],
  ], look: ROLE_LOOKS.growth },
 { id: "planner", name: "Nora", role: "Planner", area: "Your day",
  line: "Plans your days, briefs your meetings and lists what's waiting on you.",
  summary: "Plans tomorrow with what matters first, briefs you before meetings and keeps a short list of what's waiting on you.",
  about: "Hi, I'm Nora. I turn a full calendar and a busy inbox into one short plan, most important first. I brief you before meetings, list what's waiting on you with replies ready, and break projects into steps with dates. I won't send, post or change anything without your OK, and that includes your calendar.",
  tips: ["Tell me your top three priorities. I'll plan every day around them.", "Ask me what's waiting on you whenever your inbox feels heavy.", "Turn on my evening plan and tomorrow's list is ready before you log off."],
  bubble: "Hand me the chaos. You get back a plan.",
  expect: ["Tomorrow planned tonight, most important first", "A two-minute brief before each meeting", "What's waiting on you, with replies drafted"],
  uses: ["gmail", "googlecalendar", "slack"],
  routine: ["Plan tomorrow: open my calendar and inbox, then give me one short list, most important first, with what I could move or skip.", "17:30", [1, 2, 3, 4, 5], "plan-tomorrow"],
  job: "A planner for the user's days and projects. Plans tomorrow with the important things first, briefs the user before meetings, keeps a short list of what's waiting on them and drafts the replies, and turns projects into checklists with owners and dates. Works in the user's own calendar and mail in Still's tabs when asked. Asks before sending, accepting, declining or changing anything.",
  tone: "Composed and organized. Short lists, clear priorities and one next step at a time.",
  asks: [
   ["Plan tomorrow", "Open my calendar and plan tomorrow for me: what matters most, when to do it, and what I could move or skip. Keep it to one short list."],
   ["Brief my next meeting", "Open my calendar, find my next meeting and brief me: who's coming, what they do and what I should get out of it."],
   ["What's waiting on me?", "Open my inbox and list what's waiting on a reply from me, most urgent first, with a one-line draft for each. Don't send anything."],
   ["Turn a project into a checklist", "Ask me about a project, then turn it into a checklist with owners and dates, and save it as Markdown."],
  ], look: ROLE_LOOKS.planner },
 { id: "marketing", name: "Leo", role: "Marketing", area: "Posts and launches",
  line: "Turns one idea into posts, launches and newsletters in your voice.",
  summary: "Learns your voice, turns one idea into posts for every platform and drafts your launches and newsletters.",
  about: "Hey, I'm Leo! Give me one idea and I'll turn it into posts for every platform, plus launch posts and newsletters, all in your voice. I learn how you write from your own examples and keep notes on what lands. Everything I make is a draft: I won't send, post or change anything without your OK.",
  tips: ["Send me two or three things you wrote. I'll learn your voice before I write a word.", "Tell me when a post does well. I'll keep notes and do more of what works.", "Turn on my Friday drafts and next week's posts are waiting for you."],
  bubble: "One idea in, a whole week of posts out. Let's go!",
  expect: ["One idea turned into posts for every platform", "Launch posts and newsletters in your voice", "Drafts only: nothing posts without you"],
  uses: ["linkedin", "notion", "googledocs"],
  routine: ["Draft next week's posts: three ideas in my voice from what I've shared lately, each with a hook. Don't post anything.", "15:00", [5], "post-set"],
  job: "Marketing for the user's posts, launches and newsletters. Learns the user's voice from examples, turns one idea into posts sized for each platform, and drafts launch posts, newsletters and landing page copy. Drafts only: shows every draft and never posts, schedules or sends anything itself.",
  tone: "Energetic and punchy. Big on hooks, short sentences and a clear call to action.",
  asks: [
   ["Learn my voice", "Ask me for two or three links to things I've written, read them, then sum up my voice in five short rules and remember them."],
   ["One idea, every platform", "Ask me for one idea or announcement, then write a post for X, one for LinkedIn, one for Instagram and a two-line email teaser, each in my voice."],
   ["Draft a newsletter", "Ask me what this issue is about and who reads it, then draft a short newsletter in my voice with a subject line and three options for the opening line."],
   ["Write a launch post", "Ask me what I'm launching and who it's for, then write a launch post with three hooks to choose from."],
  ], look: ROLE_LOOKS.marketing },
 { id: "engineer", name: "Ivan", role: "Engineer", area: "Code and product",
  line: "Tests your site, writes clear bug reports and turns feedback into specs.",
  summary: "Tests your site like a careful user, writes bug reports anyone can follow and turns feedback into specs with checks.",
  about: "I'm Ivan. I test your site the way a careful user would, write bugs up with steps anyone can follow, and turn messy feedback into short specs with checks. I build small tools and pages when you need them, and I never say something works before I've run it. I won't send, post or change anything without your OK.",
  tips: ["Give me your site's link and the paths that matter most. I'll test those first.", "Tell me how your team likes bugs written. I'll use that format every time.", "Turn on my Monday smoke test and broken pages won't wait for a user to find them."],
  bubble: "Point me at the build. Let's see what breaks.",
  expect: ["Small tools and pages, built and tested in Still", "Bug reports with steps to reproduce", "Specs with acceptance checks from messy feedback"],
  uses: ["github", "linear", "notion"],
  routine: ["Smoke-test my site (recall its link, or ask me for it): open the main pages, try the main paths and list anything broken, with steps to reproduce.", "09:30", [1], "smoke-test"],
  job: "An engineer for the user's code and product. Builds small web tools and pages in the working folder and runs them in a tab to test them, tests web releases like a careful user, files clear bug reports with steps to reproduce, turns feedback into short specs with acceptance checks, and reads docs and code to explain how things work. Never says something works before running it, and never submits or deploys anything without asking.",
  tone: "Practical and dry. Steps, evidence and no fluff.",
  asks: [
   ["Test my site", "Ask me for my site's link and what to check, then go through it like a new user and list anything broken or confusing, with steps to reproduce each."],
   ["Write a bug report", "Ask me what went wrong, then write a clear bug report: what happened, what should happen, steps to reproduce and how bad it is."],
   ["Turn feedback into a spec", "Ask me to paste user feedback, then group it into themes and write a short spec for the top one, with acceptance checks."],
   ["Explain an API", "Ask me which API or library, then read its docs and show me how to use it with one short example."],
  ], look: ROLE_LOOKS.engineer },
 { id: "research", name: "Maya", role: "Research", area: "Answers with sources",
  line: "Researches anything and backs every claim with a source.",
  summary: "Digs into any question, compares your options side by side and backs every claim with a source you can check.",
  about: "Hi, I'm Maya. Ask me anything and I'll come back with the answer first, then the evidence, with a link for every claim. I compare options side by side, check claims before you share them and keep an eye on your market. When sources disagree or I'm not sure, I'll say so. I won't send, post or change anything without your OK.",
  tips: ["Tell me who your competitors are. I'll watch them for you every week.", "Name the sources you trust, and the ones you don't. I'll weigh them that way.", "Ask me to check a claim before you share it. It only takes a minute."],
  bubble: "Ask me anything. Every answer comes with a source.",
  expect: ["Deep research with cited sources", "Compares options side by side", "Fact-checks claims before you share them"],
  uses: ["googledrive", "notion", "googlesheets"],
  routine: ["What changed in my market this week: launches, pricing and news from my competitors, each with a link. Recall who they are first.", "09:00", [1], "market-watch"],
  job: "Research for the user. Digs into topics, compares sources and writes short briefs with a citation for every claim. Answers hard questions from solid sources, compares tools, vendors and options in one table, checks whether claims hold up, and looks into the user's market and competitors when asked. Says plainly when something is uncertain or the sources disagree.",
  tone: "Precise and direct. Leads with the answer, then the evidence, and flags weak sources.",
  asks: [
   ["Brief me on a topic", "Ask me for a topic, then give me a one-page brief with the key facts and a source link for every claim."],
   ["Compare my options", "Ask me what I'm choosing between, then compare the options in one table: price, strengths, weaknesses and who each is best for, with sources."],
   ["Check a claim", "Ask me for a claim I've seen, then check it against solid sources and tell me whether it holds up, with links."],
   ["What changed in my market?", "Ask me about my market and competitors, then find what changed in the last month: launches, pricing and news, each with a link. Remember the competitors for next time."],
  ], look: ROLE_LOOKS.research },
]
/// The role a companion was hired for, if any (its `crew`). Renaming or changing it keeps the link.
export const premadeOf = (c?: { crew?: string }) => c?.crew ? PREMADES.find(p => p.id === c.crew) : undefined
/// How a companion is introduced: its role in front of its name ("Research Maya"). Chat headers and the switcher use the name.
export const titled = (p: Premade, name = p.name) => p.role + " " + name
/// A companion's name, role first like "Research Maya": its own Role, else its crew role, else just the name.
export const introName = (c: Companion) => { const p = premadeOf(c), role = c.role?.trim() || p?.role; return role ? role + " " + c.name : c.name }
const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
/// When a routine runs, the way people say it: "Every weekday at 9:00".
export const schedule = (days: number[], time: string) => (days.length === 7 ? "Every day" : days.join() === "1,2,3,4,5" ? "Every weekday" : days.join() === "0,6" ? "Every weekend"
 : "Every " + andList(days.map(d => DAY_NAMES[d]))) + " at " + time.replace(/^0(?=\d:)/, "")
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
export const tasksFor = (interests: string[] = []) => {
 const into = interests.map(i => i.toLowerCase())
 return TASKS.filter(t => t[0] && into.some(i => t[0].toLowerCase().includes(i) || i.includes(t[0].toLowerCase().split(" ")[0])))
}
export function starters(interests: string[] = [], companion?: { crew?: string }, count = 4): [string, string][] {
 const mine = tasksFor(interests)
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
  const personality = ["direct", "warm", "playful", "formal"].includes(got.personality) ? got.personality : "", length = ["short", "detailed"].includes(got.length) ? got.length : "balanced"
  return { id: crypto.randomUUID().replace(/-/g, "").slice(0, 10), name: got.name.trim().slice(0, 24), face: "", color: "", job: String(got.job ?? ""), tone: String(got.tone ?? ""), look: String(got.look ?? ""), mode: got.mode, crew: String(got.crew ?? ""),
   role: String(got.role ?? "").slice(0, 30), personality, length }
 } catch { return null }
}

/// A new companion hired from a role: same name, job, way of talking and look, then it's the user's to change. Its
/// routine calls its skill (/id), and Still adds the role's skills and knowledge files as it saves it (Equip).
export const fromPremade = (p: Premade, id = ""): Companion => ({ id, name: p.name, face: "", color: "", job: p.job, tone: p.tone, mode: "default", look: lookKey(p.look), crew: p.id,
 routines: [{ id: p.id, text: `/${p.routine[3]} ${p.routine[0]}`, time: p.routine[1], days: p.routine[2], on: false }] })

// The gesture a companion plays when it joins the team: its Blender "yes!" (looks without one do the hired bounce).
const JOINED_GESTURE = "yes"
/// A companion just joined: it celebrates, then the user starts its first chat (it opens with a task and one question)
/// or carries on.
export function JoinedCard({ companion, onStart, onLater }: { companion: Companion; onStart: () => void; onLater: () => void }) {
 const look = lookOf(companion), role = premadeOf(companion)
 return <Dialog open onOpenChange={o => { if (!o) onLater() }}>
  <DialogContent className="app-dialog crew-dialog joined-card" style={{ "--hue": look.color } as CSSProperties}>
   <div className="crew-dialog-hero"><Mascot look={look} size={212} follow gesture={JOINED_GESTURE} gestureAt={1} /><span className="joined-badge" aria-hidden><Check /></span></div>
   <DialogHeader><DialogTitle>{introName(companion)} joined your team</DialogTitle>
    <DialogDescription>{role ? `${companion.name} is here for ${role.area.toLowerCase()}, and will open with a first task picked for your work.`
     : `${companion.name} will open with a first task and one question about how you like things done.`}</DialogDescription></DialogHeader>
   <div className="joined-actions"><Button variant="ghost" onClick={onLater}>Not now</Button><Button autoFocus onClick={onStart}>Start chatting</Button></div>
  </DialogContent>
 </Dialog>
}

/// One of Still's companions as a card, the same in setup and the library. It's built around the character: a tall art
/// area in a tint of its color with the mascot big and whole on a contact shadow, playing its idle (it waves when you
/// point at the card, and bounces when hired), then its name (with its role in front), what it does, its buttons and
/// View profile. role: a small tag under the name, for cards that aren't one of the six. compact (or no look): the mascot
/// or icon small beside the name. open: the art, the name and View profile open its profile. children: its buttons;
/// below: anything under the list.
function RoleCard({ hue, look, icon, name, role, expect, line, bubble, own, on, nudge, open, label, compact, className, children, below }: {
 hue: string; look?: Look; icon?: ReactNode; name: string; role?: string; expect?: string[]; line?: string; bubble?: string; own?: boolean; on?: boolean; nudge?: number
 open?: () => void; label?: string; compact?: boolean; className?: string; children?: ReactNode; below?: ReactNode
}) {
 const [move, setMove] = useState<[string, number]>(["", 0])
 const [was, setWas] = useState(on)
 if (was !== on) { setWas(on); if (on) setMove(["hired", Date.now()]) }
 if (nudge && nudge > move[1]) setMove(["pitch", nudge])
 const wave = () => { if (Date.now() - move[1] > 1500) setMove(["wave", Date.now()]) }
 const head = <><span className="role-glow">{look ? <Mascot look={look} size={72} follow gesture={move[0]} gestureAt={move[1]} /> : icon}</span>
  <span className="role-name"><b className="role-title">{name}</b>{role && <span className="role-tag">{role}</span>}</span></>
 const list = <div className="role-expect">{expect ? <><h4>What to expect</h4><ul>{expect.map(e => <li key={e}>{e}</li>)}</ul></> : line && <p>{line}</p>}{below}</div>
 if (look && !compact) {
  // 260px: the whole body with room for every gesture, about 70% of the stage; the top of the box is empty headroom
  const art = <Mascot look={look} size={260} follow gesture={move[0]} gestureAt={move[1]} />
  return <article className={cn("role-card is-art", on && "is-on", own && "is-own", className)} style={{ "--hue": hue } as CSSProperties} onMouseEnter={wave} onFocus={wave}>
   {open ? <button type="button" className="role-art" aria-label={label} onClick={open}>{art}</button> : <div className="role-art">{art}</div>}
   {bubble && <span className="role-bubble" aria-hidden>{bubble}</span>}
   <div className="role-body">
    <span className="role-name"><b className="role-title">{name}</b>{role && <span className="role-tag">{role}</span>}</span>
    {list}
    <div className="role-act">{children}{open && !own && <button type="button" className="role-profile" onClick={open}>View profile</button>}</div>
   </div>
  </article>
 }
 return <article className={cn("role-card", on && "is-on", own && "is-own", className)} style={{ "--hue": hue } as CSSProperties} onMouseEnter={wave} onFocus={wave}>
  {open ? <button type="button" className="role-head" aria-label={label} onClick={open}>{head}</button> : <div className="role-head">{head}</div>}
  {bubble && <span className="role-bubble" aria-hidden>{bubble}</span>}
  {children && <div className="role-act">{children}</div>}
  {list}
 </article>
}

/// The roles as cards, then "Make your own". Ones the user already has say hi instead. In setup (`picked` given) every
/// card toggles Hire and Hired, and the ones you made show beside the roles. A card's mascot or View profile opens its profile.
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
  {PREMADES.map(p => <RoleCard key={p.id} className={cn("crew-card", (on(p.id) || !!mine(p)) && "is-picked")} hue={p.look.color} look={p.look} name={titled(p)} expect={p.expect} bubble={p.bubble}
   on={on(p.id) || !!mine(p)} nudge={nudge[0] === p.id ? nudge[1] : 0} open={() => setMore(p)} label={`${titled(p)}'s profile`}>
   {mine(p) ? <><span className="role-done crew-hired"><Check />Hired</span><button className="role-btn crew-pick" onClick={() => act(p)}>Say hi</button></> : hire(p.id, titled(p), () => act(p))}
  </RoleCard>)}
  {made.map(c => <RoleCard key={c.id} className={cn("crew-card", on(c.id) && "is-picked")} hue={lookOf(c).color} look={lookOf(c)} name={c.name} role="Made by you" line={c.job || "All yours. Give them a job any time on the Companions page."} on={on(c.id)}>
   {hire(c.id, c.name, () => onMade?.(c.id))}
  </RoleCard>)}
  <RoleCard className="crew-card" own compact hue="var(--muted-foreground)" look={BLANK} name="Make your own" role="Any job" expect={OWN_EXPECT} open={onOwn} label="Make your own">
   <button className="role-btn crew-pick" onClick={onOwn}><Plus />Make</button>
  </RoleCard>
  {more && <CompanionProfile p={more} hired={on(more.id) || !!mine(more)} onHire={() => act(more)} onClose={() => setMore(null)} />}
 </div>
}

/// A companion's profile before you hire it (View profile, in the library and setup): who it is and everything hiring it
/// gives you. Its card stays put on the left while the sections on the right scroll. Every count is real: the role's kit
/// (still/Assets/roles/<role>/), its routine and the apps it works in.
export function CompanionProfile({ p, hired, onHire, onClose }: { p: Premade; hired: boolean; onHire: () => void; onClose: () => void }) {
 const [full, setFull] = useState(false)
 const skills = KIT_SKILLS[p.id] ?? [], files = KIT_KNOWLEDGE[p.id] ?? [], title = titled(p)
 const [text, time, days, skill] = p.routine, at = text.indexOf(": "), uses = skills.find(k => k.id === skill)
 const counts: [number, string, string][] = [[skills.length, "Skill", "Skills"], [1, "Routine", "Routines"], [files.length, "Knowledge file", "Knowledge files"], [p.uses.length, "App", "Apps"]]
 const say = (lines: string[]) => <div className="hire-profile-say"><Mascot look={p.look} size={32} /><div>{lines.map(l => <p key={l}>{l}</p>)}</div></div>
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="hire-profile" showCloseButton={false} style={{ "--hue": p.look.color } as CSSProperties}>
   <aside className="hire-profile-card">
    <div className="hire-profile-art"><Mascot look={p.look} size={230} follow gesture="wave" gestureAt={1} /></div>
    <DialogClose className="hire-profile-close" aria-label="Close"><X /></DialogClose>
    <DialogTitle>{title}</DialogTitle>
    <DialogDescription>{p.summary}</DialogDescription>
    {hired ? <span className="hire-profile-hired"><Check />Hired</span> : <button type="button" className="hire-profile-hire" onClick={onHire}>Hire {title}</button>}
    <div className="hire-profile-works"><h4>Works in</h4>
     <div>{p.uses.map(slug => <PluginChip key={slug} slug={slug} name={pluginName(slug)} />)}<span className="plug-chip is-web"><Plus />Any website</span></div></div>
   </aside>
   <div className="hire-profile-main">
    <section className="hire-profile-section"><h3>What's included</h3>
     <div className="hire-profile-counts">{counts.map(([n, one, many]) => <div key={one}><b>{n}</b><span>{n === 1 ? one : many}</span></div>)}</div></section>
    <section className="hire-profile-section"><h3>Skills</h3>
     <div className="hire-profile-skills">{skills.map((k, i) => { const Icon = SKILL_ICONS[k.id] ?? Sparkles; return <div key={k.id} className="hire-profile-skill" style={{ "--tile": TILES[i % TILES.length] } as CSSProperties}>
      <span aria-hidden><Icon /></span><b>{k.name}</b><small>{k.line}</small></div> })}</div></section>
    <section className="hire-profile-section"><h3>Routines</h3>
     <div className="hire-profile-routine"><span aria-hidden><CalendarClock /></span><div>
      <b>{at > 0 ? text.slice(0, at) : text}</b><small>{schedule(days, time)}{uses && <> · uses {uses.name}</>}</small>
      {at > 0 && <p>{text[at + 2].toUpperCase() + text.slice(at + 3)}</p>}</div></div>
     <p className="hire-profile-note">Routines stay off until you turn them on. {p.name} also suggests one in chat when it would help.</p></section>
    <section className="hire-profile-section"><h3>Knowledge files</h3>
     <ul className="hire-profile-files">{files.map(f => <li key={f.id}><FileText aria-hidden /><div><b>{f.name}</b><small>{f.line}</small></div></li>)}</ul>
     <p className="hire-profile-note">They start empty and fill in as you work together. You can read them any time in {p.name}'s profile.</p></section>
    <section className="hire-profile-section"><h3>About</h3>{say([p.about])}</section>
    <section className="hire-profile-section"><h3>Tips</h3>{say(p.tips)}</section>
    {ROLE_TEXT[p.id] && <section className="hire-profile-section">
     <button type="button" className="hire-profile-full" aria-expanded={full} onClick={() => setFull(!full)}>See full instructions<ChevronDown /></button>
     {full && <div className="crew-instructions hire-profile-instructions" tabIndex={0}>{ROLE_TEXT[p.id]}</div>}</section>}
   </div>
  </DialogContent>
 </Dialog>
}

/// "Hire a companion": Still's own companions first, each a live mascot with its role, its name and one line on what it
/// does, then make your own or paste one someone shared. Hire hires it right here; View profile (or the art) opens its
/// profile. Ones you have say Hired.
export function CompanionLibrary({ have = [], onProfile, onAdd, onOwn, onPaste, onClose }: {
 have?: Companion[]; onProfile: (p: Premade) => void; onAdd: (p: Premade) => void; onOwn: () => void; onPaste: (c: Companion) => void; onClose: () => void
}) {
 const [pasting, setPasting] = useState(false)
 const [bad, setBad] = useState(false)
 const mine = (p: Premade) => have.find(c => premadeOf(c) === p)
 const pasted = (text: string) => { const c = fromShared(text); setBad(!c && !!text.trim()); if (c) onPaste(c) }
 return <Dialog open onOpenChange={o => { if (!o) onClose() }}>
  <DialogContent className="app-dialog companion-library" onOpenAutoFocus={e => { e.preventDefault(); (e.target as HTMLElement).focus() }}>
   <DialogHeader><DialogTitle>Hire a companion</DialogTitle><DialogDescription>Each one comes with instructions and skills for its role, and starts working as soon as you hire it.</DialogDescription></DialogHeader>
   <div className="role-grid library-grid">{PREMADES.map(p => { const got = mine(p); return <RoleCard key={p.id} className={cn("library-card", got && "is-added")} hue={p.look.color} look={p.look} name={titled(p)} line={p.line} on={!!got}
    open={() => onProfile(p)} label={`${titled(p)}'s profile`}>
    {got ? <span className="library-added">Hired<Check /></span> : <button className="role-hire library-add" aria-label={`Hire ${titled(p)}`} onClick={() => onAdd(p)}>Hire</button>}
   </RoleCard> })}</div>
   <div className="role-grid library-more">
    <RoleCard className="library-own" compact own hue="var(--muted-foreground)" look={BLANK} name="Make your own" role="Any job" expect={OWN_EXPECT} open={onOwn} label="Make your own" />
    <RoleCard className="library-paste" hue="var(--muted-foreground)" icon={<ClipboardPaste />} name="Paste a shared companion" role="From a friend" open={() => setPasting(true)} label="Paste a shared companion"
     expect={pasting ? undefined : ["Their name, look, job and way of talking", "Starts fresh, knowing nothing about you", "Never brings their memory or files"]}
     below={pasting && <>
      <textarea autoFocus rows={2} aria-label="Shared companion" placeholder="Paste what they sent you. They copy it with Share, in their companion's profile." onPaste={e => { e.preventDefault(); pasted(e.clipboardData.getData("text")) }} onChange={e => pasted(e.target.value)} />
      {bad && <small className="library-bad" role="alert">That isn't a shared companion. Ask them to copy it again with Share.</small>}</>} />
   </div>
  </DialogContent>
 </Dialog>
}
