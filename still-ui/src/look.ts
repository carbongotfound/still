// A companion's look: a soft blob with its own color, silhouette, one real thing it holds or wears and a small accessory. Saved per
// companion as JSON (Companion.look) and drawn by companion3d.ts. Every id below is what's saved; validate against these.
export type Look = {
 color: string // body color, hex
 shape: string // silhouette: SHAPES
 prop: string // what it holds or wears: PROPS ("" for none; the six roles have none)
 accessory: string // a small extra: ACCESSORIES ("" for none)
 // Look v2 (below): all of these, or none of them (a v1 look, drawn as before)
 v?: 2
 form?: string // the sculpted body: FORMS
 second?: string // the accent, hex: the feet and anything on top (the body's own color: no accent)
 eye?: string // EYE_SHAPES
 mouth?: string // MOUTHS, at rest
 top?: string // one top feature: TOPS
 finish?: string // FINISHES
}

export const SHAPES: [string, string][] = [
 ["bean", "Bean"], ["tall", "Tall"], ["gumdrop", "Gumdrop"], ["block", "Block"], ["round", "Round"], ["squat", "Squat"], ["bump", "Bump"], ["lean", "Lean"],
]
// Silhouettes only a role wears (not offered in the shape picker): Assistant Ruth's crest, wide on top.
const ROLE_SHAPES: [string, string][] = [["crest", "Crest"]]
// Real things, modeled in Blender (rig/props.py): each picker tile shows the thing itself (assets/prop).
export const PROPS: [string, string][] = [
 ["", "None"], ["laptop", "Laptop"], ["mug", "Coffee mug"], ["headphones", "Headphones"], ["notebook", "Notebook"], ["phone", "Phone"],
 ["magnifier", "Magnifying glass"], ["wrench", "Wrench"], ["paintbrush", "Paintbrush"], ["camera", "Camera"], ["briefcase", "Briefcase"],
]
// The props before these, and what each became (the rest are dropped): a saved look keeps the nearest.
const RENAMED: Record<string, string> = { headset: "headphones", clipboard: "notebook", pencil: "paintbrush" }
/// What each role held before the roles went prop-free: a role's companion saved with it wears the role's own look.
/// How each prop is held: in both hands, one, or worn.
export const HOLD: Record<string, "both" | "hand" | "worn"> = { laptop: "both", notebook: "both", camera: "both", mug: "hand", phone: "hand", magnifier: "hand", wrench: "hand", paintbrush: "hand", briefcase: "hand", headphones: "worn" }
export const ROLE_PROPS: Record<string, string> = { sales: "chart", growth: "badge", planner: "clipboard", marketing: "megaphone", engineer: "laptop", research: "magnifier" }
export const ACCESSORIES: [string, string][] = [["", "None"], ["glasses", "Glasses"], ["bow", "Bow"], ["sprout", "Sprout"], ["flower", "Flower"]]
export const BODY_COLORS: [string, string][] = [
 ["#f7a26a", "Tangerine"], ["#f39079", "Coral"], ["#f2a5c4", "Peony"], ["#f6c3b0", "Peach"], ["#f6d56a", "Lemon"], ["#f3e2a6", "Butter"],
 ["#a6cf9c", "Leaf"], ["#93d6bd", "Mint"], ["#86d0c8", "Sea glass"], ["#8cc3ee", "Sky"], ["#a7b5f0", "Periwinkle"], ["#c0a3ec", "Lilac"],
 ["#d9b2e6", "Orchid"], ["#ddd4c6", "Oat"], ["#cfc9c0", "Pebble"], ["#9aa3b2", "Slate"],
]
/// Look v2's solid colors (Colors: the body and the accent each pick from these, or any color): the body
/// colors, then deeper ones. BODY_COLORS stays as it is: plugins take their colors from it by name.
export const SOLIDS: [string, string][] = [...BODY_COLORS,
 ["#e5574f", "Poppy"], ["#d46a9c", "Berry"], ["#a47b5b", "Cocoa"], ["#5fae6e", "Fern"], ["#4f86c6", "Cobalt"], ["#8b6fd6", "Violet"], ["#f4f2ee", "Snow"], ["#4a5263", "Charcoal"],
]

// The six roles' own looks, keyed by role id (crew.tsx): no props, their bodies say what they do.
export const ROLE_LOOKS: Record<string, Look> = {
 sales: { color: "#f7a26a", shape: "tall", prop: "", accessory: "" },
 growth: { color: "#f2a5c4", shape: "gumdrop", prop: "", accessory: "" },
 planner: { color: "#a6cf9c", shape: "block", prop: "", accessory: "" },
 marketing: { color: "#f6d56a", shape: "round", prop: "", accessory: "" },
 engineer: { color: "#8cc3ee", shape: "bump", prop: "", accessory: "" },
 research: { color: "#c0a3ec", shape: "lean", prop: "", accessory: "" },
 assistant: { color: "#2fa496", shape: "crest", prop: "", accessory: "" }, // a deep jade: apart from the six at chat sizes, and not in the picker
}
/// Make your own: the neutral blob you start from.
export const BLANK: Look = { color: "#ddd4c6", shape: "bean", prop: "", accessory: "" }
/// The Blender companions: each one's model, avatar and sprites go by this name.
export const RIGS: [Look, string][] = [[ROLE_LOOKS.sales, "jonah"], [ROLE_LOOKS.growth, "talia"], [ROLE_LOOKS.planner, "nora"], [ROLE_LOOKS.marketing, "leo"],
 [ROLE_LOOKS.engineer, "ivan"], [ROLE_LOOKS.research, "maya"], [ROLE_LOOKS.assistant, "ruth"], [BLANK, "custom"]]
/// A friendly companion for places that don't have one yet.
export const DEFAULT_LOOK: Look = { color: "#8cc3ee", shape: "bean", prop: "", accessory: "" }
// Other AI apps working in Still wear these.
export const AGENT_LOOKS: Record<string, Look> = {
 claude: { color: "#f39079", shape: "bean", prop: "", accessory: "" },
 chatgpt: { color: "#93d6bd", shape: "round", prop: "", accessory: "" },
 grok: { color: "#9aa3b2", shape: "block", prop: "", accessory: "" },
}

const known = (list: [string, string][], v: unknown, fallback: string) => list.some(([k]) => k === v) ? v as string : fallback
const hex = (v: unknown, fallback: string) => typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v) ? v.toLowerCase() : fallback
const rgb = (h: string) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))
const far = (a: string, b: string) => rgb(a).reduce((s, v, i) => s + (v - rgb(b)[i]) ** 2, 0)
// Looks from before the blobs: the head shapes they had, and what they wore that a blob can wear too.
const OLD_SHAPES: Record<string, string> = { round: "round", mochi: "squat", bean: "bean", kitty: "bump", fox: "gumdrop", pebble: "block", droopy: "lean", drop: "gumdrop" }
/// A look saved before the blobs, on the nearest blob: same color, the nearest silhouette (an official companion's own
/// body becomes the shape of the role whose color is closest), and glasses, a bow, a flower or a sprout kept.
function fromOld(o: Record<string, unknown>, f: Look): Look {
 const color = hex(o.color, f.color)
 const nearest = Object.values(ROLE_LOOKS).filter(l => l.shape !== "crest").reduce((a, b) => far(a.color, color) <= far(b.color, color) ? a : b)
 const shape = typeof o.body === "string" && o.body ? nearest.shape : OLD_SHAPES[o.shape as string] ?? f.shape
 const accessory = o.glasses ? "glasses" : o.hat === "flower" || o.hat === "bow" ? o.hat : o.hair === "sprout" ? "sprout" : ""
 return { color, shape, prop: "", accessory }
}
/// A saved look, checked field by field: anything missing or unknown falls back. Older looks move onto the nearest blob.
export function parseLook(raw: unknown, fallback: Look = DEFAULT_LOOK): Look {
 let o: Record<string, unknown> = {}
 try { o = typeof raw === "string" ? (raw ? JSON.parse(raw) : {}) : (raw as Record<string, unknown>) ?? {} } catch { return fallback }
 if (!o || typeof o !== "object") return fallback
 if (isOld(o)) return fromOld(o, fallback)
 if (o.v === 2) { // a v2 look: each part checked, the v1 fields made to match. A marking (2.10 before Stage 17) is dropped.
  const form = known(FORMS, o.form, Object.entries(FORM_SHAPE).find(([, s]) => s === o.shape)?.[0] ?? "bean"), color = hex(o.color, BLANK_V2.color)
  return v2({ form, color, second: hex(o.second, color), eye: known(EYE_SHAPES, o.eye, "round"),
   mouth: known(MOUTHS, o.mouth, "smile"), top: known(TOPS, o.top, "none"), finish: known(FINISHES, o.finish, "matte"), accessory: known(EXTRAS, o.accessory, ""), prop: known(PROPS, RENAMED[o.prop as string] ?? o.prop, "") })
 }
 return { color: hex(o.color, fallback.color), shape: known([...SHAPES, ...ROLE_SHAPES], o.shape, fallback.shape), prop: known(PROPS, RENAMED[o.prop as string] ?? o.prop, fallback.prop), accessory: known(ACCESSORIES, o.accessory, fallback.accessory) }
}
/// Saved before the blobs (it has a face of its own, or no prop field at all).
export const isOld = (o: Record<string, unknown>) => "eyes" in o || "body" in o || !("prop" in o) && "shape" in o
/// The saved string. A v1 look's is as it always was; a v2 look's leads with its v1 fields (an older Still reads those).
export const lookKey = (l: Look) => JSON.stringify(l.v === 2 ? { v: 2, color: l.color, shape: l.shape, prop: l.prop, accessory: l.accessory, form: l.form, second: l.second, eye: l.eye, mouth: l.mouth, top: l.top, finish: l.finish }
 : { color: l.color, shape: l.shape, prop: l.prop, accessory: l.accessory })

// ---------------------------------------------------------------- Look v2 (Stage 12): Make your own's new style
// A sculpted foundation on the shared rig, colored by zone (main, a light tint of it on the hands, an optional accent on the
// feet), a face (the lids' and mouth's rest, eye size), one top feature, a small accessory and a finish.
// The v1 fields stay valid (the color, the nearest v1 shape, no prop unless kept), so an older Still shows a close blob.
export const FORMS: [string, string][] = [["pebble", "Pebble"], ["column", "Column"], ["block", "Block"], ["gumdrop", "Gumdrop"], ["bean", "Leaning bean"]]
export const EYE_SHAPES: [string, string][] = [["round", "Round"], ["sleepy", "Sleepy"], ["wide", "Wide"], ["narrow", "Narrow"]]
export const MOUTHS: [string, string][] = [["smile", "Smile"], ["grin", "Grin"], ["hmm", "Hmm"], ["o", "O"]]
export const TOPS: [string, string][] = [["none", "None"], ["antennae", "Antennae"], ["tuft", "Tuft"], ["cap", "Cap"], ["sprout", "Sprout"]]
// Glasses aren't offered: at 18px they cover the eyes. A bow and a flower read at that size and sit clear of them.
export const EXTRAS: [string, string][] = [["", "None"], ["bow", "Bow"], ["flower", "Flower"]]
export const FINISHES: [string, string][] = [["matte", "Matte"], ["gloss", "Soft gloss"]]
/// The v1 shape each foundation shows as in a Still from before v2.
export const FORM_SHAPE: Record<string, string> = { pebble: "round", column: "tall", block: "block", gumdrop: "gumdrop", bean: "lean" }
/// Curated color pairs, main then second, each checked for contrast (tests/ui/look.test.ts).
export const PAIRS: [string, string, string][] = [
 ["#f7a26a", "#fff0dc", "Tangerine and cream"], ["#f39079", "#7a4a88", "Coral and plum"], ["#f2a5c4", "#b3416e", "Peony and berry"],
 ["#f6d56a", "#e9893a", "Lemon and orange"], ["#f3e2a6", "#7f9a4e", "Butter and moss"], ["#a6cf9c", "#4f8a4a", "Leaf and forest"],
 ["#93d6bd", "#2f8f86", "Mint and teal"], ["#86d0c8", "#ef7f6b", "Sea glass and coral"], ["#8cc3ee", "#3a5a9c", "Sky and navy"],
 ["#a7b5f0", "#f6d56a", "Periwinkle and lemon"], ["#c0a3ec", "#6d4fc4", "Lilac and violet"], ["#d9b2e6", "#93d6bd", "Orchid and mint"],
 ["#ddd4c6", "#8a6a50", "Oat and cocoa"], ["#9aa3b2", "#f4f2ee", "Slate and snow"],
 // the team's own, for Start from a team look
 ["#ff8a4c", "#b8481c", "Tangerine and rust"], ["#f7a1c4", "#c4466f", "Peony and rose"], ["#9fe39a", "#3f8a45", "Leaf and fern"],
 ["#ffd84d", "#d98a1c", "Lemon and honey"], ["#7cc4ff", "#3f7fc6", "Sky and blue"], ["#b79cff", "#7b5cf0", "Lilac and indigo"],
]
export type Locks = { body?: boolean; colors?: boolean; face?: boolean; feature?: boolean }
type V2 = Required<Pick<Look, "form" | "second" | "eye" | "mouth" | "top" | "finish">>
/// A v2 look from its parts: the v1 fields follow (the main color, the nearest v1 shape, the accessory).
export const v2 = (o: V2 & { color: string; accessory?: string; prop?: string }): Look =>
 ({ v: 2, color: o.color, shape: FORM_SHAPE[o.form] ?? "bean", prop: o.prop ?? "", accessory: o.accessory ?? "", form: o.form, second: o.second, eye: o.eye, mouth: o.mouth, top: o.top, finish: o.finish })
/// An accent on the feet and top: a second color that isn't the body's own.
export const hasAccent = (l: Look) => !!l.second && l.second !== l.color
export const isV2 = (l: Look) => l.v === 2
/// Where a new look starts: ten made to be told apart at 24px.
export const STARTS: [string, Look][] = ([
 ["Lemon pebble", { form: "pebble", color: "#f6d56a", eye: "round", mouth: "smile", top: "sprout", finish: "matte" }],
 ["Sky column", { form: "column", color: "#8cc3ee", second: "#3a5a9c", eye: "wide", mouth: "o", top: "antennae", finish: "matte" }],
 ["Leaf block", { form: "block", color: "#a6cf9c", eye: "sleepy", mouth: "smile", top: "none", finish: "matte" }],
 ["Peony gumdrop", { form: "gumdrop", color: "#f2a5c4", eye: "round", mouth: "grin", top: "none", finish: "matte", accessory: "bow" }],
 ["Oat bean", { form: "bean", color: "#ddd4c6", second: "#8a6a50", eye: "narrow", mouth: "hmm", top: "cap", finish: "matte" }],
 ["Coral pebble", { form: "pebble", color: "#f39079", eye: "wide", mouth: "grin", top: "tuft", finish: "matte" }],
 ["Lilac column", { form: "column", color: "#c0a3ec", eye: "sleepy", mouth: "smile", top: "none", finish: "matte", accessory: "flower" }],
 ["Mint gumdrop", { form: "gumdrop", color: "#93d6bd", second: "#2f8f86", eye: "round", mouth: "o", top: "antennae", finish: "gloss" }],
 ["Slate block", { form: "block", color: "#9aa3b2", second: "#f4f2ee", eye: "narrow", mouth: "smile", top: "cap", finish: "gloss" }],
 ["Periwinkle bean", { form: "bean", color: "#a7b5f0", eye: "wide", mouth: "smile", top: "sprout", finish: "matte" }],
] as [string, Omit<V2, "second"> & { color: string; second?: string; accessory?: string }][]).map(([name, o]) => [name, v2({ ...o, second: o.second ?? o.color })])
/// The six roles' looks as v2 choices (Start from a team look): their colors, faces and features on the nearest foundation.
export const TEAM_LOOKS: [string, Look][] = ([
 ["sales", { form: "column", color: "#ff8a4c", second: "#b8481c", eye: "narrow", mouth: "grin", top: "none", finish: "matte" }],
 ["growth", { form: "gumdrop", color: "#f7a1c4", second: "#c4466f", eye: "wide", mouth: "o", top: "tuft", finish: "matte" }],
 ["planner", { form: "block", color: "#9fe39a", second: "#3f8a45", eye: "round", mouth: "smile", top: "none", finish: "matte" }],
 ["marketing", { form: "pebble", color: "#ffd84d", second: "#d98a1c", eye: "wide", mouth: "grin", top: "antennae", finish: "matte" }],
 ["engineer", { form: "bean", color: "#7cc4ff", second: "#3f7fc6", eye: "narrow", mouth: "hmm", top: "cap", finish: "matte" }],
 ["research", { form: "column", color: "#b79cff", second: "#7b5cf0", eye: "narrow", mouth: "hmm", top: "none", finish: "matte" }],
] as [string, V2 & { color: string }][]).map(([role, o]) => [role, v2(o)])
/// Make your own's new start: the first curated look.
export const BLANK_V2 = STARTS[0][1]
// Faces that go together: the lids' rest with a mouth that suits it.
const FACES: [string, string][] = [["round", "smile"], ["round", "grin"], ["round", "o"], ["sleepy", "smile"], ["wide", "o"], ["wide", "grin"], ["wide", "smile"], ["narrow", "hmm"], ["narrow", "smile"]]

// Contrast: WCAG relative luminance, and CIEDE2000 between two colors.
const PUPIL = "#1b1420", SCLERA = "#f4f1ec"
const lin = (v: number) => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4 }
const lum = (h: string) => { const [r, g, b] = rgb(h).map(lin); return .2126 * r + .7152 * g + .0722 * b }
export const ratio = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05) }
function lab(h: string) {
 const [r, g, b] = rgb(h).map(lin), f = (t: number) => t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116
 const x = f((.4124 * r + .3576 * g + .1805 * b) / .95047), y = f(.2126 * r + .7152 * g + .0722 * b), z = f((.0193 * r + .1192 * g + .9505 * b) / 1.08883)
 return [116 * y - 16, 500 * (x - y), 200 * (y - z)]
}
export function deltaE(a: string, b: string) {
 const [L1, a1, b1] = lab(a), [L2, a2, b2] = lab(b), rad = Math.PI / 180
 const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2), Cm = (C1 + C2) / 2, G = .5 * (1 - Math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
 const p1 = a1 * (1 + G), p2 = a2 * (1 + G), c1 = Math.hypot(p1, b1), c2 = Math.hypot(p2, b2)
 const h = (x: number, y: number) => { const v = Math.atan2(y, x) / rad; return v < 0 ? v + 360 : v }
 const h1 = h(p1, b1), h2 = h(p2, b2), dL = L2 - L1, dC = c2 - c1
 let dh = c1 * c2 === 0 ? 0 : h2 - h1; if (dh > 180) dh -= 360; else if (dh < -180) dh += 360
 const dH = 2 * Math.sqrt(c1 * c2) * Math.sin(dh * rad / 2), Lm = (L1 + L2) / 2, cm = (c1 + c2) / 2
 let hm = h1 + h2; if (c1 * c2 !== 0) hm = Math.abs(h1 - h2) <= 180 ? hm / 2 : hm < 360 ? (hm + 360) / 2 : (hm - 360) / 2
 const T = 1 - .17 * Math.cos((hm - 30) * rad) + .24 * Math.cos(2 * hm * rad) + .32 * Math.cos((3 * hm + 6) * rad) - .2 * Math.cos((4 * hm - 63) * rad)
 const Sl = 1 + .015 * (Lm - 50) ** 2 / Math.sqrt(20 + (Lm - 50) ** 2), Sc = 1 + .045 * cm, Sh = 1 + .015 * cm * T
 const Rt = -2 * Math.sqrt(cm ** 7 / (cm ** 7 + 25 ** 7)) * Math.sin(60 * Math.exp(-(((hm - 275) / 25) ** 2)) * rad)
 return Math.sqrt((dL / Sl) ** 2 + (dC / Sc) ** 2 + (dH / Sh) ** 2 + Rt * (dC / Sc) * (dH / Sh))
}
/// What's wrong with a v2 look at small sizes, or [] when nothing is: an accent must stand apart from the body (or it
/// vanishes), and the eyes must read against the body: the dark pupil or the white at 3:1 or more, and lids open at least half way.
export function lookIssues(l: Look): string[] {
 if (!isV2(l)) return []
 const out: string[] = [], skin = l.color
 if (hasAccent(l) && deltaE(l.color, l.second!) < 15) out.push(`the accent ${l.second} is too close to the body ${l.color}`)
 if (Math.max(ratio(PUPIL, skin), ratio(SCLERA, skin)) < 3) out.push(`the eyes don't stand out from ${skin}`)
 if ((EYE_REST[l.eye!]?.lid ?? 0) > .5) out.push(`the ${l.eye} eyes are more than half shut`)
 return out
}
/// The face's rest (rig.ts adds blinks and talking to it): how shut the lids are, the eyes' size, the lid's "wide" shape.
export const EYE_REST: Record<string, { lid: number; scale: number; wide: number }> = {
 round: { lid: 0, scale: 1, wide: 0 }, sleepy: { lid: .42, scale: 1, wide: 0 }, wide: { lid: 0, scale: 1.1, wide: .8 }, narrow: { lid: .3, scale: .9, wide: 0 },
}
export const MOUTH_REST: Record<string, [string, number]> = { smile: ["mouth.smile", .55], grin: ["mouth.grin", .6], hmm: ["mouth.hmm", .8], o: ["mouth.o", .5] }

/// Surprise me: a compatible recipe (a foundation, a solid color or a curated pair, a face that suits, at most one top
/// feature and one accessory), keeping what's locked from base, and only one that passes lookIssues.
export function surprise(base: Look = BLANK_V2, locks: Locks = {}, random = Math.random): Look {
 const pick = <T,>(list: T[]) => list[Math.floor(random() * list.length)]
 const b = isV2(base) ? base : BLANK_V2
 for (let i = 0; i < 50; i++) {
  const solid = pick(SOLIDS)[0], [color, second] = locks.colors ? [b.color, b.second!] : random() < .5 ? [solid, solid] : pick(PAIRS)
  const [eye, mouth] = locks.face ? [b.eye!, b.mouth!] : pick(FACES)
  const feature = random() < .55, extra = random() < .3
  const l = v2({
   form: locks.body ? b.form! : pick(FORMS)[0], color, second, finish: locks.colors ? b.finish! : random() < .3 ? "gloss" : "matte",
   eye, mouth, top: locks.feature ? b.top! : feature ? pick(TOPS.slice(1))[0] : "none", accessory: locks.feature ? b.accessory : extra ? pick(EXTRAS.slice(1))[0] : "",
  })
  if (!lookIssues(l).length) return l
 }
 return b
}

// The editor's history: every change, undo and redo, back to the look it opened with (Reset), or none of it (Cancel).
/// A classic look (from before v2) as the nearest new-style one, the moment it's changed in the editor: a team member's
/// own look becomes their team look in their own color; any other keeps its color, solid, on the nearest body, a bow,
/// flower or sprout kept (glasses don't come over). Its prop only if kept.
const SHAPE_FORM: Record<string, string> = { round: "pebble", tall: "column", block: "block", gumdrop: "gumdrop", lean: "bean", bean: "bean", squat: "pebble", bump: "gumdrop", crest: "column" }
export function newStyle(l: Look, keepProp = false): Look {
 const team = TEAM_LOOKS.find(([r]) => ROLE_LOOKS[r]?.color === l.color && ROLE_LOOKS[r]?.shape === l.shape)?.[1]
 if (team) return v2({ ...team as Required<Look>, color: l.color, prop: keepProp ? l.prop : "" })
 return v2({ ...BLANK_V2 as Required<Look>, form: SHAPE_FORM[l.shape] ?? "bean", color: l.color, second: l.color, top: l.accessory === "sprout" ? "sprout" : "none",
  accessory: EXTRAS.some(([k]) => k && k === l.accessory) ? l.accessory : "", prop: keepProp ? l.prop : "" })
}
export type History = { past: Look[]; now: Look; future: Look[]; start: Look }
export const history = (start: Look): History => ({ past: [], now: start, future: [], start })
export const change = (h: History, next: Look): History => lookKey(next) === lookKey(h.now) ? h : { ...h, past: [...h.past, h.now].slice(-100), now: next, future: [] }
export const undo = (h: History): History => h.past.length ? { ...h, past: h.past.slice(0, -1), now: h.past.at(-1)!, future: [h.now, ...h.future] } : h
export const redo = (h: History): History => h.future.length ? { ...h, past: [...h.past, h.now], now: h.future[0], future: h.future.slice(1) } : h
export const reset = (h: History): History => change(h, h.start)
