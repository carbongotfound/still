"""A plugin's programs: a companion runs them with run_plugin_program, and Settings decides whether Still asks first.

A companion with a plugin's skill gets its programs from load_skill and runs one with its arguments: the card asks first
(Deny, Always for this plugin, Allow once) and shows where the plugin came from; Deny refuses it, Allow once runs it with
CLAUDE_PLUGIN_ROOT set and its output and exit code coming back, and Always for this plugin stops asking for that one.
Setup always asks, says it runs at your own risk and has no Always. A path outside the plugin, a file that isn't a
program and a plugin the companion doesn't have are refused without a card. A program that runs too long is stopped.
A companion on Keep going runs them without a card; back on Balanced, after Reset all, it asks again.
Deleting the plugin's last skill deletes its folder.

Usage: python tests/desktop/plugin_programs.py <QA exe>
The fake AI app answers a last line "CALLS: <json list of [tool, arguments]>" by calling each tool in turn through
Still's MCP server and writing each result to results.jsonl as it comes.
"""
import json
import shutil
import sys
import textwrap
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, launcher, press_ready, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("plugprog-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
PLUGIN = PROFILE / "plugins" / "video"
FAILED = []

FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    last = next((l for l in reversed(prompt.strip().splitlines()) if l.strip()), "")
    if last.startswith("CALLS: "):
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
        tools = [t["name"] for t in request("tools/list", {})["result"]["tools"]]
        for tool, arguments in json.loads(last[7:]):
            r = request("tools/call", {"name": tool, "arguments": arguments})["result"]
            with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"tool": tool, "tools": tools, "error": bool(r.get("isError")), "text": r["content"][0].get("text", "")}) + "\n")
        still.stdin.close()
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}})
''')

HELLO = "import os, sys\nprint('hello ' + ' '.join(sys.argv[1:]))\nprint('root ' + os.environ.get('CLAUDE_PLUGIN_ROOT', ''))\nsys.exit(3 if 'fail' in sys.argv else 0)\n"
SETUP = "print('set up')\n"
SLOW = "import time\ntime.sleep(60)\nprint('woke')\n"


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def results():
    f = BIN / "results.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def calls(p, cid, todo):
    """Sends one message with these tool calls and returns how many results there were before."""
    before = len(results())
    if cid is None:
        known = {c["Id"] for c in chats()}
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        send(p, "aiSend", text="CALLS: " + json.dumps(todo), home=True, companion="maya")
        cid = until(lambda: next((c["Id"] for c in chats() if c["Id"] not in known), None), 20)
    else:
        send(p, "aiSend", text="CALLS: " + json.dumps(todo))
    return cid, before


def got(before, n, seconds=30):
    """The results after before, once there are n of them."""
    return until(lambda: (r := results()[before:]) and len(r) >= n and r, seconds) or results()[before:]


def card(p):
    return until(lambda: js(p, "(c => c && { text: c.innerText, buttons: [...c.querySelectorAll('.approve-actions button')].map(b => b.innerText.trim()) })(document.querySelector('.chat-view .approve-card'))"), 20) or {}


def press(p, words):
    return press_ready(p, f"[...document.querySelectorAll('.chat-view .approve-card .approve-actions button')].find(b => b.innerText.trim() === {json.dumps(words)})")


def idle(p, cid):
    return until(lambda: (c := next((c for c in chats() if c["Id"] == cid), None)) and not c.get("Running"), 30)


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "skills").mkdir(parents=True)
    (PROFILE / "skills" / "watch.md").write_text("---\nname: Watch\ndescription: Watches a video\nwhen: A video link\nsource: github.com/acme/video\nplugin: video\n---\n\n"
                                                 "Run python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/hello.py\" <link>.\n", encoding="utf-8")
    (PLUGIN / "scripts").mkdir(parents=True)
    (PLUGIN / "scripts" / "hello.py").write_text(HELLO, encoding="utf-8")
    (PLUGIN / "scripts" / "setup.py").write_text(SETUP, encoding="utf-8")
    (PLUGIN / "scripts" / "slow.py").write_text(SLOW, encoding="utf-8")
    (PLUGIN / "notes.txt").write_text("not a program", encoding="utf-8")
    (PROFILE / "plugins" / "other").mkdir()
    (PROFILE / "plugins" / "other" / "x.py").write_text("print('other')\n", encoding="utf-8")
    (PROFILE / "outside.py").write_text("print('outside')\n", encoding="utf-8")
    crew = [{"Id": "maya", "Name": "Maya", "Job": "Researcher", "Mode": "default", "Skills": ["watch"], "Autonomy": "balanced"}]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake",
        "Width": 1300, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        send(p, "aiCheck")
        time.sleep(2)

        # load_skill names the programs; the first run asks, with where the plugin came from.
        cid, before = calls(p, None, [["load_skill", {"id": "watch"}], ["run_plugin_program", {"plugin": "video", "program": "${CLAUDE_PLUGIN_ROOT}/scripts/hello.py", "args": ["one", "two words"]}]])
        loaded = got(before, 1)
        skill = json.loads(loaded[0]["text"]) if loaded else {}
        check("run_plugin_program" in (loaded[0]["tools"] if loaded else []), "The AI is offered run_plugin_program")
        check((skill.get("plugin") or {}).get("programs") == ["scripts/hello.py", "scripts/setup.py", "scripts/slow.py"] and "run_plugin_program" in skill["plugin"].get("howTo", ""),
              f"load_skill names the plugin's programs and how to run them ({skill.get('plugin')})")
        asked = card(p)
        check("Run scripts/hello.py one two words" in asked.get("text", "") and "github.com/acme/video" in asked.get("text", "")
              and asked.get("buttons") == ["Deny", "Always for this plugin", "Allow once"], f"It asks first, showing the program and where it came from ({asked})")
        press(p, "Allow once")
        ran = got(before, 2)
        out = json.loads(ran[1]["text"]) if len(ran) > 1 else {}
        check(out.get("exitCode") == 0 and "hello one two words" in out.get("output", "") and f"root {PLUGIN}" in out.get("output", ""),
              f"Allow once runs it with its arguments as given and CLAUDE_PLUGIN_ROOT set ({out})")
        idle(p, cid)
        steps = [m["Text"] for c in chats() if c["Id"] == cid for m in c["Messages"] if m["Role"] == "tool"]
        check(any("Ran scripts/hello.py" in s for s in steps), f"The chat shows the step ({steps})")

        # Deny refuses it.
        cid, before = calls(p, cid, [["run_plugin_program", {"plugin": "video", "program": "scripts/hello.py"}]])
        card(p); press(p, "Deny")
        r = got(before, 1)
        check(r and r[0]["error"] and "said no" in r[0]["text"], f"Deny refuses it ({r[0]['text'][:90] if r else None})")
        idle(p, cid)

        # Always for this plugin: the next run doesn't ask. Its exit code comes back.
        cid, before = calls(p, cid, [["run_plugin_program", {"plugin": "video", "program": "scripts/hello.py"}], ["run_plugin_program", {"plugin": "video", "program": "scripts/hello.py", "args": ["fail"]}]])
        card(p); press(p, "Always for this plugin")
        r = got(before, 2)
        check(len(r) == 2 and not r[0]["error"] and json.loads(r[1]["text"]).get("exitCode") == 3, "Always for this plugin runs it, and the next run goes ahead with its exit code")
        idle(p, cid)

        # Setup still asks, at your own risk, with no Always.
        cid, before = calls(p, cid, [["run_plugin_program", {"plugin": "video", "program": "scripts/setup.py"}]])
        asked = card(p)
        check("own risk" in asked.get("text", "") and asked.get("buttons") == ["Deny", "Allow once"], f"Setup still asks, says it's at your own risk and has no Always ({asked})")
        press(p, "Allow once")
        r = got(before, 1)
        check(r and "set up" in r[0]["text"], "and runs once allowed")
        idle(p, cid)

        # Refused without a card.
        cid, before = calls(p, cid, [["run_plugin_program", {"plugin": "video", "program": "../../outside.py"}], ["run_plugin_program", {"plugin": "video", "program": "notes.txt"}],
                                     ["run_plugin_program", {"plugin": "other", "program": "x.py"}], ["run_plugin_program", {"plugin": "../video", "program": "scripts/hello.py"}]])
        r = got(before, 4)
        check(len(r) == 4 and all(x["error"] for x in r) and "isn't one of its programs" in r[0]["text"] and "isn't one of its programs" in r[1]["text"]
              and "don't have a plugin" in r[2]["text"] and "don't have a plugin" in r[3]["text"], "A path outside it, a file that isn't a program and a plugin it doesn't have are refused")
        check(not js(p, "!!document.querySelector('.chat-view .approve-card')"), "with no card")
        idle(p, cid)

        # Too long: stopped.
        cid, before = calls(p, cid, [["run_plugin_program", {"plugin": "video", "program": "scripts/slow.py", "timeout": 2}]])
        r = got(before, 1, 30)
        out = json.loads(r[0]["text"]) if r else {}
        check(out.get("timedOut") is True and "woke" not in out.get("output", ""), f"A program that runs too long is stopped ({out})")
        idle(p, cid)

        # Settings: Maya on Keep going, then back on Balanced and Reset all.
        send(p, "openPanel", name="settings")
        until(lambda: js(p, "!!document.querySelector('.set-shell')"), 10)
        js(p, "[...document.querySelectorAll('.set-nav-item')].find(t => t.innerText.trim() === 'Privacy & permissions')?.click()")
        auto = "document.querySelector('[aria-label=\"Autonomy for Maya\"]')?.innerText ?? ''"
        row = until(lambda: js(p, auto), 10) or ""
        check("Balanced" in row, f"Settings show Maya's Autonomy, Balanced ({row[:120]!r})")
        send(p, "permReset")
        send(p, "companionAutonomy", id="maya", level="keepgoing")
        check(until(lambda: "Keep going" in (js(p, auto) or ""), 5), "Keep going shows in Settings")
        send(p, "openPanel", name="settings")
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        cid, before = calls(p, cid, [["run_plugin_program", {"plugin": "video", "program": "scripts/hello.py", "args": ["auto"]}]])
        r = got(before, 1)
        check(r and "hello auto" in r[0]["text"] and not js(p, "!!document.querySelector('.chat-view .approve-card')"), "On Keep going it runs without a card")
        idle(p, cid)
        audit = [a for c in chats() if c["Id"] == cid for a in c.get("Audit", [])]
        check(any("without asking" in a.get("Result", "") for a in audit) and any(a.get("Result") == "You allowed this plugin" for a in audit), "The chat's log says how each run was allowed")
        send(p, "companionAutonomy", id="maya", level="balanced")
        send(p, "permReset")
        cid, before = calls(p, cid, [["run_plugin_program", {"plugin": "video", "program": "scripts/hello.py"}]])
        check("Run scripts/hello.py" in card(p).get("text", ""), "Back on Balanced, after Reset all: it asks again, Always for this plugin forgotten too")
        press(p, "Deny")
        got(before, 1)
        idle(p, cid)

        # The plugin goes with its last skill.
        send(p, "skillDelete", id="watch")
        check(until(lambda: not PLUGIN.exists(), 10) and (PROFILE / "plugins" / "other").exists(), "Deleting its last skill deletes the plugin's folder, and only that one")
        errors = rpc(p).get("shellErrors") or []
        check(not errors, "No interface errors" + (f": {errors[:1]}" if errors else ""))
    finally:
        try:
            rpc(p, "quit")
            p.wait(timeout=20)
        except Exception:
            p.kill()
        time.sleep(1)
        shutil.rmtree(RUN, ignore_errors=True)
    print("FAILED " + str(FAILED) if FAILED else "PASSED")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
