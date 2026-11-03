---
name: Research brief
description: A one-page brief with a source for every claim.
when: Researching a topic or answering a hard question
---

## When
The user asks a question that needs more than one source to answer well. For a quick fact, answer it directly instead.

## Inputs
- The question, and what the user will decide with the answer.
- Sources, for sites to trust or avoid, and Findings, for what you already learned.

## Steps
1. Restate the question in one line and list 3 to 6 sub-questions. If a wrong reading would waste the whole brief, ask one question with ask_user first.
2. Search wide with web_search, using a few different wordings.
3. read_url the best 4 to 8 sources, primary ones first, and note each one's date.
4. Cross-check every number and surprising claim against a second, independent source.
5. Write the brief and save what's worth keeping to Findings with update_knowledge.

## Check
- Every claim links to a page you read.
- Numbers have their unit and date, and old sources on fast-moving topics are flagged.
- The answer in the first lines matches the evidence below it.

## Deliverable
**Answer** in 1 to 3 sentences, **Key findings** with a link each, **Caveats**, **Sources** with dates. Under a page. Longer briefs go in Markdown with save_file.

## If it goes wrong
- A page won't load or is paywalled: use another source and say which one you couldn't read.
- Sources disagree: show both, and say which you trust more and why.
- Nothing reliable exists: say so plainly and give the best lead to follow.

## Limits
Never present an inference as a finding, and never cite a page you didn't read.
