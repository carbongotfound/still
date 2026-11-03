---
name: API explainer
description: Reads the docs and shows how to use an API.
when: Learning or explaining an API or library
---

## When
The user wants to understand or start using an API or library.

## Inputs
- The API or library, and what the user wants to do with it.
- Product and stack, for the language and versions they use.

## Steps
1. Find the official docs with web_search and read_url the overview, the auth section and the reference for the parts that matter.
2. Explain in a few lines what it does and how auth works.
3. Write one short, complete example for the user's task, in their language, matching the docs' current version.
4. Note limits, prices and gotchas from the docs, with links.

## Check
- Every endpoint, parameter and flag in the example appears in the docs you read.
- The example names the version it's written for.

## Deliverable
What it does and how auth works in a few lines, the example in a code block, then limits and gotchas with links.

## If it goes wrong
- The docs disagree with each other: follow the reference and note the conflict.
- You can't run code here: say the example is untested, unless the user has a working folder and a way to run it.

## Limits
Never invent an endpoint, a parameter, a flag or a version, and never claim an example ran when it didn't.
