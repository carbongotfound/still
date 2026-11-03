---
name: Voice match
description: Writes like you, from rules learned from your own posts.
when: Writing anything in the user's voice
---

## When
The user wants something written so it sounds like them.

## Inputs
- Your voice. If it's empty, two or three links to things the user wrote, or text they paste.

## Steps
1. read_url the samples, or read the pasted text.
2. Sum up the voice in five short rules: sentence length, words they use and avoid, humor, structure, how they end.
3. Save the rules to Your voice with update_knowledge.
4. Write the piece with those rules, then check the draft against each rule before showing it.
5. When the user edits a draft, note what changed in Your voice.

## Check
- The draft follows all five rules, and you can point to where.
- No phrase the user's samples would never use.

## Deliverable
The draft in a ```draft block. The first time, also the five rules, so the user can correct them.

## If it goes wrong
- Samples disagree with each other: ask which one sounds most like them now.
- No samples at all: write plainly and say the voice will improve once you've seen their writing.

## Limits
Never copy whole sentences from the samples into new pieces, and never claim the user said something they didn't.
