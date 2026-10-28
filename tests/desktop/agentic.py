"""Phase 3: the AI at work in the browser. No AI plan is used: a fake agent app (a manifest in Still's agents folder)
connects to Still's MCP server the way Claude Code does and runs a fixed script for each prompt:
  LAPTOPS <store>  opens a local store, clicks, types, saves a CSV with save_file and replies (the brief's acceptance flow)
  SLOW <url> <s>   opens a tab and keeps reading it for s seconds (parallel runs, Take over, Stop)
  ASK              asks the user with ask_user and replies with the answer
  LOOKUP           searches with web_search, reads the first result with read_url and replies with a table, a draft and next steps
Chat runs open their pages as background tabs beside the chat, never in the tab strip.

Run: python tests/desktop/agentic.py artifacts/Still-QA/Still.exe
Screenshots: docs/agentic/compare/ (split-v01, done-v01, viewer-side-v01, library-v01, tasks-v01, question-v01, lookup-v01, mine-v01)
"""
import csv
import http.server
import json
import os
from pathlib import Path
import re
import sys
import textwrap
import threading
import time
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, compare, js, launch, rpc, send, text, until  # noqa: E402
from mcp_client import Mcp  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
LIVE = "--live" in sys.argv  # one small real Claude run (Haiku) of the laptops task. By hand only: it uses your plan.
RUN = ROOT / "artifacts" / ("agentic-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
OUT = ROOT / "docs" / "agentic" / "compare"
REFS = Path("D:/Still/work/refs")
RESULT = {"checks": []}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


# ---- a small store ----
LAPTOPS = [("Acer Aspire 5, 15.6\"", 549), ("Lenovo IdeaPad Slim 3", 479), ("HP Pavilion 14", 699), ("ASUS Vivobook 16", 629), ("Dell Inspiron 15", 589),
           ("MacBook Air 13", 999), ("Microsoft Surface Laptop Go 3", 799), ("Samsung Galaxy Book4", 749), ("Acer Swift Go 14", 779), ("Lenovo ThinkPad E14", 899),
           ("HP Envy x360", 949), ("ASUS Zenbook 14", 1099), ("Dell XPS 13", 1299), ("Lenovo Chromebook Duet", 299), ("HP 15 Laptop", 399), ("Razer Blade 14", 2199)]
CHEAP = [(n, p) for n, p in LAPTOPS if p < 800]


def store(query):
    cap = int(query.get("max", ["100000"])[0])
    cards = "".join(f'<article class=card><div class=pic></div><h3><a href="/p/{i}">{n}</a></h3><p class=price>${p}</p><button>Add to cart</button></article>'
                    for i, (n, p) in enumerate(LAPTOPS) if p <= cap)
    return f"""<!doctype html><meta charset=utf-8><title>Laptops · Pinecone Store</title>
<style>body{{margin:0;font:15px system-ui;color:#1d2433;background:#f6f7f9}}header{{display:flex;gap:16px;align-items:center;padding:14px 28px;background:#16324f;color:#fff}}
header b{{font-size:19px}}form{{display:flex;gap:6px;flex:1;max-width:520px}}input{{flex:1;padding:9px 12px;border-radius:8px;border:0;font:inherit}}
header button,#under{{padding:9px 14px;border-radius:8px;border:0;background:#f4b740;color:#16324f;font-weight:600;text-decoration:none}}
h1{{margin:22px 28px 0;font-size:22px}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px;padding:18px 28px}}
.card{{background:#fff;border-radius:12px;padding:14px;box-shadow:0 1px 3px #0002}}.pic{{height:110px;border-radius:8px;background:linear-gradient(135deg,#d8e2f0,#eef2f7)}}
.card h3{{font-size:15px;margin:10px 0 4px}}.card a{{color:inherit}}.price{{font-weight:700;margin:0 0 10px}}.card button{{padding:7px 12px;border-radius:8px;border:1px solid #16324f;background:#fff}}</style>
<header><b>Pinecone Store</b><form action=/laptops><input id=q name=q placeholder="Search laptops"><button>Search</button></form><a id=under href="/laptops?max=800">Under $800</a></header>
<h1>Laptops{' under $800' if cap < 100000 else ''}</h1><main class=grid>{cards}</main>"""


REVIEWS = [("Best laptops under $800, tested", "/reviews/best", "We used twelve laptops for a week each. The Acer Swift Go 14 won on screen and battery."),
           ("Acer Swift Go 14 review", "/reviews/swift-go", "Bright OLED screen, 10 hours of battery, and a fair price."),
           ("Lenovo IdeaPad Slim 3 review", "/reviews/slim-3", "The best value under $500, if you can live with a dim screen.")]


def results(query):
    q = query.get("q", [""])[0]
    rows = "".join(f'<div class="result"><h2><a class="result__a" href="{path}">{title}</a></h2><a class="result__snippet">{snip}</a></div>' for title, path, snip in REVIEWS)
    return f"<!doctype html><meta charset=utf-8><title>{q} at Search</title><nav>Search menu</nav><main>{rows}</main>"


def review(path):
    title, _, snip = next(r for r in REVIEWS if r[1] == path)
    return f"<!doctype html><meta charset=utf-8><title>{title}</title><nav>Home · Reviews · Deals</nav><article><h1>{title}</h1>" + f"<p>{snip}</p>" * 8 + "</article><footer>Footer links</footer>"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        body = (store(urllib.parse.parse_qs(url.query)) if url.path == "/laptops"
                else results(urllib.parse.parse_qs(url.query)) if url.path == "/search"
                else review(url.path) if url.path.startswith("/reviews/")
                else f"<!doctype html><title>Reading {url.path}</title><h1 style='font:24px system-ui;margin:40px'>Page {url.path}</h1>").encode()
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
CSV = "Name,Price,Store\n" + "".join(f"\"{n.replace(chr(34), chr(34) * 2)}\",{p},Pinecone Store\n" for n, p in CHEAP)

# ---- the fake AI app: Still's MCP server, driven by a script ----
FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def log(name, entry):
        with open(os.path.join(here, name), "a", encoding="utf-8") as f: f.write(json.dumps(entry) + "\n")
    log("prompts.jsonl", {"args": args, "prompt": prompt})
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
        ok, text = not r.get("isError"), "\n".join(c.get("text", "") for c in r.get("content", []))
        log("calls.jsonl", {"tool": tool, "args": {k: v for k, v in a.items() if k != "content"}, "ok": ok, "text": text[:300], "t": time.time()})
        if shown: say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t%d" % n, "is_error": not ok}]}})
        return ok, text
    def reply(text): say({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    asked = prompt.rsplit("\n\n", 1)[-1]
    if m := re.search(r"LAPTOPS (\S+)", asked):
        reply("I'll open the store, find laptops under $800, and save a CSV for you.")
        call("open_tab", url=m[1] + "/laptops")
        call("read_page", text=False)
        call("click", text="Under $800")
        call("type", selector="#q", text="laptop")
        log("calls.jsonl", {"tool": "marker", "text": "typed", "t": time.time()})
        time.sleep(3)
        call("save_file", shown=False, name="../evil.exe", content="nope")
        call("save_file", shown=False, name="laptops-under-800.csv", content="draft")
        call("save_file", name="laptops-under-800.csv", content=open(os.path.join(here, "laptops.csv"), encoding="utf-8").read())
        reply("Saved 10 laptops under $800 to a CSV. The cheapest is the Lenovo Chromebook Duet at $299.")
    elif m := re.search(r"SLOW (\S+) (\d+)", asked):
        tag = m[1].rsplit("/", 1)[-1]
        call("open_tab", url=m[1])
        end = time.time() + int(m[2])
        while time.time() < end:
            ok, text = call("read_page", shown=False, text=False)
            log("slow-" + tag + ".jsonl", {"ok": ok, "text": text[:80], "t": time.time()})
            if not ok and "Stop" in text: break
            time.sleep(.4)
        reply("Done reading " + tag + ".")
    elif "LOOKUP" in asked:
        ok, text = call("web_search", query="laptop reviews under 800")
        found = json.loads(text)["results"] if ok else []
        log("calls.jsonl", {"tool": "marker", "text": "found %d" % len(found), "t": time.time()})
        if found: call("read_url", url=found[0]["url"])
        reply("**The Acer Swift Go 14 is the one to get under $800.**\n\n| Laptop | Price | Why |\n|---|---|---|\n| Acer Swift Go 14 | $779 | Bright screen, long battery |\n| Lenovo IdeaPad Slim 3 | $479 | Best value |\n\n"
              "Here's a note you could send:\n\n```draft\nHi Sam, I'd go with the Acer Swift Go 14. It's $779 and lasts about 10 hours on a charge.\n```\n\n>> Find it cheaper\n>> Compare battery life\n>> Save this as a CSV")
    elif "ASK" in asked:
        ok, text = call("ask_user", question="Which screen size do you want?", options=["13 inch", "15 inch"])
        reply("You picked: " + text[:80])
    else:
        reply("Done, fake reply.")
    still.stdin.close()
''')


def click(process, selector):
    return js(process, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.click(); return !!e }})()")


def click_text(process, selector, words):
    return js(process, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => e.innerText.trim().includes({json.dumps(words)})); e?.click(); return !!e }})()")


def open_menu(process, selector):
    """Radix menus open on pointerdown, not click."""
    js(process, f"document.querySelector({json.dumps(selector)})?.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }}))")


def escape(process):
    js(process, "document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")


def calls():
    file = BIN / "calls.jsonl"
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def slow(tag):
    file = BIN / f"slow-{tag}.jsonl"
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def chats():
    try:
        return {c["Title"]: c for c in json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {}


def tabs(process):
    return rpc(process)["tabs"]


def strip(process):
    """The tabs the user sees in the tab strip: everything but the pages a chat keeps beside it."""
    return [t for t in tabs(process) if not t["InChat"]]


def home(process):
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 20)
    time.sleep(.4)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")


def ask(process, words, companion="pip"):
    home(process)
    send(process, "aiSend", text=words, home=True, companion=companion)


def capture(process, name, reference=None):
    rpc(process, "capture", name=name + ".png")
    (OUT / f"{name}.png").write_bytes((PROFILE / f"{name}.png").read_bytes())
    if reference:
        (REFS / "compare").mkdir(exist_ok=True)
        compare(OUT / f"{name}.png", REFS / reference, REFS / "compare" / f"{name}-compare.png")  # their frames stay out of the repo


def running(process):
    label = js(process, "document.querySelector('.tasks-button')?.getAttribute('aria-label') ?? ''") or ""
    found = re.search(r"(\d+) running", label)
    return int(found[1]) if found else 0


def main():
    BIN.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    (BIN / "laptops.csv").write_text(CSV, encoding="utf-8")
    (BIN / "fakeagent.cmd").write_text(f'@"{sys.executable}" -I "{BIN / "fake_agent.py"}" %*\r\n')
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}], "ApprovedAgents": ["Outside"], "AiHarness": "claude" if LIVE else "fake", "Theme": "Light", "Width": 1720, "Height": 1080},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "STILL_QA_SEARCH": SITE + "/search?q="}
    process = launch(EXE, PROFILE, env)
    try:
        if LIVE:
            return live(process)
        laptops(process)
        lookup(process)
        parallel(process)
        hand_over(process)
        outside_app(process)
        queue_and_question(process)
        check(not js(process, "window.__shellErrors?.length") and not rpc(process).get("shellErrors"), "No interface errors")
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


def live(process):
    """The same task through real Claude on Haiku: it has to find the filter, read the prices and call save_file itself."""
    send(process, "aiToggle")
    send(process, "aiCheck")
    time.sleep(3)  # the model list loads in the background
    send(process, "aiAdvanced", on=True)
    send(process, "aiModel", harness="claude", model="haiku")
    started = time.monotonic()
    ask(process, f"Go to {SITE}/laptops, find every laptop under $800 and save them as laptops.csv with name and price columns.")
    until(lambda: next(PROFILE.glob("library/*/*.csv"), None), 300, 2)
    done = until(lambda: not running(process), 120, 2)
    saved = next(PROFILE.glob("library/*/*.csv"), None)
    check(len(list(PROFILE.glob("library/*/*"))) == 1, "Fixing a file replaces it instead of leaving a second copy")
    RESULT["seconds"] = round(time.monotonic() - started, 1)
    rows = list(csv.reader(saved.read_text(encoding="utf-8-sig").splitlines())) if saved else []
    plain = lambda name: re.sub(r"[^a-z0-9]", "", name.lower())  # "Acer Aspire 5, 15.6" or without the comma
    names = {plain(name) for name, price in LAPTOPS if price < 800}
    found = {plain(r[0]) for r in rows[1:] if r}
    RESULT["rows"], RESULT["steps"] = rows, [m["Text"] for c in chats().values() for m in c["Messages"] if m["Role"] == "tool"]
    check(bool(saved) and done, "Claude finishes and saves a CSV to the Library")
    check(found == names, f"The CSV has exactly the {len(names)} laptops under $800")
    check(bool(js(process, "!!document.querySelector('.file-card')")), "The chat shows the file card")
    capture(process, "live-v01")


def laptops(process):
    """The brief's acceptance flow: find laptops under $800 on a store site and save a CSV."""
    mine = len(strip(process))
    ask(process, f"LAPTOPS {SITE}")
    clicked = until(lambda: any(c["tool"] == "marker" for c in calls()), 40)
    check(clicked, "The AI opens the store, clicks and types through Still's MCP tools")
    page = next((t for t in tabs(process) if "/laptops" in t["Url"]), None)
    chat = chats().get(f"LAPTOPS {SITE}", {})
    check(page and page["InChat"] == chat.get("Id") and len(strip(process)) == mine + 1, "Its page opens as a background tab of the chat, and your tabs stay as they were")
    check(js(process, "!!document.querySelector('.page-column.is-split .chat-pane') && !!document.querySelector('.page-column.is-split .page-pane')"), "The chat splits to show its page on the right")
    check(until(lambda: "Pip is working" in (js(process, "document.querySelector('.page-control')?.innerText ?? ''") or ""), 5), "The pill says who's working")
    check(js(process, "[...document.querySelectorAll('.page-control button')].map(b => b.getAttribute('aria-label') || b.innerText.trim()).join('|')") == "Take over|Stop", "The pill offers Take over and Stop")
    cursor = rpc(process, "eval", tab=page["Id"], script="(() => { const h = window[Symbol.for('still.cursor')]; return h ? h[Symbol.for('still.cursor')].tag.textContent : '' })()")
    check(cursor == "Pip", "The AI's cursor shows in the page with its name")
    check(rpc(process, "eval", tab=page["Id"], script="document.querySelector('#q').value") == "laptop", "Typing reached the search field")
    check(rpc(process, "eval", tab=page["Id"], script="location.search") == "?max=800", "The click went through to the page")
    time.sleep(.6)
    capture(process, "split-v01", "screens/hero_split.png")
    done = until(lambda: js(process, "!!document.querySelector('.chat-pane .file-card')"), 30)
    check(done, "The saved file shows as a card in the chat")
    saved = next(PROFILE.glob("library/*/laptops-under-800.csv"), None)
    raw = saved.read_bytes() if saved else b""
    check(raw.startswith(b"\xef\xbb\xbf") and raw.decode("utf-8-sig").count("\n") == 11, "save_file writes the CSV to the Library, with a BOM for Excel")
    check(len(list(PROFILE.glob("library/*/*"))) == 1 and js(process, "document.querySelectorAll('.file-card').length") == 1,
          "Saving the same name again replaces the file and keeps one card")
    bad = next((c for c in calls() if c["tool"] == "save_file" and "evil" in json.dumps(c["args"])), {})
    check(bad and not bad["ok"] and not list(PROFILE.rglob("*.exe")), "save_file refuses other file types and paths outside its folder")
    steps = js(process, "document.querySelector('.chat-pane .ai-steps-group')?.innerText ?? ''") or ""
    check("more actions" in steps and js(process, "document.querySelectorAll('.chat-pane .ai-steps-state.is-done').length > 0")
          and js(process, "document.querySelectorAll('.chat-pane .ai-steps-group .ai-steps-icons > *').length >= 2"), "Steps collapse into one row with stacked icons and a check when done")

    # The chat's details list its files; the viewer opens beside the chat: a sortable grid with a sticky header.
    send(process, "chatPage", on=False)
    until(lambda: not js(process, "!!document.querySelector('.page-column.is-split')"), 5)
    check("laptops-under-800.csv" in (js(process, "document.querySelector('.chat-info')?.innerText ?? ''") or ""), "The chat's details list its files")
    check("Worked for" in (js(process, "document.querySelector('.chat-pane')?.innerText ?? ''") or ""), "A finished chat opened later still says how long it worked")
    time.sleep(.6)
    capture(process, "done-v01", "screens/hero_done.png")
    click(process, ".chat-pane .file-card-open")
    grid = ".page-column.is-viewing .file-view .csv-grid"
    check(until(lambda: js(process, f"document.querySelectorAll('{grid} tbody tr').length") == 10, 10)
          and js(process, f"getComputedStyle(document.querySelector('{grid} th')).position") == "sticky", "In a chat tab the CSV opens beside the chat: 10 rows under a sticky header")
    check(js(process, f"document.querySelector('{grid} tbody td:nth-child(2)')?.innerText") == 'Acer Aspire 5, 15.6"', "Quoted cells keep their commas and quotes")
    click_text(process, ".page-column.is-viewing .csv-col button", "Price")
    check(until(lambda: js(process, f"document.querySelector('{grid} tbody td:nth-child(3)')?.innerText") == "299", 3), "Sorting by price puts the cheapest first")
    capture(process, "viewer-side-v01")
    rpc(process, "key", key="Escape", mods="None")
    check(until(lambda: not js(process, "!!document.querySelector('.page-column.is-viewing')"), 5), "Esc closes the viewer beside the chat")

    # The Library.
    home(process)
    click(process, ".home-rail-item[aria-label=Library]")
    check(until(lambda: js(process, "document.querySelectorAll('.library-list .history-row').length") == 1, 5)
          and "LAPTOPS" in (js(process, "document.querySelector('.library-list')?.innerText ?? ''") or ""), "The Library lists the file with its chat")
    capture(process, "library-v01")


def parallel(process):
    """Two companions at work at once: the panel, take over one, stop one."""
    ask(process, f"SLOW {SITE}/slow-a 60", "pip")
    until(lambda: slow("slow-a"), 20)
    ask(process, f"SLOW {SITE}/slow-b 60", "hazel")
    until(lambda: slow("slow-b"), 20)
    check(until(lambda: running(process) == 2, 10), "Two chats run at once")
    check(not any("slow-" in t["Url"] for t in strip(process)) and js(process, "document.querySelectorAll('.tab-agent').length") == 0, "Neither page joins your tab strip")
    open_menu(process, ".tasks-button")
    items = until(lambda: js(process, "document.querySelectorAll('.tasks-item').length"), 5)
    menu = js(process, "document.querySelector('.tasks-menu')?.innerText ?? ''") or ""
    check(items == 2 and "Working for" in menu, "The running tasks panel lists both, with how long each has worked")
    check(js(process, "document.querySelectorAll('.tasks-menu .tasks-page').length") == 2 and "Move to my tabs" in menu, "Each lists its page, with Watch and Move to my tabs")
    capture(process, "tasks-v01")
    escape(process)
    until(lambda: not js(process, "!!document.querySelector('.tasks-menu')"), 3)

    # Take over Hazel's page (in front): Hazel waits, Pip keeps going.
    b = next(t for t in tabs(process) if "slow-b" in t["Url"])
    check(rpc(process)["activeId"] == next(t["Id"] for t in tabs(process) if t["ChatId"] == b["InChat"]) and "Hazel" in (js(process, "document.querySelector('.page-control')?.innerText ?? ''") or ""),
          "Hazel's chat is in front, with her page and pill beside it")
    click(process, ".page-take")
    check(until(lambda: "You're in control" in (js(process, "document.querySelector('.page-control')?.innerText ?? ''") or ""), 5), "Take over hands you Hazel's page")
    took = time.time()
    time.sleep(2.5)
    check(sum(1 for e in slow("slow-a") if e["ok"] and e["t"] > took) >= 3, "Pip keeps working while you drive Hazel's page")
    check(not any(e["ok"] and e["t"] > took + .5 for e in slow("slow-b")), "Hazel waits while you drive")
    click(process, ".page-take")
    back = time.time()
    check(until(lambda: any(e["ok"] and e["t"] > back for e in slow("slow-b")), 5), "Hand back: Hazel carries on")

    # Stop Hazel from the pill: only Hazel stops and lets go of her tab.
    click(process, ".page-stop")
    stopped = time.time()
    check(until(lambda: running(process) == 1, 10), "Stop ends that chat's run only")
    check(until(lambda: not js(process, "!!document.querySelector('.page-control')"), 5), "Stop lets go of Hazel's page")
    time.sleep(1.5)
    check(sum(1 for e in slow("slow-a") if e["ok"] and e["t"] > stopped) >= 2, "Pip is still at work")

    # Watch Pip's page, then move it into your tabs: Pip keeps working there.
    a = next(t for t in tabs(process) if "slow-a" in t["Url"])
    send(process, "aiHelpPage", id=a["Id"])
    until(lambda: "Pip" in (js(process, "document.querySelector('.page-control')?.innerText ?? ''") or ""), 5)
    before = len(strip(process))
    click(process, ".page-mine")
    moved = until(lambda: next((t for t in tabs(process) if t["Id"] == a["Id"] and not t["InChat"]), None), 5)
    check(moved and rpc(process)["activeId"] == a["Id"] and len(strip(process)) == before + 1, "Move to my tabs puts Pip's page in your tab strip, in front")
    check(until(lambda: "Pip is working" in (js(process, "document.querySelector('.page-control')?.innerText ?? ''") or "")
                and js(process, "document.querySelectorAll('.tab-agent').length") == 1, 5), "Pip keeps working there, with the pill and its mark on the tab")
    time.sleep(.5)
    capture(process, "mine-v01")
    click(process, ".page-stop")
    check(until(lambda: running(process) == 0 and js(process, "document.querySelectorAll('.tab-agent').length") == 0, 10), "Stopping Pip too leaves no agent tabs")


def lookup(process):
    """A question that only needs searching and reading: no tab opens, and the chat shows what it looked at."""
    before = len(tabs(process))
    ask(process, "LOOKUP the best laptop under $800")
    check(until(lambda: "Swift Go 14 is the one" in (js(process, "document.querySelector('.chat-pane')?.innerText ?? ''") or ""), 30), "It answers from searching and reading")
    found = next((c for c in calls() if c["tool"] == "marker" and c["text"].startswith("found")), {})
    check(found.get("text") == "found 3", "web_search returns the search page's results, with links undone")
    chat = chats().get("LOOKUP the best laptop under $800", {})
    check(chat and len(tabs(process)) == before + 1 and not any(t["InChat"] == chat["Id"] for t in tabs(process)), "A search-only question opens no tabs (just its chat)")
    rows = [re.sub(r"\s*·\s*", " · ", re.sub(r"\s+", " ", row)).strip() for row in js(process, "[...document.querySelectorAll('.chat-pane .ai-look')].map(r => r.innerText)") or []]
    check(len(rows) == 2 and rows[0].startswith("Searched “laptop reviews under 800” · 3 results") and rows[1].startswith("Read 127.0.0.1"), "The chat shows one row per search and per page read")
    click(process, ".chat-pane details.ai-look summary")
    check(until(lambda: js(process, "document.querySelectorAll('.chat-pane .ai-look[open] li').length") == 3, 3), "Opening the search row lists its results")
    check(js(process, "!!document.querySelector('.chat-pane .md-table table') && !!document.querySelector('.chat-pane .md-draft button')"), "The answer has a clean table and a draft with its own Copy button")
    check(js(process, "document.querySelectorAll('.chat-pane .ai-next-step').length") == 3, "It ends with three next steps to pick from")
    time.sleep(.5)
    capture(process, "lookup-v01")


def hand_over(process):
    """Hand a tab of yours to a companion: it leaves the strip and opens beside its chat; Move to my tabs brings it back."""
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 20)
    send(process, "navigate", url=SITE + "/reviews/best")
    tab = until(lambda: next((t for t in tabs(process) if t["Url"].endswith("/reviews/best") and not t["InChat"] and not t["Loading"]), None), 15)
    before = len(strip(process))
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    send(process, "tabHand", id=tab["Id"], companion="pip")
    given = until(lambda: next((t for t in tabs(process) if t["Id"] == tab["Id"] and t["InChat"]), None), 5)
    check(given and len(strip(process)) == before, "Hand to Pip moves the tab into a chat (the chat takes its place in the strip)")
    check(until(lambda: js(process, "!!document.querySelector('.page-column.is-split .page-pane')"), 5) and "Best laptops" in (js(process, "document.querySelector('.page-nav-url')?.innerText ?? ''") or ""),
          "The chat opens with your page beside it")
    click(process, ".page-mine")
    check(until(lambda: next((t for t in tabs(process) if t["Id"] == tab["Id"] and not t["InChat"]), None), 5) and rpc(process)["activeId"] == tab["Id"], "Move to my tabs gives it back")


def outside_app(process):
    """Other AI apps keep their tabs in the strip, unless they ask for a background tab."""
    app = Mcp(EXE, "Outside", PROFILE)
    try:
        before = len(strip(process))
        ok, _ = app.call("open_tab", url=SITE + "/reviews/slim-3")
        check(ok and until(lambda: len(strip(process)) == before + 1, 5), "An AI app's open_tab still opens a tab in the strip")
        ok, _ = app.call("open_tab", url=SITE + "/reviews/swift-go", background=True)
        hidden = until(lambda: next((t for t in tabs(process) if t["Url"].endswith("/swift-go") and t["InChat"]), None), 5)
        check(ok and hidden and len(strip(process)) == before + 1, "With background: true it opens out of sight")
        open_menu(process, ".tasks-button")
        check(until(lambda: "swift-go" in (js(process, "document.querySelector('.tasks-menu .tasks-page.is-app span')?.title ?? ''") or ""), 5), "The running tasks panel lists it")
        click_text(process, ".tasks-menu .tasks-page.is-app button", "Move to my tabs")
        check(until(lambda: next((t for t in tabs(process) if t["Id"] == hidden["Id"] and not t["InChat"]), None), 5) and len(strip(process)) == before + 2, "Move to my tabs brings it into the strip")
        escape(process)
    finally:
        app.proc.kill()


def queue_and_question(process):
    """A follow-up waits while the AI works; Send now interrupts; a question can be answered from the panel."""
    ask(process, f"SLOW {SITE}/slow-c 30")
    until(lambda: slow("slow-c"), 20)
    until(lambda: js(process, "!!document.querySelector('.chat-pane textarea')"), 5)
    send(process, "aiSend", text="ASK please")
    check(until(lambda: "ASK please" in (js(process, "document.querySelector('.ai-queued')?.innerText ?? ''") or ""), 5), "A message sent while it works waits as Up next")
    check(js(process, "document.querySelector('.chat-pane textarea')?.placeholder") == "Add to what's up next…", "The box says it adds to what's up next")
    click(process, ".ai-queued [data-slot=button]")
    check(until(lambda: js(process, "!!document.querySelector('.ask-card')"), 20), "Send now stops the run and sends the follow-up, which asks a question")
    check(until(lambda: js(process, "!!document.querySelector('.tasks-button .is-needs')"), 5), "The running tasks button shows that a chat needs you")
    time.sleep(.5)
    capture(process, "question-v01", "screens/hero_question.png")
    open_menu(process, ".tasks-button")
    until(lambda: js(process, "!!document.querySelector('.tasks-ask button')"), 5)
    click_text(process, ".tasks-ask button", "15 inch")
    check(until(lambda: "You picked" in (js(process, "document.querySelector('.chat-pane')?.innerText ?? ''") or ""), 15)
          and "15 inch" in (js(process, "document.querySelector('.chat-pane')?.innerText ?? ''") or ""), "Answering in the panel reaches the AI")
    escape(process)


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
