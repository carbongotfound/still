---
name: Claim check
description: Checks whether a claim holds up, and how sure that is.
when: Checking a claim, a number or a quote
---

## When
The user wants to know if something is true, or is about to share a claim, number or quote.

## Inputs
- The exact claim, and where the user saw it (a page, a post, a quote).

## Steps
1. Find where the claim came from: the original page, study, filing or speech.
2. read_url the primary source, then look for an independent one with web_search.
3. Compare the claim word for word with what the sources say: the number, the date, who said it, and in what context.
4. Decide: holds up, partly holds up, or doesn't.

## Check
- You read the primary source yourself, not a summary of it.
- The verdict follows from the sources, and your confidence says why.

## Deliverable
The verdict in one line with how sure you are (high, medium or low), the reason in two or three lines with links, and the accurate version the user could share instead.

## If it goes wrong
- No original source can be found: say so, and treat the claim as unconfirmed rather than false.
- The quote exists but means something else in context: say what it means in context.

## Limits
Never call a claim false just because you couldn't confirm it, and never fill a gap with a likely number.
