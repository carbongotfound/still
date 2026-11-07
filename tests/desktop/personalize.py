"""Shaping a companion (2.10 Stage 8): Role, Personality and Reply length, the Setup skill, Still's skill library and the
one editor for making and changing a companion.

Checks that an old companion loads with the defaults (no role or personality, Balanced replies); that the new fields
save, go into the prompt as short lines and travel with Share; that every profile has Setup, which can be edited and
reset but not deleted or given out, stays out of the skill index, and loads itself once on a companion's first chat
(whether the user or the companion speaks first) with "Used skill Setup" as the first step, never in a later turn or
chat, and never in an incognito chat; that an unedited skill from before 2.10 upgrades itself while an edited one stays;
that a library skill picked for a companion is added as Still's file, never an empty one; and that Make your own opens
the same editor on a draft, whose generator writes starting instructions and picks 3 or 4 skills, and Hire saves it all.

No AI plan is used: a fake AI app logs every prompt it gets and answers "Okay."

Usage: python tests/desktop/personalize.py <QA exe>
"""
import json
import sys
import textwrap
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, companions_page, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("personalize-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
SKILLS = PROFILE / "skills"
ASSETS = ROOT / "still" / "Assets"
SETUP = '[Skill "Setup"'
FAILED = []


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


FAKE = textwrap.dedent(r'''
    import json, os, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "runs.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt}) + "\n")
    print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()}), flush=True)
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay."}]}}), flush=True)
''')


def norm(text):
    return text.replace("\r\n", "\n").strip()


def runs():
    file = BIN / "runs.jsonl"
    return [json.loads(l)["prompt"] for l in file.read_text(encoding="utf-8").splitlines() if l.strip()] if file.exists() else []


def state():
    for _ in range(50):  # Still swaps the file in atomically, so a read can land mid-swap
        try:
            return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
        except (OSError, ValueError, KeyError):
            time.sleep(.1)
    return {}


def mates():
    return {c["Name"]: c for c in state().get("Companions", [])}


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def chat(cid):
    return next((c for c in chats() if c["Id"] == cid), {"Messages": []})


def skill(id):
    file = SKILLS / (id + ".md")
    return norm(file.read_text(encoding="utf-8")) if file.exists() else None


def stock(id):
    found = list((ASSETS / "roles").glob(f"*/skills/{id}.md")) or [ASSETS / "skills" / (id + ".md")]
    return norm(found[0].read_text(encoding="utf-8"))


def shown(p, selector):
    return js(p, f"!!document.querySelector({json.dumps(selector)})")


def click(p, selector, words=""):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => (e.innerText + ' ' + (e.getAttribute('aria-label') ?? '')).includes({json.dumps(words)})); e?.click(); return !!e }})()")


def type_into(p, selector, value, index=0):
    return js(p, f"""(() => {{ const e = document.querySelectorAll({json.dumps(selector)})[{index}]; if (!e) return false
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {json.dumps(value)})
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); e.focus(); return true }})()""")


def tab(p, name):
    js(p, f"document.querySelector(\".profile-panel [role=tab][id$='-trigger-{name}']\")?.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}))")
    return until(lambda: js(p, f"document.querySelector(\".profile-panel [role=tab][id$='-trigger-{name}']\")?.dataset.state === 'active'"), 3)


def escape(p):
    js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")


def profile(p, cid):
    js(p, f"dispatchEvent(new CustomEvent('still-profile', {{ detail: {json.dumps({'id': cid, 'tab': 'general'})} }}))")
    return until(lambda: shown(p, ".profile-panel .profile-field input"), 5)


def start(p, cid, text, window=None):
    """A new chat with a companion, the user speaking first; the chat's id once the fake app has answered."""
    before = {c["Id"] for c in chats()}
    n = len(runs())
    send(p, "new")
    until(lambda: shown(p, ".home-compose [aria-label=Message]"), 10)
    escape(p)
    send(p, "aiSend", text=text, home=True, companion=cid)
    new = until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before), None), 20)
    until(lambda: len(runs()) > n and not chat(new).get("Running") and any(m["Role"] == "assistant" for m in chat(new)["Messages"]), 30)
    return new


def again(p, cid, text):
    send(p, "chatOpen", id=cid)
    until(lambda: shown(p, ".chat-view [aria-label=Message]"), 10)
    n, said = len(runs()), len(chat(cid)["Messages"])
    send(p, "aiSend", text=text)
    until(lambda: len(runs()) > n and len(chat(cid)["Messages"]) > said + 1 and not chat(cid).get("Running"), 30)
    return runs()[-1] if len(runs()) > n else ""


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    SKILLS.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run"], "output": "stream-json"}))
    # Skills as an earlier Still left them: an unedited research brief (Windows line endings), a claim check the user
    # changed, and no Setup.
    old = (Path(__file__).parent / "fixtures" / "old-research-brief.md").read_text(encoding="utf-8")
    (SKILLS / "research-brief.md").write_bytes(norm(old).replace("\n", "\r\n").encode() + b"\r\n")
    (SKILLS / "claim-check.md").write_text("---\nname: Claim check\ndescription: Mine.\nwhen: Checking a claim\n---\n\n1. My own steps.\n", encoding="utf-8")
    # Olive is from before 2.10: none of the new fields. Maya was just hired from the crew and hasn't chatted yet.
    crew = [{"Id": "olive", "Name": "Olive", "Job": "Checks prices before I buy.", "Mode": "default", "Skills": ["research-brief"]},
            {"Id": "maya", "Name": "Maya", "Job": "Research for my shop.", "Crew": "research", "Mode": "default", "Greet": True}]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake",
        "Theme": "Light", "Width": 1300, "Height": 880}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "document.body.innerText.length"), 20)
        escape(p)
        send(p, "aiCheck")
        time.sleep(2)

        # Skills on disk: Setup is there, the unedited old one upgraded, the edited one kept.
        check(until(lambda: skill("setup"), 10) == stock("setup"), "Every profile has the Setup skill, Still's version")
        check(skill("research-brief") == stock("research-brief") and "## Steps" in (skill("research-brief") or ""), "An unedited skill from before 2.10 upgrades to the new version")
        check("1. My own steps." in (skill("claim-check") or ""), "A skill the user edited stays as they wrote it")

        # An old companion: no role or personality, Balanced replies.
        check(profile(p, "olive"), "Olive's profile opens")
        roles = js(p, "[...document.querySelectorAll('.profile-panel .profile-field input')].map(e => e.value)")
        check(roles and roles[1] == "" and js(p, "!document.querySelector(\".profile-panel [aria-label=Personality] [aria-checked=true]\")")
              and js(p, "document.querySelector(\".profile-panel [aria-label='Reply length'] [aria-checked=true]\")?.innerText.trim().startsWith('Balanced')"),
              f"An old companion loads with no role, no personality and Balanced replies ({roles})")
        labels = js(p, "[...document.querySelectorAll('.profile-panel .profile-field > span')].map(e => [...e.childNodes].filter(n => n.nodeName !== 'SMALL').map(n => n.textContent).join('').trim())") or []
        check(labels[:6] == ["Name", "Role", "Instructions", "Personality", "How Olive talks, in your words", "Reply length"], f"General: Name, Role, Instructions, Personality, Tone and Reply length ({labels})")
        check(tab(p, "skills") and "Skills they can use" in (js(p, "document.querySelector('.profile-panel')?.innerText") or "")
              and "loads a skill when a task fits" in (js(p, "document.querySelector('.profile-panel')?.innerText") or ""), "Skills: 'Skills they can use', loaded when a task fits")
        setup_row = js(p, "[...document.querySelectorAll('.profile-panel .profile-list li')].find(l => l.innerText.startsWith('Setup'))?.innerText") or ""
        check("Runs once, on Olive's first chat" in setup_row and js(p, "!![...document.querySelectorAll('.profile-panel .profile-list li')].find(l => l.innerText.startsWith('Setup'))?.querySelector('[aria-label=\"Edit Setup\"]')")
              and not js(p, "!![...document.querySelectorAll('.profile-panel .profile-list li')].find(l => l.innerText.startsWith('Setup'))?.querySelector('[role=switch]')"),
              "Setup is listed first: always on, with Edit and no switch")
        check(js(p, "!!document.querySelector('.profile-panel [aria-label=\"Reset Claim check to Still\\'s version\"]')") and not js(p, "!!document.querySelector('.profile-panel [aria-label=\"Reset Research brief to Still\\'s version\"]')"),
              "Reset shows for a Still skill the user changed, and only then")
        tab(p, "model")
        check("Default mode" in (js(p, "document.querySelector('.profile-panel')?.innerText") or ""), "AI: Runs on and Default mode")
        rpc(p, "capture", name="personalize-skills.png")
        escape(p)
        until(lambda: not shown(p, ".profile-panel"), 3)

        # Setup can't be deleted or given out; reset brings back Still's version.
        send(p, "skillDelete", id="setup")
        time.sleep(1)
        check(skill("setup") == stock("setup"), "Deleting Setup does nothing")
        send(p, "skillSave", id="setup", name="Setup", description="Mine", when="First chat", body="MY SETUP")
        check(until(lambda: "MY SETUP" in (skill("setup") or ""), 5), "Setup can be edited")
        send(p, "skillReset", id="setup")
        send(p, "skillReset", id="claim-check")
        check(until(lambda: skill("setup") == stock("setup") and skill("claim-check") == stock("claim-check"), 5), "Reset puts back Still's version of Setup and of an edited skill")

        # A new companion with the new fields, Setup handed to it (ignored), a library skill it doesn't have yet, and a made-up id.
        check(not (SKILLS / "lead-list.md").exists(), "(lead-list isn't in the user's skills yet)")
        send(p, "companionSave", id="scout1", name="Pip", job="Finds the best price before I buy.", role="Scout", personality="direct", length="short",
             tone="Dry wit.", skills=["lead-list", "setup", "made-up"])
        pip = until(lambda: mates().get("Pip"), 5) or {}
        check(pip.get("Role") == "Scout" and pip.get("Personality") == "direct" and pip.get("Length") == "short" and pip.get("Setup") == "pending",
              f"Role, Personality and Reply length save, and Pip is new ({ {k: pip.get(k) for k in ('Role', 'Personality', 'Length', 'Setup')} })")
        check(pip.get("Skills") == ["lead-list"], f"Setup and unknown ids aren't kept as its skills ({pip.get('Skills')})")
        check(skill("lead-list") == stock("lead-list"), "A library skill picked for it is added as Still's file, not an empty one")
        send(p, "companionSave", id="scout1", name="Pip", job="Finds the best price before I buy.", role="Scout", personality="sarcastic", length="huge")
        time.sleep(1)
        pip = mates().get("Pip", {})
        check(pip.get("Personality") == "direct" and pip.get("Length") == "short", "Values that aren't on the list are ignored")

        # Pip's first chat, the user speaking first: Setup loads once, its step first; the new fields are short lines.
        first = start(p, "scout1", "HI")
        sent = runs()[-1] if runs() else ""
        check(sent.count(SETUP) == 1 and "Open with your own words" in sent, "The first chat's first turn carries the Setup skill exactly once")
        said = chat(first)["Messages"]
        steps = [m["Text"] for m in said if m["Role"] == "tool"]
        check(said and said[0]["Role"] == "user" and steps[:1] == ["Used skill Setup"] and steps.count("Used skill Setup") == 1, f"and 'Used skill Setup' is its first step, once ({[m['Text'][:30] for m in said[:3]]})")
        check("Your role: Scout. Introduce yourself role first, as Scout Pip." in sent, "The prompt names its role, role first")
        check("Your personality: Direct:" in sent and "How you talk, in the user's words: Dry wit." in sent and "Reply length: Short:" in sent, "Personality, Tone and Reply length are short lines")
        check("- setup:" not in sent and "- lead-list:" in sent, "Setup isn't in the skill index; its own skills are")
        check(until(lambda: mates().get("Pip", {}).get("Setup") == "done", 5), "Pip isn't new anymore")
        later = again(p, first, "HELLO AGAIN")
        check(later and SETUP not in later and "Open with your own words" not in later, "A later turn in that chat has no Setup")
        second = start(p, "scout1", "HI AGAIN")
        sent2 = runs()[-1] if runs() else ""
        check(sent2 and SETUP not in sent2 and not any(m["Text"] == "Used skill Setup" for m in chat(second)["Messages"]), "Pip's next chat has no Setup either")
        check("/setup" not in json.dumps(state()) and "Used skill Setup" not in json.dumps(chat(second)), "and /setup can't be called by name")
        n = len(runs())
        again(p, second, "/setup please")
        check(SETUP not in (runs()[-1] if len(runs()) > n else SETUP), "Typing /setup doesn't load it")

        # An old companion's chats never get Setup.
        olive = start(p, "olive", "HI OLIVE")
        sent = runs()[-1] if runs() else ""
        check(SETUP not in sent and "Reply length: Balanced:" in sent and "Your role:" not in sent and "Your personality:" not in sent,
              "An old companion gets no Setup, Balanced replies and no role or personality lines")

        # Maya (hired, not chatted yet): an incognito chat doesn't count as her first; her next regular chat does.
        before = {w["id"] for w in rpc(p)["windows"]}
        send(p, "incognitoWindow")
        wid = until(lambda: next((w["id"] for w in rpc(p)["windows"] if w["incognito"] and w["id"] not in before), None), 15)
        until(lambda: rpc(p, "shellEval", window=wid, script="!!document.querySelector('[aria-label=Message]')"), 15)
        n = len(runs())
        rpc(p, "shellEval", window=wid, script="window.chrome.webview.postMessage(" + json.dumps({"op": "aiSend", "text": "PRIVATE HI", "home": True, "companion": "maya"}) + ")")
        until(lambda: len(runs()) > n, 30)
        private = runs()[-1] if len(runs()) > n else ""
        check("PRIVATE HI" in private and SETUP not in private, "An incognito chat with a new companion has no Setup")
        check(mates().get("Maya", {}).get("Setup") == "pending", "and she's still new")
        mine = start(p, "maya", "HI MAYA")
        sent = runs()[-1] if runs() else ""
        check(sent.count(SETUP) == 1 and "Your role: Research. Introduce yourself role first, as Research Maya." in sent, "Her first regular chat gets Setup once, with her crew role")
        check("## How you judge the work" in sent and sent.count("## Steps") == 1, "and her role brief comes with it, with no skill body but Setup's")

        # A companion that speaks first (kickoff) gets Setup the same way.
        send(p, "companionSave", id="kiki1", name="Kiki", job="Plans my week.", role="", length="detailed")
        until(lambda: mates().get("Kiki"), 5)
        n = len(runs())
        send(p, "aiKickoff", companion="kiki1")
        until(lambda: len(runs()) > n, 30)
        kick = runs()[-1] if len(runs()) > n else ""
        check(kick.count(SETUP) == 1 and "[Still] This is your first chat with the user" in kick and "Reply length: Detailed:" in kick, "A kickoff carries Setup once, after its own note")
        kchat = until(lambda: next((c for c in chats() if c["Companion"] == "kiki1" and any(m["Role"] == "assistant" for m in c["Messages"])), None), 20) or {"Messages": []}
        check(kchat["Messages"] and kchat["Messages"][0]["Text"] == "Used skill Setup" and kchat["Messages"][1]["Role"] == "assistant", "and its chat shows 'Used skill Setup', then the companion's hello")
        check("Tabs they have open" not in kick, "It isn't handed the user's open tabs")

        # Share carries the new fields; pasting one back keeps them.
        send(p, "new")
        profile(p, "scout1")
        js(p, "navigator.clipboard.writeText = t => { window.__shared = t; return Promise.resolve() }")
        click(p, ".profile-stage-actions button", "Share")
        shared = json.loads(until(lambda: js(p, "window.__shared"), 5) or "{}")
        check(shared.get("role") == "Scout" and shared.get("personality") == "direct" and shared.get("length") == "short" and "folder" not in shared and "skills" not in shared,
              f"Share carries Role, Personality and Reply length, and nothing personal ({shared})")
        escape(p)
        until(lambda: not shown(p, ".profile-panel"), 3)
        companions_page(p)
        click(p, ".home-new", "Hire a companion")
        until(lambda: shown(p, ".companion-library"), 5)
        click(p, ".library-more .role-head", "Paste a shared companion")
        until(lambda: shown(p, ".library-paste textarea"), 3)
        js(p, f"(() => {{ const d = new DataTransfer(); d.setData('text/plain', {json.dumps(json.dumps({**shared, 'name': 'Pip Two'}))}); document.querySelector('.library-paste textarea')?.dispatchEvent(new ClipboardEvent('paste', {{ clipboardData: d, bubbles: true, cancelable: true }})) }})()")
        until(lambda: js(p, "!!document.querySelector('.shared-review')"), 5)
        js(p, "[...document.querySelectorAll('.shared-review button')].find(b => b.innerText.trim() === 'Hire').click()")
        two = until(lambda: mates().get("Pip Two"), 5) or {}
        check(two.get("Role") == "Scout" and two.get("Personality") == "direct" and two.get("Length") == "short", "A pasted companion keeps them")
        check(until(lambda: js(p, "document.querySelector('.joined-card [data-slot=dialog-title]')?.innerText") == "Scout Pip Two joined your team", 5), "A custom companion with a Role shows role first, like the crew")
        click(p, ".joined-card button", "Not now")
        until(lambda: not shown(p, ".joined-card"), 3)

        # Make your own: the same editor on a draft. The generator writes instructions and picks skills; Hire saves it all.
        companions_page(p)
        click(p, ".home-new", "Hire a companion")
        until(lambda: shown(p, ".companion-library"), 5)
        click(p, ".library-more .role-head", "Make your own")
        check(until(lambda: shown(p, ".profile-panel .profile-foot") and not shown(p, ".companion-library"), 5), "Make your own opens the companion editor")
        tabs = js(p, "document.querySelector('.profile-tablist')?.innerText.replace(/\\s+/g, ' ').trim()")
        check(tabs == "General Skills & plugins Files Model", f"A draft shows the tabs it can use ({tabs})")
        check(not js(p, "document.querySelector('.profile-foot button:last-child')?.disabled === false"), "Hire waits for a name")
        type_into(p, ".profile-panel .profile-field input", "Wren")
        type_into(p, ".profile-panel .profile-field input", "Writer", 1)
        type_into(p, ".profile-panel .profile-field textarea", "Write my LinkedIn posts and the monthly newsletter in my voice")
        click(p, ".profile-suggest button", "Suggest instructions and skills")
        note = until(lambda: (t := js(p, "document.querySelector('.profile-suggest .profile-note')?.innerText") or "") and t.startswith("Added") and t, 3) or ""
        job = js(p, "document.querySelector('.profile-panel .profile-field textarea')?.value") or ""
        check(note.startswith("Added 4 skills from Still's library") and "Voice match" in note, f"Suggest picks skills from the library and says which ({note})")
        check(job.startswith("Write my LinkedIn posts") and "How you work:" in job and "Ask me before you send, post, buy or delete anything." in job, "and drafts instructions from what was written, to review")
        click(p, ".profile-panel [aria-label=Personality] button", "Warm")
        click(p, ".profile-panel [aria-label='Reply length'] button", "Detailed")
        tab(p, "skills")
        picked = js(p, "[...document.querySelectorAll('.profile-panel .profile-list li')].filter(l => l.querySelector('[role=switch][data-state=checked]')).map(l => l.querySelector('b').innerText)") or []
        check(len(picked) == 4 and "Voice match" in picked, f"The picked skills are on in the Skills tab, to change before hiring ({picked})")
        rpc(p, "capture", name="personalize-draft.png")
        check(not mates().get("Wren"), "Nothing is saved before Hire")
        click(p, ".profile-foot button", "Hire Wren")
        wren = until(lambda: mates().get("Wren"), 5) or {}
        check(wren.get("Role") == "Writer" and wren.get("Personality") == "warm" and wren.get("Length") == "detailed" and "How you work:" in wren.get("Job", ""),
              "Hire saves the role, personality, length and instructions")
        check(len(wren.get("Skills") or []) == 4 and all(skill(k) == stock(k) for k in wren.get("Skills") or []), "and its 4 skills, each Still's own file")
        check(until(lambda: js(p, "document.querySelector('.joined-card [data-slot=dialog-title]')?.innerText") == "Writer Wren joined your team", 5), "Writer Wren joined your team")
        click(p, ".joined-card button", "Not now")
    finally:
        rpc(p, "quit")
        until(lambda: p.poll() is not None, 15)
    print(f"{'FAILED ' + str(len(FAILED)) if FAILED else 'PASSED'}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
