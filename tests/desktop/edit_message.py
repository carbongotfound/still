"""Edit, Reset and Copy on your own messages. Only the latest prompt can be edited or reset; either one stops what's
running, forgets the reply and what it saved, and runs the message again on a new session. A fake app stands in for the
AI; with --live, one short real run on Claude Haiku shows the reply really is forgotten.

Run: python tests/desktop/edit_message.py artifacts/Still-QA/Still.exe [--live]
Out: artifacts/edit-message-*/
"""
import base64
import http.server
import json
import os
from pathlib import Path
import shutil
import sys
import textwrap
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, press_ready, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
LIVE = "--live" in sys.argv
RUN = ROOT / "artifacts" / ("edit-message-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []
HITS = []
FAKE = textwrap.dedent(r'''
    import base64, json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt, "args": args}) + "\n")
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
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    tail = prompt[-1500:]
    plan = re.search(r"TOOLS64: (\S+)\s*$", tail)
    for name, a in json.loads(base64.b64decode(plan.group(1))) if plan else []:
        got = request("tools/call", {"name": name, "arguments": a})
        with open(os.path.join(here, "replies.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps([name, got]) + "\n")
    if "SLOW" in tail:
        open(os.path.join(here, "slow-started"), "w").close()
        time.sleep(40)
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Answered " + re.findall(r"WORD\w+", tail)[-1] if "WORD" in tail else "Done."}]}})
    still.stdin.close()
''')


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>Button</title><button id=go onclick=\"fetch('/hit')\">Go on</button>"
        if self.path == "/hit":
            HITS.append(self.path)
            body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def plan(word, *steps):
    return f"{word} TOOLS64: " + base64.b64encode(json.dumps(list(steps)).encode()).decode()


def prompts():
    file = BIN / "prompts.jsonl"
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def said(p):
    return js(p, "[...document.querySelectorAll('.ai-msg, .ai-turn, .ai-stopped')].map(m => m.innerText.trim())") or []


def mine(p):
    """Your messages, oldest first, and the buttons each one has."""
    return js(p, "[...document.querySelectorAll('.ai-msg.is-user:not(.is-teammate)')].map(m => [...m.querySelectorAll('.ai-msg-actions button')].map(b => b.getAttribute('aria-label')))") or []


def running(p):
    return js(p, "document.querySelector('.tasks-button')?.getAttribute('aria-label')?.match(/[1-9]\\d* running/) != null")


def idle(p, seconds=60):
    return until(lambda: not running(p), seconds)


def chat(p):
    state = json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    return next(c for c in state if any("WORDONE" in m["Text"] for m in c["Messages"]))


def press(p, label):
    return js(p, f"(b => {{ b?.click(); return !!b }})([...document.querySelectorAll('.ai-msg.is-user:not(.is-teammate) [aria-label=\"{label}\"]')].at(-1))")


def press_word(p, word):
    return js(p, f"(b => {{ b?.click(); return !!b }})([...document.querySelectorAll('.ai-msg-actions button, .ai-edit-actions button')].find(b => b.innerText.trim() === {json.dumps(word)}))")


def edit_to(p, words):
    press(p, "Edit message")
    until(lambda: js(p, "!!document.querySelector('.ai-edit-box')"), 5)
    js(p, f"(t => {{ t.focus(); t.select(); document.execCommand('insertText', false, {json.dumps(words)}) }})(document.querySelector('.ai-edit-box'))")
    time.sleep(.2)
    press_word(p, "Send")


def fake_run(p, port):
    send(p, "new")
    until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 15)
    time.sleep(.4)
    send(p, "aiSend", text="WORDONE first question", home=True, companion="maya")
    check(until(lambda: any("Answered WORDONE" in t for t in said(p)), 30), "The first message gets its reply")
    idle(p)
    send(p, "aiSend", text="WORDTWO second question")
    check(until(lambda: any("Answered WORDTWO" in t for t in said(p)), 30), "The second one too")
    idle(p)
    time.sleep(.3)
    buttons = mine(p)
    check(buttons[0] == ["Copy message"], f"An earlier message can only be copied ({buttons})")
    check(buttons[-1] == ["Copy message", "Edit message", "Reset message"], "The latest prompt can also be edited and reset")

    first_session = chat(p)["Session"]
    runs = len(prompts())

    # Edit, then change your mind: nothing happens.
    press(p, "Edit message")
    until(lambda: js(p, "!!document.querySelector('.ai-edit-box')"), 5)
    note = js(p, "document.querySelector('.ai-edit-note')?.innerText") or ""
    check("replaces the reply" in note and "stays done" in note, f"Editing says what it replaces and what it can't undo ({note!r})")
    check(js(p, "document.querySelector('.ai-edit-box').value") == "WORDTWO second question", "The box starts with what you wrote")
    press_word(p, "Cancel")
    time.sleep(.5)
    check(len(prompts()) == runs and any("Answered WORDTWO" in t for t in said(p)), "Cancel changes nothing")

    # Edit: the reply is forgotten, here and by the AI.
    edit_to(p, "WORDTHREE changed question")
    check(until(lambda: any("Answered WORDTHREE" in t for t in said(p)), 30), "An edited message runs again")
    idle(p)
    time.sleep(.5)
    text = "\n".join(said(p))
    check("WORDTWO" not in text, f"The old message and its reply are gone ({text!r})")
    check("WORDONE" in text, "What came before stays")
    got = prompts()[-1]
    check("--resume" not in got["args"] and "WORDTWO" not in got["prompt"], "The AI starts a new session, without the old message or reply")
    check("WORDONE" in got["prompt"], "It's told what came before")
    saved = chat(p)
    check(saved["Session"] != first_session and not any("WORDTWO" in m["Text"] for m in saved["Messages"]), "The saved chat forgot them too")

    # Reset: the same message again, once you say so.
    runs = len(prompts())
    press(p, "Reset message")
    until(lambda: press_word(p, "Cancel"), 3)
    time.sleep(.3)
    check(len(prompts()) == runs, "Reset asks first")
    press(p, "Reset message")
    until(lambda: js(p, "!!document.querySelector('.is-resetting')"), 3)
    press_word(p, "Reset")
    check(until(lambda: len(prompts()) == runs + 1, 30), "Reset runs the message again")
    idle(p)
    time.sleep(.3)
    check(sum("WORDTHREE changed" in t for t in said(p)) == 1, "...with one copy of it in the chat")

    # Editing while it works stops the work first.
    send(p, "aiSend", text="WORDFOUR SLOW task")
    check(until((BIN / "slow-started").exists, 30), "A slow task starts")
    until(lambda: running(p), 5)
    edit_to(p, "WORDFIVE instead")
    check(until(lambda: any("Answered WORDFIVE" in t for t in said(p)), 30), "Editing while it works runs the new message")
    idle(p)
    time.sleep(.5)
    text = "\n".join(said(p))
    check("WORDFOUR" not in text and "You stopped it here" not in text, f"The stopped run leaves nothing behind ({text!r})")

    # What the replaced reply saved goes. What was saved before stays.
    send(p, "aiSend", text=plan("WORDSIX", ["remember", {"fact": "Likes the color teal"}]))
    idle(p)
    memory = PROFILE / "companions" / "maya" / "memory.json"
    facts = lambda: json.loads(memory.read_text(encoding="utf-8")) if memory.exists() else []
    check(until(lambda: any("teal" in f["Text"] for f in facts()), 5), "A turn saves a memory")
    send(p, "aiSend", text=plan("WORDSEVEN", ["remember", {"fact": "Likes the color amber"}]))
    idle(p)
    check(until(lambda: any("amber" in f["Text"] for f in facts()), 5), "The next turn saves another")
    edit_to(p, "WORDEIGHT no memories")
    check(until(lambda: any("Answered WORDEIGHT" in t for t in said(p)), 30), "Edit that one")
    idle(p)
    words = [f["Text"] for f in facts()]
    check(not any("amber" in w for w in words) and any("teal" in w for w in words), f"What the replaced reply saved is gone, and only that ({words})")

    # What it was allowed in this chat is asked again, and nothing is repeated on its own.
    url = f"http://127.0.0.1:{port}/page"
    click = plan("WORDNINE", ["open_tab", {"url": url}], ["click", {"selector": "#go"}])
    send(p, "aiSend", text=click)
    allow = "[...document.querySelectorAll('.approve-card button')].find(b => b.innerText.trim() === 'Allow in this chat')"
    check(press_ready(p, allow, 30), "The click asks")
    check(until(lambda: len(HITS) == 1, 15), "...and happens once you allow it")
    idle(p)
    press(p, "Reset message")
    until(lambda: js(p, "!!document.querySelector('.is-resetting')"), 3)
    press_word(p, "Reset")
    check(until(lambda: js(p, f"!!{allow}"), 30), f"Run again, it asks again ({(BIN / 'replies.jsonl').read_text(encoding='utf-8')[-900:] if not js(p, f'!!{allow}') else ''})")
    time.sleep(1)
    check(len(HITS) == 1, "Nothing was clicked again before you answered")
    def deny():
        js(p, "[...document.querySelectorAll('.approve-card button')].find(b => b.innerText.trim() === 'Deny')?.click()")
        return not running(p) and not js(p, "!!document.querySelector('.approve-card')")
    check(until(deny, 30, .5), "Deny ends the run")
    check(len(HITS) == 1, "...and leaves it at one")

    # An answer to the AI's question isn't a prompt to edit.
    send(p, "aiSend", text=plan("WORDTEN", ["ask_user", {"question": "Which one?"}]))
    check(until(lambda: "Which one?" in (js(p, "document.querySelector('[aria-label=\"Question from your AI\"]')?.innerText") or ""), 20), "The AI asks its question")
    send(p, "aiAnswer", text="The blue one")
    check(until(lambda: any("Answered WORDTEN" in t for t in said(p)), 30), "The AI gets its answer")
    idle(p)
    time.sleep(.3)
    buttons = mine(p)
    check(buttons[-1] == ["Copy message"] and buttons[-2] == ["Copy message", "Edit message", "Reset message"], f"Your answer to its question can't be edited, your prompt can ({buttons[-2:]})")
    edit_to(p, "WORDELEVEN plain")
    check(until(lambda: any("Answered WORDELEVEN" in t for t in said(p)), 30), "Editing goes back to your prompt")
    idle(p)
    check("The blue one" not in "\n".join(said(p)), "...and the answer goes with it")

    # A second window or a stale press: only what you were looking at.
    runs = len(prompts())
    send(p, "aiEdit", was="WORDONE first question", text="WORDBAD")
    time.sleep(1)
    check(len(prompts()) == runs and not any("WORDBAD" in t for t in said(p)), "An earlier message can't be edited, whatever asks")


def live_run(p):
    """A short real run on Claude Haiku: after an edit, the old message and reply really are forgotten."""
    send(p, "aiCheck")
    time.sleep(3)
    send(p, "aiAdvanced", on=True)
    send(p, "aiModel", harness="claude", model="haiku")
    send(p, "new")
    until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 15)
    time.sleep(.4)
    send(p, "aiSend", text="Reply with only this word: MAROON", home=True, companion="maya")
    check(until(lambda: any("MAROON" in t and "Reply with" not in t for t in said(p)), 150, .5), "Live: Claude answers the first message")
    idle(p, 120)
    edit_to(p, "Reply with only this word: OLIVE")
    check(until(lambda: any("OLIVE" in t and "Reply with" not in t for t in said(p)), 150, .5), "Live: the edited message gets a new answer")
    idle(p, 120)
    check("MAROON" not in "\n".join(said(p)), "Live: the old message and reply are gone from the chat")
    send(p, "aiSend", text="Without using any tools: list every color word that has come up in this chat so far, in capitals, and nothing else.")
    until(lambda: running(p), 10)
    idle(p, 150)
    last = (said(p) or [""])[-1]
    check("OLIVE" in last.upper() and "MAROON" not in last.upper(), f"Live: Claude itself has forgotten the old message ({last[:120]!r})")


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state = {"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "claude" if LIVE else "fake"},
             "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}
    if not LIVE:
        (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
        launcher(BIN / "fakeagent", BIN / "fake_agent.py")
        (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
            "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps(state))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        (live_run(p) if LIVE else fake_run(p, server.server_port))
        errors = rpc(p).get("shellErrors")
        check(not errors, f"No interface errors ({errors})" if errors else "No interface errors")
    except Exception as ex:
        check(False, f"The run finished ({type(ex).__name__}: {ex})")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
        server.shutdown()
    if FAILED:
        print(f"FAILED {len(FAILED)}: {FAILED} -> {RUN}")
    else:
        print("PASSED")
        shutil.rmtree(RUN, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
