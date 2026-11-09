"""Mac: what an older Still kept in the Keychain comes over once into files encrypted for this Mac, and Still doesn't go
back for it. The Keychain items are made for the test so any app may read them (security -A): macOS shows nothing, and
they're deleted at the end. Also: a file this Mac can't open is kept beside the new one, never written over.

Run: python tests/desktop/keychain_move.py <the QA build's Still binary>
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
FAILED = []
TAG = "StillQA-" + uuid.uuid4().hex[:6] + " "
LISTEN = """window.__tools = {};
window.chrome.webview.addEventListener('message', e => { const d = e.data; if (d?.kind === 'tools') __tools[d.name] = d.data })"""


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def keychain(*args):
    return subprocess.run(["security", *args], capture_output=True, text=True)


def logins(process):
    js(process, LISTEN)
    send(process, "refreshTools", name="passwords")
    return [v["username"] for v in until(lambda: js(process, "window.__tools.passwords?.vault ?? null"), 5) or []]


def opened(profile, env=None):
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False}), encoding="utf-8")
    return launch(EXE, profile, {**os.environ, "STILL_QA_POS": os.environ.get("STILL_QA_POS", "-1800,80"), **(env or {})})


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
    profile, other = (Path(tempfile.mkdtemp(prefix="still-keys-")).resolve() for _ in range(2))
    home = str(profile)
    kim = {"id": "k1", "origin": "https://moved.example", "username": "kim@example.com", "password": "Moved-Over-91"}
    items = [(TAG + "Still logins", home, json.dumps([kim])), (TAG + "Still Composio key", home, "ak_moved_over_1234"),
             (TAG + "Still API key", home + "#api-moved1", "sk-moved-over-5678")]
    secrets = [b"Moved-Over-91", b"ak_moved_over_1234", b"sk-moved-over-5678"]
    try:
        for service, account, secret in items:
            made = keychain("add-generic-password", "-A", "-s", service, "-a", account, "-w", secret)
            check(made.returncode == 0, f"A test item for {service[len(TAG):]} is in the Keychain {made.stderr.strip()[:80]}")
        p = opened(profile, {"STILL_QA_KEYCHAIN": TAG})
        try:
            files = [profile / "logins.sealed", profile / "composio.sealed", profile / "api-keys" / "api-moved1.sealed"]
            check(until(lambda: all(f.exists() for f in files), 10), "At the first start the login, the Composio key and the API key come over into their files")
            check(all(s not in f.read_bytes() for f in files if f.exists() for s in secrets), "None of them is in plain text there")
            check(all(f.stat().st_mode & 0o077 == 0 for f in files if f.exists()), "Only the user can read the files")
            check(logins(p) == ["kim@example.com"], "Still opens the moved login")
            moved = (profile / "keychain-moved.txt").read_text(encoding="utf-8").splitlines() if (profile / "keychain-moved.txt").exists() else []
            check(len(moved) == 3, f"It notes what came over ({len(moved)})")
        finally:
            close(p)
        # The Keychain item changes; Still, started again, doesn't go back for it.
        newer = json.dumps([kim, {"id": "k2", "origin": "https://moved.example", "username": "lee@example.com", "password": "Later-22"}])
        keychain("add-generic-password", "-U", "-A", "-s", items[0][0], "-a", home, "-w", newer)
        p = opened(profile, {"STILL_QA_KEYCHAIN": TAG})
        try:
            check(logins(p) == ["kim@example.com"], "Started again, Still doesn't read the Keychain again")
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
        for service, account, _ in items:
            keychain("delete-generic-password", "-s", service, "-a", account)
        check(all(keychain("find-generic-password", "-s", s, "-a", a).returncode != 0 for s, a, _ in items), "The test's Keychain items are gone")
        for folder in (profile, other):
            shutil.rmtree(folder, ignore_errors=True)
    print("FAILED " + str(FAILED) if FAILED else "PASSED")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
