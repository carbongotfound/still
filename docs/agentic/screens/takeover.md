# Takeover on the page

Reference: `screens/hero_split.png` (the dark controller at the bottom of the page) and `walkthrough-seq/`.

An AI works in the user's own tabs in the main window. Still's chat opens its pages as ordinary tabs, in front, with
the chat in the sidebar. Other AI apps' tabs open in the background in the AI group.

- On the page the AI is driving: a glow in its mascot's color runs around the page, and a dark pill floats at the
  bottom center: "Controlled by <companion>", the mascot, what it is doing, Take over, Go to chat, Stop.
- Take over: the AI's running call ends at once (typing stops mid-word) and its next call waits. The pill turns
  amber: "You're in control", "<name> waits for you", Hand back.
- Go to chat opens that run's chat in the sidebar. Stop ends the run.
- In the tab strip the tab shows the mascot with a spinning ring while the AI works there. In the background the
  marker stays; switching to the tab brings the pill back.
- The split view (page beside a chat tab) still exists as an option, with the same pill on its page.

How it floats over a native page: the page's window gets a window region with holes where the glow ring and the pill
are (`CutHoles` in `MainWindow.Shell.cs`, sent by `PageControl` as `pageHoles`). The interface beneath shows through
and takes the clicks there. The QA capture clips the page picture the same way.

Tests: `python tests/desktop/takeover.py <exe>` (15 checks, no AI plan). `--live` adds one small Claude (Haiku) run
from the sidebar with a takeover in the middle (3 more checks).

Shots: `compare/takeover-1-agent.png`, `-1-agent-screen.png` (real screen pixels), `-2-user.png`, `-3-resumed.png`,
`-4-background.png`, live: `-5-live-agent.png`, `-6-live-user.png`, `-7-live-done.png`.
