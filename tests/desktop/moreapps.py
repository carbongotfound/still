"""The Compatible AI apps (Qwen Code, GitHub Copilot CLI, and Amp on the Mac) end to end with fake apps (no AI usage, no
real app installed or signed in): their rows and logos, signed-in detection, the arguments and run-folder config Still
gives each (Still's MCP server, every other tool off, model, effort or mode, resume), API keys kept out, a tool call
through Still's own MCP server, and the DeepSeek preset in Settings, saved with no key.

Run: python tests/desktop/moreapps.py artifacts/Still-QA/Still.exe
The fakes print the event shapes from each app's docs: Claude-style stream-json for Qwen Code and Amp, plain text for
Copilot with -s.
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
RUN = ROOT / "artifacts" / ("moreapps-" + uuid.uuid4().hex[:8])
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"exe": str(EXE), "checks": []}
APPS = ("qwen", "copilot", "amp") if MAC else ("qwen", "copilot")

FAKE = r'''
import json, os, queue, subprocess, sys, threading
CLI = "CLI_NAME"
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
KEYS = [k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY") if k in os.environ]
def say(e): print(json.dumps(e), flush=True)
def log(entry):
    with open(os.path.join(here, "calls.jsonl"), "a") as f: f.write(json.dumps(entry) + "\n")
def after(flag): return args[args.index(flag) + 1] if flag in args else None
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
def claude_style(session, name, seen, words):
    say({"type": "system", "subtype": "init", "session_id": session, "cwd": os.getcwd()})
    say({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "mcp__still__list_tabs", "input": {}}]}, "session_id": session})
    say({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": not seen}]}, "session_id": session})
    say({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": words}]}, "session_id": session})
    say({"type": "result", "subtype": "success", "is_error": False, "result": words, "session_id": session, "usage": {"input_tokens": 900, "output_tokens": 5}})

prompt = sys.stdin.read()
if CLI == "qwen":
    settings = json.load(open(os.path.join(".qwen", "settings.json")))
    trust = os.environ.get("QWEN_CODE_TRUSTED_FOLDERS_PATH", "")
    server = settings["mcpServers"]["still"]
    seen = home_tab([server["command"]] + server["args"])
    log({"cli": CLI, "args": args, "cwd": os.getcwd(), "settings": settings, "trust": json.load(open(trust)) if trust else {}, "keys": KEYS, "prompt": len(prompt)})
    claude_style(after("--resume") or "qwen-ses-1", "qwen", seen, "Qwen saw the Home tab." if seen else "Qwen saw no tabs.")
elif CLI == "copilot":
    config = json.load(open(after("--additional-mcp-config")[1:]))
    server = config["mcpServers"]["still"]
    seen = home_tab([server["command"]] + server["args"])
    log({"cli": CLI, "args": args, "cwd": os.getcwd(), "config": config, "keys": KEYS, "prompt": len(prompt)})
    print("Copilot saw" if seen else "Copilot saw no tabs.", flush=True)
    print("the Home tab." if seen else "", flush=True)
else:
    settings = json.load(open(after("--settings-file")))
    server = settings["amp.mcpServers"]["still"]
    seen = home_tab([server["command"]] + server["args"])
    log({"cli": CLI, "args": args, "cwd": os.getcwd(), "settings": settings, "keys": KEYS, "prompt": len(prompt), "hello": "hello" in prompt})
    claude_style("T-fake-thread", "amp", seen, "Amp saw the Home tab." if seen else "Amp saw no tabs.")
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


def row(p, name):
    """A row in the AI picker: its text and whether its tile shows a mark (not a letter)."""
    return js(p, f"(r => r && [r.innerText, !!r.querySelector('.byo-tile svg')])([...document.querySelectorAll('.byo-row')].find(r => r.querySelector('.byo-name strong')?.firstChild?.textContent === {json.dumps(name)}))") or ["", False]


def main():
    BIN.mkdir(parents=True)
    PROFILE.mkdir(parents=True)
    for cli in APPS:
        (BIN / f"fake_{cli}.py").write_text(FAKE.replace("CLI_NAME", cli))
        launcher(BIN / cli, BIN / f"fake_{cli}.py")
    qwen = RUN / "qwen-home"  # signed in with Qwen OAuth, as Qwen Code saves it
    qwen.mkdir(parents=True)
    (qwen / "settings.json").write_text('{\n  // its settings allow comments\n  "security": {"auth": {"selectedType": "qwen-oauth"}},\n}\n')
    (qwen / "oauth_creds.json").write_text("{}")
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True,
        "Permissions": [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate")]},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "PATH": str(BIN) + os.pathsep + os.environ.get("PATH", ""), "QWEN_HOME": str(qwen),
           "GEMINI_API_KEY": "gm-test-not-real", "ANTHROPIC_API_KEY": "sk-test-not-real", "OPENAI_API_KEY": "sk-test-not-real"}
    p = launch(EXE, PROFILE, env)
    try:
        # The rows: under More agents, each labelled Compatible, with its own mark.
        send(p, "aiToggle")
        send(p, "aiCheck")
        until(lambda: "More agents" in (text(p) or ""), 30)
        js(p, "document.querySelector('.byo-more')?.click()")
        until(lambda: "Qwen Code" in (text(p) or ""), 10)
        rows = {cli: until(lambda: (r := row(p, name)) and r[0] and r, 20) or ["", False] for cli, name in
                (("qwen", "Qwen Code"), ("copilot", "GitHub Copilot"), ("amp", "Amp"))[:len(APPS)]}
        for cli, (shown, mark) in rows.items():
            check("Compatible" in shown and mark, f"{cli}: under More agents, labelled Compatible, with its mark ({shown!r})")
        if not MAC:
            check(not row(p, "Amp")[0], "Windows: no Amp row (its docs run it through WSL)")
        qrow = until(lambda: (r := row(p, "Qwen Code")) and "Signed in" in r[0] and r, 20) or ["", False]
        js(p, "document.querySelector('.byo-more')?.scrollIntoView({block: 'start'})")
        time.sleep(.4)
        rpc(p, "capture", name="apps-picker.png")  # in the profile folder
        check("Signed in" in qrow[0], "Qwen Code signed in with Qwen OAuth is ready (its settings file may have comments)")

        # Qwen Code: a chat, a resume.
        send(p, "aiHarness", harness="qwen")
        send(p, "aiNew")
        first = ask(p, "qwen", "hello", 1)
        a = first["args"]
        check(until(lambda: "Qwen saw the Home tab." in text(p), 10), "Qwen Code's reply, after a tool call through Still's MCP server")
        check(a[:2] == ["--output-format", "stream-json"] and after(a, "--allowed-mcp-server-names") == "still" and after(a, "-e") == "none" and after(a, "--approval-mode") == "default",
              "Qwen Code: stream-json, only Still's MCP server, no extensions, nothing approved by default")
        check("--resume" not in a and "-m" not in a, "Qwen Code: a new session, its own model")
        s = first.get("settings", {})
        server = s.get("mcpServers", {}).get("still", {})
        check(same(server.get("command", ""), EXE) and "--mcp" in server.get("args", []) and server.get("trust") is True and server.get("timeout") == 660000,
              "Qwen Code: Still's MCP server in the run folder's .qwen/settings.json, trusted, with a long timeout for ask_user")
        disabled = s.get("tools", {}).get("disabled", [])
        check(all(t in disabled for t in ("run_shell_command", "read_file", "write_file", "edit", "web_fetch", "web_search", "agent", "skill", "save_memory"))
              and s.get("tools", {}).get("core") == ["mcp__still"] and s.get("permissions", {}).get("allow") == ["mcp__still"],
              "Qwen Code: every built-in tool hidden, core tools allow none, Still's tools need no prompt")
        check(s.get("general", {}).get("chatRecording") is True, "Qwen Code: an ordinary chat is saved by the app, so it can resume")
        trust = first.get("trust", {})
        check(len(trust) == 1 and list(trust.values()) == ["TRUST_FOLDER"] and Path(first.get("cwd", "")).resolve().is_relative_to(Path(list(trust)[0]).resolve()),
              "Qwen Code: Still's own trusted-folders list covers the run folder")
        check(first.get("keys") == [] and first.get("prompt", 0) > 0, "Qwen Code: no API key in its environment, the prompt on stdin")
        check(until(lambda: "900 in" in text(p), 5), "Qwen Code: token usage from its result")
        second = ask(p, "qwen", "again", 2)["args"]
        check(after(second, "--resume") == "qwen-ses-1", "Qwen Code: the next message resumes its session")

        # GitHub Copilot: a chat, a resume, a model and an effort.
        send(p, "aiHarness", harness="copilot")
        send(p, "aiNew")
        first = ask(p, "copilot", "hello", 1)
        a = first["args"]
        check(until(lambda: "Copilot saw\nthe Home tab." in text(p) or "Copilot saw the Home tab." in text(p), 10), "Copilot's reply, after a tool call through Still's MCP server")
        check(a[:1] == ["-s"] and after(a, "--allow-tool") == "still" and after(a, "--deny-tool") == "shell,write,read,url,memory"
              and all(f in a for f in ("--disable-builtin-mcps", "--no-ask-user", "--no-custom-instructions")),
              "Copilot: only its reply, Still's tools allowed, every built-in tool kind denied, no GitHub MCP server, no ask_user of its own")
        session = after(a, "--session-id")
        check(session and len(session) == 36 and "--model" not in a and "--effort" not in a, "Copilot: a new session id from Still, its default model")
        server = first.get("config", {}).get("mcpServers", {}).get("still", {})
        check(server.get("type") == "local" and same(server.get("command", ""), EXE) and "--mcp" in server.get("args", []) and server.get("tools") == ["*"]
              and server.get("timeout") == 660000 and Path(after(a, "--additional-mcp-config")[1:]).parent == Path(first.get("cwd", "")),
              "Copilot: Still's MCP server in the run folder's config, added for the run")
        check(first.get("keys") == [] and first.get("prompt", 0) > 0, "Copilot: no API key in its environment, the prompt on stdin")
        second = ask(p, "copilot", "again", 2)["args"]
        check(after(second, "--session-id") == session, "Copilot: the next message resumes the same session")
        check(until(lambda: send(p, "aiTier", harness="copilot", tier="default", model="auto", effort="") or time.sleep(.5) or tier("copilot")[0] == "auto", 30),
              "Copilot's models fill the mode pickers (Everyday set to Auto)")
        third = ask(p, "copilot", "pick one", 3)["args"]
        check(after(third, "--model") == "auto" and "--effort" not in third, "Copilot: the picked model goes as --model")
        check(until(lambda: send(p, "aiTier", harness="copilot", tier="default", model="", effort="high") or time.sleep(.5) or tier("copilot") == ["", "high"], 30),
              "Copilot: its default model takes an effort")
        fourth = ask(p, "copilot", "think hard", 4)["args"]
        check(after(fourth, "--effort") == "high" and "--model" not in fourth, "Copilot: the effort goes as --effort")

        if MAC:
            # Amp: a chat, its mode as the effort, no thread kept (each message brings the chat so far).
            send(p, "aiHarness", harness="amp")
            send(p, "aiNew")
            first = ask(p, "amp", "hello", 1)
            a = first["args"]
            check(until(lambda: "Amp saw the Home tab." in text(p), 10), "Amp's reply, after a tool call through Still's MCP server")
            s = first.get("settings", {})
            server = s.get("amp.mcpServers", {}).get("still", {})
            check(a[:2] == ["-x", "--stream-json"] and same(server.get("command", ""), EXE) and "--mcp" in server.get("args", []) and "builtin:*" in s.get("amp.tools.disable", []),
                  "Amp: execute mode, Still's MCP server in a settings file of its own, Amp's built-in tools off")
            check(first.get("keys") == [] and first.get("prompt", 0) > 0 and "--mode" not in a, "Amp: no API key in its environment, the prompt on stdin, its default mode")
            second = ask(p, "amp", "again", 2)
            check("threads" not in second["args"] and second.get("hello") is True, "Amp: the next message starts a new thread with the chat so far")
            check(until(lambda: send(p, "aiTier", harness="amp", tier="default", model="", effort="ultra") or time.sleep(.5) or tier("amp") == ["", "ultra"], 30),
                  "Amp: its modes are the effort levels")
            check(after(ask(p, "amp", "think hard", 3)["args"], "--mode") == "ultra", "Amp: the effort goes as --mode")

        # DeepSeek: a preset in Settings → API providers, the address and models filled in, saved with no key.
        send(p, "openPanel", name="settings", value="models")
        until(lambda: "Add an API provider" in (text(p) or ""), 15)
        js(p, "[...document.querySelectorAll('button')].find(b => b.innerText.trim() === 'Add an API provider')?.click()")
        until(lambda: js(p, "!!document.querySelector('.api-presets button')"), 10)
        js(p, "[...document.querySelectorAll('.api-presets button')].find(b => b.innerText.trim() === 'DeepSeek')?.click()")
        time.sleep(.5)
        values = js(p, "[...document.querySelectorAll('.api-form input')].map(i => i.value)") or []
        check(values[:4] == ["DeepSeek", "https://api.deepseek.com", "", "deepseek-flash, deepseek-v4-pro"] and "1000000" in values,
              f"DeepSeek preset: its address, models and context filled in, the key left to you ({values})")
        js(p, "document.querySelector('.api-form')?.scrollIntoView({block: 'center'})")
        time.sleep(.4)
        rpc(p, "capture", name="deepseek-preset.png")  # in the profile folder
        js(p, "[...document.querySelectorAll('.api-form button')].find(b => b.innerText.trim() === 'Add provider')?.click()")
        saved = until(lambda: next((x for x in prefs().get("ApiProviders", []) if x.get("Name") == "DeepSeek"), None), 15) or {}
        check(saved.get("Url") == "https://api.deepseek.com" and saved.get("Kind") == "openai" and [m["Id"] for m in saved.get("Models", [])] == ["deepseek-flash", "deepseek-v4-pro"]
              and saved.get("NoKey") is True, "DeepSeek saves as an OpenAI-compatible provider with no key, no request sent")
        js(p, "[...document.querySelectorAll('.tier-head')].find(h => h.innerText.includes('GitHub Copilot'))?.scrollIntoView({block: 'start'})")
        time.sleep(.4)
        rpc(p, "capture", name="apps-modes.png")  # in the profile folder
        card = until(lambda: js(p, "(c => c && [c.innerText, !!c.querySelector('.ai-logo svg')])([...document.querySelectorAll('.api-card')].find(c => c.innerText.includes('DeepSeek')))"), 10) or ["", False]
        check("Compatible" in card[0] and card[1], "The DeepSeek card is labelled Compatible and shows its mark")
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
