# Security

Still 2.10 is a browser for Windows and macOS. It is not audited or certified. This page says what Still protects, where its protection ends, and how to report a problem.

## Releases and updates

- **Windows installers aren't code-signed**, so Windows may warn before running one. SignPath Foundation turned down the signing application because the project doesn't have enough public visibility yet. The installer runs per user and keeps your profiles when you uninstall.
- **Windows updates**: the installed copy checks GitHub's latest release at startup and every 2 hours, downloads the installer and checks it against the SHA-256 that GitHub publishes for it before installing. That catches a damaged or swapped download, not a release published from a compromised GitHub account. With Update automatically off, it downloads only when you click Update.
- **The Mac app is ad-hoc signed and not notarized**, so macOS asks once on first launch (right-click, then Open). Updates come through Sparkle and install only when their EdDSA signature matches the public key built into Still. The signing key isn't in this repository.
- **The engine**: Windows uses Microsoft's Evergreen WebView2 runtime, which updates itself. The Mac uses the system's WebKit, which updates with macOS.
- **Test builds** (`-p:StillQa=true` on Windows, `QA=1` on the Mac) open a test channel for the current user: a named pipe on Windows, a Unix socket on the Mac. Release builds don't contain it. Never share a test build.

## The browser

- Pages run in the engine's own sandbox. Still doesn't turn off certificate checks or the sandbox, and a page with an invalid certificate is blocked with no way to click through.
- Still's own interface runs in its own view. It takes commands only from that exact page, so websites can't send it commands. Messages from websites, such as a login being typed, are checked against the tab's real site, not what the page claims.
- Links that open another app (`mailto:`, Discord, Zoom and the like) ask first in Still's bar. Only a real click on the page uses or saves a yes, and Settings can forget them all. On Windows the link reaches the app as one address.
- Camera, microphone, location, pop-ups and the other site permissions ask in Still's bar, with rules per site in the toolbar's Permissions menu.
- Private windows keep nothing, and each one has its own engine profile, so two never share a sign-in.
- **Extensions (Windows only)**: Chrome Web Store packages have their developer signature and extension ID checked, you review the permissions before installing, and the files an extension names must stay in its folder. This checks the package, not whether the extension behaves well. Unpacked extensions are code you choose to trust.
- On Windows, deleting a profile always asks in Still's own dialog, Default can only be reset, and Still won't delete through a linked folder.

## Saved logins and keys

- Passwords, API keys and the Composio key are encrypted with Windows DPAPI for your Windows account, or kept in the macOS Keychain. There's no separate master password, and software running as you can reach them, as with other browsers.
- A login fills only on the exact site it was saved for, never in private tabs, and only after you click or type in a visible login field. A login list that the page hides or covers fills nothing. On a page without HTTPS, filling asks first.
- A copied password clears from the clipboard after 30 seconds and is marked so clipboard history and clipboard managers skip it.
- Once a password is in a page, that page's scripts can read it, as in every browser.

## AI companions and connected AI apps

- Still runs AI apps (Claude Code, the ChatGPT app, Gemini CLI and others) on your computer with their own sign-ins, and doesn't read those sign-ins. API-key variables are removed from every app except Claude, and an API provider key you add in Still never goes into an app's environment.
- Every step an AI takes on a page is a read, a navigation, an interaction or a sensitive step. You set rules per site and per companion (always, once per chat, every time) on the AI permissions page. Always on this site covers only that site and the companion who asked.
- For Still's companions, sensitive steps (buying, sending, deleting, posting forms, password and payment fields) ask by default, and even when allowed they wait through an 8-second countdown you can cancel. Marking a site as sensitive makes every click and keystroke there count as sensitive.
- An approval is for what its card showed. If the tab, the site or the control changes before the step runs, Still asks again. Steps on a page run one at a time, and each approval works once.
- After a chat reads from the web, opening a site you didn't name and the chat hasn't used asks first, and so does any site on your own computer or network.
- AIs can't fill saved logins, fields holding saved usernames read as hidden to them, sign-in pages hand the page back to you, and saved logins are taken out of everything that goes back to an AI.
- An AI's upload card shows every file's full path and the site that gets it. Keys and Still's own data can't be attached by an AI.
- Other AI apps connected to Still, through its MCP server or the `--cli` command, must say who they are, and go through the same rules and approval cards.

## Known limits

- Still checks what it can see of a control before a step runs: its words, its kind, where a form sends things, the site and the tab. A page's own scripts can still do something the label doesn't say, and inside another site's frame Still can't look.
- Spotting sensitive steps by their words and fields is best effort. Mark sites you care about as sensitive.
- Pages an AI reads can try to steer it. The rules above limit what it can do without you; they don't make what it read trustworthy.
- YouTube ad handling doesn't promise that every ad is removed.

## Reporting

Report a vulnerability privately through GitHub: this repository's **Security** tab, then **Report a vulnerability**. Please don't put passwords, profiles, recovery files or exploit details in public issues. Include the Still version, your system and engine version, and a reproduction that uses test data.
