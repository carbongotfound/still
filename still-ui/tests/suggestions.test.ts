import { test } from 'node:test'
import assert from 'node:assert/strict'
import { homeIdeas, rankSuggestions } from '../src/suggestions.ts'
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
test('a site you keep picking for the same letters comes first', () => {
  const sites = [{title: 'Maps', url: 'https://maps.example/', at: '2026-09-23T11:00:00Z'}, ...Array.from({length: 9}, () => ({title: 'Mail', url: 'https://mail.example/', at: '2026-09-23T11:00:00Z'}))]
  assert.equal(rankSuggestions('ma', sites, [], false, now)[0].url, 'https://mail.example/')
  const picks = [{typed: 'ma', url: 'https://maps.example/', count: 2}]
  assert.equal(rankSuggestions('ma', sites, [], false, now, picks)[0].url, 'https://maps.example/')
  assert.equal(rankSuggestions('map', sites, [], false, now, picks)[0].url, 'https://maps.example/')
  assert.equal(rankSuggestions('mai', sites, [], false, now, picks)[0].url, 'https://mail.example/')
})
test('private tabs ignore learned picks', () => assert.deepEqual(rankSuggestions('ma', [], [], true, now, [{typed: 'ma', url: 'https://maps.example/', count: 5}]), []))

// "Try one of these" on the new tab.
const tab = (id: string, title: string, url: string, more = {}) => ({id, title, url, ...more})
test('ideas never use a private tab, its title or its address', () => {
  const tabs = [tab('p', 'Secret bank statement', 'https://bank.example/statement', {isPrivate: true}), tab('n', 'Quarterly plan', 'https://docs.example/plan')]
  const ideas = homeIdeas({name: 'Maya', tabs})
  assert.deepEqual(ideas.map(i => i.label), ['Sum up Quarterly plan'])
  assert.ok(!JSON.stringify(ideas).includes('bank'))
  assert.deepEqual(homeIdeas({name: 'Maya', tabs: tabs.slice(0, 1)}), [])
})
test('ideas skip the page you are on, chats, non-web and loading tabs', () => {
  const tabs = [tab('home', 'New tab', 'https://still.home/'), tab('c', 'Chat', 'https://x.example/', {chatId: 'c1'}), tab('s', 'Settings', 'still://settings'), tab('f', 'Notes', 'file:///C:/notes.txt'), tab('l', 'New tab', 'https://slow.example/', {loading: true})]
  assert.deepEqual(homeIdeas({name: 'Maya', tabs, activeId: 'home'}), [])
})
test('no context, no ideas: nothing beats filler', () => {
  assert.deepEqual(homeIdeas({name: 'Pip'}), [])
  assert.deepEqual(homeIdeas({name: 'Pip', asks: [['Do a thing', 'Do it']]}), []) // a role's tasks need a role
  assert.deepEqual(homeIdeas({name: 'Pip', apps: [{slug: 'someapp', name: 'Some App'}]}), []) // an app Still has no task for
})
test('ideas come strongest first, three at most, each with why', () => {
  const ideas = homeIdeas({name: 'Jonah', role: 'Sales', asks: [['Prep me for a call', 'p1']], fits: [['Email and inbox', 'What needs a reply?', 'p2']], uses: ['hubspot'],
    memory: [{text: 'Old launch.', kind: 'project', at: '2026-01-01'}, {text: 'Closing the Acme renewal by Friday.', kind: 'project', at: '2026-10-01'}, {text: 'Likes short answers.', kind: 'preference', at: '2026-10-02'}],
    apps: [{slug: 'gmail', name: 'Gmail'}, {slug: 'hubspot', name: 'HubSpot'}], tabs: [tab('n', 'Acme pricing', 'https://acme.example/pricing')]})
  assert.deepEqual(ideas.map(i => [i.kind, i.label, i.why]), [
    ['project', 'Next step: Closing the Acme renewal by Friday', "From Jonah's memory"],
    ['app', 'Which deals need a nudge?', 'HubSpot is connected'],
    ['tab', 'Sum up Acme pricing', 'Open in your tabs']])
  assert.match(ideas[0].prompt, /Closing the Acme renewal by Friday/)
  assert.deepEqual(homeIdeas({name: 'Jonah', role: 'Sales', asks: [['Prep me for a call', 'p1'], ['What needs a reply?', 'p3']], fits: [['Email and inbox', 'What needs a reply?', 'p2']]}).map(i => [i.label, i.why]),
    [['What needs a reply?', 'You work on email and inbox'], ['Prep me for a call', "Jonah's role: Sales"]])
})
