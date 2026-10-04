# Still 1.6.22 verification

Checked on Windows x64 on 2026-10-04 against repository commit `53cdb2f` (1.6.20). Desktop checks use explicit QA builds, isolated disposable profiles, and local HTTP fixtures. The installed personal browser and its profile were left untouched.

## Changes

- A launch directed at an existing profile forwards its link before creating WPF or a WebView environment. The first instance listens before constructing the window. Links are queued rather than overwriting a single pending URL; stalled and oversized pipe requests are rejected.
- The shell and first page controllers initialize together. A launch URL does not load the previously active restored tab first. Browser registration runs after the window is shown.
- Managed assemblies stay inside the single-file executable rather than all being extracted at startup. The small interface files are embedded and materialized in a version-specific profile cache; reader/login scripts are read directly from resources. This follows [.NET single-file deployment guidance](https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/overview).
- Memory saver suspends eligible background tabs after one minute without destroying their WebView, reloading the document, or deleting browsing data. It protects playing media, capture streams, WebRTC, permissions, and downloads. Cross-origin iframe pages are conservatively kept awake. Timers stop on window close; retained completed screenshots are released.
- Only renderer processes whose associated frames all belong to sleeping tabs receive one working-set trim when suspension succeeds. Shared active, shell, extension, and unknown renderers are excluded. Resident RAM can decrease while private allocations remain available; waking can cause page faults. Savings depend on renderer sharing and active workload, consistent with [WebView2's process and memory model](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/performance).
- Completed download rows open their actual file on double-click. Filename double-clicks launch it once; keyboard/single-click filename activation remains available.
- Store CRX developer signatures and requested IDs are verified. Retaining the signed public key fixes extensions installed under an incorrect generated ID, which can break desktop native-host allowlists and other ID-dependent features. Popup and options pages have separate controls, including legacy manifest popup entries.

## Startup measurements

`startup.py --cold-bundle` ran sequentially with a fresh extraction directory and profile for each executable. Cycle zero is initial setup; cycles 1–3 reopen the same profile after quitting. Times include the app process startup and the local page/interface becoming usable.

| Measurement | Baseline | Changed |
|---|---:|---:|
| First visible window, fresh bundle/profile | 6.407 s | 3.469 s |
| First usable page/interface, fresh bundle/profile | 14.469 s | 13.485 s |
| Reopen usable page, cycle 1 | 6.625 s | 2.422 s |
| Reopen usable page, cycle 2 | 1.718 s | 1.578 s |
| Reopen usable page, cycle 3 | 3.562 s | 2.422 s |
| Running-instance link, all four cycles | 2.594 / 2.375 / 0.766 / 0.453 s | 2.140 / 0.484 / 2.625 / 0.343 s |

These are small samples on one machine, not guaranteed speedups. Running-link timing still has outliers, and fresh WebView profile setup remains expensive. Six simultaneous links were also checked for exactly-once delivery. Raw local results: `artifacts/startup-f71973ee64cc4d83b4a79a34f528a4a1/results.json`.

## Memory and state results

The final single-file QA build passed all twelve memory/session checks. Seven fixture tabs each allocate a 32 MiB JavaScript buffer; the restored tab remains unloaded. Measurements include Still and all its descendant engine processes.

| Process-tree memory | Loaded | After background idle |
|---|---:|---:|
| Resident working set | 791.4 MiB | 368.9 MiB |
| Private committed allocations | 878.6 MiB | 793.1 MiB |

Resident RAM decreased by about **53%** in this idle-page fixture; private committed memory decreased by about 10%. Waking preserved typed input/textarea drafts, the JavaScript marker, one original document load, pushed navigation history, cookies, and local storage. Session tabs saved on exit. Disabling memory saver resumed every loaded tab at its normal memory target.

A separate 75-second activity period confirmed that a background muted video/canvas stream and a WebRTC peer stayed awake. In an earlier combined media-and-idle workload, resident RAM decreased only from 868.3 to 856.0 MiB despite eligible tabs suspending. Active media/shared renderers are protected; the 53% figure must not be generalized to those workloads. Raw final local results: `artifacts/performance-f7440dc5e3014c2ab14c3920dc3c2a83/results.json`.

## Extension compatibility boundary

A Manifest V3 fixture verified its stable runtime ID, service-worker messaging, local extension storage, content scripts, real tab queries, and an actual round trip to a temporary registered native helper. Presence of APIs such as scripting/contextMenus/alarms was observed, but their full behavior was not independently exercised.

The official signed Cold Turkey 4.9.7 package loaded with ID `pganeibhckoanndahmnfggfoeofncnii` and reached its personal-data consent screen. Consent was not accepted, private/file permissions were not granted, and blocking rules were not modified. **Actual Cold Turkey blocking and private-window coverage are not verified.** [Cold Turkey's supported-browser list](https://getcoldturkey.com/support/system-requirements/) does not list Still, and its [Chrome instructions](https://getcoldturkey.com/support/extensions/chrome/) require additional permissions. An extension loading successfully does not establish publisher support or complete compatibility.

The final feature suite passed thirteen checks, including real download opening and the embedded reader/login scripts. Raw local results: `artifacts/features-ae45044701c14589ab42df3cfb15b285/results.json`.

Existing installed extensions and their stored data are kept. Correct store identity applies to new store installations; it does not automatically migrate an older copy with a generated ID. Export extension-specific settings before replacing an older copy. Popup pages currently open as tabs, so extensions expecting Chrome's toolbar-popup/current-tab behavior can still differ. Universal Chrome extension compatibility is not claimed.

## Build checks

The frontend's eight suggestion tests pass, TypeScript/Vite build passes, and lint has zero errors with six existing warnings. The package install reports six pre-existing high-severity dependency advisories; dependency upgrades were not included in this performance change.

Twenty-two native checks cover CRX RSA/ECDSA/legacy packages, the official downloaded package, tampering, malformed input, profile argument parsing, pipe deadlines, rejected requests, and immediate exactly-once link delivery. Production metadata checks verify that QA server/timing data is absent and all twelve embedded interface/script resources exactly match source. The installer uses the project version and a signature-verified Microsoft WebView bootstrapper.

Reproduction commands and profile/registry isolation details are in [the desktop test README](../tests/desktop/README.md). No QA executable, test profile, downloaded extension, or browsing data is included in the commit.
