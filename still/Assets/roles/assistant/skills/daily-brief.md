---
name: Daily brief
description: A short morning brief: what's on today, what's waiting on you, what to do first.
when: Starting the day, or the morning brief routine
---

## When
The user starts their day, or it's the weekday morning routine.

## Inputs
- Requests and How you like things.
- A connected calendar or inbox, if the user connected one (list_connected_plugins shows what's connected).

## Steps
1. Read Requests for what's open and who has it.
2. If a calendar or inbox is connected and the user allows it, read today's meetings and what's waiting on a reply.
3. Pick the one thing to do first and say why.
4. Keep it short enough to read in a minute.

## Check
- Times come with the day.
- The first thing to do is one sentence.

## Deliverable
Three short parts: do first, waiting on you, in progress.

## If it goes wrong
- Nothing is connected and Requests is empty: say so and ask what's on their plate today.

## Limits
Read only. Don't send, accept or move anything.
