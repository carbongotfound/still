// Look v2 (Stage 12): saved looks keep meaning what they meant, v2 looks survive a save and a Still from before v2,
// Surprise me only makes good looks and keeps what's locked, and the editor's history. Run: node tests/ui/look.test.ts
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync, writeFileSync } from "node:fs"
import * as L from "../../still-ui/src/look.ts"
import * as V1 from "../fixtures/look-v1.ts" // look.ts as it was before v2, frozen

const F = JSON.parse(readFileSync(new URL("../fixtures/looks.json", import.meta.url), "utf8"))
const seeded = (seed: number) => () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32)

test("every saved look reads exactly as before v2", () => {
 for (const s of [...F.v1, ...F.legacy]) {
  assert.equal(L.lookKey(L.parseLook(s)), V1.lookKey(V1.parseLook(s)), s)
  assert.equal(L.lookKey(L.parseLook(s)), F.parsed[s], s)
  assert.ok(!L.isV2(L.parseLook(s)), s)
 }
})

test("a v2 look survives a save, and an older Still reads its v1 fields", () => {
 const random = seeded(7), all = [...L.STARTS.map(([, l]) => l), ...L.TEAM_LOOKS.map(([, l]) => l), ...Array.from({ length: 200 }, () => L.surprise(L.BLANK_V2, {}, random))]
 for (const l of all) {
  const saved = L.lookKey(l)
  assert.deepEqual(L.parseLook(saved), l, saved)
  assert.equal(L.lookKey(L.parseLook(saved)), saved)
  const old = V1.parseLook(saved)
  assert.deepEqual({ ...old }, { color: l.color, shape: L.FORM_SHAPE[l.form!], prop: "", accessory: l.accessory }, saved)
 }
})

test("a v2 look with parts this build doesn't know falls back part by part", () => {
 const l = L.parseLook(JSON.stringify({ v: 2, color: "#ABCDEF", shape: "tall", prop: "", accessory: "glasses", form: "cube", second: "red", marking: "spots", eye: "x", mouth: "o", top: "hat", finish: "chrome" }))
 assert.deepEqual(l, L.v2({ form: "column", color: "#abcdef", second: "#abcdef", eye: "round", mouth: "o", top: "none", finish: "matte", accessory: "" }), "an unreadable accent: none")
})

test("Surprise me: 500 draws, each a good look that keeps what's locked", () => {
 const random = seeded(42), kinds = ["body", "colors", "face", "feature"] as const
 let base = L.STARTS[3][1]
 for (let i = 0; i < 500; i++) {
  const locks = Object.fromEntries(kinds.map(k => [k, random() < .35]))
  const l = L.surprise(base, locks, random)
  assert.deepEqual(L.lookIssues(l), [], L.lookKey(l))
  assert.deepEqual(L.parseLook(L.lookKey(l)), l) // every part a known one
  if (locks.body) assert.equal(l.form, base.form)
  if (locks.colors) assert.deepEqual([l.color, l.second, l.finish], [base.color, base.second, base.finish])
  assert.ok(!("marking" in l) && !("mark" in l), "Surprise me never makes a marking")
  if (locks.face) assert.deepEqual([l.eye, l.mouth], [base.eye, base.mouth])
  if (locks.feature) assert.deepEqual([l.top, l.accessory], [base.top, base.accessory])
  base = l
 }
})

test("the curated looks and pairs pass the small-size checks", () => {
 for (const [name, l] of [...L.STARTS, ...L.TEAM_LOOKS]) assert.deepEqual(L.lookIssues(l), [], name)
 for (const [a, b, name] of L.PAIRS) assert.ok(L.deltaE(a, b) >= 15, name)
 assert.deepEqual(L.TEAM_LOOKS.map(([r]) => r), ["sales", "growth", "planner", "marketing", "engineer", "research"])
 assert.equal(L.STARTS.length, 10)
 assert.deepEqual(L.lookIssues(L.v2({ ...L.BLANK_V2, form: "pebble", second: L.BLANK_V2.color, eye: "round", mouth: "smile", top: "none", finish: "matte" } as never)), [], "one solid color is a good look")
 assert.ok(L.lookIssues(L.v2({ ...L.BLANK_V2, form: "pebble", second: "#f4d36c", eye: "round", mouth: "smile", top: "none", finish: "matte" } as never)).length > 0, "an accent in nearly the body's own color is flagged")
})

test("colors: solid by default, an accent only if picked, and no markings anywhere (Stage 17)", () => {
 for (const [name, l] of [...L.STARTS, ...L.TEAM_LOOKS]) assert.ok(!("marking" in l) && !("mark" in l), name)
 assert.ok(!("MARKINGS" in L) && !("markColor" in L), "nothing left to pick a marking from")
 assert.ok(!L.hasAccent(L.BLANK_V2), "Make your own starts solid")
 assert.equal(L.STARTS.filter(([, l]) => !L.hasAccent(l)).length, 6, "most starting looks are one color")
 assert.equal(L.SOLIDS.length, 24); assert.equal(new Set(L.SOLIDS.map(([h]) => h)).size, 24)
 assert.ok(L.SOLIDS.every(([h]) => /^#[0-9a-f]{6}$/.test(h)))
 assert.equal(L.BODY_COLORS.length, 16, "plugins take their colors from BODY_COLORS by name: it stays as it was")
 // a look saved with a marking (2.10 before Stage 17), with or without its own color: everything else as it was, the marking gone
 for (const marking of ["belly", "mask", "tips", "freckles", "none", "spots"]) for (const mark of ["", ',"mark":"#4a5263"']) {
  const s = `{"v":2,"color":"#a6cf9c","shape":"block","prop":"","accessory":"bow","form":"block","second":"#4f8a4a","marking":"${marking}"${mark},"eye":"sleepy","mouth":"smile","top":"cap","finish":"gloss"}`
  const l = L.parseLook(s)
  assert.deepEqual(l, L.v2({ form: "block", color: "#a6cf9c", second: "#4f8a4a", eye: "sleepy", mouth: "smile", top: "cap", finish: "gloss", accessory: "bow" }), s)
  const saved = JSON.parse(L.lookKey(l))
  assert.ok(!("marking" in saved) && !("mark" in saved), s)
  assert.deepEqual({ ...V1.parseLook(L.lookKey(l)) }, { color: "#a6cf9c", shape: "block", prop: "", accessory: "bow" }, "an older Still still reads it")
 }
})

test("undo, redo, Reset and Cancel", () => {
 const a = L.STARTS[0][1], b = L.STARTS[1][1], c = L.STARTS[2][1]
 let h = L.history(a)
 h = L.change(h, b); h = L.change(h, c)
 assert.equal(L.change(h, c), h, "the same look again isn't a change")
 h = L.undo(h); assert.equal(h.now, b)
 h = L.undo(h); assert.equal(h.now, a)
 assert.equal(L.undo(h), h, "nothing left to undo")
 h = L.redo(h); assert.equal(h.now, b)
 h = L.change(h, L.STARTS[4][1]); assert.equal(h.future.length, 0, "a change after undo drops redo")
 h = L.reset(h); assert.equal(h.now, a); assert.equal(h.start, a)
 h = L.undo(h); assert.equal(h.now, L.STARTS[4][1], "Reset can be undone")
 assert.equal(L.history(a).now, a, "Cancel keeps the look it opened with: the editor saves nothing")
})
test("a classic look changed in the editor: every saved look becomes a good v2 look, its prop only if kept", () => {
 for (const s of [...F.v1, ...F.legacy]) {
  const old = L.parseLook(s), l = L.newStyle(old), kept = L.newStyle(old, true)
  assert.ok(L.isV2(l) && L.FORMS.some(([f]) => f === l.form), s)
  assert.deepEqual(L.lookIssues(l), [], s)
  assert.equal(l.color, old.color, s)
  assert.equal(l.prop, "", s)
  assert.equal(kept.prop, old.prop, s)
  assert.deepEqual(L.parseLook(L.lookKey(kept)), kept, s)
 }
 // a team member's own look becomes their team look (body, face, top, accent), in their own color
 for (const [role, team] of L.TEAM_LOOKS) {
  const l = L.newStyle(L.ROLE_LOOKS[role])
  assert.deepEqual([l.form, l.eye, l.mouth, l.top, l.second, l.color], [team.form, team.eye, team.mouth, team.top, team.second, L.ROLE_LOOKS[role].color], role)
  assert.deepEqual(L.lookIssues(l), [], role)
 }
 const ruth = L.newStyle(L.ROLE_LOOKS.assistant)
 assert.deepEqual([ruth.form, ruth.color], ["column", "#2fa496"], "Ruth, with no team look: her color on the nearest body")
})

test("every look string stays within 2000 characters", () => {
 const random = seeded(3), longest = [...L.STARTS.map(([, l]) => l), ...Array.from({ length: 200 }, () => L.surprise(L.BLANK_V2, {}, random)),
  L.v2({ ...L.BLANK_V2 as Required<L.Look>, top: "antennae", accessory: "flower", prop: "paintbrush" })].map(l => L.lookKey(l).length)
 assert.ok(Math.max(...longest) < 2000, String(Math.max(...longest)))
})
test("tests/fixtures/looks-v2.json (the desktop test's new-style looks) is what look.ts makes now; UPDATE=1 rewrites it", () => {
 const random = seeded(11)
 const now = { starts: L.STARTS.map(([n, l]) => [n, L.lookKey(l)]), team: L.TEAM_LOOKS.map(([r, l]) => [r, L.lookKey(l)]),
  surprise: Array.from({ length: 40 }, () => L.lookKey(L.surprise(L.BLANK_V2, {}, random))),
  kept: [8, 9, 10].map(i => L.lookKey(L.newStyle(L.parseLook(F.v1[i]), true))) }
 const path = new URL("../fixtures/looks-v2.json", import.meta.url)
 if (process.env.UPDATE) writeFileSync(path, JSON.stringify(now, null, 1))
 assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), now)
})
