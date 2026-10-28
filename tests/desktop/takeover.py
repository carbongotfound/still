"""Takeover on the real browser: an AI works in an ordinary tab of the main window, its controls float over that page,
and Take over, Hand back and Stop work there. No AI plan is used: a test MCP client plays the agent.
With --live it also runs one small real task through Claude (Haiku) from the sidebar chat and takes over mid-run.

Run: python tests/desktop/takeover.py artifacts/Still-QA/Still.exe [--live]
Screenshots: docs/agentic/compare/takeover-*.png
"""
import ctypes
import ctypes.wintypes as wt
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
from mcp_client import Mcp, call_async  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
LIVE = "--live" in sys.argv
RUN = ROOT / "artifacts" / ("takeover-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
PROFILE.mkdir(parents=True)
OUT = ROOT / "docs" / "agentic" / "compare"
RESULT = {"checks": []}

PAGE = """<!doctype html><title>Sign-up sheet</title>
<style>body{font:16px system-ui;margin:40px;max-width:640px}input{font:inherit;padding:8px;width:280px}button{font:inherit;padding:8px 16px}
li{margin:6px 0}</style>
<h1>Sign-up sheet</h1><p>Add a name, then press Add.</p>
<input id=who aria-label="Name" placeholder="Name"> <button id=add>Add</button>
<ol id=names></ol>
<script>add.onclick=()=>{if(!who.value.trim())return;const li=document.createElement('li');li.textContent=who.value;names.append(li);who.value=''}</script>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{SERVER.server_port}/sheet"


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def shot(process, name):
    rpc(process, "capture", name=name + ".png")
    shutil.copy(PROFILE / (name + ".png"), OUT / ("takeover-" + name + ".png"))


user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # physical pixels, like the windows themselves


def main_window(pid):
    found = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        rect = wt.RECT()
        if owner.value == pid and user32.IsWindowVisible(hwnd) and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            found.append(((rect.right - rect.left) * (rect.bottom - rect.top), hwnd))
        return True
    user32.EnumWindows(each, 0)
    return max(found)[1]


def host_at(process, x, y):
    """The child window of Still's main window under a point given in interface (CSS) pixels."""
    top = main_window(process.pid)
    origin = wt.POINT(0, 0)
    user32.ClientToScreen(top, ctypes.byref(origin))
    scale = js(process, "devicePixelRatio")
    hit = user32.WindowFromPoint(wt.POINT(int(origin.x + x * scale), int(origin.y + y * scale)))
    while hit and user32.GetParent(hit) and user32.GetParent(hit) != top:
        hit = user32.GetParent(hit)
    return hit


def rect(process, selector):
    return js(process, f"(() => {{ const r = document.querySelector({json.dumps(selector)})?.getBoundingClientRect(); return r ? [r.x, r.y, r.width, r.height] : null }})()")


def control(process):
    return js(process, "document.querySelector('.page-control')?.innerText ?? ''")


(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 5, "Welcome": False, "Preferences": {"AgentsEnabled": True, "ApprovedAgents": ["Claude"], "AiHarness": "claude"},
    "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
process = launch(EXE, PROFILE)
agent = None
try:
    agent = Mcp(EXE, "Claude", PROFILE)
    ok, opened = agent.call("open_tab", url=URL)
    tab = json.loads(opened)["tabId"] if ok else ""
    state = rpc(process)
    shown = js(process, f"[...document.querySelectorAll('.tab-row')].some(r => r.dataset.tabId === {json.dumps(tab)})")
    check(ok and shown, "The agent's tab is an ordinary tab in the main strip")
    send(process, "select", id=tab)
    check(until(lambda: "Controlled by" in control(process), 10), "The pill shows over the agent's page")
    check(js(process, "!!document.querySelector('.tab-row.is-driven .tab-agent .mascot')"), "The tab shows the companion's mascot")

    pill, slot = rect(process, ".page-control"), rect(process, ".page-slot")
    page_host = host_at(process, slot[0] + slot[2] * .5, slot[1] + 60)
    pill_host = host_at(process, pill[0] + pill[2] * .5, pill[1] + pill[3] * .5)
    edge_host = host_at(process, slot[0] + 1, slot[1] + slot[3] * .5)
    check(page_host and pill_host and pill_host != page_host and edge_host != page_host, "The page window leaves the pill and the glowing edge open, so they take clicks")

    ok1, _ = agent.call("type", selector="#who", text="Ada from the agent")
    ok2, _ = agent.call("click", selector="#add")
    check(ok1 and ok2 and "Ada from the agent" in rpc(process, "eval", script="names.innerText"), "The agent types and clicks in the page")
    shot(process, "1-agent")
    # The real screen, not a composed capture: the pill must show through the page's window.
    from PIL import ImageGrab
    box = wt.RECT()
    user32.GetWindowRect(main_window(process.pid), ctypes.byref(box))
    user32.SetForegroundWindow(main_window(process.pid))
    time.sleep(.5)
    ImageGrab.grab((box.left, box.top, box.right, box.bottom), all_screens=True).save(OUT / "takeover-1-agent-screen.png")

    # Take over in the middle of a call: the call returns at once and the agent waits.
    waiting = call_async(agent, "wait_for", text="never on this page", timeoutMs=10000)
    time.sleep(.8)
    started = time.monotonic()
    js(process, "document.querySelector('.page-take').click()")
    ok, said = waiting.get(timeout=15)
    check(not ok and "took over" in said and time.monotonic() - started < 2.5, "Take over stops the running call right away")
    check(until(lambda: "You're in control" in control(process), 5), "The pill says the user is in control")

    # The user types in that same page while the agent's next call waits.
    rpc(process, "eval", script="who.focus()")
    rpc(process, "pageCdp", method="Input.insertText", parameters={"text": "Grace typed this"})
    rpc(process, "eval", script="add.click()")
    pending = call_async(agent, "type", selector="#who", text="Linus after hand back")
    time.sleep(2)
    check(pending.empty() and "Linus" not in rpc(process, "eval", script="document.body.innerText"), "The agent waits while the user drives")
    check("Grace typed this" in rpc(process, "eval", script="names.innerText"), "The user can type in the page")
    shot(process, "2-user")
    js(process, "document.querySelector('.page-take').click()")
    ok, _ = pending.get(timeout=15)
    agent.call("click", selector="#add")
    check(ok and "Linus after hand back" in rpc(process, "eval", script="names.innerText"), "Hand back lets the agent carry on")
    shot(process, "3-resumed")

    # In the background the tab keeps its marker; switching back shows the pill.
    send(process, "select", id="home")
    until(lambda: not control(process), 5)
    check(not control(process) and js(process, "!!document.querySelector('.tab-row.is-driven .mascot')"), "A background agent tab keeps its mascot marker")
    shot(process, "4-background")
    send(process, "select", id=tab)
    check(until(lambda: "Controlled by" in control(process), 5), "Switching to the agent's tab shows the pill again")

    js(process, "document.querySelector('.page-stop').click()")
    check(until(lambda: not control(process) and not js(process, "!!document.querySelector('.tab-row.is-driven')"), 5), "Stop removes the pill and the marker")
    time.sleep(.5)
    check(host_at(process, pill[0] + pill[2] * .5, pill[1] + pill[3] * .5) == host_at(process, slot[0] + slot[2] * .5, slot[1] + 60), "After Stop the whole page takes clicks again")
    ok, said = agent.call("list_tabs")
    check(not ok and "Stop" in said, "The agent is told the user pressed Stop")

    if LIVE:
        agent.close(); agent = None
        time.sleep(31)  # Stop holds the agent off for 30 seconds
        send(process, "aiCheck")
        time.sleep(3)
        send(process, "aiAdvanced", on=True)  # without Advanced, the companion's mode picks the model
        send(process, "aiModel", harness="claude", model="haiku")
        send(process, "aiToggle")
        send(process, "aiSend", text=f"Open {URL} in a new tab. Type Ada in the Name box and press Add. Then type Linus and press Add. Then type Grace and press Add. Then tell me how many names are listed.")
        live_tab = until(lambda: next((t for t in rpc(process)["tabs"] if "sheet" in t.get("Url", "") and t["Id"] != tab), None), 120, 1)
        seen = until(lambda: "Controlled by" in control(process), 60)
        check(bool(live_tab and seen), "Live: the chat's page opens in front with the pill")
        shot(process, "5-live-agent")
        until(lambda: "Ada" in (rpc(process, "eval", script="names.innerText") or ""), 90, .5)
        js(process, "document.querySelector('.page-take').click()")
        until(lambda: "You're in control" in control(process), 5)
        rpc(process, "eval", script="who.focus()")
        rpc(process, "pageCdp", method="Input.insertText", parameters={"text": "Typed by you"})
        rpc(process, "eval", script="add.click()")
        shot(process, "6-live-user")
        time.sleep(4)
        js(process, "document.querySelector('.page-take').click()")
        send(process, "aiToggle")  # close the sidebar, so Go to chat has to open it
        until(lambda: not js(process, "!!document.querySelector('.ai-sidebar')"), 5)
        js(process, "document.querySelector('.page-chat')?.click()")
        check(until(lambda: js(process, "!!document.querySelector('.ai-sidebar')"), 5), "Live: Go to chat opens the run's chat in the sidebar")
        done = until(lambda: not js(process, "!!document.querySelector('[aria-label=Stop]')") and "Grace" in (rpc(process, "eval", script="names.innerText") or ""), 180, 1)
        names = rpc(process, "eval", script="names.innerText") or ""
        RESULT["live_names"] = names
        check(bool(done) and "Typed by you" in names and "Grace" in names, "Live: the task finishes after the user hands it back")
        shot(process, "7-live-done")
finally:
    if agent:
        agent.close()
    try:
        rpc(process, "quit")
        process.wait(timeout=15)
    except Exception:
        process.kill()
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
    failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
    print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
