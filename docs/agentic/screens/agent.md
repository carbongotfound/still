# The agent at work

`still/MainWindow.Ai.cs` (runs, the Library), `still/MainWindow.Agents.cs` (workers, the cursor, `save_file`),
`still-ui/src/AiSidebar.tsx` (the chat, running tasks) and `still-ui/src/Files.tsx` (file card, viewer).

## Runs

- Every chat runs on its own. `runs` holds one `ChatRun` per chat id: who drives it, when it started, its question and
  its queue. Start a second chat while the first works and both run at once.
- Each run is its own worker in the MCP server: Still starts the AI app with `--mcp --run <chatId>`, and every
  tool call carries that id. Take over, Hand back and Stop act on that run's tabs only.
- The AI's tabs are real tabs in the main window, marked with its companion. The chat stays in the sidebar.
- A message sent while a chat works waits as "Up next". "Send now" stops the run and sends it; X drops it.
- The runner in the toolbar ("2" with a spinner) lists every running chat with its time, answers `ask_user`
  questions in place, and shows chats with new replies. It opens over the page, so the page steps aside.

## In the page

- The AI's cursor glides to what it clicks or types into, with its name under it, in its companion's hue.
  It lives in a closed shadow root, and goes when the page navigates.
- The pill at the bottom says what it's doing: "Maya is working…", the last step, Take over, Open chat, Stop.

## Files

- `save_file` writes a CSV, TSV, Markdown, JSON or text file (up to 5 MB) to `library/<chatId>/` in the data
  folder. A CSV gets a BOM so Excel reads accents. Any other name or ending is refused.
- Saving the same name again in the same chat replaces the file, so the AI can fix a mistake without leaving a
  second copy. A new name next to an old file gets " (2)".
- The chat shows a card: the file's icon, name, kind, and "Show in folder". Open shows the viewer:
  beside the chat in a chat tab, or in a dialog anywhere else. CSV is a sortable grid with resizable columns;
  Markdown renders; JSON is pretty-printed. Copy all, Show in folder, Close.
- The Library page lists every saved file with its chat, a search box and a companion filter.
- The chat's details (the i button) list its files.

## Working folder

A companion can have a working folder (the editor's "Working folder"). Claude can then read and edit files there
(`--tools Read,Write,Edit,Glob,Grep --add-dir <folder> --permission-mode acceptEdits`). Other AI apps still help in
the browser only, and the editor says so.

## Tests

- `python tests/desktop/agentic.py <exe>`: a fake AI app on a local store. The laptops flow, two runs at once,
  per-run Take over and Stop, Up next and Send now, a question answered from the runner. Screens go to
  `docs/agentic/compare/`.
- `python tests/desktop/agentic.py <exe> --live`: the same laptops task through real Claude on Haiku. By hand only.
