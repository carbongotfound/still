"""Agent adapters end to end with fake agent apps (no AI usage): onboarding row states, a run, resume, API keys kept
out, Stop ending the whole process tree within a second, and no "Codex" anywhere on screen.

Run: python tests/desktop/providers.py artifacts/Still-QA/Still.exe
The fakes are manifest agents (Still's agents folder) backed by a small Python script; see docs/agentic/agents.md.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, alive, launcher, rpc, until_started  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("providers-" + uuid.uuid4().hex)
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
BIN = RUN / "bin"
LOG = BIN / "calls.jsonl"
RESULT = {"exe": str(EXE), "checks": []}

def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def send(process, op, **args):
    rpc(process, "shellEval", script="window.chrome.webview.postMessage(" + json.dumps({"op": op, **args}) + ")")

def text(process):
    return rpc(process, "shellEval", script="document.body.innerText")

def until(predicate, seconds=20, step=.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    return None


FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    if args[:1] == ["status-out"]: print("signed out"); sys.exit(0)
    prompt = sys.stdin.read()
    keys = [k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY") if k in os.environ]
    with open(os.path.join(here, "calls.jsonl"), "a") as log: log.write(json.dumps({"args": args, "keys": keys, "pid": os.getpid()}) + "\n")
    session = args[args.index("--resume") + 1] if "--resume" in args else "fake-session-1"
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": session})
    if "SLEEP" in prompt:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        open(os.path.join(here, "child.pid"), "w").write(str(child.pid))
        say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Working on it"}]}})
        time.sleep(120)
    n = sum(1 for _ in open(os.path.join(here, "calls.jsonl")))
    say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__still__list_tabs", "input": {}}]}})
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Fake reply %d, keys: %s" % (n, ",".join(keys) or "none")}]}})
    say({"type": "result", "subtype": "success", "is_error": False, "session_id": session})
''')

def manifest(file, **fields):
    (PROFILE / "agents" / (file + ".json")).write_text(json.dumps({"id": file, "enabled": True, **fields}))

process = None
try:
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE)
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    fake = str(BIN / "fakeagent")
    manifest("fake", name="Fake agent", command=fake, detect=["status"], expect="signed in", run=["run"], resume=["--resume", "{session}"], output="stream-json")
    manifest("fake-out", name="Fake signed out", command=fake, detect=["status-out"], expect="^signed in", run=["run"], output="stream-json")
    manifest("fake-missing", name="Fake missing", command=str(BIN / "not-installed"), install="pip install not-a-real-agent", run=["run"])
    (PROFILE / "agents" / "broken.json").write_text("{ not json")
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "ANTHROPIC_API_KEY": "sk-test-not-real", "OPENAI_API_KEY": "sk-test-not-real"}
    process = subprocess.Popen([str(EXE), "--qa", "--profile", str(PROFILE), "--profiles-root", str(PROFILE)], env=env)
    until_started(process)

    # Onboarding: every app in one list, each with its state.
    send(process, "aiToggle")
    send(process, "aiCheck")
    # Claude, ChatGPT, Grok and Gemini show first; OpenCode and the manifests wait under More agents, which opens in place.
    folded = until(lambda: rpc(process, "shellEval", script="(b => b ? b.innerText.replace(/\\s+/g, ' ').trim() : '')(document.querySelector('.byo-more'))"), 30)
    first = text(process)
    check(folded.startswith("More agents") and "Fake missing" not in first and all(n in first for n in ("Claude", "ChatGPT", "Grok", "Gemini")),
          f"Claude, ChatGPT, Grok and Gemini show; the rest wait under More agents ({folded!r})")
    rpc(process, "shellEval", script="document.querySelector('.byo-more[aria-expanded=false]')?.click()")
    shown = until(lambda: (t := text(process)) and "Fake missing" in t and "Fake agent\nLogged in" in t and t, 30)
    check(shown and all(n in shown for n in ("ChatGPT", "Grok", "Claude")), "Pick your model lists ChatGPT, Grok and Claude")
    check(shown and "Codex" not in shown, "The screen never says Codex")
    names = rpc(process, "shellEval", script="[...document.querySelectorAll('.byo-row strong')].map(s => s.innerText)") or []
    check(all(n in names for n in ("OpenCode", "Fake agent", "Fake signed out", "Fake missing")) and len(names) == len(set(names)),
          f"More agents opens them in the same list: OpenCode and the three manifests, the broken one skipped ({names})")
    rows = shown
    check(rows and "Fake agent\nLogged in" in rows, "Signed-in row")
    check(rows and "Fake signed out\nInstalled\nSet up" in rows, "Installed but signed out row, with Set up")
    check(rows and "Fake missing\nNot installed\nAdd" in rows, "Not installed row, with Add")
    rpc(process, "shellEval", script="[...document.querySelectorAll('.byo-row')].find(r => r.innerText.includes('Fake missing')).querySelector('.byo-act').click()")
    check(until(lambda: "pip install not-a-real-agent" in text(process), 5), "Add shows the install command")
    rpc(process, "capture", name="onboarding.png")  # saved in the profile folder

    # A run, with API keys set in Still's environment.
    send(process, "aiHarness", harness="fake")
    send(process, "aiSend", text="hello")
    reply = until(lambda: (t := text(process)) and "Fake reply 1" in t and t, 30)
    check(reply, "A run streams its reply into the chat")
    check(reply and "keys: none" in reply, "API keys never reach the agent")
    check(reply and "Looked at open tabs" in reply, "Tool calls show as steps")
    check(reply and "Your Fake agent plan" not in reply, "A custom AI gets no plan line (only Claude, ChatGPT and Grok come with one)")

    # Resume: the next message continues the agent's session.
    until(lambda: not rpc(process, "shellEval", script="!!document.querySelector('[aria-label=Stop]')"), 10)
    send(process, "aiSend", text="again")
    until(lambda: "Fake reply 2" in text(process), 30)
    calls = [json.loads(l) for l in LOG.read_text().splitlines()]
    check(len(calls) == 2 and "--resume" not in calls[0]["args"] and calls[1]["args"][-2:] == ["--resume", "fake-session-1"], "The second message resumes the session")

    # Stop ends the agent and everything it started.
    send(process, "aiSend", text="SLEEP for a while")
    until(lambda: (BIN / "child.pid").exists(), 30)
    child = int((BIN / "child.pid").read_text())
    agent = json.loads(LOG.read_text().splitlines()[-1])["pid"]
    check(alive(child) and alive(agent), "The agent and its child are running")
    started = time.monotonic()
    send(process, "aiStop")
    gone = until(lambda: not alive(child) and not alive(agent), 5, .02)
    took = time.monotonic() - started
    RESULT["stop_seconds"] = round(took, 3)
    check(gone and took < 1, "Stop ends the whole process tree within 1s (%.2fs)" % took)
    check(until(lambda: "Stopped." in text(process), 5), "The chat says it stopped")
    check(not rpc(process)["shellErrors"], "No interface JavaScript errors")
    rpc(process, "quit")
    process.wait(timeout=15)
except Exception as error:
    RESULT["error"] = repr(error)
    print("ERROR " + repr(error), flush=True)
finally:
    if process and process.poll() is None:
        process.kill()
    RESULT["passed"] = "error" not in RESULT and all(c["passed"] for c in RESULT["checks"])
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
    print(("PASSED " if RESULT["passed"] else "FAILED ") + str(sum(c["passed"] for c in RESULT["checks"])) + "/" + str(len(RESULT["checks"])) + " -> " + str(RUN), flush=True)
    sys.exit(0 if RESULT["passed"] else 1)
