# Contributing to Still

Thanks for helping. Bug reports, ideas, docs fixes and code are all welcome, and you don't need to be a C# or Swift expert to start. If this is your first contribution, the [good first issues](https://github.com/carbongotfound/still/labels/good%20first%20issue) are small, real problems with a pointer to the code. Comment on one to say you're taking it, and ask questions in the issue whenever you're stuck.

## Set up

### Windows (the main host)

- Windows 10 or 11, x64
- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0), 10.0.401 or a later patch (`global.json` pins it)
- Node 22.12 or newer
- Python 3.11 or newer with Pillow (`pip install pillow`), for the desktop tests
- Optional: [Inno Setup 7](https://jrsoftware.org/isinfo.php) to build the installer

```powershell
git clone https://github.com/carbongotfound/still
cd still
./build.ps1 -Qa
```

### macOS

- macOS 13 or newer with Xcode 15 or newer
- Node 22.12 or newer, only if you change the interface

```sh
git clone https://github.com/carbongotfound/still
cd still
ARCH=arm64 QA=1 sh mac/build.sh
```

The Mac app loads the same interface as Windows from `still/Shell`, which is committed, so you only need Node when you change `still-ui`.

## Run, test and build

### Run a dev copy

`./build.ps1 -Qa` builds a test copy into `artifacts/Still-QA`. Run it on its own profile folder so it never touches your real browser data and can run next to an installed Still:

```powershell
artifacts\Still-QA\Still.exe --qa --profile D:\still-dev --profiles-root D:\still-dev
```

After changing only the interface, rebuild it and then the app:

```powershell
cd still-ui; npm run build; cd ..       # writes still/Shell
dotnet publish still/Still.csproj -c Release -r win-x64 --self-contained true -p:StillQa=true -p:DebugType=None -o artifacts/Still-QA
```

On the Mac, `QA=1 sh mac/build.sh` builds `mac/build/qa/Still.app`.

### Test

| What | Command |
|---|---|
| Interface types | `cd still-ui; npx tsc -p tsconfig.app.json --noEmit` |
| Interface lint | `cd still-ui; npm run lint` |
| Interface unit tests | `cd still-ui; node --test tests/suggestions.test.ts` |
| One desktop suite | `python tests/desktop/<suite>.py artifacts/Still-QA/Still.exe` |
| .NET checks | `dotnet run --project tests/Still.PerformanceChecks` |
| Mac suites | `sh mac/test.sh` |

Each desktop suite starts a real Still window on a throwaway profile, drives it through the QA hooks and prints `PASS` or `FAIL` per check. Pick the suites for the area you changed (`tabs`, `passwords`, `attach`, `exchange`, `plugins`, `settings` and so on; there's one file per area in `tests/desktop`). Set `STILL_QA_POS=-1800,80` to open test windows on a second monitor. Tests never talk to a real AI: they use a stand-in agent.

The QA hooks are compiled in only with `-p:StillQa=true` (or `QA=1` on the Mac). Never ship or share a QA build.

### Build a release copy

```powershell
./build.ps1              # artifacts/Still/Still.exe
./build.ps1 -Installer   # plus the installer in artifacts/ (needs ISCC.exe on your PATH)
```

On the Mac, `sh mac/build.sh` builds `Still.app`, `Still-<version>.dmg` and `Still-mac.zip` in `mac/build`. The version comes from `still/Still.csproj` for both.

## How the code is laid out

| Folder | What's in it |
|---|---|
| `still/` | The Windows host in C#: WPF window, WebView2 tabs, AI runs, MCP server, passwords, plugins |
| `still/Assets/` | The six companions' role setups (`roles/*.md`), the setup prompt and page scripts |
| `still/Shell/` | The built interface, written by `still-ui` and committed so both hosts build without Node |
| `still-ui/` | The interface both hosts load: React, TypeScript, shadcn/ui and three.js companions |
| `mac/` | The macOS host in Swift (AppKit and WebKit), with its build and test scripts |
| `tests/desktop/` | Python suites that drive a real Still window, one file per area |
| `tests/Still.PerformanceChecks/` | .NET checks for extension signatures and unsafe URLs and arguments |
| `installer/` | The Inno Setup script for the Windows installer |
| `launcher/` | `StillOpen.c`, the small program that hands clicked links to the running Still |
| `tools/sound/` | Makes the intro and setup sounds in code |
| `docs/` | Screenshots, the security review and verification notes |
| `Licenses/` | The license of everything Still bundles, listed in `THIRD-PARTY-NOTICES.txt` |

[FEATURES.md](FEATURES.md) maps every feature to the file that runs it. It's the fastest way to find where something lives.

## Code style

- **Match the code around you**: its naming, its comment density and its idioms. A change should read like the rest of the file.
- **Keep it small.** Reuse what's already there before adding a helper, and prefer the platform over a new dependency. A new dependency needs a reason in the PR and an MIT-compatible license, added to `THIRD-PARTY-NOTICES.txt` and `Licenses/`.
- **Comments say why**, in plain sentences, when the code can't.
- **Interface:** use the shadcn/ui components in `still-ui/src/components/ui`, keep light and dark themes and reduced motion working, and give every control a keyboard path and a label.
- **Words in the app** are short, plain and confident. Say what a thing does. Companions are hired (Hire and Hired). No em dashes.
- **Both hosts:** a change to how Still behaves usually needs the same change in `mac/Sources/Still`. If you can't build for the Mac, say so in the PR and someone will help.
- `npm run lint` and `tsc` pass with no errors, and the C# build adds no new warnings.

## Making a good pull request

1. **One change per PR.** Small PRs get reviewed fast.
2. **Test it.** Run the suites for the area you touched and list them in the PR. For a fix, add a check that fails without it. A change to a security boundary (origins, paths, permissions, passwords) needs a check that the wrong case is refused.
3. **Update [FEATURES.md](FEATURES.md) in the same commit** whenever you add, change or remove a feature: one line per feature, with its status and where it lives, plus the Known gaps list.
4. **Show it.** Add before and after screenshots for anything you can see.
5. **Keep personal data out.** Never commit browsing data, profiles, vault files, API keys or real passwords. Tests use throwaway profiles and made-up data.

The PR template has this checklist.

## Reporting bugs and suggesting features

- **Bugs:** [open a bug report](https://github.com/carbongotfound/still/issues/new?template=bug_report.yml). Include your Still version (**Settings > About**), your OS, which AI you use, and the steps that make it happen. Never paste passwords, cookies, keys or private browsing data.
- **Ideas:** [open a feature request](https://github.com/carbongotfound/still/issues/new?template=feature_request.yml). Describe the problem first, then the change you'd like.
- **Security problems:** don't open a public issue. See [SECURITY.md](SECURITY.md).

## Adding a companion, skill or plugin

### A companion

Anyone can make a companion in the app with **Make your own**, then **Share** it from its profile. Pasting that on the Companions page adds it for someone else. No code needed.

To add one to Still's own library, open a feature request first so we can agree on the role. Then:

1. Add it to `PREMADES` in `still-ui/src/crew.tsx`: its role id, name, role, the three things to expect, what it says on hover, how it learns, the apps it uses, its starter routine (off until the user turns it on), its job, its tone, the tasks it's good at and its look.
2. Write its role setup in `still/Assets/roles/<role>.md`: how it plans, does, checks and reports, how it opens its first chat, and its standards. Read the six that are there first. `mac/build.sh` copies the folder for the Mac.
3. The six have their own Blender models in `still-ui/src/assets/rig`. Their Blender sources aren't in the repo yet, so a new companion starts on the Make your own model: give it a `bean` look in its own color with no prop (`rigFor` in `still-ui/src/rig.ts`).
4. Update `tests/desktop/library.py` and `companions.py`, which count the library, and FEATURES.md.

### A skill

A skill is a Markdown file with a short header, kept in the profile's `skills` folder. Make one in **Skills & plugins > New skill**, or write the file yourself:

```markdown
---
name: Weekly report
description: Turns this week's numbers into a one-page summary
when: The user asks for a weekly report or a summary of the week
---

1. Ask which numbers matter this week.
2. Collect them from the open tabs.
3. Write one page: what changed, why, and what to do next.
```

Give it to a companion from Skills & plugins, or run it with `/` in the message box. If you think a skill belongs in Still for everyone, open a feature request with the file.

### A plugin

Plugins come from [Composio](https://composio.dev)'s catalog, so any app Composio supports can already be connected from **Skills & plugins > Add an app**. To give an app its proper name in Still and a place in setup's list, add its Composio slug to `POPULAR` in `still-ui/src/Plugins.tsx`, `PluginNames` in `still/MainWindow.Plugins.cs` and `pluginNames` in `mac/Sources/Still/Plugins.swift`. To have a companion work in it, add the slug to that companion's `uses` in `crew.tsx`.

Plugins follow one rule: reads go ahead, and anything that sends, posts, deletes, pays or changes data asks the user first. Keep that true for any new action.

## Code of Conduct

Everyone taking part in Still follows the [Code of Conduct](CODE_OF_CONDUCT.md). Be kind, assume good intent, and help newcomers find their way.

## License

By contributing, you agree that your contributions are licensed under the [MIT license](LICENSE).
