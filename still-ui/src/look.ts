// A companion's look: body color, head shape, face and what it wears. Saved per companion as JSON (Companion.look),
// drawn by the 3D model (companion3d.ts) and its face texture (face.ts).
export type Look = {
 color: string; shape: string; head: number; ears: number
 eyes: string; eyeGap: number; eyeY: number; eyeSize: number; pupil: number
 brows: string; browGap: number; browY: number; browSize: number; browTilt: number
 mouth: string; mouthY: number; mouthSize: number
 blush: boolean; hair: string; hairColor: string; hat: string
}
// Sliders run -1..1 with 0 in the middle, except head size (0.88..1.12).

export const BODY_COLORS: [string, string][] = [
 ["#f2ede4", "Cream"], ["#e9dfd0", "Oat"], ["#f6d7c3", "Peach"], ["#f4c2a8", "Apricot"], ["#f0a989", "Coral"], ["#e5876a", "Terracotta"],
 ["#f3b7c1", "Blush"], ["#eea0b4", "Rose"], ["#e58fa8", "Berry pink"], ["#d77a8f", "Raspberry"], ["#f7d58b", "Butter"], ["#f2c66b", "Honey"],
 ["#e9b04f", "Mustard"], ["#f6e3a1", "Lemon"], ["#d9e7a6", "Pear"], ["#bcd98f", "Lime"], ["#a6cf98", "Leaf"], ["#8fbf8a", "Sage"],
 ["#7fb39b", "Jade"], ["#9ed8c6", "Mint"], ["#83cbc4", "Sea glass"], ["#6fb9c0", "Teal"], ["#9fd3ea", "Sky"], ["#8fb8e8", "Cornflower"],
 ["#7aa3dc", "Denim"], ["#6c8fd0", "Blue"], ["#b8c4f0", "Periwinkle"], ["#a99be0", "Lavender"], ["#c4a8e6", "Lilac"], ["#9a86c9", "Violet"],
 ["#d6b4d8", "Orchid"], ["#c9a48d", "Latte"], ["#a98068", "Cocoa"], ["#8a6a58", "Chestnut"], ["#c9c6c0", "Pebble"], ["#a9adb3", "Stone"],
 ["#80868f", "Slate"], ["#5b6170", "Graphite"], ["#3f4450", "Ink"], ["#fbfaf7", "Snow"],
]
export const HAIR_COLORS: [string, string][] = [
 ["#3b2f2a", "Espresso"], ["#6b4a35", "Brown"], ["#a8714a", "Caramel"], ["#e2b866", "Golden"], ["#d4683f", "Ginger"],
 ["#2c2f3a", "Black"], ["#ece6dc", "White"], ["#f3a3b9", "Pink"], ["#8fb8e8", "Blue"], ["#9ccf9a", "Green"],
]
export const SHAPES: [string, string][] = [["round", "Round"], ["mochi", "Mochi"], ["bean", "Bean"], ["kitty", "Kitty"], ["fox", "Fox"], ["pebble", "Pebble"], ["droopy", "Floppy"], ["drop", "Drop"]]
export const EYES: [string, string][] = [
 ["dot", "Dots"], ["button", "Buttons"], ["bean", "Beans"], ["sparkle", "Sparkly"], ["iris", "Bright"], ["ring", "Rings"], ["tiny", "Tiny"],
 ["wide", "Wide"], ["sleepy", "Sleepy"], ["happy", "Happy"], ["line", "Chill"], ["star", "Stars"], ["heart", "Hearts"], ["cat", "Cat"],
 ["lashes", "Lashes"], ["glow", "Glow"], ["square", "Pixel"], ["droop", "Puppy"], ["almond", "Almond"], ["shine", "Glossy"],
]
export const BROWS: [string, string][] = [["none", "None"], ["soft", "Soft"], ["straight", "Straight"], ["thick", "Bold"], ["thin", "Thin"], ["dots", "Dots"], ["fluffy", "Fluffy"], ["tapered", "Tapered"], ["arch", "Arched"]]
export const MOUTHS: [string, string][] = [["smile", "Smile"], ["grin", "Grin"], ["cat", "Cat"], ["open", "Oh"], ["tooth", "Tooth"], ["tongue", "Tongue"], ["flat", "Flat"], ["smirk", "Smirk"]]
export const HAIRS: [string, string][] = [["", "None"], ["tuft", "Tuft"], ["curls", "Curls"], ["bowl", "Bowl"], ["swoop", "Swoop"], ["spiky", "Spiky"], ["bun", "Bun"], ["buns", "Two buns"],
 ["pigtails", "Pigtails"], ["cloud", "Cloud"], ["mohawk", "Mohawk"], ["ponytail", "Ponytail"], ["bob", "Bob"], ["sprout", "Sprout"], ["part", "Side part"], ["wisp", "Wisp"]]
export const HATS: [string, string][] = [["", "None"], ["beanie", "Beanie"], ["cap", "Cap"], ["tophat", "Top hat"], ["party", "Party hat"], ["beret", "Beret"], ["bucket", "Bucket hat"],
 ["crown", "Crown"], ["headphones", "Headphones"], ["flower", "Flower"], ["bow", "Bow"]]

const base: Look = {
 color: "#8fb8e8", shape: "round", head: 1, ears: 0,
 eyes: "dot", eyeGap: 0, eyeY: 0, eyeSize: 0, pupil: 0,
 brows: "none", browGap: 0, browY: 0, browSize: 0, browTilt: 0,
 mouth: "smile", mouthY: 0, mouthSize: 0, blush: true, hair: "", hairColor: "#6b4a35", hat: "",
}
/// The plain shape a new companion starts as, before it has a color or a face.
export const BLANK: Look = { ...base, color: "#ece8e1", eyes: "none", mouth: "none", blush: false }
export const DEFAULT_LOOK = base
// Ready-made faces to start from (eyes, brows, mouth).
export const FACES: Partial<Look>[] = [
 { eyes: "dot", brows: "none", mouth: "smile" }, { eyes: "sparkle", brows: "soft", mouth: "grin" }, { eyes: "happy", brows: "none", mouth: "cat" },
 { eyes: "iris", brows: "thin", mouth: "smile", pupil: .3 }, { eyes: "bean", brows: "dots", mouth: "open" }, { eyes: "almond", brows: "straight", mouth: "smirk" },
 { eyes: "button", brows: "fluffy", mouth: "tooth" }, { eyes: "lashes", brows: "arch", mouth: "tongue" },
]
// Other AI apps working in Still wear these.
export const AGENT_LOOKS: Record<string, Look> = {
 claude: { ...base, color: "#e5876a", eyes: "dot", mouth: "smile", hair: "tuft", hairColor: "#c4623f" },
 chatgpt: { ...base, color: "#7fb39b", shape: "mochi", eyes: "bean", mouth: "smile", hair: "sprout", hairColor: "#3f7a5a" },
 grok: { ...base, color: "#5b6170", shape: "fox", eyes: "glow", mouth: "flat", brows: "straight", blush: false },
}

const pick = <T,>(list: T[]) => list[Math.floor(Math.random() * list.length)]
const jitter = (amount: number) => Math.round((Math.random() * 2 - 1) * amount * 100) / 100
export function surprise(): Look {
 const face = pick(FACES)
 return {
  ...base, ...face, color: pick(BODY_COLORS)[0], shape: pick(SHAPES)[0], head: 1 + jitter(.06), ears: jitter(.6),
  eyeGap: jitter(.4), eyeY: jitter(.3), eyeSize: jitter(.4), browTilt: jitter(.5), mouthSize: jitter(.3),
  hair: Math.random() < .55 ? pick(HAIRS.slice(1))[0] : "", hairColor: pick(HAIR_COLORS)[0], hat: Math.random() < .35 ? pick(HATS.slice(1))[0] : "",
 }
}

const known = (list: [string, string][], v: unknown, fallback: string) => list.some(([k]) => k === v) ? v as string : fallback
const num = (v: unknown, lo: number, hi: number, fallback: number) => typeof v === "number" && isFinite(v) ? Math.min(hi, Math.max(lo, v)) : fallback
const hex = (v: unknown, fallback: string) => typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v) ? v : fallback
/// A saved look, checked field by field: anything missing or unknown falls back to the default.
export function parseLook(raw: unknown, fallback: Look = base): Look {
 let o: Record<string, unknown> = {}
 try { o = typeof raw === "string" ? (raw ? JSON.parse(raw) : {}) : (raw as Record<string, unknown>) ?? {} } catch { return fallback }
 if (!o || typeof o !== "object") return fallback
 const f = fallback
 return {
  color: hex(o.color, f.color), shape: known(SHAPES, o.shape, f.shape), head: num(o.head, .88, 1.12, f.head), ears: num(o.ears, -1, 1, f.ears),
  eyes: o.eyes === "none" ? "none" : known(EYES, o.eyes, f.eyes), eyeGap: num(o.eyeGap, -1, 1, f.eyeGap), eyeY: num(o.eyeY, -1, 1, f.eyeY), eyeSize: num(o.eyeSize, -1, 1, f.eyeSize), pupil: num(o.pupil, -1, 1, f.pupil),
  brows: known(BROWS, o.brows, f.brows), browGap: num(o.browGap, -1, 1, f.browGap), browY: num(o.browY, -1, 1, f.browY), browSize: num(o.browSize, -1, 1, f.browSize), browTilt: num(o.browTilt, -1, 1, f.browTilt),
  mouth: o.mouth === "none" ? "none" : known(MOUTHS, o.mouth, f.mouth), mouthY: num(o.mouthY, -1, 1, f.mouthY), mouthSize: num(o.mouthSize, -1, 1, f.mouthSize),
  blush: typeof o.blush === "boolean" ? o.blush : f.blush, hair: known(HAIRS, o.hair, f.hair), hairColor: hex(o.hairColor, f.hairColor), hat: known(HATS, o.hat, f.hat),
 }
}
export const lookKey = (l: Look) => JSON.stringify(l)
