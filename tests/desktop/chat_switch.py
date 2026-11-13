"""Switching chats: each opens at its end (where a running chat's live step is), or where you scrolled up to in it
yourself, in the side panel and on the full chat page alike. A run keeps going in the background through chat, page and
tab switches, a sign-in handoff and an interface reload. Each tab's side panel keeps its own chat: another chat opened
full-page in another tab, or working there, never changes it, and a chat at work in a tab only shows in that tab's panel
when it had no chat yet. A run that dies says so, with Continue. A fake app stands in for the AI.

Run: python tests/desktop/chat_switch.py artifacts/Still-QA/Still.exe
Out: artifacts/chat-switch-*/
"""
import http.server
import json
from pathlib import Path
import re
import shutil
import sys
import textwrap
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("chat-switch-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []
FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(prompt) + "\n")
    tail = prompt[-1500:]
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if "CRASH" in tail and "stopped before you finished" not in tail:
        sys.stderr.write("boom, the fake app fell over\n"); sys.exit(3)
    work = re.search(r"STEPS(\d+) (\S+)", tail)
    if work:
        # Works in a tab of its own: a step each second, and a sign-in page at step 5.
        server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
        still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        n = 0
        def request(name, a):
            global n
            n += 1
            still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": n, "method": name, "params": a}) + "\n").encode()); still.stdin.flush()
            for line in still.stdout:
                try: m = json.loads(line)
                except ValueError: continue
                if m.get("id") == n:
                    with open(os.path.join(here, "replies.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps([name, a, m]) + "\n")
                    return m
        request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
        still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
        def step(i, name, a, tool, targs):
            say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t%d" % i, "name": name, "input": a}]}})
            request("tools/call", {"name": tool, "arguments": targs})
            say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t%d" % i}]}})
        url = work.group(2)
        step(0, "mcp__still__open_tab", {"url": url + "work"}, "open_tab", {"url": url + "work", "background": False})
        open(os.path.join(here, "work-started"), "w").close()
        for i in range(1, int(work.group(1)) + 1):
            if i == 5: step(100, "mcp__still__navigate", {"url": url + "login"}, "navigate", {"url": url + "login"})
            step(i, "check_step", {"text": str(i)}, "read_page", {})
            time.sleep(1)
        still.stdin.close()
    slow = re.search(r"SLOW(\d+)", tail)
    if slow:
        open(os.path.join(here, "slow-started"), "w").close()
        time.sleep(int(slow.group(1)))
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Answered " + re.findall(r"WORD\w+", tail)[-1] if "WORD" in tail else "Done."}]}})
''')
PANEL, PAGE = ".ai-sidebar .ai-log", ".chat-view[data-mode=tab] .ai-log"


class Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (b"<!doctype html><title>Sign in</title><form><input name=user><input type=password name=pass></form>" if self.path == "/login"
                else b"<!doctype html><title>Work</title><p>The page the chat works on.</p>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        FAILED.append(label)


def long_chat(id, title):
    words = "The lamp throws a warm light across the desk, with no glare on the screen and a base that stays put. "
    messages = []
    for n in range(30):
        messages += [{"Role": "user", "Text": f"{title} question {n}"}, {"Role": "assistant", "Text": f"{title} answer {n}. " + words * 4}]
    return {"Id": id, "Title": title, "Harness": "fake", "Companion": "maya", "Updated": "2026-11-01T10:00:00Z", "Messages": messages}


def where(p, view):
    """The view's scroll: how far down, how far it goes, and whether the live step is in sight."""
    return json.loads(js(p, f"""(el => el ? JSON.stringify({{ top: Math.round(el.scrollTop), end: Math.round(el.scrollHeight - el.clientHeight),
        live: (l => !!l && l.getBoundingClientRect().top >= el.getBoundingClientRect().top - 1 && l.getBoundingClientRect().bottom <= el.getBoundingClientRect().bottom + 1)(el.querySelector('.ai-live')) }}) : 'null')(document.querySelector('{view}'))""") or "null")


def at_end(w):
    return bool(w) and w["end"] > 400 and w["end"] - w["top"] < 8


def shows(p, view, title):
    return js(p, f"(el => !!el && el.innerText.includes({json.dumps(title + ' answer 29')}))(document.querySelector('{view}'))")


def open_in_panel(p, id, title):
    send(p, "aiOpenChat", id=id)
    ok = until(lambda: shows(p, PANEL, title), 10)
    time.sleep(.6)
    return ok


def progress(p, view):
    """How far the run in view has got: its highest step, its timer's seconds, and whether it shows as working."""
    return json.loads(js(p, f"""(el => el ? JSON.stringify({{ step: Math.max(0, ...[...el.querySelectorAll('.ai-step-text')].map(e => +((e.textContent.match(/check step (\\d+)/) || [0, 0])[1]))),
        timer: el.querySelector('.ai-timer')?.textContent ?? '', live: !!el.querySelector('.ai-live') }}) : 'null')(document.querySelector('{view}'))""") or "null")


def seconds(timer):
    m = re.search(r"(?:(\d+)m )?(\d+)s", timer or "")
    return int(m.group(1) or 0) * 60 + int(m.group(2)) if m else -1


def prompts(word):
    f = BIN / "prompts.jsonl"
    return [p for p in map(json.loads, f.read_text(encoding="utf-8").splitlines()) if word in p] if f.exists() else []


def scroll_to(p, view, top):
    """As the user would: the view moves, and its scroll event follows."""
    js(p, f"document.querySelector('{view}').scrollTop = {top}")
    time.sleep(.4)


def main():
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    BIN.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([long_chat("lamps", "Lamps"), long_chat("chairs", "Chairs")]))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake", "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        send(p, "aiToggle")
        until(lambda: js(p, f"!!document.querySelector('{PANEL}')"), 10)

        check(open_in_panel(p, "lamps", "Lamps") and at_end(where(p, PANEL)), f"A chat opens in the side panel at its end ({where(p, PANEL)})")
        scroll_to(p, PANEL, 300)
        check(open_in_panel(p, "chairs", "Chairs") and at_end(where(p, PANEL)), f"Having scrolled up in another chat, the next one still opens at its end ({where(p, PANEL)})")
        check(open_in_panel(p, "lamps", "Lamps") and abs(where(p, PANEL)["top"] - 300) <= 2, f"Back to the first, it's where you scrolled up to ({where(p, PANEL)})")

        send(p, "chatOpen", id="lamps")
        # The page is wider than the panel: rows settle as it opens, and the row in view stays put, a few pixels off 300.
        check(until(lambda: shows(p, PAGE, "Lamps"), 10) and until(lambda: abs((where(p, PAGE) or {"top": -99})["top"] - 300) <= 12, 3), f"...and on its full chat page too ({where(p, PAGE)})")
        scroll_to(p, PAGE, 10 ** 6)
        send(p, "chatOpen", id="chairs")
        check(until(lambda: shows(p, PAGE, "Chairs"), 10) and until(lambda: at_end(where(p, PAGE)), 3), f"The other chat's page opens at its end ({where(p, PAGE)})")
        send(p, "chatOpen", id="lamps")
        check(until(lambda: shows(p, PAGE, "Lamps"), 10) and until(lambda: at_end(where(p, PAGE)), 3), f"Scrolled back down to its end, the first opens there again ({where(p, PAGE)})")

        # A running chat opens at its live step, however often you go away and come back.
        send(p, "new", url="about:blank")
        time.sleep(1)
        if not js(p, f"!!document.querySelector('{PANEL}')"):
            send(p, "aiToggle")
        open_in_panel(p, "chairs", "Chairs")
        # As a run starts, WebKit's layout can nudge the view up a few pixels while rows come in: that isn't the user
        # reading further up, so the chat still follows its end (it stopped short and stayed there).
        js(p, f"""(el => {{ el.scrollTop -= 2; const d = document.createElement('div'); d.id = 'qa-grow'; d.style.height = '160px'; el.firstElementChild.append(d) }})(document.querySelector('{PANEL}'))""")
        time.sleep(.8)
        w = where(p, PANEL)
        js(p, "document.getElementById('qa-grow')?.remove()")
        check(at_end(w), f"Nudged up 2 px as rows come in, the chat still follows its end ({w})")
        time.sleep(.5)
        send(p, "aiSend", text="WORDRUN SLOW25", companion="maya")
        check(until(lambda: (BIN / "slow-started").exists(), 30) and until(lambda: where(p, PANEL)["live"], 10), f"The chat works, its live step in sight ({where(p, PANEL)})")
        for n in range(3):
            open_in_panel(p, "lamps", "Lamps")
            check(at_end(where(p, PANEL)), f"Away {n + 1}: the other chat opens at its end ({where(p, PANEL)})")
            open_in_panel(p, "chairs", "Chairs")
            w = where(p, PANEL)
            check(at_end(w) and w["live"], f"Back {n + 1}: the running chat opens at its live step ({w})")
        check(until(lambda: shows(p, PANEL, "Answered WORDRUN") or "Answered WORDRUN" in (js(p, f"document.querySelector('{PANEL}').innerText") or ""), 40), "The run finishes")
        time.sleep(1)
        check(at_end(where(p, PANEL)), f"...with its answer in sight ({where(p, PANEL)})")
        open_in_panel(p, "lamps", "Lamps")
        open_in_panel(p, "chairs", "Chairs")
        check(at_end(where(p, PANEL)), f"The chat's own scrolling to its answer isn't kept as yours ({where(p, PANEL)})")

        # A run keeps going through chat, page and tab switches, a sign-in handoff and an interface reload. The tab it
        # works in had no chat in its side panel, so the panel shows it there.
        site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=site.serve_forever, daemon=True).start()
        mine = rpc(p)["activeId"]
        open_in_panel(p, "chairs", "Chairs")
        send(p, "aiSend", text=f"WORDWORK STEPS40 http://127.0.0.1:{site.server_port}/", companion="maya")
        check(until(lambda: (BIN / "work-started").exists(), 30), "The chat starts work in a tab of its own")
        work = next((t["Id"] for t in rpc(p)["tabs"] if t.get("RunChat") == "chairs"), None)
        check(work is not None and work != mine, f"...a tab beside yours ({[(t['Id'], t.get('RunChat')) for t in rpc(p)['tabs']]})")
        send(p, "select", id=mine)
        open_in_panel(p, "lamps", "Lamps")
        check(until(lambda: rpc(p)["activeId"] == mine, 5) and shows(p, PANEL, "Lamps"), "You go back to your own tab and another chat")
        signin = until(lambda: any("sign-in page" in json.dumps(r[2]) for r in map(json.loads, (BIN / "replies.jsonl").read_text(encoding="utf-8").splitlines())) if (BIN / "replies.jsonl").exists() else False, 30)
        check(signin and until(lambda: rpc(p)["activeId"] == work, 5), "A sign-in page brings the chat's tab to the front")
        check(until(lambda: shows(p, PANEL, "Chairs"), 5) and (progress(p, PANEL) or {}).get("live"), f"...and its side panel, which had no chat, shows the chat at work there ({progress(p, PANEL)})")
        last, timer = progress(p, PANEL) or {"step": 0}, 0
        for n in range(3):
            send(p, "select", id=mine)
            check(until(lambda: rpc(p)["activeId"] == mine, 5) and until(lambda: shows(p, PANEL, "Lamps"), 3), f"Away {n + 1}: your tab, its own chat in the panel")
            time.sleep(1.5)
            send(p, "select", id=work)
            ok = until(lambda: rpc(p)["activeId"] == work and shows(p, PANEL, "Chairs"), 5)
            now = progress(p, PANEL) or {}
            check(ok and now.get("live") and now["step"] >= last["step"] and seconds(now["timer"]) > timer, f"Back {n + 1} to the chat's tab: the panel shows it, still working, nothing lost ({last} -> {now})")
            last, timer = now, seconds(now["timer"])
        send(p, "chatOpen", id="chairs")
        check(until(lambda: shows(p, PAGE, "Chairs") and (progress(p, PAGE) or {}).get("live"), 10) and progress(p, PAGE)["step"] >= last["step"] and seconds(progress(p, PAGE)["timer"]) >= timer,
              f"Its full chat page shows the same live run ({progress(p, PAGE)})")
        send(p, "agentTakeOver", on=False, key="chairs")
        check(until(lambda: (progress(p, PAGE) or {"step": 0})["step"] > last["step"], 50), f"Signed in and handed back, the run carries on ({last} -> {progress(p, PAGE)})")
        send(p, "select", id=work)
        check(until(lambda: shows(p, PANEL, "Chairs") and (progress(p, PANEL) or {}).get("live"), 10), f"From its page back to its tab: the panel shows it working ({progress(p, PANEL)})")
        before = progress(p, PANEL)
        js(p, "setTimeout(() => location.reload(), 50); 1")
        time.sleep(1)
        check(until(lambda: shows(p, PANEL, "Chairs") and (progress(p, PANEL) or {}).get("live"), 20) and progress(p, PANEL)["step"] >= before["step"] and seconds(progress(p, PANEL)["timer"]) >= seconds(before["timer"]),
              f"After the interface reloads, it's still working, steps and timer intact ({before} -> {progress(p, PANEL)})")
        check(until(lambda: "Answered WORDWORK" in (js(p, f"document.querySelector('{PANEL}')?.innerText ?? ''") or ""), 90), "The run finishes")
        done = progress(p, PANEL) or {"step": 0}
        check(done["step"] == 40 and len(prompts("STEPS40")) == 1, f"...with all 40 steps, from one start: never restarted ({done}, {len(prompts('STEPS40'))} starts)")
        site.shutdown()

        # Each tab's side panel keeps its own chat: another chat opened full-page in another tab, and working there in the
        # background, never changes it.
        send(p, "select", id=mine)
        check(until(lambda: rpc(p)["activeId"] == mine, 5) and open_in_panel(p, "lamps", "Lamps"), "Your tab's side panel on one chat")
        send(p, "chatOpen", id="chairs", newTab=True)
        check(until(lambda: shows(p, PAGE, "Chairs"), 10) and rpc(p)["activeId"] != mine, "Another chat opens full-page in another tab")
        page = rpc(p)["activeId"]
        (BIN / "slow-started").unlink(missing_ok=True)
        send(p, "aiSend", text="WORDBACK SLOW20", companion="maya")
        check(until(lambda: (BIN / "slow-started").exists(), 30), "...and works there")
        for n in range(5):
            send(p, "select", id=mine)
            ok = until(lambda: rpc(p)["activeId"] == mine, 5) and until(lambda: shows(p, PANEL, "Lamps"), 3)
            time.sleep(.4)
            check(ok and shows(p, PANEL, "Lamps") and not shows(p, PANEL, "Chairs"), f"Back to your tab {n + 1}: its panel still shows its own chat, with the other at work in the background")
            send(p, "select", id=page)
            until(lambda: rpc(p)["activeId"] == page, 5)
            time.sleep(.4)
        check(until(lambda: "Answered WORDBACK" in (js(p, f"document.querySelector('{PAGE}')?.innerText ?? ''") or ""), 40), "The background run finishes")
        send(p, "select", id=mine)
        check(until(lambda: rpc(p)["activeId"] == mine, 5) and until(lambda: shows(p, PANEL, "Lamps"), 3), "...and your tab's panel still shows its own chat")

        # A run that dies says so in the chat, with Continue.
        open_in_panel(p, "lamps", "Lamps")
        send(p, "aiSend", text="WORDBOOM CRASH", companion="maya")
        error = lambda: js(p, "document.querySelector('.ai-sidebar .ai-error')?.innerText ?? ''") or ""
        check(until(lambda: error().startswith("Stopped: ") and "boom" in error(), 20), f"A run whose app quits says Stopped, and why ({error()!r})")
        check(js(p, "[...document.querySelectorAll('.ai-sidebar .ai-error button')].some(b => b.textContent.trim() === 'Continue')"), "...with a Continue button")
        js(p, "[...document.querySelectorAll('.ai-sidebar .ai-error button')].find(b => b.textContent.trim() === 'Continue').click()")
        check(until(lambda: any("stopped before you finished" in q for q in prompts("")), 20), "Continue starts it again, told why it stopped")
        check(until(lambda: not error() and "Done." in (js(p, f"document.querySelector('{PANEL}')?.innerText ?? ''") or ""), 20), f"...and it answers, the error gone ({error()!r})")

        errors = rpc(p).get("shellErrors")
        check(not errors, f"No interface errors ({errors})" if errors else "No interface errors")
    except Exception as ex:
        check(False, f"The run finished ({type(ex).__name__}: {ex})")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
    if FAILED:
        print(f"FAILED {len(FAILED)}: {FAILED} -> {RUN}")
    else:
        print("PASSED")
        shutil.rmtree(RUN, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
