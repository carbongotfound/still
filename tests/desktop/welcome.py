"""Setup on a fresh profile, the tour, Run setup again, "Set me up with <name>", and the look editor.

A fresh profile starts with the intro (skipped with Space) and no companions. The steps of the Quick setup are walked
like a person would: pick an AI, pick Glint from the crew and make your own companion too (a color, a face, a name), pick
the main one, say who you are, pick interests, keep the Classic layout, try the permission card, and start the first
task. Setup can't finish with no companion, and the last one can't be deleted. Quick setup runs no AI at all. The task runs on a fake AI app (a manifest in Still's agents folder): it
searches, opens a page beside the chat and reads it for a while. The whole run is recorded with ffmpeg, frames taken
from the window itself. Then setup runs again and is skipped ("Nothing right now" starts nothing), and the AI setup
runs: the fake app asks one question, then picks settings, which apply, show in a summary and undo one by one.

A second fresh profile lets the intro play out, then shoots the crew with 0, 1 and 3 picked and the main pick, light and dark.

Run: python tests/desktop/welcome.py artifacts/Still-QA/Still.exe
Out: docs/agentic/mascot/look-*.png (the look editor for 6 companions), artifacts/welcome-*/setup.mp4 (the recording),
     artifacts/welcome-*/shots/pick-*.png
"""
import ctypes
import ctypes.wintypes
import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

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
    def reply(text): say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    # "Set it up with <name>": a follow-up on each answer until it knows them or hears "that's enough", then the settings.
    # Later turns carry only the answer, so a file keeps the topics left and the lead's id from the first prompt's team.
    asked = os.path.join(here, "setup.json")
    if "set Still up around them" in prompt or os.path.exists(asked):
        say({"type": "system", "subtype": "init", "session_id": "setup-1"})
        if not os.path.exists(asked):
            lead = next(l[2:].split(":")[0] for l in prompt.splitlines() if l.startswith("- ") and ": Miso," in l)
            json.dump({"lead": lead, "left": ["goals", "tools", "replies", "schedule"]}, open(asked, "w"))
            reply(json.dumps({"say": "Hi! I'd like to get to know you a bit.", "question": "What do you work on these days?", "options": ["I run a small bakery", "Research", "Sales"]}))
            sys.exit(0)
        talk = json.load(open(asked))
        answer = prompt.strip()
        ask = {"goals": ("What's the big goal for the next few months?", ["Grow wholesale", "Hire help"]),
               "tools": ("Which apps and sites are open all day?", ["Gmail", "Shopify", "Sheets"]),
               "replies": ("How do you like my answers?", ["Short and direct", "Detailed"]),
               "schedule": ("When does your day start and end?", ["5am to 1pm", "9 to 5"])}
        if not answer.startswith("That's enough") and talk["left"]:
            topic = talk["left"].pop(0) if answer == "(skip)" or "wholesale" in answer.lower() or talk.get("work") else None
            talk["work"] = True
            json.dump(talk, open(asked, "w"))
            if topic is None:
                reply(json.dumps({"say": f"Nice: {answer.lower()}.", "question": f"Tell me more: who buys from you, walk-ins or other businesses?", "options": []}))
            else:
                reply(json.dumps({"say": "No problem, let's skip that." if answer == "(skip)" else "Got it.", "question": ask[topic][0], "options": ask[topic][1]}))
            sys.exit(0)
        os.remove(asked)
        reply(json.dumps({"say": "Got it, you're all set.", "done": True, "settings": {"name": "Sammy", "interests": ["Baking", "Wholesale"], "layout": "", "theme": "Dark",
            "search": "", "pinned": [{"title": "Weeknight Kitchen", "url": site + "/recipes/pasta"}], "sites": [], "newTab": "", "agent": "careful",
            "tone": "Keep it short and cheerful.", "memories": ["Runs a small bakery that sells to cafes.", "uses Gmail and Shopify all day. Has  two cats"],
            "hire": ["scout", "researcher", "nobody"],
            "companions": [{"id": talk["lead"], "instructions": "Keep my wholesale orders on track and tell me when a cafe is late to pay.", "memories": ["Bakes sourdough for six cafes."]},
                           {"id": "scout", "instructions": "Find me a second baker who can start at 5am.", "memories": ["Hiring a second baker for early shifts."]},
                           {"id": "nobody", "instructions": "Not on the team, so this goes nowhere."}],
            "routines": [{"id": "scout", "text": "Check new applicants for the baker job and pick the best three.", "time": "08:30", "days": [1, 2, 3, 4, 5]}],
            "first": "Find three flour suppliers near me with next-day delivery."}}))
        sys.exit(0)
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
    """Frames come from the window itself (PrintWindow with full content), so it records wherever the window is, even off screen.
    On the Mac, macOS records the whole screen to a .mov (Screen Recording must be allowed for the terminal or SSH)."""
    if MAC:
        recorder = subprocess.Popen(["screencapture", "-v", "-x", "-C", str(Path(out).with_suffix(".mov"))], stdin=subprocess.DEVNULL)
        recorder.done = None
        return recorder
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
    if recorder.done is None:  # screencapture stops and saves at Ctrl-C (a keypress needs a terminal, which SSH runs lack)
        recorder.send_signal(signal.SIGINT)
        recorder.wait(timeout=60)
        return
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
    time.sleep(pause)  # the companion's lines come in one by one


def not_now(process, pause=1.6):
    """A step that asks for something: Continue waits for an answer, and "Not now" moves on without one."""
    click(process, ".ob-not-now")
    time.sleep(pause)


def tools(process):
    """Connect your tools, with no key: the belt of apps, the key field, the note about Composio, and Skip."""
    check(until(lambda: "Want the team to work in your apps?" in talk_text(process), 4), "After hiring, setup offers to connect your apps")
    until(lambda: js(process, "document.querySelectorAll('.plug-row').length") == 2, 5)
    rows = js(process, "[...document.querySelectorAll('.plug-row')].map(r => [r.classList.contains('is-reverse'), r.querySelectorAll('.plug-chip:not([aria-hidden=true])').length])") or []
    check(rows == [[False, 12], [True, 12]], f"Two rows of apps glide opposite ways ({rows})")
    check(js(process, "document.querySelector('.plug-track')?.getAnimations().length > 0"), "The belt moves")
    box = js(process, "(() => { const r = document.querySelector('.plug-belt').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2] })()") or [0, 0]
    rpc(process, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": box[0], "y": box[1]})
    check(until(lambda: js(process, "getComputedStyle(document.querySelector('.plug-track')).animationPlayState") == "paused", 2), "It pauses under the pointer")
    rpc(process, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": 5, "y": 5})
    rpc(process, "shellCdp", method="Emulation.setEmulatedMedia", parameters={"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    check(until(lambda: js(process, "[...document.querySelectorAll('.plug-belt .plug-chip')].filter(c => c.getClientRects().length).length === 24 && !document.querySelector('.plug-track').getAnimations().length"), 3), "With reduced motion it's a still grid")
    rpc(process, "shellCdp", method="Emulation.setEmulatedMedia", parameters={"features": [{"name": "prefers-reduced-motion", "value": ""}]})
    until(lambda: js(process, "!!document.querySelector('.plug-row')"), 3)
    names = js(process, "[...document.querySelectorAll('.plug-row .plug-chip')].map(c => c.lastChild.textContent)") or []
    check(all(n in names for n in ("Gmail", "Google Calendar", "Slack", "Notion", "GitHub", "Google Drive", "Linear", "HubSpot")), "Gmail, Calendar, Slack, Notion, GitHub, Drive, Linear and HubSpot are on it, as name chips")
    check(js(process, "document.querySelector(\"input[aria-label='Composio API key']\")?.type") == "password", "Below it, a field for your Composio API key")
    words = talk_text(process)
    check("Get a key" in words and "Project Settings" in words and "ak_" in words and "third-party service" in words and "pricing" not in words, "With where to get a project key (ak_), and a note that Composio is a third party (no pricing)")
    check("Skills & plugins" in words, "No key: it says you can do it later in Skills & plugins")
    foot = js(process, "[...document.querySelectorAll('.ob-foot button')].map(b => b.innerText.trim() + (b.disabled ? ' (off)' : ''))") or []
    check(foot == ["Back", "Skip", "Continue (off)"], f"Skip is the only other way on ({foot})")


def state():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def memory(name):
    """What the companion called name remembers: companions/<id>/memory.json."""
    mate = next((c for c in state().get("Preferences", {}).get("Companions", []) if c["Name"] == name), None)
    try:
        return json.loads((PROFILE / "companions" / mate["Id"] / "memory.json").read_text(encoding="utf-8")) if mate else []
    except (OSError, ValueError):
        return []


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def talk_text(process):
    return js(process, "document.querySelector('.ob-talk')?.innerText ?? ''") or ""


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    (BIN / "site.txt").write_text(SITE)
    (BIN / "seconds.txt").write_text("14")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    process = launch(EXE, PROFILE, {**os.environ, "STILL_QA_SEARCH": SITE + "/search?q="})
    try:
        setup(process)
        tour(process)
        again(process)
        interview(process)
        looks(process)
        replay(process)
        errors = rpc(process).get("shellErrors") or js(process, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
    shots()


def sounds(process):
    return js(process, "stillSounds.played.map(p => p.name)") or []


def key(process, name):
    js(process, f"(document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', {{ key: {json.dumps(name)}, bubbles: true }}))")


def companions(prefs=None):
    return [c["Name"] for c in (prefs or state().get("Preferences", {})).get("Companions") or []]


def to_crew(process):
    """hello -> import -> ai, picking the fake AI app -> the crew."""
    next_step(process)
    not_now(process)
    if not until(lambda: click_text(process, ".byo-main", "Fake agent"), 4):
        click(process, ".byo-more")  # agents you added sit under More agents
        until(lambda: click_text(process, ".byo-main", "Fake agent"), 6)
    ok = until(lambda: js(process, "!!document.querySelector('.byo-row[data-chosen] .byo-ok')"), 10)
    time.sleep(1)
    next_step(process)
    until(lambda: js(process, "document.querySelectorAll('.crew-card').length") >= 8, 4)
    return ok


def setup(process):
    if not MAC:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # window sizes in real pixels
    check(until(lambda: js(process, "!!document.querySelector('.welcome.ob .ob-next')"), 20), "A fresh profile opens on setup")
    check(js(process, "document.querySelector('.ob-dots')?.getAttribute('aria-valuemax')") == "11", "Setup has 11 steps")
    check(rpc(process).get("theme") == "System", "The theme follows the system until you pick one")
    check(js(process, "document.querySelector('.ob-theme [aria-checked=true]')?.getAttribute('aria-label')") == "System", "Setup's theme switch shows System")
    check(not companions(), "A fresh profile has no companions")
    check(until(lambda: js(process, "!!document.querySelector('.welcome.ob .intro.is-on')"), 6), "The intro plays first")
    reduced = js(process, "matchMedia('(prefers-reduced-motion: reduce)').matches")
    check(reduced or until(lambda: "intro" in sounds(process), 2), "Its sound plays with it")
    check(js(process, "!!document.querySelector('.intro-sound[aria-label=Mute]') && document.activeElement?.matches('.intro-skip')"), "It has a mute button, and Skip has the focus")
    time.sleep(1.5)
    key(process, " ")
    check(until(lambda: not js(process, "!!document.querySelector('.intro')"), 2), "Space skips it")
    check(until(lambda: "Hi! Welcome to Still." in talk_text(process), 3), "Then setup asks its first question")
    check(js(process, "localStorage.getItem('still.intro')") == "1", "The intro plays only once")
    time.sleep(1)
    recorder = record(process.pid, RUN / "setup.mp4")
    try:
        time.sleep(2.5)
        if js(process, "document.querySelector('.ob-sound')?.disabled"):
            check(js(process, "document.querySelector('.ob-sound')?.title").startswith("Off because"), "The sound switch says why it's off")
        else:
            click(process, ".ob-sound")
            check(until(lambda: js(process, "document.querySelector('.ob-sound')?.getAttribute('aria-pressed')") == "true", 2) and until(lambda: state().get("Preferences", {}).get("Sounds") is False, 5),
                  "The sound switch mutes setup, and Still remembers it")
            heard = len(sounds(process))
            next_step(process)  # hello -> import
            check(len(sounds(process)) == heard, "Muted, nothing plays")
            click(process, ".ob-sound")
            check(until(lambda: js(process, "document.querySelector('.ob-sound')?.getAttribute('aria-pressed')") == "false", 2) and until(lambda: state().get("Preferences", {}).get("Sounds") is True, 5),
                  "And it turns them back on")
            click(process, ".ob-foot button")  # back to hello
            until(lambda: step_now(process) == 1, 3)
            time.sleep(1)
        next_step(process)  # hello -> import
        check(js(process, "document.querySelectorAll('.ob-option').length") == 2, "Step 2 offers to bring your stuff over and to open your links in Still")
        foot = js(process, "[...document.querySelectorAll('.ob-foot button')].map(b => b.innerText.trim() + (b.disabled ? ' (off)' : ''))") or []
        check(foot == ["Back", "Not now", "Continue (off)"], f"Continue waits for a choice, and a single Not now link moves on ({foot})")
        not_now(process)  # -> ai
        if not until(lambda: click_text(process, ".byo-main", "Fake agent"), 4):
            click(process, ".byo-more")  # agents you added sit under More agents
            until(lambda: click_text(process, ".byo-main", "Fake agent"), 6)
        check(until(lambda: js(process, "!!document.querySelector('.byo-row[data-chosen] .byo-ok')"), 10), "Step 3: picking an AI app that's signed in")
        time.sleep(1)
        next_step(process)  # -> crew
        until(lambda: js(process, "document.querySelectorAll('.crew-card').length") == 8, 4)
        rpc(process, "capture", name="pick-none.png")
        crew = js(process, "[...document.querySelectorAll('.crew-card .role-title')].map(h => h.innerText.trim())") or []
        check(crew == ["Zest", "Bloom", "Noon", "Fizz", "Mallow", "Rivet", "Glint", "Make your own"], f"Step 4: seven roles to hire, then Make your own ({', '.join(crew)})")
        check(js(process, """[...document.querySelectorAll('.crew-card')].every(c => c.querySelector('.role-tag')?.innerText && c.querySelector('.role-expect h4')?.innerText === 'What to expect'
              && c.querySelectorAll('.role-expect li').length === 3 && ['Hire', 'Make'].includes(c.querySelector('.crew-pick')?.innerText.trim()))"""),
              "Each card has its role, three things to expect and Hire, like the library's")
        check(not js(process, "/\\bI'll\\b|\\bI will\\b/.test([...document.querySelectorAll('.crew-card')].map(c => c.innerText).join(' '))"), "No card makes a first-person promise")
        check(js(process, "document.querySelector('.crew-card .role-bubble')?.textContent") == "Give me your toughest lead. I like a challenge."
              and js(process, "document.querySelector('.crew-card.is-own .role-expect li')?.innerText") == "Any job you describe, in your words", "Each one has its own line for when you hover it, and Make your own lists what you get")
        check("Geist" in (js(process, "getComputedStyle(document.querySelector('.crew-card .role-title')).fontFamily") or "") and "Geist" in (js(process, "getComputedStyle(document.querySelector('.ob-name') ?? document.body).fontFamily") or ""),
              "Setup uses the same UI typeface, no serif")
        check(js(process, "document.querySelector('.ob-next').disabled && !document.querySelector('.crew-card.is-picked')") and not js(process, "!!document.querySelector('.ob-not-now')") and not click_text(process, ".ob-foot button", "Skip"),
              "Nothing is picked, and Continue waits for a pick; this step can't be skipped")
        click(process, ".ob-skip-all")
        check(until(lambda: "Hire at least one companion first" in talk_text(process), 3) and js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')"), "Skip setup asks for a companion first")
        time.sleep(.8)
        click(process, ".crew-pick[aria-label='Hire Glint']")
        check(until(lambda: js(process, "!document.querySelector('.ob-next').disabled && document.querySelector('.crew-card.is-picked .role-title')?.innerText.trim() == 'Glint'"), 3)
              and js(process, "document.querySelector('.crew-card.is-picked .crew-pick')?.innerText.trim()") == "Hired", "Hiring Glint turns its button into Hired and lets you continue")
        time.sleep(1)
        click_text(process, ".crew-card.is-own button", "Make your own")
        check(until(lambda: js(process, "!!document.querySelector('.ob-colors')"), 3) and js(process, "document.querySelectorAll('.ob-faces button').length") == 0, "Your own starts as a plain shape, before a color")
        click(process, ".ob-colors button[aria-label=Sky]")
        check(until(lambda: js(process, "document.querySelectorAll('.ob-faces button').length") == 8, 3), "Picking a color brings up shapes")
        time.sleep(1.2)
        click(process, ".ob-faces button[aria-label='Tall']")
        until(lambda: js(process, "!!document.querySelector('.ob-name-box input')"), 3)
        time.sleep(1.2)
        check(js(process, "document.querySelector('.ob-next').disabled && !document.querySelector('.ob-chips')"), "Your own needs a name you type: Still doesn't hand one out")
        type_into(process, ".ob-name-box input", "Miso")
        time.sleep(1.4)
        check(until(lambda: js(process, "!!document.querySelector('.ob-name-box textarea')"), 3), "Then it asks what it's there to do")
        type_into(process, ".ob-name-box textarea", "Plans my trips and keeps receipts in order.")
        time.sleep(.6)
        check(js(process, "document.querySelector('.ob-next')?.innerText.trim()") == "Add Miso", "Making your own ends with Add Miso")
        click(process, ".ob-next")
        both = until(lambda: js(process, "[...document.querySelectorAll('.crew-card.is-picked .role-title')].map(h => h.innerText.trim()).join()") == "Glint,Miso", 3)
        check(both and js(process, "document.querySelector('.ob-dots')?.getAttribute('aria-valuemax')") == "12", "Miso joins the crew, picked with Glint, and setup adds a step to pick the main one")
        time.sleep(1.2)
        next_step(process)  # -> main
        mains = js(process, "[...document.querySelectorAll('.ob-mains [role=radio] strong')].map(s => s.innerText.trim())") or []
        check(mains == ["Glint", "Miso"] and js(process, "document.querySelector('.ob-next').disabled"), f"Then you pick who leads ({mains})")
        click_text(process, ".ob-mains [role=radio]", "Miso")
        time.sleep(1)
        next_step(process)  # -> tools
        tools(process)
        not_now(process)  # Skip -> how
        check(until(lambda: companions() == ["Miso", "Glint"], 5), f"Both are added, Miso first as the main one ({companions()})")
        mate = until(lambda: next((c for c in state().get("Preferences", {}).get("Companions", []) if c["Name"] == "Miso"), None), 5)
        look = json.loads(mate["Look"]) if mate and mate.get("Look") else {}
        check(look.get("color") == "#8cc3ee" and look.get("shape") == "tall" and mate.get("Job") == "Plans my trips and keeps receipts in order.", "Step 4 saves your companion's name, color, shape and job")
        options = js(process, "[...document.querySelectorAll('.ob-option')].map(b => b.innerText)") or []
        check(len(options) == 2 and "Set it up with Miso" in options[0] and "Uses a little of your" in options[0] and "Uses no AI at all" in options[1], "Step 5: set up with Miso (with what it uses) or Quick setup")
        time.sleep(1)
        click_text(process, ".ob-option", "Quick setup")
        until(lambda: js(process, "!!document.querySelector(\".ob-name-box input[aria-label='Your name']\")"), 4)
        time.sleep(1.4)
        type_into(process, ".ob-name-box input[aria-label='Your name']", "Sam")
        time.sleep(1)
        next_step(process)  # -> interests
        check("Thanks, Sam" in (js(process, "document.querySelector('.ob-talk')?.innerText ?? ''") or ""), "Step 6 greets you by name")
        for k in ("Research", "Sales", "Hiring"):
            click_text(process, ".ob-chips.is-big button", k)
            time.sleep(.35)
        time.sleep(.8)
        next_step(process)  # -> layout
        facts = until(lambda: [f["Text"] for f in memory("Miso")] if len(memory("Miso")) >= 2 else None, 5) or []
        check("Likes to be called Sam." in facts and "Works on research, sales, hiring." in facts, f"Your name and interests are Miso's first memories ({facts})")
        theirs = [f["Text"] for f in memory("Glint")]
        check("Likes to be called Sam." in theirs and "Works on research, sales, hiring." in theirs, f"Glint remembers them too ({theirs})")
        glint = next((c for c in state().get("Preferences", {}).get("Companions", []) if c["Name"] == "Glint"), {})
        check(glint.get("Crew") == "researcher" and not glint.get("AskName"), "A companion hired for a role remembers which one it is")
        check(js(process, "document.querySelector('.ob-layouts [aria-checked=true]')?.innerText ?? ''").startswith("Classic"), "Step 7: Classic tabs are the default")
        time.sleep(.8)
        next_step(process)  # -> charge
        check(js(process, "!!document.querySelector('.ob-ask')"), "Step 8 shows a sample permission card")
        time.sleep(1.2)
        click_text(process, ".ob-ask button", "Allow once")
        check(until(lambda: "only go ahead when you say so" in (js(process, "document.querySelector('.ob-ask')?.innerText ?? ''") or ""), 3), "Answering it explains what happened")
        time.sleep(1.4)
        next_step(process)  # -> start
        check(js(process, "document.querySelector('.ob-next').disabled && document.querySelector('.ob-not-now')?.innerText.trim() == 'Not now'"), "The first task waits for a pick, with Not now to finish without one")
        tasks = js(process, "[...document.querySelectorAll('.ob-tasks button')].map(b => b.innerText.trim())") or []
        check(tasks[:1] == ["Brief me on a topic"], "Step 9 suggests first tasks that match your work")
        click(process, ".ob-tasks button")
        time.sleep(1)
        check(js(process, "document.querySelector('.ob-next')?.innerText.trim() == \"Let's go\" && !document.querySelector('.ob-next').disabled && !document.querySelector('.ob-not-now')"), "Picking one turns on Let's go, and Not now goes")
        check(rpc(process).get("aiCalls") == 0, "Quick setup ran no AI at all")
        click(process, ".ob-next")
        check(until(lambda: not js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')"), 5), "Setup closes")
        played = sorted(set(sounds(process)))
        check(set(played) <= {"intro", "jingle"}, "Setup plays only the intro and the end jingle: no step, click or pick sounds" + ("" if set(played) <= {"intro", "jingle"} else f" ({played})"))
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
    video = RUN / ("setup.mov" if MAC else "setup.mp4")
    size = video.stat().st_size if video.exists() else 0
    check(size > 200_000, f"The recording is saved ({size // 1024} KB)")


def new_tab(process):
    """A new tab opens with the address bar's suggestions; the tour waits until they close, as a person would close them."""
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.address-bar.is-editing')"), 10)
    for _ in range(3):  # a busy computer can miss the first one
        js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        if until(lambda: not js(process, "!!document.querySelector('.address-bar.is-editing')"), 3):
            break


RING = """(() => {
 const ring = document.querySelector('.tour-ring'), el = ring && document.querySelector(ring.dataset.target)
 if (!el) return 0
 const a = ring.getBoundingClientRect(), b = el.getBoundingClientRect(), clip = el.closest('.home-main')?.getBoundingClientRect()
 const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
 const seen = b.top >= -1 && b.left >= -1 && b.bottom <= innerHeight + 1 && b.right <= innerWidth + 1 && (!clip || b.top >= clip.top - 1 && b.bottom <= clip.bottom + 1)
 return seen && w > 0 && h > 0 ? w * h / (b.width * b.height) : 0
})()"""


def ringed(process):
    """True when the coach mark's ring holds its target, on screen; else what it rings and how much of it."""
    if until(lambda: (js(process, RING) or 0) > .95, 3):
        return True
    return f"{js(process, 'document.querySelector(`.tour-ring`)?.dataset.target')}: {js(process, RING)}"


def walk_tour(process, moves, on_card=lambda seen, card: None):
    """Walks the tour to the end, checking each ring is on its target, and again after each move on step 2.
    Returns the steps' titles and the rings that were off."""
    seen, off = [], []
    for _ in range(8):
        card = js(process, "document.querySelector('.tour-card')?.innerText ?? ''") or ""
        if not card:
            break
        seen.append(card.split("\n")[1] if "\n" in card else card)
        on_card(seen, card)
        off.append(ringed(process))
        if len(seen) == 2:
            for move in moves:
                move()
                time.sleep(.8)
                off.append(ringed(process))
        click_text(process, ".tour-card button", "Next") or click_text(process, ".tour-card button", "Done")
        time.sleep(.6)
    return seen, [r for r in off if r is not True]


def tour(process):
    new_tab(process)
    check(until(lambda: js(process, "!!document.querySelector('.tour-card')"), 10), "Back on the new tab page, the tour starts")

    def on_card(seen, card):
        if len(seen) == 1:
            check("Miso works in background tabs" in card, "Its first card names your companion")
            rpc(process, "capture", name="tour.png")
        if len(seen) == 2:
            check([line for line in card.split("\n") if line][1:3] == ["Your companions", "Switch companions or make a new one. Each has its own look, job and memory."], f"Its second card says companions ({card})")
    chat = lambda: send(process, "aiToggle")
    seen, off = walk_tour(process, [chat, chat], on_card)
    check(len(seen) == 5 and not js(process, "!!document.querySelector('.tour')"), f"Five coach marks, then it's done ({', '.join(seen)})")
    check(not off, f"Classic: every ring sits on its target, with the side chat open and closed ({off})")
    check(js(process, "localStorage.getItem('still.tour')") is None, "It doesn't come back")


def again(process):
    send(process, "welcomeAgain")
    check(until(lambda: "I'm Miso. I'll get you set up." in talk_text(process), 10), "Run setup again opens setup with your companion")
    calls, started = rpc(process).get("aiCalls"), len(chats())
    time.sleep(3)
    next_step(process, .8)  # hello -> import
    not_now(process, .8)  # -> ai
    next_step(process, .8)  # -> crew
    check(click_text(process, ".ob-keep", "Keep Miso"), "It offers to keep Miso")
    until(lambda: js(process, "!!document.querySelector('.plug-belt')"), 4)
    not_now(process, .8)  # Skip connecting apps -> how
    until(lambda: "How do you want to set things up?" in talk_text(process), 4)
    time.sleep(1.2)
    click_text(process, ".ob-option", "Quick setup")
    time.sleep(1.2)
    while step_now(process) < 11 and not js(process, "!!document.querySelector('.ob-tasks')"):
        at = step_now(process)
        click_text(process, ".ob-foot button", "Not now") or click(process, ".ob-next")  # skipping what can be skipped
        if not until(lambda: step_now(process) == at + 1, 4):
            break
        time.sleep(.6)
    type_into(process, ".ob-name-box textarea", "Nothing right now")
    time.sleep(.3)
    check(js(process, "document.querySelector('.ob-next')?.innerText.trim()") == "Finish", "Saying no to a first task keeps it Finish")
    click(process, ".ob-next")
    check(until(lambda: not js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')"), 5), "Setup closes")
    time.sleep(2)
    check(rpc(process).get("aiCalls") == calls and len(chats()) == started, "\"Nothing right now\" starts no task and runs no AI")
    send(process, "welcomeAgain")
    until(lambda: "I'm Miso. I'll get you set up." in talk_text(process), 10)
    click(process, ".ob-skip-all")
    check(until(lambda: not js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')"), 5) and until(lambda: state().get("Welcome") is False, 5), "Skip setup closes it")
    new_tab(process)
    check(until(lambda: js(process, "!!document.querySelector('.tour-card')"), 10), "The tour offers itself again")
    click_text(process, ".tour-card button", "Skip tour")
    check(until(lambda: not js(process, "!!document.querySelector('.tour')"), 3) and js(process, "localStorage.getItem('still.tour')") is None, "Skip tour ends it")
    # Modern, from the start: the rings stay on their targets, also when the layout switches mid-tour.
    send(process, "preference", key="tabLayout", value="Modern")
    js(process, "localStorage.setItem('still.tour', '1'); location.reload()")
    until(lambda: js(process, "!!document.querySelector('.tour-card')"), 15)
    rpc(process, "capture", name="tour-modern.png")
    layout = lambda value: lambda: send(process, "preference", key="tabLayout", value=value)
    seen, off = walk_tour(process, [layout("Classic"), layout("Modern")])
    check(len(seen) >= 4 and not off, f"Modern: every ring sits on its target, also after switching layouts mid-tour ({', '.join(seen)}; {off})")
    send(process, "preference", key="tabLayout", value="Classic")


def interview(process):
    """Set me up with Miso: the fake AI app follows up on each answer; a question can be skipped and "that's enough" ends it.
    Then what it set up: a companion from the library with its instructions, memory and a routine (off), what Miso focuses
    on and remembers, settings and a first task, each with an undo, and the wording ones editable. Recorded as interview.mp4."""
    calls = rpc(process).get("aiCalls")
    recorder = record(process.pid, RUN / "interview.mp4")
    sent = lambda: [json.loads(l)["prompt"] for l in (BIN / "prompts.jsonl").read_text(encoding="utf-8").splitlines()]
    talked = len(sent())
    try:
        send(process, "welcomeAgain", talk=True)
        check(until(lambda: "What do you work on these days?" in talk_text(process), 20), "Set me up again opens straight into Miso's questions")
        first = sent()[talked]
        check("- scout: Bloom, Scout, Hiring" in first and "- researcher:" not in first and "Glint, Researcher" in first,
              "It knows Still's companions, and which ones are already on the team")
        options = js(process, "[...document.querySelectorAll('.ob-interview .ob-chips button')].map(b => b.innerText.trim())") or []
        check(options == ["I run a small bakery", "Research", "Sales"], f"Its question comes with answers to tap ({options})")
        time.sleep(1.2)
        click_text(process, ".ob-interview .ob-chips button", "I run a small bakery")
        check(until(lambda: "who buys from you" in talk_text(process), 20) and sent()[-1].strip() == "I run a small bakery", "It follows up on the answer instead of moving down a list")
        time.sleep(1)
        type_into(process, ".ob-interview .ob-say input", "Mostly cafes, wholesale. Walk-ins on Saturdays.")
        time.sleep(.8)
        js(process, "document.querySelector('.ob-interview .ob-say')?.requestSubmit()")
        check(until(lambda: "big goal" in talk_text(process), 20), "Typed answers work too")
        rpc(process, "capture", name="interview.png")
        time.sleep(1)
        click_text(process, ".ob-interview-foot button", "Skip this one")
        check(until(lambda: "Which apps and sites" in talk_text(process), 20) and sent()[-1].strip() == "(skip)" and "Skipped" in talk_text(process),
              "Any question can be skipped, and it moves on")
        time.sleep(1)
        click_text(process, ".ob-interview .ob-chips button", "Shopify")
        check(until(lambda: "How do you like my answers?" in talk_text(process), 20), "Then the next topic")
        time.sleep(1)
        click_text(process, ".ob-interview-foot button", "That's enough")
        check(until(lambda: js(process, "document.querySelectorAll('.ob-summary li').length") >= 10, 20), "\"That's enough\" ends it, and it sets Still up from what it heard")
        rows = js(process, "[...document.querySelectorAll('.ob-summary section')].map(s => s.querySelector('h4').textContent.trim() + ': ' + [...s.querySelectorAll('li b')].map(b => b.innerText.trim()).join(' | '))") or []
        check(rows == ["Your team: New on your team | Your team will remember | What I'll focus on | I'll also remember | What Bloom will focus on | Bloom will also remember | Bloom's routine, off for now",
                       "Your Still: Theme | Pinned | When I work in tabs | How I talk | Ideas about", "First up: First, I'll help with"], f"The summary groups what it set up ({rows})")
        told = (js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('Your team will remember'))?.querySelector('small')?.innerText") or "").split("\n")
        check(len(told) >= 2 and all(t[:1].isupper() and t.endswith(".") and t.count(". ") == 0 for t in told), f"Each memory is its own short sentence, on its own line ({told})")
        time.sleep(1.5)
        rpc(process, "capture", name="interview-summary.png")
        prefs = until(lambda: (p := state().get("Preferences", {})).get("Interests") == ["Baking", "Wholesale"] and "Bloom" in companions(p) and p, 5) or {}  # saved a moment later
        check(rpc(process).get("theme") == "Dark" and prefs, "The theme and interests it picked apply")
        check(any(t["Pinned"] and t["Url"].endswith("/recipes/pasta") for t in rpc(process)["tabs"]), "Its pinned site is pinned")
        check(sorted(companions(prefs)) == ["Bloom", "Glint", "Miso"], f"It hired Bloom from the library, and not Glint twice ({companions(prefs)})")
        mate = next((c for c in prefs.get("Companions", []) if c["Name"] == "Miso"), {})
        bloom = next((c for c in prefs.get("Companions", []) if c["Name"] == "Bloom"), {})
        check(mate.get("Job", "").endswith("For me: Keep my wholesale orders on track and tell me when a cafe is late to pay.") and bloom.get("Job", "").endswith("For me: Find me a second baker who can start at 5am."),
              "Each companion's instructions get a paragraph about the user")
        check(bloom.get("Crew") == "scout" and len(bloom.get("Routines", [])) == 2 and not any(r["On"] for r in bloom["Routines"])
              and any(r["Time"] == "08:30" and r["Days"] == [1, 2, 3, 4, 5] for r in bloom["Routines"]), f"Bloom's routines, its own and the new one, start off ({bloom.get('Routines')})")
        facts, glint, bloom_facts = [f["Text"] for f in memory("Miso")], [f["Text"] for f in memory("Glint")], [f["Text"] for f in memory("Bloom")]
        check(mate.get("Tone") == "Keep it short and cheerful." and "Runs a small bakery that sells to cafes." in facts and "Uses Gmail and Shopify all day." in facts and "Has two cats." in facts
              and "Likes to be called Sammy." in facts and "Likes to be called Sam." not in facts and "Bakes sourdough for six cafes." in facts, f"Miso's tone and memories are set, and the new name replaces the old ({facts})")
        check("Has two cats." in glint and "Bakes sourdough for six cafes." not in glint and "Has two cats." in bloom_facts and "Hiring a second baker for early shifts." in bloom_facts,
              f"The whole team learns about the user, and each one what's just for it ({glint}, {bloom_facts})")

        def edit(label, text):
            js(process, f"[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith({json.dumps(label)}))?.querySelector('button')?.click()")
            until(lambda: js(process, "!!document.querySelector('.ob-edit textarea')"), 3)
            time.sleep(.6)
            type_into(process, ".ob-edit textarea", text)
            time.sleep(.6)
            js(process, "document.querySelector('.ob-edit')?.requestSubmit()")
        edit("How I talk", "Short answers, no small talk.")
        check(until(lambda: next((c for c in state().get("Preferences", {}).get("Companions", []) if c["Name"] == "Miso"), {}).get("Tone") == "Short answers, no small talk.", 5)
              and "Short answers, no small talk." in (js(process, "document.querySelector('.ob-summary')?.innerText") or ""), "Its wording can be edited right in the summary")
        edit("I'll also remember", "Bakes sourdough and rye for six cafes.\nDelivers before 7am.")
        check(until(lambda: "Delivers before 7am." in [f["Text"] for f in memory("Miso")] and "Bakes sourdough for six cafes." not in [f["Text"] for f in memory("Miso")], 5),
              "An edited memory replaces what it kept")
        js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('Theme'))?.querySelector('button')?.click()")
        check(until(lambda: rpc(process).get("theme") == "System" and "Undone" in (js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('Theme'))?.innerText") or ""), 5),
              "Undo puts the theme back")
        bloom_dir = PROFILE / "companions" / bloom.get("Id", "-")
        js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('New on your team'))?.querySelector('button')?.click()")
        check(until(lambda: "Bloom" not in companions() and not bloom_dir.exists(), 5) and until(lambda: js(process, "[...document.querySelectorAll('.ob-summary li')].filter(l => /Bloom/.test(l.innerText) && l.classList.contains('is-undone')).length") == 4, 3),
              "Undoing a hire lets that companion go, with everything setup gave it")
        js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('First,'))?.querySelectorAll('button')[1]?.click()")  # no first task: the next suite wants no chat running
        time.sleep(2)
        check(rpc(process).get("aiCalls") - calls == 6, f"Each message is one small AI run ({rpc(process).get('aiCalls') - calls})")
        click(process, ".ob-next")
        check(until(lambda: not js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')"), 5), "Done closes setup")
    finally:
        stop(recorder)


CREW = [("Juniper", "#a6cf98", {"shape": "kitty", "eyes": "iris", "pupil": .3, "brows": "thin", "mouth": "cat", "hat": "beret"}),
        ("Pebble", "#c9c6c0", {"shape": "pebble", "eyes": "button", "mouth": "smile", "hair": "curls", "hairColor": "#3b2f2a"}),
        ("Clementine", "#f0a989", {"shape": "fox", "eyes": "almond", "brows": "straight", "mouth": "smirk", "hat": "headphones"}),
        ("Bao", "#f2ede4", {"shape": "mochi", "eyes": "happy", "mouth": "open", "hair": "sprout", "hairColor": "#9ccf9a"}),
        ("Indigo", "#7aa3dc", {"shape": "drop", "eyes": "shine", "brows": "soft", "mouth": "grin", "hat": "beanie"})]
BASE = {"shape": "round", "head": 1, "ears": 0, "eyes": "dot", "eyeGap": 0, "eyeY": 0, "eyeSize": 0, "pupil": 0, "brows": "none", "browGap": 0, "browY": 0,
        "browSize": 0, "browTilt": 0, "mouth": "smile", "mouthY": 0, "mouthSize": 0, "blush": True, "hair": "", "hairColor": "#6b4a35", "hat": ""}


def looks(process):
    """Deleting companions, then the look editor, open for six companions."""
    new_tab(process)
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 10)
    click(process, ".home-rail-item[aria-label=Companions]")
    until(lambda: js(process, "document.querySelectorAll('.mate-card').length") == 2, 10)
    for name in ("Glint", "Miso"):
        click(process, f".mate-portrait[aria-label='Edit {name}']")
        until(lambda: js(process, "!!document.querySelector('.profile-panel')"), 5)
        js(process, "document.querySelector('.profile-head [aria-label=More]')?.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' }))")
        until(lambda: js(process, "!!document.querySelector('[role=menuitem][data-variant=destructive]')"), 3)
        click(process, "[role=menuitem][data-variant=destructive]")
        until(lambda: js(process, "!!document.querySelector('[data-slot=alert-dialog-content]')"), 3)
        if name == "Glint":
            click(process, "[data-slot=alert-dialog-action]")
            check(until(lambda: companions() == ["Miso"], 5), "Deleting Glint works while Miso is there")
            until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 3)
            continue
        note = js(process, "document.querySelector('[data-slot=alert-dialog-content]')?.innerText") or ""
        time.sleep(1)
        check("Still needs at least one" in note and companions() == ["Miso"], f"Miso, the last one, can't be deleted ({note})")
        rpc(process, "capture", name="last-one.png")
        click(process, "[data-slot=alert-dialog-cancel]")
        until(lambda: not js(process, "!!document.querySelector('[data-slot=alert-dialog-content]')"), 3)
        js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 3)
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
        until(lambda: js(process, "!!document.querySelector('.profile-panel')"), 5)
        click_text(process, ".profile-stage-actions button", "Edit look")
        if until(lambda: js(process, "!!document.querySelector('.look-dialog canvas, .look-dialog .look-stage img')"), 8):
            time.sleep(1.8)  # the model loads and settles
            rpc(process, "capture", name=f"look-{name.lower()}.png")
            shutil.copy(PROFILE / f"look-{name.lower()}.png", LOOKS / f"look-{name.lower()}.png")
            shot += 1
        click_text(process, ".look-dialog .look-foot button", "Cancel")
        until(lambda: not js(process, "!!document.querySelector('.look-dialog')"), 3)
        js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        if not until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 2):
            click(process, ".profile-head [aria-label=Close]")
            until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 3)
    check(shot == 6, f"The look editor opens for all six ({shot} screenshots)")


def replay(process):
    send(process, "openPanel", name="about")
    check(until(lambda: click_text(process, ".about-content button", "Replay the intro"), 5), "About can replay the intro")
    check(until(lambda: js(process, "!!document.querySelector('.intro-replay .intro.is-on')"), 6), "It plays over the browser")
    time.sleep(2)
    rpc(process, "capture", name="replay.png")
    key(process, " ")
    check(until(lambda: not js(process, "!!document.querySelector('.intro-replay')"), 3), "Space skips it there too")


def shots():
    """A second fresh profile: the intro plays out on its own, then the crew with 0, 1 and 3 picked and the main pick, light and dark."""
    profile, out = RUN / "profile2", RUN / "shots"
    (profile / "agents").mkdir(parents=True)
    out.mkdir()
    shutil.copy(PROFILE / "agents" / "fake.json", profile / "agents" / "fake.json")
    process = launch(EXE, profile)
    try:
        until(lambda: js(process, "!!document.querySelector('.welcome.ob .intro.is-on')"), 8)
        time.sleep(4)
        rpc(process, "capture", name="intro-mark.png")  # Still's name below the companion
        check(until(lambda: not js(process, "!!document.querySelector('.intro')"), 8) and until(lambda: "Hi! Welcome to Still." in talk_text(process), 3), "Left alone, the intro ends and setup begins")
        to_crew(process)

        def shoot(name):
            for theme in ("Light", "Dark"):
                click(process, f".ob-theme [aria-label={theme}]")
                time.sleep(1.4)
                rpc(process, "capture", name=f"{name}-{theme.lower()}.png")
                shutil.copy(profile / f"{name}-{theme.lower()}.png", out / f"{name}-{theme.lower()}.png")
        time.sleep(1.5)
        shoot("pick-0")
        click(process, ".crew-pick[aria-label='Hire Glint']")
        shoot("pick-1")
        for name in ("Zest", "Fizz"):
            click(process, f".crew-pick[aria-label='Hire {name}']")
            time.sleep(.3)
        shoot("pick-3")
        next_step(process)
        click_text(process, ".ob-mains [role=radio]", "Zest")
        shoot("pick-main")
        next_step(process)  # -> tools
        shoot("tools")
        shutil.copy(profile / "intro-mark.png", out / "intro-mark.png")
        check(len(list(out.glob("pick-*.png"))) == 8 and len(list(out.glob("tools-*.png"))) == 2, "Screenshots of the roles with 0, 1 and 3 hired, the lead pick and Connect your tools, light and dark")
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
