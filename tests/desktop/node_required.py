"""Node.js before npm: wherever Still shows an npm install, it first says Node.js 18 or newer is required (from
https://nodejs.org) and how to check (node --version). When Still can't find Node.js, it says so up front instead.

- Settings > Models: Add on an app that installs from npm shows the Node.js line before "Run this in ..." and the
  command; an app that installs another way (pipx) shows none.
- The chat's setup pane and setup's Connect step say the same.
- With no Node.js on the computer (STILL_QA_NODE=0) each of those says Node.js isn't on this computer yet.
- The companion instructions say to name Node.js before an npm install, and that it's missing when it is.

The apps are made-up manifests in Still's agents folder, so no real app is ever found or run; Claude is a stand-in.

Run: python tests/desktop/node_required.py artifacts/Still-QA/Still.exe
Out: artifacts/node-required-*/ (kept when something fails), artifacts/screens/node-required-*.png
"""
import json
import os
from pathlib import Path
import shutil
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, screens, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("node-required-" + uuid.uuid4().hex[:8])
NEEDED = "Node.js 18 or newer is required (from https://nodejs.org). Check with node --version."
MISSING = "Still can't find Node.js, which this command needs. Install Node.js 18 or newer from https://nodejs.org first, then check with node --version."
RULE = "say first that Node.js 18 or newer is required"
RULE_MISSING = "Node.js isn't on this computer now, so say that up front."
NPM = "npm install -g @example/npm-agent"
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_"))}
FAILED = []

CLAUDE = textwrap.dedent(r'''
    import json, os, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if "status" in args: print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"})); sys.exit(0)
    if "auth" in args or "login" in args or args[:1] in (["--version"], ["mcp"]): sys.exit(0)
    open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8").write(json.dumps({"args": args, "prompt": sys.stdin.read()}) + "\n")
    session = args[args.index("--session-id") + 1] if "--session-id" in args else "standin"
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": session})
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Stand-in reply"}]}, "session_id": session})
    say({"type": "result", "subtype": "success", "is_error": False, "session_id": session})
''')


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        FAILED.append(label)


def start(name, node, harness="claude", fresh=False):
    folder = RUN / name
    bin, profile = folder / "bin", folder / "profile"
    bin.mkdir(parents=True)
    (profile / "agents").mkdir(parents=True)
    (bin / "claude.py").write_text(CLAUDE, encoding="utf-8")
    launcher(bin / "claude", bin / "claude.py")
    common = {"enabled": True, "detect": ["status"], "expect": "signed in", "run": ["run"], "output": "stream-json"}
    (profile / "agents" / "npm.json").write_text(json.dumps({"id": "npm", "name": "Npm agent", "command": str(bin / "no-such-npm-agent"),
                                                             "site": "https://npm-agent.example", "install": NPM, **common}))
    (profile / "agents" / "pip.json").write_text(json.dumps({"id": "pip", "name": "Pip agent", "command": str(bin / "no-such-pip-agent"),
                                                             "site": "https://pip-agent.example", "install": "pipx install pip-agent", **common}))
    if not fresh:
        (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": harness},
                                                        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, profile, {**CLEAN, "STILL_QA_CLIS": str(bin), "STILL_QA_NODE": "1" if node else "0"}), bin, profile


def stop(p):
    try:
        rpc(p, "quit")
        p.wait(timeout=15)
    except Exception:
        p.kill()


def row(name):
    return f"[...document.querySelectorAll('#set-ai .byo-row')].find(r => r.querySelector('strong')?.innerText.trim() === {json.dumps(name)})"


def how(p, name):
    """Add on that app in Settings > Models, and what its card then says."""
    js(p, "document.querySelector('#set-ai .byo-more[aria-expanded=false]')?.click()")
    until(lambda: js(p, f"!!{row(name)}"), 6)
    js(p, f"[...{row(name)}?.querySelectorAll('.byo-act') ?? []].find(b => b.innerText.includes('Add'))?.click()")
    return until(lambda: js(p, f"{row(name)}?.querySelector('.byo-how')?.innerText"), 6) or ""


def first(said, line, then):
    """line is there, and comes before then."""
    return line in said and then in said and said.index(line) < said.index(then)


def prompts(bin):
    f = bin / "prompts.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def settings_and_chat(node):
    shell = "Terminal" if sys.platform == "darwin" else "PowerShell"
    line, tag = (NEEDED, "found") if node else (MISSING, "missing")
    p, bin, profile = start(f"settings-{tag}", node, harness="npm")
    try:
        send(p, "aiCheck")
        send(p, "aiToggle")
        pane = until(lambda: js(p, "(e => e && e.innerText.includes('Npm agent') && e.innerText)(document.querySelector('.ai-sidebar .ai-pane'))"), 20) or ""
        check(first(pane, line, f"Run this in {shell}, then sign in.") and NPM in pane,
              f"Node.js {tag}: the chat's setup pane says it before the npm command ({pane!r})")
        screens(p, profile, f"node-required-panel-{tag}")
        send(p, "openPanel", name="settings", value="models")
        until(lambda: js(p, "!!document.querySelector('#set-ai .byo-row')"), 15)
        said = how(p, "Npm agent")
        check(first(said, line, f"Run this in {shell}, then come back:") and NPM in said, f"...and so does Add in Settings > Models ({said!r})")
        screens(p, profile, f"node-required-models-{tag}")
        said = how(p, "Pip agent")
        check("pipx install pip-agent" in said and "Node.js" not in said, f"An app that installs another way says nothing about Node.js ({said!r})")
        send(p, "aiHarness", harness="claude")
        time.sleep(1)
        send(p, "aiSend", text="hello there")
        check(until(lambda: [x for x in prompts(bin) if "--session-id" in x["args"]], 20), "A message runs on the Claude stand-in")
        new = [x["prompt"] for x in prompts(bin) if "--session-id" in x["args"]]
        check(new and all(RULE in x for x in new), "The companion instructions say to name Node.js before an npm install")
        check(new and all((RULE_MISSING in x) != node for x in new), f"...and {'not ' if node else ''}that Node.js is missing")
        errors = rpc(p).get("shellErrors")
        check(not errors, f"No interface errors ({errors})" if errors else "No interface errors")
    finally:
        stop(p)


def setup_step(node):
    line, tag = (NEEDED, "found") if node else (MISSING, "missing")
    p, bin, profile = start(f"setup-{tag}", node, fresh=True)
    try:
        until(lambda: js(p, "!!document.querySelector('.welcome.ob .intro-skip')"), 20)
        js(p, "document.querySelector('.intro-skip')?.click()")
        until(lambda: js(p, "[...document.querySelectorAll('.ob-foot button')].some(b => b.innerText.includes('Create your companion'))"), 15)
        time.sleep(1)
        js(p, "[...document.querySelectorAll('.ob-foot button')].find(b => b.innerText.includes('Create your companion'))?.click()")
        until(lambda: js(p, "!!document.querySelector('.welcome .byo-main')"), 15)
        js(p, "document.querySelector('.welcome .byo-more[aria-expanded=false]')?.click()")
        until(lambda: js(p, "(e => { e?.click(); return !!e })([...document.querySelectorAll('.welcome .byo-main')].find(b => b.innerText.includes('Npm agent')))"), 6)
        card = until(lambda: js(p, "(e => e && e.innerText.includes('Install Npm agent') && e.innerText)(document.querySelector('.ob-connect'))"), 10) or ""
        check(first(card, line, "Get it from npm-agent.example") and NPM in card, f"Node.js {tag}: setup's Connect step says it first ({card!r})")
        time.sleep(1.5)  # the step fades in
        screens(p, profile, f"node-required-setup-{tag}")
    finally:
        stop(p)


def main():
    RUN.mkdir(parents=True)
    for node in (True, False):
        settings_and_chat(node)
        setup_step(node)
    if FAILED:
        print(f"FAILED {len(FAILED)}: {FAILED} -> {RUN}")
    else:
        print("PASSED")
        shutil.rmtree(RUN, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
