# Still for Mac

Still for Mac runs the same interface as Windows on Apple's WebKit, in a native AppKit window. It needs macOS 12 or later and runs natively on Apple silicon and Intel Macs.

## Install

1. Open **Still-&lt;version&gt;.dmg** and drag **Still** onto **Applications**.
2. Still isn't notarized yet, so macOS asks once the first time you open it:
   - Right-click Still in Applications and choose **Open**, then **Open** again.
   - If macOS only offers **Done** or **Move to Trash** (macOS 15 and later), choose **Done**, go to **System Settings > Privacy & Security**, scroll to the message about Still and click **Open Anyway**.

After that, Still opens like any other app.

## Connect your AI

MCP and the command line work just as they do on Windows: the same tool names, the same approval prompts and the same safety rules. Your AI never sees private tabs, passwords or cookies, and it asks you before it submits a form or buys anything.

Keep Still open, then add it to your AI app. In Claude Code:

```sh
claude mcp add still -- /Applications/Still.app/Contents/MacOS/Still --mcp
```

In Claude Desktop, Cursor or another MCP app, add this to its MCP settings:

```json
{ "mcpServers": { "still": { "command": "/Applications/Still.app/Contents/MacOS/Still", "args": ["--mcp"] } } }
```

From a terminal or a script, call a tool directly. Say who you are with `as=`, so Still can show you who is using it:

```sh
still=/Applications/Still.app/Contents/MacOS/Still
"$still" --cli open_tab as=Claude url=example.com
"$still" --cli read_page as=Claude
"$still" --cli click as=Claude id=7
"$still" --cli help        # every tool
```

## Where your data lives

- `~/Library/Application Support/Still`: your profile, with bookmarks, history, settings, your AI chats and companions, and `agent.sock`, the private socket MCP and the command line talk through.
- `~/Library/WebKit/com.carbongotfound.still` and `~/Library/Caches/com.carbongotfound.still`: website data (cookies, site storage) and caches.

To remove Still completely, quit it, move it to the Trash and delete those folders.

## Build from source

On a Mac with Xcode 15 or newer, from the repository:

```sh
sh mac/build.sh            # mac/build/Still.app, Still-<version>.dmg and Still-mac.zip (universal)
ARCH=arm64 sh mac/build.sh # one architecture, faster
```

The build is ad-hoc signed, so the first launch asks the same way as above. The shell, the page scripts and the blocklist come straight from the Windows sources (`still/`), so both apps stay in step.

## Tests

`QA=1 sh mac/build.sh` makes a test build in `mac/build/qa/` with the QA channel: a private socket in the test profile (`qa-pipe.txt` holds its path) that the desktop tests use in place of the Windows pipe. It has its own bundle id, so it never touches your real data. Never hand it to anyone.

```sh
sh mac/test.sh             # builds the test app, runs every Mac suite, prints a table
sh mac/test.sh polish      # just one suite
python3 tests/desktop/baseline.py mac/build/qa/Still.app/Contents/MacOS/Still 1   # start time, idle memory, tab switching
```

Run them while you're logged in to the Mac (in Terminal or over SSH): they open real Still windows. Logs go to `artifacts/mac-test/`. `baseline.py` measures memory as the physical footprint (Activity Monitor's Memory column) of Still plus the WebKit helpers macOS counts as Still's.
