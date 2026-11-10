"""Assistant Ruth: hired from the library only (never by setup, never on a fresh profile), she can be made the main
companion from the card that greets her, she's still Ruth after a restart, and her prompt carries her brief and kit
(still/Assets/roles/assistant).
A request with two parts goes to two hired teammates as child tasks of her one chat, and she returns one answer. She
can't ask anyone who isn't hired, and a teammate she asks acts only where she may too: approvals come to the user, in
her chat.

No AI plan is used: the same fake agent app as exchange.py plays every companion from plan.json.

Run: python tests/desktop/assistant.py artifacts/Still-QA/Still.exe [OUTDIR]  (OUTDIR: screenshots)
"""
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import press_ready, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402
import exchange as X  # noqa: E402  the fake agent app and its chat helpers

RUN = ROOT / "artifacts" / ("assistant-" + uuid.uuid4().hex[:8])
X.RUN, X.PROFILE, X.BIN = RUN, RUN / "profile", RUN / "bin"
PROFILE, BIN = X.PROFILE, X.BIN
FAILED = []
BRIEF = "You're the user's personal assistant in Still"


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def state():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def team():
    return state().get("Preferences", {}).get("Companions") or []


def shot(name):
    time.sleep(.8)
    rpc(X.P, "capture", name=name)
    if (PROFILE / name).exists():
        shutil.copy(PROFILE / name, OUT / name)


def library_hire(title):
    """Hires one of Still's companions from the library by its card title; returns its card's text."""
    if not js(X.P, "!!document.querySelector('.companion-library')"):
        js(X.P, "document.querySelector(\".mate-switch-more[aria-label='Hire a companion']\")?.click()")
        until(lambda: js(X.P, "!!document.querySelector('.companion-library')"), 5)
    card = f"[...document.querySelectorAll('.library-card')].find(c => c.querySelector('.role-title')?.innerText === {json.dumps(title)})"
    js(X.P, f"{card}?.querySelector('.library-add')?.click()")
    return until(lambda: js(X.P, "document.querySelector('.joined-card')?.innerText ?? ''"), 5) or ""


def setup():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(X.FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    crew = [{"Id": "maya", "Name": "Maya", "Job": "Research for the user: briefs with a source for every claim.", "Crew": "research", "Autonomy": "balanced"},
            {"Id": "jonah", "Name": "Jonah", "Job": "Sales for the user: leads, call prep and follow-up drafts.", "Crew": "sales", "Autonomy": "balanced"}]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake", "Theme": "Light",
        "Width": 1280, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, PROFILE)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    X.P = P = setup()
    try:
        until(lambda: js(P, "!!document.body.innerText.length"), 20)
        send(P, "new")
        until(lambda: js(P, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
        js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        time.sleep(.5)

        # The library has her last, after the six. Hiring one of the six greets them with no main-companion offer.
        joined = library_hire("Planner Nora")
        names = json.loads(js(P, "JSON.stringify([...document.querySelectorAll('.library-card .role-title')].map(e => e.innerText))") or "[]")
        check(names[-1:] == ["Assistant Ruth"] and len(names) == 7, f"The library lists Assistant Ruth after the six ({names})")
        line = js(P, "[...document.querySelectorAll('.library-card')].find(c => c.querySelector('.role-title')?.innerText === 'Assistant Ruth')?.querySelector('.role-expect p')?.innerText")
        check(line == "Your personal assistant. Ask her anything, and she'll handle it or bring in the right companion.", f"Her card says what she does ({line!r})")
        check("Nora" in joined and not js(P, "!!document.querySelector('.joined-main')"), "Hiring Nora offers no main-companion button")
        js(P, "[...document.querySelectorAll('.joined-actions button')].find(b => b.innerText.trim() === 'Not now')?.click()")
        until(lambda: not js(P, "!!document.querySelector('.joined-card')"), 5)

        # Hiring Ruth: one click makes her the main companion, never by itself.
        joined = library_hire("Assistant Ruth")
        offer = js(P, "document.querySelector('.joined-main button')?.innerText.trim()") or ""
        ruth = until(lambda: next((c for c in team() if c.get("Crew") == "assistant"), None), 5) or {}  # saved a moment later
        check(ruth.get("Name") == "Ruth" and offer == "Make Ruth your main companion", f"Hiring Ruth offers to make her the main companion ({offer!r})")
        check("Ruth is here for anything you need, and will open with a first task picked for your work." in joined, f"The card says what she's here for ({joined[:160]!r})")
        check(team()[0].get("Crew") != "assistant", "She isn't made main until the user says so")
        shot("joined-ruth.png")
        js(P, "document.querySelector('.joined-main button')?.click()")
        check(until(lambda: team() and team()[0].get("Crew") == "assistant", 5), f"Make main puts her first, so she runs new chats ({[c['Name'] for c in team()]})")
        done = until(lambda: (lambda t: t if "is your main" in t else "")(js(P, "document.querySelector('.joined-main button')?.innerText.trim()") or ""), 5) or ""
        check(done == "Ruth is your main companion" and js(P, "document.querySelector('.joined-main button').disabled"), f"The button says it's done ({done!r})")
        shot("joined-ruth-main.png")
        js(P, "[...document.querySelectorAll('.joined-actions button')].find(b => b.innerText.trim() === 'Not now')?.click()")
        time.sleep(.5)
        js(P, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        check(until(lambda: not js(P, "!!document.querySelector('.companion-library')"), 5), "Escape closes the library")
        rid = ruth.get("Id") or "missing"

        # Her prompt carries her brief, role and kit.
        X.plan({"Ruth": [{"text": "Hi, I'm Ruth."}]})
        hi = X.new_chat("Hi Ruth.", companion=rid)
        check(X.settled(hi, 1), "Ruth answers")
        first = next((p["prompt"] for p in X.prompts() if p["name"] == "Ruth"), "")
        check(BRIEF in first and "Your role: Assistant." in first, "Her prompt has her brief and her role")
        kit = ("handle-it", "route-request", "split-and-merge", "status-update", "daily-brief", "Requests", "Team", "How you like things")
        check(all(k in first for k in kit), f"and her five skills and her knowledge files ({[k for k in kit if k not in first]} missing)")

        # A request with two parts: one chat, two child tasks, one answer.
        X.plan({"Ruth": [{"text": "Here's both.\n\n{1}\n\n{2}\n\nMaya wrote the brief and Jonah the draft.", "calls": [
                    {"name": "list_companions", "arguments": {}},
                    {"name": "ask_companion", "arguments": {"name": "Maya", "message": "Write a short brief on Acme Bakery as a prospect, with sources.", "title": "a prospect brief"}},
                    {"name": "ask_companion", "arguments": {"name": "Jonah", "message": "Draft a short outreach email to Acme Bakery.", "title": "an outreach draft"}}]}],
                "Maya": [{"text": "Acme Bakery: three shops, wholesale to cafes. Source: https://example.com/acme"}],
                "Jonah": [{"text": "Hi Acme team, we help bakeries like yours get cafe orders in on time."}]})
        top, every = X.tops(), len(X.chats())
        both = X.new_chat("Brief me on Acme Bakery as a prospect and draft an outreach email.", companion=rid)
        check(X.settled(both, 1, 60), "Ruth finishes")
        c = X.chat(both)
        listed = json.loads(X.calls("Ruth", "list_companions")[0]["text"] or "{}").get("companions", [])
        check(sorted(m["name"] for m in listed) == ["Jonah", "Maya", "Nora", "Ruth"] and any(m["name"] == "Ruth" and m.get("you") for m in listed),
              f"list_companions shows only the hired team, her included ({[m['name'] for m in listed]})")
        check(X.cards(c) == [("ask", rid, "maya", "replied"), ("ask", rid, "jonah", "replied")], f"Two asks, both replied ({X.cards(c)})")
        kids = [k for k in X.chats() if k.get("From") == both]
        check(sorted(k["Companion"] for k in kids) == ["jonah", "maya"] and len(X.chats()) == every + 3, f"Each part is a child task of her chat ({[k['Title'] for k in kids]})")
        check(sorted(X.tops()) == sorted(top + [both]), "History gains one chat for the request")
        said = X.said(c)
        check(len(said) == 1 and "three shops" in said[0] and "Hi Acme team" in said[0], f"She returns one answer with both parts ({said})")
        shot("routed.png")

        # Someone who isn't hired can't be asked.
        X.plan({"Ruth": [{"text": "Talia isn't on your team. {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Talia", "message": "Draft a referral program."}}]}]})
        every = len(X.chats())
        nobody = X.new_chat("Have Talia draft a referral program.", companion=rid)
        check(X.settled(nobody, 1), "Ruth answers")
        refused = X.calls("Ruth", "ask_companion")[-1]
        check(refused["error"] and "No teammate is called \"Talia\"" in refused["text"] and len(X.chats()) == every + 1, f"Asking someone not hired is refused, and no task starts ({refused['text']!r})")

        # A teammate acts only where Ruth may too: Maya may always click here, Ruth has to ask. The ask comes to the user in Ruth's chat.
        site = X.pages()
        send(P, "permSet", site="127.0.0.1", action="interact", companion=rid, mode="ask")
        send(P, "permSet", site="127.0.0.1", action="interact", companion="maya", mode="always")
        X.plan({"Ruth": [{"text": "Maya did it: {0}", "calls": [{"name": "ask_companion", "arguments": {"name": "Maya", "message": "Open the review and click its heading.", "title": "a click"}}]}],
                "Maya": [{"text": "Clicked it.", "calls": [{"name": "open_tab", "arguments": {"url": site + "/review"}}, {"name": "read_page", "arguments": {}}, {"name": "click", "arguments": {"selector": "h1"}}]}]})
        chain = X.new_chat("Have Maya click the review's heading.", companion=rid)
        card = until(lambda: js(P, "document.querySelector('.chat-view .approve-card')?.innerText ?? ''"), 30) or ""
        check(X.shown_chat() == chain and "Maya wants to do this" in card, f"Maya's click asks first, in Ruth's chat ({card[:80]!r})")
        shot("needs-you.png")
        press_ready(P, "document.querySelector('.chat-view .approve-card [data-approve]')")
        check(X.settled(chain, 1, 30) and X.calls("Maya", "click") and not X.calls("Maya", "click")[-1]["error"], "Once the user allows it, Maya's click goes ahead")
        send(P, "permSet", site="127.0.0.1", action="interact", companion=rid, mode="")
        send(P, "permSet", site="127.0.0.1", action="interact", companion="maya", mode="")
    finally:
        rpc(P, "quit")
        P.wait(timeout=20)

    # After a restart she's still Ruth, still the assistant and still first (an old crew id would move her to another role).
    R = launch(EXE, PROFILE)
    try:
        until(lambda: js(R, "!!document.body.innerText.length"), 20)
        time.sleep(1.5)
    finally:
        rpc(R, "quit")
        R.wait(timeout=20)
    again = team()
    check(again and again[0].get("Name") == "Ruth" and again[0].get("Crew") == "assistant" and again[0].get("Id") == rid,
          f"After a restart she's still Assistant Ruth, first on the team ({[(c.get('Name'), c.get('Crew')) for c in again]})")

    # A fresh profile starts without her.
    fresh = RUN / "fresh"
    fresh.mkdir()
    F = launch(EXE, fresh)
    try:
        until(lambda: js(F, "!!document.body.innerText.length"), 20)
        time.sleep(1)
    finally:
        rpc(F, "quit")
        F.wait(timeout=20)
    mates = json.loads((fresh / "state.json").read_text(encoding="utf-8")).get("Preferences", {}).get("Companions") if (fresh / "state.json").exists() else None
    check(mates is not None and not any(c.get("Crew") == "assistant" for c in mates), f"A fresh profile has no Assistant Ruth ({[c.get('Name') for c in mates or []]})")
    print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'ALL PASSED'}  shots in {OUT}")
    sys.exit(1 if FAILED else 0)


EXE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else RUN / "shots"
if __name__ == "__main__":
    main()
