---
name: Project checklist
description: Turns a project into steps with owners and dates.
when: Planning a project or breaking work down
---

## When
The user has a project to plan or a big piece of work to break down.

## Inputs
- The goal and the deadline. Ask with ask_user only if neither is clear from the chat.
- Who's involved, from People or the user.

## Steps
1. Write the goal as an outcome you could check off.
2. Break the work into steps of a day or less, each with an owner and a date.
3. Mark what blocks what, and the first step to take today.
4. Save the checklist in Markdown with save_file, and add the project to Priorities.

## Check
- Dates fit before the deadline, with blocked steps after what blocks them.
- Every step has one owner.

## Deliverable
The checklist file, and in the chat: the first step for today and the riskiest step.

## If it goes wrong
- The deadline doesn't fit the work: say so and show what to cut or move.
- Owners are unknown: put the user and mark the step to reassign.

## Limits
Never assign work to someone or message them yourself. The plan is a suggestion until the user agrees.
