"""Links to other apps on the Mac. Still asks first, in the name of the frame that wanted it, and only a real click by the page
itself uses or saves a yes. A test build records the link instead of opening the app, so nothing else starts. Local pages only.

Run: python tests/desktop/app_links_mac.py <Still.app/Contents/MacOS/Still>
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
RUN = ROOT / "artifacts" / ("app-links-mac-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
FAILED = []
PAGE = "<!doctype html><title>Links</title><a id=go style='display:block;width:200px;height:40px;background:#ccc'>Open</a>"
FRAME = "<!doctype html><title>Frame</title><a id=go href='mailto:framed@example.com' style='display:block;width:200px;height:40px;background:#ccc'>Open</a>"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data = (FRAME if self.path.startswith("/frame") else PAGE).encode()
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


def bar(process):
    return js(process, "document.querySelector('.permission-wrap.is-open .permission-bar')?.innerText ?? ''") or ""


def answer(process, word):
    time.sleep(.7)
    js(process, f"[...document.querySelectorAll('.permission-wrap.is-open .permission-bar button')].find(b => b.innerText.trim() === {json.dumps(word)}).click()")
    until(lambda: "wants to" not in bar(process), 5)


def main():
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False}), encoding="utf-8")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    process = launch(EXE, PROFILE)
    try:
        opened = lambda: rpc(process, "appLinks").get("opened", [])
        send(process, "new", url=f"http://127.0.0.1:{port}/")
        until(lambda: rpc(process, "eval", script="document.title") == "Links", 20)

        def press_link(link):
            at = rpc(process, "eval", script=f"(a => (a.href = {json.dumps(link)}, (r => [r.x + 20, r.y + 10])(a.getBoundingClientRect())))(document.querySelector('#go'))")
            for kind in ("mousePressed", "mouseReleased"):
                rpc(process, "pageCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": at[0], "y": at[1], "button": "left", "clickCount": 1})

        press_link("mailto:one@example.com")
        check(until(lambda: "wants to" in bar(process), 15, .02), f"A link to another app asks first ({bar(process)[:70]!r})")
        allow = "[...document.querySelectorAll('.permission-wrap.is-open .permission-bar button')].find(b => b.innerText.trim() === 'Allow')"
        check(js(process, allow + ".disabled") is True, "Allow doesn't take a click the moment the bar appears")
        check(not opened(), "...and nothing has opened")
        answer(process, "Allow")
        check(until(lambda: opened() == ["mailto:one@example.com"], 5), f"Allow opens it ({opened()})")

        press_link("mailto:two@example.com")
        check(until(lambda: "mailto:two@example.com" in opened(), 10), "On that site a real click doesn't ask again")

        rpc(process, "eval", script="(a => (a.href = 'mailto:scripted@example.com', a.click()))(document.querySelector('#go'))")
        check(until(lambda: "wants to" in bar(process), 15), "A click from the page's script asks, even on an allowed site")
        answer(process, "Block")
        check("mailto:scripted@example.com" not in opened(), "...and Block opens nothing")

        rpc(process, "eval", script=f"document.body.insertAdjacentHTML('beforeend', '<iframe id=f src=\"http://localhost:{port}/frame\" style=\"width:300px;height:80px;border:0\"></iframe>')")
        time.sleep(1.5)
        at = rpc(process, "eval", script="(r => [r.x + 20, r.y + 10])(document.querySelector('#f').getBoundingClientRect())")
        for kind in ("mousePressed", "mouseReleased"):
            rpc(process, "pageCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": at[0], "y": at[1], "button": "left", "clickCount": 1})
        said = until(lambda: bar(process) if "wants to" in bar(process) else "", 15) or ""
        check("localhost" in said and "127.0.0.1" not in said, f"Another site's frame asks in its own name ({said[:70]!r})")
        answer(process, "Allow")
        check(until(lambda: "mailto:framed@example.com" in opened(), 5), "...and Allow is for that one link")

        send(process, "forgetAppLinks")
        time.sleep(.5)
        press_link("mailto:three@example.com")
        check(until(lambda: "wants to" in bar(process), 15), "After forgetting, the site asks again")
        answer(process, "Block")
        rpc(process, "quit")
        process.wait(timeout=20)
    finally:
        server.shutdown()
        if process.poll() is None:
            process.kill()
    shutil.rmtree(RUN, ignore_errors=True)
    print(f"FAILED {len(FAILED)}: {FAILED}" if FAILED else "PASSED", flush=True)
    sys.exit(1 if FAILED else 0)


main()
