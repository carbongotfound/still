import { test } from 'node:test'
import assert from 'node:assert/strict'
import { rankSuggestions } from '../src/suggestions.ts'
const now = Date.parse('2026-09-23T12:00:00Z')
const visits = [
  ...Array.from({length: 12}, (_, i) => ({title: 'ChatGPT conversation', url: `https://chatgpt.com/c/${i}`, at: '2026-09-22T12:00:00Z'})),
  {title: 'Chat room', url: 'https://chat.example.org/latest', at: '2026-09-23T11:59:00Z'},
]
test('frequent host outranks a single recent similar match', () => {
  const sites = rankSuggestions('chat', visits, [], false, now)
  assert.equal(sites[0].url, 'https://chatgpt.com/')
  assert.equal(sites[0].visits, 12)
  assert.equal(sites.length, 2)
})
test('exact host wins and URL prefixes work', () => assert.equal(rankSuggestions('https://www.chatgpt.com', visits, [], false, now)[0].host, 'chatgpt.com'))
test('private tabs never suggest normal history', () => assert.deepEqual(rankSuggestions('chat', visits, [], true, now), []))
test('bookmarks retain paths and match titles in private tabs', () => assert.equal(rankSuggestions('Guide', visits, [{title:'My Guide',url:'https://example.org/guide'}], true, now)[0].url, 'https://example.org/guide'))
test('unsafe schemes, credential URLs and invalid URLs are excluded', () => assert.deepEqual(rankSuggestions('evil', [], ['javascript:evil()', 'file:///evil', 'https://user:password@evil.test/', 'evil'].map(url=>({title:'evil',url}))), []))
test('clearing history removes its suggestions', () => assert.deepEqual(rankSuggestions('chat', [], []), []))
test('empty input returns no suggestions', () => assert.deepEqual(rankSuggestions('  ', visits, []), []))
test('large history stays bounded to six suggestions', () => assert.equal(rankSuggestions('site', Array.from({length:2000}, (_,i)=>({title:'site',url:`https://site${i}.example/`})), []).length, 6))
