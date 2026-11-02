// Next steps the AI offers at the end of a reply: the last lines, each ">> " and plain text. They show as chips, never as
// raw ">>" lines. Models don't always follow the format, so a step may come quoted, bulleted, numbered, indented, in
// bold or italics, or as "»" or "&gt;&gt;". Only the trailing run counts, never one inside a code fence or mid-message.

const MAX_STEPS = 3, MAX_LENGTH = 80
const MARK = /^(?:>>|»|&gt;&gt;|\\>\\?>)\s*/
const LIST = /^(?:[-*+•]|\d{1,2}[.)])\s+/
const QUOTE = /^>\s*(?=>>|»|&gt;&gt;|[-*+•]\s|\d{1,2}[.)]\s|[*_])/
const WRAP = /^(\*\*|__|\*|_)(.+)\1$/
const FENCE = /^\s*(```|~~~)/
// A label models put before the steps ("**Next steps**", "Next steps:"): it goes with them.
const LABEL = /^(?:\*\*|__)?\s*(?:next steps?|what's next|you could|try next|options|suggestions?)\s*:?\s*(?:\*\*|__)?\s*:?$/i

/** The step a line offers ("" when it isn't one), whatever wraps it. */
export function stepOf(line: string): string {
  let s = line.trim(), before = ""
  while (s !== before) { // peel quote, list and emphasis wrappers in any order
    before = s
    s = s.replace(QUOTE, "").replace(LIST, "").trim()
    const wrapped = WRAP.exec(s)
    if (wrapped) s = wrapped[2].trim()
  }
  if (!MARK.test(s)) return ""
  s = s.replace(MARK, "").trim()
  for (let w = WRAP.exec(s); w; w = WRAP.exec(s)) s = w[2].trim() // ">> **Compare them**"
  return s.replace(/\*\*|__/g, "").replace(/\s+/g, " ").trim()
}

/** Splits a reply into its body and its next steps (at most 3). A step past the limits stays in the body as plain text. */
export function nextSteps(text: string): { body: string; next: string[] } {
  const lines = text.split(/\r?\n/)
  // Lines inside a code fence never count; an unclosed fence runs to the end.
  const fenced: boolean[] = []
  let open = false
  for (const line of lines) {
    if (FENCE.test(line)) { fenced.push(true); open = !open; continue }
    fenced.push(open)
  }
  let i = lines.length - 1
  while (i >= 0 && !lines[i].trim()) i--
  let start = i + 1
  for (; i >= 0; i--) {
    if (!lines[i].trim()) continue // a blank line between steps
    if (fenced[i] || !stepOf(lines[i])) break
    start = i
  }
  const run = lines.slice(start).filter(l => l.trim())
  if (!run.length) return { body: text.trim(), next: [] }
  let end = start
  while (end > 0 && !lines[end - 1].trim()) end--
  if (end > 0 && !fenced[end - 1] && LABEL.test(lines[end - 1].trim())) end-- // "**Next steps**" goes with them
  const next: string[] = [], plain: string[] = []
  for (const line of run) {
    const step = stepOf(line)
    if (next.some(n => n.toLowerCase() === step.toLowerCase())) continue
    if (next.length < MAX_STEPS && step.length <= MAX_LENGTH) next.push(step)
    else plain.push(step) // shown as text, never with its ">>"
  }
  const body = [...lines.slice(0, end), ...(plain.length ? ["", ...plain] : [])].join("\n").trim()
  return { body, next }
}
