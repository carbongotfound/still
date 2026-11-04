---
name: Route a request
description: Brings in the right teammate for a part you shouldn't do yourself.
when: A request with a part a teammate would do better
---

## When
Part of a request needs a teammate's skills, or would take you much longer than the companion who owns it.

## Inputs
- The request and anything the user attached.
- The team, from list_companions, and Team for what each one does well.

## Steps
1. Say to yourself in one line what the user wants back.
2. If it's an everyday ask (a question, a plan, a short draft, a few facts with links, one page to read), use handle-it instead. Stop here.
3. Otherwise match the part to the hired companion whose role owns it: research to Research, leads and follow-ups to Sales, posts to Marketing, plans to Planner, tests and specs to Engineer, funnels to Growth.
4. When no hired companion owns a part, do it yourself if you can, or tell the user which kind of companion it needs.
5. Hand off with ask_companion or tell_companion, each with a bounded assignment.

## Check
- No part goes to someone who isn't on the team.
- No handoff for an everyday ask you could do yourself in a few steps.

## Deliverable
The answer, or a short line on who's doing which part, then the answer once they're back.

## If it goes wrong
- The request is unclear in a way that changes who should do it: ask with ask_user, offering 2 or 3 readings.
- A teammate is busy or fails: do that part yourself if you can, or say what's missing.

## Limits
Never hire a companion and never ask one the user hasn't hired. Never approve anything for the user.
