"""A page a companion opens out of sight never takes the keyboard from the page in front of you, and a screenshot of it
leaves it there. Local pages only.

Real keys aren't sent: this reads who holds the keyboard. On Windows the test window may not be in front, so what's checked
there is the page in front keeping its focus and its caret.

Run: python tests/desktop/hidden_focus.py <Still.exe or Still.app/Contents/MacOS/Still>
"""
import base64
import http.server
import json
from pathlib import Path
import shutil
import struct
import sys
import threading
import time
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, rpc, send, until  # noqa: E402
from mcp_client import Mcp, call_async  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("hidden-focus-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
FAILED = []
PAGES = {
    "/front": """<!doctype html><title>Front</title><input id=note autofocus>
<script>window.__blurs = 0; addEventListener('blur', () => __blurs++); note.addEventListener('blur', () => __blurs++)
window.__hides = 0; addEventListener('visibilitychange', () => __hides++)</script>""",
    "/busy": """<!doctype html><title>Busy</title><input id=a autofocus><iframe srcdoc="<input autofocus><script>setInterval(() => { focus(); document.querySelector('input').focus() }, 100)</script>"></iframe>
<script>setInterval(() => { focus(); a.focus(); top.focus(); a.click() }, 100)</script>""",
    "/shot": "<!doctype html><title>Shot</title><html style='background:#e00'>",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data = PAGES.get(self.path, "<!doctype html>ok").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def red(data):
    """The picture's top row is the page's red, not a blank: an 8-bit RGB or RGBA PNG, its first row unfiltered by hand."""
    try:
        png = base64.b64decode(data)
        width, _, depth, kind = struct.unpack(">IIBB", png[16:26])
        packed, i = b"", 8
        while i < len(png):
            size, name = struct.unpack(">I4s", png[i:i + 8])
            if name == b"IDAT":
                packed += png[i + 8:i + 8 + size]
            i += 12 + size
        raw, step = zlib.decompress(packed), {2: 3, 6: 4}[kind]
        row = bytearray(raw[1:1 + width * step])
        for x in range(step, len(row)):  # no row above: Sub and Paeth add the pixel to the left, Average half of it
            row[x] = (row[x] + {1: row[x - step], 4: row[x - step], 3: row[x - step] // 2}.get(raw[0], 0)) % 256
        r, g, b = row[step * 10:step * 10 + 3]
        return depth == 8 and r > 180 and g < 80 and b < 80
    except Exception:
        return False


def holder(process):
    return rpc(process, "keyboardHolder")


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{server.server_port}"
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AgentsEnabled": True}}), encoding="utf-8")
    process = launch(EXE, PROFILE)
    try:
        send(process, "navigate", url=site + "/front")
        until(lambda: rpc(process, "eval", script="location.pathname + document.readyState") == "/frontcomplete", 15)
        at = rpc(process, "eval", script="(r => ({x: r.x + 20, y: r.y + r.height / 2}))(note.getBoundingClientRect())")
        for kind in ("mousePressed", "mouseReleased"):
            rpc(process, "pageCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": at["x"], "y": at["y"], "button": "left", "clickCount": 1})
        check(until(lambda: rpc(process, "eval", script="document.activeElement.id") == "note", 5), "The note in front has the caret")
        front = rpc(process, "state")["activeId"]
        rpc(process, "eval", script="__blurs = 0")

        agent = Mcp(EXE, "Probe", PROFILE)
        try:
            pending = call_async(agent, "list_tabs")
            until(lambda: "Probe" in (js(process, "document.body.innerText") or ""), 30)
            send(process, "agentAnswer", allow=True)
            pending.get(timeout=60)
            ok, _ = agent.call("open_tab", url=site + "/busy")
            check(ok, "A companion's app opens a page that keeps grabbing focus, out of sight")
            agent.call("read_page")
            time.sleep(5)
            check(rpc(process, "state")["activeId"] == front, "The tab in front stays in front")
            check(rpc(process, "eval", script="document.activeElement.id") == "note", "The note keeps the caret")
            blurs = rpc(process, "eval", script="__blurs")
            check(blurs == 0, f"The note never loses focus ({blurs} times)")
            who = holder(process)
            check(not who["hidden"], f"The keyboard isn't with a page out of sight ({who})")
            who = rpc(process, "keyboardToHidden")
            check(who["tried"] and not who["took"] and not who["hidden"], f"Even when asked, a page out of sight can't take the keyboard ({who})")
            check(rpc(process, "eval", script="__blurs") == blurs, "...and asking leaves the note alone")
            # A screenshot of a page out of sight pictures it there: the page in front never leaves the screen.
            ok, opened = agent.call("open_tab", url=site + "/shot")
            shot = json.loads(opened)["tabId"] if ok else ""
            agent.call("read_page", tabId=shot)
            rpc(process, "eval", script="__hides = 0")
            reply = agent.request("tools/call", {"name": "screenshot", "arguments": {"tabId": shot}})["result"]
            image = next((c.get("data", "") for c in reply.get("content", []) if c.get("type") == "image"), "")
            check(not reply.get("isError") and red(image), "A screenshot of a page out of sight shows that page")
            hides = rpc(process, "eval", script="__hides")
            check(rpc(process, "state")["activeId"] == front and hides == 0, f"...and the page in front stays in front ({hides} hides)")
        finally:
            agent.close()
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
        shutil.rmtree(RUN, ignore_errors=True)
    print(f"{'FAILED ' + str(len(FAILED)) if FAILED else 'PASSED'}", flush=True)
    sys.exit(1 if FAILED else 0)


main()
