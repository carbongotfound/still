import { useEffect, useState } from "react"
import { ImageOff, Image as ImageIcon, Play } from "lucide-react"
import type { MediaLine } from "./media"

// Still fetches the picture (no cookies, no profile) and hands it back as a data URL: the page's rules allow only those.
// A reply's own images load when the user asks, so a page can't get the AI to leak data through an image address;
// a YouTube thumbnail is built from the video's id alone, so it loads by itself.
type Got = { src?: string; error?: string }
const got = new Map<string, Got>(), waiting = new Map<string, Set<(g: Got) => void>>()
let listening = false

function fetchMedia(url: string, done: (g: Got) => void) {
 const bridge = window.chrome?.webview
 if (!bridge) { done({ error: "The image didn't load." }); return }
 if (!listening) {
  listening = true
  bridge.addEventListener("message", (e: MessageEvent) => {
   if (e.data?.kind !== "media") return
   const { url: from, ...result } = e.data.data as Got & { url: string }
   got.set(from, result); waiting.get(from)?.forEach(f => f(result)); waiting.delete(from)
  })
 }
 const set = waiting.get(url)
 if (set) { set.add(done); return }
 waiting.set(url, new Set([done]))
 bridge.postMessage({ op: "mediaFetch", url })
}

const hostOf = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url } }

export function MediaCard({ media, onLink }: { media: MediaLine; onLink: (url: string) => void }) {
 const thumb = media.kind === "video" ? `https://i.ytimg.com/vi/${media.id}/hqdefault.jpg` : media.url
 const [want, setWant] = useState(media.kind === "video" || got.has(thumb))
 const [result, setResult] = useState<Got | undefined>(got.get(thumb))
 useEffect(() => { if (want && !result) fetchMedia(thumb, setResult) }, [want, thumb, result])
 const open = (e: React.MouseEvent) => { e.preventDefault(); onLink(media.url) }
 const broken = () => setResult({ error: "The image didn't load." })
 if (media.kind === "video") return <figure className="md-media md-video">
  <a href={media.url} title={media.url} onClick={open} className="md-media-frame">
   {result?.src ? <img src={result.src} alt="" onError={broken} /> : <span className="md-media-empty" />}<span className="md-play"><Play /></span>
  </a>
  <figcaption><span>{media.title || "YouTube video"}</span>{media.start && <small>Starts at {media.start}</small>}
   <a href={media.url} onClick={open}>youtube.com</a></figcaption>
 </figure>
 return <figure className="md-media">
  {result?.src ? <img src={result.src} alt={media.alt} onError={broken} />
   : <div className="md-media-empty">{result?.error ? <><ImageOff /><span>{result.error}</span></>
    : <button type="button" disabled={want} onClick={() => setWant(true)}><ImageIcon />{want ? "Loading…" : "Show image"}</button>}</div>}
  <figcaption>{media.alt && <span>{media.alt}</span>}<a href={media.url} title={media.url} onClick={open}>{hostOf(media.url)}</a></figcaption>
 </figure>
}
