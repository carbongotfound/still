<div align="center">

# still.

**An open-source agent browser that works with the Claude, ChatGPT and Grok CLIs you're already signed into. No API keys.**

[**Download for Windows**](https://github.com/carbongotfound/still/releases/latest/download/Still-Setup-x64.exe) · [**Download for Mac**](https://github.com/carbongotfound/still/releases/latest/download/Still-mac.dmg) · [**Features**](#features) · [**Install**](#install) · [**Connect your AI**](#connect-your-ai) · [**Contributing**](#contributing)

[![Latest release](https://img.shields.io/github/v/release/carbongotfound/still?label=release)](https://github.com/carbongotfound/still/releases/latest)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE)
![Windows 10 | 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4)
![macOS 12+](https://img.shields.io/badge/macOS-12%2B-111111)
[![Good first issues](https://img.shields.io/github/issues/carbongotfound/still/good%20first%20issue?label=good%20first%20issues&color=7057ff)](https://github.com/carbongotfound/still/labels/good%20first%20issue)

</div>

<!-- LAUNCH FILM -->
<!-- The 2.0 launch film goes here, between the pitch and the first screenshot: an embed or a linked thumbnail. -->

<p align="center"><img src="docs/screenshots/home.png" alt="Still's new tab: Maya, the companion you work with, with the rest of the team behind her and the message box below" width="900"></p>

Still is a real browser with a team of AI companions built in. Hire the ones you need, give them a task, and they work in their own background tabs: reading pages, clicking, typing, filling forms and reporting back. They run on the Claude, ChatGPT or Grok app you already use, signed in to your own plan, so there's nothing new to pay for and no key to paste. Everything stays on your computer.

## Features

The highlights are below. [FEATURES.md](FEATURES.md) lists everything Still does.

### Companions you hire

Six companions come ready to hire. Each one owns a part of your work and has its own skills, memory, routines and way of talking.

| | Role | What to expect |
|---|---|---|
| **Jonah** | Sales | A one-page brief before every sales call, lead lists that fit who you sell to, follow-ups in your voice sent only on your OK |
| **Talia** | Growth | The biggest leak in your funnel with the number, small experiments ranked with one metric each, ready-to-run copy launched only on your OK |
| **Nora** | Planner | Tomorrow planned tonight with the most important thing first, a two-minute brief before each meeting, what's waiting on you with replies drafted |
| **Leo** | Marketing | One idea turned into posts for every platform, launch posts and newsletters in your voice, drafts only: nothing posts without you |
| **Ivan** | Engineer | Small tools and pages built and tested in Still, bug reports with steps to reproduce, specs with acceptance checks from messy feedback |
| **Maya** | Research | Deep research with cited sources, options compared side by side, claims fact-checked before you share them |
| **Make your own** | Any job | Pick its look, name, job, way of talking, AI and skills, and give it a prop to hold |

<p align="center"><img src="docs/screenshots/library.png" alt="Hire a companion: each card shows the character, its role and name, what it does in a line, Hire or Hired, and View profile" width="900"></p>

- **Hire in one click.** Each card shows the character, its role and what to expect. **View profile** shows its full instructions before you hire.
- **They get to work.** A new hire opens its first chat by itself, says what it will do first and starts on real work.
- **Yours to shape.** Edit a companion's look, instructions, skills, routines, files and model. Its memory stays on your computer, and you can see, edit and forget anything it keeps.
- **They work together.** A companion can ask a teammate for help or hand work over, and you see who asked whom.

### The message box

<p align="center"><img src="docs/screenshots/composer.png" alt="The message box with a tab attached with #, two files dropped in, and the @ list of companions open" width="900"></p>

- **`#` attaches a tab** and the companion reads that page. Private tabs never appear.
- **`@` pulls in a teammate**, and **`/` runs one of your skills**.
- **Drop in files.** Text, code, PDFs and images, up to 10 a message, with every AI.

### Plugins

<p align="center"><img src="docs/screenshots/plugins.png" alt="The Plugins page: connected apps at the top, one search for apps and skills, category chips, then Recommended apps two across, each with its logo and Connect or a Connected check" width="900"></p>

- **Hundreds of apps.** Gmail, Slack, Notion, GitHub and the rest of [Composio](https://composio.dev)'s catalog, connected with **your own** Composio API key. Still keeps the key in Windows DPAPI or the macOS Keychain and only ever shows its last four characters.
- **Light on tokens.** Companions don't carry every app's tools. They look up what's connected and load one app's actions only when a task needs it.
- **Reads go ahead, writes ask first.** Anything that sends, posts, deletes, pays or changes data waits for your OK. If a companion needs an app you haven't connected, it asks you to connect it.

### You stay in charge

<p align="center"><img src="docs/screenshots/permissions.png" alt="The Permissions button on a Wikipedia page: Allow, Ask or Block for camera, microphone, location and more" width="900"></p>

- **Per-site permissions.** Allow, Ask or Block camera, microphone, location, notifications and more, site by site.
- **AI permissions.** Set rules per site and per companion. Buying, sending, deleting and payment fields always wait on an 8 second countdown you can cancel.
- **Watch, take over or stop.** A colored cursor shows where the companion clicks. **Take over** pauses it while you drive, and **Stop** ends the run.

### A full browser

- Tabs, groups, split view, private windows and profiles, with tabs on top or on the side.
- Ads and trackers blocked, YouTube ads included, and one-click import from Chrome, Edge, Brave, Opera GX, Vivaldi and Firefox.
- A password manager encrypted with Windows DPAPI or the macOS Keychain. Companions never see saved passwords.

### Use Still from other AI apps

Turn on **Settings > Models > Let other AI apps use Still** and Claude Code, Claude Desktop, Cursor or any MCP app can drive it. Each app asks once before it starts.

```powershell
claude mcp add still -- "C:\Users\<you>\AppData\Local\Programs\Still\Still.exe" --mcp
```

Settings has **Copy config** with your real path filled in, and `Still.exe --cli help` lists the one-step commands for agents without MCP.

<table>
<tr>
<td width="50%"><img src="docs/screenshots/profile.png" alt="Maya's profile: her live character, instructions, skills, routines, files, memory and model"></td>
<td width="50%"><img src="docs/screenshots/settings.png" alt="Settings, Models page: chat titles and AI models"></td>
</tr>
<tr>
<td align="center">A companion's profile</td>
<td align="center">Settings</td>
</tr>
</table>

## Install

### Windows

1. Download [**Still-Setup-x64.exe**](https://github.com/carbongotfound/still/releases/latest/download/Still-Setup-x64.exe) and run it. No admin rights needed.
2. Still isn't code-signed yet, so SmartScreen may warn the first time. Choose **More info > Run anyway**.
3. Setup walks you through importing your old browser, picking your AI and hiring your first companions.

Still updates itself after that.

### macOS

1. Download [**Still-mac.dmg**](https://github.com/carbongotfound/still/releases/latest/download/Still-mac.dmg), open it and drag **Still** to **Applications**. It runs natively on Apple silicon and Intel.
2. Still isn't notarized yet, so the first time, right-click Still and choose **Open**. On macOS 15, open it once, then choose **Open Anyway** in **System Settings > Privacy & Security**.

### Requirements

- **Windows** 10 (1809 or later) or 11, x64. Setup installs the Microsoft Edge WebView2 Runtime if it's missing.
- **macOS** 12 or later.
- **An AI app** for the companions: Claude Code, ChatGPT's CLI from OpenAI, or Grok Build, signed in to your own account. Setup can install and sign in for you. Still works as a browser without one.

## Connect your AI

Still runs the AI's own command-line app in the background, signed in to your plan. It never asks for an API key, never reads the app's login, and removes API-key settings from each run so nothing is billed to an API account.

| AI | What Still runs | How it connects |
|---|---|---|
| **Claude** | [Claude Code](https://claude.com/product/claude-code) | **Install it for me** runs Anthropic's official installer. **Sign in with Anthropic** opens Claude's own sign-in. |
| **ChatGPT** | OpenAI's agent CLI | **Install it for me** installs it from npm. **Sign in with OpenAI** uses your ChatGPT account. API-key logins are ignored. |
| **Grok** | [Grok Build](https://x.ai/cli) | **Install it for me** runs xAI's official installer. **Sign in with xAI** opens xAI's device sign-in. |

The buttons are on each AI's tile in setup and in the chat's AI picker. If the app is already installed and signed in, Still finds it. Switch AI anytime, even halfway through a chat: the chat moves over with its history.

## Privacy

- **No telemetry.** No Still account, no analytics. The only request Still makes on its own is a check of GitHub for a newer release.
- **Agents never see private tabs, saved passwords or cookies.** Fields that hold saved logins read as hidden. When a companion reaches a sign-in page it pauses and asks you to sign in, then carries on.
- **Private tabs never save passwords, history or form data.**
- **Your data stays local** in `%LOCALAPPDATA%\Still` on Windows and `~/Library/Application Support/Still` on the Mac.
- **Plugins are opt-in.** Still talks to Composio only after you paste your own key: to list its apps and their logos, and to work in the apps you connect.

## Build from source

**Windows** needs the [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0) (10.0.401 or a later patch) and Node 22.12 or newer.

```powershell
git clone https://github.com/carbongotfound/still
cd still
./build.ps1              # UI tests, lint and build, then a self-contained Still.exe in artifacts/Still
./build.ps1 -Installer   # also builds the installer (needs Inno Setup 7's ISCC.exe on your PATH)
```

**macOS** needs Xcode 15 or newer. `sh mac/build.sh` builds `mac/build/Still.app`, a `.dmg` and `Still-mac.zip` from the same interface.

More detail, including how to run the tests, is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Contributing

First-time contributors are welcome. Pick one of the [good first issues](https://github.com/carbongotfound/still/labels/good%20first%20issue), or [open an issue](https://github.com/carbongotfound/still/issues/new/choose) with a bug or an idea. [CONTRIBUTING.md](CONTRIBUTING.md) covers setting up, running the tests, how the code is laid out, and adding a companion, skill or plugin. Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

[FEATURES.md](FEATURES.md) maps every feature to the code that runs it.

## Security

See [SECURITY.md](SECURITY.md) and the [security review](docs/SECURITY-REVIEW.md). Still has had internal code reviews but no independent audit yet, so please report vulnerabilities privately rather than in a public issue.

## License

Still is open source under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later), © 2026 Carbon. Versions released before this change stay available under the MIT license.

The companions, their animations and props, the app icon and the two setup sounds are original work made for Still and covered by the same license. Everything Still bundles from others keeps its own license: the list is in [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) and every license text is in [Licenses](Licenses). Claude, ChatGPT and Grok and their logos belong to Anthropic, OpenAI and xAI. Still isn't affiliated with them.
