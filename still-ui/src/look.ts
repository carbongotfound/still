// A companion's look: a soft blob with its own color, silhouette, one job prop and a small accessory. Saved per
// companion as JSON (Companion.look) and drawn by companion3d.ts. Every id below is what's saved; validate against these.
export type Look = {
 color: string // body color, hex
 shape: string // silhouette: SHAPES
 prop: string // what it holds or wears for its job: PROPS ("" for none)
 accessory: string // a small extra: ACCESSORIES ("" for none)
}

export const SHAPES: [string, string][] = [
 ["bean", "Bean"], ["tall", "Tall"], ["gumdrop", "Gumdrop"], ["block", "Block"], ["round", "Round"], ["squat", "Squat"], ["bump", "Bump"], ["lean", "Lean"],
]
export const PROPS: [string, string][] = [
 ["", "None"], ["chart", "Chart"], ["badge", "Badge"], ["clipboard", "Clipboard"], ["megaphone", "Megaphone"], ["headset", "Headset"],
 ["laptop", "Laptop"], ["magnifier", "Magnifier"], ["pencil", "Pencil"], ["envelope", "Envelope"],
]
export const ACCESSORIES: [string, string][] = [["", "None"], ["glasses", "Glasses"], ["bow", "Bow"], ["sprout", "Sprout"], ["flower", "Flower"]]
export const BODY_COLORS: [string, string][] = [
 ["#f7a26a", "Tangerine"], ["#f39079", "Coral"], ["#f2a5c4", "Peony"], ["#f6c3b0", "Peach"], ["#f6d56a", "Lemon"], ["#f3e2a6", "Butter"],
 ["#a6cf9c", "Leaf"], ["#93d6bd", "Mint"], ["#86d0c8", "Sea glass"], ["#8cc3ee", "Sky"], ["#a7b5f0", "Periwinkle"], ["#c0a3ec", "Lilac"],
 ["#d9b2e6", "Orchid"], ["#ddd4c6", "Oat"], ["#cfc9c0", "Pebble"], ["#9aa3b2", "Slate"],
]

// The seven roles' own looks, keyed by role id (crew.tsx).
export const ROLE_LOOKS: Record<string, Look> = {
 closer: { color: "#f7a26a", shape: "tall", prop: "chart", accessory: "" },
 scout: { color: "#f2a5c4", shape: "gumdrop", prop: "badge", accessory: "" },
 chief: { color: "#a6cf9c", shape: "block", prop: "clipboard", accessory: "" },
 marketer: { color: "#f6d56a", shape: "round", prop: "megaphone", accessory: "" },
 fixer: { color: "#86d0c8", shape: "squat", prop: "headset", accessory: "" },
 builder: { color: "#8cc3ee", shape: "bump", prop: "laptop", accessory: "" },
 researcher: { color: "#c0a3ec", shape: "lean", prop: "magnifier", accessory: "" },
}
/// Make your own: the neutral blob you start from.
export const BLANK: Look = { color: "#ddd4c6", shape: "bean", prop: "", accessory: "" }
/// A friendly companion for places that don't have one yet.
export const DEFAULT_LOOK: Look = { color: "#8cc3ee", shape: "bean", prop: "", accessory: "" }
// Other AI apps working in Still wear these.
export const AGENT_LOOKS: Record<string, Look> = {
 claude: { color: "#f39079", shape: "bean", prop: "", accessory: "" },
 chatgpt: { color: "#93d6bd", shape: "round", prop: "", accessory: "" },
 grok: { color: "#9aa3b2", shape: "block", prop: "", accessory: "" },
}

const pick = <T,>(list: T[]) => list[Math.floor(Math.random() * list.length)]
export const surprise = (): Look => ({
 color: pick(BODY_COLORS)[0], shape: pick(SHAPES)[0], prop: pick(PROPS.slice(1))[0], accessory: Math.random() < .4 ? pick(ACCESSORIES.slice(1))[0] : "",
})

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
 const nearest = Object.values(ROLE_LOOKS).reduce((a, b) => far(a.color, color) <= far(b.color, color) ? a : b)
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
 return { color: hex(o.color, fallback.color), shape: known(SHAPES, o.shape, fallback.shape), prop: known(PROPS, o.prop, fallback.prop), accessory: known(ACCESSORIES, o.accessory, fallback.accessory) }
}
/// Saved before the blobs (it has a face of its own, or no prop field at all).
export const isOld = (o: Record<string, unknown>) => "eyes" in o || "body" in o || !("prop" in o) && "shape" in o
export const lookKey = (l: Look) => JSON.stringify({ color: l.color, shape: l.shape, prop: l.prop, accessory: l.accessory })
