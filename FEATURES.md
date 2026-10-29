# Still: feature map

Everything Still has today, read from the code. ✅ shipped (on `welcome`, built and installed locally; the last public release is v1.6.34, so not all of it is public yet) · 🚧 in progress (branch named) · 🧪 experimental.
Paths: `still/` = Windows host (WPF, WebView2), `still-ui/src/` = the React interface both hosts load, `mac/Sources/Still/` = Mac host (AppKit, WebKit).

**Rule:** any commit that adds, changes or removes a feature updates this file in the same commit.

## Browser and tabs

- ✅ **Tabs**: open, close, pin, duplicate, mute, reorder, sleep; saved in `state.json` (`Models.cs` `SavedState`, written via `.tmp` then `.bak` swap).
- ✅ **Restore tabs**: reopens last session's tabs on start; Preferences `RestoreTabs`.
- ✅ **Reopen closed tab**: Ctrl+Shift+T, plus a recently closed list (`recent`/`recentPick` in `MainWindow.Shell.cs`).
- ✅ **Recent-tab switcher**: Ctrl+Tab flips to the last tab; holding Ctrl shows an MRU list (`MainWindow.Tabs.cs` `SwitchRecent`).
- ✅ **Cycle tabs**: Ctrl+Alt+Left/Right moves through tabs in strip order (`CycleTabs`).
- ✅ **Find a tab**: Ctrl+K sheet filters open tabs (`MainWindow.Panels.cs`).
- ✅ **Tab groups**: named, colored, collapsible; members stay adjacent in the strip (`MainWindow.Tabs.cs`, `TabGroup`).
- ✅ **Split view**: two tabs side by side in one window, resizable, swappable; one pair per window (`StartSplit`).
- ✅ **Tab layout**: Classic (tabs on top) or Modern (resizable left sidebar); Preferences `TabLayout`, `SidebarWidth`.
- ✅ **Multiple windows**: one process, shared history/bookmarks/settings; each window owns its tabs (`MainWindow.Windows.cs`).
- ✅ **Move tabs between windows**: drag out (setting "Drag tabs into their own window", off by default) or Move to; live page moves without reload.
- ✅ **Private window**: every tab InPrivate and unsaved; Ctrl+Shift+N (`OpenIncognito`).
- ✅ **Address bar**: search or URL; local history/bookmark suggestions, learned typed→picked ranking (`suggestions.ts`, `AddressPick`); never fetches icons or sends keystrokes.
- ✅ **Search engine**: Google, Bing or DuckDuckGo (Preferences `SearchEngine`).
- ✅ **New tab page**: the companion home (chats, ideas) or "sites" (speed dial, suggested sites, open tabs); Preferences `NewTab`.
- ✅ **Bookmarks**: Ctrl+D, bookmarks bar, edit/move/remove, import/export HTML (`MainWindow.Panels.cs`).
- ✅ **History**: searchable panel, remove entries, clear all (`MainWindow.Panels.cs`).
- ✅ **Downloads**: card on start, progress ring, open/show/cancel, choose folder (`MainWindow.xaml.cs`, Preferences `DownloadFolder`).
- ✅ **Reader mode**: Ctrl+Shift+R, Mozilla Readability on a copy of the page (`MainWindow.Actions.cs`, `Assets/Readability.js`).
- ✅ **Hide an element**: pick an element to hide; per-site rules re-applied on load (`PickHidden`, `SavedState.Hidden`).
- ✅ **Find in page, zoom, picture-in-picture**: toolbar and shortcuts (`find`, `zoom`, `pictureInPicture` in `MainWindow.Shell.cs`).
- ✅ **Full screen**: F11 covers the monitor incl. taskbar; video full screen fills the window instantly (`MainWindow.FullScreen.cs`).
- ✅ **Pop-ups**: sized `window.open` gets a small window titled with its site; unrequested pop-ups blocked, allow per site (`MainWindow.Popups.cs`).
- ✅ **App links**: discord:, mailto: etc. ask in the permission bar, remember Allow per site+app, refuse abusable schemes (`MainWindow.AppLinks.cs`).
- ✅ **Site permissions**: camera/mic/location etc. asked in Still's own bar; denied after 90 s unanswered (`MainWindow.Permissions.cs`).
- ✅ **Page dialogs**: alert/confirm/prompt shown inside Still, not as Windows dialogs (`dialogAnswer`).
- ✅ **Upload card**: a site's file picker opens a card of recent matching files, copied image first; picker intercepted via CDP (`MainWindow.FilePaste.cs`, `UploadCard.tsx`).
- ✅ **Draft keeper**: text typed into a box survives a surprise reload; a chip offers it back for 6 h (`MainWindow.Drafts.cs`).
- ✅ **Audio follows the default output**: on a Windows output switch, playing media reopens on the new device; 1.5 s poll (`MainWindow.Audio.cs`).
- ✅ **Memory saver**: background tabs sleep after 1 min, unload after 5; media and downloads stay awake, pinned and typed-in tabs only sleep (`MainWindow.Memory.cs`).
- ✅ **Error and crash pages**: one page per load failure ("you're offline" etc.); renderer crash shows in place, no auto-reload (`ErrorPages.cs`, `MainWindow.xaml.cs`).
- ✅ **Engine crash recovery**: if the engine's main process dies, Still saves tabs and restarts once (`App.xaml.cs`).
- ✅ **Themes**: Light, Dark, System (Preferences `Theme`).

## Blocking and privacy

- ✅ **Ad and tracker blocking**: built-in third-party domain list answered with 204; per-site off switch (`MainWindow.Actions.cs` `BlockedDomains`, `UnblockedHosts`).
- ✅ **YouTube ads**: strips ad data from YouTube's own responses; ads reaching the player are muted, skipped, or sped past (`YouTubeAdScript`).
- ✅ **Tracking prevention**: Basic, Balanced or Strict via WebView2 `PreferredTrackingPreventionLevel` (Preferences `Tracking`).
- ✅ **Cookies panel**: search and delete cookies per cookie or per site (`MainWindow.BrowserTools.cs`).
- ✅ **Form autofill**: on/off for the engine's general autofill; password autosave always off (own manager instead).
- ✅ **No telemetry**: no account, no analytics; the only background request is the GitHub release check.

## Profiles, import and export

- ✅ **Profiles**: separate logins/cookies/tabs; each opens as its own process (`ProfileCatalog.cs`, `MainWindow.Profiles.cs`).
- ✅ **Temp profile**: throwaway window with no cookies or history, deleted once closed (`App.xaml.cs`; MCP `profile: "temp"`).
- ✅ **Import from another browser (Windows)**: Chrome, Edge, Brave, Vivaldi, Opera/GX, Firefox: bookmarks, history, passwords, cookies (sessions), autofill; reviewed before commit (`ExternalProfileImport.cs`).
- ✅ **Close source and retry**: a running Chromium browser locks its cookies; with your OK Still closes it and reads again (`CloseSourceAndRetry`).
- ✅ **File import/export**: bookmarks HTML/JSON, passwords CSV, Still data JSON (tabs, bookmarks, history) (`MainWindow.Import.cs`).

## Passwords and autofill

- ✅ **Password manager (Windows)**: save, update, fill, delete, never-save list; vault encrypted with DPAPI (`Vault.cs`, `MainWindow.Passwords.cs`, `Assets/LoginObserver.js`).
- ✅ **Password manager (Mac)**: same features, one Keychain item per profile (`Vault.swift`).
- ✅ **Key in the field**: login fields get a fill button for this exact site's saved logins; optional auto sign-in.
- ✅ **Strong passwords**: suggests one for new accounts and saves it immediately so it's never lost.
- ✅ **Two-step sign-ins**: remembers the username from step one for the password step.
- ✅ **Insecure pages**: filling on non-https asks first; auto sign-in stays off there (localhost excepted).
- ✅ **OS check before reveal**: Windows Hello/PIN or Touch ID before show, copy, edit or export, at most once a minute (`OsAuth.cs`).
- ✅ **Weak password flags**: short, one or two character kinds, common, or repetitive (`MainWindow.Passwords.cs`).
- ✅ **CSV import/export**: Chrome/Edge/Firefox-compatible CSV; import can replace matching logins.
- ✅ **Never in private tabs**: no prompts, no saving, no filling there.
- ✅ **Kept from AIs**: AIs can't fill while driving a tab; fields holding saved usernames read as hidden; sign-in pages pause the AI for you.

## AI chat (bring your own AI)

- ✅ **Chat sidebar and chat tabs**: chat beside any page or as its own tab; resizable (`AiSidebar.tsx`, `MainWindow.Ai.cs`).
- ✅ **Claude**: drives the Claude Code CLI headless on your own plan; Still never reads its login (`Agents/AgentAdapter.cs`).
- ✅ **ChatGPT**: drives OpenAI's agent CLI signed in with your ChatGPT plan; API-key logins are ignored (`AgentAdapter.cs`).
- ✅ **Grok**: drives Grok Build headless; its own tools off, Still's MCP tools only (`AgentAdapter.cs`).
- 🧪 **Custom agent manifests**: any agent CLI described by a JSON file in the agents folder; written but untested, off by default.
- ✅ **Install and sign in from Still**: runs the maker's official installer and sign-in after you press the button; no admin (`aiInstall`, `aiLogin`).
- ✅ **No API billing**: API-key env vars are stripped so runs use your app plan.
- ✅ **One model list**: every AI's models in one picker; picking another AI's model moves the chat over with its history.
- ✅ **Modes**: Quick, Everyday, Thorough; Advanced swaps in model and effort pickers (Preferences `AiAdvanced`, `AiModels`, `AiEfforts`).
- ✅ **Parallel chats**: any number run at once, each its own CLI process in its own folder.
- ✅ **Follow-ups queue**: messages sent while working wait; send now or clear the queue (`aiNow`, `aiUnqueue`).
- ✅ **Stop and resume**: stop a run; runs cut off by a close or crash offer Resume all (`aiStop`, `aiResumeAll`).
- ✅ **Chat history**: saved per profile in `chats.json`; open, archive, delete one or all.
- ✅ **Off-record chats**: a chat set to no memory, and anything it taught companions is forgotten (`chatNoMemory`).
- ✅ **Pages beside the chat**: the AI's pages show next to the chat; move one into your tabs, or hand your tab to a chat (`chatPopOut`, `tabHand`).
- ✅ **Chat from anywhere**: Ctrl+Shift+A chats about the page; text typed in the address bar offers "Start a chat" (`aiAsk`).
- ✅ **Questions with options**: the AI asks via `ask_user`; the chat shows options and waits up to 10 min.
- ✅ **Replies**: Markdown renderer (no HTML injection), copyable draft cards, next-step suggestions from `>>` lines (`Markdown.tsx`).
- 🚧 **Step cards**: the companion's avatar sits left of a turn's first line, once per turn, its name only as the avatar's tooltip, and every card and paragraph lines up right of it; each run of actions is one card: icon tile, bold verb and muted target (a site shows as its host, the full address on hover), a check, "+ N more" opens the list (`AiSidebar.tsx` `Step`; branch `chatpolish`).
- ✅ **Skills**: Markdown files with front matter in the profile's skills folder; invoke as `/id` or give to a companion (`MainWindow.Ai.cs` `Skill`).
- ✅ **Library**: files the AI saved with `save_file`, one folder per chat; built-in viewer with CSV grid and Markdown (`Files.tsx`).
- ✅ **Set me up again**: typing it reopens setup's interview.

## Agent control (Still's chat and outside AI apps)

- ✅ **Browser tools**: list/open/switch/close tabs, navigate, back, forward, reload, read_page, find, click, type, press_key, scroll, wait_for, handle_dialog, upload_file, screenshot (`MainWindow.Agents.cs`).
- ✅ **Token-light page reads**: numbered element lines plus page text; ids persist across reads; walks open shadow roots and same-origin frames.
- ✅ **Lookups without tabs**: `web_search` and `read_url` load in one hidden page, closed after a minute unused (`MainWindow.Lookup.cs`).
- ✅ **AI tabs**: agents work in background tabs grouped under AI; tabs close 48 h after their chat goes quiet.
- ✅ **AI cursor and glow**: a named arrow in the companion's color glides to each click; a glow frames the page in use.
- ✅ **Take over and Stop**: Take over pauses the agent while you drive; Stop cancels and releases its tabs.
- 🚧 **Working pill restyle**: roomier "X is working…" pill with the full avatar, the current step cut with an ellipsis, Take over and Stop at the same height (`App.tsx` `PageControl`; branch `chatpolish`).
- ✅ **Permission layer**: every call is read, navigate, interact or sensitive; rules per site and companion: always, once per chat, or every time.
- ✅ **Sensitive steps**: buying, sending, deleting, posting forms, password/payment fields; even when allowed, an 8 s cancel countdown first.
- ✅ **Sensitive sites**: every click or keystroke on a listed site counts as sensitive (Preferences `SensitiveSites`).
- ✅ **AI permissions page**: defaults, rules per site and companion, sensitive sites, reset all (`Permissions.tsx`).
- ✅ **Ask when away**: idle 1 min, locked or minimized → the agent asks in its own chat; answer verified with a one-time code (`user_confirmed`).
- ✅ **File uploads by AI**: `upload_file` attaches files only after you approve in the bar.
- ✅ **Private tabs off-limits**: agents never see private tabs, saved passwords or cookies.

## MCP and CLI

- ✅ **MCP server**: `Still.exe --mcp`, stdio JSON-RPC; forwards to the running Still over a current-user pipe (`McpServer.cs`).
- ✅ **Off until enabled**: Settings "Let other AI apps use Still"; each app approved once in the agent bar (Preferences `AgentsEnabled`, `ApprovedAgents`).
- ✅ **Profiles from MCP**: `list_profiles`; every tool takes `profile` (opens it if closed) or `"temp"`.
- ✅ **Elicitation**: when you're away, MCP apps that support it ask you themselves; the AI never sees the question.
- ✅ **CLI**: `Still.exe --cli <tool> key=value`; prints JSON, saves screenshots as PNG; `help` lists tools.
- ✅ **Copy config**: Settings copies the MCP config with your real Still path (`App.tsx`).

## Companions

- ✅ **Crew**: seven ready companions with a job and voice (Zest, Bloom, Noon, Fizz, Mallow, Rivet, Glint) plus Make your own (`crew.tsx`).
- ✅ **Create**: Make your own: look, name, job, way of talking, AI, effort, skills; one is main; the last can't be deleted (`Home.tsx` `CompanionEditor`); a companion that exists edits in its profile.
- 🚧 **Companion library**: New companion (switcher +, Companions page, chat sidebar menu) opens Still's seven first, each a live mascot with name, role, one line and Add, or Added for ones you have; then Make your own and Paste a shared companion. A card opens a preview in the profile panel (General, Skills, Routines, Model; nothing saved until Add) (`crew.tsx` `CompanionLibrary`, `ProfilePanel.tsx` `preview`; branch `team`).
- 🚧 **Team chat**: Team chat (switcher, when you have two or more) picks companions for one thread, or @Name pulls one into a chat; each speaks as itself on its own AI app and session, asks others with @Name, and passes work with a HANDOFF line that shows as a card (Up next, On it, Done, Stopped); the team carries on by itself for up to 8 turns, you can jump in (the one you @name goes next) or stop it any time; what any member remembers in the chat is shared with the team and stays in that member's own memory; the speaker talks and lifts over the message box, the others listen, and a handoff waves on the sender and nods on the receiver (`MainWindow.Ai.cs` `TeamNext`, `Ai.swift` `teamNext`, `AiSidebar.tsx` `HandoffCard`, `TeamBar`; `tests/desktop/team.py`; branch `team`).
- 🚧 **Companion profile**: clicking any mascot (home, chat header, chat turns and hello, switcher, Companions page) slides in a panel: a switcher, ⋯ (rename, duplicate, reset to the crew original, fire or delete after a confirm) and close; tabs General (live mascot on a dotted stage, Edit look, Share, name, instructions, way of talking), Skills, Routines, Files (working folder, files it made), Memory, Plugins, Model (AI and thinking); saves as you type; Esc or the backdrop closes (`ProfilePanel.tsx`; branch `characters`).
- 🚧 **Share a companion**: Share copies its name, look, instructions, way of talking, thinking and role, never its memory, folder, skills, plugins or routines; pasting that on the Companions page or in the library adds it (`ProfilePanel.tsx`, `Home.tsx`; branch `characters`).
- 🚧 **Routines**: up to 20 per companion, each "do this at HH:MM on these days"; while Still is open it runs once that day in a new chat (up to 15 minutes late), approvals as in any chat (`MainWindow.Routines.cs`, `Routines.swift`; branch `characters`).
- ✅ **3D companions**: Blender-built glTF on a shared rig, rendered by three.js through one hidden WebGL canvas (`companion3d.ts`, `Mascot.tsx`, `tools/mascot`).
- ✅ **Still pictures**: small idle companions are cached renders in localStorage; WebGL off or reduced motion → stills only.
- 🚧 **Chat avatars**: under 40px, every role and Make your own is a full-body Blender avatar (96/144px, `assets/avatar`, `crew/blob.py` view `avatar`) that bobs while working; other looks get a full-body still, never a head crop (`Mascot.tsx`; branch `chatpolish`). Rigged companions there play 96px strips of their own clips by CSS steps: idle, working, thinking, a nod when done, a shrug on an error, a wave when they need you; reduced motion holds the first frame (`assets/sprite`; branch `characters`).
- 🚧 **Whole-body framing**: every 3D companion is framed from its own bounds swept over every state and gesture (rigs carry theirs in the file), centered with 12% clear and grown for the camera's perspective on deep bodies, at every size; the head and bust crops are gone except the look editor's extras grid (`companion3d.ts` `fit`; branch `chatpolish`).
- ✅ **Look editor**: color, eyes, brows, mouth, body shape, hair, hats, glasses, live 3D preview (`LookEditor.tsx`, `look.ts`, `face.ts`).
- ✅ **Old-name check**: once after an update, a companion with an old stock name asks whether to keep it.
- ✅ **Outside AI apps' look**: other AI apps working in Still wear their maker's look and color.
- 🚧 **Blob companions**: soft blobs in three.js, Zest to the character spec (branch `blobs`).
- 🚧 **Roles that own outcomes**: Hire picker; Zest, Bloom, Noon, Fizz, Mallow, Rivet, Glint pitch their roles; work interests (branch `roles`). Fizz is the Marketer (learns your voice, drafts only, never posts) and Glint the Researcher (short cited briefs) on branch `chatpolish`.
- 🚧 **Rigged, animated companions**: all eight (seven roles and Make your own, tinted to its color) are Blender rigs with 26 clips checked for intersections on every frame, shipped as 2.6–2.8 MB Draco glTF and played by a three.js mixer; idle blinks, glances and fidgets, the eyes and body follow the cursor, thinking and working look toward the tab, done nods or celebrates, an error shrugs or startles, needs-you waves, talking moves the mouth, hire celebrates, a rename or new look spins, and every move blends in and out (`rig.ts`, `assets/rig`, `companion3d.ts`; branch `characters`).
- 🚧 **Companions act on themselves**: change their look, settings and memory on request, each with Undo (branch `selfact`, uncommitted).

## Memory

- ✅ **Per-companion memory**: `companions/<id>/memory.json`, local plain JSON, used only in that companion's chats (`CompanionMemory.cs`).
- ✅ **remember / recall / forget tools**: Still's own chat only; recall ranks by shared words, core facts, then newest.
- ✅ **Never stored**: passwords, codes, keys, card/account numbers, form input the AI typed, anything from private tabs.
- ✅ **Past chats**: each finished chat is kept as a short memory; long memory keeps the 60 latest.
- ✅ **Memory page**: Settings → Memory: view, add, edit, forget, clear per companion (`Memory.tsx`).

## Plugins (Composio)

- 🚧 **Plugins**: your apps through Composio with your own API key, stored with DPAPI/Keychain; reads go ahead, writes ask first (branch `plugins`, `MainWindow.Plugins.cs`, `Plugins.swift`).
- 🚧 **Plugin settings and setup step**: Plugins tab with per-companion switches; "Connect your tools" setup step; Connect cards for unlinked apps (branch `plugins`).

## Extensions (Windows only)

- ✅ **Add from Chrome Web Store**: "Add to Still" on store pages; CRX downloaded, signature verified, permissions reviewed first (`MainWindow.ExtensionCatalog.cs`, `CrxPackage.cs`).
- ✅ **Manage extensions**: enable, disable, pin to toolbar, remove, open their pages, context menu (`MainWindow.BrowserTools.cs`).
- ✅ **Popups and side panels**: popups float under the toolbar, sized like Chrome; `chrome.sidePanel` docks right via a service-worker adapter (`MainWindow.ExtensionActions.cs`, `MainWindow.ExtensionPopup.cs`).

## Onboarding

- ✅ **Intro**: about 5 s, synced to `sounds/intro.ogg` and the companion's wake clip; skippable; replay from About (`Intro.tsx`).
- ✅ **Setup flow**: hello, import, pick your AI, crew, main companion, then Quick setup or Talk (`Welcome.tsx`).
- ✅ **Quick setup**: your name, interests, Classic/Modern layout, "You're in charge" demo; no AI runs.
- ✅ **Set it up with your companion**: your AI interviews you, then applies settings with an Undo each and saves memories (`MainWindow.Setup.cs`).
- ✅ **First task**: setup ends on a first task; typing a "no" counts as skip.
- ✅ **Tour**: coach marks on the new tab page that follow their targets through layout changes (`Tour.tsx`).
- ✅ **Sounds**: intro, setup and look editor only; off with the Sounds setting, system "no sounds" or reduced motion (`sound.ts`, `tools/sound`).
- 🚧 **Quieter setup sound**: setup plays only the intro and end jingle, 6 dB quieter (branch `fixes12`, done, not merged).
- 🚧 **Intro rebuilt for the blobs**: storyboard first (branch `intro12`, uncommitted).

## Settings

- ✅ **Settings page**: Ctrl+, : theme, search, new tab, layout, restore tabs, sounds, downloads, blocking, tracking, memory saver, autofill, passwords, AI, permissions, memory, profiles, import.
- ✅ **Open Still at sign-in**: per-user `HKCU\…\Run` entry (`StartupRegistration.cs`).
- ✅ **Default browser**: per-user HKCU registration; opens Windows Default apps for you to confirm (`BrowserRegistration.cs`).
- ✅ **About**: version, release notes, check for updates, replay the intro.
- 🚧 **Address-bar notice**: a notice ends when the page or tab changes (branch `fixes12`, done, not merged).

## Updates and install

- ✅ **Auto-update (Windows)**: checks GitHub at start and every 2 h, verifies SHA-256, installs on close or Restart to update (`MainWindow.Updates.cs`); installed copy only.
- ✅ **Update notice (Mac)**: same check; updating means downloading from the release page (`Tools.swift`).
- ✅ **Windows installer**: Inno Setup, per-user, no admin, installs WebView2 if missing; portable `Still.exe` too (`installer/Still.iss`).
- ✅ **Link hand-off**: tiny `StillOpen.exe` passes clicked links to the open Still over a pipe; single-instance (`launcher/StillOpen.c`).
- ✅ **Mac build**: `mac/build.sh` makes `Still.app`, `.dmg` and `Still-mac.zip`; GitHub Actions attaches the zip to releases (`.github/workflows/mac.yml`).

## Mac vs Windows

- ✅ **Same interface**: both hosts load the same React shell; page scripts are copied from the Windows app by `mac/build.sh`.
- ✅ **Mac parity**: chats, companions, memory, MCP/CLI, permissions, tabs, groups, split, private windows, profiles, passwords, import, blocking, downloads.
- **Windows only**: extensions; cookie/session import; automatic update install; audio output follow; DPAPI vault (Mac uses the Keychain).
- **Mac only**: Safari import (bookmarks, history; needs Full Disk Access); Touch ID instead of Windows Hello.
- **Mac blocking**: WebKit content rules (third-party url-filter) instead of request interception (`main.swift`).

## Dev and tests

- 🧪 **QA hooks**: test-only automation compiled in only with `StillQa=true` (`STILL_QA`), never in releases (`MainWindow.Qa.cs`, `Qa.swift`).
- ✅ **Desktop tests**: Python suites per area run against real windows on Windows and Mac (`tests/desktop/*.py`, `mac/test.sh`).
- 🚧 **Avatar edge check**: every look at 16 to 168px, through every frame of every state and gesture, fails if a drawn pixel touches its box (except the drop's fall from above); plus the avatar files' margins (`tests/desktop/avatars.py`; branch `chatpolish`).
- ✅ **Unit checks**: CRX signature and ID verification, unsafe URL and argument rejection (`tests/Still.PerformanceChecks`); speed and RAM in `tests/desktop/performance.py`.

## Known gaps

- Extensions don't exist on Mac; Mac can't import cookies, so sign-ins don't carry over.
- Not code-signed (Windows SmartScreen) or notarized (Mac); no independent security audit.
- ChatGPT and Grok adapters ship but live tests cover Claude only; custom agent manifests are untested.
- Agents can't read cross-origin frames or closed shadow roots.
- Companions on `welcome` still use placeholder bodies; the blob crew, roles, plugins and self-actions sit on unmerged branches.
- Team chat has no hand-off clip of its own: the sender waves and the receiver nods. Team chats are tested with a fake agent, not live.
- Routines only run while Still is open; one missed by more than 15 minutes waits for its next day.
- Firefox passwords can't be read when a primary password is set; Safari passwords need an export from the Passwords app.
- Local `main` holds older copies of 14 commits that `welcome` replaced; it needs a cleanup decision before release.
- Dropped: the Chromium port (`chromium`) and the animal mascots (`characters-app`), both unmerged.
