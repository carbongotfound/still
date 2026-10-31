"""Hiring a companion: a "<name> joined your team" card (it celebrates, with a check badge, Start chatting and Not now),
then its first chat, which it starts itself exactly once: from Start chatting, from "Say hi" the first time, or at the
end of setup. A hidden note starts it (never in the chat); the first thing in the chat is the companion's own message,
with its face, and its tools wait for that hello. Then it may ask one question (choices, or the user's own words, Send
or Skip), and the answer goes to its memory. The title model names the chat from the hello. Talking to it first means
it never kicks off; reopening never starts it again. No test stub ships: "Fake agent" lives only in test profiles.

No AI plan is used: exchange.py's fake agent plays each companion and asks its question through Still's ask_user.

Run: python tests/desktop/hire.py artifacts/Still-QA/Still.exe
Out: artifacts/hire-*/ (hire-*.png in each profile folder)
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402
import exchange as X  # noqa: E402  its fake agent: what each companion says comes from plan.json, and it can call Still's tools
import welcome as W  # noqa: E402  setup's steps

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("hire-" + uuid.uuid4().hex[:8])
BIN = X.BIN = RUN / "bin"
FAILED = []
KICK = "[Still] You were just hired"
SRC = Path(__file__).resolve().parents[2]


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def kickoffs(name):
    return [q for q in X.prompts() if q["name"] == name and KICK in q["prompt"]]


def mates(profile):
    for _ in range(50):  # Still swaps the file in atomically, so a read can land mid-swap
        try:
            return {c["Name"]: c for c in json.loads((profile / "state.json").read_text(encoding="utf-8"))["Preferences"]["Companions"]}
        except (OSError, ValueError, KeyError):
            time.sleep(.1)
    return {}


def memory(profile, name):
    file = profile / "companions" / mates(profile).get(name, {}).get("Id", "-") / "memory.json"
    return file.read_text(encoding="utf-8") if file.exists() else ""


def first_chat(profile, name):
    """The companion's first chat: its oldest (the list is newest first)."""
    try:
        mine = [c for c in json.loads((profile / "ai" / "chats.json").read_text(encoding="utf-8")) if c["Companion"] == mates(profile).get(name, {}).get("Id")]
        return mine[-1] if mine else None
    except (OSError, ValueError):
        return None


def opening(p):
    """The first thing in the open chat: a companion message with its face, or what else is there."""
    return js(p, "(() => { const f = document.querySelector('.chat-view .chat-column > *'); return f && { message: !!f.matches('.ai-turn') && !!f.querySelector(':scope > .ai-msg.is-assistant'), face: !!f.querySelector(':scope > .ai-turn-face .face, :scope > .ai-turn-face img, :scope > .ai-turn-face canvas, :scope > .ai-turn-face'),"
                 " text: f.innerText.slice(0, 160), all: document.querySelector('.chat-view')?.innerText ?? '' } })()")


def shown(p, selector):
    return js(p, f"!!document.querySelector({json.dumps(selector)})")


def click(p, selector, words=""):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => (e.innerText + ' ' + (e.getAttribute('aria-label') ?? '')).includes({json.dumps(words)})); e?.click(); return !!e }})()")


def card(p):
    return js(p, "(() => { const c = document.querySelector('.joined-card'); return c && { title: c.querySelector('[data-slot=dialog-title]')?.innerText, line: c.querySelector('[data-slot=dialog-description]')?.innerText,"
                 " buttons: [...c.querySelectorAll('.joined-actions button')].map(b => b.innerText.trim()), mascot: !!c.querySelector('.crew-dialog-hero .mascot'), badge: !!c.querySelector('.joined-badge svg') } })()")


def say_hi(p, name):
    send(p, "new")
    until(lambda: shown(p, ".home-face") and not shown(p, ".mate-grid"), 10)
    until(lambda: js(p, "document.querySelector('.home-rail-item[aria-label=Companions]')?.click()") or shown(p, ".mate-grid"), 10, .5)
    return until(lambda: js(p, f"(() => {{ const b = [...document.querySelectorAll('.mate-card')].find(c => c.querySelector('h3')?.innerText === {json.dumps(name)})?.querySelector('.mate-chat'); b?.click(); return !!b }})()"), 5)


def library_add(p, name):
    send(p, "new")
    until(lambda: shown(p, ".home-face"), 15)
    js(p, "document.querySelector('.mate-switch-more[aria-label=\"Hire a companion\"]')?.click()")
    until(lambda: shown(p, ".companion-library"), 5)
    click(p, ".library-add", "Hire " + name)
    return until(lambda: (card(p) or {}).get("title") == name + " joined your team", 5)


def asked(p):
    return js(p, "(() => { const q = document.querySelector('.ask-card'); return q && { text: q.querySelector('.ask-q p')?.innerText, options: [...q.querySelectorAll('.ask-option span')].map(s => s.innerText),"
                 " own: q.querySelector('.ask-own input')?.placeholder, buttons: [...q.querySelectorAll('.ask-own button')].map(b => b.innerText.trim()) } })()")


def fake_agent(profile):
    (profile / "agents").mkdir(parents=True)
    (profile / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))


def ask(question, options, hello="Hi Sam! First up, a launch plan for your spring catalog. I'm pulling your recent posts now."):
    """A kickoff the way the role asks for it: its hello first, then (if it must) one question."""
    return {"say": hello, "calls": [{"name": "ask_user", "arguments": {"question": question, "options": options}}], "text": "Got it. Drafting the first week now."}


def hiring():
    profile = RUN / "hiring"
    fake_agent(profile)
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": [{**CREW[0], "Crew": "research"}], "AgentsEnabled": True, "AiHarness": "fake",
        "Width": 1280, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    X.plan({"Leo": [ask("Where do you post most?", ["LinkedIn", "Instagram", "Your newsletter"]), {"text": "On it."}],
            "Talia": [ask("Which channel should I size first?", ["Search", "Referrals"]), {"text": "On it."}], "Nora": [{"text": "Hello back."}],
            # Ivan reaches for a tool before saying anything: Still holds it until its hello, and the step never shows first.
            "Ivan": [{"steps": True, "calls": [{"name": "ask_user", "arguments": {"question": "Which site should I test?", "options": ["Shop", "Blog"]}}],
                      "text": "Hi Sam! I'm Ivan. I'll start by smoke-testing the site you have open."}],
            "nobody": [{"text": "Spring catalog launch"}, {"text": "Sizing the first channel"}, {"text": "Hello Nora"}, {"text": "Smoke-testing your site"}]})  # the title model
    p = launch(EXE, profile, env={**os.environ, "STILL_QA_TITLES": "1"})  # test builds only name chats when asked to
    try:
        # Hire from the library: the card, and nothing starts until the user says so.
        check(library_add(p, "Leo"), "Hiring Leo from the library says Leo joined your team")
        got = card(p) or {}
        check(got.get("buttons") == ["Not now", "Start chatting"] and got.get("mascot") and got.get("badge") and "first task" in (got.get("line") or ""),
              f"The card has Leo celebrating with a check, a line on what's next, Not now and Start chatting ({got})")
        check(until(lambda: mates(profile).get("Leo", {}).get("Greet") is True, 5), "Leo is new: its first chat is still to come")
        time.sleep(1.2)
        rpc(p, "capture", name="hire-joined.png")
        click(p, ".joined-card button", "Not now")
        check(until(lambda: not shown(p, ".joined-card"), 3) and shown(p, ".companion-library"), "Not now closes the card and leaves the library open")
        time.sleep(2)
        check(not kickoffs("Leo"), "and starts nothing")
        W.key(p, "Escape")

        # Say hi the first time: Leo opens the chat itself with its own message, then one question, and no message from the user.
        check(say_hi(p, "Leo"), "Say hi on the Companions page")
        check(until(lambda: len(kickoffs("Leo")) == 1, 20), "Leo starts its first chat itself")
        first = until(lambda: (o := opening(p)) and o.get("message") and o, 20) or {}
        check(first.get("message") and first.get("face") and first.get("text", "").startswith("Hi Sam! First up"), f"The first thing in the chat is Leo's own message, with its face ({first.get('text')!r})")
        check(first and "[Still]" not in first.get("all", "") and "You were just hired" not in first.get("all", ""), "The hidden note that started it never shows in the chat")
        got = until(lambda: (asked(p) or {}).get("options") and asked(p), 20) or {}
        check(got.get("text") == "Where do you post most?" and got.get("options") == ["LinkedIn", "Instagram", "Your newsletter"]
              and got.get("own") == "Or tell me what you're deciding…" and got.get("buttons") == ["Skip", "Send"],
              f"It asks one question: three choices, or your own words, Send or Skip ({got})")
        check("Getting started" not in (js(p, "document.body.innerText") or "x"), "No made-up title: until it's named, the chat goes by Leo's name")
        check(js(p, "document.querySelector('.chat-view')?.getAttribute('aria-label')") == "Chat with Leo", "Its chat is open in a tab")
        prompt = kickoffs("Leo")[0]["prompt"]
        check("Never open with a generic" in prompt and "your first words are your own message" in prompt and "# Marketing" in prompt and "learning their voice" in prompt,
              "Its hidden first turn asks for a hello and a first task for its role, with its role's setup")
        time.sleep(.8)
        rpc(p, "capture", name="hire-kickoff.png")
        click(p, ".ask-option", "Instagram")
        check(until(lambda: "Instagram" in memory(profile, "Leo") and "Where do you post most?" in memory(profile, "Leo"), 10), "The answer goes to Leo's memory")
        check(until(lambda: (first_chat(profile, "Leo") or {}).get("Title") == "Spring catalog launch", 15), f"The title model names the chat from Leo's hello ({(first_chat(profile, 'Leo') or {}).get('Title')!r})")
        check(any(q["name"] == "nobody" and "First up, a launch plan" in q["prompt"] for q in X.prompts()), "and it's given the hello, not the hidden note")
        chat = first_chat(profile, "Leo") or {}
        said = chat.get("Messages", [])
        check(said and said[0]["Role"] == "assistant" and [m["Role"] for m in said].count("user") == 1 and said[[m["Role"] for m in said].index("user")]["Text"] == "Instagram"
              and not [m for m in said if "[Still]" in m["Text"]], f"Saved: Leo spoke first, the user's only message is their answer, and the note isn't there ({[m['Role'] for m in said]})")
        check(until(lambda: mates(profile).get("Leo", {}).get("Greet") is False, 5), "and Leo isn't new anymore")

        # Reopening never starts it again.
        check(say_hi(p, "Leo"), "Say hi again")
        send(p, "aiKickoff", companion=mates(profile)["Leo"]["Id"])
        send(p, "chatOpen", id=chat.get("Id"))
        js(p, "location.reload()")
        time.sleep(4)
        check(len(kickoffs("Leo")) == 1, f"Saying hi again, reopening its chat or reloading doesn't start it again ({len(kickoffs('Leo'))})")

        # Start chatting: right away, once, even when pressed twice.
        check(library_add(p, "Talia"), "Hiring Talia says Talia joined")
        click(p, ".joined-card button", "Start chatting")
        send(p, "aiKickoff", companion=until(lambda: mates(profile).get("Talia", {}).get("Id"), 5))
        check(until(lambda: not shown(p, ".companion-library") and not shown(p, ".joined-card"), 5), "Start chatting closes the card and the library")
        check(until(lambda: len(kickoffs("Talia")) == 1, 20) and until(lambda: (asked(p) or {}).get("text") == "Which channel should I size first?", 20), "and Talia starts its first chat, asking its question")
        js(p, "document.querySelector('.ask-own input')?.focus()")
        W.type_into(p, ".ask-own input", "Whichever brings the biggest accounts")
        js(p, "document.querySelector('.ask-own button[type=submit]')?.click()")
        check(until(lambda: "biggest accounts" in memory(profile, "Talia"), 10), "Your own words go to its memory too")
        time.sleep(3)
        check(len(kickoffs("Talia")) == 1, "Pressed twice, it still starts once")

        # Talk to it first: it never kicks off.
        check(library_add(p, "Nora"), "Hiring Nora says Nora joined")
        click(p, ".joined-card button", "Not now")
        W.key(p, "Escape")
        nora = until(lambda: mates(profile).get("Nora", {}).get("Id"), 5)
        send(p, "new")
        until(lambda: shown(p, ".home-compose [aria-label=Message]"), 10)
        send(p, "aiSend", text="Hello Nora", home=True, companion=nora)
        until(lambda: any(q["name"] == "Nora" for q in X.prompts()), 20)
        say_hi(p, "Nora")
        time.sleep(4)
        said = [q["prompt"][-200:] for q in X.prompts() if q["name"] == "Nora"]
        check(not kickoffs("Nora") and mates(profile).get("Nora", {}).get("Greet") is False, f"Talking to a new companion first means it never kicks off ({said}, {mates(profile).get('Nora', {}).get('Greet')})")

        # A tool before the hello: Still holds it, then refuses, so the chat still opens with Ivan's words.
        check(library_add(p, "Ivan"), "Hiring Ivan says Ivan joined")
        click(p, ".joined-card button", "Start chatting")
        refused = until(lambda: X.calls("Ivan", "ask_user"), 20) or []
        check(refused and refused[0]["error"] and "Write your hello first" in refused[0]["text"], f"Asking before saying hello is refused ({refused[:1]})")
        first = until(lambda: (o := opening(p)) and o.get("message") and o, 20) or {}
        check(first.get("message") and first.get("text", "").startswith("Hi Sam! I'm Ivan"), f"The chat still opens with Ivan's message, not a step or a question card ({first.get('text')!r})")
        said = (until(lambda: (c := first_chat(profile, "Ivan")) and c.get("Messages") and c, 10) or {}).get("Messages", [])
        check(said and said[0]["Role"] == "assistant" and not shown(p, ".ask-card"), f"and nothing comes before it ({[m['Role'] for m in said]})")
    finally:
        rpc(p, "quit")
        until(lambda: p.poll() is not None, 15)


def after_setup():
    """A first setup that ends without a first task: the main companion has already started its first chat."""
    profile = RUN / "setup"
    fake_agent(profile)
    X.plan({"Maya": [ask("What are you researching this month?", ["Suppliers", "Competitors", "A trip"]), {"text": "On it."}]})
    p = launch(EXE, profile)
    try:
        until(lambda: shown(p, ".welcome.ob .ob-next"), 20)
        if until(lambda: shown(p, ".intro"), 3):
            time.sleep(1)
            W.key(p, " ")
            until(lambda: not shown(p, ".intro"), 3)
        time.sleep(1)
        W.to_crew(p)
        js(p, "document.querySelector(\".crew-pick[aria-label='Hire Maya']\")?.click()")
        time.sleep(.6)
        W.next_step(p, .8)  # -> tools
        W.not_now(p, .8)  # -> how
        until(lambda: W.click_text(p, ".ob-option", "Quick setup"), 6)
        time.sleep(1.2)
        while W.step_now(p) < 11 and not shown(p, ".ob-tasks"):
            at = W.step_now(p)
            W.click_text(p, ".ob-foot button", "Not now") or W.click(p, ".ob-next")
            if not until(lambda: W.step_now(p) == at + 1, 4):
                break
            time.sleep(.6)
        check(shown(p, ".ob-tasks") and not kickoffs("Maya"), "Setup reaches its last step, nothing started yet")
        W.click(p, ".ob-not-now")
        check(until(lambda: not shown(p, ".welcome.ob:not(.is-hidden)"), 6), "Not now finishes setup")
        check(until(lambda: len(kickoffs("Maya")) == 1, 20) and until(lambda: (asked(p) or {}).get("text") == "What are you researching this month?", 20),
              "and Maya has already started its first chat, with its question")
        time.sleep(.8)
        rpc(p, "capture", name="hire-after-setup.png")
        click(p, ".ask-option", "Suppliers")
        check(until(lambda: "Suppliers" in memory(profile, "Maya"), 10), "The answer goes to Maya's memory")
        js(p, "location.reload()")
        time.sleep(2)
        say_hi(p, "Maya")
        time.sleep(4)
        check(len(kickoffs("Maya")) == 1, "Reloading or saying hi doesn't start it again")
    finally:
        rpc(p, "quit")
        until(lambda: p.poll() is not None, 15)


def main():
    BIN.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(X.FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    hiring()
    for f in ("prompts.jsonl", "calls.jsonl"):
        (BIN / f).unlink(missing_ok=True)
    after_setup()
    # No test stub ships: the fake agent and its plan line exist only in test profiles.
    stub = [str(f.relative_to(SRC)) for f in [*SRC.glob("still/Shell/assets/*.js"), *SRC.glob("still/*.cs"), *SRC.glob("still/Agents/*.cs"), *SRC.glob("mac/Sources/Still/*.swift"), *SRC.glob("still-ui/src/*.tsx")]
            if any(w in f.read_text(encoding="utf-8", errors="replace").lower() for w in ("fake agent", "fakeagent"))]
    check(not stub, f"No fake agent in the app's code or its built UI ({stub})")
    print(f"\n{len(FAILED)} failed" if FAILED else "\nAll hire checks passed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
