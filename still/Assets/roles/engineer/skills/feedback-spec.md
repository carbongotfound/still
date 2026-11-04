---
name: Spec from feedback
description: Groups feedback into themes and writes a spec.
when: Turning feedback or a request into a spec
---

## When
The user has feedback, requests or a problem to turn into a spec.

## Inputs
- The feedback: pasted, in a file, or on pages the user points to.
- Product and stack, for what exists today.

## Steps
1. Group the feedback into themes and count how often each comes up.
2. Pick the top theme, or the one the user names.
3. Write the spec: the problem, who has it, the change, and what's out of scope.
4. Add acceptance checks anyone can test, one per line.
5. List open questions at the end.

## Check
- Every theme's count matches the feedback you read.
- Each acceptance check could pass or fail without debate.

## Deliverable
The themes with counts, then the spec in Markdown under a page, saved with save_file.

## If it goes wrong
- The feedback is too thin to see a theme: say so and suggest what to ask users.
- Two themes conflict: spec the bigger one and note the conflict as an open question.

## Limits
Quote feedback only as written. Never add a theme or a count the feedback doesn't support.
