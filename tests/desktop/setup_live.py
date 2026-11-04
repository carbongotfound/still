"""Setup through a real signed-in agent app (uses that plan; Claude Haiku at low effort by default). First the four
steps on a fresh profile: connect the app, hire Miso, and setup's first task, the sample page that ships with Still,
which Miso opens, reads and compares. Then Set me up again with Jonah: a baker answers Jonah's questions, skips one,
and the interview runs until Jonah has what it needs (or "That's enough" after ten turns). Checks the follow-ups and
what it set up: companions suggested from the library (none hired), what Jonah focuses on, memories, a first task.
Frames of the whole interview go to frames/ (for a GIF). Questions are skipped; nothing is approved or sent. Run it by
hand only.

Run: python tests/desktop/setup_live.py artifacts/Still-QA/Still.exe [claude] [model] [effort]
"""
import json
from pathlib import Path
import re
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import js, launch, rpc, send, until  # noqa: E402
import welcome as W  # noqa: E402  setup's steps

ROOT = Path(__file__).resolve().parents[2]
EXE = Path(sys.argv[1]).resolve()
AGENT = sys.argv[2] if len(sys.argv) > 2 else "claude"
MODEL = sys.argv[3] if len(sys.argv) > 3 else "haiku"
EFFORT = sys.argv[4] if len(sys.argv) > 4 else "low"
RUN = ROOT / "artifacts" / ("setup-live-" + AGENT + "-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
# The baker's answers, by what the question is about (the first topic word found wins); the third question is skipped.
ANSWERS = [(("first", "start with", "right now", "help with"), "First, find me a flour supplier near Portland with next-day delivery."),
           (("hours", "days", "schedule", "check-in"), "I start at 5am and I'm done by 1pm, Monday to Saturday. Mornings are chaos, afternoons are for admin."),
           (("answers", "replies", "reply", "tone", "short"), "Short and direct, no fluff. Bullet points are fine."),
           (("apps", "sites", "tools"), "Gmail all day, Shopify for the shop, a Google Sheet for cafe orders, and Instagram."),
           (("months", "goal", "trying", "grow", "want to"), "Growing wholesale to ten cafes by spring, and hiring a second baker for the early shift."),
           (("order", "hear from"), "Standing weekly orders, mostly by text. Two cafes email on Sunday night."),
           (("",), "I run a small bakery. We sell sourdough to six cafes in town, plus walk-ins on Saturdays.")]
TURNS = 10
CHECKS = []
RESULT = {}


def check(ok, name):
    CHECKS.append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def first_task():
    """The four steps with the real app, then the sample page as the first task: Miso opens it, reads it and compares."""
    profile = RUN / "first"
    profile.mkdir(parents=True)
    process = launch(EXE, profile)
    chats = lambda: json.loads((profile / "ai" / "chats.json").read_text(encoding="utf-8")) if (profile / "ai" / "chats.json").exists() else []
    try:
        until(lambda: js(process, "!!document.querySelector('.welcome.ob .ob-dots')"), 20)
        if until(lambda: js(process, "!!document.querySelector('.intro')"), 3):
            time.sleep(1)
            W.key(process, " ")
        time.sleep(3)
        send(process, "aiAdvanced", on=True)
        send(process, "aiModel", harness=AGENT, model=MODEL, effort=EFFORT)
        W.next_step(process)
        W.pick_ai(process, "Claude" if AGENT == "claude" else AGENT)
        check(until(lambda: "is ready" in W.card(process), 30), f"Connect finds the app signed in ({W.card(process)[:80]!r})")
        W.next_step(process)
        check(W.make(process, "Miso", "Helps me shop: compares products and prices for me.", wait=150), "Miso asks what to help with in a chat, then says what it will do")
        plain = js(process, "[...document.querySelectorAll('.ob-plain li')].map(l => l.innerText.trim())") or []
        check(len(plain) >= 1 and not js(process, "document.querySelector('.ob-more')?.open"), f"in plain words, with the instructions closed ({plain})")
        time.sleep(1)
        W.click(process, ".ob-next")  # Hire Miso
        until(lambda: js(process, "!!document.querySelector('.joined-card')"), 6)
        W.click_text(process, ".joined-actions button", "Start chatting")
        until(lambda: W.step_now(process) == 4, 5)
        time.sleep(1.5)
        W.click(process, ".ob-tasks [role=radio]")
        time.sleep(.6)
        W.click(process, ".ob-next")
        miso = until(lambda: next((c for c in chats() if c.get("Messages")), None), 30) or {}
        asked = next((m.get("Text", "") for m in miso.get("Messages", []) if m.get("Role") == "user"), "")  # after Still's note, on a fresh profile, that it let the app use the tabs
        check(asked.startswith("Open https://sample.still.internal/compare.html"), "Let's go starts the sample task in Miso's chat")

        def done():
            now = next((c for c in chats() if c["Id"] == miso.get("Id")), {})
            if now.get("Running"):
                send(process, "aiAnswer", id=now["Id"], text="")  # a question is skipped
            return not now.get("Running") and any(m["Role"] == "assistant" and m["Text"].strip() for m in now.get("Messages", [])) and now
        end = until(done, 300, 5) or {}
        answer = "\n\n".join(m["Text"] for m in end.get("Messages", []) if m["Role"] == "assistant")
        rpc(process, "capture", name="first-task.png")
        check(all(n in answer for n in ("Pinecrest", "Tallow", "Marlin")) and sum(p in answer for p in ("129", "74", "159")) >= 2,
              f"Miso compares the three packs from the page, with their prices ({len(answer)} characters)")
        check(any(t["InChat"] and "sample.still.internal" in t["Url"] for t in rpc(process)["tabs"]), "It worked in its own tab, beside the chat")
        RESULT["first"] = {"answer": answer, "messages": [{"role": m["Role"], "text": m["Text"]} for m in end.get("Messages", [])]}
        rpc(process, "quit")
        process.wait(timeout=15)
    finally:
        if process.poll() is None:
            process.kill()


def main():
    PROFILE.mkdir(parents=True)
    src = (ROOT / "still-ui" / "src" / "crew.tsx").read_text(encoding="utf-8")
    job, tone = re.search(r'\{ id: "sales", name: "Jonah".*?job: "((?:[^"\\]|\\.)*)",\s*tone: "((?:[^"\\]|\\.)*)"', src, re.S).groups()
    jonah = {"Id": "zest0001", "Name": "Jonah", "Job": job, "Tone": tone, "Crew": "sales", "Mode": "default"}
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": [jonah], "AiHarness": AGENT, "Width": 1250, "Height": 800},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    frames, shot, said = RUN / "frames", [0], []
    frames.mkdir()

    def film():
        shot[0] += 1
        rpc(process, "capture", name=f"frame-{shot[0]:03}.png")

    def bubbles():
        return js(process, "[...document.querySelectorAll('.ob-chat .ob-bubble:not(.is-typing)')].map(b => (b.classList.contains('is-you') ? 'you: ' : 'jonah: ') + b.innerText.trim())") or []

    def wait():  # for Jonah's next message, filming as it types
        end = time.monotonic() + 150
        while time.monotonic() < end:
            film()
            if js(process, "!document.querySelector('.ob-bubble.is-typing') && (!!document.querySelector('.ob-summary, .ob-fallback') || !!document.querySelector('.ob-say input'))"):
                return True
            time.sleep(.6)
        return False
    started = time.monotonic()
    try:
        send(process, "aiCheck")
        time.sleep(4)
        send(process, "aiAdvanced", on=True)
        send(process, "aiModel", harness=AGENT, model=MODEL, effort=EFFORT)
        send(process, "welcomeAgain", talk=True)
        until(lambda: js(process, "!!document.querySelector('.ob-interview')"), 20)
        time.sleep(1)
        wait()
        answers = 0
        while not js(process, "!!document.querySelector('.ob-summary, .ob-fallback')") and answers < TURNS:
            time.sleep(1.5); film()
            asked = " ".join(re.findall(r"[^.?!]*\?", (bubbles() or [""])[-1])).lower()  # the questions, not what it says first
            answer = "(skip)" if answers == 2 else next(a for words, a in ANSWERS if any(w in asked for w in words))
            if answer == "(skip)":
                js(process, "[...document.querySelectorAll('.ob-interview-foot button')].find(b => b.innerText.includes('Skip'))?.click()")
            else:
                js(process, f"""(() => {{ const e = document.querySelector('.ob-say input'); e.focus(); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, {json.dumps(answer)});
                 e.dispatchEvent(new Event('input', {{ bubbles: true }})) }})()""")
                time.sleep(.8); film()
                js(process, "document.querySelector('.ob-say')?.requestSubmit()")
            answers += 1
            time.sleep(.5)
            wait()
        if not js(process, "!!document.querySelector('.ob-summary, .ob-fallback')"):
            js(process, "[...document.querySelectorAll('.ob-interview-foot button')].find(b => b.innerText.includes('enough'))?.click()")
            time.sleep(.5)
            wait()
        said = bubbles()
        error = js(process, "document.querySelector('.ob-fallback')?.innerText") or ""
        check(not error and js(process, "!!document.querySelector('.ob-summary')"), f"The interview ends in a summary ({error or len(said)} messages)")
        asks = [b for b in said if b.startswith("jonah: ")]
        check(len(asks) >= 4 and len(set(asks)) == len(asks), f"Jonah asked {len(asks) - 1} questions, none twice")
        check(any(w in " ".join(asks[1:3]).lower() for w in ("cafe", "bakery", "sourdough", "wholesale", "bake")), "Its follow-ups build on the answers (they mention the bakery)")
        time.sleep(2); film()
        rows = js(process, "[...document.querySelectorAll('.ob-summary li')].map(l => l.querySelector('b').innerText.trim() + ': ' + (l.querySelector('small')?.innerText.trim() ?? ''))") or []
        time.sleep(3)  # saved a moment later
        prefs = json.loads((PROFILE / "state.json").read_text(encoding="utf-8")).get("Preferences", {})
        team = prefs.get("Companions", [])
        check(any(r.startswith("Suggested for your team: ") for r in rows) and [c["Name"] for c in team] == ["Jonah"], f"It suggests companions from the library and hires nobody ({[c['Name'] for c in team]})")
        check(all(c["Job"].count("For me: ") == 1 for c in team), "Jonah got what to focus on for this user")
        check(all(not r["On"] for c in team for r in c.get("Routines", [])), "Any routine it set up starts off")
        check(any(r.startswith("First, I'll help with: ") and "flour" in r.lower() for r in rows), "The first task is the one asked for")
        facts = json.loads((PROFILE / "companions" / "zest0001" / "memory.json").read_text(encoding="utf-8")) if (PROFILE / "companions" / "zest0001" / "memory.json").exists() else []
        check(len(facts) >= 3, f"Jonah remembers {len(facts)} things about the user")
        rpc(process, "capture", name="summary.png")
        js(process, "document.querySelector('.ob-summary').scrollTop = 1e6")
        time.sleep(.6); film()
        rpc(process, "capture", name="summary-end.png")
        (RUN / "result.json").write_text(json.dumps({**RESULT, "agent": AGENT, "model": MODEL, "effort": EFFORT, "minutes": round((time.monotonic() - started) / 60, 1), "said": said, "rows": rows,
                                                    "companions": [{k: c.get(k) for k in ("Name", "Crew", "Job", "Tone", "Routines")} for c in team], "facts": [f["Text"] for f in facts],
                                                    "checks": CHECKS}, indent=2))
        rpc(process, "quit")
        process.wait(timeout=15)
    finally:
        if process.poll() is None:
            process.kill()
        for f in PROFILE.glob("frame-*.png"):
            f.replace(frames / f.name)
        failed = [c["name"] for c in CHECKS if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(CHECKS) - len(failed)}/{len(CHECKS)}", "->", RUN)


first_task()
main()
W.SERVER.shutdown()
