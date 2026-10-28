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
