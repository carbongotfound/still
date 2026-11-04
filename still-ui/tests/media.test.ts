import { test } from "node:test"
import assert from "node:assert/strict"
import { mediaLine, startOf } from "../src/media.ts"

test("an image on its own line is a card", () => {
 assert.deepEqual(mediaLine("![A blue desk lamp](https://example.com/lamp.jpg)"), { kind: "image", alt: "A blue desk lamp", url: "https://example.com/lamp.jpg" })
 assert.deepEqual(mediaLine("  ![](https://example.com/a.png)  "), { kind: "image", alt: "", url: "https://example.com/a.png" })
})

test("only https images, and only alone on a line", () => {
 assert.equal(mediaLine("![x](http://example.com/a.png)"), null)
 assert.equal(mediaLine("![x](data:image/png;base64,AAAA)"), null)
 assert.equal(mediaLine("![x](javascript:alert(1))"), null)
 assert.equal(mediaLine("See ![x](https://example.com/a.png) here"), null)
 assert.equal(mediaLine("[a link](https://example.com/a.png)"), null)
})

test("YouTube links are video cards", () => {
 assert.deepEqual(mediaLine("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), { kind: "video", title: "", url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ", id: "dQw4w9WgXcQ", start: undefined })
 const titled = mediaLine("[How sourdough works](https://youtu.be/abcDEF12345?t=95)")
 assert.equal(titled?.kind, "video")
 assert.equal(titled?.kind === "video" && titled.id, "abcDEF12345")
 assert.equal(titled?.kind === "video" && titled.title, "How sourdough works")
 assert.equal(titled?.kind === "video" && titled.start, "1:35")
 assert.equal((mediaLine("https://www.youtube.com/watch?feature=share&v=abcDEF12345") as { id: string }).id, "abcDEF12345")
 assert.equal((mediaLine("https://youtube.com/shorts/abcDEF12345") as { id: string }).id, "abcDEF12345")
})

test("not videos: other sites, text around the link, a bad id", () => {
 assert.equal(mediaLine("https://vimeo.com/123456"), null)
 assert.equal(mediaLine("Watch https://youtu.be/abcDEF12345 now"), null)
 assert.equal(mediaLine("https://youtu.be/short"), null)
 assert.equal(mediaLine("https://youtu.be/abcDEF123456789"), null)
 assert.equal(mediaLine("https://youtube.com.evil.example/watch?v=abcDEF12345"), null)
})

test("a start time only when it can be read", () => {
 assert.equal(startOf("https://youtu.be/x?t=90"), "1:30")
 assert.equal(startOf("https://youtu.be/x?t=1m30s"), "1:30")
 assert.equal(startOf("https://youtu.be/x?t=1h2m3s"), "1:02:03")
 assert.equal(startOf("https://www.youtube.com/watch?v=x&start=5"), "0:05")
 assert.equal(startOf("https://youtu.be/x?t=abc"), undefined)
 assert.equal(startOf("https://youtu.be/x?t=0"), undefined)
 assert.equal(startOf("https://youtu.be/x"), undefined)
})
