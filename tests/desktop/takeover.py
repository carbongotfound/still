"""Takeover on the real browser: an AI works in an ordinary tab of the main window, its controls float over that page,
and Take over, Hand back and Stop work there. No AI plan is used: a test MCP client plays the agent.
With --live it also runs one small real task through Claude (Haiku at low effort) from the sidebar chat and takes over mid-run,
recording each step line the pill shows (result.json live_steps).

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
user32.ChildWindowFromPointEx.argtypes = [wt.HWND, wt.POINT, wt.UINT]
user32.ChildWindowFromPointEx.restype = wt.HWND


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
    """The child window of Still's main window under a point given in interface (CSS) pixels, by its window regions;
    another app's window over Still (a full-screen lock, say) doesn't count, nor does the click-through window that draws
    the pill's edge and shadow over the page."""
    top = main_window(process.pid)
    scale = js(process, "devicePixelRatio")
    return user32.ChildWindowFromPointEx(top, wt.POINT(int(x * scale), int(y * scale)), 1 | 2)  # CWP_SKIPINVISIBLE, CWP_SKIPDISABLED (the edge window is disabled)


def name(h):
    """A window's class and its place, so a failed check says which window took the point."""
    if not h:
        return "none"
    buf, r = ctypes.create_unicode_buffer(64), wt.RECT()
    user32.GetClassNameW(h, buf, 64)
    user32.GetWindowRect(h, ctypes.byref(r))
    return f"{buf.value} {r.left},{r.top} {r.right - r.left}x{r.bottom - r.top}"


def rect(process, selector):
    return js(process, f"(() => {{ const r = document.querySelector({json.dumps(selector)})?.getBoundingClientRect(); return r ? [r.x, r.y, r.width, r.height] : null }})()")


def control(process):
    return js(process, "document.querySelector('.page-control')?.innerText ?? ''")


def working(process):
    """The pill is up with the agent at work (its step line, then its name and time)."""
    return js(process, "document.querySelector('.page-control')?.dataset.state === 'working'")


(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AgentsEnabled": True, "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}], "ApprovedAgents": ["Claude"], "AiHarness": "claude"},
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
    check(until(lambda: working(process), 10), "The pill shows over the agent's page")
    check(js(process, "!!document.querySelector('.tab-row.is-driven .tab-agent .mascot')"), "The tab shows the companion's mascot")

    pill, slot = rect(process, ".page-control"), rect(process, ".page-slot")
    page_host = host_at(process, slot[0] + slot[2] * .5, slot[1] + 60)
    pill_host = host_at(process, pill[0] + pill[2] * .5, pill[1] + pill[3] * .5)
    edge_host = host_at(process, slot[0] + 1, slot[1] + slot[3] * .5)
    check(page_host and pill_host and pill_host != page_host and edge_host != page_host, f"The page window leaves the pill and the glowing edge open, so they take clicks (page: {name(page_host)}; pill: {name(pill_host)}; edge: {name(edge_host)})")

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

    # The pill (Stage 11): the step line follows the agent within a second, then its name and time underneath.
    line = lambda: js(process, "document.querySelector('.page-control-text b')?.innerText ?? ''") or ""
    waiting = call_async(agent, "wait_for", text="never on this page", timeoutMs=4000)
    started = time.monotonic()
    check(until(lambda: line().startswith("Waiting for"), 1.5, .05) and time.monotonic() - started < 1.5, f"The step line shows the running step within a second: {line()}")
    waiting.get(timeout=15)
    started = time.monotonic()
    check(until(lambda: line() == "Thinking about the next step", 1.5, .05) and time.monotonic() - started < 1.5, "and between steps, that it's thinking")
    who = js(process, "document.querySelector('.page-control-text small')?.innerText ?? ''") or ""
    check(who.startswith("Claude, ") and who.split(", ")[1].rstrip("s").split("m")[0].strip().isdigit(), f"Under it, the name and the time it's been working: {who}")
    # One button system: 32px tall, 14px icons, 6px from icon to label, one radius; Stop names who it stops; Tab goes Take over, (Open chat,) Stop.
    look = json.loads(js(process, """JSON.stringify([...document.querySelectorAll('.page-control button:not(.page-more)')].map(b => { const s = getComputedStyle(b), i = b.querySelector('svg')?.getBoundingClientRect()
      return { h: Math.round(b.getBoundingClientRect().height), icon: i ? Math.round(i.width) : 0, gap: s.columnGap, radius: s.borderTopLeftRadius, label: b.getAttribute('aria-label') || b.innerText.trim(), title: b.title, tab: b.tabIndex } }))"""))
    check(look and all(b["h"] == 32 and b["icon"] == 14 and b["radius"] == look[0]["radius"] for b in look) and all(b["gap"] == "6px" for b in look if b["label"] in ("Take over", "Open chat")),
          "The pill's buttons share height, icon size, spacing and radius: " + json.dumps([(b["label"], b["h"], b["icon"], b["gap"]) for b in look]))
    check(look[-1]["label"] == "Stop Claude" and look[-1]["title"] == "Stop", "Stop has a tooltip (Stop) and a name: Stop Claude")
    order = [b["label"] for b in look if b["tab"] >= 0]
    check(order in (["Take over", "Stop Claude"], ["Take over", "Open chat", "Stop Claude"]), "The keyboard goes Take over, Open chat, Stop: " + " | ".join(order))
    # Contrast: both lines at 4.5:1 or more on the pill's own card, light and dark (the card is solid, so the page behind doesn't matter).
    CONTRAST = """(() => { const rgb = c => { const k = document.createElement('canvas').getContext('2d'); k.fillStyle = c; k.fillRect(0, 0, 1, 1); return [...k.getImageData(0, 0, 1, 1).data].slice(0, 3) }
      const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4 }); return .2126 * r + .7152 * g + .0722 * b }
      const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return +((x + .05) / (y + .05)).toFixed(2) }
      const pill = document.querySelector('.page-control'), bg = getComputedStyle(pill).backgroundColor
      return [ratio(getComputedStyle(pill.querySelector('.page-control-text b')).color, bg), ratio(getComputedStyle(pill.querySelector('.page-control-text small')).color, bg), getComputedStyle(pill).opacity] })()"""
    was_dark = js(process, "document.documentElement.classList.contains('dark')")
    for dark in (False, True):
        js(process, f"document.documentElement.classList.toggle('dark', {'true' if dark else 'false'})")
        time.sleep(.3)
        a, b, _ = json.loads(js(process, "JSON.stringify(" + CONTRAST + ")"))
        check(a >= 4.5 and b >= 4.5, f"{'Dark' if dark else 'Light'}: the step line is {a}:1 and the name line {b}:1 on the pill")
        shot(process, "pill-" + ("dark" if dark else "light"))
    js(process, f"document.documentElement.classList.toggle('dark', {'true' if was_dark else 'false'})")
    # Expanded: Enter on the pill opens the last steps above it, with the same buttons, and its spot on the page takes clicks; Esc closes it.
    js(process, "(p => { p.focus(); p.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })) })(document.querySelector('.page-control'))")
    steps = until(lambda: json.loads(js(process, "JSON.stringify([...document.querySelectorAll('.page-panel li')].map(l => l.innerText))") or "[]"), 3)
    check(steps and steps[-1] == "Thinking about the next step" and any(s.startswith("Typed into") or s.startswith("Clicked") for s in steps), "Enter opens the last steps: " + " / ".join(steps or []))
    check(js(process, "document.querySelectorAll('.page-panel-buttons button').length") >= 2, "with the same buttons")
    time.sleep(.4)
    panel = rect(process, ".page-panel")
    at = panel and host_at(process, panel[0] + panel[2] * .5, panel[1] + panel[3] * .5)
    check(panel and at != page_host, f"The open panel shows through the page and takes the clicks (panel: {name(at)})")
    shot(process, "pill-open")
    js(process, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    check(until(lambda: not js(process, "!!document.querySelector('.page-panel')"), 2), "Esc closes it")
    # A narrow window (under 520px): Take over and Open chat keep only their icons, with tooltips.
    rpc(process, "shellCdp", method="Emulation.setDeviceMetricsOverride", parameters={"width": 500, "height": 700, "deviceScaleFactor": 0, "mobile": False})
    time.sleep(.6)
    narrow = json.loads(js(process, "JSON.stringify([...document.querySelectorAll('.page-take, .page-chat')].map(b => [Math.round(b.getBoundingClientRect().width), getComputedStyle(b.querySelector('span')).display, b.title]))") or "[]")
    check(narrow and all(w == 32 and d == "none" and t for w, d, t in narrow), f"In a narrow window the buttons are icons with tooltips: {narrow}")
    shot(process, "pill-narrow")
    rpc(process, "shellCdp", method="Emulation.clearDeviceMetricsOverride", parameters={})
    time.sleep(.6)

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
    check(until(lambda: working(process), 5), "Switching to the agent's tab shows the pill again")

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
        send(process, "aiModel", harness="claude", model="haiku", effort="low")
        send(process, "aiToggle")
        send(process, "aiSend", text=f"Open {URL} in a new tab. Type Ada in the Name box and press Add. Then type Linus and press Add. Then type Grace and press Add. Then tell me how many names are listed.")
        live_tab = until(lambda: next((t for t in rpc(process)["tabs"] if "sheet" in t.get("Url", "") and t["Id"] != tab), None), 120, 1)
        seen = until(lambda: working(process), 60)
        check(bool(live_tab and seen), "Live: the chat's page opens in front with the pill")
        shot(process, "5-live-agent")
        steps = RESULT.setdefault("live_steps", [])
        def step():  # every step line the pill shows, in order
            line = js(process, "document.querySelector('.page-control-text b, .page-control-text span')?.innerText ?? ''") or ""
            if line and (not steps or steps[-1] != line):
                steps.append(line)
        until(lambda: step() or "Ada" in (rpc(process, "eval", script="names.innerText") or ""), 90, .5)
        js(process, "document.querySelector('.page-take').click()")
        until(lambda: "You're in control" in control(process), 5)
        rpc(process, "eval", script="who.focus()")
        rpc(process, "pageCdp", method="Input.insertText", parameters={"text": "Typed by you"})
        rpc(process, "eval", script="add.click()")
        shot(process, "6-live-user")
        time.sleep(4)
        js(process, "document.querySelector('.page-take').click()")
        send(process, "aiToggle")  # close the sidebar, so Open chat has to open it
        until(lambda: not js(process, "!!document.querySelector('.ai-sidebar')"), 5)
        js(process, "document.querySelector('.page-chat')?.click()")
        check(until(lambda: js(process, "!!document.querySelector('.ai-sidebar')"), 5), "Live: Open chat opens the run's chat in the sidebar")
        done = until(lambda: step() or not js(process, "!!document.querySelector('[aria-label=Stop]')") and "Grace" in (rpc(process, "eval", script="names.innerText") or ""), 180, .5)
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
