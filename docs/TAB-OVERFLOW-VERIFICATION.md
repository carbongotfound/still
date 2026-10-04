# Still 1.6.24 inline tab controls

The New tab button is back immediately after the tabs, inside the scrolling list in both layouts. Version 1.6.23 kept it outside the list, which changed the original appearance unnecessarily. The lists retain their overflow handling. Selecting the last tab or creating a new one reveals both that tab and the inline button; resizing a short window also updates their visibility. The top list accepts vertical mouse-wheel scrolling as horizontal scrolling.

The updated isolated-profile desktop check passed 41 assertions: inline placement with three tabs in both layouts, 27 trusted pointer clicks through 25 sidebar tabs and 30 top tabs, shrinking the shell from 500 to 340 pixels, reaching the inline button by mouse wheel from the first tab, selecting the first and last tabs, Ctrl T creating tab 31, no interface errors, and all 31 tabs saved on exit. Results: `artifacts/tabs-c296ad56354c4a72913771b1c6bab61b/results.json`.

Frontend lint passed with zero errors and the same six existing warnings; all eight suggestion tests and the TypeScript/Vite build passed. The QA profile is separate from the installed browser's data.

## Previous 1.6.23 fix

The New tab control was inside the scrolling tab list. With ten tabs in a short window, it was clipped below the sidebar; the top layout also placed its plus button past the horizontal viewport. Native tab creation had no ten-tab cap.

The sidebar New tab button now stays below the scroll area, and the top plus button stays beside it. Tab lists scroll independently; selecting or adding a tab reveals it using layout offsets that are unaffected by entrance animations. Window controls stay outside the scrolling list.

`tests/desktop/tabs.py` uses an isolated QA profile with ten initial tabs and a 500-pixel-high shell. The old build reproduced inaccessible controls in both layouts. The changed build passed 27 checks: twenty trusted pointer clicks, 25 sidebar tabs, 30 top-layout tabs, first/last selection in both layouts, Ctrl T creating tab 31, no interface errors, and all 31 tabs saved on exit.

Local reproduction results: `artifacts/tabs-bdf2a5ec1b5244f891f2db332f34056e/results.json`. Passing regression results: `artifacts/tabs-b5ca5c856ed64a869de3d242f0591979/results.json`. Test profiles and results are ignored and never committed.

The eight suggestion tests, frontend lint (zero errors; six existing warnings), and TypeScript/Vite build also passed. Production packaging is separately checked for embedded content matching source and absence of QA automation.
