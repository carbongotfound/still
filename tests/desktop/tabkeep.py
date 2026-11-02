"""Switching tabs never reloads or empties one: typed text (a textarea and an editable box like a chat site's), scroll
and the page itself stay as they were on a web tab; a chat's message box keeps its own draft and scroll, per chat, also
after the chat is closed and opened again; the new tab page keeps its box. Under memory pressure a background tab may be
unloaded: then it comes back where it was scrolled to, and a tab holding typed text is never unloaded. A web page fetch is counted by the test server, so a reload
or a new navigation fails the round trip.

Run: python tests/desktop/tabkeep.py artifacts/Still-QA/Still.exe
Out: artifacts/tabkeep-*/ (result.json, before and after shots)
"""
import http.server
import json
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("tabkeep-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
CHECKS = []
HITS = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        HITS[self.path] = HITS.get(self.path, 0) + 1
        body = (f"<!doctype html><title>Page {self.path}</title><body style='height:4000px;font:16px system-ui'>"
                "<textarea id=t rows=4 cols=60></textarea><div id=ce contenteditable style='min-height:40px;border:1px solid #ccc'></div>"
                "<script>window.__mark = Math.random()</script>").encode()
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SERVER.server_port}"


def check(ok, name):
    CHECKS.append({"name": name, "passed": bool(ok)}); print(("PASS " if ok else "FAIL ") + name)


def page(p, tab, script):
    r = rpc(p, "evalTab", id=tab, script=script)
    return json.loads(r) if isinstance(r, str) and r[:1] in ("[", "{") and r else r


def shell(p, script):
    r = rpc(p, "shellEval", script=script)
    return json.loads(r) if isinstance(r, str) and r[:1] in ("[", "{") and r else r


def select(p, tab):
    send(p, "select", id=tab); until(lambda: rpc(p).get("activeId") == tab, 10); time.sleep(.8)


def type_shell(p, selector, words):
    shell(p, f"document.querySelector({json.dumps(selector)}).focus()")
    rpc(p, "shellCdp", method="Input.insertText", parameters={"text": words})
    time.sleep(.3)


BOX = "[role=textbox][aria-label=Message]"
LOG = ".ai-log"
chats = [{"Id": f"chat{i}", "Title": f"Chat {i}", "Harness": "claude", "Started": True, "Companion": "maya",
          "Messages": [{"Role": "user" if k % 2 == 0 else "assistant", "Text": f"Line {k} of chat {i}. " * 12} for k in range(40)]} for i in (1, 2)]
(PROFILE / "ai").mkdir(parents=True)
(PROFILE / "ai" / "chats.json").write_text(json.dumps(chats))
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AiHarness": "claude", "Width": 1280, "Height": 800},
    "Tabs": [{"Id": "w1", "Title": "Page /a", "Url": BASE + "/a"}, {"Id": "w2", "Title": "Page /b", "Url": BASE + "/b"}], "ActiveId": "w1"}))
process = launch(EXE, PROFILE)
try:
    until(lambda: page(process, "w1", "document.readyState") == "complete", 30)
    # The Mac's interface keeps its storage per app, not per profile: drafts from an earlier run would come back
    shell(process, "Object.keys(localStorage).filter(k => k.startsWith('still.draft.')).forEach(k => localStorage.removeItem(k))")
    # 1. A web tab: typed text in a textarea and an editable box, scroll, the page itself
    page(process, "w1", "document.getElementById('t').focus()")
    rpc(process, "pageCdp", method="Input.insertText", parameters={"text": "Typed into the textarea"})
    page(process, "w1", "document.getElementById('ce').focus()")
    rpc(process, "pageCdp", method="Input.insertText", parameters={"text": "Typed into the editable box"})
    page(process, "w1", "scrollTo(0, 1500)")
    mark = page(process, "w1", "window.__mark")
    select(process, "w2"); until(lambda: page(process, "w2", "document.readyState") == "complete", 30)
    select(process, "w1")
    got = page(process, "w1", "JSON.stringify({t: document.getElementById('t').value, ce: document.getElementById('ce').innerText, y: scrollY, mark: window.__mark})")
    got = json.loads(got) if isinstance(got, str) else got
    check(got.get("t") == "Typed into the textarea" and got.get("ce") == "Typed into the editable box", "A web tab keeps typed text across a switch")
    check(got.get("y") == 1500, f"A web tab keeps its scroll ({got.get('y')})")
    check(got.get("mark") == mark and HITS.get("/a") == 1, f"A web tab isn't reloaded or navigated (fetched {HITS.get('/a')} time)")
    rpc(process, "capture", name="web.png"); shutil.copy(PROFILE / "web.png", RUN / "web.png")

    # 2. A chat tab's message box, per chat
    send(process, "chatOpen", id="chat1"); until(lambda: shell(process, f"!!document.querySelector('{BOX}')"), 20); time.sleep(.8)
    type_shell(process, BOX, "A long thought for chat one")
    shell(process, f"document.querySelector('{LOG}').scrollTop = 600")
    time.sleep(.3)
    send(process, "chatOpen", id="chat2"); time.sleep(1)
    check(shell(process, f"document.querySelector('{BOX}').innerText") == "", "Another chat's box starts empty (no draft carried over)")
    type_shell(process, BOX, "Something else for chat two")
    send(process, "chatOpen", id="chat1"); time.sleep(1)
    check(shell(process, f"document.querySelector('{BOX}').innerText") == "A long thought for chat one", "Chat one's draft comes back")
    top = shell(process, f"Math.round(document.querySelector('{LOG}').scrollTop)")
    check(abs((top or 0) - 600) <= 2, f"Chat one's scroll comes back ({top})")
    select(process, "w1")
    send(process, "chatOpen", id="chat1"); time.sleep(1)
    check(shell(process, f"document.querySelector('{BOX}').innerText") == "A long thought for chat one", "The draft survives a trip to a web tab")
    rpc(process, "capture", name="chat.png"); shutil.copy(PROFILE / "chat.png", RUN / "chat.png")

    # 2b. The Still tab's own views: Chat History, another chat from it, then Back twice, all in the same tab
    count = len(rpc(process)["tabs"])
    send(process, "appHome", view="chats"); until(lambda: shell(process, "!!document.querySelector('section[aria-label=\"Chat History\"] .history-open')"), 10)
    shell(process, "[...document.querySelectorAll('.history-open')].find(e => e.innerText.includes('Chat 2'))?.click()"); time.sleep(1)
    check(shell(process, f"document.querySelector('{BOX}').innerText") == "Something else for chat two", "Chat two, opened from Chat History, has its own draft")
    send(process, "back"); time.sleep(.6); send(process, "back"); time.sleep(1)
    check(shell(process, f"document.querySelector('{BOX}').innerText") == "A long thought for chat one", "Chat one's draft is there after Chat History, chat two and Back")
    check(len(rpc(process)["tabs"]) == count, f"Going through the views opened no tabs ({len(rpc(process)['tabs'])}, was {count})")

    # 3. Closed and opened again
    chat_tab = next(t["Id"] for t in rpc(process)["tabs"] if t.get("ChatId") == "chat1")
    send(process, "closeTab", id=chat_tab); time.sleep(.8)
    send(process, "chatOpen", id="chat1"); time.sleep(1)
    check(shell(process, f"document.querySelector('{BOX}').innerText") == "A long thought for chat one", "The draft is still there after closing and reopening the chat")

    # 4. The new tab page's box
    send(process, "new"); time.sleep(1)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    home = rpc(process).get("activeId")
    until(lambda: shell(process, f"!!document.querySelector('.home-compose {BOX}')"), 20)
    type_shell(process, f".home-compose {BOX}", "Plan a weekend")
    select(process, "w2"); select(process, home)
    check(shell(process, f"document.querySelector('.home-compose {BOX}')?.innerText") == "Plan a weekend", "The new tab page keeps its box")

    # 5. Memory pressure (from the new tab page): the untouched tab unloads, the one with typed text stays
    select(process, "w2"); page(process, "w2", "scrollTo(0, 900)")
    select(process, home)
    ready = lambda tab: next(t for t in rpc(process)["tabs"] if t["Id"] == tab).get("ready")
    for _ in range(10):
        rpc(process, "memoryPressure")
        if ready("w2") is False: break
        time.sleep(1)
    check(ready("w2") is False and ready("w1") is True, f"Under memory pressure only the tab without typed text unloads (w2 {ready('w2')}, w1 {ready('w1')})")
    select(process, "w2"); until(lambda: page(process, "w2", "document.readyState") == "complete", 30); time.sleep(1)
    y = page(process, "w2", "scrollY")
    check(HITS.get("/b") == 2 and y == 900, f"The unloaded tab reloads where it was scrolled to (fetched {HITS.get('/b')}, at {y})")
    select(process, "w1")
    check(page(process, "w1", "document.getElementById('t').value") == "Typed into the textarea" and HITS.get("/a") == 1, "The tab with typed text still has it, never reloaded")
finally:
    rpc(process, "quit"); process.wait(timeout=15)

(RUN / "result.json").write_text(json.dumps({"checks": CHECKS}, indent=1))
print(("PASSED " if all(c["passed"] for c in CHECKS) else "FAILED ") + f"{sum(c['passed'] for c in CHECKS)}/{len(CHECKS)} -> {RUN}")
