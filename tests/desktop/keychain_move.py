"""Mac: Still reads the Keychain only when you import. Import > An older Still brings the logins and keys an older Still kept
for this profile into files encrypted for this Mac; starting Still doesn't. The test build reads made-up items instead of
the Keychain (STILL_QA_OLD_KEYCHAIN), so this never touches the Keychain or brings up a macOS question. Also: a file this
Mac can't open is kept beside the new one, never written over.

Run: python tests/desktop/keychain_move.py <the QA build's Still binary>
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
FAILED = []
LISTEN = """window.__tools = {};
window.chrome.webview.addEventListener('message', e => { const d = e.data; if (d?.kind === 'tools') __tools[d.name] = d.data })"""


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def logins(process):
    js(process, LISTEN)
    send(process, "refreshTools", name="passwords")
    return [v["username"] for v in until(lambda: js(process, "window.__tools.passwords?.vault ?? null"), 5) or []]


def toasts(process):
    return js(process, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.textContent).join(' ')") or ""


def opened(profile, old=None):
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False}), encoding="utf-8")
    return launch(EXE, profile, {**os.environ, **({"STILL_QA_OLD_KEYCHAIN": json.dumps(old)} if old is not None else {})})


def close(process):
    try:
        rpc(process, "quit")
        process.wait(timeout=20)
    except Exception:
        process.kill()
    time.sleep(1)


def main():
    if not MAC:
        print("PASSED (Mac only: Windows keeps DPAPI)")
        return 0
    # Not resolved: Still names a profile by its path as macOS standardizes it (/var/..., not /private/var/...).
    profile, other = (Path(tempfile.mkdtemp(prefix="still-keys-")) for _ in range(2))
    home = str(profile)
    kim = {"id": "k1", "origin": "https://moved.example", "username": "kim@example.com", "password": "Moved-Over-91"}
    lee = {"id": "k2", "origin": "https://moved.example", "username": "lee@example.com", "password": "Other-Profile-7"}
    old = [["Still logins", home, json.dumps([kim])], ["Still Composio key", home, "ak_moved_over_1234"],
           ["Still API key", home + "#api-moved1", "sk-moved-over-5678"],
           ["Still logins", home + "-other", json.dumps([lee])], ["Still API key", home + "#../bad", "sk-not-this-one"]]
    secrets = [b"Moved-Over-91", b"ak_moved_over_1234", b"sk-moved-over-5678"]
    files = [profile / "logins.sealed", profile / "composio.sealed", profile / "api-keys" / "api-moved1.sealed"]
    try:
        p = opened(profile, old)
        try:
            time.sleep(3)
            check(not any(f.exists() for f in files), "Starting brings nothing over from the Keychain")
            send(p, "importOldStill")
            check(until(lambda: all(f.exists() for f in files), 10), "Import > An older Still brings over the login, the Composio key and the API key")
            check(all(s not in f.read_bytes() for f in files if f.exists() for s in secrets), "None of them is in plain text there")
            check(all(f.stat().st_mode & 0o077 == 0 for f in files if f.exists()), "Only the user can read the files")
            check(logins(p) == ["kim@example.com"], "Still opens the moved login, and not another profile's")
            keys = sorted(f.name for f in (profile / "api-keys").iterdir()) if (profile / "api-keys").exists() else []
            check(keys == ["api-moved1.sealed"], f"and only this profile's well-formed key ({keys})")
            check(until(lambda: "Brought over 1 login and 2 keys from an older Still" in toasts(p), 5), f"It says what came over ({toasts(p)!r})")
            send(p, "importOldStill")
            check(until(lambda: "Nothing new came over" in toasts(p), 5), "Importing again brings nothing twice")
            check(logins(p) == ["kim@example.com"], "and the login is there once")
        finally:
            close(p)

        # A logins file this Mac can't open (from another Mac, say) is kept, not written over.
        (other / "logins.sealed").write_bytes(b"\x00" * 12 + os.urandom(64))
        p = opened(other)
        try:
            send(p, "vaultSave", origin="https://new.example", username="sam@example.com", password="Fresh-Start-33")
            check(until(lambda: list(other.glob("logins.sealed.unreadable-*")), 10), "A file it can't open is moved aside, not written over")
            check(logins(p) == ["sam@example.com"], "and the new login is saved in a file it can open")
        finally:
            close(p)
    finally:
        for folder in (profile, other):
            shutil.rmtree(folder, ignore_errors=True)
    print("FAILED " + str(FAILED) if FAILED else "PASSED")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
