"""Clicks and key presses only count once the page took them. An outside AI app (over MCP) works on a local test page in a tab
the user isn't looking at: every way a click can miss comes back as an error, a no-op is never called Clicked, and a form only
counts as sent on a signal from the form or the page.

Run: python tests/desktop/actions.py artifacts/Still-QA/Still.exe
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from mcp_client import Mcp  # noqa: E402
from qa import launch, rpc, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("actions-" + uuid.uuid4().hex[:8])
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
FAILED = []

PAGE = """<!doctype html><meta charset=utf-8><title>Actions</title>
<style>body{font:15px system-ui} button{display:block;margin:6px}</style>
<p id=log>idle</p>
<button id=works onclick="log.textContent='works clicked'">Works</button>
<button id=nothing>Does nothing</button>
<button id=off disabled>Switched off</button>
<button id=ariaoff aria-disabled=true>Aria off</button>
<button id=gone style="display:none">Hidden one</button>
<button id=invisible style="visibility:hidden">Invisible one</button>
<button id=away style="position:fixed;left:-900px;top:10px">Off to the side</button>
<div style="position:relative;width:200px;height:40px"><button id=under style="width:200px;height:40px">Under a banner</button>
 <div id=banner style="position:absolute;inset:0;background:#fffc">Cookie banner</div></div>
<button id=trap>Moves away</button>
<button id=presser>Works on press</button>
<label><input id=tick type=checkbox> Tick me</label>
<input id=field placeholder="A field">
<a id=link href="/next">Next page</a>
<a id=hash href="#later">To the later part</a>
<a id=file href="/file.bin" download>Get file</a>
<form id=need onsubmit="event.preventDefault();log.textContent='need sent'"><input id=must required placeholder=Must><button id=needgo>Send need</button></form>
<form id=spa onsubmit="event.preventDefault();log.textContent='spa sent '+q.value"><input id=q placeholder=Query><button id=spago>Send spa</button></form>
<form id=mute onsubmit="event.preventDefault()"><input id=m placeholder=Mute><button id=mutego>Send mute</button></form>
<form id=real action="/next" method=get><input id=r name=r placeholder=Real></form>
<input id=loose placeholder="No form">
<button id=count onclick="n.textContent='count='+(window.c=(window.c||0)+1)">Count</button><p id=n>count=0</p>
<form id=once onsubmit="event.preventDefault();sent.textContent='sent='+(window.s=(window.s||0)+1)"><input id=o placeholder=Once></form><p id=sent>sent=0</p>
<a id=onelink href="/once">One link</a>
<iframe id=same src="/frame" style="width:300px;height:90px"></iframe>
<div id=later style="margin-top:2000px">Later</div>
<script>
trap.addEventListener('mousemove', () => { if (document.getElementById('sheet')) return; const s = document.createElement('div'); s.id = 'sheet'; s.textContent = 'Sheet';
 s.style.cssText = 'position:fixed;inset:0;background:#0000;z-index:9'; document.body.append(s); s.onclick = () => s.remove(); });
presser.addEventListener('mousedown', () => { presser.remove(); log.textContent = 'pressed'; });
</script>"""
FRAME = """<!doctype html><meta charset=utf-8><div style="position:relative;width:200px;height:40px"><button id=framed style="width:200px;height:40px">In a frame, covered</button>
<div style="position:absolute;inset:0;background:#fffc">Over it</div></div><button id=inframe onclick="this.textContent='In a frame, clicked'">In a frame</button>"""


HITS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS.append(self.path)
        if self.path.startswith("/file.bin"):
            data, kind = b"x" * 100, "application/octet-stream"
        else:
            kind = "text/html"
            data = (FRAME if self.path.startswith("/frame") else "<!doctype html><title>Next</title><p>The next page</p>" if self.path.startswith(("/next", "/once")) else PAGE).encode()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % server.server_address[1]
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AgentsEnabled": True, "ApprovedAgents": ["Tester"],
        "Permissions": [{"Site": "127.0.0.1", "Action": "sensitive", "Companion": "", "Mode": "always"}]},  # its Send buttons are the test's own
        "Tabs": [{"Id": "home", "Title": "Mine", "Url": url + "/next"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    client = None
    try:
        client = Mcp(EXE, "Tester", PROFILE)
        ok, opened = client.call("open_tab", url=url + "/", background=True)
        tab = json.loads(opened)["tabId"]
        check(ok and rpc(p)["activeId"] != tab, "The test page opens in a tab the user isn't looking at")

        def click(selector):
            return client.call("click", selector=selector, tabId=tab)

        def page():
            return client.call("read_page", tabId=tab)[1]

        def fresh():
            client.call("navigate", url=url + "/", tabId=tab)

        ok, said = click("#works")
        check(ok and "Clicked" in said, f"A click the page took says Clicked ({said[:80]})")
        check("works clicked" in page(), "and it really happened in the background tab")

        ok, said = click("#nothing")
        check(not ok and "nothing on the page changed" in said and not said.startswith("Clicked \"Does nothing\"."), f"A button that does nothing is an error, not Clicked ({said[:80]})")

        ok, said = click("#off")
        check(not ok and "disabled" in said, f"A disabled button is refused ({said[:70]})")
        ok, said = click("#ariaoff")
        check(not ok and "disabled" in said, f"So is aria-disabled ({said[:70]})")
        ok, said = click("#gone")
        check(not ok and "hidden" in said, f"A display:none button is refused ({said[:70]})")
        ok, said = click("#invisible")
        check(not ok and "hidden" in said, f"A visibility:hidden button is refused ({said[:70]})")
        ok, said = click("#away")
        check(not ok and "outside the visible page" in said, f"A button outside the viewport is refused ({said[:70]})")
        ok, said = click("#under")
        check(not ok and "on top of" in said and "Cookie banner" in said, f"A covered button names what covers it ({said[:90]})")
        ok, said = click("#nosuchthing")
        check(not ok and "Couldn't find" in said, f"A missing element is an error ({said[:70]})")

        ok, said = client.call("click", selector="#same", tabId=tab)
        fresh()
        ok, said = client.call("click", text="In a frame, covered", tabId=tab)
        check(not ok and "on top of" in said, f"A covered button inside a frame is refused too ({said[:90]})")
        ok, said = client.call("click", text="In a frame", tabId=tab)
        check(ok, f"A button in a same-origin frame clicks ({said[:80]})")

        fresh()
        ok, said = click("#trap")
        # Windows moves the real mouse over the page first, so the sheet takes the click. A Mac tab out of view gets no hover, so the click reaches a button that does nothing.
        check(not ok and (("didn't reach" in said or "on top of" in said) and "Sheet" in said or "nothing on the page changed" in said), f"A sheet that slides in on hover: never called Clicked ({said[:110]})")

        fresh()
        ok, said = click("#presser")
        check(ok, f"A control that acts on mouse-down and leaves counts ({said[:80]})")

        fresh()
        ok, said = client.call("click", text="Tick me", tabId=tab)
        check(ok, f"Ticking a checkbox counts ({said[:80]})")
        ok, said = click("#field")
        check(ok, f"Clicking into a field counts ({said[:80]})")
        ok, said = click("#hash")
        check(ok, f"A link to a part of the page counts ({said[:80]})")
        fresh()
        ok, said = click("#file")
        check(ok, f"A download link counts ({said[:80]})")
        fresh()
        ok, said = click("#link")
        check(ok and "/next" in said, f"A link that navigates counts ({said[:80]})")

        # Exactly once, on a page that has only just loaded out of view: input that gets dropped is sent again, so it must never land twice.
        for i in range(6):
            fresh()
            ok, said = click("#count")
            time.sleep(1.2)
            words = page()
            check(ok and "count=1" in words and "count=2" not in words, f"Round {i}: one click, one press of the button ({said[:60]})")
            fresh()
            ok, said = client.call("type", selector="#o", text="x", submit=True, tabId=tab)
            time.sleep(1.2)
            words = page()
            check(ok and "sent=1" in words and "sent=2" not in words, f"Round {i}: one Enter, one form sent ({said[:60]})")
            fresh()
            before = HITS.count("/once")
            ok, said = click("#onelink")
            time.sleep(.8)
            check(ok and HITS.count("/once") == before + 1, f"Round {i}: one click on a link that navigates fast, one request ({HITS.count('/once') - before}, {said[:60]})")

        # Forms: only a signal from the form or the page counts.
        fresh()
        ok, said = click("#needgo")
        check(not ok and "wasn't sent" in said and "Must" in said, f"A required field left empty: not sent, and which field ({said[:100]})")
        check("need sent" not in page(), "and the form didn't go")
        client.call("type", selector="#must", text="filled", tabId=tab)
        ok, said = click("#needgo")
        check(ok and "need sent" in page(), f"Filled in, the same button sends it ({said[:70]})")

        fresh()
        ok, said = client.call("type", selector="#q", text="pears", submit=True, tabId=tab)
        check(ok and "and pressed Enter" in said and "spa sent pears" in page(), f"Enter in a form the page handles itself counts ({said[:80]})")
        ok, said = client.call("type", selector="#r", text="plums", submit=True, tabId=tab)
        check(ok and "/next?r=plums" in said, f"Enter in a form that navigates counts ({said[:90]})")
        fresh()
        ok, said = client.call("type", selector="#m", text="nope", submit=True, tabId=tab)
        check(not ok and "didn't change" in said and "read_page" in said, f"A form that takes the Enter and does nothing isn't called sent ({said[:110]})")
        ok, said = client.call("type", selector="#loose", text="nope", submit=True, tabId=tab)
        check(not ok and "nothing on the page changed" in said, f"Enter in a field with no form and no effect is an error ({said[:90]})")
        ok, said = client.call("type", selector="#must", text="", submit=True, tabId=tab)
        check(not ok and "wasn't sent" in said, f"Enter with a required field empty: not sent ({said[:90]})")

        # Keys and scrolling.
        fresh()
        client.call("click", selector="#field", tabId=tab)
        ok, said = client.call("press_key", key="a", tabId=tab)
        check(ok, f"A key that types counts ({said[:70]})")
        ok, said = client.call("press_key", key="Tab", tabId=tab)
        check(ok, f"Tab moves focus and counts ({said[:70]})")
        ok, said = client.call("press_key", key="Escape", tabId=tab)
        check(not ok and "nothing on the page changed" in said, f"A key that does nothing is an error ({said[:90]})")
        ok, said = client.call("scroll", direction="down", tabId=tab)
        check(ok, f"Scrolling that moves counts ({said[:70]})")
        client.call("scroll", direction="up", amount=20000, tabId=tab)
        ok, said = client.call("scroll", direction="up", tabId=tab)
        check(not ok and "Nothing scrolled" in said, f"Scrolling that can't move is an error ({said[:70]})")

        ok, said = client.call("navigate", url="http://127.0.0.1:1/", tabId=tab)
        check(not ok and "didn't load" in said, f"A page that doesn't load isn't Went to ({said[:80]})")

        check(rpc(p)["activeId"] != tab, "All this time the user's own tab stayed selected")
    finally:
        if client:
            client.close()
        if p.poll() is None:
            p.kill()
        server.shutdown()
        time.sleep(.5)
        shutil.rmtree(RUN, ignore_errors=True)
    print(f"{len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)


main()
