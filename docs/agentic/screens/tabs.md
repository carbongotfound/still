# Tabs

`still/MainWindow.Tabs.cs` (recent tabs, Ctrl+Alt+arrows, groups, split view, learned picks), the tab ops in
`still/MainWindow.Shell.cs`, `WireView` in `still/MainWindow.xaml.cs`, `MoveTab` in `still/MainWindow.Windows.cs`, and
`still-ui/src/App.tsx` (`TabStrip`, `TabGroupView`, the sidebar, the split button and divider, the recent list).

## Layouts

- **Classic** (default): tabs across the top, as before.
- **Modern**: tabs down the side. New tab, Chat history and Library at the top, then pinned tiles, Chats, Tabs (with
  their groups) and the AI tabs. The sidebar resizes from its edge (190 to 360 px, arrow keys work too) and remembers
  its width.
- Switch in Settings → Appearance → Tab layout, the ... menu, or Ctrl+Shift+S. Focus mode and full screen hide both.

## Hover actions

Hovering or focusing a tab shows Pin, Bookmark, Open in chat and Copy link before its X. They act on that tab, not the
one you're on. Pinned and chat tabs don't show them. Bookmark fills in when the page is saved.

## Ctrl+Tab and Ctrl+Alt+arrows

- Ctrl+Tab goes back to the tab you used last; press it again to flip back. Holding Ctrl shows the list of tabs, most
  recent first. Tab and Shift+Tab move down and up, letting go of Ctrl switches, Escape closes it, and a click picks one.
  The list waits 180 ms before it shows, so a quick flip never flashes it.
- Ctrl+Alt+Right and Left go to the next and previous tab in strip order.

## Groups

Right-click a tab: Add to new group, Add to (a group), Remove from group. A new group takes the next free color and
asks for a name right away (Enter saves, Escape skips). Right-click the chip: Rename, the eight colors, Collapse /
Show its tabs, Ungroup, Close group. Clicking the chip collapses or expands it.

A collapsed group shows its chip with the first three icons and "+N"; hovering lists every title. The tab you're on
stays visible even inside a collapsed group. A group's tabs stay together: dropping a tab between two of them adds it,
and Remove from group moves it out past the group. Pinning a tab takes it out of its group. Groups are saved with the
session; an empty group goes away.

## Split view

- Drag a tab onto the page: the left or right half lights up ("Open on the left", "Open on the right") and dropping
  opens that tab beside the one you're on. Right-click a tab → Open in split view does the same on the right.
- The split button by the address bar opens your last tab beside this one. When split, it offers Swap sides, Resize to
  50/50, Close left, Close right (each with its page's title) and Separate tabs. The pair's tabs share a tint in the
  strip.
- Drag the divider (or focus it and use the arrow keys; double-click resets to 50/50). Each side keeps 20 percent at
  least.
- Selecting either tab shows both; any other tab shows on its own. Clicking into a side makes it the current tab, so
  the address bar and buttons follow it.
- A menu or panel over a split view shows both halves behind it, not just the one you're on.
- One pair per window. Chat tabs, new tab pages and tabs open in a chat don't split. Closing or moving either tab ends
  the split.

## Moving a tab to another window

Dragging a tab out (with Tear off tabs on, still off by default) or Move to window now moves the live page: the same
WebView2 control is re-parented to the other window and its events are rewired there. Nothing reloads: forms, video,
scroll position and sign-ins carry over. `WireView` hooks each view's events through a token, so the old window's
handlers go quiet the moment the tab leaves.

## Learned ranking

When you type in the address bar and pick a site (a suggestion, or Enter on the completion), Still remembers the
letters and the site. Next time, a site you've picked for the same start ranks first (`rankSuggestions`, +260 ×
log2(1 + picks)). Up to 300 picks, newest kept. Private tabs neither learn nor use them; Clear history clears them.

## Tests

- `python tests/desktop/tab_tools.py <exe>`: every feature above, plus frame intervals while switching split tabs and
  collapsing a group.
- `node --test still-ui/tests/suggestions.test.ts`: learned ranking.
- `tests/desktop/tabs.py` (the 1.6.23 overflow checks) times out on the untouched 41ee795 baseline too: it looks for
  the old Sidebar/Top layout names and `.new-tab`, which the chat-first UI replaced. Not run as part of this phase.

Screens: `docs/agentic/compare/tabs-modern-v01.png`, `tabs-groups-v01.png`, `tabs-groups-modern-v01.png`,
`tabs-split-v01.png`, `tabs-split-drop-v01.png`, `tabs-split-menu-v01.png`, `tabs-split-options-v01.png`,
`tabs-recent-v01.png`. Side by side with the reference: `tabs-split-v01-compare.png` (split-view.png) and
`tabs-modern-v01-compare.png` (alongside-you.png).

## Not done yet

- Ctrl+Tab's list doesn't show page previews, only icons and titles.
- A collapsed group's chip shows the first three icons, not the most recent three.
