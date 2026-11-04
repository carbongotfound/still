"""Settings > About > Update automatically (Windows), on by default. Off, Still still finds a new version and shows
Update, but downloads nothing until it's clicked, and the About text says so. The choice is kept through a restart,
and Settings search finds it. The Mac has no automatic install, so it has no such switch.

STILL_QA_VERSION stands in for an old version, so GitHub's latest release counts as new (one request to GitHub's API).
The test never turns the switch on while an update is known: that would download the real installer.

Run: python tests/desktop/autoupdate.py artifacts/Still-QA/Still.exe
Out: artifacts/autoupdate-*/
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("autoupdate-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
SWITCH = '[aria-label="Update automatically"]'
results = []


def check(ok, name):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def about(p):
    send(p, "openPanel", name="settings")
    until(lambda: js(p, "!!document.querySelector('.set-nav-item')"), 10)
    js(p, "[...document.querySelectorAll('.set-nav-item')].find(b => b.innerText.trim() === 'About')?.click()")
    return until(lambda: js(p, "document.querySelector('.set-title')?.innerText") == "About", 5)


def switch(p):
    return js(p, f"document.querySelector('{SWITCH}')?.getAttribute('aria-checked') ?? null")


def text(p):
    return js(p, "document.getElementById('set-about')?.innerText ?? ''") or ""


def search(p, words):
    js(p, f"(() => {{ const i = document.querySelector('.set-search input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, {json.dumps(words)}); i.dispatchEvent(new Event('input', {{ bubbles: true }})) }})()")
    time.sleep(.6)
    return js(p, "[...document.querySelectorAll('.set-result strong')].map(s => s.innerText)") or []


def quit(p):
    try: rpc(p, "quit")
    except RuntimeError: pass
    try: p.wait(timeout=20)
    except Exception: p.kill()


def start():
    p = launch(EXE, PROFILE, env={**os.environ, "STILL_QA_VERSION": "1.0.0"})
    until(lambda: js(p, "!!document.body.innerText.length"), 20)
    return p


def mac():
    p = start()
    try:
        check(about(p), "Settings opens on About")
        check(switch(p) is None, "The Mac has no Update automatically switch")
        check("shows you where to download" in text(p), "and About says where updates come from")
        found = search(p, "auto update")
        check("Update automatically" not in found, f"and search doesn't offer it ({found})")
    finally:
        quit(p)


def windows():
    p = start()
    try:
        check(about(p), "Settings opens on About")
        check(switch(p) == "true", "Update automatically is on by default")
        check("updates itself automatically" in text(p), "and About says Still updates itself")
        js(p, f"document.querySelector('{SWITCH}').click()")
        check(until(lambda: switch(p) == "false", 3), "Clicking it turns it off")
        check(until(lambda: "Automatic updates are off" in text(p), 3), f"About says updates are off ({text(p)[-160:]!r})")
        send(p, "openPanel", name="")
        time.sleep(.5)
        r = rpc(p, "checkUpdate")
        update = r.get("update") or {}
        check(update.get("version"), f"With it off, Still still finds the newer version on GitHub ({update})")
        check(not r.get("installer") and not r.get("exists") and not update.get("downloading"), f"but downloads nothing ({r})")
        time.sleep(2)
        r = rpc(p, "checkUpdate")
        check(not r.get("installer") and not (r.get("update") or {}).get("downloading"), "and still nothing two seconds later")
        pill = until(lambda: js(p, "document.querySelector('.update-pill')?.innerText.trim()"), 5)
        check(pill == "Update", f"The toolbar shows Update ({pill!r})")
    finally:
        quit(p)

    saved = json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"].get("AutoUpdate")
    check(saved is False, f"The choice is saved ({saved})")
    p = start()
    try:
        about(p)
        check(switch(p) == "false", "and still off after Still restarts")
        found = search(p, "auto update")
        check("Update automatically" in found, f"Settings search finds it ({found})")
        js(p, "[...document.querySelectorAll('.set-result')].find(r => r.innerText.includes('Update automatically'))?.click()")
        check(until(lambda: js(p, "document.getElementById('set-autoUpdate')?.classList.contains('set-flash')"), 3), "and jumps to it lit up")
        # Turning it on: QA builds never check on their own, so nothing downloads here.
        js(p, f"document.querySelector('{SWITCH}').click()")
        check(until(lambda: switch(p) == "true", 3), "Clicking it again turns it back on")
        check(until(lambda: "updates itself automatically" in text(p), 3), "and About says so again")
    finally:
        quit(p)


def main():
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Width": 1280, "Height": 860},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    mac() if MAC else windows()
    print(f"{'PASSED' if all(results) else 'FAILED'} {sum(results)}/{len(results)} -> {RUN}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
