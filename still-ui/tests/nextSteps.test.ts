import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nextSteps } from '../src/nextSteps.ts'
import { readFileSync } from 'node:fs'

const noRawMarker = (body: string) => assert.ok(!/^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)?(?:\*\*|\*|_)?(?:>>|»|&gt;&gt;)/m.test(body.split(/```[\s\S]*?```/).join('')), body)
const steps = (text: string) => { const r = nextSteps(text); noRawMarker(r.body); return r }

// A live reply (Claude Haiku, Stage 4 check) with a bold label before the steps.
const live = `Here's Jonah's pitch:

> **"Warm, glare-free light that's easy on your eyes, for just $49. It ships next week."**

**Sources:** None. Jonah didn't look anything up.

**Next steps**
>> Swap in the exact ship date
>> Get 3 more pitch variants with different tones
>> Draft a short product description to go with it`

test('a live reply: three chips, and the label goes with them', () => {
  const r = steps(live)
  assert.deepEqual(r.next, ['Swap in the exact ship date', 'Get 3 more pitch variants with different tones', 'Draft a short product description to go with it'])
  assert.ok(r.body.endsWith("Jonah didn't look anything up."))
  assert.ok(!r.body.includes('Next steps'))
})
test('plain', () => assert.deepEqual(steps('Done.\n\n>> One\n>> Two').next, ['One', 'Two']))
test('the body keeps everything before the steps', () => assert.equal(steps('Done.\n\n>> One').body, 'Done.'))
test('bold', () => assert.deepEqual(steps('Done.\n**>> One**\n>> **Two**\n**>>Three**').next, ['One', 'Two', 'Three']))
test('italic', () => assert.deepEqual(steps('Done.\n*>> One*\n>> _Two_').next, ['One', 'Two']))
test('bulleted', () => assert.deepEqual(steps('Done.\n- >> One\n* >> Two\n+ >> Three').next, ['One', 'Two', 'Three']))
test('numbered', () => assert.deepEqual(steps('Done.\n1. >> One\n2) >> Two').next, ['One', 'Two']))
test('quoted', () => assert.deepEqual(steps('Done.\n> >> One\n> >> Two').next, ['One', 'Two']))
test('indented', () => assert.deepEqual(steps('Done.\n   >> One\n\t>> Two').next, ['One', 'Two']))
test('», no space too', () => assert.deepEqual(steps('Done.\n» One\n»Two').next, ['One', 'Two']))
test('escaped', () => assert.deepEqual(steps('Done.\n&gt;&gt; One\n\\>\\> Two').next, ['One', 'Two']))
test('blank lines between steps', () => assert.deepEqual(steps('Done.\n\n>> One\n\n>> Two\n\n').next, ['One', 'Two']))
test('inside a code fence: never parsed', () => {
  const text = 'Run this:\n```\n>> not a step\n>> nor this\n```'
  assert.deepEqual(nextSteps(text), { body: text, next: [] })
})
test('an unclosed fence runs to the end', () => assert.deepEqual(nextSteps('Code:\n```sh\n>> not a step').next, []))
test('steps after a closed fence still count', () => assert.deepEqual(steps('```\ncode\n```\n>> One').next, ['One']))
test('mid-message: not parsed', () => {
  const text = 'First part.\n>> looks like a step\nBut the reply goes on.'
  assert.deepEqual(nextSteps(text), { body: text, next: [] })
})
test('only the trailing run counts', () => {
  const r = nextSteps('Intro.\n>> early\nMiddle.\n>> One\n>> Two')
  assert.deepEqual(r.next, ['One', 'Two'])
  assert.equal(r.body, 'Intro.\n>> early\nMiddle.')
})
test('4+ steps: three chips, the rest plain text without the marker', () => {
  const r = steps('Done.\n>> One\n>> Two\n>> Three\n>> Four\n>> Five')
  assert.deepEqual(r.next, ['One', 'Two', 'Three'])
  assert.equal(r.body, 'Done.\n\nFour\nFive')
})
test('too long: plain text, never raw syntax', () => {
  const long = 'Compare every lamp under fifty dollars that ships this week and has a warm color temperature setting'
  const r = steps('Done.\n>> One\n**>> ' + long + '**')
  assert.deepEqual(r.next, ['One'])
  assert.ok(r.body.endsWith(long) && !r.body.includes('**'))
})
test('duplicates and spacing', () => assert.deepEqual(steps('Done.\n>>   One  \n>> one\n>> Two').next, ['One', 'Two']))
test('an empty marker is no step', () => assert.deepEqual(nextSteps('Done.\n>>').next, []))
test('CRLF line endings', () => {
  const r = steps('Done.\r\n\r\n>> One\r\n>> Two\r\n')
  assert.deepEqual(r.next, ['One', 'Two'])
  assert.equal(r.body, 'Done.')
})
test('a reply with no steps is unchanged', () => assert.deepEqual(nextSteps('Just an answer.'), { body: 'Just an answer.', next: [] }))
test('a quote that is not a step stays a quote', () => assert.deepEqual(nextSteps('He said:\n> Ship it').next, []))

// Real replies, recorded from live runs (Claude only so far: ChatGPT and Grok weren't run for Stage 6).
const recorded = JSON.parse(readFileSync(new URL('./recorded-replies.json', import.meta.url), 'utf8')) as { from: string; text: string; next: string[] }[]
for (const r of recorded) test('recorded: ' + r.from, () => assert.deepEqual(steps(r.text).next, r.next))
