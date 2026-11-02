"""What's typed and not sent stays: the home box (one draft per window) and each chat's box keep it when you leave and
come back, and after a restart, with any files still on disk. Sending clears it, an incognito window leaves nothing on
disk, and a draft not touched for 7 days is gone.

Run: python tests/desktop/drafts.py artifacts/Still-QA/Still.exe
Out: artifacts/drafts-*/
"""
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
import qa
from qa import js, rpc, send, until

EXE = Path(sys.argv[1]).resolve()
RUN = Path(__file__).resolve().parents[2] / "artifacts" / f"drafts-{uuid.uuid4().hex[:8]}"
FAKE = r'''
import json, sys, time
if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
sys.stdin.read()
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay."}]}}), flush=True)
'''
HOME, CHAT = ".home-compose [role=textbox]", ".chat-view [role=textbox][aria-label=Message]"
SECRET = "Incognito words " + uuid.uuid4().hex[:10]
results = []


def check(ok, name):
    results.append({"name": name, "ok": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def typed(p, box, words, window=None):
    script = f"""(() => {{ const e = document.querySelector({json.dumps(box)}); if (!e) return false; e.focus(); const s = getSelection(); s.selectAllChildren(e); s.collapseToEnd()
        document.execCommand('insertText', false, {json.dumps(words)}); return true }})()"""
    ok = rpc(p, "shellEval", script=script, **({"window": window} if window else {}))
    time.sleep(.6)  # past the moment drafts wait before they're kept
    return ok


def box(p, sel, window=None):
    return rpc(p, "shellEval", script=f"document.querySelector({json.dumps(sel)})?.innerText ?? null", **({"window": window} if window else {}))


def chips(p, sel=".home-compose"):
    return json.loads(js(p, f"JSON.stringify([...document.querySelectorAll('{sel} .file-chip')].map(e => e.title))") or "[]")


def select(p, tab):
    send(p, "select", id=tab); until(lambda: rpc(p).get("activeId") == tab, 10); time.sleep(.6)


def open_chat(p, chat):
    send(p, "chatOpen", id=chat); until(lambda: box(p, CHAT) is not None and js(p, f"!!document.querySelector('.chat-view')"), 10); time.sleep(.6)


def quit(p):
    try: rpc(p, "quit")
    except RuntimeError: pass
    try: p.wait(timeout=20)
    except Exception: p.kill()


def on_disk(words):
    """Where the interface's storage can be: the profile, and on the Mac WebKit's own folders for the app."""
    places = [PROFILE] + ([Path.home() / "Library" / "WebKit" / "com.carbongotfound.still.qa"] if qa.MAC else [])
    needles = [words.encode("utf-8"), words.encode("utf-16-le")]
    for place in places:
        for f in place.rglob("*") if place.exists() else []:
            try:
                if f.is_file() and any(n in f.read_bytes() for n in needles): return str(f)
            except OSError: pass
    return None


shutil.rmtree(RUN, ignore_errors=True)
PROFILE = RUN / "profile"; (PROFILE / "ai").mkdir(parents=True); (PROFILE / "agents").mkdir()
bin_ = RUN / "bin"; bin_.mkdir(); (bin_ / "fake_agent.py").write_text(FAKE, encoding="utf-8"); qa.launcher(bin_ / "fakeagent", bin_ / "fake_agent.py")
(PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(bin_ / "fakeagent"),
    "detect": ["status"], "expect": "signed in", "run": ["run"], "output": "stream-json"}))
(PROFILE / "ai" / "chats.json").write_text(json.dumps([{"Id": f"chat{i}", "Title": f"Chat {i}", "Harness": "fake", "Started": True, "Companion": "maya",
    "Messages": [{"Role": "user", "Text": f"Hello {i}"}, {"Role": "assistant", "Text": "Hi."}]} for i in (1, 2)]))
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1",
    "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}, {"Id": "w2", "Title": "Blank", "Url": "about:blank"}],
    "Preferences": {"AiHarness": "fake", "AgentsEnabled": True, "Companions": qa.CREW}}))

ids = {}
p = qa.launch(EXE, PROFILE)
try:
    until(lambda: box(p, HOME) is not None, 15)
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    typed(p, HOME, "Home words to keep")
    select(p, "w2"); select(p, "w1")
    check(box(p, HOME) == "Home words to keep", f"The home box keeps its draft after going to another tab and back ({box(p, HOME)!r})")
    send(p, "new"); until(lambda: rpc(p).get("activeId") not in ("w1", "w2"), 10); time.sleep(.6)
    check(box(p, HOME) == "Home words to keep", "A new tab in the same window has the same home draft")

    # Two files in the home box: one is deleted before the next start.
    notes, brief = base64.b64encode(b"Plan notes").decode(), base64.b64encode(b"Brief text").decode()
    js(p, f"""(() => {{ const t = new DataTransfer(); t.items.add(new File([Uint8Array.from(atob('{notes}'), c => c.charCodeAt(0))], 'notes.txt', {{ type: 'text/plain' }}))
        t.items.add(new File([Uint8Array.from(atob('{brief}'), c => c.charCodeAt(0))], 'brief.txt', {{ type: 'text/plain' }}))
        document.querySelector('.home-compose .composer').dispatchEvent(new DragEvent('drop', {{ bubbles: true, cancelable: true, dataTransfer: t }})) }})()""")
    check(until(lambda: sorted(chips(p)) == ["brief.txt", "notes.txt"], 10), f"Files dropped on the home box show ({chips(p)})")
    # Saved a moment after the last change (later when the machine is busy).
    kept = until(lambda: (lambda d: d if len(d.get("files", [])) == 2 else None)(json.loads(js(p, "localStorage.getItem('still.draft.home')") or "{}")), 5) or {}
    ids = {f["name"]: f["id"] for f in kept.get("files", [])}
    check(set(ids) == {"notes.txt", "brief.txt"} and kept.get("text") == "Home words to keep", f"The draft keeps the text and the files ({sorted(ids)})")

    open_chat(p, "chat1")
    typed(p, CHAT, "Chat words to keep")
    select(p, "w2"); open_chat(p, "chat1")
    check(box(p, CHAT) == "Chat words to keep", f"A chat's box keeps its draft after leaving and coming back ({box(p, CHAT)!r})")
    open_chat(p, "chat2")
    check((box(p, CHAT) or "").strip() == "", "Another chat's box starts empty")
    js(p, f"localStorage.setItem('still.draft.chat.chat2', JSON.stringify({{ at: Date.now() - 8 * 86400000, text: 'Old words' }}))")

    # Incognito: typed in a chat's box there, never written anywhere.
    before = {w["id"] for w in rpc(p)["windows"]}
    send(p, "incognitoWindow")
    wid = until(lambda: next((w["id"] for w in rpc(p)["windows"] if w.get("incognito") and w["id"] not in before), None), 15)
    until(lambda: rpc(p, "shellEval", window=wid, script="document.body.innerText.length > 0"), 15)
    rpc(p, "shellEval", window=wid, script="window.chrome.webview.postMessage(" + json.dumps({"op": "aiSend", "text": "Hello from incognito", "companion": "maya", "home": True}) + ")")
    until(lambda: box(p, CHAT, wid) is not None, 15); time.sleep(1)
    got = typed(p, CHAT, SECRET, wid)
    check(got and box(p, CHAT, wid) == SECRET, f"An incognito chat's box takes text ({got}, {box(p, CHAT, wid)!r})")
    rpc(p, "shellEval", window=wid, script="document.activeElement?.blur()"); time.sleep(.6)
    check(rpc(p, "shellEval", window=wid, script=f"Object.values(localStorage).some(v => v.includes({json.dumps(SECRET)}))") is False, "...and keeps it out of the interface's storage")
    rpc(p, "closeWindow", id=wid); time.sleep(1)
finally:
    quit(p)

check(on_disk("Home words to keep"), "A normal window's draft is on disk (the search below can find words)")
check(not on_disk(SECRET), f"The incognito draft is nowhere on disk ({on_disk(SECRET)})")
if ids.get("notes.txt"): shutil.rmtree(PROFILE / "ai" / "attachments" / ids["notes.txt"], ignore_errors=True)
(PROFILE / "qa-pipe.txt").unlink(missing_ok=True)

p = qa.launch(EXE, PROFILE)
try:
    select(p, "w1")
    until(lambda: box(p, HOME) is not None, 15)
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    check(box(p, HOME) == "Home words to keep", f"After a restart the home draft is there ({box(p, HOME)!r})")
    check(until(lambda: chips(p) == ["brief.txt"], 5), f"...with the file still on disk, and not the deleted one ({chips(p)})")
    open_chat(p, "chat2")
    check((box(p, CHAT) or "").strip() == "" and js(p, "localStorage.getItem('still.draft.chat.chat2')") is None, "A draft older than 7 days is gone")
    open_chat(p, "chat1")
    check(box(p, CHAT) == "Chat words to keep", f"After a restart a chat's draft is there ({box(p, CHAT)!r})")
    saved = (PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")
    check("Chat words to keep" not in saved and "Home words to keep" not in saved, "Drafts are never in chats.json")
    js(p, f"document.querySelector({json.dumps(CHAT)}).focus(); document.querySelector({json.dumps(CHAT)}).dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true, cancelable: true }}))")
    sent = until(lambda: any("Chat words to keep" in m.get("Text", "") for c in json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")) if c["Id"] == "chat1" for m in c["Messages"]), 15)
    check(sent and (box(p, CHAT) or "").strip() == "", "Sending sends it and empties the box")
    select(p, "w2"); open_chat(p, "chat1")
    check((box(p, CHAT) or "").strip() == "" and js(p, "localStorage.getItem('still.draft.chat.chat1')") is None, "...and the draft is gone")
finally:
    quit(p)

(RUN / "results.json").write_text(json.dumps(results, indent=1))
failed = [r for r in results if not r["ok"]]
print(f"{'FAILED' if failed else 'PASSED'} {len(results) - len(failed)}/{len(results)} -> {RUN}")
sys.exit(1 if failed else 0)
