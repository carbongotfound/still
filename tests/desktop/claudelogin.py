"""Claude Code keeps its login settings, every other AI app still loses its keys, and Claude's card says who gets billed.

- Claude Code's status check and runs see ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, CLAUDE_CODE_USE_BEDROCK and
  CLAUDE_CODE_USE_VERTEX. ANTHROPIC_BASE_URL is still removed.
- ChatGPT, Grok, Gemini and OpenCode see none of the API keys, in their checks or their runs.
- Claude's card in Settings > Models, and setup's card, say what a run will use and who's billed, from what Claude Code's
  own status says. A plain sign-in says nothing extra, and the chat stops saying "Your Claude plan" when it isn't one.
- A refused key stays on screen as an error and starts no sign-in, because signing in wouldn't help: the key would still
  win. An expired sign-in still starts one, then the message runs again by itself.

Stand-in apps only (STILL_QA_CLIS puts them ahead of anything installed), with made-up values. No real AI runs and nothing
signs in. The stand-in's status answers in the shape Claude Code 2.1.318 does; the suite stops before picking anything if
Still isn't running the stand-in.

Run: python tests/desktop/claudelogin.py artifacts/Still-QA/Still.exe
Out: artifacts/claudelogin-*/
"""
import json
import os
from pathlib import Path
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, text, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("claudelogin-" + uuid.uuid4().hex[:8])
APPS = {"claude": "claude", "chatgpt": "codex", "grok": "grok", "gemini": "gemini", "opencode": "opencode"}
OTHER_APPS = [a for a in APPS if a != "claude"]
KEPT = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"]
REMOVED = ["ANTHROPIC_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_BASE_URL", "GOOGLE_GENAI_USE_VERTEXAI"]
CLEAN = {k: v for k, v in os.environ.items() if k not in KEPT + REMOVED + ["CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_OAUTH_TOKEN"]}
KEY = "Using an API key from your environment. Your API account is billed."
results = []

FAKE = textwrap.dedent(r'''
    import json, os, sys, time
    APP = "APP_NAME"
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    quick = args[:1] in (["status"], ["models"], ["--version"], ["mcp"], ["debug"]) or args[:2] == ["login", "status"] or "status" in args or "login" in args
    call = os.path.join(here, "calls", f"{time.time_ns()}-{os.getpid()}")  # the apps start at once: one file per call, whole or not there yet
    with open(call + ".tmp", "w") as log:
        json.dump({"app": APP, "args": args, "run": not quick, "keys": sorted(k for k in WATCHED if k in os.environ)}, log)
    os.replace(call + ".tmp", call + ".json")
    def say(e): print(json.dumps(e), flush=True)
    if APP == "chatgpt" and args[:2] == ["login", "status"]: print("Logged in using ChatGPT"); sys.exit(0)
    if APP == "grok" and args[:1] == ["models"]: print("  * grok-standin"); sys.exit(0)
    if APP == "opencode" and args[:1] == ["models"]: print("anthropic/claude-standin"); sys.exit(0)
    if APP != "claude":
        if not quick and APP != "grok": sys.stdin.read()
        sys.exit(0)
    if "status" in args:
        env = os.environ.get
        provider = "bedrock" if env("CLAUDE_CODE_USE_BEDROCK") else "vertex" if env("CLAUDE_CODE_USE_VERTEX") else "foundry" if env("CLAUDE_CODE_USE_FOUNDRY") else "firstParty"
        saved = os.path.exists(os.path.join(here, "signed-in"))
        method = "third_party" if provider != "firstParty" else "oauth_token" if env("ANTHROPIC_AUTH_TOKEN") else "api_key" if env("ANTHROPIC_API_KEY") else "claude.ai" if saved else "none"
        status = {"loggedIn": method != "none", "authMethod": method, "apiProvider": provider}
        if method == "api_key": status["apiKeySource"] = "ANTHROPIC_API_KEY"
        print(json.dumps(status))
        sys.exit(0 if status["loggedIn"] else 1)
    if "login" in args:
        open(os.path.join(here, "relogged"), "w").close()
        sys.exit(0)
    prompt = sys.stdin.read()
    session = args[args.index("--session-id") + 1] if "--session-id" in args else args[args.index("--resume") + 1] if "--resume" in args else "standin"
    say({"type": "system", "subtype": "init", "session_id": session})
    refused = "Invalid API key · Fix external API key" if "REFUSE" in prompt else "Not logged in · Please run /login" if "EXPIRED" in prompt and not os.path.exists(os.path.join(here, "relogged")) else ""
    if refused:
        if "TOLD" in prompt:  # Claude Code 2.1.318 also says it as a message, which Still shows as the reply
            say({"type": "assistant", "message": {"content": [{"type": "text", "text": refused}]}, "error": "authentication_failed", "session_id": session})
        say({"type": "result", "subtype": "success", "is_error": True, "result": refused, "session_id": session})
        sys.exit(1)
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Stand-in reply"}]}, "session_id": session})
    say({"type": "result", "subtype": "success", "is_error": False, "session_id": session})
''').replace("WATCHED", json.dumps(KEPT + REMOVED))


def check(ok, name):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def start(name, env=None, login=True, fresh=False):
    """Still on its own profile with the stand-ins first in line. fresh: a new profile, which opens on setup."""
    folder = RUN / name
    bin, profile = folder / "bin", folder / "profile"
    (bin / "calls").mkdir(parents=True)
    profile.mkdir()
    for app, command in APPS.items():
        (bin / f"{app}.py").write_text(FAKE.replace("APP_NAME", app), encoding="utf-8")
        launcher(bin / command, bin / f"{app}.py")
    if login:
        (bin / "signed-in").write_text("")
    google = folder / "gemini-home" / ".gemini"  # signed in with Google, as Gemini CLI saves it
    google.mkdir(parents=True)
    (google / "settings.json").write_text('{"security": {"auth": {"selectedType": "oauth-personal"}}}')
    (google / "oauth_creds.json").write_text("{}")
    if not fresh:
        (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True},
                                                        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, profile, {**CLEAN, "STILL_QA_CLIS": str(bin), "GEMINI_CLI_HOME": str(folder / "gemini-home"), **(env or {})}), bin


def stop(p):
    try:
        rpc(p, "quit")
        p.wait(timeout=15)
    except Exception:
        p.kill()


def calls(bin, app="claude"):
    logged = [json.loads(f.read_text()) for f in sorted((bin / "calls").glob("*.json"))]
    return [c for c in logged if c["app"] == app]


def statuses(bin):
    return [c for c in calls(bin) if "status" in c["args"]]


def models(p, bin):
    """Settings > Models, and proof Still is running the stand-in. Without that, nothing gets picked or sent."""
    send(p, "openPanel", name="settings", value="models")
    until(lambda: js(p, "!!document.querySelector('#set-ai .byo .byo-row')"), 15)
    send(p, "aiCheck")
    if not until(lambda: statuses(bin), 20):
        check(False, "Still runs the stand-in Claude")
        stop(p)
        raise SystemExit(1)


def card(p, name="Claude"):
    return js(p, f"[...document.querySelectorAll('.byo-row')].find(r => r.querySelector('strong')?.innerText.trim() === {json.dumps(name)})?.innerText ?? ''") or ""


def close(p):
    js(p, "(document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    time.sleep(.5)


def ask(p, words, app="claude"):
    send(p, "aiHarness", harness=app)
    send(p, "aiNew")
    send(p, "aiSend", text=words)


def everything():
    """Every setting at once: what each app sees, in its check and in a run."""
    env = {**{k: "not-real" for k in REMOVED + ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"]}, "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_USE_VERTEX": "1"}
    p, bin = start("everything", env)
    try:
        models(p, bin)
        first = statuses(bin)[0]
        check(first["keys"] == KEPT, f"Claude's status check sees its four login settings and nothing else ({first['keys']})")
        at = first["args"].index("--setting-sources") if "--setting-sources" in first["args"] else -1
        check(at >= 0 and first["args"][at + 1] == "project,local", "It checks with the setting sources a run uses, so the card and the run agree")
        check(until(lambda: "Using Amazon Bedrock from your environment. Your AWS account is billed." in card(p), 10), f"The card says a cloud provider wins, as Claude Code's own status does ({card(p)!r})")
        check(js(p, "document.querySelectorAll('.byo-billing').length") == 1, "No other app's card says anything about billing")
        close(p)
        send(p, "aiToggle")
        ask(p, "hello")
        run = until(lambda: [c for c in calls(bin) if c["run"]], 20)
        check(run and run[0]["keys"] == KEPT, f"A Claude run sees its four login settings ({run and run[0]['keys']})")
        check(run and "ANTHROPIC_BASE_URL" not in run[0]["keys"], "ANTHROPIC_BASE_URL is still removed, from Claude too")
        check(until(lambda: "Stand-in reply" in (text(p) or ""), 15), "The run answers in the chat")
        for app in OTHER_APPS:
            ask(p, "hello", app)
            ran = until(lambda: [c for c in calls(bin, app) if c["run"]], 20)
            seen = sorted({k for c in calls(bin, app) for k in c["keys"]})
            check(ran and not seen, f"{app} ran and saw no API keys, in its checks or its run ({seen})")
    finally:
        stop(p)


def refused_key():
    """A saved sign-in and a key: the key wins (the real one does, in a run), the card says so, and refusal isn't a sign-out."""
    p, bin = start("key", {"ANTHROPIC_API_KEY": "not-real"})
    try:
        models(p, bin)
        check(until(lambda: KEY in card(p), 10), f"A key with a saved sign-in: the card says the API account is billed ({card(p)!r})")
        check("Logged in" not in card(p), "and doesn't say Logged in")
        rpc(p, "capture", name="card.png")  # saved in the profile folder
        close(p)
        send(p, "aiToggle")
        ask(p, "hello")
        check(until(lambda: "Stand-in reply" in (text(p) or ""), 15), "A run answers")
        usage = until(lambda: js(p, "document.querySelector('.ai-usage')?.innerText"), 5) or ""
        check(KEY in usage and "Your Claude plan" not in usage, f"The chat says the same, not Your Claude plan ({usage!r})")
        for words, how in (("REFUSE TOLD this", "as Claude Code 2.1.318 reports it"), ("REFUSE this", "reported only in the result line")):
            ask(p, words)
            check(until(lambda: "Invalid API key" in (text(p) or ""), 15), f"A refused key stays on screen, {how}")
            time.sleep(1.5)
            check(not (bin / "relogged").exists(), "and starts no sign-in")
    finally:
        stop(p)


def other_logins():
    """What the card says for each of the rest."""
    for name, env, line in (("token", {"ANTHROPIC_AUTH_TOKEN": "not-real"}, "Using an auth token from your environment. The account it belongs to is billed."),
                            ("vertex", {"CLAUDE_CODE_USE_VERTEX": "1"}, "Using Google Cloud from your environment. Your Google Cloud account is billed."),
                            ("foundry", {"CLAUDE_CODE_USE_FOUNDRY": "1"}, "Using Microsoft Foundry from your environment. Your Azure account is billed.")):
        p, bin = start(name, env)
        try:
            models(p, bin)
            check(until(lambda: line in card(p), 10), f"{name}: {line}")
        finally:
            stop(p)


def plain_sign_in():
    """Claude's own sign-in: nothing extra, and an expired one still signs in here and runs the message again."""
    p, bin = start("plain")
    try:
        models(p, bin)
        check(until(lambda: "Logged in" in card(p), 10) and not js(p, "!!document.querySelector('.byo-billing')"), f"A plain sign-in says Logged in and nothing about billing ({card(p)!r})")
        close(p)
        send(p, "aiToggle")
        ask(p, "hello")
        check(until(lambda: "Stand-in reply" in (text(p) or ""), 15), "A run answers")
        usage = until(lambda: js(p, "document.querySelector('.ai-usage')?.innerText"), 5) or ""
        check("Your Claude plan" in usage, f"The chat says Your Claude plan ({usage!r})")
        ask(p, "EXPIRED this")
        check(until(lambda: (bin / "relogged").exists(), 15), "An expired sign-in, reported only in the result line, starts Claude's own sign-in")
        check(until(lambda: len([c for c in calls(bin) if c["run"]]) >= 3, 15) and until(lambda: "Stand-in reply" in (text(p) or "") and "Not logged in" not in (text(p) or ""), 15), "and the message runs again by itself")
    finally:
        stop(p)
    p, bin = start("out", login=False)
    try:
        models(p, bin)
        check(until(lambda: "Set up" in card(p), 10) and "Logged in" not in card(p) and not js(p, "!!document.querySelector('.byo-billing')"), f"Signed out: Set up, and nothing about billing ({card(p)!r})")
    finally:
        stop(p)


def setup_card():
    """Setup's Connect step says it too, instead of "signed in"."""
    p, bin = start("setup", {"ANTHROPIC_API_KEY": "not-real"}, fresh=True)
    try:
        until(lambda: js(p, "!!document.querySelector('.welcome.ob .intro-skip')"), 20)
        js(p, "document.querySelector('.intro-skip')?.click()")
        until(lambda: js(p, "[...document.querySelectorAll('.ob-foot button')].some(b => b.innerText.includes('Create your companion'))"), 15)
        time.sleep(1)
        js(p, "[...document.querySelectorAll('.ob-foot button')].find(b => b.innerText.includes('Create your companion'))?.click()")
        until(lambda: js(p, "!!document.querySelector('.byo-row')"), 15)
        if not until(lambda: statuses(bin), 20):
            check(False, "Still runs the stand-in Claude in setup")
            return
        js(p, "[...document.querySelectorAll('.byo-row')].find(r => r.querySelector('strong')?.innerText.trim() === 'Claude')?.querySelector('.byo-main')?.click()")
        ready = until(lambda: js(p, "document.querySelector('.ob-ready')?.innerText"), 15) or ""
        check(f"Claude is ready. {KEY}" in ready, f"Setup says who's billed ({ready!r})")
        how = js(p, "document.querySelector('.ob-how')?.textContent") or ""
        check("What you send goes to your AI provider" in how, f"How this works doesn't say it all goes to Anthropic ({how!r})")
    finally:
        stop(p)


def main():
    RUN.mkdir(parents=True)
    everything()
    refused_key()
    other_logins()
    plain_sign_in()
    setup_card()
    print(f"{'PASSED' if all(results) else 'FAILED'} {sum(results)}/{len(results)}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
