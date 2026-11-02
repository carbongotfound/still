// Media in a reply: an image (![alt](https://...)) or a YouTube video link, each on a line of its own, shows as a card.
export type MediaLine =
 | { kind: "image"; alt: string; url: string }
 | { kind: "video"; title: string; url: string; id: string; start?: string }

const IMAGE = /^\s*!\[([^\]\n]*)\]\((https:\/\/[^)\s]+)\)\s*$/
const YOUTUBE = String.raw`https:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:[^)\s]*&)?v=|shorts\/)|youtu\.be\/)([\w-]{11})(?![\w-])[^)\s]*`
const VIDEO_LINK = new RegExp(String.raw`^\s*\[([^\]\n]+)\]\((${YOUTUBE})\)\s*$`)
const VIDEO_BARE = new RegExp(String.raw`^\s*(${YOUTUBE})\s*$`)

export function mediaLine(line: string): MediaLine | null {
 const image = IMAGE.exec(line)
 if (image) return { kind: "image", alt: image[1].trim(), url: image[2] }
 const link = VIDEO_LINK.exec(line), bare = link ? null : VIDEO_BARE.exec(line)
 if (link) return { kind: "video", title: link[1].trim(), url: link[2], id: link[3], start: startOf(link[2]) }
 if (bare) return { kind: "video", title: "", url: bare[1], id: bare[2], start: startOf(bare[1]) }
 return null
}

/** Where a video link starts (t= or start=, as seconds or 1h2m3s), as m:ss or h:mm:ss; nothing when it can't be read. */
export function startOf(url: string): string | undefined {
 const t = /[?&#](?:t|start)=([^&#]+)/.exec(url)?.[1]
 const m = t ? /^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$/.exec(t) : null
 if (!t || !m || !/\d/.test(t)) return undefined
 const secs = Number(m[1] ?? 0) * 3600 + Number(m[2] ?? 0) * 60 + Number(m[3] ?? 0)
 if (!secs) return undefined
 const h = Math.floor(secs / 3600), min = Math.floor((secs % 3600) / 60), s = String(secs % 60).padStart(2, "0")
 return h ? `${h}:${String(min).padStart(2, "0")}:${s}` : `${min}:${s}`
}
