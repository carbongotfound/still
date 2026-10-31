"""Importing from another browser: a Chromium profile's bookmarks and history, reviewed first, end up in Still.

Run: python tests/desktop/browserimport.py <Still.exe or Still.app/Contents/MacOS/Still>
With STILL_IMPORT_REAL=<a real Chrome profile folder> it also imports that one and prints only the counts.

Checks: the review shows the profile's bookmark (the signed-in account's too) and history counts; Import adds them,
says how many, and they are saved (state.json's Bookmarks and History) and shown on the History page; importing again
adds nothing twice and says they were already there.
"""
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("browserimport-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
RESULT = {"checks": []}
LISTEN = """window.__tools = {};
window.chrome.webview.addEventListener('message', e => { const d = e.data; if (d?.kind === 'tools') __tools[d.name] = d.data })"""
CHROME_EPOCH = 11_644_473_600  # Chromium counts microseconds from 1601


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def chromium_profile(folder):
    """A Chrome-shaped profile: two bookmarks (one in a folder), one more saved to the signed-in account, two visited pages."""
    folder.mkdir(parents=True)
    (folder / "Bookmarks").write_text(json.dumps({"roots": {
        "bookmark_bar": {"type": "folder", "children": [{"type": "url", "name": "Garden notes", "url": "https://garden.example/"}]},
        "other": {"type": "folder", "children": [{"type": "folder", "name": "Work", "children": [{"type": "url", "name": "Ledger", "url": "https://ledger.example/"}]}]}}}))
    (folder / "AccountBookmarks").write_text(json.dumps({"roots": {"bookmark_bar": {"type": "folder", "children": [
        {"type": "url", "name": "Account page", "url": "https://account.example/"}, {"type": "url", "name": "Garden notes", "url": "https://garden.example/"}]}}}))
    db = sqlite3.connect(folder / "History")
    db.execute("CREATE TABLE urls(id INTEGER PRIMARY KEY, url LONGVARCHAR, title LONGVARCHAR, visit_count INTEGER DEFAULT 0, typed_count INTEGER DEFAULT 0, last_visit_time INTEGER NOT NULL, hidden INTEGER DEFAULT 0)")
    now = int((time.time() + CHROME_EPOCH) * 1_000_000)
    db.executemany("INSERT INTO urls(url, title, last_visit_time, hidden) VALUES (?, ?, ?, ?)", [
        ("https://recipes.example/soup", "Soup", now - 60_000_000, 0), ("https://maps.example/", "", now - 120_000_000, 0)])
    db.commit()
    db.close()


def stage(process, folder, name):
    js(process, "window.__tools.import = null")
    rpc(process, "stageExternalProfile", path=str(folder), name=name)
    return until(lambda: js(process, "window.__tools.import?.external?.preview ?? null"), 30) or {}


def confirm(process, preview):
    js(process, "window.__tools.import = null")
    send(process, "externalConfirm", id=preview.get("id", ""), bookmarks=True, history=True)
    return until(lambda: js(process, "window.__tools.import?.external?.done || null"), 15) or ""


def saved():
    until(lambda: (PROFILE / "state.json").exists(), 5)
    time.sleep(.5)
    state = json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))
    return [b.get("Url") for b in state.get("Bookmarks") or []], [h.get("Url") for h in state.get("History") or []]


def main():
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    try:
        js(process, LISTEN)
        chromium_profile(RUN / "chrome")
        preview = stage(process, RUN / "chrome", "Chrome")
        check(preview.get("bookmarks") == 3 and preview.get("history") == 2, f"The review counts Chrome's bookmarks (folders and the account's too) and history ({preview.get('bookmarks')}, {preview.get('history')})")
        done = confirm(process, preview)
        check(done.startswith("Imported 3 bookmarks, 2 history entries"), f"Import says what it brought over ({done!r})")
        marks, visits = saved()
        check({"https://garden.example/", "https://ledger.example/", "https://account.example/"} <= set(marks), f"The bookmarks are saved ({marks})")
        check({"https://recipes.example/soup", "https://maps.example/"} <= set(visits), f"The history is saved ({visits})")
        send(process, "openPanel", name="history")
        check(until(lambda: "Soup" in (js(process, "document.body.innerText") or ""), 10), "and the History page shows it")
        again = confirm(process, stage(process, RUN / "chrome", "Chrome"))
        check(again.startswith("Imported 0 bookmarks, 0 history entries") and "5 were already in Still" in again, f"Importing the same profile again adds nothing twice, and says so ({again!r})")
        real = os.environ.get("STILL_IMPORT_REAL")
        if real:
            preview = stage(process, Path(real), "Chrome")
            print(f"REAL review: {preview.get('bookmarks')} bookmarks, {preview.get('history')} history, error={js(process, 'window.__tools.import?.external?.error || null')!r}", flush=True)
            if preview:
                print("REAL import:", confirm(process, preview), "| saved history:", len(saved()[1]), flush=True)
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
    failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
    print(f"FAILED: {failed}" if failed else "ALL PASSED", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
