# Security and release status

Still 1.3 is a preview, not an audited or certified browser. Do not advertise it as industrial-grade. Before a public stable release: obtain trusted Windows code signing, arrange independent review of the native bridge/profile/import/extension/vault code, establish an authenticated update channel and vulnerability reporting contact, and test multiple clean Windows installations and WebView2 versions.

## Current protections

- Chromium/WebView2 provides sandboxing, HTTPS verification, reputation checks and tracking prevention. Still does not disable certificate validation or engine sandboxing.
- The local interface uses a restrictive Content Security Policy. Its privileged bridge accepts messages only from the exact local main document. Host objects and shell frame navigation are disabled. Websites have no generic browser-management bridge.
- Passwords use Windows DPAPI for the current Windows account. Save, fill and update offers are separately opt-in. Filling checks the exact origin, excludes private tabs and never submits a form. This is not a separate master-password vault, and software running as your Windows user can access your data.
- Profile deletion is never a background cleanup action. The native dialog requires the exact profile name. Open profiles are locked. Default cannot be deleted through Still; resetting it requires the same confirmation from another profile. Links/junctions are rejected before deletion. No claim is made that Still prevents external filesystem tools or malware from deleting files.
- Suggestions use local history and bookmarks. Typing sends no search-provider request. Private tabs exclude normal history suggestions and do not persist visits. Clearing history clears its suggestion source.
- Official uBlock Origin Lite downloads come from the upstream GitHub release, with a matching publisher SHA-256 digest and permission review. Installed files must match the reviewed content. This protects transfer integrity; it is not independent authentication of a compromised upstream account. Unpacked extensions are code chosen and trusted by the user.
- Test automation is compiled out of production. Building with `-p:StillQa=true` intentionally exposes a current-user named pipe for testing; never distribute that build.

## Known boundaries

Still has no application auto-updater; publish maintained, signed releases before supporting other users. WebView2 Evergreen updates separately. Extensions update only when the user checks for updates and approves the new release. Chromium extension API compatibility is limited by WebView2. Ad blocking is not a guarantee that every YouTube ad is removed; see VERIFICATION.md for the actual observation.

The installer is currently unsigned. Checksums detect altered downloads only if obtained through a trusted channel. The included Microsoft runtime bootstrapper is signed by Microsoft and checked during packaging. Still's installer runs per-user, preserves profiles on uninstall, and does not remove the shared runtime. Uninstall through Windows Settings > Apps > Installed apps > Still, or the Start-menu Uninstall Still shortcut.

## Reporting

Before publishing a GitHub repository, enable private vulnerability reporting in repository settings and add its private reporting link here. Until that exists, this source package has no public security-reporting endpoint. Do not post passwords, browsing profiles, recovery files or exploit details in public issues. Include the Still version, WebView2 version and a synthetic reproduction when reporting privately.
