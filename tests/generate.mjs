// Checks the "Make your own" generator (still-ui/src/generate.ts) against Still's real skill library and role briefs.
// Run: node tests/generate.mjs (Node 22.6+ strips the TypeScript types). Exits 1 on any failure.
// node tests/generate.mjs --make "<goal>" "<role>" prints what the generator makes, as JSON (personalize_live.py uses it).
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { generate, judgment, pickSkills } from "../still-ui/src/generate.ts"

const roles = join(import.meta.dirname, "..", "still", "Assets", "roles")
const library = [], briefs = {}
for (const role of readdirSync(roles, { withFileTypes: true }).filter(d => d.isDirectory()).map(d => d.name)) {
 briefs[role] = readFileSync(join(roles, role + ".md"), "utf8")
 for (const f of readdirSync(join(roles, role, "skills"))) {
  const text = readFileSync(join(roles, role, "skills", f), "utf8").replace(/\r\n/g, "\n")
  const head = Object.fromEntries(/^---\n([\s\S]*?)\n---/.exec(text)[1].split("\n").map(l => [l.slice(0, l.indexOf(":")), l.slice(l.indexOf(":") + 1).trim()]))
  library.push({ id: f.slice(0, -3), role, name: head.name, text: head.description + " " + head.when })
 }
}
if (process.argv[2] === "--make") { console.log(JSON.stringify(generate(process.argv[3], process.argv[4] ?? "", library, briefs))); process.exit(0) }
let pass = 0, fail = 0
const check = (ok, what) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + what) }
const kinOf = id => library.find(s => s.id === id)?.role

check(library.length === 24 && Object.keys(briefs).length === 6, `library has 24 skills in 6 roles (${library.length})`)
for (const r of Object.keys(briefs)) check(judgment(briefs[r]).length === 3, `${r} brief has judgment rules to borrow`)

const cases = [
 ["Find the best price for anything before I buy it, and compare the options with sources", "", "research"],
 ["Write my LinkedIn posts and the monthly newsletter in my voice", "", "marketing"],
 ["Keep my week organized: plan tomorrow, prep my meetings and tell me which emails need a reply", "", "planner"],
 ["Find new leads for my agency and draft follow-ups to prospects", "", "sales"],
 ["Test our web app after each release and write up the bugs", "", "engineer"],
 ["Figure out why people sign up but never come back, and plan experiments to fix it", "", "growth"],
]
const plans = []
for (const [goal, role, kin] of cases) {
 const g = generate(goal, role, library, briefs)
 plans.push(g)
 check(g.kin === kin, `"${goal.slice(0, 40)}..." is closest to ${kin} (got ${g.kin})`)
 check(g.skills.length >= 3 && g.skills.length <= 4, `  picks 3 or 4 skills (${g.skills.join(", ")})`)
 check(g.skills.every(id => library.some(s => s.id === id)), "  every pick is from the library")
 check(g.skills.filter(id => kinOf(id) === kin).length >= 2, "  most picks fit the job")
 check(g.job.startsWith(goal) && g.job.includes("How you work:") && g.job.length <= 1000, "  instructions start from the user's words, with rules, under 1000")
 check(g.job.includes("Ask me before you send, post, buy or delete anything."), "  instructions keep the ask-first rule")
}
// Two different goals make different starting setups (the brief's "different work plans").
check(new Set(plans.map(p => p.skills.join())).size === plans.length, "each goal gets a different set of skills")
check(new Set(plans.map(p => p.job)).size === plans.length, "each goal gets different instructions")
// A role word alone steers the pick.
check(pickSkills("Researcher", library).role === "research", "a Role of Researcher alone points to research")
// Nothing to go on: still 3 skills, never an empty set.
const none = generate("", "", library, briefs)
check(none.skills.length === 3 && none.job.startsWith("How you work:"), "an empty goal still gets 3 skills and rules")
// A very long goal stays under the cap and keeps the ask-first rule.
const long = generate("Research ".repeat(120), "", library, briefs)
check(long.job.length <= 1000 && long.job.includes("Ask me before"), "a long goal stays under 1000 and keeps the ask-first rule")
console.log(`${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
