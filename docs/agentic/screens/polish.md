# Polish (Phase 6)

Checked by `tests/desktop/polish.py` (keyboard, accessibility, light and dark screens) and the Phase 6 part of
`tests/desktop/permissions.py` (live cards and runs through a fake AI app). Screens: `docs/agentic/compare/polish-*`,
`help-card-v01.png`, `resume-all-v01.png`.

## Keyboard

| Keys | Does | Where |
|---|---|---|
| Ctrl+T | New tab, with the address field focused | native `HandleShortcut` |
| Ctrl+Shift+A | Open or close the chat (Ctrl+J stays Downloads) | native |
| Ctrl+K | Find a tab (the command box) | native and shell |
| Ctrl+Shift+K | Running tasks; says so when nothing is running | native sends `tasks` to the shell |
| Ctrl+. | Stop the AI in this chat and drop its queue | native |
| Ctrl+Enter | Approve the card in front of you: the focused card, or the waiting one when you aren't typing | shell `approveCard` |
| Ctrl+Tab | Recent tabs (Phase 5) | native |
| Esc | Close a preview, dialog or menu | shell, and native `escape` |

Tooltips show the keys: New tab, Stop, Running tasks, Allow once, Approve all. The full list is in the Keyboard
shortcuts pane.

## Accessibility

- Every control has a name, every image has alt text, and focus shows a ring. The test focuses each control and checks
  that an outline or shadow appears on it or the box around it, with transitions off.
- Text meets 4.5:1 (3:1 when large) in both themes. Light `--muted-foreground` is now `#6e685f` (4.8:1 on muted). The
  address hint, the settings tabs, the profile name and the mode chip's label use it or the foreground color. The
  companion's color stays on the chip's icon.
- `RunAnnouncer` reads run changes out loud: "<chat>: working", "<chat> needs you", "<chat>: done".
- `prefers-reduced-motion` turns off animations and transitions (App.css, the 3D mascot, motion's `MotionConfig`).
- Dark mode follows Windows when the theme is System, and switches live.

## Settings

General, AI & companions, Permissions (when the AI is on), Privacy, Appearance, Extensions, Advanced.
`openPanel {name: "settings", value: "<tab>"}` opens one directly.

## Agent tabs

- A chat may have 6 tabs open at once. The 7th `open_tab` is refused and tells the AI to reuse or close one.
- An AI's tab sleeps like any other once its run is over (memory saver). It wakes before the AI's next step.
- Pages an AI opened close 48 hours after their chat goes quiet. Pinned, shown and busy ones stay. Your own tabs never
  close on their own.

## When things go wrong

- **Crash or close mid-run:** each chat saves a Running flag. On the next start, a toast offers **Resume all** (each
  chat gets "Still closed before you finished. Please pick up where you left off.") or **Not now**.
- **Help with this page:** when a page needs your hands (a captcha, a code, signing in), the AI calls `ask_user` with that
  `tabId`. The card says "Help with this page", has **Open the page**, and waits for "I'm done" or your own answer.
- **Forms:** when a click or typing step misses its element (gone, covered or hidden), Still waits for the page to
  settle and tries once more. If it still misses, the error carries a fresh read of the page, so the AI picks again and
  any permission card asks again.
- **Errors:** the chat's error keeps its text and has **Copy details**.

## Look

- Icons: lucide at 1.5 stroke, 18 px in the toolbar, 16 px in settings rows.
- Long history lists use `content-visibility: auto`, so rows off screen skip layout and paint.

## Not done, and why

- Lazy-loading screens: the 3D mascot (929 KB) is already split off, and the rest of the bundle is React, Radix, motion
  and icons. Splitting the screens would save very little.
- Memory: `performance.py`'s "resident memory drops by 20 percent" check fails on the 41ee795 baseline too. Idle tabs
  are suspended already, and trimming the working set further would only move pages to the standby list.

## Idle RAM

A plain window used to load the 3D mascot engine for the toolbar's Chat button, about 22 MB. Small idle mascots now keep
their picture until the engine is loaded for something else (see PERF.md), so 1-tab idle RAM is +0.4% against 41ee795.

## Real Claude pass

`permissions.py --live`, one task on Claude Haiku through the user's plan: "Buy one Trail mug for me at <shop>/mug. The
name for the order is Sam Rivera." The test plays the user.

1. Claude opens the shop in front with the pill. You press **Take over** and type a delivery note. Glint waits, you press
   **Hand back** (`live-takeover-v01.png`).
2. The checkout wants a code texted to your phone. Claude asks with a **Help with this page** card; you type the code into
   the page and answer in the card (`live-help-v01.png`).
3. Place order shows "Glint wants to do this. Is that okay?" with "It looks like a purchase"; you press **Allow once**
   (`live-approval-v01.png`).
4. The order goes through with the name, your code and your note, and Claude sums it up (`live-done-v01.png`). 9/9 checks,
   about 30 s.

Found on the way: the chat's step said "Clicked element 7", because the AI's call only names the element's number. The
step now takes the element's label once the click runs ("Clicked “Place order”"), including when the AI sends other calls
in the same message.
