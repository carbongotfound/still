// Still's own little sounds (tools/sound makes them, MIT like the rest): the intro, setup's whooshes, clicks and pops,
// the look editor, and a jingle at the end. Companions don't make noises when they talk. Browsing never makes a sound.
// They stay off with the Sounds setting off, the system's "no sounds", or reduced motion.
const reduce = matchMedia("(prefers-reduced-motion: reduce)")
let allowed = true, ctx: AudioContext | undefined, out: GainNode | undefined
const buffers = new Map<string, Promise<AudioBuffer | undefined>>()
export const played: { name: string; at: number }[] = [] // what played, for the tests
;(window as unknown as { stillSounds: unknown }).stillSounds = { played }

export const soundOn = () => allowed && !reduce.matches
export function setSounds(on: boolean) {
 allowed = on
 if (ctx && out) out.gain.setTargetAtTime(soundOn() ? 1 : 0, ctx.currentTime, .04) // muting fades what's playing
}

function context() {
 if (!ctx) { ctx = new AudioContext(); out = ctx.createGain(); out.connect(ctx.destination) }
 if (ctx.state === "suspended") void ctx.resume()
 return ctx
}
function load(name: string) {
 let b = buffers.get(name)
 if (!b) buffers.set(name, b = fetch(`sounds/${name}.ogg`).then(r => r.arrayBuffer()).then(a => context().decodeAudioData(a)).catch(() => undefined))
 return b
}
export const warm = (...names: string[]) => { if (soundOn()) for (const n of names) void load(n) }

export type Playing = { stop: (fade?: number) => void }
export function play(name: string, { rate = 1, gain = 1, delay = 0 } = {}): Playing {
 if (!soundOn()) return { stop() {} }
 played.push({ name, at: performance.now() + delay * 1000 })
 const c = context(), level = c.createGain()
 level.gain.value = gain; level.connect(out!)
 let src: AudioBufferSourceNode | undefined, stopped = false
 void load(name).then(buffer => {
  if (!buffer || stopped) return
  src = c.createBufferSource(); src.buffer = buffer; src.playbackRate.value = rate; src.connect(level); src.start(c.currentTime + delay)
 })
 return { stop(fade = .25) { stopped = true; level.gain.setTargetAtTime(0, c.currentTime, fade / 4); src?.stop(c.currentTime + fade) } }
}
