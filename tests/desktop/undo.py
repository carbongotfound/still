"""Confirm and Undo for everything that destroys data. Each delete asks first in a dialog that names what goes; Cancel
keeps it; after confirming, the item hides at once and an Undo toast stays about 6 seconds. Undo brings it back and
nothing is deleted; otherwise the delete lands once the toast is gone. Checked for a chat, all chats, firing a
companion (from Settings, its card and its profile, and the last one, which can't go), a memory, an API key, and the
browsing history. Also: Fire is easy to find (the card, Settings > Companions, the profile's General tab).

Run: python tests/desktop/undo.py artifacts/Still-QA/Still.exe
"""
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, companions_page, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("undo-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
RESULT = {"checks": []}
KEY = "sk-fake-" + uuid.uuid4().hex + "LMNO"
DIALOG = "[data-slot=alert-dialog-content]"


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def click(p, selector, words=""):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => e.innerText.trim().includes({json.dumps(words)})); e?.click(); return !!e }})()")


def asking(p):
    return js(p, f"document.querySelector('{DIALOG}')?.innerText ?? ''") or ""


def confirm(p):
    until(lambda: asking(p), 3)
    return js(p, "(() => { const b = document.querySelector('[data-slot=alert-dialog-action]'); b?.click(); return !!b })()")


def cancel(p):
    until(lambda: asking(p), 3)
    js(p, "document.querySelector('[data-slot=alert-dialog-cancel]')?.click()")
    return until(lambda: not asking(p), 3)


def toast(p):
    return js(p, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.innerText).join(' | ')") or ""


def undo(p):
    return until(lambda: js(p, "(() => { const b = [...document.querySelectorAll('[data-sonner-toast] [data-button]')].find(b => b.innerText.trim() === 'Undo'); b?.click(); return !!b })()"), 3)


def saved(name):
    try:
        return json.loads((PROFILE / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def chats():
    return [c["Title"] for c in saved("ai/chats.json") or []]


def mates():
    return [c["Name"] for c in (saved("state.json") or {}).get("Preferences", {}).get("Companions", [])]


def facts(who):
    return [f["Text"] for f in saved(f"companions/{who}/memory.json") or []]


def main():
    PROFILE.mkdir(parents=True)
    (PROFILE / "ai").mkdir()
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([{"Id": f"c{i}", "Title": f"Garden plan {i}", "Harness": "claude", "Started": True, "Companion": "maya",
        "Messages": [{"Role": "user", "Text": f"Plan bed {i}"}, {"Role": "assistant", "Text": "Sure."}]} for i in (1, 2, 3)]))
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}],
        "History": [{"Title": "Seed catalog", "Url": "https://example.com/seeds", "At": now}],
        "Preferences": {"AgentsEnabled": True, "Companions": CREW}}))
    p = launch(EXE, PROFILE)
    try:
        # A chat: Cancel keeps it; Undo brings it back; otherwise it goes once the toast is gone.
        send(p, "appHome", view="chats")
        row = lambda t: js(p, f"!!document.querySelector('[aria-label=\"Delete {t}\"]')")
        until(lambda: row("Garden plan 1"), 15)
        # Web pages sit above the interface, so they hide while a dialog is up, and only then.
        covered = lambda: rpc(p)["overlay"]
        check(until(lambda: covered() is False, 3), f"With no dialog open, pages aren't hidden (overlay {covered()})")
        click(p, '[aria-label="Delete Garden plan 1"]')
        said = until(lambda: asking(p), 3) or ""
        check('Delete "Garden plan 1"?' in said and "messages" in said and "files" in said, "Deleting a chat asks first and names what goes")
        check(until(lambda: covered() is True, 3), "Pages hide under the dialog")
        check(cancel(p) and row("Garden plan 1") and "Garden plan 1" in chats(), "Cancel keeps the chat")
        check(until(lambda: covered() is False, 3), "and show again")
        click(p, '[aria-label="Delete Garden plan 1"]')
        confirm(p)
        check(until(lambda: not row("Garden plan 1"), 3) and "Chat deleted" in toast(p) and "Garden plan 1" in chats(), "Confirmed: the chat hides at once, with an Undo toast, and isn't deleted yet")
        check(undo(p) and until(lambda: row("Garden plan 1"), 3), "Undo brings it back")
        time.sleep(8)
        check("Garden plan 1" in chats(), "and nothing is deleted after the toast would have gone")
        click(p, '[aria-label="Delete Garden plan 1"]')
        confirm(p)
        time.sleep(4)
        check("Garden plan 1" in chats(), "A confirmed delete waits while Undo is up")
        check(until(lambda: "Garden plan 1" not in chats(), 12) and not row("Garden plan 1"), "then lands once the toast is gone")

        # Delete all chats.
        js(p, "document.querySelector('.home-page [aria-label=More]')?.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' }))")
        opened = until(lambda: js(p, "!!document.querySelector('[role=menuitem]')"), 3)
        click(p, "[role=menuitem]", "Delete all chats")
        said = until(lambda: asking(p), 3) or ""
        check(opened and "Delete all chats?" in said and "All 2 chats" in said, "Delete all chats asks first and counts them")
        confirm(p)
        check(until(lambda: not row("Garden plan 2"), 3) and len(chats()) == 2, "They hide at once, still on disk")
        undo(p)
        check(until(lambda: row("Garden plan 2") and row("Garden plan 3"), 3), "Undo brings them all back")

        # Fire: easy to find, asks first, with Undo.
        send(p, "openPanel", name="settings", value="companions")
        rows = until(lambda: js(p, "[...document.querySelectorAll('.team-row')].map(r => r.innerText)"), 10) or []
        check(len(rows) == 4 and js(p, "document.querySelectorAll('.team-row [aria-label^=\"Fire \"]').length") == 4, "Settings > Companions lists every companion with a Fire button")
        check(js(p, "[...document.querySelectorAll('.team-row > :first-child')].every(f => { const r = f.getBoundingClientRect(); return r.width > 20 && Math.abs(r.width - r.height) < 2 })"),
              "Each row's face keeps its shape")
        click(p, '.team-row [aria-label="Fire Nora"]')
        said = until(lambda: asking(p), 3) or ""
        check("Fire Nora?" in said and "remember" in said and "Keep Nora" in said, "Fire asks first, saying what goes, with Keep Nora")
        check(cancel(p) and "Nora" in mates(), "Keep Nora keeps her")
        click(p, '.team-row [aria-label="Fire Nora"]')
        confirm(p)
        check(until(lambda: js(p, "document.querySelectorAll('.team-row').length") == 3, 3) and "Fired Nora" in toast(p) and "Nora" in mates(), "Fired: hidden at once, Undo up, still saved")
        undo(p)
        time.sleep(8)
        check("Nora" in mates() and js(p, "document.querySelectorAll('.team-row').length") == 4, "Undo keeps Nora")
        js(p, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        companions_page(p)
        check(js(p, "(() => { const b = document.querySelector('.mate-fire[aria-label=\"Fire Nora\"]'); return !!b && b.getBoundingClientRect().height > 20 && getComputedStyle(b).borderTopWidth !== '0px' })()"),
              "Each card on the Companions page has a visible Fire button")
        js(p, "document.querySelector('.mate-portrait[aria-label=\"Edit Nora\"]')?.click()")
        check(until(lambda: js(p, "!!document.querySelector('.profile-fire [aria-label=\"Fire Nora\"]')"), 5), "and so does the profile's General tab")
        click(p, '.profile-fire [aria-label="Fire Nora"]')
        confirm(p)
        check(until(lambda: not js(p, "!!document.querySelector('.profile-panel')"), 3) and until(lambda: "Nora" not in mates(), 15), "Fire from the profile closes it and fires her once Undo is gone")

        # A memory.
        send(p, "memoryAdd", companion="maya", text="Grows tomatoes on the balcony.", kind="fact")
        send(p, "openPanel", name="settings", value="memory")
        forget = "[...document.querySelectorAll('.memory-row')].find(r => r.innerText.includes('tomatoes'))"
        until(lambda: js(p, f"!!{forget}"), 10)
        js(p, f"{forget}?.querySelector('[aria-label^=Forget]')?.click()")
        said = until(lambda: asking(p), 3) or ""
        check("Forget this?" in said and "tomatoes" in said, "Forgetting a memory asks first and quotes it")
        cancel(p)
        js(p, f"{forget}?.querySelector('[aria-label^=Forget]')?.click()")
        confirm(p)
        check(until(lambda: not js(p, f"!!{forget}"), 3) and any("tomatoes" in f for f in facts("maya")), "Forgotten: hidden at once, kept until Undo is gone")
        check(until(lambda: not any("tomatoes" in f for f in facts("maya")), 15), "then forgotten for good")

        # An API key.
        send(p, "apiSave", id="", kind="openai", name="Local box", url="http://127.0.0.1:9/v1", key=KEY, models=["box-model"], priceIn=0, priceOut=0, limit=0, context=0)
        send(p, "openPanel", name="settings", value="models")
        card = lambda: js(p, "[...document.querySelectorAll('.api-card')].find(c => c.innerText.includes('Local box'))?.innerText") or ""
        check(until(lambda: "Key ending in LMNO" in card(), 15), "A saved key shows by its last four characters")
        click(p, ".api-card .api-key button", "Remove")
        said = until(lambda: asking(p), 3) or ""
        check("Remove the key for Local box?" in said and "LMNO" in said and KEY not in said, "Removing a key asks first, naming only its last four characters")
        confirm(p)
        undo(p)
        time.sleep(8)
        check("Key ending in LMNO" in card(), "Undo keeps the key")
        click(p, ".api-card .api-key button", "Remove")
        confirm(p)
        check(until(lambda: "Key ending in" not in card() and card(), 15), "Confirmed and left alone, the key is removed")
        check(KEY not in (js(p, "document.documentElement.outerHTML") or ""), "The key never shows in the interface")

        # Browsing history.
        send(p, "openPanel", name="history")
        until(lambda: js(p, "[...document.querySelectorAll('.settings-link')].some(b => b.innerText.includes('Clear browsing history'))"), 10)
        click(p, ".settings-link", "Clear browsing history")
        said = until(lambda: asking(p), 3) or ""
        check("Clear your browsing history?" in said and "bookmarks" in said, "Clear history asks first and says what stays")
        confirm(p)
        check(len((saved("state.json") or {}).get("History", [])) == 1, "History stays on disk while Undo is up")
        check(until(lambda: not (saved("state.json") or {}).get("History"), 20), "then it's cleared")

        # The last companion can't be fired.
        for who in ("jonah", "rosa"):
            send(p, "companionDelete", id=who)
        until(lambda: mates() == ["Maya"], 10)
        js(p, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        companions_page(p)
        until(lambda: js(p, "document.querySelectorAll('.mate-card').length") == 1, 10)
        click(p, '.mate-fire[aria-label="Fire Maya"]')
        said = until(lambda: asking(p), 3) or ""
        check("Maya is your only companion" in said and not js(p, "!!document.querySelector('[data-slot=alert-dialog-action]')"), "The last companion can't be fired: it says why, with only OK")
        cancel(p)
        check("Maya" in mates(), "and Maya stays")
        errors = rpc(p).get("shellErrors") or js(p, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(p, "quit")
        RUN.joinpath("result.json").write_text(json.dumps(RESULT, indent=1))
    failed = [c for c in RESULT["checks"] if not c["passed"]]
    print(f"Results: {len(RESULT['checks']) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
