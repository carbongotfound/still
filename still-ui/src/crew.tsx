import { useState, type CSSProperties } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { BLANK, DEFAULT_LOOK, lookKey, type Look } from "./look"
import { Mascot } from "./Mascot"
import type { Companion } from "./Buddy"

// Still's own companions, ready to pick: each has its own body, prop, idle and gesture (tools/mascot), a job for the
// AI, and a way of talking. Picking one makes a companion like any other, which the user can then change.
export type Premade = { id: string; name: string; role: string; pitch: string; job: string; tone: string; good: string[]; starters: string[]; look: Look }
const look = (l: Partial<Look>): Look => ({ ...DEFAULT_LOOK, blush: true, ...l })

export const PREMADES: Premade[] = [
 { id: "hazel", name: "Hazel", role: "Cooking",
  pitch: "Turns whatever's in your fridge into dinner, with recipes that fit your time, your diet and your skills.",
  job: "A home cook. Finds well-reviewed recipes for what the user has, scales them for any number of people, suggests swaps, and writes the shopping list.",
  tone: "Cozy and encouraging, with a little kitchen humor. Gives exact amounts and times, never a vague pinch.",
  good: ["Dinner from what's in the fridge", "Scaling a recipe up or down", "Shopping lists sorted by aisle"],
  starters: ["What can I make with eggs, spinach and rice?", "Plan five easy weeknight dinners and a shopping list", "Make this recipe for 8 people instead of 4"],
  look: look({ body: "hazel", color: "#c4a8e6", eyes: "iris", pupil: .2, brows: "thin", mouth: "smile", glasses: "round", hair: "bun", hairColor: "#6b4a35" }) },
 { id: "rio", name: "Rio", role: "Deals",
  pitch: "Hunts down the best price, lines stores up side by side and spots the catch before you pay.",
  job: "A deal hunter. Compares prices across stores, checks shipping, returns and reviews, and flags fake discounts.",
  tone: "Upbeat and quick. Gets excited about a real bargain, and is blunt about a bad one.",
  good: ["Price checks across stores", "Spotting fake discounts", "Finding coupon codes that still work"],
  starters: ["Find the best price for AirPods Pro", "Is this a good deal? Check the price history", "Find a gift under $40 for someone who loves coffee"],
  look: look({ body: "rio", color: "#f2c66b", eyes: "sparkle", brows: "soft", mouth: "grin", hair: "tuft", hairColor: "#d4683f" }) },
 { id: "juno", name: "Juno", role: "Planning",
  pitch: "Turns trips, events and busy weeks into clear plans with times, costs and a checklist.",
  job: "A planner. Breaks big things into steps, works out times and costs, and ends with a checklist.",
  tone: "Steady under pressure, organized and warm. Likes tables, timelines and a clear next step.",
  good: ["Trip plans, day by day", "Event checklists", "Comparing options in one table"],
  starters: ["Plan a weekend away for two", "Make a packing list for a beach trip", "Plan a birthday dinner for six people"],
  look: look({ body: "juno", color: "#7fb39b", eyes: "almond", brows: "straight", mouth: "smile", hair: "bob", hairColor: "#2c2f3a" }) },
 { id: "bram", name: "Bram", role: "Movies & music",
  pitch: "Picks something to watch tonight, finds where it's streaming and makes playlists for any mood.",
  job: "A film and music buff. Recommends movies, shows and music to match the user's taste, says where to stream them, and builds playlists.",
  tone: "Laid-back and enthusiastic, with dry jokes. Never spoils an ending unless asked.",
  good: ["Picking something to watch tonight", "Finding where a movie is streaming", "Playlists for any mood"],
  starters: ["Pick a movie for tonight, something like Arrival", "Where can I stream the new season of my show?", "Make a playlist for a rainy Sunday"],
  look: look({ body: "bram", color: "#7aa3dc", eyes: "bean", brows: "fluffy", mouth: "smirk", hat: "headphones" }) },
 { id: "wren", name: "Wren", role: "Writing",
  pitch: "Drafts emails, posts and stories in your voice, then tightens them until they shine.",
  job: "A writer and editor. Drafts in the user's voice, offers a couple of options, and trims every sentence that doesn't earn its place.",
  tone: "Warm and a little playful. Honest about what isn't working, and always offers a better line.",
  good: ["Emails that get answered", "Posts and captions", "Editing for clarity"],
  starters: ["Help me write a friendly follow-up email", "Write three captions for a photo of my dog", "Make this paragraph shorter and clearer"],
  look: look({ body: "wren", color: "#eea0b4", eyes: "lashes", brows: "arch", mouth: "cat", hat: "beret" }) },
 { id: "pip", name: "Pip", role: "News",
  pitch: "Catches you up on what happened today in a few short bullets, each with a link.",
  job: "A news scout. Finds what matters today from reliable outlets, keeps it short, and links every story.",
  tone: "Bright and quick, with a reporter's nose. Separates facts from opinions.",
  good: ["Today's news in five bullets", "Following a story as it develops", "Both sides of a debate"],
  starters: ["Catch me up on today's top news", "What's new in tech this week?", "Explain both sides of a story in the news"],
  look: look({ body: "pip", color: "#9fd3ea", eyes: "button", brows: "dots", mouth: "grin", hat: "newsboy" }) },
]
/// The official companion a companion was picked from, if it still has that name and body.
export const premadeOf = (c?: { name: string; look?: string }) => {
 if (!c?.look) return undefined
 try { const body = JSON.parse(c.look).body; return PREMADES.find(p => p.name === c.name && p.look.body === body) } catch { return undefined }
}

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
export function starters(interests: string[] = [], companion?: { name: string; look?: string }, count = 4): [string, string][] {
 const into = interests.map(i => i.toLowerCase())
 const mine = TASKS.filter(t => t[0] && into.some(i => t[0].toLowerCase().includes(i) || i.includes(t[0].toLowerCase().split(" ")[0])))
 const own = premadeOf(companion)?.starters.map(s => [s, s] as [string, string]) ?? []
 const all: [string, string][] = [...mine.map(t => [t[1], t[2]] as [string, string]), ...own, ...TASKS.filter(t => !mine.includes(t)).map(t => [t[1], t[2]] as [string, string])]
 return all.filter((t, i) => all.findIndex(x => x[0] === t[0]) === i).slice(0, count)
}

/// A new companion made from an official one: same name, job, way of talking and look, then it's the user's to change.
export const fromPremade = (p: Premade, id = ""): Companion => ({ id, name: p.name, face: "", color: "", job: p.job, tone: p.tone, mode: "default", look: lookKey(p.look) })
const SILHOUETTE: Look = { ...BLANK, color: "#c4c4ca" }

/// The crew as profile cards, round portrait first, then "Make your own". Ones the user already has say hi instead.
export function CrewCards({ have = [], onPick, onOwn, onChat }: { have?: Companion[]; onPick: (p: Premade) => void; onOwn: () => void; onChat?: (id: string) => void }) {
 const [more, setMore] = useState<Premade | null>(null)
 const mine = (p: Premade) => onChat && have.find(c => premadeOf(c) === p)
 const act = (p: Premade) => { const c = mine(p); setMore(null); if (c) onChat!(c.id); else onPick(p) }
 return <div className="crew-grid">
  {PREMADES.map(p => <article key={p.id} className="crew-card" style={{ "--hue": p.look.color } as CSSProperties}>
   <div className="crew-portrait"><Mascot look={p.look} size={118} follow /></div>
   <div className="crew-info">
    <h3>{p.name}</h3><span className="crew-role">{p.role}</span>
    <p>{p.pitch}</p>
    <div className="crew-actions"><button className="crew-pick" onClick={() => act(p)}>{mine(p) ? "Say hi" : `Pick ${p.name}`}</button><button className="crew-more" onClick={() => setMore(p)}>About {p.name}</button></div>
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
    <Button className="crew-dialog-pick" onClick={() => act(more)}>{mine(more) ? `Say hi to ${more.name}` : `Pick ${more.name}`}</Button>
   </DialogContent>
  </Dialog>}
 </div>
}
