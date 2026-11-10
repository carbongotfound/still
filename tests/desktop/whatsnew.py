"""Still has updated: the first start after an update to a version with news (announce on in whatsnew.json) shows a
small popup: Still has updated, the new version under it, the news in short lines, Got it and See all changes. It shows
once: the version is saved when it closes (Got it, Esc or a click outside). A version with announce off shows nothing,
versions skipped show together (newest first), and a new install gets setup, not this. Settings > About opens the
latest news again.

STILL_QA_VERSION stands in for the update and STILL_QA_NOTES for the notes the app ships with; QA builds only show
the popup with STILL_QA_WHATSNEW set.

Run: python tests/desktop/whatsnew.py artifacts/Still-QA/Still.exe [shots folder]
Out: artifacts/whatsnew-*/ (pictures copied to the shots folder, artifacts/whatsnew-shots by default)
"""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "artifacts" / "whatsnew-shots"
RUN = ROOT / "artifacts" / ("whatsnew-" + uuid.uuid4().hex[:8])
RESULT = {"checks": []}
POPUP = ".whatsnew"
SHIPPED = json.loads((ROOT / "still-ui" / "src" / "whatsnew.json").read_text(encoding="utf-8"))
NOTES = {
    "2.8.0": {"announce": True, "news": ["Old news one", "Old news two", "Old news three"]},
    "2.9.0": {"announce": True, "news": ["Companions can now work inside a folder you pick.", "Long pasted text stays tidy in a small pill.", "Stopping a reply keeps what it already did."]},
    "2.9.1": {"announce": False, "news": ["A crash on start is fixed."]},
    "2.10.0": {"announce": True, "news": ["Your unsent messages are kept, even after a restart.", "Companions stop to ask less often.", "Drop files anywhere on a chat."]},
    "2.10.1": {"announce": False, "news": ["Small fixes."]},
    "2.11.0": {"announce": True, "news": ["Not out yet."]},
}
NOTES_FILE = RUN / "whatsnew.json"


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def env(version):
    return {**os.environ, "STILL_QA_WHATSNEW": "1", "STILL_QA_VERSION": version, "STILL_QA_NOTES": str(NOTES_FILE)}


def profile(name, seen=None, url=""):
    folder = RUN / name
    folder.mkdir()
    state = {"UiVersion": 6, "Welcome": False, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": url}], "Preferences": {"AgentsEnabled": True, "Companions": CREW}}
    if seen is not None:
        state["SeenVersion"] = seen
    (folder / "state.json").write_text(json.dumps(state))
    return folder


def saved(folder):
    for _ in range(50):
        try:
            return json.loads((folder / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.05)
    return {}


def shown(p):
    return js(p, f"!!document.querySelector('{POPUP}')")


def popup(p):
    return js(p, f"(d => d && {{ title: d.querySelector('[data-slot=dialog-title]').innerText, version: d.querySelector('[data-slot=dialog-description]').innerText, news: [...d.querySelectorAll('li')].map(l => l.innerText), buttons: [...d.querySelectorAll('button')].map(b => b.innerText.trim()) }})(document.querySelector('{POPUP}'))") or {}


def shot(p, name):
    time.sleep(.6)
    reply = rpc(p, "capture", name=name)
    path = Path(reply.get("path") or "") if isinstance(reply, dict) else None
    if path and path.exists():
        SHOTS.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, SHOTS / name)


def quit_(p):
    try:
        rpc(p, "quit")
    except (RuntimeError, OSError):
        pass
    until(lambda: p.poll() is not None, 15)
    if p.poll() is None:
        p.kill()
    time.sleep(1)


def main():
    RUN.mkdir(parents=True)
    NOTES_FILE.write_text(json.dumps(NOTES))
    tag = "mac" if MAC else "windows"

    # The notes the app ships with: each version with announce, and 3 to 5 plain lines when it's on.
    good = all(re.fullmatch(r"\d+\.\d+\.\d+", v) and isinstance(r.get("announce"), bool) and isinstance(r.get("news"), list) and all(isinstance(n, str) and n for n in r["news"])
               and (not r["announce"] or 3 <= len(r["news"]) <= 5) for v, r in SHIPPED.items())
    check(SHIPPED and good, "The shipped notes say per version whether to announce it, with 3 to 5 lines when it's on")
    check(not any("—" in n for r in SHIPPED.values() for n in r["news"]), "No em dashes in them")

    # An update to a version with news: it shows once.
    a = profile("updated", "2.9.1")
    p = launch(EXE, a, env("2.10.0"))
    try:
        check(until(lambda: shown(p), 10), "The first start after an update to a version with news shows the popup")
        got = popup(p)
        shot(p, f"whatsnew-on-{tag}.png")
        check(got.get("title") == "Still has updated" and got.get("version") == "Version 2.10.0", f"Still has updated, with the new version under it ({got.get('title')!r}, {got.get('version')!r})")
        check(got.get("news") == NOTES["2.10.0"]["news"], f"Its news, in short lines ({got.get('news')})")
        check(got.get("buttons") == ["See all changes", "Got it"], f"Got it, and See all changes ({got.get('buttons')})")
        js(p, f"[...document.querySelectorAll('{POPUP} button')].find(b => b.innerText.trim() === 'Got it').click()")
        check(until(lambda: not shown(p), 3), "Got it closes it")
        check(until(lambda: saved(a).get("SeenVersion") == "2.10.0", 5), f"and saves the version as shown ({saved(a).get('SeenVersion')!r})")
    finally:
        quit_(p)
    p = launch(EXE, a, env("2.10.0"))
    try:
        time.sleep(4)
        check(not shown(p), "It doesn't come back on the next start")
        send(p, "openPanel", name="settings", value="about")
        found = until(lambda: js(p, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.innerText.trim() === \"What's new in 2.10.0\"); b?.click(); return !!b })()"), 10)
        got = until(lambda: shown(p) and popup(p), 5) or {}
        check(found and got.get("title") == "What's new" and got.get("news") == NOTES["2.10.0"]["news"], f"Settings > About opens the latest news again ({got.get('title')!r})")
        js(p, f"document.querySelector('{POPUP}').dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Escape', bubbles: true }}))")
        check(until(lambda: not shown(p), 3), "Esc closes it")
        time.sleep(1)
        check(saved(a).get("SeenVersion") == "2.10.0", "and that changes nothing")
        errors = rpc(p).get("shellErrors") or js(p, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        quit_(p)

    # An update to a version with announce off: nothing.
    p = launch(EXE, a, env("2.10.1"))
    try:
        time.sleep(4)
        shot(p, f"whatsnew-off-{tag}.png")
        check(not shown(p), "An update to a version with announce off shows nothing")
    finally:
        quit_(p)
    check(saved(a).get("SeenVersion") == "2.10.0", f"and saves nothing ({saved(a).get('SeenVersion')!r})")

    # Versions skipped (from 2.8, saved the old way): their news together, newest first; not what was seen, what's
    # off, or what isn't out yet.
    b = profile("skipped", "2.8")
    p = launch(EXE, b, env("2.10.1"))
    try:
        check(until(lambda: shown(p), 10), "Skipping versions shows the popup")
        got = popup(p)
        shot(p, f"whatsnew-skipped-{tag}.png")
        check(got.get("version") == "Version 2.10.1" and got.get("news") == NOTES["2.10.0"]["news"] + NOTES["2.9.0"]["news"],
              f"with the news of every version skipped, newest first ({got.get('version')!r}, {got.get('news')})")
        js(p, f"document.querySelector('{POPUP}').dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Escape', bubbles: true }}))")
        check(until(lambda: not shown(p), 3) and until(lambda: saved(b).get("SeenVersion") == "2.10.1", 5), "Esc closes it, and the version is saved")
    finally:
        quit_(p)

    # Someone on 2.10, who saw its What's New: an update to 2.10.1 with no news shows nothing.
    p = launch(EXE, profile("on210", "2.10"), env("2.10.1"))
    try:
        time.sleep(4)
        check(not shown(p), "\"2.10\" counts as 2.10.0 seen")
    finally:
        quit_(p)

    # Over a web page: it lifts the interface above the page like any dialog, and a click outside closes it.
    c = profile("web", "2.9.1", "about:blank")
    p = launch(EXE, c, env("2.10.0"))
    try:
        check(until(lambda: shown(p), 10) and until(lambda: rpc(p)["overlay"] is True, 5), f"Over a web page it shows too, above the page (overlay {rpc(p)['overlay']})")
        js(p, "(o => { o.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerType: 'mouse', button: 0 })); o.dispatchEvent(new MouseEvent('click', { bubbles: true, button: 0 })) })(document.querySelector('[data-slot=dialog-overlay]'))")  # a press, then its click
        check(until(lambda: not shown(p), 3) and until(lambda: saved(c).get("SeenVersion") == "2.10.0", 5), "A click outside closes it, and the version is saved")
    finally:
        quit_(p)

    # A new install: setup, not this.
    fresh = RUN / "fresh"
    fresh.mkdir()
    p = launch(EXE, fresh, env("2.10.0"))
    try:
        until(lambda: js(p, "!!document.querySelector('.welcome.ob')"), 15)
        time.sleep(3)
        shot(p, f"whatsnew-fresh-{tag}.png")
        check(not shown(p), "A new install gets setup, not the popup")
    finally:
        quit_(p)
    check(until(lambda: saved(fresh).get("SeenVersion") == "2.10.0", 5), "and counts its version as seen")

    RUN.joinpath("result.json").write_text(json.dumps(RESULT, indent=1))
    failed = [c for c in RESULT["checks"] if not c["passed"]]
    print(f"Results: {len(RESULT['checks']) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
