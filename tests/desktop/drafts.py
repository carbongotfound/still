"""Drafts and undo. What's typed in a message box and not sent comes back after leaving, a refresh, closing the tab or
Still being killed, with a Draft restored hint and Discard. Send clears it once Still takes the message; a send that
fails keeps it and puts the text back. Settings > Save drafts (on by default) turns it off after a confirm, deleting
every draft, and then nothing comes back. A private window keeps nothing on disk. Ctrl+Z, Ctrl+Shift+Z (and Ctrl+Y on
Windows; Cmd on the Mac) undo and redo step by step in every box, through switching chats and a restart.

Run: python tests/desktop/drafts.py artifacts/Still-QA/Still.exe
Out: artifacts/drafts-*/
"""
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
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
class PageDrafts(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>Form</title><form action=/sent><textarea id=note name=note rows=4></textarea><textarea id=apikey aria-label='Your API Key' rows=2></textarea></form>"
        if self.path.startswith("/sent"):
            body = b"<!doctype html><title>Sent</title><p>Sent</p>"
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


HOME, CHAT, SIDE = ".home-compose [role=textbox]", ".chat-view [role=textbox][aria-label=Message]", ".ai-sidebar [role=textbox][aria-label=Message]"
SECRET = "Incognito words " + uuid.uuid4().hex[:10]
results = []


def check(ok, name):
    results.append({"name": name, "ok": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def ev(p, script, window=None):
    return rpc(p, "shellEval", script=script, **({"window": window} if window else {}))


def focus_end(p, sel, window=None):
    return ev(p, f"""(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return false; e.focus(); const s = getSelection(); s.selectAllChildren(e); s.collapseToEnd(); return true }})()""", window)


def typed(p, sel, words, window=None):
    """Put in by the page (execCommand), as one step."""
    ok = focus_end(p, sel, window) and ev(p, f"document.execCommand('insertText', false, {json.dumps(words)})", window)
    time.sleep(.8)  # past the moment drafts wait before they're kept
    return ok


def real(p, sel, words):
    """Typed for real (the text input path), so it runs together with typing just before it."""
    focus_end(p, sel)
    rpc(p, "shellCdp", method="Input.insertText", parameters={"text": words})
    time.sleep(.15)


def box(p, sel, window=None):
    return ev(p, f"document.querySelector({json.dumps(sel)})?.innerText ?? null", window)


def text(p, sel):
    return (box(p, sel) or "").replace(" ", " ").strip()


def press(p, letter, shift=False):
    """Ctrl (Cmd on the Mac) with a letter, a real key press."""
    if qa.MAC:
        rpc(p, "key", key=letter.upper(), mods="Control" + (",Shift" if shift else ""), post=True)
    else:
        name = letter.upper() if shift else letter.lower()
        for kind in ("rawKeyDown", "keyUp"):
            rpc(p, "shellCdp", method="Input.dispatchKeyEvent", parameters={"type": kind, "key": name, "code": "Key" + letter.upper(), "windowsVirtualKeyCode": ord(letter.upper()), "modifiers": 2 | (8 if shift else 0)})
    time.sleep(1 if qa.MAC else .4)  # on the Mac a posted key waits in the event queue, longer while Still comes forward


def backspace(p):
    for kind in ("rawKeyDown", "keyUp"):
        rpc(p, "shellCdp", method="Input.dispatchKeyEvent", parameters={"type": kind, "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8})
    time.sleep(.4)


def select_all(p, sel):
    ev(p, f"(() => {{ const e = document.querySelector({json.dumps(sel)}); e.focus(); getSelection().selectAllChildren(e) }})()")


def select_word(p, sel, word):
    ev(p, f"""(() => {{ const e = document.querySelector({json.dumps(sel)}); e.focus(); const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT)
        for (let n; (n = w.nextNode());) {{ const i = n.textContent.indexOf({json.dumps(word)}); if (i >= 0) {{ getSelection().setBaseAndExtent(n, i, n, i + {len(word)}); return }} }} }})()""")


def clip(p, sel, kind, words=""):
    ev(p, f"""(() => {{ const d = new DataTransfer(); if ({json.dumps(words)}) d.setData('text/plain', {json.dumps(words)})
        document.querySelector({json.dumps(sel)}).dispatchEvent(new ClipboardEvent({json.dumps(kind)}, {{ clipboardData: d, bubbles: true, cancelable: true }})) }})()""")
    time.sleep(.3)


def hint(p, scope):
    return ev(p, f"document.querySelector({json.dumps(scope + ' .draft-hint')})?.innerText ?? ''") or ""


def draft(key):
    f = PROFILE / "ai" / "drafts" / f"{key}.json"
    try: return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError): return None


def draft_text(key):
    return (draft(key) or {}).get("text")


def key_of(p, sel):
    return ev(p, f"document.querySelector({json.dumps(sel)})?.dataset.history ?? null")


def select(p, tab):
    send(p, "select", id=tab); until(lambda: rpc(p).get("activeId") == tab, 10); time.sleep(.6)


def open_chat(p, chat):
    send(p, "chatOpen", id=chat); until(lambda: key_of(p, CHAT) == "chat." + chat, 10); time.sleep(.6)


def toast(p):
    return js(p, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.innerText).join(' | ')") or ""


def settings_switch(p):
    send(p, "openPanel", name="settings")
    until(lambda: js(p, "!!document.querySelector('[aria-label=\"Save drafts\"]')"), 10)
    return js(p, "document.querySelector('[aria-label=\"Save drafts\"]')?.getAttribute('aria-checked')")


def close_panel(p):
    send(p, "openPanel", name=""); time.sleep(.5)


def quit(p):
    try: rpc(p, "quit")
    except RuntimeError: pass
    try: p.wait(timeout=20)
    except Exception: p.kill()


def kill(p):
    """Still ends with no warning, as in a crash: on Windows with its page processes, so nothing is written on the way out."""
    if qa.MAC: p.kill()
    else: subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    try: p.wait(timeout=20)
    except Exception: pass
    time.sleep(1)


def launch():
    (PROFILE / "qa-pipe.txt").unlink(missing_ok=True)
    p = qa.launch(EXE, PROFILE)
    until(lambda: box(p, HOME) is not None or rpc(p).get("activeId") == "w2", 20)
    if qa.MAC:  # forward first, as a user's click would: a box focused in a background window loses it when the window comes forward
        rpc(p, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": 4, "y": 300}); time.sleep(.8)
    return p


def new_tab(p):
    """A New Tab: every one shows the same New Tab box (and draft)."""
    was = rpc(p).get("activeId")
    send(p, "new"); until(lambda: rpc(p).get("activeId") != was and box(p, HOME) is not None, 10); time.sleep(.6)
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")


def on_disk(words):
    """Where anything typed could be kept: the profile, and on the Mac WebKit's own folders for the app."""
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
    "Messages": [{"Role": "user", "Text": f"Hello {i}"}, {"Role": "assistant", "Text": "Hi."}]} for i in (1, 2, 9)]))
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1",
    "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}, {"Id": "w2", "Title": "Blank", "Url": "about:blank"}],
    "Preferences": {"AiHarness": "fake", "AgentsEnabled": True, "Companions": qa.CREW}}))
# A draft kept by the interface itself before 2.10 moves to Still's files.
OLD = "Words from before"

p = launch()
side_key = None
try:
    until(lambda: box(p, HOME) is not None, 15)
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    check(settings_switch(p) == "true", "Settings > Save drafts is on by default")
    close_panel(p)

    # The New Tab box: kept while typing, back after a refresh with the hint, and after closing the tab.
    typed(p, HOME, "Home words to keep")
    check(until(lambda: draft_text("home") == "Home words to keep", 3), f"Typing in the New Tab box keeps a draft in Still's files ({draft_text('home')!r})")
    check(not hint(p, ".home-compose"), "No Draft restored hint while typing")
    js(p, "location.reload()"); time.sleep(1.5)
    until(lambda: box(p, HOME) is not None, 15)
    check(text(p, HOME) == "Home words to keep", f"After a refresh the New Tab box has it back ({box(p, HOME)!r})")
    check("Draft restored" in hint(p, ".home-compose") and "Discard" in hint(p, ".home-compose"), f"...with the Draft restored hint and Discard ({hint(p, '.home-compose')!r})")
    focus_end(p, HOME); press(p, "z")
    check(text(p, HOME) == "", f"Ctrl+Z right after the draft came back takes back the last step ({box(p, HOME)!r})")
    press(p, "z", shift=True)
    check(text(p, HOME) == "Home words to keep", f"...and Ctrl+Shift+Z puts it back ({box(p, HOME)!r})")
    time.sleep(.8)
    send(p, "closeTab", id="w1"); until(lambda: rpc(p).get("activeId") == "w2", 10)
    send(p, "new"); until(lambda: rpc(p).get("activeId") not in ("w1", "w2") and box(p, HOME) is not None, 10); time.sleep(.6)
    check(text(p, HOME) == "Home words to keep", f"Closing the tab and opening a new one brings it back ({box(p, HOME)!r})")
    
    # A chat's box: undo step by step, select all and delete, cut, paste over.
    open_chat(p, "chat1")
    real(p, CHAT, "alpha"); real(p, CHAT, " beta"); time.sleep(1.2); real(p, CHAT, " gamma"); time.sleep(.8)
    check(text(p, CHAT) == "alpha beta gamma", f"Typing in a chat's box ({box(p, CHAT)!r})")
    check(until(lambda: draft_text("chat.chat1") == "alpha beta gamma", 3), "...is kept as that chat's draft")
    press(p, "z"); first = text(p, CHAT); press(p, "z"); second = text(p, CHAT)
    check((first, second) == ("alpha beta", "alpha"), f"Ctrl+Z undoes typing a word at a time ({first!r}, {second!r})")
    press(p, "z", shift=True); press(p, "z", shift=True)
    check(text(p, CHAT) == "alpha beta gamma", f"Ctrl+Shift+Z redoes it ({box(p, CHAT)!r})")
    if qa.MAC:  # through the menu bar (Edit > Undo, Edit > Redo), as a click on the menu does
        rpc(p, "key", key="Z", mods="Control"); time.sleep(1)
        check(text(p, CHAT) == "alpha beta", f"Edit > Undo takes the same step back ({box(p, CHAT)!r})")
        rpc(p, "key", key="Z", mods="Control,Shift"); time.sleep(1)
        check(text(p, CHAT) == "alpha beta gamma", f"...and Edit > Redo puts it back ({box(p, CHAT)!r})")
    select_all(p, CHAT); backspace(p)
    check(text(p, CHAT) == "", f"Select all and Backspace empties the box ({box(p, CHAT)!r})")
    press(p, "z")
    check(text(p, CHAT) == "alpha beta gamma", f"Ctrl+Z brings the text back ({box(p, CHAT)!r})")
    press(p, "z", shift=True)
    check(text(p, CHAT) == "", f"Ctrl+Shift+Z deletes it again ({box(p, CHAT)!r})")
    press(p, "z")
    if not qa.MAC:
        press(p, "y")
        check(text(p, CHAT) == "", f"Ctrl+Y redoes too ({box(p, CHAT)!r})")
        press(p, "z")
    check(text(p, CHAT) == "alpha beta gamma", f"...and Ctrl+Z again brings it back ({box(p, CHAT)!r})")
    select_word(p, CHAT, "gamma"); clip(p, CHAT, "cut")
    check(text(p, CHAT) == "alpha beta", f"Cut takes the word out ({box(p, CHAT)!r})")
    press(p, "z")
    check(text(p, CHAT) == "alpha beta gamma", f"Ctrl+Z undoes the cut ({box(p, CHAT)!r})")
    select_all(p, CHAT); clip(p, CHAT, "paste", "Pasted over")
    check(text(p, CHAT) == "Pasted over", f"Paste over the whole text ({box(p, CHAT)!r})")
    press(p, "z")
    check(text(p, CHAT) == "alpha beta gamma", f"Ctrl+Z undoes the paste ({box(p, CHAT)!r})")
    time.sleep(.8)
    open_chat(p, "chat2")
    check(text(p, CHAT) == "", "Another chat's box starts empty: each chat has its own draft")
    open_chat(p, "chat1")
    check(text(p, CHAT) == "alpha beta gamma", f"Back in the first chat, its draft is there ({box(p, CHAT)!r})")
    focus_end(p, CHAT); press(p, "z")
    check(text(p, CHAT) == "alpha beta", f"Undo history survives switching chats ({box(p, CHAT)!r})")
    press(p, "z", shift=True); time.sleep(.8)

    # A send that fails (too long) keeps the draft and puts the text back.
    open_chat(p, "chat2")
    long = "x" * 20001
    typed(p, CHAT, long)
    ev(p, f"document.querySelector({json.dumps(CHAT)}).dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true, cancelable: true }}))")
    told = until(lambda: "20,000" in toast(p), 5)
    check(told, f"A send Still can't take says why ({toast(p)[:120]!r})")
    check(until(lambda: len(text(p, CHAT)) == 20001, 3), f"...the text is back in the box ({len(text(p, CHAT))} characters)")
    check(draft_text("chat.chat2") == long, "...and the draft is kept")
    select_all(p, CHAT); backspace(p); time.sleep(.8)
    press(p, "z")
    check(len(text(p, CHAT)) == 20001, "Ctrl+Z brings back a box emptied after a failed send")
    select_all(p, CHAT); backspace(p); time.sleep(.8)

    # The side chat.
    select(p, "w2")
    send(p, "aiToggle"); until(lambda: box(p, SIDE) is not None, 10); time.sleep(.6)
    side_key = key_of(p, SIDE)
    typed(p, SIDE, "Side chat words")
    check(side_key and until(lambda: draft_text(side_key) == "Side chat words", 3), f"The side chat's box keeps a draft ({side_key})")
    send(p, "aiToggle"); time.sleep(.5)
finally:
    kill(p)

check(draft_text("home") == "Home words to keep" and draft_text("chat.chat1") == "alpha beta gamma", "Killing Still leaves the drafts in its files")
STALE = PROFILE / "ai" / "drafts" / "chat.stale.json"
STALE.write_text(json.dumps({"text": "Old words"}), encoding="utf-8")
os.utime(STALE, (time.time() - 8 * 86400,) * 2)

p = launch()
try:
    new_tab(p)
    check(text(p, HOME) == "Home words to keep" and "Draft restored" in hint(p, ".home-compose"), f"After Still is killed and opens again, the New Tab draft is back with the hint ({box(p, HOME)!r})")
    check(not STALE.exists(), "A draft not touched for 7 days is gone when Still starts")
    open_chat(p, "chat1")
    check(text(p, CHAT) == "alpha beta gamma" and "Draft restored" in hint(p, ".chat-view"), f"...and the chat's ({box(p, CHAT)!r})")
    focus_end(p, CHAT); press(p, "z")
    check(text(p, CHAT) == "alpha beta", f"Undo history survives the restart ({box(p, CHAT)!r})")
    press(p, "z", shift=True)
    check(text(p, CHAT) == "alpha beta gamma", "...and redo")
    open_chat(p, side_key[5:]); select(p, "w2"); send(p, "aiToggle"); until(lambda: key_of(p, SIDE) == side_key, 10); time.sleep(.6)
    check(text(p, SIDE) == "Side chat words", f"...and the side chat's ({box(p, SIDE)!r})")
    send(p, "aiToggle"); time.sleep(.5)
    # A draft the interface kept itself before 2.10 (the page's own storage, which a crash can lose) moves to Still's files.
    js(p, f"localStorage.setItem('still.draft.chat.chat9', JSON.stringify({{ at: Date.now(), text: {json.dumps(OLD)} }}))")
    js(p, "location.reload()"); time.sleep(1.5); until(lambda: rpc(p).get("activeId") == "w2", 10)
    open_chat(p, "chat9")
    check(text(p, CHAT) == OLD and until(lambda: draft_text("chat.chat9") == OLD, 3), f"A draft the interface kept before 2.10 moves to Still's files ({box(p, CHAT)!r})")
    check(js(p, "localStorage.getItem('still.draft.chat.chat9')") is None, "...and leaves the page's storage")

    # Discard, then undo.
    open_chat(p, "chat1")
    ev(p, "document.querySelector('.chat-view .draft-hint button').click()"); time.sleep(.8)
    check(text(p, CHAT) == "" and draft("chat.chat1") is None and not hint(p, ".chat-view"), f"Discard empties the box and deletes the draft ({box(p, CHAT)!r}, {draft('chat.chat1')})")
    focus_end(p, CHAT); press(p, "z")
    check(text(p, CHAT) == "alpha beta gamma", f"Ctrl+Z right after Discard brings it back ({box(p, CHAT)!r})")
    check(until(lambda: draft_text("chat.chat1") == "alpha beta gamma", 3), "...and it's kept again")

    # Send clears it once Still takes it.
    ev(p, f"document.querySelector({json.dumps(CHAT)}).dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true, cancelable: true }}))")
    went = until(lambda: any("alpha beta gamma" in m.get("Text", "") for c in json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")) if c["Id"] == "chat1" for m in c["Messages"]), 15)
    check(went and text(p, CHAT) == "", "Send sends it and empties the box")
    check(until(lambda: draft("chat.chat1") is None, 5), "...and the draft is gone")
    open_chat(p, "chat2"); open_chat(p, "chat1")
    check(text(p, CHAT) == "", "Leaving and coming back, nothing comes back after a send")

    # A routine's "What to do" (a prompt box that isn't a message box).
    js(p, "dispatchEvent(new CustomEvent('still-profile', { detail: { id: 'maya', tab: 'routines' } }))")
    WHAT = ".profile-panel textarea[aria-label='What to do']"
    until(lambda: box(p, WHAT) is not None, 10)
    ev(p, f"document.querySelector({json.dumps(WHAT)}).focus()"); ev(p, "document.execCommand('insertText', false, 'Every morning, check the weather')")
    check(until(lambda: draft_text("routine.maya") == "Every morning, check the weather", 3), "A routine's What to do keeps a draft")
    js(p, "location.reload()"); time.sleep(1.5); until(lambda: box(p, CHAT) is not None or box(p, HOME) is not None, 15)
    js(p, "dispatchEvent(new CustomEvent('still-profile', { detail: { id: 'maya', tab: 'routines' } }))")
    until(lambda: box(p, WHAT) is not None, 10)
    check(js(p, f"document.querySelector({json.dumps(WHAT)}).value") == "Every morning, check the weather" and "Draft restored" in hint(p, ".profile-panel"), "...back after a refresh, with the hint")
    ev(p, f"document.querySelector({json.dumps(WHAT)}).focus()"); press(p, "z")
    check(js(p, f"document.querySelector({json.dumps(WHAT)}).value") == "", "Ctrl+Z works in it right after it came back")
    press(p, "z", shift=True)
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))"); time.sleep(.6)

    # Any other text box: the settings search.
    send(p, "openPanel", name="settings"); time.sleep(.6)
    FIND = "[aria-label='Search settings']"
    if box(p, FIND) is None: FIND = ".settings-search input"
    ev(p, f"document.querySelector({json.dumps(FIND)})?.focus()"); ev(p, "document.execCommand('insertText', false, 'sounds')"); time.sleep(.3)
    ev(p, "document.execCommand('insertText', false, ' extra')"); time.sleep(.3)
    press(p, "z")
    got = js(p, f"document.querySelector({json.dumps(FIND)})?.value")
    press(p, "z", shift=True)
    check(got == "sounds" and js(p, f"document.querySelector({json.dumps(FIND)})?.value") == "sounds extra", f"Undo and redo work in other text boxes too ({got!r})")
    ev(p, f"(() => {{ const e = document.querySelector({json.dumps(FIND)}); e.select(); document.execCommand('delete') }})()"); close_panel(p)

    # A private window keeps nothing on disk.
    before = {w["id"] for w in rpc(p)["windows"]}
    send(p, "incognitoWindow")
    wid = until(lambda: next((w["id"] for w in rpc(p)["windows"] if w.get("incognito") and w["id"] not in before), None), 15)
    until(lambda: rpc(p, "shellEval", window=wid, script="document.body.innerText.length > 0"), 15)
    rpc(p, "shellEval", window=wid, script="window.chrome.webview.postMessage(" + json.dumps({"op": "aiSend", "text": "Hello from incognito", "companion": "maya", "home": True}) + ")")
    until(lambda: box(p, CHAT, wid) is not None, 15); time.sleep(1)
    got = typed(p, CHAT, SECRET, wid)
    check(got and box(p, CHAT, wid) == SECRET, f"A private window's chat box takes text ({got}, {box(p, CHAT, wid)!r})")
    rpc(p, "shellEval", window=wid, script="document.activeElement?.blur()"); time.sleep(.8)
    check(not on_disk(SECRET), "...and nothing of it is on disk")
    rpc(p, "closeWindow", id=wid); time.sleep(1)

    # In a page: what the draft keeper leaves in the tab's own storage.
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PageDrafts)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    def in_page(sel, words):
        rpc(p, "eval", script=f"(e => {{ e.value = {json.dumps(words)}; e.dispatchEvent(new InputEvent('input', {{ bubbles: true, composed: true }})) }})(document.querySelector({json.dumps(sel)}))")
        time.sleep(.2)
    def kept():
        return rpc(p, "eval", script="sessionStorage.getItem('__stillDraft') ?? ''") or ""
    send(p, "new", url=base + "/form")
    until(lambda: rpc(p, "eval", script="!!document.querySelector('#note')"), 15)
    in_page("#note", "A long note that the draft keeper should keep for me")
    check("A long note" in kept(), "A page's long text is kept in the tab")
    rpc(p, "eval", script="document.querySelector('form').requestSubmit()")
    until(lambda: "sent" in str(rpc(p, "eval", script="location.pathname")), 10)
    check(not kept(), "Sending the form forgets it")
    send(p, "navigate", url=base + "/form")
    until(lambda: rpc(p, "eval", script="!!document.querySelector('#note')"), 15)
    in_page("#apikey", "words that are long enough to be kept but the box says secret")
    check(not kept(), "A box named for a secret keeps nothing, whatever the case of its name")
    in_page("#note", "my key is sk8aB3dE6gH9jK2mN5pQ8rT1vW4yZ7 and more words")
    check(not kept(), "A long run of letters and digits isn't kept")
    in_page("#note", "-----BEGIN PRIVATE KEY-----\nabc")
    check(not kept(), "Nor is a private key's header")
    in_page("#note", "An ordinary note, https://example.com/a-link and all, is still kept")
    check("An ordinary note" in kept(), "Ordinary text with a link is still kept")
    rpc(p, "eval", script="sessionStorage.removeItem('__stillDraft')")

    # Save drafts off: asks first, deletes every draft, and then nothing comes back.
    new_tab(p)
    check(settings_switch(p) == "true", "Save drafts is on")
    js(p, "document.querySelector('[aria-label=\"Save drafts\"]').click()")
    asked = until(lambda: "Turn off Save drafts?" in (js(p, "document.querySelector('[role=alertdialog][data-state=open]')?.innerText") or ""), 5)
    check(asked, "Turning it off asks first")
    js(p, "[...document.querySelectorAll('[role=alertdialog][data-state=open] button')].find(b => b.innerText.trim() === 'Turn off')?.click()")
    check(until(lambda: js(p, "document.querySelector('[aria-label=\"Save drafts\"]')?.getAttribute('aria-checked')") == "false", 3), "...then it shows off")
    gone = until(lambda: not (PROFILE / "ai" / "drafts").exists(), 12)
    check(gone, "...and once the Undo toast is gone, every draft is deleted")
    close_panel(p)
    check(text(p, HOME) == "Home words to keep", f"Turning it off leaves what's in the box ({box(p, HOME)!r})")
    typed(p, HOME, " and more")
    time.sleep(1)
    check(text(p, HOME) == "Home words to keep and more" and not (PROFILE / "ai" / "drafts").exists(), "With it off, typing keeps nothing")
    js(p, "location.reload()"); time.sleep(1.5); until(lambda: box(p, HOME) is not None, 15)
    check(box(p, HOME) is not None and text(p, HOME) == "" and not hint(p, ".home-compose"), f"...and after a refresh nothing comes back ({box(p, HOME)!r})")
    send(p, "new", url=base + "/form")
    until(lambda: rpc(p, "eval", script="!!document.querySelector('#note')"), 15)
    in_page("#note", "A long note written with Save drafts turned off")
    check(not kept(), "With it off, a new tab's pages keep nothing either")
    new_tab(p)
    typed(p, HOME, "Typed while off")
    open_chat(p, "chat2"); typed(p, CHAT, "Chat typed while off")
finally:
    kill(p)

p = launch()
try:
    new_tab(p)
    check(box(p, HOME) is not None and text(p, HOME) == "", f"With it off, after Still is killed nothing comes back ({box(p, HOME)!r})")
    open_chat(p, "chat2")
    check(text(p, CHAT) == "", f"...in a chat either ({box(p, CHAT)!r})")
    check(settings_switch(p) == "false", "It stays off")
    js(p, "document.querySelector('[aria-label=\"Save drafts\"]').click()")
    check(until(lambda: js(p, "document.querySelector('[aria-label=\"Save drafts\"]')?.getAttribute('aria-checked')") == "true", 3), "Turning it on needs no confirm")
    close_panel(p)
    new_tab(p)
    typed(p, HOME, "On again")
    check(until(lambda: draft_text("home") == "On again", 3), "...and drafts are kept again")
    saved = (PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")
    check("Home words to keep" not in saved and "On again" not in saved, "Drafts are never in chats.json")
finally:
    quit(p)

check(not on_disk(SECRET), f"The private window's text is nowhere on disk ({on_disk(SECRET)})")
(RUN / "results.json").write_text(json.dumps(results, indent=1))
failed = [r for r in results if not r["ok"]]
print(f"{'FAILED' if failed else 'PASSED'} {len(results) - len(failed)}/{len(results)} -> {RUN}")
sys.exit(1 if failed else 0)
