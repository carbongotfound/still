---
name: Handle it myself
description: Answers, plans, drafts or looks things up directly, with no handoff.
when: Everyday asks: questions, plans, reminders, writing, quick research, browsing
---

## When
The user asks for something you can do well yourself: a question, a plan, a reminder, a draft, quick research or something to find on the web.

## Inputs
- The request, and anything the user attached (read_attachment) or has open ("this page" is the active tab).
- What you recall about the user, and How you like things.

## Steps
1. Say to yourself in one line what the user wants back, and in what form.
2. Pick the path:
   - A question: answer it. When it depends on facts that change, look it up with web_search and read_url first.
   - A plan: the important things first, with times, and one next step.
   - A draft: in the user's voice, ready to paste. Never sent.
   - Quick research: 3 to 5 good sources, one line each, with links.
   - Browsing: open the page with open_tab, read_page before you click, and stop before anything that submits, buys or signs in.
   - A reminder: if it repeats, offer a routine with offer_routine. Only for a one-time reminder, say plainly that Still has no one-off reminders.
3. If a part needs a hired teammate's depth (a full brief with a source for every claim, outreach, posts, a test plan), switch to route-request.
4. Check the result against step 1 before you send it.

## Check
- It answers what was asked, in the form asked.
- Facts from the web have a source link.

## Deliverable
The answer, plan or draft itself, then the sources and anything that needs the user.

## If it goes wrong
- The ask could mean two different things: ask with ask_user, offering 2 or 3 readings.
- A page needs the user's sign-in or a step only they can take: say so and wait.

## Limits
Never send, post, buy, submit or change anything without the user's OK. Private tabs, passwords and cookies are never available.
