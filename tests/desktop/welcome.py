"""Setup on a fresh profile in four steps, the tour, Run setup again, "Set me up again", and the look editor.

A fresh profile starts with the intro (skipped with Space) and no companions. Then four steps, walked like a person
would: Welcome (the headline, Create your companion and Just browse for now); Connect (an AI app on this computer: two
made-up apps show Sign in, which waits for a click, and Install and sign in with no installer, then the fake one is
ready; How this works);
Create (a name, a starting look, Surprise me, Customize, what to help with and a reply length, then the instructions to
check before Hire, and the joined card); and a first task, the sample page that ships with Still. The task runs on a
fake AI app (a manifest in Still's agents folder): it opens the sample page beside the chat and reads it. The run is
recorded, frames taken from the window itself. Then Run setup again (Just browse leaves everything as it was) and Set
me up again: the fake app asks a few questions and sets things up; the companions it suggests join only on Hire.

A second fresh profile lets the intro play out: Just browse for now leaves a browser with no companion, and the new tab
page offers Create your companion and Get started. A third one is closed at every step and opened again, once with a
hard kill right after Hire: the same step and answers, never a second companion. Screenshots of each step, light and
dark, and the preview the last step shows with no AI connected.

Run: python tests/desktop/welcome.py artifacts/Still-QA/Still.exe
Out: docs/agentic/mascot/look-*.png (the look editor for 6 companions), artifacts/welcome-*/setup.mp4 (the recording),
     artifacts/welcome-*/shots/*.png
"""
import atexit
import ctypes
import ctypes.wintypes
import http.server
import json
import os
from pathlib import Path
import re
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
from qa import MAC, ROOT, companions_page, js, launch, launcher, rpc, send, until  # noqa: E402

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
    if args[:1] == ["whoami"]: print("signed out"); sys.exit(0)  # the made-up app that isn't signed in
    if args[:1] == ["login"]:  # its sign-in, which fails and says why, the way real apps do
        open(os.path.join(here, "logins.txt"), "a").write("login\n")
        print("Starting local login server on http://localhost:1455.", flush=True)
        print("Error logging in: Port 127.0.0.1:1455 is already in use", file=sys.stderr); sys.exit(1)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt}) + "\n")
    site = open(os.path.join(here, "site.txt")).read().strip()
    def say(e): print(json.dumps(e), flush=True)
    def reply(text): say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    # Create's chat (make.md): plain questions one at a time, then the new companion's own wording. The first answer is
    # what it helps with; "Short" anywhere makes the replies short.
    making = os.path.join(here, "make.json")
    if "a new companion the user is making" in prompt or os.path.exists(making):
        say({"type": "system", "subtype": "init", "session_id": "make-1"})
        questions = [("What would you like my help with?", ["Plan my week", "Keep my inbox tidy"]),
                     ("What takes up too much of your time?", ["Email", "Planning"]), ("How do you like my answers?", ["Short", "Detailed"])]
        if "a new companion the user is making" in prompt:
            json.dump({"answers": [], "asked": 1}, open(making, "w"))
            reply(json.dumps({"say": "Hi! Let's get started.", "question": questions[0][0], "options": questions[0][1]}))
            sys.exit(0)
        talk = json.load(open(making))
        answer = prompt.strip()
        if not answer.startswith("That's enough"):
            if answer != "(skip)": talk["answers"].append(answer)
            if talk["asked"] < len(questions):
                q = questions[talk["asked"]]
                talk["asked"] += 1
                json.dump(talk, open(making, "w"))
                reply(json.dumps({"say": "No problem." if answer == "(skip)" else "Got it.", "question": q[0], "options": q[1]}))
                sys.exit(0)
        os.remove(making)
        said = talk["answers"]
        reply(json.dumps({"say": "Thanks, that's all I need.", "done": True, "companion": {"help": said[0] if said else "",
            "instructions": ["Start with what matters most today.", "Point out anything that looks late or forgotten."],
            "summary": ["Sort out what matters most each day", "Point out anything that's late"],
            "length": "short" if any("short" in a.lower() for a in said) else ""}}))
        sys.exit(0)
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
            "hire": ["growth", "research", "assistant", "nobody"],  # assistant: Ruth isn't in setup's library, so she's never hired
            "companions": [{"id": talk["lead"], "instructions": "Keep my wholesale orders on track and tell me when a cafe is late to pay.", "memories": ["Bakes sourdough for six cafes."]},
                           {"id": "growth", "instructions": "Find me a second baker who can start at 5am.", "memories": ["Hiring a second baker for early shifts."]},
                           {"id": "nobody", "instructions": "Not on the team, so this goes nowhere."}],
            "routines": [{"id": "growth", "text": "Check new applicants for the baker job and pick the best three.", "time": "08:30", "days": [1, 2, 3, 4, 5]}],
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
        return r
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    end = lambda: time.time() + float(open(os.path.join(here, "seconds.txt")).read())
    if "https://sample.still.internal/compare.html" in prompt:  # setup's sample: open it, read it, compare
        reply("On it. I'll open the sample page and compare the three packs.")
        opened = not call("open_tab", url="https://sample.still.internal/compare.html").get("isError")
        page = call("read_page")
        json.dump({"opened": opened, "text": "".join(c.get("text", "") for c in page.get("content", []))}, open(os.path.join(here, "sample.json"), "w", encoding="utf-8"))
        stop = end()
        while time.time() < stop and not call("read_page", shown=False, text=False).get("isError"): time.sleep(.5)
        reply("**The Pinecrest Weekender 28 is the pick for a weekend.**\n\n| Pack | Price | Weight | Rating |\n|---|---|---|---|\n| Pinecrest Weekender 28 | $129 | 1.1 kg | 4.6 |\n| Tallow Daypack 22 | $74 | 0.6 kg | 4.2 |\n| Marlin Trek 32 | $159 | 1.4 kg | 4.4 |\n\nIt's a sample page, so there's nothing to buy.\n\n>> Compare two of them in more detail\n>> Make a packing list\n>> Save this as a CSV")
        still.stdin.close()
        sys.exit(0)
    reply("On it. I'll look for easy dinners and check the best one.")
    call("web_search", query="easy weeknight dinner recipes")
    call("open_tab", url=site + "/recipes/pasta")
    stop = end()
    while time.time() < stop and not call("read_page", shown=False, text=False).get("isError"): time.sleep(.5)
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
        atexit.register(lambda: recorder.poll() is None and recorder.send_signal(signal.SIGINT))  # a run that fails partway still stops it
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


def foot(process):
    return js(process, "[...document.querySelectorAll('.ob-foot button')].map(b => b.innerText.trim() + (b.disabled ? ' (off)' : ''))") or []


def setup_open(process):
    return js(process, "!!document.querySelector('.welcome.ob:not(.is-hidden)')")


SPLIT = []


def pick_ai(process, name):
    """Picks an AI app in Connect's list: the main four show, the rest (fake apps too) wait under More agents."""
    until(lambda: js(process, "!!document.querySelector('.welcome .byo-main')"), 6)
    if not SPLIT:
        SPLIT.append(js(process, "[...document.querySelectorAll('.welcome .byo-main strong')].map(e => e.childNodes[0]?.textContent.trim())") or [])
        main = SPLIT[0]
        check(all(n in main for n in ("Claude", "ChatGPT", "Grok", "Gemini")) and not any(n in main for n in ("OpenCode", "Qwen Code", "Fake agent"))
              and js(process, "!!document.querySelector('.welcome .byo-more')"), f"Connect shows Claude, ChatGPT, Grok and Gemini, the rest under More agents ({main})")
    js(process, "document.querySelector('.welcome .byo-more[aria-expanded=false]')?.click()")
    until(lambda: click_text(process, ".byo-main", name), 6)
    time.sleep(.6)


def card(process):
    return js(process, "document.querySelector('.ob-connect')?.innerText ?? ''") or ""


def to_create(process):
    """Welcome -> Connect, picking the fake AI app -> Create."""
    next_step(process)
    pick_ai(process, "Fake agent")
    ok = until(lambda: "Fake agent is ready" in card(process), 10)
    time.sleep(.6)
    next_step(process)
    return ok


def bubbles(process):
    """What the companion has said in Create's chat."""
    return js(process, "[...document.querySelectorAll('.ob-interview .ob-bubble:not(.is-you):not(.is-typing)')].map(b => b.innerText)") or []


def chat(process, text=None, button=None, wait=30):
    """Create's chat: one answer, typed or a button (selector, words), then the companion's next line."""
    before = len(bubbles(process))
    if text is None:
        click_text(process, *button)
    else:
        type_into(process, ".ob-interview .ob-say input", text)
        time.sleep(.3)
        click(process, ".ob-interview .ob-say button[type=submit]")
    return until(lambda: len(bubbles(process)) > before and not js(process, "!!document.querySelector('.ob-bubble.is-typing')") and bubbles(process)[-1], wait)


def made_lines(goal):
    """Create's chat for a fake app that plays lines from a plan (exchange.py): a question, one more, then its wording."""
    ask = lambda q: {"text": json.dumps({"say": "Got it.", "question": q, "options": []})}
    return [ask("What would you like my help with?"), ask("Anything else I should know?"),
            {"text": json.dumps({"say": "Thanks.", "done": True, "companion": {"help": goal, "instructions": ["Keep it short."], "summary": ["Help with what you asked"], "length": ""}})}]


def make(process, name, goal, wait=30):
    """Create: a name, then what to help with (told in the companion's chat with an AI app ready, typed without one),
    then Continue to what it will do."""
    until(lambda: js(process, "!!document.querySelector(\"input[aria-label='Name your companion']\")"), 5)
    type_into(process, "input[aria-label='Name your companion']", name)
    time.sleep(.4)
    if js(process, "!!document.querySelector(\"textarea[aria-label='What should they help with?']\")"):
        type_into(process, "textarea[aria-label='What should they help with?']", goal)
        time.sleep(.4)
        click(process, ".ob-next")
    else:
        click(process, ".ob-next")
        until(lambda: bubbles(process) and not js(process, "!!document.querySelector('.ob-bubble.is-typing')"), wait)
        chat(process, goal, wait=wait)
        click_text(process, ".ob-interview-foot button", "That's enough")
    return until(lambda: js(process, "!!document.querySelector(\"textarea[aria-label='Instructions']\")?.value"), wait)


def onboarding(process):
    return json.loads(js(process, "localStorage.getItem('still.onboarding') ?? '{}'") or "{}")


def words(process):
    """Everything the welcome says, closed disclosures included."""
    return js(process, "document.querySelector('.welcome.ob')?.textContent ?? ''") or ""


BANNED = re.compile(r"—|\b(calm|quiet|minimal|unlimited|free)\b", re.I)


def copy_ok(process, where, seen):
    found = BANNED.findall(words(process))
    seen.append((where, found))


def state(profile=PROFILE):
    for _ in range(50):  # Still swaps the file in atomically, so a read can land mid-swap
        try:
            return json.loads((profile / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.1)
    return {}


def mates(profile=PROFILE):
    return state(profile).get("Preferences", {}).get("Companions") or []


def mate(name, profile=PROFILE):
    return next((c for c in mates(profile) if c["Name"] == name), {})


def memory(name):
    """What the companion called name remembers: companions/<id>/memory.json."""
    m = mate(name)
    try:
        return json.loads((PROFILE / "companions" / m["Id"] / "memory.json").read_text(encoding="utf-8")) if m else []
    except (OSError, ValueError):
        return []


def chats(profile=PROFILE):
    try:
        return json.loads((profile / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def talk_text(process):
    return js(process, "document.querySelector('.ob-talk')?.innerText ?? ''") or ""


def manifests(profile):
    """The fake AI app, and two more that are never ready: one signed out, one not on this computer."""
    (profile / "agents").mkdir(parents=True, exist_ok=True)
    common = {"enabled": True, "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}
    (profile / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "command": str(BIN / "fakeagent"), "detect": ["status"], "expect": "signed in", **common}))
    (profile / "agents" / "out.json").write_text(json.dumps({"id": "out", "name": "Signed-out agent", "command": str(BIN / "fakeagent"), "detect": ["whoami"], "expect": "signed in",
        "signin": ["login"], **common}))
    (profile / "agents" / "gone.json").write_text(json.dumps({"id": "gone", "name": "Offline agent", "command": str(BIN / "no-such-agent"), "detect": ["status"], "expect": "signed in",
        "site": "https://offline-agent.example/get", "install": "pipx install offline-agent", **common}))


def main():
    BIN.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    (BIN / "site.txt").write_text(SITE)
    (BIN / "seconds.txt").write_text("8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    manifests(PROFILE)
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
    browse()
    resume()


def sounds(process):
    return js(process, "stillSounds.played.map(p => p.name)") or []


def key(process, name):
    js(process, f"(document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', {{ key: {json.dumps(name)}, bubbles: true }}))")


def companions(prefs=None):
    return [c["Name"] for c in (prefs or state().get("Preferences", {})).get("Companions") or []]


def setup(process):
    if not MAC:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # window sizes in real pixels
    check(until(lambda: js(process, "!!document.querySelector('.welcome.ob .ob-dots')"), 20), "A fresh profile opens on setup")
    check(js(process, "document.querySelector('.ob-dots')?.getAttribute('aria-valuemax')") == "4", "Setup has four steps")
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
    check(until(lambda: "A little less work. A little more still." in talk_text(process), 3), "Then the welcome, with its headline")
    check(js(process, "localStorage.getItem('still.intro')") == "1", "The intro plays only once")
    time.sleep(1)
    recorder = record(process.pid, RUN / "setup.mp4")
    copy = []
    try:
        time.sleep(2.5)
        said = talk_text(process)
        check("a companion that works in your tabs with you" in said and "It works with an AI app on your computer" in said, "It says what Still is, and that it works with an AI app on the computer")
        check(js(process, "document.querySelectorAll('.ob-companion .mascot').length") == 1, "One neutral companion")
        check(foot(process) == ["Just browse for now", "Create your companion"], f"Create your companion, and Just browse for now ({foot(process)})")
        copy_ok(process, "welcome", copy)
        if js(process, "document.querySelector('.ob-sound')?.disabled"):
            check(js(process, "document.querySelector('.ob-sound')?.title").startswith("Off because"), "The sound switch says why it's off")
        else:
            click(process, ".ob-sound")
            check(until(lambda: js(process, "document.querySelector('.ob-sound')?.getAttribute('aria-pressed')") == "true", 2) and until(lambda: state().get("Preferences", {}).get("Sounds") is False, 5),
                  "The sound switch mutes setup, and Still remembers it")
            heard = len(sounds(process))
            next_step(process)  # -> connect
            check(len(sounds(process)) == heard, "Muted, nothing plays")
            click(process, ".ob-sound")
            check(until(lambda: js(process, "document.querySelector('.ob-sound')?.getAttribute('aria-pressed')") == "false", 2) and until(lambda: state().get("Preferences", {}).get("Sounds") is True, 5),
                  "And it turns them back on")
            click_text(process, ".ob-foot button", "Back")
            until(lambda: step_now(process) == 1, 3)
            time.sleep(1)
        next_step(process)  # -> connect
        connect(process, copy)
        next_step(process)  # -> create
        create(process, copy)
        first(process, copy)
    finally:
        stop(recorder)
    tabs = rpc(process)["tabs"]
    check(sum(1 for t in tabs if not t["InChat"]) == 1 and any(t["InChat"] and t["Url"].startswith("https://sample.still.internal/compare.html") for t in tabs),
          f"The sample page opens beside the chat, out of the tab strip ({[t['Url'] for t in tabs]})")
    until(lambda: (BIN / "sample.json").exists(), 20)
    time.sleep(.5)
    try:
        seen = json.loads((BIN / "sample.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    text = seen.get("text", "")
    check(seen.get("opened") and all(p in text for p in ("Pinecrest Weekender 28", "Tallow Daypack 22", "Marlin Trek 32", "$129")) and "nothing here is for sale" in text,
          f"Miso reads the sample page: three made-up packs, labeled as a sample ({seen.get('opened')}, {text[:80]!r})")
    rows = js(process, "[...document.querySelectorAll('.chat-pane .ai-look')].map(r => r.innerText)") or []
    check(until(lambda: js(process, "document.querySelectorAll('.chat-pane .choice-card .ask-option').length") == 3, 30), f"It finishes with a choice card of three next steps ({rows})")
    miso = mate("Miso")
    theirs = [c for c in chats() if c.get("Companion") == miso.get("Id")]
    asked = [m["Text"] for c in theirs for m in c.get("Messages", []) if m["Role"] == "user"]
    check(len(theirs) == 1 and asked[:1] and asked[0].startswith("Open https://sample.still.internal/compare.html"),
          f"The task is the first message in Miso's own chat, and nothing else started ({len(theirs)} chats)")
    video = RUN / ("setup.mov" if MAC else "setup.mp4")
    size = video.stat().st_size if video.exists() else 0
    check(size > 200_000, f"The recording is saved ({size // 1024} KB)")
    bad = [(w, f) for w, f in copy if f]
    check(not bad, f"Every step's words pass the copy rules: no em dash, no calm, quiet or minimal, no unlimited or free ({bad})")


def connect(process, copy):
    """Step 2: three made-up AI apps, one in each state, then the one that's ready."""
    check(until(lambda: "which model should your companion think with" in talk_text(process), 4), "Step 2 asks which model to use")
    until(lambda: js(process, "!!document.querySelector('.ob-connect')"), 4)
    shell = "Terminal" if MAC else "PowerShell"
    buttons = lambda: js(process, "[...document.querySelectorAll('.ob-connect button')].map(b => b.innerText.trim())") or []
    pick_ai(process, "Offline agent")
    check(until(lambda: "Install and sign in" in card(process), 8) and "Offline agent isn't on this computer yet, and Still can't install it for you" in card(process)
          and f"offline-agent.example or run this in {shell}" in card(process) and "pipx install offline-agent" in card(process) and buttons() == ["Check again"],
          f"Not installed, with no installer: where to get it, the {shell} command, and Check again ({card(process)!r}, {buttons()})")
    seen = "(() => { const c = document.querySelector('.ob-connect')?.getBoundingClientRect(), t = document.querySelector('.ob-talk')?.getBoundingClientRect(); return !!c && !!t && c.bottom <= t.bottom + 2 })()"
    check(until(lambda: js(process, seen), 3), "Picking an app low in the list brings its card into view")
    check(foot(process)[-2:] == ["Set up later", "Continue (off)"], f"Continue waits for an app that's ready, and Set up later moves on ({foot(process)})")
    calls = rpc(process).get("aiCalls")
    click_text(process, ".ob-connect button", "Check again")
    time.sleep(1.5)
    check("Install and sign in" in card(process) and rpc(process).get("aiCalls") == calls, "Check again looks again and stays put")
    rpc(process, "capture", name="connect-missing.png")
    pick_ai(process, "Signed-out agent")
    check(until(lambda: card(process).startswith("Sign in"), 8) and "Signed-out agent is installed. Sign in once." in card(process) and buttons() == ["Sign in"],
          f"Installed but signed out: Sign in ({card(process)!r})")
    time.sleep(3)
    check(card(process).startswith("Sign in") and not (BIN / "logins.txt").exists(), f"Picking it doesn't start its sign-in ({card(process)!r})")
    check(foot(process)[-1] == "Continue (off)", "Continue still waits")
    click_text(process, ".ob-connect button", "Sign in")
    check(until(lambda: (BIN / "logins.txt").exists(), 8), "Sign in starts it")
    check(until(lambda: "didn't finish" in card(process), 10) and buttons() == ["Sign in", "Retry"],
          f"A sign-in that doesn't finish stays here, with Retry ({card(process)!r}, {buttons()})")
    check("didn't finish: Port 127.0.0.1:1455 is already in use. Try again." in card(process) and "Error logging in" not in card(process),
          f"...and says the app's own reason ({card(process)!r})")
    pick_ai(process, "Fake agent")
    check(until(lambda: "Fake agent is ready, signed in." in card(process), 10) and foot(process)[-1] == "Continue", "Ready: a check, and Continue")
    check(not js(process, "document.querySelector('.ob-how')?.open"), "How this works starts closed")
    click(process, ".ob-how summary")
    time.sleep(.5)
    how = js(process, "document.querySelector('.ob-how')?.innerText ?? ''") or ""
    check("counts the same as using" in how and "Still doesn't charge anything of its own" in how and "Still keeps your chats and your companion's memory on this computer" in how
          and "Your companion asks you before buying anything, sending messages or posts, or deleting things. Private tabs, passwords and cookies are never available." in how,
          "How this works: what it uses, where data goes, and what the companion asks first")
    rpc(process, "capture", name="connect-ready.png")
    copy_ok(process, "connect", copy)
    time.sleep(.6)


def create(process, copy):
    """Step 3: a name and a look, then a short chat in which Miso asks what you'd like help with; then what it will do, in
    plain words, with its instructions closed under Edit instructions; Hire and the joined card."""
    check(until(lambda: js(process, "!!document.querySelector(\"input[aria-label='Name your companion']\")"), 5), "Step 3 makes your companion")
    check(js(process, "document.querySelectorAll('.ob-faces [role=radio]').length") == 10, "Ten starting looks")
    check(foot(process)[-1] == "Continue (off)", "Continue waits for a name")
    time.sleep(1)
    type_into(process, "input[aria-label='Name your companion']", "Miso")
    check(until(lambda: js(process, "document.querySelector('.ob-name')?.innerText") == "Miso", 3), "The name shows under the companion")
    look = lambda: json.dumps(onboarding(process).get("look"), sort_keys=True)
    click(process, ".ob-faces [role=radio]:nth-child(3)")
    time.sleep(.5)
    third = js(process, "document.querySelector('.ob-faces [role=radio]:nth-child(3)')?.getAttribute('aria-label')")
    check(js(process, "document.querySelector('.ob-faces [aria-checked=true]')?.getAttribute('aria-label')") == third, f"Picking a starting look ({third})")
    before = look()
    click_text(process, ".ob-build-actions button", "Surprise me")
    check(until(lambda: look() != before, 3), "Surprise me picks another look")
    click(process, ".ob-faces [role=radio]:nth-child(3)")
    time.sleep(.5)
    chosen = look()
    click_text(process, ".ob-build-actions button", "Customize")
    check(until(lambda: js(process, "!!document.querySelector('.look-dialog')"), 6), "Customize opens the look editor")
    time.sleep(1.5)
    click_text(process, ".look-dialog .look-foot button", "Cancel")
    check(until(lambda: not js(process, "!!document.querySelector('.look-dialog')"), 4) and look() == chosen, "Cancel there keeps the look")
    check(not js(process, "!!document.querySelector(\"textarea[aria-label='What should they help with?']\")") and "Then Miso will ask what you'd like help with." in talk_text(process),
          "With an AI app ready there's nothing to fill in about the work: Miso will ask")
    check(foot(process) == ["Back", "Just browse for now", "Continue"], f"Then Continue ({foot(process)})")
    copy_ok(process, "create", copy)
    rpc(process, "capture", name="create.png")
    click(process, ".ob-next")
    typing = lambda: js(process, "!!document.querySelector('.ob-bubble.is-typing')")
    check(until(lambda: bubbles(process) and not typing(), 30) and bubbles(process)[-1].endswith("What would you like my help with?"), "Continue opens a short chat: Miso asks what you'd like help with")
    chips = js(process, "[...document.querySelectorAll('.ob-interview .ob-chips button')].map(b => b.innerText)")
    check(chips == ["Plan my week", "Keep my inbox tidy"] and foot(process)[-1] == "Continue (off)", f"with answers to tap, and Continue waits ({chips})")
    asked = next((p for p in (json.loads(x)["prompt"] for x in (BIN / "prompts.jsonl").read_text(encoding="utf-8").splitlines()) if "a new companion the user is making" in p), "")
    check("You are Miso, a new companion" in asked and "Don't use any tools" in asked and "keep every question simple" in asked, "The AI app you picked asks, as Miso, in plain words and with no tools")
    time.sleep(1)
    rpc(process, "capture", name="create-chat.png")
    chat(process, "Plans my trips and keeps receipts in order.")
    check(bubbles(process)[-1].endswith("What takes up too much of your time?"), "One simple question at a time")
    chat(process, button=(".ob-interview-foot button", "Skip this one"))
    check(bubbles(process)[-1].endswith("How do you like my answers?"), "Skip this one moves on")
    click_text(process, ".ob-interview .ob-chips button", "Short")
    check(until(lambda: js(process, "!!document.querySelector(\"textarea[aria-label='Instructions']\")?.value"), 30), "After the last answer Miso writes what it will do")
    time.sleep(1.2)
    plain = js(process, "[...document.querySelectorAll('.ob-plain li')].map(l => l.innerText.trim())") or []
    skills = js(process, "[...document.querySelectorAll('.ob-review .ob-chips span')].map(s => s.innerText)") or []
    check(plain == ["Sort out what matters most each day", "Point out anything that's late"] and 3 <= len(skills) <= 4 and "Replies: Short" in talk_text(process),
          f"To check before hiring, in plain words: what it will do, its skills and the reply length ({plain}, {skills})")
    check(js(process, "!!document.querySelector(\".ob-more:not([open]) textarea[aria-label='Instructions']\")"),
          "Its instructions stay closed under Edit instructions")
    job = js(process, "document.querySelector(\"textarea[aria-label='Instructions']\").value") or ""
    check(job.startswith("Plans my trips and keeps receipts in order.\n\nHow you work:\n- Start with what matters most today.\n") and job.endswith("\n- Ask me before you send, post, buy or delete anything."),
          "They're written from the chat, and still say to ask before sending, posting, buying or deleting")
    check(foot(process)[-1] == "Hire Miso", f"The last button says Hire Miso ({foot(process)})")
    click(process, ".ob-more summary")
    check(until(lambda: js(process, "!!document.querySelector(\".ob-more[open] textarea[aria-label='Instructions']\")"), 2), "Edit instructions opens them")
    edited = job + "\nKeep a running list of receipts."
    type_into(process, "textarea[aria-label='Instructions']", edited)
    time.sleep(.4)
    click_text(process, ".ob-foot button", "Back")
    check(until(lambda: js(process, "document.querySelector(\"input[aria-label='Name your companion']\")?.value") == "Miso", 3)
          and js(process, "document.querySelector(\"textarea[aria-label='What should they help with?']\")?.value") == "Plans my trips and keeps receipts in order.", "Back keeps the answers, and what Miso heard is there to change")
    time.sleep(.6)
    click(process, ".ob-next")
    check(until(lambda: js(process, "document.querySelector(\"textarea[aria-label='Instructions']\")?.value") == edited, 4), "and the edited instructions, since the goal didn't change")
    copy_ok(process, "review", copy)
    time.sleep(1.5)  # the step slides in
    rpc(process, "capture", name="review.png")
    click(process, ".ob-next")
    check(until(lambda: js(process, "document.querySelector('.joined-card [data-slot=dialog-title]')?.innerText") == "Miso joined your team", 5), "Hire Miso shows the joined card")
    on_top = js(process, "(() => { const c = document.querySelector('.joined-card')?.getBoundingClientRect(); return !!c && !!document.elementFromPoint(c.left + c.width / 2, c.top + c.height - 30)?.closest('.joined-card') })()")
    check(on_top, "in front of setup")
    time.sleep(1.5)
    rpc(process, "capture", name="joined.png")
    m = until(lambda: mate("Miso") or None, 5) or {}
    l = json.loads(m.get("Look") or "{}")
    check(companions() == ["Miso"] and m.get("Job") == edited and m.get("Length") == "short" and l.get("v") == 2 and m.get("Setup") == "pending",
          f"Miso is saved once, with the new-style look, the edited instructions and short replies ({companions()}, {m.get('Length')}, {l.get('v')}, {m.get('Setup')})")
    click_text(process, ".joined-actions button", "Start chatting")
    check(until(lambda: step_now(process) == 4, 5), "Start chatting goes on to the first task")


def first(process, copy):
    """Step 4: a first task in Miso's chat, the sample page first."""
    check(until(lambda: "Miso is ready. What should we start with?" in talk_text(process), 4), "Step 4 asks what to start with")
    time.sleep(1.5)
    tasks = js(process, "[...document.querySelectorAll('.ob-tasks [role=radio]')].map(b => b.innerText.trim())") or []
    check(tasks[:1] == ["Compare three backpacks\nSample page from Still. The products are made up."] and len(tasks) >= 3, f"The sample page first, labeled, then tasks for your work ({tasks})")
    check(not js(process, "!!document.querySelector('.ob-preview')"), "With an AI app ready there's no preview note")
    check(foot(process)[-1] == "Let's go (off)" and "Not now, just browse" in foot(process), f"Let's go waits for a task; you can still just browse ({foot(process)})")
    type_into(process, "textarea[aria-label='Your own task']", "Nothing right now")
    time.sleep(.4)
    check(foot(process)[-1] == "Let's go (off)", "\"Nothing right now\" isn't a task")
    type_into(process, "textarea[aria-label='Your own task']", "")
    click(process, ".ob-tasks [role=radio]")
    check(until(lambda: foot(process)[-1] == "Let's go", 2), "Picking the sample turns on Let's go")
    copy_ok(process, "first", copy)
    rpc(process, "capture", name="first.png")
    time.sleep(1)
    click(process, ".ob-next")
    check(until(lambda: not setup_open(process), 5), "Let's go closes setup")
    played = sorted(set(sounds(process)))
    check(set(played) <= {"intro", "jingle"}, "Setup plays only the intro and the end jingle" + ("" if set(played) <= {"intro", "jingle"} else f" ({played})"))
    split = until(lambda: js(process, "!!document.querySelector('.page-column.is-split .page-pane') && !!document.querySelector('.page-control')"), 20)
    check(split, "The task runs in Miso's chat: the chat on the left, the sample page on the right, the pill at work")
    time.sleep(6)


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
    tiles = js(process, "[...document.querySelectorAll('.get-started button')].map(b => b.innerText.trim())") or []
    side = "Tabs across the top" if state().get("Preferences", {}).get("TabLayout") == "Modern" else "Tabs down the side"
    check(len(tiles) == 4 and tiles[0] == "Import from another browser" and tiles[1] in ("Open links in Still", "Still opens your links") and tiles[2] == side,
          f"What setup left for later waits on the home page: import, open links in Still, where the tabs go ({tiles})")


def again(process):
    """Run setup again, from Settings: the four steps from the top, and Just browse leaves everything as it was."""
    calls, started = rpc(process).get("aiCalls"), len(chats())
    send(process, "welcomeAgain")
    check(until(lambda: "A little less work. A little more still." in talk_text(process), 10) and step_now(process) == 1, "Run setup again starts at the welcome")
    time.sleep(2.5)
    click(process, ".ob-browse")
    check(until(lambda: not setup_open(process), 5) and until(lambda: state().get("Welcome") is False, 5), "Just browse for now closes it")
    time.sleep(2)
    check(companions() == ["Miso"] and rpc(process).get("aiCalls") == calls and len(chats()) == started, f"Nothing changed: still just Miso, no AI run, no new chat ({companions()})")
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
    """Set me up again with Miso: the fake AI app follows up on each answer; a question can be skipped and "that's enough"
    ends it. Then what it set up, each with an undo and the wording ones editable, and the companions it suggests, which
    join only on Hire. Recorded as interview.mp4."""
    calls = rpc(process).get("aiCalls")
    recorder = record(process.pid, RUN / "interview.mp4")
    sent = lambda: [json.loads(l)["prompt"] for l in (BIN / "prompts.jsonl").read_text(encoding="utf-8").splitlines()]
    talked = len(sent())
    li = lambda words: f"[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.includes({json.dumps(words)}))"
    try:
        send(process, "welcomeAgain", talk=True)
        check(until(lambda: "What do you work on these days?" in talk_text(process), 20), "Set me up again opens straight into Miso's questions")
        first = sent()[talked]
        check("- growth: Talia, Growth, Signups and retention" in first and "- research: Maya, Research" in first and "- assistant:" not in first and "Ruth" not in first,
              "It knows Still's companions; Assistant Ruth isn't offered")
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
        groups = lambda: js(process, "[...document.querySelectorAll('.ob-summary section')].map(s => s.querySelector('h4').textContent.trim() + ': ' + [...s.querySelectorAll('li b')].map(b => b.innerText.trim()).join(' | '))") or []
        rows = groups()
        check(rows == ["Your team: Suggested for your team | Suggested for your team | I'll remember | What I'll focus on | I'll also remember",
                       "Your Still: Theme | Pinned | When I work in tabs | How I talk | Ideas about", "First up: First, I'll help with"], f"The summary groups what it set up ({rows})")
        offered = js(process, "[...document.querySelectorAll('.ob-summary li')].filter(l => l.querySelector('.is-hire')).map(l => l.querySelector('small').innerText + ': ' + [...l.querySelectorAll('button')].map(b => b.innerText.trim()).join(', '))") or []
        check(len(offered) == 2 and offered[0].startswith("Growth Talia · Signups and retention: Hire, No thanks") and offered[1].startswith("Research Maya ·"),
              f"It suggests Talia and Maya, each with Hire and No thanks ({offered})")
        time.sleep(1.5)
        prefs = until(lambda: (p := state().get("Preferences", {})).get("Interests") == ["Baking", "Wholesale"] and p, 5) or {}  # saved a moment later
        check(companions(prefs) == ["Miso"], f"Nobody joins on their own ({companions(prefs)})")
        rpc(process, "capture", name="interview-summary.png")
        check(rpc(process).get("theme") == "Dark" and prefs, "The theme and interests it picked apply")
        check(any(t["Pinned"] and t["Url"].endswith("/recipes/pasta") for t in rpc(process)["tabs"]), "Its pinned site is pinned")
        js(process, f"{li('Growth Talia')}?.querySelector('.is-hire')?.click()")
        check(until(lambda: "Talia" in companions(), 5), "Hire adds Talia")
        until(lambda: "Talia's routine" in " ".join(groups()), 3)
        rows = groups()
        check(rows[0] == "Your team: Suggested for your team | I'll remember | What I'll focus on | I'll also remember | New on your team | Talia will remember | What Talia will focus on | Talia will also remember | Talia's routine, off for now",
              f"and what setup has for Talia shows under Your team ({rows[0]})")
        js(process, f"[...{li('Research Maya')}?.querySelectorAll('button') ?? []].find(b => b.innerText.trim() == 'No thanks')?.click()")
        check(until(lambda: "Not hired" in (js(process, f"{li('Research Maya')}?.innerText") or ""), 3) and "Maya" not in companions(), "No thanks leaves Maya out")
        mate_ = mate("Miso")
        talia = mate("Talia")
        check(mate_.get("Job", "").endswith("For me: Keep my wholesale orders on track and tell me when a cafe is late to pay.") and talia.get("Job", "").endswith("For me: Find me a second baker who can start at 5am."),
              "Each companion's instructions get a paragraph about the user")
        check(talia.get("Crew") == "growth" and len(talia.get("Routines", [])) == 2 and not any(r["On"] for r in talia["Routines"])
              and any(r["Time"] == "08:30" and r["Days"] == [1, 2, 3, 4, 5] for r in talia["Routines"]), f"Talia's routines, its own and the new one, start off ({talia.get('Routines')})")
        facts, theirs = [f["Text"] for f in memory("Miso") if f.get("Status", "active") == "active"], [f["Text"] for f in memory("Talia")]
        check(mate_.get("Tone") == "Keep it short and cheerful." and "Runs a small bakery that sells to cafes." in facts and "Uses Gmail and Shopify all day." in facts and "Has two cats." in facts
              and "Likes to be called Sammy." in facts and "Bakes sourdough for six cafes." in facts, f"Miso's tone and memories are set ({facts})")
        check("Has two cats." in theirs and "Hiring a second baker for early shifts." in theirs and "Bakes sourdough for six cafes." not in theirs,
              f"Talia learns about the user too, and what's just for it ({theirs})")

        def edit(label, text):
            js(process, f"[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith({json.dumps(label)}))?.querySelector('button')?.click()")
            until(lambda: js(process, "!!document.querySelector('.ob-edit textarea')"), 3)
            time.sleep(.6)
            type_into(process, ".ob-edit textarea", text)
            time.sleep(.6)
            js(process, "document.querySelector('.ob-edit')?.requestSubmit()")
        edit("How I talk", "Short answers, no small talk.")
        check(until(lambda: mate("Miso").get("Tone") == "Short answers, no small talk.", 5)
              and "Short answers, no small talk." in (js(process, "document.querySelector('.ob-summary')?.innerText") or ""), "Its wording can be edited right in the summary")
        edit("I'll also remember", "Bakes sourdough and rye for six cafes.\nDelivers before 7am.")
        check(until(lambda: "Delivers before 7am." in [f["Text"] for f in memory("Miso")] and "Bakes sourdough for six cafes." not in [f["Text"] for f in memory("Miso")], 5),
              "An edited memory replaces what it kept")
        js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('Theme'))?.querySelector('button')?.click()")
        check(until(lambda: rpc(process).get("theme") == "System" and "Undone" in (js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('Theme'))?.innerText") or ""), 5),
              "Undo puts the theme back")
        talia_dir = PROFILE / "companions" / talia.get("Id", "-")
        js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('New on your team'))?.querySelector('button')?.click()")
        check(until(lambda: "Talia" not in companions() and not talia_dir.exists(), 5) and until(lambda: js(process, "[...document.querySelectorAll('.ob-summary li')].filter(l => /Talia/.test(l.innerText) && l.classList.contains('is-undone')).length") == 5, 3),
              "Undoing a hire lets that companion go, with everything setup gave it")
        js(process, "[...document.querySelectorAll('.ob-summary li')].find(l => l.innerText.startsWith('First,'))?.querySelectorAll('button')[1]?.click()")  # no first task: the next suite wants no chat running
        time.sleep(2)
        check(rpc(process).get("aiCalls") - calls == 6, f"Each message is one small AI run ({rpc(process).get('aiCalls') - calls})")
        click(process, ".ob-next")
        check(until(lambda: not setup_open(process), 5), "Done closes setup")
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
    """The last companion can't be deleted, then the look editor, open for six companions."""
    new_tab(process)
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 10)
    companions_page(process)
    until(lambda: js(process, "document.querySelectorAll('.mate-card').length") == 1, 10)
    click(process, ".mate-portrait[aria-label='Edit Miso']")
    until(lambda: js(process, "!!document.querySelector('.profile-panel')"), 5)
    js(process, "document.querySelector('.profile-head [aria-label=More]')?.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' }))")
    until(lambda: js(process, "!!document.querySelector('[role=menuitem][data-variant=destructive]')"), 3)
    click(process, "[role=menuitem][data-variant=destructive]")
    until(lambda: js(process, "!!document.querySelector('[data-slot=alert-dialog-content]')"), 3)
    note = js(process, "document.querySelector('[data-slot=alert-dialog-content]')?.innerText") or ""
    time.sleep(1)
    check("Still needs at least one" in note and companions() == ["Miso"], f"Miso, the only one, can't be deleted ({note})")
    rpc(process, "capture", name="last-one.png")
    click(process, "[data-slot=alert-dialog-cancel]")
    until(lambda: not js(process, "!!document.querySelector('[data-slot=alert-dialog-content]')"), 3)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    until(lambda: not js(process, "!!document.querySelector('.profile-panel')"), 3)
    for i, (name, color, look) in enumerate(CREW):
        send(process, "companionSave", id=f"crew{i}", name=name, job="", look=json.dumps({**BASE, "color": color, **look}))
    new_tab(process)
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 10)
    companions_page(process)
    six = until(lambda: js(process, "document.querySelectorAll('.mate-card').length") == 6, 10)
    check(six, f"Six companions on the Companions page ({js(process, 'document.querySelectorAll(`.mate-card`).length')})")
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


def fresh(name):
    profile = RUN / name
    manifests(profile)
    return profile


def browse():
    """A second fresh profile: the intro plays out on its own; Just browse for now leaves a working browser with no
    companion, whose new tab page offers Create your companion (back into setup at Connect) and Get started."""
    profile = fresh("browse")
    process = launch(EXE, profile, {**os.environ, "STILL_QA_SEARCH": SITE + "/search?q="})
    try:
        until(lambda: js(process, "!!document.querySelector('.welcome.ob .intro.is-on')"), 8)
        time.sleep(4)
        rpc(process, "capture", name="intro-mark.png")  # Still's name below the companion
        check(until(lambda: not js(process, "!!document.querySelector('.intro')"), 8) and until(lambda: "A little less work" in talk_text(process), 3), "Left alone, the intro ends and the welcome begins")
        time.sleep(2.5)
        calls = rpc(process).get("aiCalls")
        click(process, ".ob-browse")
        check(until(lambda: not setup_open(process), 5) and until(lambda: state(profile).get("Welcome") is False, 5),
              "Just browse for now closes setup")
        time.sleep(1.5)
        check(not mates(profile) and rpc(process).get("aiCalls") == calls and not chats(profile), "with no companion, no AI run and no chat")
        check(until(lambda: js(process, "!!document.querySelector('.new-tab-create')") and not js(process, "!!document.querySelector('.home-face')"), 10),
              "The new tab page is the plain one, with Create your companion")
        check(js(process, "!!document.querySelector('.get-started')"), "and Get started")
        send(process, "navigate", url=SITE + "/recipes/tacos")
        check(until(lambda: any("Black bean tacos" in t.get("Title", "") for t in rpc(process)["tabs"]), 30), "Browsing works")  # a fresh profile's first page can take a while
        rpc(process, "capture", name="browse.png")
        new_tab(process)
        until(lambda: js(process, "!!document.querySelector('.get-started-x')"), 6)
        click(process, ".get-started-x")
        check(until(lambda: not js(process, "!!document.querySelector('.get-started')"), 3) and js(process, "localStorage.getItem('still.getStarted')") == "1", "Get started can be put away")
        click(process, ".new-tab-create")
        check(until(lambda: setup_open(process) and step_now(process) == 2, 6), "Create your companion opens setup at Connect")
        send(process, "aiHarness", harness="gone")  # an app that isn't on this computer
        time.sleep(1.5)
        click_text(process, ".ob-foot button", "Set up later")
        check(until(lambda: js(process, "!!document.querySelector(\"textarea[aria-label='What should they help with?']\")"), 5)
              and "tell them what you'd like help with" in talk_text(process), "Without an AI app ready, what to help with is typed instead")
        check(make(process, "Taro", "keep my inbox under control"), "and Continue goes straight to what it will do")
        time.sleep(1.2)
        plain = js(process, "[...document.querySelectorAll('.ob-plain li')].map(l => l.innerText.trim())") or []
        check(plain == ["Keep my inbox under control."], f"in the words they typed ({plain})")
        check(rpc(process).get("aiCalls") == calls and not js(process, "!!document.querySelector('.ob-interview')"), "with no chat and no AI run")
        rpc(process, "capture", name="review-typed.png")
        click(process, ".ob-browse")
        check(until(lambda: not setup_open(process), 5) and not mates(profile), "and Just browse closes it again, still with no companion")
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
        close_all(profile)


def resume():
    """A third fresh profile, closed at every step and opened again: the same step with the same answers, and never a
    second companion, also after a hard kill right after Hire. Screenshots of each step, light and dark. A link from
    another app during setup opens in a window of its own. No AI connected on the last step: a labeled preview."""
    profile, out = fresh("resume"), RUN / "shots"
    out.mkdir()
    process = None

    def start():
        nonlocal process
        try:
            process = launch(EXE, profile)
        except RuntimeError as e:  # Windows' QA pipe sometimes isn't up in time on a loaded machine
            print(f"NOTE start failed ({e}), trying once more", flush=True)
            close_all(profile)
            time.sleep(3)
            process = launch(EXE, profile)
        until(lambda: js(process, "!!document.querySelector('.welcome.ob .ob-dots')"), 20)
        if until(lambda: js(process, "!!document.querySelector('.intro')"), 3):
            time.sleep(1)
            key(process, " ")
            until(lambda: not js(process, "!!document.querySelector('.intro')"), 3)
        time.sleep(2.5)

    def reopen(hard=False):
        if hard:
            process.kill()
        else:
            rpc(process, "quit")
        process.wait(timeout=20)
        close_all(profile)
        time.sleep(2)
        start()

    def shoot(name):
        for theme in ("Light", "Dark"):
            click(process, f".ob-theme [aria-label={theme}]")
            time.sleep(1.4)
            rpc(process, "capture", name=f"{name}-{theme.lower()}.png")
            shutil.copy(profile / f"{name}-{theme.lower()}.png", out / f"{name}-{theme.lower()}.png")
        click(process, ".ob-theme [aria-label=System]")
        time.sleep(.6)

    try:
        start()
        shoot("1-welcome")
        reopen()
        check(step_now(process) == 1 and "A little less work" in talk_text(process), "Closed on the welcome, it opens on the welcome")
        next_step(process)
        pick_ai(process, "Fake agent")
        until(lambda: "Fake agent is ready" in card(process), 10)
        shoot("2-connect")
        link = SITE + "/page?signin"
        if MAC:  # started from the command line, a second copy on the Mac runs on its own; a link from another app comes through Launch Services
            subprocess.run(["open", "-a", str(EXE.parents[2]), link], timeout=30)
        else:
            subprocess.run([str(EXE), "--qa", "--profile", str(profile), "--profiles-root", str(profile), link], timeout=30)
        ok = until(lambda: any(w["temporary"] and link in w["tabs"] for w in rpc(process).get("windows", [])), 10)
        check(ok and not any(t["Url"] == link for t in rpc(process).get("tabs", [])), "A link from another app during setup opens in a window of its own, not behind setup")
        reopen()
        check(step_now(process) == 2 and until(lambda: "Fake agent is ready" in card(process), 10), "Closed on Connect, it opens there, with the app still picked")
        next_step(process)
        type_into(process, "input[aria-label='Name your companion']", "Pip")
        click(process, ".ob-faces [role=radio]:nth-child(5)")
        time.sleep(1)
        look = json.dumps(onboarding(process).get("look"), sort_keys=True)
        shoot("3-create")
        reopen()
        check(step_now(process) == 3 and js(process, "document.querySelector(\"input[aria-label='Name your companion']\")?.value") == "Pip"
              and js(process, "document.querySelector('.ob-faces [role=radio]:nth-child(5)')?.getAttribute('aria-checked')") == "true"
              and json.dumps(onboarding(process).get("look"), sort_keys=True) == look, "Closed while making it, it opens with the same name and look")
        click(process, ".ob-next")
        until(lambda: bubbles(process) and not js(process, "!!document.querySelector('.ob-bubble.is-typing')"), 30)
        chat(process, "Research suppliers for my shop and keep a short list.")
        time.sleep(1)
        shoot("3-chat")
        reopen()
        check(step_now(process) == 3 and js(process, "document.querySelector(\"input[aria-label='Name your companion']\")?.value") == "Pip"
              and not js(process, "!!document.querySelector('.ob-interview')") and not mates(profile), "Closed in the chat, it opens on the name and look, and nobody is hired")
        check(make(process, "Pip", "Research suppliers for my shop and keep a short list."), "Continue starts the chat again, and it ends on what Pip will do")
        click(process, ".ob-more summary")
        job = js(process, "document.querySelector(\"textarea[aria-label='Instructions']\").value") + "\nAlways list three options."
        type_into(process, "textarea[aria-label='Instructions']", job)
        time.sleep(1)
        shoot("3-review")
        reopen()
        check(step_now(process) == 3 and js(process, "document.querySelector(\"textarea[aria-label='Instructions']\")?.value") == job
              and js(process, "document.querySelectorAll('.ob-plain li').length") == 2 and not mates(profile),
              "Closed on what it will do, it opens there with the edits, and nobody is hired yet")
        click(process, ".ob-next")
        until(lambda: js(process, "!!document.querySelector('.joined-card')"), 5)
        until(lambda: mates(profile), 5)
        reopen(hard=True)  # right after Hire, before the joined card is answered
        at, names = step_now(process), [c["Name"] for c in mates(profile)]
        check(at in (3, 4) and names == ["Pip"], f"Killed right after Hire, it opens with Pip hired once (step {at}, {names})")
        if at == 3:  # the kill beat the page's storage to disk: Hire again updates the same Pip
            click(process, ".ob-next")
            until(lambda: js(process, "!!document.querySelector('.joined-card')"), 5)
            click_text(process, ".joined-actions button", "Start chatting")
            until(lambda: step_now(process) == 4, 5)
        check(step_now(process) == 4 and [c["Name"] for c in mates(profile)] == ["Pip"], "On the first task, still with one Pip")
        shoot("4-first")
        click_text(process, ".ob-foot button", "Back")
        until(lambda: js(process, "!!document.querySelector(\"input[aria-label='Name your companion']\")"), 5)
        time.sleep(1)
        click(process, ".ob-next")
        check(until(lambda: foot(process)[-1] == "Save changes", 4), "Going back after Hire says Save changes")
        click(process, ".ob-next")
        check(until(lambda: step_now(process) == 4, 4) and [c["Name"] for c in mates(profile)] == ["Pip"] and not js(process, "!!document.querySelector('.joined-card')"),
              "Saving again updates Pip: still one, and no second joined card")
        reopen()
        check(step_now(process) == 4 and [c["Name"] for c in mates(profile)] == ["Pip"], "Closed on the first task, it opens there, still with one Pip")
        send(process, "aiHarness", harness="gone")
        check(until(lambda: js(process, "!!document.querySelector('.ob-preview')"), 6) and "Offline agent isn't connected yet, so Pip can't start" in (js(process, "document.querySelector('.ob-preview')?.innerText") or "")
              and foot(process)[-1] == "Let's go (off)", "No AI connected: a labeled preview, and Let's go stays off")
        check((js(process, "[...document.querySelectorAll('.ob-preview button')].map(b => b.innerText.trim())") or []) == ["Connect", "Retry"], "with Connect and Retry")
        legible = """(() => {
         const rgba = c => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c; x.fillRect(0, 0, 1, 1); return [...x.getImageData(0, 0, 1, 1).data] }
         const lum = ([r, g, b]) => [r, g, b].map(v => (v /= 255) <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((t, v, i) => t + v * [.2126, .7152, .0722][i], 0)
         const card = rgba(getComputedStyle(document.querySelector('.ob-preview')).backgroundColor)
         return [...document.querySelectorAll('.ob-preview button')].map(b => { const s = getComputedStyle(b), back = rgba(s.backgroundColor), [x, y] = [lum(rgba(s.color)), lum(back[3] ? back : card)].sort((p, q) => q - p)
          return Math.round((x + .05) / (y + .05) * 10) / 10 })
        })()"""
        for theme in ("Light", "Dark"):
            click(process, f".ob-theme [aria-label={theme}]")
            time.sleep(.6)
            ratios = js(process, legible) or []
            check(len(ratios) == 2 and min(ratios) >= 4.5, f"Their labels read against their backgrounds, {theme.lower()} ({ratios})")
        click(process, ".ob-theme [aria-label=System]")
        shoot("4-preview")
        click_text(process, ".ob-preview button", "Connect")
        check(until(lambda: step_now(process) == 2, 4), "Connect goes back to step 2")
        calls = rpc(process).get("aiCalls")
        click(process, ".ob-browse")
        check(until(lambda: not setup_open(process), 5), "Not now, just browse closes setup")
        time.sleep(4)
        pip = [c for c in mates(profile) if c["Name"] == "Pip"]
        check(len(pip) == 1 and rpc(process).get("aiCalls") == calls and not chats(profile), "Pip stays hired, once, and waits: no chat starts until it's opened")
        check(len(list(out.glob("*.png"))) == 14, f"Screenshots of each step, light and dark ({len(list(out.glob('*.png')))})")
    finally:
        if process:
            rpc(process, "quit")
            process.wait(timeout=20)
        close_all(profile)


def close_all(profile):
    """Nothing this suite started outlives it: a copy still running on the profile would answer the next suite's AI apps."""
    if MAC:
        subprocess.run(["pkill", "-f", "--", "--profile " + str(profile)], capture_output=True)
    else:  # only QA copies started on this suite's profiles
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Get-CimInstance Win32_Process -Filter \"Name='Still.exe'\" | Where-Object {{ $_.CommandLine -like '*--profile {profile}*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"], capture_output=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        close_all(RUN)  # every profile lives under it
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
