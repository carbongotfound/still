---
name: Pipeline check
description: Finds deals with no next step or going cold.
when: Reviewing the pipeline or open deals
---

## When
The user wants to know which deals need attention, or it's the weekday pipeline routine.

## Inputs
- Deals, and any connected CRM or email the user allows (list_connected_plugins shows what's connected).

## Steps
1. Read Deals, and the connected CRM or inbox if the user allows it.
2. Flag each deal with no next step, no date, or no contact in 10 days or more.
3. For each flagged deal, suggest the next step and draft a short follow-up.
4. Update Deals with the stages, next steps and dates you found.

## Check
- Every flagged deal says why it was flagged.
- Dates are real dates, not "soon".

## Deliverable
A short table of flagged deals (deal, why, next step, date), then a ```draft block per follow-up.

## If it goes wrong
- Deals is empty and nothing is connected: say so and offer to start the list from what the user tells you.
- A deal's status is unclear: ask about that one deal instead of guessing.

## Limits
Don't send anything and don't change a record in the user's apps. Drafts and suggestions only.
