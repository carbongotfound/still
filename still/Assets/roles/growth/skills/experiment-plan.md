---
name: Experiment plan
description: Small tests with one metric and a clear stop.
when: Planning a growth experiment or deciding what to test
---

## When
The user wants to test an idea, or asks what to try next to grow.

## Inputs
- Experiments, so nothing repeats a test already run.
- Your numbers, for the baseline each test would move.

## Steps
1. List the ideas, the user's and two or three of yours from the biggest known leak.
2. For each: the hypothesis, the one metric it moves, the baseline, the effort (small, medium, large) and the stop date.
3. Say what result would count as a win, before anything runs.
4. Rank by likely impact against effort and recommend one.
5. Add the plan to Experiments with update_knowledge.

## Check
- Every test has one metric, a baseline and a stop date.
- None repeats a test in Experiments without saying why.

## Deliverable
A small table of ideas ranked, then the recommended test written out: hypothesis, metric, baseline, what counts as a win, stop date.

## If it goes wrong
- No baseline exists: make measuring it the first step.
- Traffic is too low to tell: say so and suggest a qualitative test instead.

## Limits
Plans only. Launching anything live waits for the user's OK, and no result is called before the stop date.
