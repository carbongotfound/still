# Desktop regression checks

Use Windows x64, Python 3, .NET 10, and the WebView2 Evergreen Runtime. These scripts launch **QA builds only** with fresh profiles under ignored `artifacts/` directories. Run desktop scripts sequentially so they do not compete for focus or distort startup timings. Do not distribute a QA executable.

Build the QA executable:

```powershell
.\build.ps1 -Qa
```

The extension fixture needs a public store package to obtain a developer public key. Download the official Cold Turkey package without installing it in your normal profile:

```powershell
Invoke-WebRequest 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=140.0&acceptformat=crx2,crx3&x=id%3Dpganeibhckoanndahmnfggfoeofncnii%26uc' -OutFile artifacts/cold-turkey.crx
dotnet run --project tests/Still.PerformanceChecks -c Release -- artifacts/cold-turkey.crx pganeibhckoanndahmnfggfoeofncnii
python tests/desktop/features.py artifacts/Still-QA/Still.exe --cold-turkey
python tests/desktop/performance.py artifacts/Still-QA/Still.exe
```

`features.py` checks download opening, embedded reader/login scripts, extension identity, service workers, storage, content scripts, real tab queries, native messaging, and simultaneous external links. Its temporary file association and native messaging registration use unique names and are removed in `finally`. The optional official Cold Turkey check stops at the consent screen; it does not consent, change blocking rules, or verify actual blocking.

`performance.py` measures the entire app process tree, compares loaded and idle resident RAM, and checks page state, navigation history, cookies, local storage, session saving, and disabling memory saver. It then waits another idle period to check that muted video and WebRTC stay awake. Each idle period lasts 75 seconds. Resident RAM and private committed allocations are recorded separately. Live/shared renderers are deliberately protected, so the idle-page RAM reduction is not a promise for media workloads.

For a baseline comparison, build the earlier commit with `-p:StillQa=true` and pass both single-file executables:

```powershell
python tests/desktop/startup.py artifacts/baseline-qa-single/Still.exe artifacts/Still-QA/Still.exe --cold-bundle
```

This runs four sequential launch/quit cycles per executable. Cycle zero uses a new profile and a fresh native extraction directory; the next cycles reuse them. It measures visible-window time, usable-page/interface time, and links delivered to a running instance. Startup timing depends on machine load and WebView runtime caching.

After publishing a **production** build, verify that QA code is absent and its embedded UI/scripts match source:

```powershell
dotnet run --project tests/Still.ReleaseChecks -c Release -- still/bin/Release/net10.0-windows/win-x64/Still.dll .
```

Profiles, downloaded packages, test native hosts, binaries, and results stay in `artifacts/` and must not be committed.

Tab overflow regression (starts with ten tabs in a short window, clicks through to thirty, checks both layouts, Ctrl T, and session saving):

```powershell
python tests/desktop/tabs.py artifacts/Still-QA/Still.exe
```
