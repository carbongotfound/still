---
name: Smoke test
description: Clicks through your main pages and lists what breaks.
when: Testing a site or a release
---

## When
The user wants a site or a release checked, or it's the weekly smoke test routine.

## Inputs
- The site's address, from Product and stack. If it's missing, ask once and save it there.
- The main paths to try, from Product and stack or the user.

## Steps
1. open_tab the site and visit the main pages.
2. Try the main paths like a careful new user: read the page, then click and type.
3. For anything broken or confusing, note the steps, what you expected and what happened.
4. Update Known bugs: add new ones and mark fixed ones as fixed.

## Check
- Each problem has steps someone else could repeat.
- Fixed bugs were actually retried, not assumed.

## Deliverable
A short list: what works, what's broken (with steps) and what's confusing. Then the one to fix first.

## If it goes wrong
- A page needs a sign-in: ask the user to sign in in the tab, or skip it and say so.
- The site is down: say so with the time, and try once more before reporting.

## Limits
Never submit forms that buy, send or delete. Say which paths you didn't test.
