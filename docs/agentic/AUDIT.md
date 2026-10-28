# Still audit (Phase 0)

Date: 2026-10-28. Version 1.8.0 (`still/Still.csproj:8`).

Method: code reading only. Nothing was built or run. Every `file:line` below was checked in the source. "Not verified" means I could not confirm it from code alone. Paths are relative to the repo root.

**Snapshot.** This describes the code at commit 41ee795, before any agentic work. Phase 1 started while it was being written (adapters in `still/Agents/`, ChatGPT renamed from "codex"), so line refs in `MainWindow.Ai.cs`, `McpServer.cs`, `Models.cs` and `MainWindow.xaml.cs` may have moved since.

## 1. Process model

**One process per profile.**

- `Program.Main` runs first (`still/Program.cs:10-33`). For a normal launch it resolves the profile. If that profile is already running, it forwards the URL over a pipe and exits without starting WPF (`still/Program.cs:13-23`).
- The instance name is `Local\Still-` plus a SHA-256 of the lowercased profile folder (`still/App.xaml.cs:22`). A named mutex with that name marks a running profile (`still/App.xaml.cs:45`). A second launch forwards its link, or shows "Still is already open. Look for it in your taskbar." (`still/App.xaml.cs:46-50`).
- `--cli` (must be the first argument) and `--mcp` run inside the WPF app object but open no window (`still/App.xaml.cs:43-44`).

**Data locations.**

| Value | Source | Default | Ref |
|---|---|---|---|
| `App.DataRoot` | `--profile <folder>` | `%LOCALAPPDATA%\Still` | `still/App.xaml.cs:27` |
| `App.ProfileHome` | `--profiles-root <folder>` | DataRoot | `still/App.xaml.cs:28-29` |
| DataRoot without `--profile` | launch profile's folder | | `still/App.xaml.cs:30` |
| Profile list | `ProfileHome\profiles.json`, `launch-profile.txt` | | `still/ProfileCatalog.cs:11-12` |
| Profile folder | default = ProfileHome, others `ProfileHome\Profiles\<id>` | | `still/ProfileCatalog.cs:15` |
| WebView2 data | `DataRoot\WebView`, profile "Default"; private tabs use a per-run `Private<guid>` profile | | `still/MainWindow.xaml.cs:304`, `still/MainWindow.Windows.cs:16` |

- At most 30 profiles (`still/ProfileCatalog.cs:80`). A temp window reports its name as "Temporary" (`still/ProfileCatalog.cs:75`).
- Several windows share one process. An incognito window lives in the same process and makes every tab in it private (`still/MainWindow.Windows.cs:23`, `still/MainWindow.xaml.cs:205`).
- Errors go to `DataRoot\errors.log` (`still/App.xaml.cs:93`). If the WebView2 engine crashes, Still relaunches itself with `--recovered` (`still/App.xaml.cs:98-116`). A temp profile folder is deleted when its window exits (`still/App.xaml.cs:121-122`).

**Named pipes.** All use `PipeOptions.CurrentUserOnly`.

| Pipe | Name | Purpose | Ref |
|---|---|---|---|
| Links | `Still-<hash>-open` | URLs from a second launch | `still/BrowserRegistration.cs:74,91,108` |
| Launcher | `Still-links-<user>` | StillOpen.exe links; only without `--profile` and not in QA | `still/BrowserRegistration.cs:18,99`, `still/App.xaml.cs:58` |
| Agent | `Still-<hash>-agent` | every MCP and CLI tool call; unlimited instances; one JSON line in, one out | `still/MainWindow.Agents.cs:33-56` |
| QA | `StillQa-<pid>` | test automation, QA builds only | `still/MainWindow.Qa.cs:12-13` |

**Shell WebView (the React UI).**

- Its own WebView2 profile "Shell" under `DataRoot\WebView` (`still/MainWindow.Shell.cs:51,62`). Served from the virtual host `still.internal` with `DenyCors` (`still/MainWindow.Shell.cs:71`). DevTools only in QA (`still/MainWindow.Shell.cs:67`).
- UI to C#: `send(op, data)` calls `chrome.webview.postMessage` (`still-ui/src/App.tsx:55`). C# accepts a message only if it comes from `https://still.internal/index.html` and is under 64 KB (`still/MainWindow.Shell.cs:76-77`). The op switch is `still/MainWindow.Shell.cs:85-185`. Every op ends with `ShellPublish()` (`still/MainWindow.Shell.cs:186`).
- C# to UI: `ShellSend` posts JSON (`still/MainWindow.Shell.cs:192-195`). `ShellPublish` batches a full `kind:"state"` snapshot (`still/MainWindow.Shell.cs:196-216`). `ShellOpen` sends `kind:"panel"` (`still/MainWindow.Shell.cs:217-225`). `PublishAi` sends `kind:"ai"` (`still/MainWindow.Ai.cs:127`). `PublishBrowserTools` sends `kind:"tools"` (`still/MainWindow.BrowserTools.cs:45-71`).
- The UI listens for `state`, `ai`, `tools`, `panel`, `toast`, `snapshot`, `upload`, `tabArrived` and `escape` (`still-ui/src/App.tsx:280-296`).

**Shell ops (`still/MainWindow.Shell.cs:85-185`).**

| Group | Ops |
|---|---|
| Tabs and pages | ready, bounds, overlay, openPanel, navigate, new, select, closeTab, pin, duplicate, sleep, mute, tearOff, moveTab, reorder, back, forward, reload, zoom, bookmark, reader, hide, unhide, pip, find, reopen, focus, panel, drag |
| Answers | uploadAnswer, permissionAnswer, dialogAnswer |
| Agents | agentAnswer (110), agentStop (111), agentTakeOver (112) |
| Settings | siteBlocking (128-129), preference (130-142), startup, startupSettings, defaultBrowser, welcomeDone |
| Data | bookmarkMove, removeBookmark, removeHistory, clearHistory, clearCookies, importBookmarks, exportBookmarks |
| Downloads and updates | chooseDownloads, downloadsFolder, showDownload, openDownload, cancelDownload, openUpdate, releaseNotes, checkUpdate |
| Window | incognitoWindow, copyText, fullscreen, exitFullscreen, maximize, minimize, closeWindow |
| AI | all `ai*`, `chat*` and `companion*` ops go to `HandleAi` (183) |
| Everything else | `HandleBrowserTool` (184): profiles, import, passwords, cookies, extensions, security |

**QA pipe.** `MainWindow.Qa.cs` is wrapped in `#if STILL_QA`. That symbol is defined only when `StillQa=true` (`still/Still.csproj:6`). `--qa` is parsed only in QA builds (`still/App.xaml.cs:36-38`). The server starts for the first window (`still/MainWindow.xaml.cs:79`) and writes its pipe name to `DataRoot\qa-pipe.txt` (`still/MainWindow.Qa.cs:13`). Ops: state, windowAt, checkUpdate, eval, stageExtension, stageStorePackage, stageImport, stageExternalProfile, shellEval, shellCdp, pageCdp, key, capture, quit (`still/MainWindow.Qa.cs:27-73`).

## 2. MCP and CLI

`Still.exe --mcp [--as <name>] [--this-profile]` runs a JSON-RPC server on stdio (`still/App.xaml.cs:44`). `Still.exe --cli <tool> as=<name> [key=value ...]` makes one call (`still/App.xaml.cs:43`). Both target the launch profile unless `--profile` is given (`still/App.xaml.cs:30`).

**Tools** (`still/McpServer.cs:14-32`; `*` = required; every tool also takes `tabId` where listed).

| Tool | Args | Notable behavior |
|---|---|---|
| list_profiles | none | Only when not locked. Returns name, id, open, launch, defaultForAgent (`still/McpServer.cs:146-147`) |
| list_tabs | none | Never lists private tabs. Fields tabId, title, url, active, yours, window (`still/MainWindow.Agents.cs:489-490`) |
| open_tab | url* | http/https only (`still/MainWindow.Agents.cs:434-439`). Background tab in the AI group; for the sidebar's own run, inside the chat (`still/MainWindow.Agents.cs:408-422`) |
| navigate | url*, tabId | Same URL rule |
| switch_tab | tabId*, show | Stays in background unless show |
| close_tab, go_back, go_forward, reload | tabId | |
| read_page | text, all, offset, tabId | Text 8000 characters at a time (`still/McpServer.cs:22`) |
| find | text*, tabId | |
| click | id, text, selector, tabId | |
| type | text*, id, selector, submit, append, tabId | |
| press_key | key*, tabId | |
| scroll | direction (down/up), amount, id, tabId | |
| wait_for | text, id, selector, gone, timeoutMs, tabId | Server limit is timeoutMs clamped to 100-30000, plus 5 s (`still/MainWindow.Agents.cs:89`) |
| handle_dialog | accept, text, tabId | Other page tools refuse while a dialog is open (`still/MainWindow.Agents.cs:382`) |
| upload_file | paths*, id, tabId | Up to 12 existing files; asks the user every time; 60 s limit (`still/MainWindow.Agents.cs:598-622`) |
| user_confirmed | code*, allow | Answers a pending approval by code (`still/MainWindow.Agents.cs:142-150`) |
| screenshot | tabId | Briefly brings the tab to the front (`still/MainWindow.Agents.cs:522-531`). CLI saves `%TEMP%\still-screenshot-*.png` (`still/McpServer.cs:241-245`) |
| ask_user | question*, options | Only with `--this-profile` (`still/McpServer.cs:46`). Works only for the sidebar's own run, else "Only Still's own chat can ask the user this way. Ask in your reply instead." (`still/MainWindow.Ai.cs:532`). Up to 6 options, 10 minutes (`still/MainWindow.Ai.cs:537,542`) |
| `profile` (on every tool) | name, id or "temp" | Not offered when locked (`still/McpServer.cs:46-47`) |

**MCP protocol.**

- `initialize`: the client name comes from `--as`, else `clientInfo.name` through `AgentName`, else "An AI agent" (`still/McpServer.cs:68,97`). Still echoes the client's protocol version, default "2025-06-18" (`still/McpServer.cs:99`). It sends the instructions at `still/McpServer.cs:34-39`, plus a profiles sentence when not locked (`still/McpServer.cs:101`).
- `AgentName` maps claude→Claude, codex→Codex, openai→Codex, grok→Grok, gemini, cursor, copilot, windsurf (`still/McpServer.cs:53-59`).
- `tools/call` runs on its own task, so calls run in parallel (`still/McpServer.cs:105-126`).
- Cancellation: `notifications/cancelled` cancels by requestId. A cancelled call gets no reply (`still/McpServer.cs:92,121`).
- Elicitation: if the client declares it (`still/McpServer.cs:98`) and Still answers with `confirm`, the server asks through `elicitation/create`. It waits up to 10 minutes (`still/McpServer.cs:83`), then sends `user_confirmed` and retries, at most 2 rounds. Decline returns "The user said no. Don't try again unless they ask." (`still/McpServer.cs:116-120`).
- Results: errors as `isError` text, screenshots as image content, a lone `text` as plain text, the rest as compact JSON (`still/McpServer.cs:135-143`). JSON-RPC errors: -32603 "Still error: ..." and -32601 "Method not found: ..." (`still/McpServer.cs:123,128,130`).

**Profile routing** (`Call`, `still/McpServer.cs:152-189`).

- A profile is matched by name (any case) or id. Unknown: `No Still profile is named "X". Use list_profiles.` (`still/McpServer.cs:160`).
- A closed named profile is launched with `--profile`/`--profiles-root` and retried for 25 s (`still/McpServer.cs:163-171`). With no profile, there is one attempt and no launch.
- One pipe connection per call, 3 s connect timeout (`still/McpServer.cs:176`). Request is `{client, tool, args, elicit}` (`still/McpServer.cs:179`).
- Client cap: 2 minutes, 12 for ask_user, then "Still didn't answer in time. It may be busy; try again, or ask the user to check Still." (`still/McpServer.cs:181-183`).
- Unreachable: "Still isn't running. Open it and turn on Settings → Let AI agents control Still (each profile has its own switch), then try again." (`still/McpServer.cs:186`).

**`temp`** (`still/McpServer.cs:191-210`). Creates `%TEMP%\Still-temp\<guid>`, deletes older temp folders whose windows are closed, writes a `state.json` with `AgentsEnabled=true` and `ApprovedAgents=[client]` (UiVersion 4), and launches with `--temp`. The window is reused only inside one MCP server process (`still/McpServer.cs:194`). Each `--cli` call is a new process, so each `--cli ... profile=temp` opens a new temp window (code reading; not verified at runtime).

**`--this-profile` locking.** Strips `profile` from every call (`still/McpServer.cs:109`), hides list_profiles and answers "Unknown tool: list_profiles" (`still/McpServer.cs:46-48,114`), and adds ask_user (`still/McpServer.cs:46`).

**Server-side limits** (`still/MainWindow.Agents.cs:89-92`): ask_user 660 s, wait_for as above, upload_file 60 s, everything else 30 s. Then: "<tool> didn't finish within N s, so Still stopped waiting. The page may be slow or stuck: call read_page to see where it is." A dialog or file picker in the agent's tab ends its running call early (`still/MainWindow.Agents.cs:181-184`, `still/MainWindow.FilePaste.cs:70`, `still/MainWindow.xaml.cs:489`).

**How `as=` is enforced.**

- CLI: missing `as=` prints `Error: say who you are with as=<your name>, for example as=Claude or as=Codex.` and exits 2 (`still/McpServer.cs:235`). The name goes through `AgentName` (`still/McpServer.cs:237`). Leading dashes are trimmed from keys, so `--as=X` also works (`still/McpServer.cs:231`).
- MCP has no `as=`. Identity is `--as` or `clientInfo.name`.
- The agent pipe trusts the `client` field. It only strips control characters and cuts it to 40 characters (`still/MainWindow.Agents.cs:67-68`). Any process of the same Windows user can claim any name.

**CLI details.** Exit 0 on success, 1 on a tool error (`Error: ...`), 2 on bad arguments (`still/McpServer.cs:230,235,239`). `true`/`false` become booleans; numbers only for amount, timeoutMs and offset; `paths` splits on `;` (`still/McpServer.cs:232`).

**What `--cli help` prints** (also with no args, `--help` or `-h`; exit 0; `still/McpServer.cs:220-227`):

```
Usage: Still.exe --cli <tool> as=<your name> [key=value ...]

Tools:
  <name> <key>= <key>= ... profile=
      <description>
```

It uses `BuildTools(false)`: list_profiles first, then the 19 browser tools, each ending in `profile=`. ask_user is not listed. Any change to a tool name, property order or description changes this output.

## 3. Approval and the per-profile switch

`HandleAgent` checks in this order (`still/MainWindow.Agents.cs:62-98`):

| # | Check | Result | Ref |
|---|---|---|---|
| 1 | `Prefs.AgentsEnabled` off | "AI control is turned off. The user can turn it on in Still → Settings → Let other AI apps use Still." | `:71` |
| 2 | tool is user_confirmed | handled before approval | `:72` |
| 3 | client in `blockedAgents` | "The user blocked this agent in Still for this session." | `:75` |
| 4 | Stop pressed in the last 30 s | "The user pressed Stop. Stop what you are doing and wait for the user's next message." | `:76` |
| 5 | name in `Prefs.ApprovedAgents` | approved for the session | `:77` |
| 6 | not approved | bar: Block gives the message in row 3; no answer gives "Waiting for the user to let you in: Still shows a bar with Allow and Block at the top of its window. Tell the user to click Allow, then call the tool again." | `:78-81` |
| 7 | user took over | waits up to 40 s, then "The user took over the browser for now. Wait a little, then call the tool again." | `:84-86` |

- **Storage.** `approvedAgents` and `blockedAgents` are static sets, so they are per process, which means per profile (`still/MainWindow.Agents.cs:18-19`). Allow adds the name to both the session set and `Prefs.ApprovedAgents` in state.json. Block is session only (`still/MainWindow.Agents.cs:119-127`). `AgentsEnabled` defaults to false (`still/Models.cs:69`).
- **Switch off** clears both approval lists and answers a pending bar with Block (`still/MainWindow.Shell.cs:139`). That puts the asking client in `blockedAgents`, which is never cleared.
- **Waiting.** The bar waits 45 s, or 0 s if the client can elicit or the user is away (`still/MainWindow.Agents.cs:102-111`). Away means no input for 60 s or every window minimized (`still/MainWindow.Agents.cs:154-158`). One question shows at a time. An answer is reused for 2 minutes (`still/MainWindow.Agents.cs:104`).
- **Ask in chat.** With `AgentsAskInChat` on (default, `still/Models.cs:70`) the refusal carries a 6-hex code, valid 10 minutes, and the question "Allow X to use your Still browser? It can open, read and click pages, but never private tabs, passwords or cookies." (`still/MainWindow.Agents.cs:132-141`). A bad code: "That code isn't valid anymore (the user may have answered in Still). Call the tool again." (`still/MainWindow.Agents.cs:144-145`).
- **Approval bar** (`still-ui/src/App.tsx:442-447`): "<client> wants to control Still. It can open, read and click pages, but never private tabs, passwords or cookies." or "<client> wants to <ask>." with Block and Allow (`agentAnswer`).
- **Private tabs.** Hidden from list_tabs (`still/MainWindow.Agents.cs:490`). Any other use throws "Private tabs are off-limits to agents." (`still/MainWindow.Agents.cs:374`). No tool exposes passwords or cookies (`still/McpServer.cs:14-32`).
- **Activity UI.** The bar stays for 2 minutes after the last call (`still/MainWindow.Agents.cs:161-162`). The dock pill shows "<client> is working" or "You're driving", with Take over and Stop (`still-ui/src/App.tsx:520-529`). In split view a card shows "Controlled by <companion or client>" with Take over / Hand back, Go to chat and Stop (`still-ui/src/App.tsx:508-515`).
- **Stop** releases the agent's tabs, refuses its calls for 30 s, ends its running call, stops a sidebar run with the same name, and toasts "Stopped X." The agent stays approved (`still/MainWindow.Agents.cs:171-178`).
- **Take over** pauses the agent and brings its tab to the front (`still/MainWindow.Agents.cs:164-169`).
- **Tab claims.** `agentTabs` maps an agent name to its tab (`still/MainWindow.Agents.cs:390`). Without tabId the agent keeps its last tab (`still/MainWindow.Agents.cs:370-371`). `Claim` sets `tab.Agent` and `LastActive` (`still/MainWindow.Agents.cs:391-397`). `ReleaseAgentTabs` clears `Agent` only on tabs outside the AI group (`still/MainWindow.Agents.cs:399-403`). `Agent` and `AgentGroup` are not saved (`still/Models.cs:12-13`). The tab strip shows an agent icon (`still-ui/src/App.tsx:128`) and an "AI tabs" group (`still-ui/src/App.tsx:235`).

## 4. AI sidebar

**CLIs** (`AiClis`, `still/MainWindow.Ai.cs:39-44`).

| Id | Name (`--as`) | App | Installer | Sign-in args | Allowed sign-in domains |
|---|---|---|---|---|---|
| claude | Claude | Claude Code | `https://claude.ai/install.ps1` | `auth login` | claude.ai, claude.com, anthropic.com |
| codex | Codex | Codex | `https://chatgpt.com/codex/install.ps1` | `login` | openai.com, chatgpt.com |
| grok | Grok | Grok Build | `https://x.ai/cli/install.ps1` | `login --device-auth` | x.ai |

**FindCli** (`still/MainWindow.Ai.cs:114-125`) searches User PATH, Machine PATH, process PATH, then `~\.local\bin`, `~\.grok\bin`, `%APPDATA%\npm` and `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin`, trying `.exe` then `.cmd`. A `.cmd` runs through `cmd.exe /d /s /c` (`still/MainWindow.Ai.cs:496-504`).

**Launch** (`RunAi`, `still/MainWindow.Ai.cs:252-356`). Working folder `DataRoot\ai` (`still/MainWindow.Ai.cs:47,275`). Still's MCP is passed as `--mcp --as <Name> --this-profile --profile <DataRoot> --profiles-root <ProfileHome>`, plus `--qa` in QA (`still/MainWindow.Ai.cs:277-278`).

| CLI | Exact args | Ref |
|---|---|---|
| Claude | writes `ai\mcp.json`; `-p --output-format stream-json --verbose --mcp-config <ai\mcp.json> --strict-mcp-config --tools "" --allowedTools mcp__still --session-id <uuid>` (or `--resume <uuid>`), then `--model`, `--effort` | `:287-292` |
| Grok | first `grok mcp add -s project still <Still.exe> -- <mcp args>`; then `--prompt-file <file> --output-format streaming-messages-json --trust --tools search_tool,use_tool --no-subagents --always-approve -s <uuid>` (or `-r <uuid>`), then `-m`, `--reasoning-effort` | `:293-301` |
| Codex | `exec [resume] --json --skip-git-repo-check -c sandbox_mode='read-only' -c mcp_servers.still.tool_timeout_sec=660 -c mcp_servers.still.command='<exe>' -c mcp_servers.still.args=[...]`, then `-c model=`, `-c model_reasoning_effort=`, the session id on resume, and `-`. Refuses a Still path with `'` or `!` | `:302-312` |

- The prompt goes through stdin (Claude, Codex) or the prompt file (Grok), never the command line (`still/MainWindow.Ai.cs:318-319`). stdin is closed right after (`:320`). The first message of a session gets the instructions and page context (`:274`, instructions at `:223-239`). A chat moved to a new session gets the last 20 messages (`:267-268`).
- Only catalog models and efforts reach the command line (`:281-282`).
- No environment variables are changed for runs (`:496-504`). Stop is `Process.Kill(true)` (`:176`). There is no Job Object and no per-run log; stderr keeps the last 20 lines for the error text (`:321`).
- One run per window: `aiSend` is ignored while busy (`:177`).
- A lost session reruns once on a new session (`:333-340,359`). A signed-out error starts sign-in, then reruns (`:350-355,360`).

**Profile locking.** `--as <Name> --this-profile --profile <DataRoot>` (`:277`). The run is approved for the session without the bar (`:270`). If the switch is off, the first send turns it on and adds the note "Turned on Settings → Let other AI apps use Still, so X can use your tabs." (`:269`).

**Models and efforts.** Claude is hard-coded: Default, Fable, Opus, Sonnet, Haiku, efforts low to max (`:67-69`). Codex reads `codex debug models` JSON, keeping `visibility == "list"` with its `supported_reasoning_levels` (`:77,82-85`). Grok reads `grok models` lines that start with `*` or `-`, efforts low/medium/high (`:66,86-87`). Choices are saved per CLI in `Prefs.AiModels` and `Prefs.AiEfforts` (`still/Models.cs:71-72`).

**Sign-in detection** (`CheckAi`, `:382-402`, 20 s timeout, at most every 30 s per `:376`): Claude `auth status` JSON `loggedIn`; Codex `login status` contains "Logged in" and not "Not logged in"; Grok `models` without "not authenticated". It does not check whether Codex uses ChatGPT or an API key.

**Sign-in flow** (`AiSignIn`, `:425-461`). Runs the CLI's own login with no window. Takes the first https URL on that CLI's allowed domains (`:420-421,439`), opens it in a Still tab if not already open, picks up a device code, and gives up after 10 minutes.

**Install flow** (`AiInstall`, `:464-494`). Runs only from the "Install <App>" button (`still-ui/src/AiSidebar.tsx:139`). Hidden PowerShell `irm '<installer>' | iex` with `CODEX_NON_INTERACTIVE=1`, 10-minute limit, then straight to sign-in (`:490`).

**Chats.** `DataRoot\ai\chats.json`, newest 200 kept, written through `.tmp` (`:52-60`). Fields: Id, Title, Harness, Session, Started, Companion, Updated, Messages of Role and Text (`:8-20`).

**Companions.** Fields Id, Name, Face, Color, Job (`:23-30`). Stored in `state.json` as `Preferences.Companions`; when empty the defaults are Pip, Hazel, Rio and Juno (`:96-102`, `still/Models.cs:73`). Name up to 24 characters, job up to 1000 (`:196-203`). The last one can't be deleted (`:204`). Faces are Fluent Emoji 3D images on 8 colors (`still-ui/src/Buddy.tsx:4-9`). The job goes into the instructions (`:223`).

**Event parsing.**

- `MessagesEvent` for Claude and Grok (`:549-570`): text blocks become messages; `tool_use` becomes step rows, unwrapping Grok's `use_tool` and hiding `search_tool`; `rate_limit_event` with `unifiedWindows` becomes "5-hour limit X% used · weekly Y%"; for Grok, `result.usage` becomes "Last reply: N in, M out".
- `CodexEvent` (`:572-588`): `thread.started` sets the session; `mcp_tool_call` steps; `agent_message` text; `turn.completed` usage; `turn.failed` with 401 becomes "Codex: not signed in. Sign in, then try again."

**UI** (`still-ui/src/AiSidebar.tsx`). The follow-up queue is client-side and holds one message. It is sent when the run ends without an error (`:173,181,232`). The placeholder while busy is "Queue a follow-up…" (`:235`). There is no interrupt. Question cards take keys 1-9 and have Skip (`:100-115`). Steps collapse to "(and N more actions)" (`:213`). Timers read "Working for" and "Worked for" (`:221,225`). The usage line shows in panel mode only (`:236`).

**Chat tabs.** `ChatId` marks a chat tab and is saved. `InChat` marks a page the AI opened inside a chat and is saved. `PageOpen` is not saved (`still/Models.cs:15-17`). Ops chatOpen, chatPage and chatPopOut are at `still/MainWindow.Ai.cs:189-195`. Selecting an in-chat page shows its chat tab (`still/MainWindow.xaml.cs:227-240`). Ctrl+Shift+A toggles the sidebar (`still/MainWindow.Actions.cs:290`). The mac build hides AI and extensions (`mac/Sources/Still/main.swift:214-215`).

## 5. State and settings

- **state.json** is `DataRoot\state.json`, saved through `.tmp` with a `.bak` (`still/Models.cs:104-121`). `Preferences` is `still/Models.cs:57-84` (Theme "Dark", MemorySaver true, AgentsEnabled, AgentsAskInChat, AiModels, AiEfforts, Companions, AiHarness, ApprovedAgents and more). Migrations run by `UiVersion` 1 to 4 (`still/MainWindow.xaml.cs:42-45`). Private tabs are never saved (`still/MainWindow.Windows.cs:60-65`).
- **Other files.** `DataRoot\ai\` (chats.json, mcp.json, Grok's project config), `DataRoot\Extensions\<id>.path` (`still/MainWindow.BrowserTools.cs:62,206`), `ProfileHome\profiles.lock` (`still/ProfileCatalog.cs:71`).
- **Settings dialog.** Three tabs: Appearance, Browsing, Your data (`still-ui/src/App.tsx:577-580`). Rows include theme, search engine, "Let other AI apps use Still" (`:589`), "Ask me in the AI's chat when I'm away" (`:590`), an MCP config and agent prompt to copy (`:591-614`), drag tabs into their own window, open at sign-in, default browser, restore tabs, block ads and trackers, download folder, and links to profiles, import, passwords, cookies and security. Tracking prevention, memory saver and form autofill are in `still-ui/src/BrowserTools.tsx:58-60`.
- **Preference keys** (`still/MainWindow.Shell.cs:130-142`): theme, search, restore, blocking, tracking, tearOff, askInChat, agents, memory, autofill.
- **Extensions.** Chrome Web Store CRX download and signature check (`still/MainWindow.ExtensionCatalog.cs:39,52`). Popups in a floating window (`still/MainWindow.ExtensionPopup.cs:13-17`). Toolbar actions and side panel (`still/MainWindow.ExtensionActions.cs:10-15`). The toolbar shows pinned extensions and a menu with pin toggles and "Manage extensions" (`still-ui/src/App.tsx:391-401`).
- **Tabs and layout.** Only the horizontal top tab strip exists (`still-ui/src/App.tsx:343`). There is no layout preference (`still/Models.cs:57-84`, `still/MainWindow.Shell.cs:130-142`). Focus mode is Ctrl+Shift+F (`still/MainWindow.Actions.cs:287`). Tabs tear off into windows (`still/MainWindow.Windows.cs:85`). The shortcut list is `still-ui/src/App.tsx:67`; the handler is `still/MainWindow.Actions.cs:257-292`.
- **Tab sleeping** (`still/MainWindow.Memory.cs`). A 15 s timer (`:11`). Background tabs get memory target Low (`:83-84`). Tabs suspend after 1 minute idle and are discarded after 5 minutes (`STILL_QA_DISCARD_MINUTES` in QA) (`:93-134,165`). Renderer working sets are trimmed (`:157,178`). `CanSuspend` skips the shown tab, tabs with an agent, media, loading, downloads, pending permissions and audio (`:183-186`).
- **Ad blocking.** `BlockedDomains` (`still/MainWindow.Actions.cs:9`), a YouTube ad script (`:23,75-83`), and `SetupBlocking` per tab, counting `tab.Blocked` (`:84-98`), called when a view is created (`still/MainWindow.xaml.cs:463`).
- **Theme tokens.** `still-ui/src/index.css` has stock shadcn neutral oklch tokens in `:root` (`:52-85`) and `.dark` (`:87-119`), radius 0.625rem (`:76`), and imports Geist Variable and Fraunces (`:4-5`). `still-ui/src/App.css` redefines the same tokens in hex (warm light, gray dark) and adds `--chrome`, `--pop`, `--ink` and `--font-display` (`still-ui/src/App.css:2-5`). App.css loads after index.css (`still-ui/src/main.tsx:3`, `still-ui/src/App.tsx:25`), so its values should win. Not verified in the built bundle.
- **Motion.** `motion.css` (imported at `still-ui/src/App.tsx:658`) defines `--ease-flow` and `--ease-spring` (`still-ui/src/motion.css:2`), fade/dialog/menu/tooltip keyframes (`:47-54`) and turns animation off for `prefers-reduced-motion` (`:56-59`). The shared spring is `FLOW` (`still-ui/src/App.tsx:69`). WPF chrome colors come from `ApplyTheme` (`still/MainWindow.xaml.cs:135`).

## 6. Tests

**Build.** `build.ps1` runs `npm ci`, `node --test tests/suggestions.test.ts`, `npm run lint` and `npm run build` in `still-ui` (`build.ps1:6-12`), then `dotnet publish` self-contained. `-Qa` writes `artifacts/Still-QA` with `StillQa=true` (`build.ps1:13-19`). `-Installer` with `-Qa` is refused (`build.ps1:26`).

**Desktop scripts.** Each launches the QA exe with `--qa --profile <fresh folder under artifacts/>` and drives it over the QA pipe (`tests/desktop/performance.py:141`, `tests/desktop/features.py:115`, `tests/desktop/tabs.py:99`, `tests/desktop/startup.py:68`). Run them one at a time (`tests/desktop/README.md:3`).

| Test | What it checks | Ref |
|---|---|---|
| features.py | download opens once, packaged login observer and reader, extension ID, service worker and storage, native messaging, real tab queries, content scripts, six simultaneous external links, no UI errors; optional Cold Turkey identity | `tests/desktop/features.py:128-242` |
| performance.py | restored tabs stay unloaded, external links, idle renderers suspend, resident RAM drops at least 20 percent, media/WebRTC tab stays awake, forms/JS state/cookies/storage survive wake, memory saver off resumes all, no UI errors, session saves; two 75 s idle periods | `tests/desktop/performance.py:151-200` |
| startup.py | four launch/quit cycles per exe: visible window, usable page, link to running instance | `tests/desktop/README.md:27-30` |
| tabs.py | new-tab button placement, 25 and 30 tabs, resize, mouse wheel, Ctrl T, 31 tabs saved | `tests/desktop/tabs.py:85-150` |
| Still.ReleaseChecks | production build has no `StartQa` and no QA timings; every Shell file plus 2 scripts embedded and byte-identical to source | `tests/Still.ReleaseChecks/Program.cs:12-29` |
| Still.PerformanceChecks | CRX3/CRX2 signature and ID checks (RSA, ECDSA, tampering), URL argument parsing, link pipe delivery, rejection and stall handling; compiles only `CrxPackage.cs` and `BrowserRegistration.cs` with an App stub | `tests/Still.PerformanceChecks/Program.cs:31-78`, `tests/Still.PerformanceChecks/AppStub.cs` |

**How to run** (`tests/desktop/README.md:7-43`):

```powershell
.\build.ps1 -Qa
python tests/desktop/features.py artifacts/Still-QA/Still.exe [--cold-turkey]
python tests/desktop/performance.py artifacts/Still-QA/Still.exe
python tests/desktop/tabs.py artifacts/Still-QA/Still.exe
python tests/desktop/startup.py <baseline-qa>/Still.exe artifacts/Still-QA/Still.exe --cold-bundle
dotnet run --project tests/Still.PerformanceChecks -c Release -- [artifacts/cold-turkey.crx pganeibhckoanndahmnfggfoeofncnii]
dotnet run --project tests/Still.ReleaseChecks -c Release -- still/bin/Release/net10.0-windows/win-x64/Still.dll .
```

**Findings.**

- tabs.py looks stale. It sets `Preferences.Layout = "Sidebar"` (`tests/desktop/tabs.py:98`), sends `preference layout` and reads `rpc()['layout']` (`:107,115,118,134`). No layout preference exists, and the QA `state` op returns no `layout` field (`still/MainWindow.Qa.cs:27-33`). It would likely fail with a KeyError. Not verified at runtime.
- No test covers `--mcp`, `--cli`, the agent pipe, approvals, the switch, private-tab filtering or the AI sidebar. A search of `tests/desktop` for mcp, --cli, agent and AgentsEnabled finds nothing.
- performance.py opens about 8 tabs (`tests/desktop/performance.py:138-165`). It does not measure idle RAM with 1 and 10 tabs, or tab-switch latency, which Phase 0 asks for.

## 7. Verified CLI flags on this PC (2026-10-28)

- Claude Code 2.1.312: `-p`, `--output-format stream-json`, `--input-format stream-json`, `--verbose`, `--mcp-config`, `--strict-mcp-config`, `--tools`, `--allowedTools`, `--session-id`, `--resume`, `--add-dir`, `--model` and `--effort` all exist. `claude auth status` prints JSON with `loggedIn` and `authMethod` ("claude.ai" here). Signed in.
- Grok Build 1.0.50: `-p` is `--single <PROMPT>`, plus `--prompt-file` and `--prompt-json`. `--output-format streaming-json` emits ACP session updates; `streaming-messages-json` emits the Anthropic Messages wire format (Still uses this). `-s/--session-id` takes a UUID and only for a NEW session; resume is `-r/--resume`. Also `-m/--model`, `--reasoning-effort` (alias `--effort`), `--tools`, `--disallowed-tools`, `--cwd`, `--always-approve`, `--trust` and `--no-subagents`. `grok login --oauth` / `--device-auth`. `grok agent stdio` exists (ACP). There's no status command: `grok models` prints "You are not authenticated." when signed out. MCP is configured with `grok mcp add -s project`, not per run. Installed, NOT signed in.
- Codex CLI 0.146.0: `exec --json`, `exec resume <id>` (or `--last`), `-m`, `-s/--sandbox`, `-c key=value`, `-C/--cd`, `--add-dir`, `--skip-git-repo-check`, `--ephemeral` and `-o`. `codex login status` prints "Not logged in" here. `codex login --device-auth` and `--with-api-key` exist. Installed, NOT signed in.

## 8. Gaps vs the brief, and risks

**Gaps.**

| Brief asks for | Today | Ref |
|---|---|---|
| No "Codex" in the UI | Shown in the picker and setup ("Install Codex", "Sign in to Codex"), errors, settings prompt, About | `still/MainWindow.Ai.cs:42,303,584`, `still-ui/src/AiSidebar.tsx:139,157`, `still-ui/src/App.tsx:595,638` |
| Never auto-install; show the command on "How to install" | One-click Install runs the installer script | `still-ui/src/AiSidebar.tsx:139`, `still/MainWindow.Ai.cs:464-494` |
| Sign-in in a visible terminal | Login runs with no window; URL opens in a Still tab | `still/MainWindow.Ai.cs:425-461,498` |
| Confirm Codex uses ChatGPT, not an API key | Only checks "Logged in" | `still/MainWindow.Ai.cs:396` |
| Strip API-key env vars | No environment changes | `still/MainWindow.Ai.cs:496-504` |
| Job Object, per-run timeouts, per-run crash log | `Kill(true)`, no run timeout, last 20 stderr lines | `still/MainWindow.Ai.cs:176,321` |
| Claude `--input-format stream-json`, queue and interrupt | One prompt on stdin, stdin closed; one client-side queued message; no interrupt | `still/MainWindow.Ai.cs:289,319-320`, `still-ui/src/AiSidebar.tsx:173,181` |
| Adapter interface, manifests in `%LOCALAPPDATA%\Still\agents` | Three hard-coded CLIs and switch statements | `still/MainWindow.Ai.cs:39-44,285-312` |
| Companions in `companions\<id>\companion.json` with memory and skills | In state.json, five fields, no memory or skills | `still/MainWindow.Ai.cs:23-30,102` |
| Chats as `chats/<id>.jsonl` | One `ai/chats.json`, 200 kept | `still/MainWindow.Ai.cs:52-60` |
| Agent tabs sleep when idle | AI-group tabs keep `Agent` set, and `CanSuspend` needs `Agent == null`, so they never sleep (code reading) | `still/MainWindow.Agents.cs:402`, `still/MainWindow.Memory.cs:184` |
| Per-site permission layer, Approve All | Session approval per agent, plus per-upload asks | `still/MainWindow.Agents.cs:77-81,614-615` |
| Several runs at once | One run per window | `still/MainWindow.Ai.cs:177` |
| Regression tests for agent surfaces | None (see section 6) | |

**Places where the brief disagrees with itself or with the code.**

- `--always-approve`: section 0 says keep it; section 4.1 says never pass it. Code passes it (`still/MainWindow.Ai.cs:298`).
- Ctrl+J: section 0 says it stays Downloads; the section 6 table makes it "Toggle chat". Code: Downloads (`still/MainWindow.Actions.cs:286`).
- Layout: section 0 says no vertical layout; Phase 5 asks for Modern and Classic.
- Grok run: sections 1 and 4.1 say `grok -p ... --output-format streaming-json`; section 0 and the code use `--prompt-file` and `streaming-messages-json`.
- Section 1 says there is no unit-test project. True for .NET, but `still-ui/tests/suggestions.test.ts` runs in every build (`build.ps1:9`).
- Section 4.2 suggests "Juno" as a starter name. Juno is already a default companion, the organizer (`still/MainWindow.Ai.cs:100`).
- The switch has two names in code: "Let other AI apps use Still" (`still-ui/src/App.tsx:589`, `still/MainWindow.Agents.cs:71`) and "Let AI agents control Still" (`still/McpServer.cs:186`).

**Risks: changes that would alter external MCP or CLI behavior.**

1. Tool names, argument names, property order and descriptions feed both `tools/list` and `--cli help` (`still/McpServer.cs:14-32,220-227`). The initialize instructions are also sent to every client (`still/McpServer.cs:34-39`).
2. Identity is the display name. Remembered approvals pass the stored name through `AgentName` too (`still/MainWindow.Agents.cs:77`), so a rename inside `AgentName` carries old approvals over only while the stored name still contains a mapped key (a saved "Codex" still maps). The rename does change the name users see for `as=Codex` callers. Renaming an `AiClis` entry changes the `--as` name (`still/MainWindow.Ai.cs:277`), Stop matching (`still/MainWindow.Agents.cs:176`) and `ChatRunner` (`still/MainWindow.Agents.cs:405`).
3. The sidebar approves "Claude", "Codex" or "Grok" for the session (`still/MainWindow.Ai.cs:270`). An outside client whose name maps to the same display name (for example `claude-code`) then skips the bar for the rest of the session (`still/McpServer.cs:56-57`). While a sidebar run is busy, `ChatRunner` also sends that client's `open_tab` into the chat (`still/MainWindow.Agents.cs:405,492`).
4. The first sidebar send turns the per-profile switch on for every outside agent too (`still/MainWindow.Ai.cs:269`).
5. Refusal strings are a contract the brief's tests will check (`still/MainWindow.Agents.cs:71,75,76,80,86,92,374`).
6. Time budgets: 30 s server default, 2 minutes client side, ask_user 660 s and 12 minutes, Codex `tool_timeout_sec=660` (`still/MainWindow.Agents.cs:89`, `still/McpServer.cs:181`, `still/MainWindow.Ai.cs:306`). A new permission card that waits on the user inside a tool call must fit these, or the call fails with "didn't finish within".
7. The temp profile writes `Preferences.AgentsEnabled` and `ApprovedAgents` by name (`still/McpServer.cs:202`). Renaming these properties breaks temp windows and saved settings.
8. `mac/build.sh` extracts `BlockedDomains`, `YouTubeAdScript` and `PageJs`, `SnapshotJs`, `FindJs`, `ClickJs`, `FocusJs`, `ScrollJs`, `WaitJs`, `FileInputJs` by name from the C# files (`mac/build.sh:19-26`). Moving or renaming them breaks the mac build.
9. Letting agent tabs sleep or close changes what an outside agent finds between calls. A discarded tab loses page state and its read_page ids (`still/MainWindow.Memory.cs:104-113`).
10. `OpenAgentTab` builds a non-private tab even when the active window is incognito (`still/MainWindow.Agents.cs:30,408-411`; compare `still/MainWindow.xaml.cs:205`). Not verified at runtime.
11. Shortcuts: Ctrl+Tab cycles tabs in order today (`still/MainWindow.Actions.cs:278`). Ctrl+K does not check Shift, so Ctrl+Shift+K also opens "Find a tab" (`still/MainWindow.Actions.cs:273`). Adding Ctrl+Shift+K needs that order changed.
12. Moving chats to jsonl must keep `Session` and `Started`, which drive `--resume`, `-r` and `exec resume` (`still/MainWindow.Ai.cs:289,298,305-310`).
