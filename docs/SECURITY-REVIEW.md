# Security review: Still 1.4.1

**Date:** 2026-09-24 · **Scope:** the full source in this repository · **Type:** internal code review. This is **not** an independent third-party audit.

## Summary

No critical issues were found. Two medium-risk issues were found and fixed in 1.4.1. All npm and NuGet dependencies had zero known vulnerabilities (`npm audit`, `dotnet list package --vulnerable`) on the review date.

## Fixed in 1.4.1

| # | Severity | Issue | Fix |
|---|---|---|---|
| 1 | Medium | **Auto-fill could target hidden fields.** Automatic password fill accepted any rendered password field on the matching origin, including a tiny, transparent or covered field. A malicious script running on that site (for example through XSS or a compromised ad script) could plant one and read the filled password. | Fill now requires a real, visible field: at least 24×10 px, opacity ≥ 0.5, `visibility: visible`, not covered by another element when on screen, and not disabled or read-only. The same rule applies to the username field. |
| 2 | Low | **Import leftovers after a crash.** If Still crashed mid-import, snapshot copies of the source browser's still-encrypted `Login Data` / `Cookies` databases could stay in the profile folder. | Leftover snapshots are deleted when Still starts and before each import. |

## Reviewed and found sound

- **UI isolation.** The interface runs in its own WebView on a virtual host (`still.internal`). It can't be navigated elsewhere, and host commands are accepted only from that exact origin. Website tabs can't send it commands.
- **Messages from websites.** Login and "hide element" messages are checked against the tab's actual origin from WebView2 (`e.Source`), not against values the page supplies. Per-tab random tokens stop stale scripts from sending messages. Payload sizes are capped.
- **Password vault.** Passwords are encrypted with Windows DPAPI (current user). Filling works only on the exact origin, over HTTPS (or loopback), without certificate errors, only in the top frame, and never when the form posts to another origin. Private tabs never capture or fill passwords. Copied passwords are cleared from the clipboard after 30 seconds.
- **Browser import.** Only the current Windows user's own data is decrypted, with that browser's DPAPI-wrapped key. Chrome's app-bound (v20) values are detected and skipped. Source files are read-only and never modified. URLs are allow-listed to http/https, and sizes and counts are capped.
- **TLS.** Pages with invalid certificates are always blocked, with no click-through.
- **Navigation.** Non-web schemes are blocked; `mailto:` and `tel:` ask first. Pop-ups need a user gesture.
- **Extensions.** Chrome Web Store installs download the CRX over HTTPS from Google's update service only (the CRX signature itself is not verified). ZIP extraction rejects path traversal, symlinks, absolute paths and oversized archives, and shows a permission review before installing.
- **Permissions.** Camera, microphone, location and similar requests use a native Yes/No prompt per request.
- **Automation interface.** The QA named pipe is compiled only into builds with `StillQa=true`. It doesn't exist in release builds.

## Known limitations (accepted)

- **The app isn't code-signed**, so users have to trust the GitHub release. Check the SHA-256 on the release page.
- **No automatic updater.** Browser engine updates come from Microsoft's Evergreen WebView2 runtime, which updates itself. Still's own fixes need a manual download.
- **DPAPI protects data at rest only.** Malware running as your Windows user can read it, which is the same as other browsers on Windows.
- **Once a password is filled into a page, that page's scripts can read it.** This is true of every browser. Automatic fill can be turned off in Passwords.
- **"Close and include sign-ins" force-closes the source browser's remaining background processes** after asking its windows to close. For Chrome, Edge and Brave this affects every profile of that browser.

## Reporting

Please report vulnerabilities privately as described in [SECURITY.md](../SECURITY.md).
