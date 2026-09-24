# Contributing

Build with Windows 11 x64, .NET SDK 10.0.401 (or a later 10.0.4xx patch) and Node 24. Run `./build.ps1` from this directory. Inno Setup 7 is optional unless packaging the installer.

Keep changes small and include the problem, behavior, and validation. Use actual shadcn/ui components, retain black mode and reduced-motion support, and preserve keyboard labels. Test with isolated profiles, synthetic passwords, and local fixtures. Never commit browsing data, vault files, signing keys, downloaded extensions, or test credentials.

Run frontend lint/build and `node --test tests/suggestions.test.ts` in still-ui. Native regression tests are under tests; automation-enabled builds must never be released. For changes affecting security boundaries, include a negative test (wrong origin, invalid path, cancellation, or permission denied). A compile or scripted click alone is not proof of interactive behavior.

Keep third-party notices and lockfiles. Original Still code is MIT licensed; dependencies keep their own licenses. No Office Commun source code is included. Do not claim affiliation with Office Commun, Microsoft, shadcn, or uBlock Origin.
