"""Still never runs an AI app's sign-in for the user. When Claude Code, the ChatGPT app or Grok Build needs signing in,
Still shows the command to run in a terminal, with Copy, and "I'm done" checks the connection again.

- Settings > Models: Set up on a signed-out app shows "To connect your <app> plan, open a terminal and run:", the app's
  own command in a code block (claude auth login, codex login, grok login --device-auth), Copy and I'm done.
- Picking a signed-out app, the old aiLogin message, I'm done while still signed out, a message sent while signed out
  and a sign-in that expires mid-chat: none of them starts a sign-in. The chat shows the same steps, and once the user
  has signed in (here: the stand-in's sign-in file appears), I'm done runs the waiting message.
- Setup's Connect step shows the same steps.
- The companion instructions say never to run a sign-in or auth command for the user.

Every call to the stand-in apps is logged; the only ones allowed to name login or auth are status checks.

Run: python tests/desktop/no_login.py artifacts/Still-QA/Still.exe
Out: artifacts/no-login-*/ (kept when something fails), artifacts/screens/no-login-*.png
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
from qa import CREW, ROOT, js, launch, launcher, rpc, screens, send, text, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("no-login-" + uuid.uuid4().hex[:8])
APPS = {"claude": "claude", "chatgpt": "codex", "grok": "grok"}
COMMANDS = {"Claude": "claude auth login", "ChatGPT": "codex login", "Grok": "grok login --device-auth"}
RULE = "Never run a sign-in or auth command"
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_", "OPENAI_", "CODEX_", "XAI_", "GROK_"))}
FAILED = []

FAKE = textwrap.dedent(r'''
    import json, os, sys, time
    APP = "APP_NAME"
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    signed = os.path.exists(os.path.join(here, APP + "-signed-in"))
    quick = "status" in args or "login" in args or "auth" in args or args[:1] in (["models"], ["--version"], ["mcp"], ["debug"])
    prompt = "" if quick else sys.stdin.read()
    call = os.path.join(here, "calls", f"{time.time_ns()}-{os.getpid()}")
    with open(call + ".tmp", "w") as log:
        json.dump({"app": APP, "args": args, "run": not quick, "rule": "RULE" in prompt}, log)
    os.replace(call + ".tmp", call + ".json")
    def say(e): print(json.dumps(e), flush=True)
    if APP == "chatgpt" and args[:2] == ["login", "status"]: print("Logged in using ChatGPT" if signed else "Not logged in"); sys.exit(0 if signed else 1)
    if APP == "grok" and args[:1] == ["models"]: print("  * grok-standin" if signed else "Error: not authenticated"); sys.exit(0 if signed else 1)
    if APP != "claude": sys.exit(0)
    if "status" in args:
        print(json.dumps({"loggedIn": signed, "authMethod": "claude.ai" if signed else "none", "apiProvider": "firstParty"}))
        sys.exit(0 if signed else 1)
    if quick: sys.exit(0)  # a sign-in: logged above, and the test fails on it
    session = args[args.index("--session-id") + 1] if "--session-id" in args else args[args.index("--resume") + 1] if "--resume" in args else "standin"
    say({"type": "system", "subtype": "init", "session_id": session})
    if not signed:
        say({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login", "session_id": session})
        sys.exit(1)
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Stand-in reply " + str(time.time_ns())}]}, "session_id": session})
    say({"type": "result", "subtype": "success", "is_error": False, "session_id": session})
''').replace("RULE", RULE)


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        FAILED.append(label)


def start(name, fresh=False):
    folder = RUN / name
    bin, profile = folder / "bin", folder / "profile"
    (bin / "calls").mkdir(parents=True)
    profile.mkdir()
    for app, command in APPS.items():
        (bin / f"{app}.py").write_text(FAKE.replace("APP_NAME", app), encoding="utf-8")
        launcher(bin / command, bin / f"{app}.py")
    if not fresh:
        (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "claude"},
                                                        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, profile, {**CLEAN, "STILL_QA_CLIS": str(bin)}), bin, profile


def stop(p):
    try:
        rpc(p, "quit")
        p.wait(timeout=15)
    except Exception:
        p.kill()


def calls(bin):
    return [json.loads(f.read_text()) for f in sorted((bin / "calls").glob("*.json"))]


def sign_ins(bin):
    """Every call that would sign in: names login or auth and isn't a status check."""
    return [c for c in calls(bin) if any(a in ("login", "auth") for a in c["args"]) and "status" not in c["args"]]


def no_sign_in(bin, when):
    time.sleep(1.5)
    found = sign_ins(bin)
    check(not found, f"{when}: no sign-in started ({[c['app'] + ' ' + ' '.join(c['args']) for c in found]})")


def steps(p, scope):
    """The sign-in steps shown in scope: their words, the command, and whether Copy and I'm done are there (I'm done readable: its text isn't its background's colour)."""
    return js(p, f"""(s => s && {{ text: s.innerText, code: s.querySelector('code')?.textContent ?? '',
        copy: [...s.querySelectorAll('button')].some(b => b.innerText.trim() === 'Copy'),
        done: (b => !!b && b.innerText.trim() === "I'm done" && getComputedStyle(b).color !== getComputedStyle(b).backgroundColor)(s.querySelector('.signin-done')) }})(document.querySelector({json.dumps(scope + ' .signin-steps')}))""")


def words_ok(s, name):
    return bool(s) and f"To connect your {name} plan, open a terminal and run:" in s["text"] and "Finish the sign-in in your browser, then tell me when you're done." in s["text"]


def row(p, name):
    return f"[...document.querySelectorAll('.byo-row')].find(r => r.querySelector('strong')?.innerText.trim() === {json.dumps(name)})"


def done(p, scope):
    js(p, f"document.querySelector({json.dumps(scope + ' .signin-done')})?.click()")


def settings():
    p, bin, profile = start("settings")
    try:
        send(p, "openPanel", name="settings", value="models")
        until(lambda: js(p, "!!document.querySelector('#set-ai .byo-row')"), 15)
        send(p, "aiCheck")
        if not until(lambda: [c for c in calls(bin) if "status" in c["args"]], 20):
            check(False, "Still runs the stand-in apps")
            return
        for name, command in COMMANDS.items():
            check(until(lambda: js(p, f"!!{row(p, name)}?.querySelector('.byo-act[aria-expanded]')"), 10), f"{name} signed out: its card has Set up")
            js(p, f"{row(p, name)}?.querySelector('.byo-act[aria-expanded]')?.click()")
            s = until(lambda: steps(p, "#set-ai .byo-how"), 3)
            check(words_ok(s, name) and s["code"] == command and s["copy"] and s["done"],
                  f"...which shows the terminal command in a code block, with Copy and I'm done ({s and s['code']!r})")
            if name == "Claude":
                screens(p, profile, "no-login-models")
                done(p, "#set-ai .byo-how")
                no_sign_in(bin, "I'm done while still signed out")
            js(p, f"{row(p, name)}?.querySelector('.byo-act[aria-expanded]')?.click()")
            js(p, f"{row(p, name)}?.querySelector('.byo-main')?.click()")
            no_sign_in(bin, f"Picking signed-out {name}")
        send(p, "aiHarness", harness="claude")
        send(p, "aiLogin")
        no_sign_in(bin, "The old aiLogin message")
    finally:
        stop(p)
    return bin


def chat():
    p, bin, profile = start("chat")
    try:
        send(p, "aiCheck")
        until(lambda: [c for c in calls(bin) if "status" in c["args"]], 20)
        send(p, "aiToggle")
        panel = ".ai-sidebar"
        s = until(lambda: steps(p, panel), 15)
        check(words_ok(s, "Claude") and s["code"] == "claude auth login" and s["copy"] and s["done"],
              f"Signed out, the side panel says how to sign in from a terminal, with the command to copy ({s and s['text']!r})")
        check(js(p, "document.querySelector('.ai-sidebar .ai-pane h3')?.textContent") == "Connect Claude", "...under Connect Claude")
        screens(p, profile, "no-login-panel")
        send(p, "aiSend", text="hello there")
        check(until(lambda: js(p, "document.querySelector('.ai-sidebar .ai-pane')?.innerText.includes('Your message runs as soon as Claude is ready')"), 15),
              "A message sent while signed out waits")
        no_sign_in(bin, "A message sent while signed out")
        done(p, panel)
        said = until(lambda: js(p, "document.querySelector('.ai-sidebar .signin-error')?.textContent"), 10) or ""
        check("Claude Code isn't signed in yet" in said, f"I'm done while still signed out says so ({said!r})")
        no_sign_in(bin, "I'm done while still signed out")
        (bin / "claude-signed-in").write_text("")  # the user signed in, in their own terminal
        done(p, panel)
        check(until(lambda: "Stand-in reply" in (text(p) or ""), 20), "Signed in, I'm done checks again and the waiting message runs")
        new = [c for c in calls(bin) if c["run"] and "--session-id" in c["args"]]  # a resumed run doesn't bring the instructions again
        check(new and all(c["rule"] for c in new), f"The companion's instructions say: {RULE} for the user")
        (bin / "claude-signed-in").unlink()  # the sign-in expires mid-chat
        before = len([c for c in calls(bin) if c["run"]])
        send(p, "aiSend", text="and again")
        check(until(lambda: len([c for c in calls(bin) if c["run"]]) > before and steps(p, panel), 20), "An expired sign-in mid-chat shows the terminal steps")
        no_sign_in(bin, "An expired sign-in mid-chat")
        replies = (text(p) or "").count("Stand-in reply")
        (bin / "claude-signed-in").write_text("")
        done(p, panel)
        check(until(lambda: (text(p) or "").count("Stand-in reply") > replies, 20), "...and after signing in again, I'm done runs the message")
        errors = rpc(p).get("shellErrors")
        check(not errors, f"No interface errors ({errors})" if errors else "No interface errors")
    finally:
        stop(p)
    return bin


def setup_step():
    p, bin, profile = start("setup", fresh=True)
    try:
        until(lambda: js(p, "!!document.querySelector('.welcome.ob .intro-skip')"), 20)
        js(p, "document.querySelector('.intro-skip')?.click()")
        until(lambda: js(p, "[...document.querySelectorAll('.ob-foot button')].some(b => b.innerText.includes('Create your companion'))"), 15)
        time.sleep(1)
        js(p, "[...document.querySelectorAll('.ob-foot button')].find(b => b.innerText.includes('Create your companion'))?.click()")
        until(lambda: js(p, "!!document.querySelector('.byo-row')"), 15)
        if not until(lambda: [c for c in calls(bin) if "status" in c["args"]], 20):
            check(False, "Still runs the stand-in apps in setup")
            return bin
        js(p, f"{row(p, 'Claude')}?.querySelector('.byo-main')?.click()")
        s = until(lambda: steps(p, ".ob-connect"), 15)
        check(words_ok(s, "Claude") and s["code"] == "claude auth login" and s["copy"] and s["done"], f"Setup's Connect step shows the same steps ({s and s['text']!r})")
        check(not js(p, "[...document.querySelectorAll('.byo-row .byo-act')].some(b => b.innerText.includes('Set up'))"), "...once: the list itself has no second Set up")
        screens(p, profile, "no-login-setup")
        send(p, "preference", key="theme", value="Dark")
        time.sleep(.8)
        check((steps(p, ".ob-connect") or {}).get("done"), "...and I'm done is readable in dark too")
        send(p, "preference", key="theme", value="Light")
        no_sign_in(bin, "Picking signed-out Claude in setup")
        done(p, ".ob-connect")
        no_sign_in(bin, "I'm done in setup while still signed out")
        (bin / "claude-signed-in").write_text("")
        done(p, ".ob-connect")
        check(until(lambda: js(p, "document.querySelector('.ob-ready')?.innerText.includes('Claude is ready')"), 15), "Signed in, I'm done shows Claude is ready")
    finally:
        stop(p)
    return bin


def main():
    RUN.mkdir(parents=True)
    bins = [b for b in (settings(), chat(), setup_step()) if b]
    every = [c for b in bins for c in calls(b)]
    check(every and not [c for b in bins for c in sign_ins(b)], f"Across the run, {len(every)} calls to the stand-in apps and not one sign-in")
    if FAILED:
        print(f"FAILED {len(FAILED)}: {FAILED} -> {RUN}")
    else:
        print("PASSED")
        shutil.rmtree(RUN, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
