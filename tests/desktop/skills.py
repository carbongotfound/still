"""Skills load when they fit, the model tiers run what Settings says, and a model that isn't on the plan falls back.

Checks that a companion's first turn carries an index of its skills (under its cap) and no skill bodies, that load_skill
gives the body of any skill with a "Used skill" step (every skill is for every companion) and refuses one limited to
another companion or an id that doesn't exist, that typing /skill still
brings the body in, that a tier's model and effort reach the AI app and can be reset, that a model the app refuses is
retried once on its default model with a note in the chat, that next steps show as suggestion rows with an icon, that an image or a video link
shows as a card (the image only on Show image, fetched by Still within its limits), and that the end of a reply sits
close to the message box. Choices: every app is told about the choices block; a card offers one pick, several then
Submit, a dropdown, or your own words; the pick goes back as your reply, and a card takes one answer. A block that isn't
valid JSON stays as text. A reply has no Took line, its Copy shows on hover, and message text selects and copies. A tier saved before launch shows in Settings, as after a restart.
A skill added from a link (it has a source) counts as reading from the web when it loads or is typed; Still's own don't.

Usage: python tests/desktop/skills.py <QA exe>
The fake AI app (its models: good and notonplan) answers the last line of its prompt:
  SKILL: <id> [<id>...]   calls load_skill with each id and writes what it got to results.jsonl
  NEXT                    replies with a paragraph and three next steps
  CHOOSE / MULTI / DROP   replies with a choices block: one pick and your own words / several / a dropdown
  BADJSON                 replies with a choices block that isn't JSON
  STEPS                   says a line, takes a step, says another, takes a step, then answers
  MEDIA                   replies with an image whose address doesn't answer and a YouTube link with a start time
  anything else           replies "Okay."
With --model notonplan it answers the way Claude Code does for a model the user can't use, and exits 1.
"""
import base64
import http.server
import json
import sys
import threading
import textwrap
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("skills-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}
CAP = 4800  # Skill.IndexCap
# The gap between the end of the chat and the message box: TYPE puts one line or ten in the box, GAP measures.
VIEW = "[...document.querySelectorAll('.chat-view')].find(v => v.dataset.mode === %s && v.offsetParent)"
TYPE = """(() => { const view = """ + VIEW + """, field = view?.querySelector('[aria-label=Message]'), log = view?.querySelector('.ai-log'); if (!field) return false;
 field.focus(); getSelection().selectAllChildren(field); document.execCommand('delete');
 %s.forEach((line, i) => { if (i) document.execCommand('insertLineBreak'); if (line) document.execCommand('insertText', false, line) });
 setTimeout(() => { log.scrollTop = log.scrollHeight }, 150); return true })()"""
GAP = """(() => { const view = """ + VIEW + """, log = view?.querySelector('.ai-log'), box = view?.querySelector('.ai-compose'); if (!log || !box) return null;
 const items = log.querySelectorAll('.chat-column > *'), last = items[items.length - 1].getBoundingClientRect(), b = box.getBoundingClientRect();
 return { gap: Math.round(b.top - last.bottom), visible: last.bottom <= log.getBoundingClientRect().bottom + 1, box: Math.round(b.height) } })()"""
REFUSED = "There's an issue with the selected model (notonplan). It may not exist or you may not have access to it. Run --model to pick a different model."


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "runs.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"args": args, "prompt": prompt}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    def text(t): say({"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}})
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if "--model" in args and args[args.index("--model") + 1] == "notonplan":
        text(REFUSED)
        say({"type": "result", "subtype": "success", "is_error": True, "result": REFUSED})
        sys.exit(1)
    last = next((l for l in reversed(prompt.strip().splitlines()) if l.strip()), "")
    verb, _, rest = last.partition(": ")
    if verb == "SKILL":
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
        out = {"tools": [t["name"] for t in request("tools/list", {})["result"]["tools"]], "calls": []}
        for skill in rest.split():
            r = request("tools/call", {"name": "load_skill", "arguments": {"id": skill}})["result"]
            out["calls"].append({"id": skill, "error": bool(r.get("isError")), "text": r["content"][0].get("text", "")})
        with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(out) + "\n")
        still.stdin.close()
        text("Done.")
    elif verb == "MEDIA":
        text("Here's the lamp I found.\n\n![A blue desk lamp](https://127.0.0.1:9/lamp.png)\n\n[How desk lamps work](https://youtu.be/abcDEF12345?t=95)")
    elif verb == "CHOOSE":
        text('Two good ones.\n\n```choices\n{"question": "Where to?", "type": "single", "options": ["Lisbon", "Porto"], "other": true}\n```')
    elif verb == "MULTI":
        text('Pick what matters.\n\n```choices\n{"question": "Which should I compare?", "type": "multiple", "options": ["Price", "Weight", "Battery"]}\n```')
    elif verb == "DROP":
        text('Which day?\n\n```choices\n{"question": "Pick a day", "type": "dropdown", "options": ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7", "Day 8", "Day 9"]}\n```')
    elif verb == "SETLINK":
        text("Fewer check-ins? [Have Jonah check in more](still:settings/autonomy/Jonah?to=ask), [use the dark theme](still:settings/theme?to=Dark) or see [your permissions](still:settings/permissions).")
    elif verb == "RATE":
        text("Here's **the plan**: book `Alfama House` and see [the map](https://example.com/map).")
    elif verb == "STEPS":
        for n, line in enumerate(["Found it. Pulling frames now.", "Going through the frames now."]):
            text(line)
            say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t%d" % n, "name": "mcp__still__list_tabs", "input": {}}]}})
            say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t%d" % n, "content": "[]"}]}})
        text("All done: the frames are in.")
    elif verb == "BADJSON":
        text("Here's a list.\n\n```choices\nnot json at all\n```")
    elif verb == "NEXT":
        text("Here's the short version: the blue one is cheaper.\n\n**Next steps**\n>> Compare the two cheapest options\n>> **Check delivery times**\n>> Save the table")
    else:
        text("Okay.")
''').replace("REFUSED", json.dumps(REFUSED))


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
FILES = {"/lamp.png": ("image/png", PNG), "/page.png": ("text/html", b"<p>not a picture</p>"), "/big.png": ("image/png", PNG + b"\0" * 5_100_000)}


class Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        kind, body = FILES.get(self.path, ("text/plain", b"missing"))
        self.send_response(200 if self.path in FILES else 404)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


# Asks Still for a picture the way a card does; the answer lands in window.__media.
FETCH = """(() => { if (!window.__media) { window.__media = {}; window.chrome.webview.addEventListener('message', e => { if (e.data?.kind === 'media') window.__media[e.data.data.url] = e.data.data }) }
 window.chrome.webview.postMessage({ op: 'mediaFetch', url: %s }); return true })()"""
CARDS = "[...[...document.querySelectorAll('.chat-view .md')].pop()?.querySelectorAll('.md-media') ?? []]"


def lines(name):
    file = BIN / name if name != "qa-prompts.jsonl" else PROFILE / name
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines() if l.strip()] if file.exists() else []


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def chat(cid):
    return next((c for c in chats() if c["Id"] == cid), {"Messages": []})


def settled(cid):
    return until(lambda: (c := chat(cid)) and c.get("Id") and not c.get("Running") and any(m["Role"] == "assistant" for m in c["Messages"]), 60)


def start(p, companion, text):
    before = {c["Id"] for c in chats()}
    send(p, "new")
    until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    send(p, "aiSend", text=text, home=True, companion=companion)
    cid = until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before), None), 20)
    settled(cid)
    return cid


def again(p, cid, text):
    send(p, "chatOpen", id=cid)
    until(lambda: next((t for t in rpc(p)["tabs"] if t.get("ChatId") == cid), None) and js(p, "!!document.querySelector('.chat-view [aria-label=Message]')"), 10)
    n = len(chat(cid)["Messages"])
    send(p, "aiSend", text=text)
    until(lambda: len(chat(cid)["Messages"]) > n + 1 and not chat(cid).get("Running"), 60)


CARD = "[...document.querySelectorAll('.chat-view .choice-card')].pop()"


def card(p):
    """The last choice card: its question, options, picked ones, and whether it's answered and takes no more."""
    return js(p, "(c => c && { q: c.querySelector('.choice-q')?.innerText ?? '', options: [...c.querySelectorAll('.ask-option')].map(b => b.innerText.trim()),"
                 " on: [...c.querySelectorAll('.ask-option[aria-pressed=true], .ask-option[aria-checked=true]')].map(b => b.innerText.trim()), done: c.hasAttribute('data-done'),"
                 " off: [...c.querySelectorAll('button, input')].every(b => b.disabled), own: !!c.querySelector('[aria-label=\"Type your own\"]'),"
                 " select: c.querySelector('.choice-select')?.innerText.trim() ?? null })(" + CARD + ")") or {}


def option(p, words):
    return js(p, f"(c => {{ const b = [...(c?.querySelectorAll('.ask-option') ?? [])].find(b => b.innerText.trim() === {json.dumps(words)}); b?.click(); return !!b && !b.disabled }})({CARD})")


def users(cid):
    return [m["Text"] for m in chat(cid)["Messages"] if m["Role"] == "user"]


def answered(cid, n):
    return until(lambda: len(chat(cid)["Messages"]) > n + 1 and not chat(cid).get("Running"), 60)


def mouse(p, kind, x, y, **more):
    rpc(p, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": x, "y": y, **more})


def drag_select(p, sel):
    """Selects the last element's text with the mouse, from its first character to its last."""
    box = js(p, "(e => { if (!e) return null; const r = document.createRange(); r.selectNodeContents(e); (s => s && r.setEndBefore(s))(e.querySelector(':scope > .msg-files, :scope > .ai-msg-actions')); const q = [...r.getClientRects()].filter(q => q.width)"
                "; if (!q.length) return null; const a = q[0], z = q.at(-1); return [a.left + 1, a.top + a.height / 2, z.right - 1, z.top + z.height / 2] })"
                f"([...document.querySelectorAll({json.dumps(sel)})].pop())")
    if not box:
        return ""
    x0, y0, x1, y1 = box
    js(p, "getSelection().removeAllRanges()")
    mouse(p, "mousePressed", x0, y0, button="left", buttons=1, clickCount=1)
    mouse(p, "mouseMoved", (x0 + x1) / 2, y1, button="left", buttons=1)
    mouse(p, "mouseMoved", x1, y1, button="left", buttons=1)
    mouse(p, "mouseReleased", x1, y1, button="left", buttons=0, clickCount=1)
    return js(p, "getSelection().toString()") or ""


def copy_keys(p):
    """Ctrl+C (Cmd+C on the Mac) as the keyboard sends it; returns what the page's copy saw selected."""
    js(p, "window.__copied = null; document.addEventListener('copy', () => { window.__copied = getSelection().toString() }, { once: true })")
    if MAC:
        rpc(p, "key", key="C", mods="Control", post=True)
    else:
        for kind in ("rawKeyDown", "keyUp"):
            rpc(p, "shellCdp", method="Input.dispatchKeyEvent", parameters={"type": kind, "key": "c", "code": "KeyC", "windowsVirtualKeyCode": 67, "modifiers": 2})
    return until(lambda: js(p, "window.__copied"), 3) or ""


def clipboard():
    """The Windows clipboard's text."""
    import ctypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetClipboardData.restype = k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not u.OpenClipboard(None):
        return None
    try:
        h = u.GetClipboardData(13)  # CF_UNICODETEXT
        if not h:
            return ""
        try:
            return ctypes.wstring_at(k.GlobalLock(h))
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def tiers(p):
    """The fake app's tiers the user picked, as saved: {tier: {model, effort, custom}}."""
    try:
        picked = json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"].get("AiTiers") or {}
    except (OSError, ValueError, KeyError):
        picked = {}
    return {k.split(":", 1)[1]: {"model": v[0], "effort": v[1], "custom": True} for k, v in picked.items() if k.startswith("fake:") and len(v) == 2}


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json",
        "model": ["--model", "{model}"], "effort": ["--effort", "{effort}"], "models": ["good", "notonplan"]}))
    (PROFILE / "skills").mkdir(parents=True)
    (PROFILE / "skills" / "deal-notes.md").write_text("---\nname: Deal notes\ndescription: Jonah's own notes on a deal\nwhen: Notes on a deal\nonly: jonah\n---\n\nJonah's steps.\n", encoding="utf-8")
    (PROFILE / "skills" / "from-web.md").write_text("---\nname: From the web\ndescription: Someone else's skill\nwhen: Testing\nsource: github.com/acme/kit\n---\n\nStep one from someone else.\n", encoding="utf-8")
    crew = [{"Id": "nora", "Name": "Nora", "Job": "Researcher: reads several sources and cites them.", "Crew": "research", "Mode": "default", "Skills": ["from-web"]},
            {"Id": "jonah", "Name": "Jonah", "Job": "Sales: follow-ups and the pipeline.", "Crew": "sales", "Mode": "efficient"}]
    site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    here = f"http://127.0.0.1:{site.server_address[1]}"
    # A Thorough pick saved before launch, as if from an earlier run.
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake",
        "AiTiers": {"fake:expert": ["good", "low"]},
        "Theme": "Light", "Width": 1300, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        send(p, "aiCheck")
        time.sleep(2)

        # The first turn: an index of the companion's skills, no bodies.
        nora = start(p, "nora", "HI")
        first = next((x["prompt"] for x in lines("qa-prompts.jsonl") if x["chat"] == nora), "")
        head = "Your skills. Before you start, check this list"
        at = first.find(head)
        index = first[at:first.find("\n\n", at)] if at >= 0 else ""
        ids = ["claim-check", "market-watch", "option-compare", "research-brief"]
        check(index and all(f"- {i}: " in index for i in ids), "The first turn lists the companion's four skills by id")
        check(0 < len(index) <= CAP, f"and the index stays under its cap ({len(index)} of {CAP} characters)")
        mine_at = max(index.find(f"- {i}: ") for i in ids)
        check(index.find("- follow-up: ") > mine_at, "Every companion can use every skill: Jonah's Follow-up drafts is on Nora's list too, after her own")
        check("- deal-notes: " not in index and "- setup: " not in index, "but not one limited to Jonah, nor Setup")
        check("[Skill \"" not in first and "Agree the options and what matters most" not in first, f"and carries no skill bodies (prompt {len(first)} characters)")

        # load_skill: its own skill, a teammate's kit skill, one limited to someone else, one that doesn't exist.
        steps_before = sum(1 for m in chat(nora)["Messages"] if m["Role"] == "tool")
        again(p, nora, "SKILL: option-compare follow-up deal-notes nope")
        got = (lines("results.jsonl") or [{}])[-1]
        calls = {c["id"]: c for c in got.get("calls", [])}
        check("load_skill" in got.get("tools", []), "The AI is offered load_skill")
        own = calls.get("option-compare", {})
        check(not own.get("error") and "Fix the list of options" in own.get("text", ""), "load_skill gives the body of the companion's own skill")
        used = [m["Text"] for m in chat(nora)["Messages"] if m["Role"] == "tool"][steps_before:]
        check(used.count("Used skill Compare options") == 1, "and the chat shows one step: Used skill Compare options")
        kit = calls.get("follow-up", {})
        check(not kit.get("error") and used.count("Used skill Follow-up drafts") == 1, "A skill from a teammate's kit loads too, with its step: " + kit.get("text", "")[:60])
        theirs = calls.get("deal-notes", {})
        check(theirs.get("error") and "You don't have a skill with the id" in theirs.get("text", ""), "A skill limited to another companion is refused: " + theirs.get("text", "")[:70])
        check(calls.get("nope", {}).get("error"), "and so is an id that doesn't exist")
        check(not any("Deal notes" in s or "nope" in s for s in used), "and neither shows a step")

        # A skill added from a link is someone else's text: once it loads, the chat counts as having read from the web.
        check(chat(nora).get("Read", 0) == 0, "Loading one of Still's skills doesn't count as reading the web")
        again(p, nora, "SKILL: from-web")
        got = (lines("results.jsonl") or [{}])[-1]
        fetched = next((c for c in got.get("calls", []) if c.get("id") == "from-web"), {})
        check(not fetched.get("error") and "Step one from someone else" in fetched.get("text", ""), "A skill added from a link loads like any other")
        check(chat(nora).get("Read", 0) >= 1, "and then the chat counts as having read from the web, so a new site asks first")

        # Typing /skill still brings the body in, with a step.
        n = len(lines("qa-prompts.jsonl"))
        again(p, nora, "/option-compare which is cheaper?")
        typed = (lines("qa-prompts.jsonl")[n:] or [{}])[0].get("prompt", "")
        check("Fix the list of options" in typed, "A /skill the user types brings its body into that turn")
        check(any(m["Role"] == "tool" and m["Text"] == "Used skill Compare options" for m in chat(nora)["Messages"][-4:]), "with a Used skill step")

        # Next steps show as plain muted lines, each with a small arrow, not as a card or a box, and without the markup.
        again(p, nora, "NEXT")
        steps = "[...document.querySelectorAll('.chat-view .ai-next .ai-next-step')]"
        shown = until(lambda: js(p, steps + ".map(b => b.innerText.trim())"), 10) or []
        plain = js(p, steps + ".every(b => (s => s && getComputedStyle(s).borderTopWidth === '0px' && s.getBoundingClientRect().width <= 16)(b.querySelector('svg'))"
                      " && getComputedStyle(b).backgroundColor === 'rgba(0, 0, 0, 0)' && getComputedStyle(b).borderTopWidth === '0px')")
        check(shown == ["Compare the two cheapest options", "Check delivery times", "Save the table"] and plain
              and not js(p, "!![...document.querySelectorAll('.chat-view .ai-turn')].find(t => t.innerText.includes('blue one is cheaper'))?.querySelector('.choice-card')"),
              f"Next steps show as three plain lines with a small arrow, not a card or a box: {shown}")
        body = js(p, "[...document.querySelectorAll('.chat-view .md')].pop()?.innerText || ''") or ""
        check(">>" not in body and "Next steps" not in body and "blue one is cheaper" in body, "and the reply shows without the >> lines or their label")

        time.sleep(1)  # the reply finishes scrolling into view before the picture
        rpc(p, "capture", name="skills-next-steps.png")

        # Choices: every app is told; a pick goes back as the reply, and a card takes one answer.
        check("one choices block" in first and "```choices" in first, "The first turn tells the AI how to offer choices, with an example")
        check("Don't end a reply by asking whether the user wants more" in first and "start with `>> `" in first, "...and to end a reply with next steps, not by asking if you want more")
        step = lambda words: js(p, f"(b => {{ b?.click(); return !!b && !b.disabled }})({steps}.find(b => b.innerText.trim() === {json.dumps(words)}))")  # noqa: E731
        n = len(chat(nora)["Messages"])
        check(step("Check delivery times") and answered(nora, n) and users(nora)[-1] == "Check delivery times", f"Picking a next step sends it as your reply ({users(nora)[-1:]})")
        check(until(lambda: js(p, steps + ".every(b => b.disabled)"), 5), "Then the rows take no more")
        n = len(chat(nora)["Messages"])
        step("Save the table")
        time.sleep(1.5)
        check(len(chat(nora)["Messages"]) == n, "Clicking one again sends nothing")
        check("Took " not in (js(p, "document.querySelector('.chat-view')?.innerText ?? ''") or ""), "A reply has no Took line")

        again(p, nora, "MULTI")
        c = until(lambda: (c := card(p)) and c.get("q") == "Which should I compare?" and c, 10) or {}
        submit = "[...(" + CARD + ")?.querySelectorAll('button') ?? []].find(b => b.innerText.trim() === 'Submit')"
        check(c.get("options") == ["Price", "Weight", "Battery"] and js(p, submit + "?.disabled"), f"Several: options to tick, Submit off until one is ticked ({c})")
        option(p, "Price")
        option(p, "Battery")
        c = card(p)
        check(c.get("on") == ["Price", "Battery"] and not c.get("done") and len(chat(nora)["Messages"]) == n + 2, f"Ticking sends nothing yet ({c.get('on')})")
        n = len(chat(nora)["Messages"])
        js(p, submit + "?.click()")
        check(answered(nora, n) and users(nora)[-1] == "Price\nBattery", f"Submit sends the ticked ones as your reply ({users(nora)[-1:]})")
        check(until(lambda: card(p).get("done") and card(p).get("off"), 5), "and the card takes no more")

        again(p, nora, "DROP")
        c = until(lambda: (c := card(p)) and c.get("q") == "Pick a day" and c, 10) or {}
        check(c.get("select") is not None and not c.get("options"), f"A long list is a dropdown ({c})")
        js(p, "(t => t?.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' })))((" + CARD + ")?.querySelector('.choice-select'))")
        listed = until(lambda: js(p, "[...document.querySelectorAll('[role=option]')].map(o => o.innerText.trim())"), 3) or []
        js(p, "(o => { o?.focus(); o?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })) })([...document.querySelectorAll('[role=option]')].find(o => o.innerText.trim() === 'Day 7'))")
        check(len(listed) == 9 and until(lambda: card(p).get("select") == "Day 7", 3), f"It lists every option, and picking one shows it ({len(listed)}, {card(p).get('select')})")
        n = len(chat(nora)["Messages"])
        js(p, "[...(" + CARD + ")?.querySelectorAll('button') ?? []].find(b => b.innerText.trim() === 'Send')?.click()")
        check(answered(nora, n) and users(nora)[-1] == "Day 7" and until(lambda: card(p).get("off"), 5), f"Send sends it, once ({users(nora)[-1:]})")

        again(p, nora, "CHOOSE")
        c = until(lambda: (c := card(p)) and c.get("q") == "Where to?" and c, 10) or {}
        check(c.get("options") == ["Lisbon", "Porto"] and c.get("own"), f"One pick, with a box for your own words ({c})")
        js(p, "(i => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, 'Madeira'); i.dispatchEvent(new Event('input', { bubbles: true })) })"
              "((" + CARD + ").querySelector('[aria-label=\"Type your own\"]'))")
        n = len(chat(nora)["Messages"])
        js(p, "(" + CARD + ").querySelector('[aria-label=\"Type your own\"]').closest('form').querySelector('button[type=submit]').click()")
        check(answered(nora, n) and users(nora)[-1] == "Madeira", f"Your own words go back as your reply ({users(nora)[-1:]})")
        c = until(lambda: (c := card(p)) and c.get("done") and c, 5) or {}
        check(c.get("off") and not c.get("on") and js(p, "(" + CARD + ").querySelector('[aria-label=\"Type your own\"]').value") == "Madeira", "and the card shows them, taking no more")
        rpc(p, "capture", name="skills-choices.png")

        again(p, nora, "BADJSON")
        bad = js(p, "(t => t && [t.innerText, !!t.querySelector('.choice-card')])([...document.querySelectorAll('.chat-view .ai-turn')].find(t => t.innerText.includes(\"Here's a list\")))") or ["", True]
        check("not json at all" in bad[0] and not bad[1], "A choices block that isn't JSON stays as text, with no card")
        check(js(p, "document.querySelectorAll('.chat-view .choice-card').length") == 3, "Plain replies get no card (three cards in all; next steps are rows)")

        # Reply actions show on hover, lined up with the message; message text selects and copies.
        acts = "[...document.querySelectorAll('.chat-view .ai-turn > .ai-actions')].pop()"
        look = lambda: js(p, f"(a => a && [getComputedStyle(a).opacity, Math.round(a.querySelector('svg').getBoundingClientRect().left - a.parentElement.querySelector('.ai-msg').getBoundingClientRect().left)])({acts})") or []  # noqa: E731
        check(js(p, "['.ai-msg.is-user', '.ai-msg.is-assistant .md'].every(s => (c => c.userSelect || c.webkitUserSelect)(getComputedStyle(document.querySelector('.chat-view ' + s))) === 'text')"),
              "Your messages and the replies are selectable text")
        if MAC:
            js(p, "(e => getSelection().selectAllChildren(e))([...document.querySelectorAll('.chat-view .ai-msg.is-assistant .md p')].pop())")
            got = copy_keys(p)
            check("Here's a list" in got, f"Cmd+C copies the selected reply text ({got[:40]!r})")
        else:
            mouse(p, "mouseMoved", 4, 4)
            time.sleep(.4)
            hidden = look()
            js(p, f"{acts}.parentElement.querySelector('.ai-msg').scrollIntoView({{ block: 'center' }})")
            box = js(p, f"(r => [r.left + r.width / 2, r.top + r.height / 2])({acts}.parentElement.querySelector('.ai-msg').getBoundingClientRect())")
            mouse(p, "mouseMoved", *box)
            time.sleep(.4)
            shown = look()
            check(hidden[:1] == ["0"] and shown[:1] == ["1"], f"Copy shows only while the pointer is over the reply ({hidden}, {shown})")
            check(shown and abs(shown[1]) <= 2, f"lined up with the reply's text ({shown[1:]}px)")
            mine = drag_select(p, ".chat-view .ai-msg.is-user")
            check(mine == "BADJSON", f"Dragging across your own message selects it ({mine!r})")
            reply = drag_select(p, ".chat-view .ai-msg.is-assistant .md p")
            check(reply.startswith("Here's a list"), f"and across a reply ({reply!r})")
            got = copy_keys(p)
            check(got.startswith("Here's a list") and (clipboard() or "").startswith("Here's a list"), f"Ctrl+C copies it ({got!r})")

        # A turn's actions show once, under its final reply, not under the lines between its steps.
        again(p, nora, "STEPS")
        turn = "[...document.querySelectorAll('.chat-view .ai-turn')].filter(t => /Found it|Going through|All done/.test(t.querySelector('.ai-msg.is-assistant')?.innerText ?? ''))"
        under = until(lambda: (r := js(p, f"{turn}.map(t => [t.querySelector('.ai-msg.is-assistant').innerText.trim(), !!t.querySelector(':scope > .ai-actions')])")) and len(r) == 3 and r, 10) or []
        check([u[1] for u in under] == [False, False, True] and under[-1][0].startswith("All done"), f"Only the turn's final reply has the actions, not the lines between its steps ({under})")
        # Under an answer: Copy, Share and More; the last answer Regenerate too. No thumbs.
        again(p, nora, "RATE")
        acts = "[...document.querySelectorAll('.chat-view .ai-turn > .ai-actions')]"
        rated = "[...document.querySelectorAll('.chat-view .ai-turn')].find(t => t.querySelector('.ai-msg.is-assistant')?.innerText.startsWith(\"Here's the plan\"))?.querySelector('.ai-actions')"
        labels = js(p, f"{acts}.map(a => [...a.querySelectorAll('button')].map(b => b.getAttribute('aria-label')).join(','))") or []
        check(labels and labels[-1] == "Copy,Share,Regenerate,More" and all(l == "Copy,Share,More" for l in labels[:-1]),
              f"Every answer has Copy, Share and More, and no thumbs; the last one Regenerate too ({labels[-2:]})")
        js(p, "window.__shared = null; navigator.share = d => { window.__shared = d; return Promise.resolve() }")
        js(p, f"{rated}.querySelector('[aria-label=Share]').click()")
        shared = until(lambda: js(p, "window.__shared"), 5) or {}
        check(shared.get("text") == "Here's the plan: book Alfama House and see the map (https://example.com/map).", f"Share hands over the reply as plain text ({shared})")
        # The old thumbs op does nothing now: no rating kept, and no note to the companion.
        send(p, "aiRate", text="Here's **the plan**: book `Alfama House` and see [the map](https://example.com/map).", rating="down")
        n = len(lines("qa-prompts.jsonl"))
        again(p, nora, "Thanks")
        sent = [entry["prompt"] for entry in lines("qa-prompts.jsonl")[n:] if entry["chat"] == nora]
        kept = [m.get("Rating") for m in chat(nora)["Messages"] if m.get("Rating")]
        check(sent and "thumbs" not in sent[-1] and not kept, f"A thumbs op sent anyway is ignored: no rating kept, no note to the companion ({kept})")
        again(p, nora, "And again")
        out = RUN / "reply.md"
        rpc(p, "osAuth", answer="deny", exportPath=str(out))
        js(p, f"{rated}.querySelector('[aria-label=More]').dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }}))")
        items = until(lambda: js(p, "[...document.querySelectorAll('[role=menuitem]')].map(e => e.innerText.trim())"), 5) or []
        js(p, "[...document.querySelectorAll('[role=menuitem]')].find(e => e.innerText.trim() === 'Save as file')?.click()")
        saved = until(lambda: out.exists() and out.read_text(encoding="utf-8"), 5)
        check(items == ["Copy as Markdown", "Save as file"] and saved == "Here's **the plan**: book `Alfama House` and see [the map](https://example.com/map).",
              f"More has Copy as Markdown and Save as file, which saves the reply as Markdown ({items}, {saved!r})")
        js(p, f"{acts}.pop().querySelector('[aria-label=Regenerate]').click()")
        ask = until(lambda: (t := js(p, f"{acts}.pop().innerText")) and "Forget" in t and t, 5) or ""
        check("Forget this reply and run your message again?" in ask, f"Regenerate asks first ({ask!r})")
        before, n = len(chat(nora)["Messages"]), len(lines("qa-prompts.jsonl"))
        js(p, f"[...{acts}.pop().querySelectorAll('button')].find(b => b.innerText.trim() === 'Regenerate').click()")
        until(lambda: len(lines("qa-prompts.jsonl")) > n and not chat(nora).get("Running") and chat(nora)["Messages"][-1]["Role"] == "assistant", 30)
        sent = [entry["prompt"] for entry in lines("qa-prompts.jsonl")[n:] if entry["chat"] == nora]
        check(len(sent) == 1 and sent[0].rstrip().endswith("And again") and len(chat(nora)["Messages"]) == before and users(nora)[-1] == "And again",
              "Then it forgets the reply and runs your message again in its place")

        # Media: an image and a video link on lines of their own show as cards; the image waits for Show image.
        again(p, nora, "MEDIA")
        n = until(lambda: js(p, CARDS + ".length") == 2 and 2, 10)
        check(n == 2, "An image and a YouTube link show as two cards")
        image = js(p, CARDS + "[0]?.innerText || ''") or ""
        check("Show image" in image and not js(p, CARDS + "[0]?.querySelector('img')"), "The image waits until Show image is pressed")
        js(p, CARDS + "[0]?.querySelector('button')?.click()")
        broken = until(lambda: "didn't load" in (t := js(p, CARDS + "[0]?.innerText || ''") or "") and t, 20) or ""
        check(broken, "An image that doesn't load says so: " + broken.replace("\n", " ")[:60])
        video = js(p, CARDS + "[1]?.innerText || ''") or ""
        check("How desk lamps work" in video and "Starts at 1:35" in video, "The video card shows its title and start time: " + video.replace("\n", " ")[:60])
        rpc(p, "capture", name="skills-media.png")
        # What Still fetches for a card: a picture as data; not a page, nothing too big, nothing over http.
        for url in (here + "/lamp.png", here + "/page.png", here + "/big.png", "http://example.com/a.png"):
            js(p, FETCH % json.dumps(url))
        got = lambda path: until(lambda: js(p, "window.__media?.[%s] || null" % json.dumps(path)), 20) or {}
        check((got(here + "/lamp.png").get("src") or "").startswith("data:image/png;base64,"), "Still fetches a picture and hands it over as data")
        check(got(here + "/page.png").get("error") == "The image didn't load.", "but not a page that says it's a picture")
        big = got(here + "/big.png")
        check(big.get("error") == "The image is too big to show here.", "nor one over 5 MB: " + str(big.get("error") or big.get("src", "")[:30] or "no answer"))
        check(got("http://example.com/a.png").get("error") == "Only https images show here.", "nor one over http")

        # The end of the chat keeps its gap above the message box (tab 32px, split and panel 24px), also with a tall box.
        for view, least in (("tab", 32), ("split", 24), ("panel", 24)):
            if view == "split":  # a page of the chat's beside it
                known = {t["Id"] for t in rpc(p)["tabs"]}
                send(p, "new", url="about:blank")
                page = until(lambda: next((t["Id"] for t in rpc(p)["tabs"] if t["Id"] not in known), None), 10)
                send(p, "tabHand", id=page, chat=nora)
                send(p, "chatOpen", id=nora)
                until(lambda: js(p, "!!document.querySelector('.page-column.is-chat')"), 10)
                send(p, "chatPage", id=page, on=True)
                check(until(lambda: js(p, "!!document.querySelector('.page-column.is-split .chat-view')"), 10), "The chat shows beside its page")
                rpc(p, "capture", name="skills-split.png")
            if view == "panel":
                send(p, "chatPage", on=False)
                send(p, "new")
                time.sleep(.5)
                send(p, "aiToggle")
                send(p, "aiOpenChat", id=nora)
                until(lambda: js(p, "!!document.querySelector('.chat-view[data-mode=panel] .ai-log')"), 10)
            for tall in (False, True):
                mode = json.dumps("panel" if view == "panel" else "tab")
                js(p, TYPE % (mode, json.dumps(["line"] * 10 if tall else [""])))
                time.sleep(.8)
                got = js(p, GAP % mode) or {}
                js(p, TYPE % (mode, '[""]'))
                ok = got.get("gap") is not None and least <= got["gap"] <= least + 6 and got.get("visible") and (not tall or got.get("box", 0) >= 180)
                check(ok, f"{view}, {'a ' + str(got.get('box')) + 'px' if tall else 'a one-line'} message box: the last line sits {got.get('gap')}px above it" + ("" if got.get("visible") else ", cut off"))
            if view == "panel":
                rpc(p, "capture", name="skills-panel.png")
                send(p, "aiToggle")

        # Tiers: Settings picks a tier's model and effort; only what the app offers.
        send(p, "aiTier", harness="fake", tier="efficient", model="good", effort="low")
        t = until(lambda: (x := tiers(p).get("efficient")) and x.get("custom") and x, 5) or {}
        check(t.get("model") == "good" and t.get("effort") == "low", f"A tier takes a model and effort from the app's list: {t}")
        send(p, "aiTier", harness="fake", tier="expert", model="made-up", effort="high")
        time.sleep(.5)
        check(tiers(p).get("expert", {}).get("model") == "good", "A model the app doesn't list is ignored")
        send(p, "aiTier", harness="fake", tier="default", model="good", effort="bogus")
        d = until(lambda: (x := tiers(p).get("default")) and x.get("custom") and x, 5) or {}
        check(d.get("model") == "good" and d.get("effort") == "", "An effort the model doesn't offer falls back to its default effort")
        jonah = start(p, "jonah", "HI")
        args = (lines("runs.jsonl") or [{}])[-1].get("args", [])
        check(args[args.index("--model") + 1:][:1] == ["good"] if "--model" in args else False, "Jonah (Efficient) runs on the tier's model")
        check(args[args.index("--effort") + 1:][:1] == ["low"] if "--effort" in args else False, "and its effort")

        # A model the app refuses: the same message again on the app's default model, and the chat says why.
        send(p, "aiTier", harness="fake", tier="efficient", model="notonplan", effort="")
        until(lambda: tiers(p).get("efficient", {}).get("model") == "notonplan", 5)
        runs = len(lines("runs.jsonl"))
        again(p, jonah, "HI again")
        until(lambda: len(lines("runs.jsonl")) >= runs + 2 and not chat(jonah).get("Running"), 30)
        tried = [r["args"] for r in lines("runs.jsonl")[runs:]]
        check(len(tried) == 2 and "notonplan" in tried[0] and "--model" not in tried[1], f"A refused model is retried once on the default model ({len(tried)} runs)")
        msgs = chat(jonah)["Messages"]
        check(not any(REFUSED[:30] in m["Text"] for m in msgs), "The refusal doesn't stay in the chat")
        check(sum(1 for m in msgs if m["Role"] == "user" and m["Text"] == "HI again") == 1, "and the message shows once")
        note = next((m["Text"] for m in msgs if m["Role"] == "note" and "isn't available" in m["Text"]), "")
        check(note.startswith("notonplan isn't available on your Fake agent account") and "Settings → Models" in note, "The chat says it ran on the default model: " + note[:90])
        check(msgs and msgs[-1]["Role"] == "assistant" and msgs[-1]["Text"] == "Okay.", "and the answer follows")

        # A settings link in a reply opens that exact setting; a change it offers waits for Change it.
        again(p, jonah, "SETLINK")
        link = lambda words: js(p, "[...[...document.querySelectorAll('.chat-view .md')].pop().querySelectorAll('a.md-setting')].find(a => a.innerText.includes(%s))?.click() ?? 'none'" % json.dumps(words))
        offer = lambda: js(p, "document.querySelector('.set-offer')?.innerText.replace(/\\s+/g, ' ').trim() || ''") or ""
        def prefs():  # Still may be writing it right now (Windows locks the file then)
            for _ in range(20):
                try:
                    return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
                except (OSError, ValueError):
                    time.sleep(.1)
            return {}
        level = lambda: next((c.get("Autonomy") for c in prefs().get("Companions", []) if c["Id"] == "jonah"), None)
        link("check in more")
        lit = until(lambda: js(p, "document.querySelector('#set-autonomy-jonah')?.classList.contains('set-flash')"), 10)
        said = until(offer, 5) or ""
        check(lit and said.startswith("Set Jonah to Ask more?"), f"A settings link opens that setting, lit up, and offers the change ({said!r})")
        time.sleep(1)  # the list has scrolled to the row
        check(js(p, "document.querySelector('.settings-dialog').scrollTop") == 0, "...scrolling only the list, so the dialog keeps its title in view")
        time.sleep(.5)
        rpc(p, "capture", name="skills-setlink.png")
        js(p, "[...document.querySelectorAll('.set-offer button')].find(b => b.innerText.trim() === 'Change it').click()")
        check(until(lambda: level() == "ask", 10) and until(lambda: not offer(), 5), "Change it makes the change and the offer goes")
        link("dark theme")
        lit = until(lambda: js(p, "document.querySelector('#set-theme')?.classList.contains('set-flash')"), 10)
        said = until(offer, 5) or ""
        js(p, "[...document.querySelectorAll('.set-offer button')].find(b => b.innerText.trim() === 'Not now').click()")
        time.sleep(1)
        theme = prefs().get("Theme")
        check(lit and said.startswith("Set Theme to Black?") and not offer() and theme == "Light", f"Not now leaves it as it was ({said!r}, {theme})")
        link("permissions")
        lit = until(lambda: js(p, "document.querySelector('#set-permissions')?.classList.contains('set-flash')"), 10)
        check(lit and not offer(), "A link without a value only opens the setting")
        send(p, "companionAutonomy", id="jonah", level="keepgoing")

        # Settings → Models: the tiers, with Advanced off; Reset puts the defaults back.
        send(p, "openPanel", name="settings")
        until(lambda: js(p, "!!document.querySelector('.set-shell')"), 10)
        js(p, "[...document.querySelectorAll('.set-nav-item')].find(t => t.innerText.trim() === 'Models')?.click()")
        until(lambda: js(p, "!!document.querySelector('#set-tiers')"), 5)
        js(p, "document.querySelector('#set-tiers')?.scrollIntoView({block: 'center'})")
        rows = until(lambda: js(p, "document.querySelectorAll('#set-tiers .tier-row').length"), 5) or 0
        check(rows >= 3, f"Settings shows the tiers ({rows} rows)")
        kept = js(p, "document.querySelector('#tiers-fake .tier-row[data-tier=expert]')?.innerText || ''") or ""
        check("good" in kept and "Low effort" in kept, "and the Thorough pick saved before launch: " + kept.replace("\n", " ")[:60])
        flagged = until(lambda: js(p, "document.querySelector('#set-tiers .tier-row[data-tier=efficient] .tier-failed')?.innerText"), 5) or ""
        check(flagged, "with the refused one flagged: " + flagged[:80])
        time.sleep(.5)
        rpc(p, "capture", name="skills-tiers.png")
        send(p, "aiTiersReset", harness="fake")
        check(until(lambda: not any(v.get("custom") for v in tiers(p).values()), 5), "Reset to defaults clears the picks")
        typed = start(p, "jonah", "/from-web please")
        check(chat(typed).get("Read", 0) >= 1, "Typing a skill added from a link counts the same")

        # The Skills page: My skills under the companion whose kit brought them, then All companions; Built-in; Run skill; the ⋯ menu.
        send(p, "appHome", view="skills")
        check(until(lambda: js(p, "!!document.querySelector(\"section.skills-page[aria-label='Skills']\")"), 10), "Skills has a page of its own")
        page = js(p, "document.querySelector('.skills-page')?.innerText") or ""
        check("Reusable instructions your companions can use." in page and "New skill" in page, "with its line and New skill at the top")
        tabs = js(p, "[...document.querySelectorAll('.skills-tabs [role=tab]')].map(t => t.innerText.trim() + ':' + t.getAttribute('aria-selected'))") or []
        check(tabs == ["My skills:true", "Built-in:false"] and js(p, "!!document.querySelector('.skills-find input[aria-label=\"Search skills\"]')"), f"Two tabs, My skills first, and a search ({tabs})")
        groups = js(p, "[...document.querySelectorAll('.skill-group')].map(g => g.getAttribute('aria-label'))") or []
        check(groups[:2] == ["Nora", "Jonah"] and groups[-1:] == ["All companions"], f"My skills sit under the companion whose kit brought them, then All companions ({groups})")
        cols = js(p, "getComputedStyle(document.querySelector('.skill-grid')).gridTemplateColumns.split(' ').length")
        check(cols == 2, f"Cards sit two across ({cols})")
        own = js(p, "document.querySelector(\".skill-group[aria-label='Nora'] .skill-card[aria-label='Compare options']\")?.innerText") or ""
        check("Run skill" in own and "Built in" in own, f"A card has its name, description, where it's from and Run skill ({own[-60:]!r})")
        check("Only Jonah" in (js(p, "document.querySelector(\".skill-card[aria-label='Deal notes']\")?.innerText") or ""), "A limited skill says who can use it")
        check(not js(p, "!!document.querySelector('.skills-page .plug-who, .skills-page [aria-pressed]')"), "and no skill has a row of companion chips")
        js(p, "[...document.querySelectorAll('.skills-tabs [role=tab]')].find(t => t.innerText.trim() === 'Built-in')?.click()")
        built = until(lambda: js(p, "document.querySelectorAll('.skills-page > .skill-grid .skill-card').length"), 5) or 0
        check(built >= 30, f"Built-in lists Setup and every skill in Still's kits ({built})")
        check("Sales kit" in (js(p, "document.querySelector(\".skill-card[aria-label='Lead list']\")?.innerText") or ""), "each with its kit")
        js(p, "[...document.querySelectorAll('.skills-tabs [role=tab]')].find(t => t.innerText.trim() === 'My skills')?.click()")
        js(p, "document.querySelector(\".skill-card[aria-label='Compare options'] .skill-run\")?.click()")
        box = lambda: js(p, "(document.querySelector('.home-compose [aria-label=Message]')?.innerText ?? '') + '|' + (document.querySelector('.home-compose .mention.is-skill')?.innerText ?? '')") or ""
        check(until(lambda: "/option-compare" in box() or "Compare options" in box(), 5), f"Run skill opens a new chat with the skill in the box ({box()[:60]!r})")

        def menu(name):  # the last menu fades out first, so only the open one counts
            until(lambda: not js(p, "!!document.querySelector('[role=menu]')"), 3)
            send(p, "appHome", view="skills")
            until(lambda: js(p, f"!!document.querySelector(\".skill-card[aria-label='{name}'] .skill-more\")"), 10)
            js(p, f"document.querySelector(\".skill-card[aria-label='{name}'] .skill-more\").dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }}))")
            return until(lambda: js(p, "[...document.querySelectorAll('[role=menu][data-state=open] [role=menuitem]')].map(i => i.innerText.trim())"), 5) or []

        def pick(words):
            js(p, f"[...document.querySelectorAll('[role=menu][data-state=open] [role=menuitem]')].find(i => i.innerText.includes({json.dumps(words)}))?.click()")
        items = menu("From the web")
        check(items == ["Edit", "Limit to companions…", "Duplicate", "Delete"], f"⋯ has Edit, Limit to companions, Duplicate and Delete ({items})")
        pick("Limit")
        until(lambda: js(p, "!!document.querySelector('.skill-limit')"), 5)
        js(p, "[...document.querySelectorAll('.skill-limit-pick label')].find(l => l.innerText.includes('Only some'))?.querySelector('input').click()")
        until(lambda: js(p, "!!document.querySelector(\".skill-limit-list input[aria-label='Jonah']\")"), 5)
        js(p, "document.querySelector(\".skill-limit-list input[aria-label='Jonah']\").click()")
        js(p, "[...document.querySelectorAll('.skill-limit button')].find(b => b.innerText.trim() === 'Save')?.click()")
        web = PROFILE / "skills" / "from-web.md"
        check(until(lambda: "only: nora" in web.read_text(encoding="utf-8"), 5), "Limit to companions keeps it to Nora, in the skill's file")
        check(until(lambda: "Only Nora" in (js(p, "document.querySelector(\".skill-card[aria-label='From the web']\")?.innerText") or ""), 5), "and its card says so")
        menu("Deal notes")
        pick("Duplicate")
        copy = lambda: next((f for f in (PROFILE / "skills").glob("*.md") if "name: Deal notes copy" in f.read_text(encoding="utf-8")), None)
        check(until(copy, 5), "Duplicate makes a copy")
        until(lambda: js(p, "!!document.querySelector(\".skill-card[aria-label='Deal notes copy']\")"), 5)
        menu("Deal notes copy")
        pick("Delete")
        check(until(lambda: "no companion can use it" in (js(p, "document.querySelector('[role=alertdialog][data-state=open]')?.innerText") or ""), 5), "Delete asks first")
        js(p, "[...document.querySelectorAll('[role=alertdialog][data-state=open] button')].find(b => b.innerText.trim() === 'Delete skill')?.click()")
        check(until(lambda: not copy(), 20), "and then deletes it")
        errors = rpc(p).get("shellErrors") or []
        check(not errors, "No interface errors" + (f": {errors[:1]}" if errors else ""))
    finally:
        site.shutdown()
        try:
            rpc(p, "quit")
            p.wait(timeout=20)
        except Exception:
            p.kill()
    passed = sum(c["passed"] for c in RESULT["checks"])
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=1))
    print(("PASSED" if passed == len(RESULT["checks"]) else "FAILED") + f" {passed}/{len(RESULT['checks'])} -> {RUN}")
    sys.exit(0 if passed == len(RESULT["checks"]) else 1)


if __name__ == "__main__":
    main()
