import type { Look } from "./look"

// The companion's face, drawn flat onto the front of its head (the model's face UVs are a front projection of a
// 0.58-unit square centered 0.655 up). The same drawing serves the 3D model's texture and any flat preview.
export type FacePose = {
 open: number // eyelids: 1 open, 0 shut
 squint: number // happy squint: 0..1
 raise: number // brows up (+) or down (-)
 worry: number // inner brow ends up: 0..1
 mouthOpen: number // 0..1
 smile: number // -1 frown .. 1 smile (a little past 1 is a big smile)
 gx: number; gy: number // gaze, -1..1 (x to the viewer's right, y down)
}
export const REST: FacePose = { open: 1, squint: 0, raise: 0, worry: 0, mouthOpen: 0, smile: 1, gx: 0, gy: 0 }

const INK = "#221a2a", WHITE = "#ffffff", TONGUE = "#ef7d8a", GLOW = "rgba(150,132,214,.6)"
const FACE = { cz: .655, size: .58 }
const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))
type G = CanvasRenderingContext2D

export function drawFace(g: G, S: number, look: Look, p: FacePose) {
 const U = S / FACE.size
 const X = (x: number) => S / 2 + x * U, Y = (z: number) => S * (.5 - (z - FACE.cz) / FACE.size)
 g.clearRect(0, 0, S, S)
 g.lineCap = g.lineJoin = "round"
 if (look.blush) for (const side of [-1, 1]) {
  const bx = X(side * .19), by = Y(.598), rx = .05 * U, ry = .028 * U
  const r = g.createRadialGradient(bx, by, 0, bx, by, rx)
  r.addColorStop(0, "rgba(242,120,132,.42)"); r.addColorStop(1, "rgba(242,120,132,0)")
  g.fillStyle = r; g.beginPath(); g.ellipse(bx, by, rx, ry, 0, 0, Math.PI * 2); g.fill()
 }
 // big eyes set fairly close and low, with the mouth tucked under them: the face reads as one group, not three dots
 const ez = .648 + look.eyeY * .028, er = .053 * (1 + look.eyeSize * .26) * U
 const ex = .116 + look.eyeGap * .028
 if (look.eyes !== "none") for (const side of [-1, 1]) eye(g, look.eyes, X(side * ex), Y(ez), er, side, p, look.pupil)
 if (look.glasses) glasses(g, look.glasses, X(-ex), X(ex), Y(ez), Math.max(er * 1.72, .086 * U))
 if (look.brows !== "none") {
  const bz = ez + .088 + look.browY * .022 + p.raise * .018, L = .058 * (1 + look.browSize * .3) * U
  for (const side of [-1, 1]) brow(g, look.brows, X(side * (.118 + look.browGap * .03)), Y(bz), L, side, side * look.browTilt * .38 - side * p.worry * .42)
 }
 if (look.mouth !== "none") mouth(g, look.mouth, X(0), Y(.568 + look.mouthY * .024), .054 * (1 + look.mouthSize * .32) * U, p)
}

function ellipse(g: G, x: number, y: number, rx: number, ry: number, rot = 0) { g.beginPath(); g.ellipse(x, y, Math.max(.01, rx), Math.max(.01, ry), rot, 0, Math.PI * 2) }
// Dark eyes are glossy beads: deep ink sitting a touch proud of the face, a glow of color low down, one big highlight up
// and to the left and a small one below. Every style shares the same light, so the two eyes read as one window's.
function bead(g: G, shape: () => void, r: number, k = 1) {
 g.save()
 g.shadowColor = "rgba(48,28,36,.22)"; g.shadowBlur = r * .16; g.shadowOffsetY = r * .06
 g.fillStyle = INK; shape(); g.fill()
 g.shadowColor = "transparent"; shape(); g.clip()
 const glow = g.createRadialGradient(0, r * 1.05, 0, 0, r * 1.05, r * .95)
 glow.addColorStop(0, GLOW); glow.addColorStop(1, "rgba(150,132,214,0)")
 g.fillStyle = glow; g.fillRect(-r * 2, -r * 2, r * 4, r * 4)
 g.restore()
 shine(g, r, k)
}
function shine(g: G, r: number, k = 1) {
 g.fillStyle = WHITE
 ellipse(g, -.3 * r, -.36 * r, .27 * r * k, .34 * r * k, -.45); g.fill()
 ellipse(g, .3 * r, .4 * r, .11 * r * k, .11 * r * k); g.fill()
}
function lemon(g: G, w: number, h: number) { g.beginPath(); g.moveTo(-w, 0); g.quadraticCurveTo(0, -h * 2, w, 0); g.quadraticCurveTo(0, h * 2, -w, 0); g.closePath() }
function star(g: G, r: number) {
 g.beginPath()
 for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, q = i % 2 ? r * .48 : r; g.lineTo(Math.cos(a) * q, Math.sin(a) * q) }
 g.closePath()
}
function heart(g: G, r: number) {
 g.beginPath(); g.moveTo(0, r * .9)
 g.bezierCurveTo(-r * 1.3, 0, -r * .9, -r * 1.05, 0, -r * .45)
 g.bezierCurveTo(r * .9, -r * 1.05, r * 1.3, 0, 0, r * .9); g.closePath()
}
function round(g: G, x: number, y: number, w: number, h: number, r: number) { g.beginPath(); g.roundRect(x, y, w, h, r) }

function eye(g: G, style: string, x: number, y: number, r: number, side: number, p: FacePose, pupil: number) {
 const open = clamp(p.open), sq = clamp(p.squint)
 const ox = clamp(p.gx, -1, 1) * r * .3, oy = clamp(p.gy, -1, 1) * r * .24
 g.fillStyle = g.strokeStyle = INK
 if (style === "happy" || style === "line" || open < .12) { // a closed or smiling eye is a line
  g.lineWidth = r * (style === "line" ? .22 : .24)
  g.beginPath()
  if (style === "line" && open >= .16) { g.moveTo(x - r * .7 + ox, y + oy); g.lineTo(x + r * .7 + ox, y + oy) }
  else if (style === "happy" || sq > .4) g.arc(x + ox, y + r * .38 + oy, r * .74, Math.PI + .35, Math.PI * 2 - .35)
  else { g.moveTo(x - r * .75 + ox, y + oy); g.quadraticCurveTo(x + ox, y + r * .35 + oy, x + r * .75 + ox, y + oy) }
  g.stroke(); return
 }
 g.save()
 if (sq > .02) { // the cheek pushes up from below
  g.beginPath(); g.rect(x - r * 3, y - r * 3, r * 6, r * 6)
  g.ellipse(x, y + r * (2.35 - 1.45 * sq), r * 1.7, r * 1.45, 0, 0, Math.PI * 2)
  g.clip("evenodd")
 }
 g.translate(x + ox, y + oy)
 // Blinks and sleepy looks bring the upper lid down over the eye: the eye keeps its shape, less of it shows.
 const lid = open < .97 && style !== "sleepy" ? lidEdge(r, open) : null
 if (lid) { g.beginPath(); g.moveTo(-r * 2, lid(-r * 2)); for (let i = 1; i <= 8; i++) g.lineTo(-r * 2 + i * r / 2, lid(-r * 2 + i * r / 2)); g.lineTo(r * 2, r * 3); g.lineTo(-r * 2, r * 3); g.closePath(); g.clip() }
 const hl = 1 - pupil * .35
 switch (style) {
  case "button": bead(g, () => ellipse(g, 0, 0, r * .95, r * .95), r, hl * 1.1); break
  case "bean": bead(g, () => ellipse(g, 0, 0, r * .62, r * 1.08), r * .8, hl); break
  case "sparkle":
   bead(g, () => ellipse(g, 0, 0, r * .9, r * 1.12), r * 1.08, hl * 1.1)
   g.fillStyle = WHITE; ellipse(g, .12 * r, -.08 * r, .07 * r, .07 * r); g.fill(); break
  case "iris": {
   g.fillStyle = WHITE; ellipse(g, 0, 0, r * 1.02, r * 1.18); g.fill(); g.lineWidth = r * .13; g.stroke()
   g.save(); ellipse(g, 0, 0, r * .96, r * 1.12); g.clip()
   const ir = r * .74, ix = ox * .6, iy = oy * .6
   g.fillStyle = "#6b4a3a"; ellipse(g, ix, iy + r * .08, ir, ir); g.fill()
   g.fillStyle = INK; ellipse(g, ix, iy + r * .08, ir * (.48 + pupil * .2), ir * (.48 + pupil * .2)); g.fill()
   g.fillStyle = WHITE; ellipse(g, ix - ir * .35, iy - ir * .3, ir * .26, ir * .26); g.fill(); g.restore(); break
  }
  case "ring": g.lineWidth = r * .3; ellipse(g, 0, 0, r * .82, r * .9); g.stroke(); ellipse(g, 0, 0, r * (.26 + pupil * .12), r * (.28 + pupil * .12)); g.fill(); break
  case "tiny": ellipse(g, 0, 0, r * .45, r * .5); g.fill(); g.fillStyle = WHITE; ellipse(g, -r * .14, -r * .18, r * .13, r * .13); g.fill(); break
  case "wide": bead(g, () => ellipse(g, 0, 0, r * 1.1, r * .76), r * .85, hl); break
  case "sleepy":
   g.save(); g.beginPath(); g.rect(-r * 2, -r * .12, r * 4, r * 3); g.clip(); ellipse(g, 0, 0, r * .9, r * .95); g.fill(); g.restore()
   g.lineWidth = r * .16; g.beginPath(); g.moveTo(-r * 1.02, -r * .12); g.lineTo(r * 1.02, -r * .12); g.stroke()
   g.fillStyle = WHITE; ellipse(g, -r * .28, r * .22, r * .16 * hl, r * .16 * hl); g.fill(); break
  case "star": star(g, r * 1.1); g.fill(); g.fillStyle = WHITE; ellipse(g, -r * .2, -r * .25, r * .17 * hl, r * .17 * hl); g.fill(); break
  case "heart": g.fillStyle = "#e0526f"; heart(g, r * 1.05); g.fill(); g.fillStyle = WHITE; ellipse(g, -r * .38, -r * .38, r * .18 * hl, r * .14 * hl, -.5); g.fill(); break
  case "cat":
   g.fillStyle = "#e3b23c"; lemon(g, r * 1.1, r * .62); g.fill(); g.lineWidth = r * .12; g.stroke()
   g.fillStyle = INK; ellipse(g, 0, 0, r * (.15 + pupil * .1 + .05), r * .6); g.fill()
   g.fillStyle = WHITE; ellipse(g, -r * .38, -r * .2, r * .12, r * .12); g.fill(); break
  case "lashes":
   bead(g, () => ellipse(g, 0, 0, r * .8, r * .96), r * .95, hl)
   g.strokeStyle = INK; g.lineWidth = r * .12
   for (const [a, l] of [[-.5, .5], [-.95, .45], [-1.35, .38]] as const) {
    const ax = Math.cos(a) * r * .82 * side, ay = Math.sin(a) * r
    g.beginPath(); g.moveTo(ax, ay); g.lineTo(ax + Math.cos(a) * r * l * side, ay + Math.sin(a) * r * l); g.stroke()
   }
   break
  case "glow":
   g.fillStyle = "#d4ff4f"; g.shadowColor = "rgba(212,255,79,.85)"; g.shadowBlur = r * .7
   round(g, -r * .38, -r * .66, r * .76, r * 1.32, r * .38); g.fill(); g.shadowBlur = 0; break
  case "square": round(g, -r * .78, -r * .78, r * 1.56, r * 1.56, r * .32); g.fill(); g.fillStyle = WHITE; round(g, -r * .5, -r * .5, r * .38 * hl, r * .38 * hl, r * .08); g.fill(); break
  case "droop": bead(g, () => ellipse(g, 0, 0, r * .9, r * 1.0, -side * .32), r, hl); break
  case "almond": g.rotate(-side * .22); lemon(g, r * 1.15, r * .72); g.fill(); g.rotate(side * .22); g.fillStyle = WHITE; ellipse(g, -r * .3, -r * .12, r * .2 * hl, r * .16 * hl); g.fill(); break
  case "shine": {
   bead(g, () => ellipse(g, 0, 0, r * .95, r * 1.18), r * 1.12, hl * 1.1)
   g.fillStyle = WHITE; g.globalAlpha = .5; ellipse(g, -.05 * r, .66 * r, .3 * r, .07 * r); g.fill(); g.globalAlpha = 1; break
  }
  default: bead(g, () => ellipse(g, 0, 0, r * .8, r * .98), r, hl) // dot
 }
 g.restore()
 if (lid) { // the lid's edge, as wide as the eye
  g.save(); g.translate(x + ox, y + oy); g.strokeStyle = INK; g.lineWidth = r * .17
  g.beginPath(); for (let i = 0; i <= 8; i++) { const lx = -r * .95 + i * r * 1.9 / 8; g.lineTo(lx, lid(lx)) } g.stroke(); g.restore()
 }
}
/// Where the upper lid's edge is at x: a soft curve that drops from above the eye to below it as the eye shuts.
function lidEdge(r: number, open: number) {
 const edge = -r * 1.6 + (1 - open) * r * 2.9, sag = r * .3
 return (x: number) => edge - sag + sag * 2 * (1 - (x / (r * 2)) ** 2)
}

function glasses(g: G, style: string, xl: number, xr: number, y: number, R: number) {
 g.save(); g.strokeStyle = "#3b2f36"; g.lineWidth = R * .13
 for (const x of [xl, xr]) {
  g.beginPath()
  if (style === "square") g.roundRect(x - R, y - R * .8, R * 2, R * 1.6, R * .32); else g.arc(x, y, R, 0, Math.PI * 2)
  g.stroke()
  g.save(); g.globalAlpha = .4; g.strokeStyle = WHITE; g.lineWidth = R * .08; g.beginPath(); g.arc(x, y, R * .74, -2.6, -1.95); g.stroke(); g.restore() // a glint on the lens
 }
 g.beginPath(); g.moveTo(xl + R * .96, y - R * .1); g.quadraticCurveTo((xl + xr) / 2, y - R * .42, xr - R * .96, y - R * .1); g.stroke()
 g.restore()
}

function brow(g: G, style: string, x: number, y: number, L: number, side: number, angle: number) {
 g.save(); g.translate(x, y); g.rotate(angle)
 g.strokeStyle = g.fillStyle = INK
 const t = L * .2, h = L / 2
 const arc = (lift: number, w: number) => { g.lineWidth = w; g.beginPath(); g.moveTo(-h, 0); g.quadraticCurveTo(0, -L * lift, h, 0); g.stroke() }
 switch (style) {
  case "straight": g.lineWidth = t; g.beginPath(); g.moveTo(-h, 0); g.lineTo(h, 0); g.stroke(); break
  case "thick": round(g, -h, -t, L, t * 2, t); g.fill(); break
  case "thin": arc(.3, t * .55); break
  case "dots": ellipse(g, side * L * .12, 0, L * .26, t * 1.05); g.fill(); break
  case "fluffy": for (const [dx, dy, r] of [[-.32, .06, .2], [0, -.04, .24], [.32, .06, .2]]) { ellipse(g, dx * L, dy * L, r * L, r * L * .8); g.fill() } break
  case "tapered": { // thick at the inner end
   const i = -side * h, o = side * h
   g.beginPath(); g.moveTo(i, -t * .9); g.quadraticCurveTo(0, -t * 1.6, o, -t * .1); g.quadraticCurveTo(0, -t * .2, i, t * .9); g.closePath(); g.fill(); break
  }
  case "arch": arc(.62, t * .8); break
  default: arc(.3, t) // soft
 }
 g.restore()
}

function mouth(g: G, style: string, x: number, y: number, W: number, p: FacePose) {
 g.save(); g.translate(x, y)
 g.strokeStyle = g.fillStyle = INK
 const s = clamp(p.smile, -1, 1.6), h = W / 2, line = W * .17
 let open = clamp(p.mouthOpen)
 if (style === "grin") open = Math.max(open, .35)
 if (style === "open") { const k = .8 + open * .9; ellipse(g, 0, W * .05, W * .2 * k, W * .24 * k); g.fill(); g.restore(); return }
 if (open > .12) { // talking, cheering
  g.beginPath(); g.moveTo(-h, 0); g.quadraticCurveTo(0, -s * W * .06, h, 0)
  g.quadraticCurveTo(h * .9, W * (.2 + .75 * open), 0, W * (.22 + .8 * open)); g.quadraticCurveTo(-h * .9, W * (.2 + .75 * open), -h, 0)
  g.closePath(); g.fill()
  g.save(); g.clip(); g.fillStyle = TONGUE; ellipse(g, 0, W * (.3 + .8 * open), W * .28, W * .2); g.fill(); g.restore()
  g.restore(); return
 }
 g.lineWidth = line
 const curve = (k: number) => { g.beginPath(); g.moveTo(-h, 0); g.quadraticCurveTo(0, s * W * k, h, 0); g.stroke() }
 switch (style) {
  case "cat":
   g.lineWidth = line * .85; g.beginPath()
   g.arc(-W * .24, 0, W * .24, s >= 0 ? 0 : Math.PI, s >= 0 ? Math.PI : 0, s < 0)
   g.moveTo(W * .48, 0); g.arc(W * .24, 0, W * .24, s >= 0 ? 0 : Math.PI, s >= 0 ? Math.PI : 0, s < 0); g.stroke(); break
  case "tooth":
   curve(.42); g.fillStyle = WHITE; g.lineWidth = line * .5
   round(g, -W * .1, s * W * .2 - line * .1, W * .2, W * .2, W * .05); g.fill(); g.stroke(); break
  case "tongue":
   g.fillStyle = TONGUE; ellipse(g, W * .12, s * W * .2 + W * .08, W * .14, W * .16); g.fill(); curve(.42); break
  case "flat": g.beginPath(); g.moveTo(-h * .8, 0); g.quadraticCurveTo(0, s * W * .08, h * .8, 0); g.stroke(); break
  case "smirk": g.beginPath(); g.moveTo(-h, W * .02); g.quadraticCurveTo(W * .12, W * .3 * Math.max(s, 0) + W * .02, h, -W * .16); g.stroke(); break
  default: curve(.42) // smile
 }
 g.restore()
}
