"""Companions see what a person sees. An outside AI app (over MCP) reads a local test page in a tab the user isn't looking at:
controls and words that are hidden, see-through, clipped away, parked off the page or covered are left out of read_page and find,
and a click on one is refused. Typing into an editor that draws its own text (like Google Docs) goes in once and says so.

Run: python tests/desktop/seen.py artifacts/Still-QA/Still.exe
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
from qa import launch, rpc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("seen-" + uuid.uuid4().hex[:8])
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
FAILED = []

PAGE = """<!doctype html><meta charset=utf-8><title>Seen</title>
<style>body{font:15px system-ui;overflow-x:hidden} .sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}</style>
<p>Plain words a person sees</p>
<button id=shown>Shown button</button>
<div style="opacity:0"><button id=ghost>Ghost button</button><p>Ghost words</p></div>
<button id=sronly class=sr>Reader-only button</button>
<p class=sr>Reader-only words</p>
<p style="font-size:0">Zero-size words</p>
<p style="color:transparent">Clear words</p>
<p style="position:absolute;left:-5000px">Far-off words</p>
<a href="/x" style="position:absolute;left:-5000px">Far-off link</a>
<div style="height:0;overflow:hidden"><a href="/y">Folded link</a><p>Folded words</p></div>
<nav style="position:fixed;top:0;left:100%;width:200px"><a href="/z">Side menu link</a></nav>
<div style="display:flex;width:200px;overflow:hidden"><button style="flex:none;width:220px">Slide one</button><button style="flex:none;width:220px">Slide two</button></div>
<div inert><button>Inert button</button></div>
<input type=checkbox id=c1 class=sr><label for=c1>Styled check</label>
<div style="visibility:hidden"><span style="visibility:visible">Shown inside hidden</span> <span>Hidden inside hidden</span></div>
<div style="position:relative;width:220px;height:40px"><button id=under style="width:220px;height:40px">Under a banner</button><div style="position:absolute;inset:0;background:#fff">A banner</div></div>
<x-card><span slot=s>Slotted words</span></x-card>
<iframe src="/frame" style="width:300px;height:70px"></iframe>
<iframe src="/frame?hidden" style="display:none"></iframe>
<div style="position:fixed;top:0;left:0;right:0;height:0"><div style="position:absolute;top:4px;right:8px;background:#fff"><button onclick="this.textContent='Bar pressed'">Bar button</button></div></div>
<div style="position:relative;height:30px"><div style="height:0;overflow:hidden"><button style="position:absolute;top:0;left:0">Spilled button</button></div></div>
<div style="position:relative;height:0;overflow:hidden"><button style="position:absolute;top:0;left:0">Held button</button></div>
<input id=stuck placeholder="Stuck field" oninput="this.value=''">
<div id=canvas onclick="kix.contentDocument.querySelector('[contenteditable]').focus()" style="width:300px;height:60px;border:1px solid #888">Drawn:<span id=drawn></span></div>
<iframe id=kix src="/kix" style="position:absolute;top:-10000px;width:20px;height:20px"></iframe>
<script>customElements.define('x-card', class extends HTMLElement { constructor() { super(); this.attachShadow({ mode: 'open' }).innerHTML = '<p>Shadow words</p><slot name=s></slot><button>Shadow button</button>'; } });</script>"""
FRAME = "<!doctype html><meta charset=utf-8><p>Frame words</p><button>Frame button</button>"
HIDDEN_FRAME = "<!doctype html><meta charset=utf-8><p>Hidden frame words</p>"
# Like Google Docs: typing lands in a hidden field in a frame, which hands it to the page to draw and empties itself.
KIX = """<!doctype html><meta charset=utf-8><div contenteditable=true aria-label="Document" style="width:10px;height:10px"></div>
<script>const f = document.querySelector('div'); f.addEventListener('input', () => { parent.document.getElementById('drawn').textContent += f.textContent; f.textContent = ''; });</script>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        data = (HIDDEN_FRAME if self.path.startswith("/frame?hidden") else FRAME if self.path.startswith("/frame") else KIX if self.path.startswith("/kix") else PAGE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def text_of(said):
    try:
        return json.loads(said).get("text", said)
    except ValueError:
        return said


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % server.server_address[1]
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AgentsEnabled": True, "ApprovedAgents": ["Tester"]},
        "Tabs": [{"Id": "home", "Title": "Mine", "Url": url + "/frame"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    client = None
    try:
        client = Mcp(EXE, "Tester", PROFILE)
        ok, opened = client.call("open_tab", url=url + "/", background=True)
        tab = json.loads(opened)["tabId"]
        check(ok and rpc(p)["activeId"] != tab, "The test page opens in a tab the user isn't looking at")
        time.sleep(1)

        page = text_of(client.call("read_page", tabId=tab)[1])
        for seen in ("Plain words a person sees", 'button "Shown button"', "Shadow words", "Slotted words", 'button "Shadow button"', "Frame words",
                     'button "Frame button"', "Shown inside hidden", 'label "Styled check"', 'button "Slide one"', 'button "Bar button"',
                     'button "Spilled button"'):
            check(seen in page, f"read_page has what shows: {seen}")
        for hidden in ("Ghost button", "Ghost words", "Reader-only button", "Reader-only words", "Zero-size words", "Clear words", "Far-off words",
                       "Far-off link", "Folded link", "Folded words", "Side menu link", "Slide two", "Hidden inside hidden", "Hidden frame words",
                       'button "Inert button"', 'button "Under a banner"', "Held button"):
            check(hidden not in page, f"read_page leaves out what doesn't: {hidden}")
        check("1 more under something on top" in page, "read_page says one control is under something on top")

        found = text_of(client.call("find", text="Ghost", tabId=tab)[1])
        check("No buttons, links or fields match" in found and "No text matches" in found, f"find doesn't find what's see-through ({found[:80]})")
        found = text_of(client.call("find", text="Far-off", tabId=tab)[1])
        check("No buttons, links or fields match" in found and "No text matches" in found, f"or what's parked off the page ({found[:80]})")
        ok, said = client.call("wait_for", text="Reader-only words", timeoutMs=600, tabId=tab)
        check('"found":false' in said.replace(" ", ""), f"wait_for doesn't count words only a screen reader gets ({said[:80]})")

        ok, said = client.call("click", selector="#ghost", tabId=tab)
        check(not ok and "hidden" in said, f"A click on a see-through button is refused ({said[:70]})")
        ok, said = client.call("click", selector="#sronly", tabId=tab)
        check(not ok and "hidden" in said, f"So is one clipped to nothing ({said[:70]})")
        ok, said = client.call("click", text="Slide two", tabId=tab)
        check(not ok, f"A button cut off by its box isn't clicked by its words ({said[:70]})")
        ok, said = client.call("click", text="Shown button", tabId=tab)
        check("hidden" not in said, f"A button that shows is still clicked by its words ({said[:70]})")
        ok, said = client.call("click", text="Bar button", tabId=tab)
        check(ok and "hidden" not in said, f"So is one in a bar with no height of its own, like Google's top bars ({said[:70]})")

        ok, said = client.call("type", selector="#stuck", text="pears", tabId=tab)
        check(not ok and "didn't change" in said, f"A field that throws typing away isn't called typed ({said[:90]})")
        ok, said = client.call("click", selector="#canvas", tabId=tab)
        ok, said = client.call("type", text="hello", tabId=tab)
        check(ok and "draws its own text" in said, f"Typing into an editor that draws its own text counts, and says to check ({said[:120]})")
        page = text_of(client.call("read_page", tabId=tab)[1])
        check("Drawn:hello" in page and "hellohello" not in page, f"and it went in once ({page[page.find('Drawn'):][:40]!r})")

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
