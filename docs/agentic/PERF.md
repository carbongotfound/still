# Performance baseline (Phase 0)

Build: untouched commit 41ee795, QA publish (`artifacts/baseline-41ee795`, self-contained, `-p:StillQa=true`).
Machine: this PC, Windows 11, 2026-10-28. Test windows on the second monitor, muted, fresh profile per launch, pages from a loopback server.
Script: `python tests/desktop/baseline.py <Still.exe> 3` (3 runs; medians below) plus `python tests/desktop/performance.py <Still.exe> --baseline`.

| Metric | Median | Runs |
|---|---|---|
| Cold start (launch to first tab loaded) | 19.625 s | 16.125, 21.766, 19.625 |
| Idle RAM, 1 tab (working set of Still + WebView2 tree, after 75 s idle) | 634.3 MB | 641.8, 634.3, 634.0 |
| Idle RAM, 10 tabs (all visited once, memory saver on, after 75 s idle) | 848.6 MB | 843.3, 848.6, 851.4 |
| Tab switch (request to strip showing the new tab, shell side) | 112.0 ms (p90 129.2 ms) | 60 switches |

`performance.py --baseline` (one run, 10-tab session): loaded 878.9 MB working / 1053.1 MB private (15 processes); idle 837.7 MB working / 1021.2 MB private (14 processes). Every check passed.

**Caveat.** These runs overlapped with a .NET compile and a background code-reading agent, so cold start in particular is inflated and noisy (16 to 22 s). Phase 6 re-runs this baseline build and the new build back to back on a quiet machine with the same script, and compares those two sets. Treat the numbers here as a first reading, not the bar.

## After each phase
| Phase | Cold start | Idle RAM 1 / 10 tabs | Tab switch | Notes |
|---|---|---|---|---|
| 0 (baseline) | 19.625 s | 634.3 / 848.6 MB | 112.0 ms | noisy, see caveat |
| 2 (87409da) | 15.187 s | 682.9 / 858.8 MB | 51.4 ms | 1-tab idle RAM +7.7% over the first reading; Phase 6 re-measures both builds back to back |
| 3 (c713293) | 14.485 s | 679.4 / 850.7 MB | 51.1 ms | flat against Phase 2 |
| 4 | 6.625 s | 684.1 / 869.5 MB | 53.3 ms | RAM and switch flat (+0.7% / +2.2%, +4%). Cold start swings with machine load: an earlier run of the same build gave 16.45 s while a compile ran |
| 5 | 14.641 s | 673.8 / 804.2 MB | 74.4 ms | Same day, Phase 4 rebuilt and run alternately with Phase 5: switch 65 and 91 ms (Phase 4) vs 91 and 90 ms (Phase 5), 1-tab RAM 662 and 666 vs 671 and 665 MB, cold start 7 to 16 s for both. No change traceable to Phase 5; the machine was noisier than for Phase 4's row. Split view and group collapse frames: p95 8.5 ms |
| 6 | 13.43 s | 624.4 / 768.9 MB | 64.8 ms | Measured back to back against 41ee795, below. Within 5% on every metric |


## Phase 6: this build against 41ee795, back to back

Same machine and day, nothing else running, test windows on the second monitor, fresh profile per launch.
`baseline.py <exe> 1` alternated 4 rounds (baseline, then Phase 6), then a cold-start-only probe alternated 8 more
rounds (the order flipped each round). Medians:

| Metric | 41ee795 | Phase 6 | Change |
|---|---|---|---|
| Cold start, all 12 launches each | 13.95 s | 13.43 s | -3.7% |
| Cold start, `baseline.py` rounds only (4 each) | 9.26 s | 12.60 s | +36%, reversed in the 8-round probe (15.82 vs 14.78 s) |
| Idle RAM, 1 tab | 595.4 MB | 624.4 MB | +4.9% |
| Idle RAM, 10 tabs | 741.2 MB | 768.9 MB | +3.7% |
| Tab switch (80 each) | 70.3 ms (p90 88.9) | 64.8 ms (p90 76.5) | -7.8% |

Single cold starts run from 5.6 to 18.4 s for both builds. Still's own stages put almost all of it, and almost all the
swing, in `shell-ready`: the interface's first paint in a new WebView2 profile, 8 to 16 s for both. Everything before
it is usually under 5 s (one baseline launch took 7.8 s to create its controllers). 1-tab idle RAM is the closest to the limit, at +4.9%. It has crept up a little in each phase (the
chat, companions, mascots and permissions all live in the shell), so it's the number to watch.

`performance.py` without `--baseline` fails "Resident memory drops by at least 20 percent" on Phases 2 and 3, and on the
untouched baseline build too (loaded 906.6 MB, idle 889.1 MB working set). It's an older check, not a regression from
this work. Phase 6: still fails on both builds. Idle background tabs are suspended (that check passes), and trimming
working sets further would only move pages to the standby list, so it stays as is.
