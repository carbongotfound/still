---
name: Market watch
description: What changed in your market: launches, pricing and news.
when: Tracking a market or competitors
---

## When
The user wants to know what changed in their market or with their competitors over a period (a week by default).

## Inputs
- Your market, for the space and the competitors to watch. If it's empty, ask once with ask_user and save the answer there with update_knowledge.
- The period to cover.

## Steps
1. For each competitor, read_url their site, blog, changelog and pricing page.
2. web_search for news about each one from the period.
3. Keep only what changed in the period: launches, pricing, hires, funding, partnerships.
4. Note why each change matters to the user in one line.
5. Add lasting changes to Findings and any new competitor to Your market.

## Check
- Every item has a link and a date inside the period.
- Nothing is listed as new that was already in Findings.

## Deliverable
A list, newest first: the change, its date and link, and one line on why it matters. Then the one change most worth acting on.

## If it goes wrong
- Nothing changed for a competitor: say "no changes found", don't pad.
- A pricing page is behind a sign-in: say so instead of guessing the price.

## Limits
Only report changes you found on a page you read, with its date. Never guess a competitor's plans.
