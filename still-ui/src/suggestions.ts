export type SuggestionVisit = { title: string; url: string; at?: string }
export type SiteSuggestion = { title: string; url: string; host: string; visits: number; bookmark: boolean; score: number }

// Only local history and bookmarks are used. Never fetch icons or send keystrokes.
export function rankSuggestions(query: string, history: SuggestionVisit[], bookmarks: SuggestionVisit[], privateTab = false, now = Date.now()): SiteSuggestion[] {
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
    return { ...site, score: match + Math.log2(1 + site.visits) * 30 + (site.bookmark ? 45 : 0) + Math.max(0, 30 - ageDays) }
  }).sort((a, b) => b.score - a.score || a.url.localeCompare(b.url)).slice(0, 6)
}
