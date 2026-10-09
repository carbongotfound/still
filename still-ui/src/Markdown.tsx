import type { ReactNode } from "react"

// A small Markdown renderer for AI replies: headings, lists, quotes, code, tables, links, bold/italic/strike.
// React escapes all text, so a reply can't inject HTML. Links open in a new Still tab.
type Link = (url: string) => void

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(~~[^~]+~~)|(\*[^*\s][^*]*\*|(?<![\w])_[^_\s][^_]*_(?![\w]))|(\[[^\]]+\]\((?:https?:\/\/|mailto:)[^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/g

function inline(text: string, onLink: Link, key = ""): ReactNode[] {
 const out: ReactNode[] = []
 let last = 0, i = 0
 for (const m of text.matchAll(INLINE)) {
  if (m.index > last) out.push(text.slice(last, m.index))
  const t = m[0], k = key + "." + i++
  if (m[1]) out.push(<code key={k}>{t.slice(1, -1)}</code>)
  else if (m[2]) out.push(<strong key={k}>{inline(t.slice(2, -2), onLink, k)}</strong>)
  else if (m[3]) out.push(<del key={k}>{inline(t.slice(2, -2), onLink, k)}</del>)
  else if (m[4]) out.push(<em key={k}>{inline(t.slice(1, -1), onLink, k)}</em>)
  else {
   const [label, url] = m[5] ? [t.slice(1, t.indexOf("](")), t.slice(t.indexOf("](") + 2, -1)] : [t, t]
   out.push(<a key={k} href={url} title={url} onClick={e => { e.preventDefault(); onLink(url) }}>{m[5] ? inline(label, onLink, k) : label}</a>)
  }
  last = m.index + t.length
 }
 if (last < text.length) out.push(text.slice(last))
 return out
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim())

export function Markdown({ text, onLink }: { text: string; onLink: Link }) {
 const lines = text.replace(/\r/g, "").split("\n"), blocks: ReactNode[] = []
 for (let i = 0; i < lines.length;) {
  const line = lines[i], k = "b" + i
  if (!line.trim()) { i++; continue }
  if (/^\s*```/.test(line)) {
   const code: string[] = []; i++
   while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++])
   i++; blocks.push(<pre key={k}><code>{code.join("\n")}</code></pre>); continue
  }
  const h = /^(#{1,6})\s+(.*)$/.exec(line)
  if (h) { const Tag = (["h3", "h3", "h4", "h5", "h5", "h5"] as const)[h[1].length - 1]; blocks.push(<Tag key={k}>{inline(h[2], onLink, k)}</Tag>); i++; continue }
  if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { blocks.push(<hr key={k} />); i++; continue }
  if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
   const head = cells(line), rows: string[][] = []; i += 2
   while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]))
   blocks.push(<div key={k} className="md-table"><table><thead><tr>{head.map((c, j) => <th key={j}>{inline(c, onLink, k + j)}</th>)}</tr></thead>
    <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j}>{inline(c, onLink, k + ri + j)}</td>)}</tr>)}</tbody></table></div>)
   continue
  }
  if (/^\s*>/.test(line)) {
   const quote: string[] = []
   while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""))
   blocks.push(<blockquote key={k}><Markdown text={quote.join("\n")} onLink={onLink} /></blockquote>); continue
  }
  const item = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/
  if (item.test(line)) {
   const ordered = /\d/.test(item.exec(line)![2]), items: { depth: number; text: string }[] = []
   while (i < lines.length && (item.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
    const m = item.exec(lines[i])
    if (m) items.push({ depth: Math.min(3, Math.floor(m[1].length / 2)), text: m[3] }); else items[items.length - 1].text += " " + lines[i].trim()
    i++
   }
   const List = ordered ? "ol" : "ul"
   blocks.push(<List key={k}>{items.map((it, j) => <li key={j} style={it.depth ? { marginLeft: it.depth * 16 } : undefined}>{inline(it.text, onLink, k + j)}</li>)}</List>)
   continue
  }
  const para: string[] = []
  while (i < lines.length && lines[i].trim() && !/^\s*(```|#{1,6}\s|>|([-*+]|\d+[.)])\s|\|)/.test(lines[i])) para.push(lines[i++])
  if (!para.length) para.push(lines[i++])
  blocks.push(<p key={k}>{para.flatMap((p, j) => j ? [<br key={"br" + j} />, ...inline(p, onLink, k + j)] : inline(p, onLink, k + j))}</p>)
 }
 return <div className="md">{blocks}</div>
}
