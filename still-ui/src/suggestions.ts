export type SuggestionVisit = { title: string; url: string; at?: string }
export type AddressPick = { typed: string; url: string; count: number }
export type SiteSuggestion = { title: string; url: string; host: string; visits: number; bookmark: boolean; score: number }

// Only local history and bookmarks are used. Never fetch icons or send keystrokes.
// picks: what you typed before and the site you chose then. A site you keep choosing for these letters comes first.
export function rankSuggestions(query: string, history: SuggestionVisit[], bookmarks: SuggestionVisit[], privateTab = false, now = Date.now(), picks: AddressPick[] = []): SiteSuggestion[] {
  const q = query.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '')
  if (!q) return []
  const sites = new Map<string, SiteSuggestion & { last: number }>()
  for (const [items, bookmark] of [[privateTab ? [] : history, false], [bookmarks, true]] as const) {
    for (const visit of items) {
      let parsed: URL
      try { parsed = new URL(visit.url) } catch { continue }
      if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password) continue
      const host = parsed.hostname.replace(/^www\./, '')
      const url = bookmark ? parsed.href : parsed.origin + '/'
      const existing = sites.get(url)
      const date = Date.parse(visit.at ?? '')
      const last = Number.isFinite(date) ? Math.min(now, date) : 0
      sites.set(url, { url, host, title: bookmark ? visit.title : host, visits: (existing?.visits ?? 0) + (bookmark ? 0 : 1), bookmark: bookmark || !!existing?.bookmark, last: Math.max(existing?.last ?? 0, last), score: 0 })
    }
  }
  return [...sites.values()].filter(site => (site.host + ' ' + site.title + ' ' + site.url).toLowerCase().includes(q)).map(site => {
    const match = site.host === q ? 1000 : site.host.startsWith(q) ? 700 : site.host.split('.').some(part => part.startsWith(q)) ? 500 : 100
    const ageDays = (now - site.last) / 86400000
    const chosen = privateTab ? 0 : picks.filter(p => p.url === site.url && (q.startsWith(p.typed) || p.typed.startsWith(q))).reduce((n, p) => n + p.count, 0)
    return { ...site, score: match + Math.log2(1 + site.visits) * 30 + (site.bookmark ? 45 : 0) + Math.max(0, 30 - ageDays) + Math.log2(1 + chosen) * 260 }
  }).sort((a, b) => b.score - a.score || a.url.localeCompare(b.url)).slice(0, 6)
}

// The new tab's "Try one of these": up to three concrete tasks, each with why it's there. Sources, strongest first: a
// project the companion remembers, a connected app it works in, an open tab (never a private one), then its role's tasks
// that match what the user said they work on, then its role's own. No context, no cards: nothing beats filler.
export type HomeIdea = { kind: 'project' | 'app' | 'tab' | 'role'; label: string; why: string; prompt: string }
export type IdeaTab = { id: string; title: string; url: string; isPrivate?: boolean; chatId?: string | null; inChat?: string; loading?: boolean }
// One task per app Still knows well (Composio toolkit slugs). Reads only: nothing is sent or changed.
const APP_TASKS: Record<string, [string, string]> = {
  gmail: ['What needs a reply?', "Check my Gmail and list what's waiting on a reply from me, most urgent first, with a one-line draft for each. Don't send anything."],
  outlook: ['What needs a reply?', "Check my Outlook inbox and list what's waiting on a reply from me, most urgent first, with a one-line draft for each. Don't send anything."],
  googlecalendar: ['Brief my next meeting', "Look at my Google Calendar, find my next meeting and brief me: who's coming, what they do and what I should get out of it."],
  slack: ['Catch me up on Slack', "Read my Slack mentions and direct messages from the last day and list what needs me, most urgent first. Don't post anything."],
  github: ['What needs my review?', 'List the GitHub pull requests waiting on my review and the issues assigned to me, most urgent first, with one line on each.'],
  linear: ["What's on my plate?", 'List my open Linear issues by priority and due date, and flag anything blocked or overdue.'],
  jira: ["What's on my plate?", 'List my open Jira issues by priority and due date, and flag anything blocked or overdue.'],
  asana: ["What's on my plate?", 'List my open Asana tasks by due date, and flag anything overdue.'],
  notion: ['Find my open to-dos', 'Search my Notion for unchecked to-dos from the last two weeks and list them by page, oldest first.'],
  hubspot: ['Which deals need a nudge?', "Look at my open HubSpot deals, list the ones with no next step or no activity in a week, and draft a short follow-up for each. Don't send anything."],
  stripe: ['How did this week go?', "Compare this week's Stripe revenue, new customers and refunds with last week's, and name the biggest change. Don't change anything."],
  googledrive: ['What changed in my files?', 'List the Google Drive files changed in the last week, newest first, with one line on what each is.'],
}
const clip = (text: string, max: number) => (text = text.trim().replace(/[.\s]+$/, ''), text.length > max ? text.slice(0, max - 1).trimEnd() + '…' : text)
export function homeIdeas({ name, role, asks = [], fits = [], uses = [], memory = [], apps = [], tabs = [], activeId }: {
  name: string; role?: string; asks?: [string, string][]; fits?: [string, string, string][]; uses?: string[]
  memory?: { text: string; kind: string; at: string }[]; apps?: { slug: string; name: string }[]; tabs?: IdeaTab[]; activeId?: string
}): HomeIdea[] {
  const out: HomeIdea[] = []
  const add = (idea: HomeIdea) => { if (out.length < 3 && !out.some(o => o.label === idea.label)) out.push(idea) }
  const project = memory.filter(f => f.kind === 'project').sort((a, b) => b.at.localeCompare(a.at))[0]
  if (project) add({ kind: 'project', label: 'Next step: ' + clip(project.text, 40), why: `From ${name}'s memory`,
    prompt: `You remember this about my work: "${project.text}". Suggest the next concrete step, then do the parts you can. Ask me before sending or changing anything.` })
  const app = [...apps].sort((a, b) => Number(uses.includes(b.slug)) - Number(uses.includes(a.slug))).find(a => APP_TASKS[a.slug])
  if (app) add({ kind: 'app', label: APP_TASKS[app.slug][0], why: `${app.name} is connected`, prompt: APP_TASKS[app.slug][1] })
  const tab = tabs.find(t => !t.isPrivate && !t.chatId && !t.inChat && !t.loading && t.id !== activeId && /^https?:\/\//.test(t.url))
  if (tab) add({ kind: 'tab', label: 'Sum up ' + clip(tab.title || new URL(tab.url).hostname, 40), why: 'Open in your tabs',
    prompt: `Sum up my open tab "${tab.title}" (${tab.url}) in a few short bullet points.` })
  for (const [interest, label, prompt] of fits) add({ kind: 'role', label, why: `You work on ${interest.toLowerCase()}`, prompt })
  if (role) for (const [label, prompt] of asks) add({ kind: 'role', label, why: `${name}'s role: ${role}`, prompt })
  return out
}
