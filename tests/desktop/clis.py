"""Gemini CLI and OpenCode as built-in AIs, end to end with fake apps (no AI usage): their rows, signed-in detection,
the arguments and run-folder config Still gives each (model, effort or variant, resume, Still's MCP server, every
other tool off), API keys kept out, a tool call through Still's own MCP server, and a resumed session.

Run: python tests/desktop/clis.py artifacts/Still-QA/Still.exe
The fakes print the event shapes recorded from the real apps (tests/fixtures/agents/gemini.jsonl, opencode.jsonl).
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, js, launch, launcher, rpc, send, text, until  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("clis-" + uuid.uuid4().hex[:8])
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"exe": str(EXE), "checks": []}

FAKE = r'''
import json, os, queue, subprocess, sys, threading
CLI = "CLI_NAME"
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
KEYS = [k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY") if k in os.environ]
def say(e): print(json.dumps(e), flush=True)
def log(entry):
    with open(os.path.join(here, "calls.jsonl"), "a") as f: f.write(json.dumps(entry) + "\n")
def home_tab(command):
    """list_tabs through Still's MCP server, as the real app calls it."""
    p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(l) for l in p.stdout], daemon=True).start()
    def ask(i, method, params):
        p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n").encode()); p.stdin.flush()
        while True:
            m = json.loads(lines.get(timeout=30))
            if m.get("id") == i: return m
    try:
        ask(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": CLI, "version": "1"}})
        p.stdin.write(b'{"jsonrpc": "2.0", "method": "notifications/initialized"}\n'); p.stdin.flush()
        r = ask(2, "tools/call", {"name": "list_tabs", "arguments": {}})
        return "Home" in " ".join(c.get("text", "") for c in r.get("result", {}).get("content", []))
    except Exception:
        return False
    finally:
        p.kill()

if CLI == "gemini":
    settings = json.load(open(os.path.join(".gemini", "settings.json")))
    policy = open(args[args.index("--policy") + 1]).read() if "--policy" in args else ""
    prompt = sys.stdin.read()
    session = args[args.index("--session-id") + 1] if "--session-id" in args else args[args.index("--resume") + 1]
    server = settings["mcpServers"]["still"]
    seen = home_tab([server["command"]] + server["args"])
    log({"cli": CLI, "args": args, "cwd": os.getcwd(), "settings": settings, "policy": policy, "keys": KEYS, "trust": os.environ.get("GEMINI_CLI_TRUST_WORKSPACE"), "prompt": len(prompt)})
    say({"type": "init", "session_id": session, "model": "auto"})
    say({"type": "message", "role": "user", "content": "not shown"})
    say({"type": "tool_use", "tool_name": "mcp_still_list_tabs", "tool_id": "t1", "parameters": {}})
    say({"type": "tool_result", "tool_id": "t1", "status": "success" if seen else "error"})
    say({"type": "message", "role": "assistant", "content": "Gemini saw ", "delta": True})
    say({"type": "message", "role": "assistant", "content": "the Home tab." if seen else "no tabs.", "delta": True})
    say({"type": "result", "status": "success", "stats": {"input_tokens": 1200, "output_tokens": 7, "cached": 0}})
else:
    if args == ["--version"]: print("1.19.5"); sys.exit(0)
    if args[:1] == ["models"]:
        models = {"opencode/big-pickle": {"name": "Big Pickle", "capabilities": {"toolcall": True}, "variants": {}},
                  "fake/no-tools": {"name": "No Tools", "capabilities": {"toolcall": False}},
                  "anthropic/claude-fake": {"name": "Claude Fake", "capabilities": {"toolcall": True}, "variants": {"max": {}, "high": {}, "low": {}}}}
        for k, v in models.items():
            print(k)
            if "--verbose" in args: print(json.dumps(v, indent=2))
        sys.exit(0)
    folder = args[args.index("--dir") + 1]
    config = json.load(open(os.path.join(folder, "opencode.json")))
    prompt = sys.stdin.read()
    session = args[args.index("--session") + 1] if "--session" in args else "ses_fake1"
    seen = home_tab(config["mcp"]["still"]["command"])
    log({"cli": CLI, "args": args, "cwd": os.getcwd(), "config": config, "keys": KEYS, "prompt": len(prompt)})
    say({"type": "step_start", "sessionID": session, "part": {"type": "step-start"}})
    say({"type": "tool_use", "sessionID": session, "part": {"callID": "c1", "tool": "still_list_tabs", "state": {"status": "completed" if seen else "error", "input": {}}}})
    say({"type": "text", "sessionID": session, "part": {"text": "OpenCode saw the Home tab." if seen else "OpenCode saw no tabs."}})
    say({"type": "step_finish", "sessionID": session, "part": {"tokens": {"input": 800, "output": 6, "cache": {"read": 0}}}})
'''


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def calls(cli):
    try:
        return [c for c in map(json.loads, (BIN / "calls.jsonl").read_text().splitlines()) if c["cli"] == cli]
    except OSError:
        return []


def after(args, flag):
    return args[args.index(flag) + 1] if flag in args else None


def prefs():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
    except (OSError, ValueError, KeyError):
        return {}


def same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def ask(p, cli, words, n):
    """Sends a message and waits for the app's nth run and its reply in the chat."""
    send(p, "aiSend", text=words)
    until(lambda: len(calls(cli)) >= n, 30)
    until(lambda: not js(p, "!!document.querySelector('[aria-label=Stop]')"), 30)
    return calls(cli)[n - 1] if len(calls(cli)) >= n else {"args": []}


def tier(cli):
    return prefs().get("AiTiers", {}).get(cli + ":default") or ["", ""]


def pick(p, cli, model, effort=""):
    """Settings → Models, Everyday for this AI, as the shell sends it: the models load in the background, so it retries."""
    return until(lambda: send(p, "aiTier", harness=cli, tier="default", model=model, effort=effort) or time.sleep(.5) or tier(cli)[0] == model, 30)


def main():
    BIN.mkdir(parents=True)
    PROFILE.mkdir(parents=True)
    for cli in ("gemini", "opencode"):
        (BIN / f"fake_{cli}.py").write_text(FAKE.replace("CLI_NAME", cli))
        launcher(BIN / cli, BIN / f"fake_{cli}.py")
    google = RUN / "gemini-home" / ".gemini"  # signed in with Google, as Gemini CLI saves it
    google.mkdir(parents=True)
    (google / "settings.json").write_text('{\n  // its settings allow comments\n  "security": {"auth": {"selectedType": "oauth-personal"}},\n}\n')
    (google / "oauth_creds.json").write_text("{}")
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True,
        "Permissions": [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate")]},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "PATH": str(BIN) + os.pathsep + os.environ.get("PATH", ""), "GEMINI_CLI_HOME": str(RUN / "gemini-home"),
           "GEMINI_API_KEY": "gm-test-not-real", "GOOGLE_API_KEY": "gg-test-not-real", "ANTHROPIC_API_KEY": "sk-test-not-real", "OPENAI_API_KEY": "sk-test-not-real"}
    p = launch(EXE, PROFILE, env)
    try:
        # The rows: Gemini up front, OpenCode under More agents, both ready, each with its gaps.
        send(p, "aiToggle")
        send(p, "aiCheck")
        shown = until(lambda: (t := text(p)) and "More agents" in t and "Gemini" in t and t, 30) or ""
        check("More agents (1)" in shown and "OpenCode" not in shown, "Gemini is a headline AI, OpenCode is under More agents")
        js(p, "document.querySelector('.byo-more')?.click()")
        rows = until(lambda: (t := text(p)) and "OpenCode\nSigned in" in t and "Gemini\nSigned in" in t and t, 30) or text(p)
        check("Gemini\nSigned in" in rows, "Gemini signed in with Google is ready (its settings file may have comments)")
        check("OpenCode\nSigned in" in rows, "OpenCode is ready once it lists a model")
        check("run gemini in a terminal" in rows and "Gemini keeps its own record of incognito chats" in rows, "Gemini's card says how to sign in and what it can't do")
        check("set up in OpenCode" in rows and "OpenCode keeps its own record of incognito chats" in rows, "OpenCode's card says it runs on the provider set up in OpenCode")

        # Gemini: a chat, a resume and a model.
        send(p, "aiHarness", harness="gemini")
        send(p, "aiNew")
        first = ask(p, "gemini", "hello", 1)
        a = first["args"]
        check(until(lambda: "Gemini saw the Home tab." in text(p), 10), "Gemini's reply, after a tool call through Still's MCP server")
        check(a[:2] == ["--output-format", "stream-json"] and after(a, "--allowed-mcp-server-names") == "still" and after(a, "-e") == "none", "Gemini: stream-json, only Still's MCP server, no extensions")
        session = after(a, "--session-id")
        check(session and len(session) == 36 and "--resume" not in a and "-m" not in a, "Gemini: a new session id from Still, default model")
        server = first.get("settings", {}).get("mcpServers", {}).get("still", {})
        check(same(server.get("command", ""), EXE) and "--mcp" in server.get("args", []) and server.get("trust") is True and server.get("timeout") == 660000,
              "Gemini: Still's MCP server in the run folder's .gemini/settings.json, trusted, with a long timeout for ask_user")
        policy = first.get("policy", "")
        check('toolName = "*"\ndecision = "deny"' in policy and 'toolName = "mcp_still_*"\ndecision = "allow"' in policy and Path(after(a, "--policy")).parent.name == ".gemini",
              "Gemini: a policy that denies every tool but Still's")
        check(first.get("trust") == "true", "Gemini: the run folder is trusted for the run")
        check(first.get("keys") == [] and first.get("prompt", 0) > 0, "Gemini: no API key in its environment, the prompt on stdin")
        check(until(lambda: "1.2k in" in text(p), 5), "Gemini: token usage from its result")
        second = ask(p, "gemini", "again", 2)["args"]
        check(after(second, "--resume") == session and "--session-id" not in second, "Gemini: the next message resumes the session")
        check(pick(p, "gemini", "flash"), "Gemini's models fill the mode pickers (Everyday set to Flash)")
        check(after(ask(p, "gemini", "quick one", 3)["args"], "-m") == "flash", "Gemini: the picked model goes as -m")

        # OpenCode: a chat, a resume, a model and its variant.
        send(p, "aiHarness", harness="opencode")
        send(p, "aiNew")
        first = ask(p, "opencode", "hello", 1)
        a = first["args"]
        check(until(lambda: "OpenCode saw the Home tab." in text(p), 10), "OpenCode's reply, after a tool call through Still's MCP server")
        check(a[:3] == ["run", "--format", "json"] and after(a, "--title") == "Still" and same(after(a, "--dir") or "", first.get("cwd", "")), "OpenCode: run --format json in the run folder")
        check("--session" not in a and "-m" not in a and "--variant" not in a, "OpenCode: a new session, its default model")
        config = first.get("config", {})
        still = config.get("mcp", {}).get("still", {})
        check(still.get("type") == "local" and same((still.get("command") or [""])[0], EXE) and "--mcp" in still.get("command", []) and still.get("timeout") == 660000,
              "OpenCode: Still's MCP server in the run folder's opencode.json")
        check(config.get("tools") == {"*": False, "still_*": True}, "OpenCode: every tool off but Still's")
        check(first.get("keys") == [] and first.get("prompt", 0) > 0, "OpenCode: no API key in its environment, the prompt on stdin")
        check(until(lambda: "800 in" in text(p), 5), "OpenCode: token usage per step")
        second = ask(p, "opencode", "again", 2)["args"]
        check(after(second, "--session") == "ses_fake1", "OpenCode: the next message resumes its session")
        check(pick(p, "opencode", "opencode/big-pickle"), "OpenCode's models fill the mode pickers")
        send(p, "aiTier", harness="opencode", tier="default", model="fake/no-tools", effort="")
        time.sleep(1.5)
        check(tier("opencode")[0] == "opencode/big-pickle", "OpenCode: a model without tool calls isn't offered")
        check(pick(p, "opencode", "anthropic/claude-fake", "high") and tier("opencode")[1] == "high", "OpenCode: a model's variants are its effort levels")
        third = ask(p, "opencode", "think hard", 3)["args"]
        check(after(third, "-m") == "anthropic/claude-fake" and after(third, "--variant") == "high", "OpenCode: the picked model as -m and effort as --variant")
    finally:
        try:
            rpc(p, "quit")
        except Exception:
            pass
        time.sleep(2)
        if p.poll() is None:
            p.kill()


try:
    main()
except Exception as e:
    RESULT["error"] = repr(e)
    print("ERROR", repr(e), flush=True)
finally:
    RESULT["passed"] = "error" not in RESULT and all(c["passed"] for c in RESULT["checks"])
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
    print(("PASSED " if RESULT["passed"] else "FAILED ") + str(sum(c["passed"] for c in RESULT["checks"])) + "/" + str(len(RESULT["checks"])) + " -> " + str(RUN), flush=True)
    sys.exit(0 if RESULT["passed"] else 1)
