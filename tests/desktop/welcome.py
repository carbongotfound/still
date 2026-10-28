"""Setup on a fresh profile, the tour, Run setup again, and the look editor.

The 9 steps are walked like a person would: pick an AI, color a helper, give it a face and a name, say who you are,
pick interests, keep the Classic layout, try the permission card, and start the first task. The task runs on a fake
AI app (a manifest in Still's agents folder): it searches, opens a page beside the chat and reads it for a while.
The whole run is recorded with ffmpeg, frames taken from the window itself.

Run: python tests/desktop/welcome.py artifacts/Still-QA/Still.exe
Out: docs/agentic/mascot/look-*.png (the look editor for 6 companions), artifacts/welcome-*/setup.mp4 (the recording)
"""
import ctypes
import ctypes.wintypes
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("welcome-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
LOOKS = ROOT / "docs" / "agentic" / "mascot"
RESULT = {"checks": []}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


# ---- a recipe site and a search page for the first task ----
RECIPES = [("Lemon garlic pasta", "/recipes/pasta", "20 minutes, pantry staples, 4.8 stars from 2,100 cooks."),
           ("Sheet pan chicken and vegetables", "/recipes/sheet-pan", "One pan, 35 minutes, 4.7 stars."),
           ("Black bean tacos", "/recipes/tacos", "15 minutes, vegetarian, 4.6 stars.")]


def page(url):
    if url.path == "/search":
        rows = "".join(f'<div class="result"><h2><a class="result__a" href="{p}">{t}</a></h2><a class="result__snippet">{s}</a></div>' for t, p, s in RECIPES)
        return f"<!doctype html><meta charset=utf-8><title>Search</title><main>{rows}</main>"
    title, _, about = next((r for r in RECIPES if r[1] == url.path), RECIPES[0])
    steps = "".join(f"<li>Step {i}: stir, taste and keep going.</li>" for i in range(1, 7))
    return f"""<!doctype html><meta charset=utf-8><title>{title} · Weeknight Kitchen</title>
<style>body{{margin:0;font:16px Georgia,serif;color:#2b2420;background:#fbf7f1}}header{{padding:16px 40px;background:#2f4a3a;color:#fff;font:600 18px system-ui}}
main{{max-width:760px;margin:0 auto;padding:28px 40px}}.hero{{height:220px;border-radius:16px;background:linear-gradient(135deg,#f3d9b5,#e7a96b)}}h1{{font-size:34px;margin:22px 0 6px}}li{{margin:8px 0}}</style>
<header>Weeknight Kitchen</header><main><div class=hero></div><h1>{title}</h1><p>{about}</p><h2>Steps</h2><ol>{steps}</ol></main>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = page(urllib.parse.urlparse(self.path)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
SITE = f"http://127.0.0.1:{SERVER.server_port}"

FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt}) + "\n")
    site = open(os.path.join(here, "site.txt")).read().strip()
    def say(e): print(json.dumps(e), flush=True)
    server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
    still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = 0
    def request(method, params):
        global n
        n += 1
        still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params}) + "\n").encode()); still.stdin.flush()
        for line in still.stdout:
            try: m = json.loads(line)
            except ValueError: continue
            if m.get("id") == n: return m
    request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
    still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
    def call(tool, shown=True, **a):
        if shown: say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t%d" % (n + 1), "name": "mcp__still__" + tool, "input": a}]}})
        r = request("tools/call", {"name": tool, "arguments": a})["result"]
        if shown: say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t%d" % n, "is_error": bool(r.get("isError"))}]}})
        return not r.get("isError")
    def reply(text): say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    reply("On it. I'll look for easy dinners and check the best one.")
    call("web_search", query="easy weeknight dinner recipes")
    call("open_tab", url=site + "/recipes/pasta")
    end = time.time() + float(open(os.path.join(here, "seconds.txt")).read())
    while time.time() < end and call("read_page", shown=False, text=False): time.sleep(.5)
    reply("**Lemon garlic pasta is the easiest win tonight.**\n\n| Dinner | Time | Rating |\n|---|---|---|\n| Lemon garlic pasta | 20 min | 4.8 |\n| Sheet pan chicken | 35 min | 4.7 |\n| Black bean tacos | 15 min | 4.6 |\n\n>> Make a shopping list\n>> Find a vegetarian one\n>> Save these as a CSV")
    still.stdin.close()
''')


# ---- recording the window with ffmpeg ----
def window_of(pid):
    """The process's biggest visible top-level window: its handle, and where its visible frame sits inside it."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def each(hwnd, _):
        owner = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            whole, frame = ctypes.wintypes.RECT(), ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(whole))
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(frame), ctypes.sizeof(frame))  # DWMWA_EXTENDED_FRAME_BOUNDS: no invisible borders
            found.append((hwnd, whole.right - whole.left, whole.bottom - whole.top, frame.left - whole.left, frame.top - whole.top, frame.right - frame.left, frame.bottom - frame.top))
        return True
    user32.EnumWindows(each, 0)
    return max(found, key=lambda f: f[1] * f[2], default=None)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


def record(pid, out, fps=20):
    """Frames come from the window itself (PrintWindow with full content), so it records wherever the window is, even off screen."""
    hwnd, ww, wh, x, y, w, h = window_of(pid)
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    screen = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, ww, wh)
    gdi32.SelectObject(mem, bitmap)
    info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), ww, -wh, 1, 32, 0)  # top-down rows
    pixels = ctypes.create_string_buffer(ww * wh * 4)

    def grab():
        user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT: WebView2 pages too
        gdi32.GetDIBits(mem, bitmap, 0, wh, pixels, ctypes.byref(info), 0)
        return memoryview(pixels.raw)

    first, middle = grab(), (y + h // 2) * ww * 4
    edge = next((i for i in range(16) if sum(first[middle + (x + i) * 4:middle + (x + i) * 4 + 3]) > 48), 0)  # the resize border comes out black
    x, y, w, h = x + edge, y + edge, (w - 2 * edge) // 2 * 2, (h - 2 * edge) // 2 * 2  # even sizes for H.264
    ffmpeg = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}", "-use_wallclock_as_timestamps", "1", "-i", "-",
                               "-fps_mode", "cfr", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    done = threading.Event()

    def frames():
        try:
            while not done.is_set():
                started = time.perf_counter()
                rows = grab()
                ffmpeg.stdin.write(b"".join(rows[(y + r) * ww * 4 + x * 4:(y + r) * ww * 4 + (x + w) * 4] for r in range(h)))
                done.wait(max(0, 1 / fps - (time.perf_counter() - started)))
        finally:
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(0, screen)
            ffmpeg.stdin.close()

    ffmpeg.thread = threading.Thread(target=frames, daemon=True)
    ffmpeg.thread.start()
    ffmpeg.done = done
    return ffmpeg


def stop(recorder):
    recorder.done.set()
    recorder.thread.join(timeout=10)
    recorder.wait(timeout=60)


# ---- driving the interface ----
def click(process, selector):
    return js(process, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.click(); return !!e }})()")


def click_text(process, selector, words):
    return js(process, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => e.innerText.trim().includes({json.dumps(words)})); e?.click(); return !!e }})()")


def type_into(process, selector, value):
    """Types into a React-controlled input or textarea."""
    js(process, f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; e.focus();
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {json.dumps(value)});
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); return true }})()""")


def step_now(process):
    return js(process, "Number(document.querySelector('.ob-dots')?.getAttribute('aria-valuenow') ?? 0)")


def next_step(process, pause=1.6):
    at = step_now(process)
    click(process, ".ob-next")
    until(lambda: step_now(process) == at + 1, 5)
    time.sleep(pause)  # the helper's lines come in one by one


def state():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    (BIN / "site.txt").write_text(SITE)
    (BIN / "seconds.txt").write_text("14")
    (BIN / "fakeagent.cmd").write_text(f'@"{sys.executable}" -I "{BIN / "fake_agent.py"}" %*\r\n')
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    process = launch(EXE, PROFILE, {**os.environ, "STILL_QA_SEARCH": SITE + "/search?q="})
    try:
        setup(process)
        tour(process)
        again(process)
        looks(process)
        check(not js(process, "window.__shellErrors?.length") and not rpc(process).get("shellErrors"), "No interface errors")
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


def setup(process):
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # window sizes in real pixels
    check(until(lambda: js(process, "!!document.querySelector('.welcome.ob .ob-next')"), 20), "A fresh profile opens on setup")
    check(js(process, "document.querySelector('.ob-dots')?.getAttribute('aria-valuemax')") == "9", "Setup has 9 steps")
    time.sleep(1)
    recorder = record(process.pid, RUN / "setup.mp4")
    try:
        time.sleep(3.5)
        next_step(process)  # hello -> import
        check(js(process, "document.querySelectorAll('.ob-option').length") == 2, "Step 2 offers to bring your stuff over and to open your links in Still")
        next_step(process)  # -> ai
        if not until(lambda: click_text(process, ".byo-main", "Fake agent"), 4):
            click(process, ".byo-more")  # agents you added sit under More agents
            until(lambda: click_text(process, ".byo-main", "Fake agent"), 6)
        check(until(lambda: js(process, "!!document.querySelector('.byo-row[data-chosen] .byo-ok')"), 10), "Step 3: picking an AI app that's signed in")
        time.sleep(1)
        next_step(process)  # -> helper
        check(js(process, "document.querySelectorAll('.ob-faces button').length") == 0, "The helper starts as a plain shape, before a color")
        click(process, ".ob-colors button[aria-label=Cornflower]")
        check(until(lambda: js(process, "document.querySelectorAll('.ob-faces button').length") == 8, 3), "Picking a color brings up faces")
        time.sleep(1.2)
        click(process, ".ob-faces button[aria-label='Face 2']")
        until(lambda: js(process, "!!document.querySelector('.ob-name-box input')"), 3)
        time.sleep(1.2)
        type_into(process, ".ob-name-box input", "Miso")
        time.sleep(1.4)
        next_step(process)  # -> you
        mate = until(lambda: next((c for c in state().get("Preferences", {}).get("Companions", []) if c["Name"] == "Miso"), None), 5)
        look = json.loads(mate["Look"]) if mate and mate.get("Look") else {}
        check(look.get("color") == "#8fb8e8" and look.get("eyes") == "sparkle", "Step 4 saves the helper's name, color and face")
        type_into(process, ".ob-name-box input[aria-label='Your name']", "Sam")
        time.sleep(1)
        next_step(process)  # -> interests
        check("Thanks, Sam" in (js(process, "document.querySelector('.ob-talk')?.innerText ?? ''") or ""), "Step 6 greets you by name")
        for k in ("Cooking", "Travel", "Music"):
            click_text(process, ".ob-chips.is-big button", k)
            time.sleep(.35)
        time.sleep(.8)
        next_step(process)  # -> layout
        shared = PROFILE / "companions" / "memory.md"
        memory = until(lambda: shared.exists() and "cooking" in shared.read_text(encoding="utf-8") and shared.read_text(encoding="utf-8"), 5) or ""
        check("My name is Sam." in memory and "cooking, travel, music" in memory, "Your name and interests go into shared memory")
        check(js(process, "document.querySelector('.ob-layouts [aria-checked=true]')?.innerText ?? ''").startswith("Classic"), "Step 7: Classic tabs are the default")
        time.sleep(.8)
        next_step(process)  # -> charge
        check(js(process, "!!document.querySelector('.ob-ask')"), "Step 8 shows a sample permission card")
        time.sleep(1.2)
        click_text(process, ".ob-ask button", "Allow once")
        check(until(lambda: "only go ahead when you say so" in (js(process, "document.querySelector('.ob-ask')?.innerText ?? ''") or ""), 3), "Answering it explains what happened")
        time.sleep(1.4)
        next_step(process)  # -> start
        tasks = js(process, "[...document.querySelectorAll('.ob-tasks button')].map(b => b.innerText.trim())") or []
        check(tasks[:1] == ["Find a dinner I can make tonight"], "Step 9 suggests first tasks that match your interests")
        click(process, ".ob-tasks button")
        time.sleep(1)
        check(js(process, "document.querySelector('.ob-next')?.innerText.trim()") == "Let's go", "Picking one turns Finish into Let's go")
        click(process, ".ob-next")
        check(until(lambda: not js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')"), 5), "Setup closes")
        split = until(lambda: js(process, "!!document.querySelector('.page-column.is-split .page-pane') && !!document.querySelector('.page-control')"), 20)
        check(split, "The first task runs: the chat on the left, its page on the right, the pill at work")
        time.sleep(7)
    finally:
        stop(recorder)
    tabs = rpc(process)["tabs"]
    check(sum(1 for t in tabs if not t["InChat"]) == 1 and any(t["InChat"] and "/recipes/" in t["Url"] for t in tabs), "Its page stays out of the tab strip")
    rows = js(process, "[...document.querySelectorAll('.chat-pane .ai-look')].map(r => r.innerText)") or []
    check(any("Searched" in r for r in rows), "The chat shows its search as one row")
    check(until(lambda: js(process, "document.querySelectorAll('.chat-pane .ai-next-step').length") == 3, 30), "It finishes with three next steps")
    size = (RUN / "setup.mp4").stat().st_size if (RUN / "setup.mp4").exists() else 0
    check(size > 200_000, f"The recording is saved ({size // 1024} KB)")


def new_tab(process):
    """A new tab opens with the address bar's suggestions; the tour waits until they close, as a person would close them."""
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.address-bar.is-editing')"), 3)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")


def tour(process):
    new_tab(process)
    check(until(lambda: js(process, "!!document.querySelector('.tour-card')"), 10), "Back on the new tab page, the tour starts")
    seen = []
    for _ in range(8):
        card = js(process, "document.querySelector('.tour-card')?.innerText ?? ''") or ""
        if not card:
            break
        seen.append(card.split("\n")[1] if "\n" in card else card)
        if len(seen) == 1:
            check("Miso works in background tabs" in card, "Its first card names your helper")
            rpc(process, "capture", name="tour.png")
        click_text(process, ".tour-card button", "Next") or click_text(process, ".tour-card button", "Done")
        time.sleep(.6)
    check(len(seen) == 5 and not js(process, "!!document.querySelector('.tour')"), f"Five coach marks, then it's done ({', '.join(seen)})")
    check(js(process, "localStorage.getItem('still.tour')") is None, "It doesn't come back")


def again(process):
    send(process, "welcomeAgain")
    check(until(lambda: "I'm Miso, your helper." in (js(process, "document.querySelector('.ob-talk')?.innerText ?? ''") or ""), 10), "Run setup again opens setup with your helper")
    click(process, ".ob-skip-all")
    check(until(lambda: not js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')"), 5) and until(lambda: state().get("Welcome") is False, 5), "Skip setup closes it")
    new_tab(process)
    check(until(lambda: js(process, "!!document.querySelector('.tour-card')"), 10), "The tour offers itself again")
    click_text(process, ".tour-card button", "Skip tour")
    check(until(lambda: not js(process, "!!document.querySelector('.tour')"), 3) and js(process, "localStorage.getItem('still.tour')") is None, "Skip tour ends it")


CREW = [("Juniper", "#a6cf98", {"shape": "kitty", "eyes": "iris", "pupil": .3, "brows": "thin", "mouth": "cat", "hat": "beret"}),
        ("Pebble", "#c9c6c0", {"shape": "pebble", "eyes": "button", "mouth": "smile", "hair": "curls", "hairColor": "#3b2f2a"}),
        ("Clementine", "#f0a989", {"shape": "fox", "eyes": "almond", "brows": "straight", "mouth": "smirk", "hat": "headphones"}),
        ("Bao", "#f2ede4", {"shape": "mochi", "eyes": "happy", "mouth": "open", "hair": "sprout", "hairColor": "#9ccf9a"}),
        ("Indigo", "#7aa3dc", {"shape": "drop", "eyes": "shine", "brows": "soft", "mouth": "grin", "hat": "beanie"})]
BASE = {"shape": "round", "head": 1, "ears": 0, "eyes": "dot", "eyeGap": 0, "eyeY": 0, "eyeSize": 0, "pupil": 0, "brows": "none", "browGap": 0, "browY": 0,
        "browSize": 0, "browTilt": 0, "mouth": "smile", "mouthY": 0, "mouthSize": 0, "blush": True, "hair": "", "hairColor": "#6b4a35", "hat": ""}


def looks(process):
    """The look editor, open for six companions."""
    for i, (name, color, look) in enumerate(CREW):
        send(process, "companionSave", id=f"crew{i}", name=name, job="", look=json.dumps({**BASE, "color": color, **look}))
    new_tab(process)
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 10)
    click(process, ".home-rail-item[aria-label=Companions]")
    six = until(lambda: js(process, "document.querySelectorAll('.mate-card').length") == 6, 10)
    check(six, f"Six companions on the Companions page ({js(process, 'document.querySelectorAll(\'.mate-card\').length')})")
    LOOKS.mkdir(parents=True, exist_ok=True)
    shot = 0
    for name in ["Miso"] + [c[0] for c in CREW]:
        click(process, f".mate-portrait[aria-label='Edit {name}']")
        until(lambda: js(process, "!!document.querySelector('.companion-dialog')"), 5)
        click_text(process, ".companion-dialog .companion-look button", "Customize")
        if until(lambda: js(process, "!!document.querySelector('.look-dialog canvas, .look-dialog .look-stage img')"), 8):
            time.sleep(1.8)  # the model loads and settles
            rpc(process, "capture", name=f"look-{name.lower()}.png")
            shutil.copy(PROFILE / f"look-{name.lower()}.png", LOOKS / f"look-{name.lower()}.png")
            shot += 1
        click_text(process, ".look-dialog .look-foot button", "Cancel")
        until(lambda: not js(process, "!!document.querySelector('.look-dialog')"), 3)
        js(process, "document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        if not until(lambda: not js(process, "!!document.querySelector('.companion-dialog')"), 2):
            click(process, ".companion-dialog [data-slot=dialog-close]")
            until(lambda: not js(process, "!!document.querySelector('.companion-dialog')"), 3)
    check(shot == 6, f"The look editor opens for all six ({shot} screenshots)")


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
