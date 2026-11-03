// "Make your own": turns what the user wants a companion for into starting instructions and 3 or 4 skills from Still's
// library (the role kits in still/Assets/roles), for the user to review before hiring. Plain keyword matching, no AI:
// the result shows up in the editor and the user can change any of it.

/// A library skill: its id, the role kit it comes from, and the words that describe it (name, description, when).
export type LibrarySkill = { id: string; role: string; name: string; text: string }

// Words that point to a role's kind of work, beyond what its skills say about themselves (matched as word starts).
const ROLE_WORDS: Record<string, string[]> = {
 sales: ["sale", "sell", "lead", "prospect", "deal", "pipeline", "customer", "client", "outreach", "crm", "call", "quota", "account"],
 growth: ["growth", "grow", "signup", "sign-up", "funnel", "conversion", "convert", "activation", "churn", "retention", "experiment", "metric", "onboarding", "trial"],
 marketing: ["marketing", "market", "post", "social", "newsletter", "content", "launch", "brand", "copy", "linkedin", "twitter", "audience", "blog", "write", "writing"],
 planner: ["plan", "calendar", "meeting", "schedule", "inbox", "email", "week", "day", "task", "project", "todo", "priorit", "deadline", "organize", "admin"],
 engineer: ["code", "coding", "bug", "api", "test", "site", "website", "app", "developer", "spec", "release", "docs", "engineer", "product", "feature"],
 research: ["research", "source", "compare", "competitor", "fact", "claim", "study", "find", "answer", "learn", "investigat", "analy", "price", "option", "vendor"],
}
const STOP = new Set(["the", "and", "for", "with", "you", "your", "that", "this", "from", "what", "when", "who", "how", "help", "helps", "into", "them", "they", "their", "out", "about", "all", "any", "can", "get", "make", "need", "want", "like", "just", "every", "each", "one", "some", "more", "also", "me", "my", "our", "its", "it's", "are", "will", "should", "would", "keep", "things", "thing"])
const stem = (w: string) => w.replace(/(ing|ed|es|s)$/, "")
const words = (text: string) => (text.toLowerCase().match(/[a-z][a-z'-]+/g) ?? []).filter(w => w.length > 2 && !STOP.has(w)).map(stem)
const hits = (asked: string[], vocab: string[]) => asked.filter(w => vocab.some(v => v.startsWith(w) || w.startsWith(v))).length

/// The skills that fit what the user asked for, best first: 3 or 4, topped up from the closest role's kit when few match.
export function pickSkills(goal: string, library: LibrarySkill[], max = 4): { role: string; skills: string[] } {
 const asked = words(goal)
 const roles = [...new Set(library.map(s => s.role))]
 const own = library.map(s => hits(asked, words(s.name + " " + s.text)))
 const roleScore = Object.fromEntries(roles.map(r => [r, 2 * hits(asked, (ROLE_WORDS[r] ?? []).map(stem)) + library.reduce((n, s, i) => n + (s.role === r ? own[i] : 0), 0)]))
 const scored = library.map((s, i) => ({ s, score: 3 * own[i] + roleScore[s.role] }))
 const role = roles.reduce((best, r) => roleScore[r] > roleScore[best] ? r : best, roles.includes("research") ? "research" : roles[0])
 const picked = scored.filter(x => x.score > 0).sort((a, b) => b.score - a.score || a.s.id.localeCompare(b.s.id)).slice(0, max).map(x => x.s.id)
 for (const s of library) if (picked.length < 3 && s.role === role && !picked.includes(s.id)) picked.push(s.id)
 return { role, skills: picked }
}

/// The first few bullets under a role brief's "How you judge the work": Still's own rules for that kind of work.
export function judgment(brief: string, count = 3): string[] {
 const section = /## How you judge the work\n([\s\S]*?)(\n## |$)/.exec(brief.replace(/\r\n/g, "\n"))?.[1] ?? ""
 return section.split("\n").filter(l => l.startsWith("- ")).slice(0, count).map(l => l.slice(2).trim())
}

/// Starting instructions and skills for a companion the user is making, from what they want it for.
export function generate(goal: string, role: string, library: LibrarySkill[], briefs: Record<string, string>, cap = 1000): { job: string; skills: string[]; kin: string } {
 const said = goal.trim().replace(/\s+/g, " ").slice(0, 600).trim() // leaves room for the rules under the cap
 const { role: kin, skills } = pickSkills(said + " " + role, library)
 const rules = [...judgment(briefs[kin] ?? ""), "Ask me before you send, post, buy or delete anything."]
 let job = ""
 for (let n = rules.length; n >= 1; n--) {
  job = (said ? (/[.!?]$/.test(said) ? said : said + ".") + "\n\n" : "") + "How you work:\n" + [...rules.slice(0, n - 1), rules[rules.length - 1]].map(r => "- " + r).join("\n")
  if (job.length <= cap) break
 }
 return { job: job.slice(0, cap), skills, kin }
}
