"""Stage 8 live checks through a real signed-in agent app (uses that plan; Claude Haiku at low effort by default):
the Setup skill's first message when a companion speaks first, a first message that is a task, Short versus Detailed
replies, two custom companions with different goals given the same task, and nothing remembered from incognito or
off-record chats. Pages can be read, nothing is approved or sent, and questions after the first are skipped.
Run it by hand only.

Run: python tests/desktop/personalize_live.py artifacts/Still-QA/Still.exe [claude] [model] [effort]
Writes artifacts/personalize-live-<id>/result.json and transcripts.md.
"""
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import js, launch, rpc, send, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXE = Path(sys.argv[1]).resolve()
AGENT = sys.argv[2] if len(sys.argv) > 2 else "claude"
MODEL = sys.argv[3] if len(sys.argv) > 3 else "haiku"
EFFORT = sys.argv[4] if len(sys.argv) > 4 else "low"
RUN = ROOT / "artifacts" / f"personalize-live-{uuid.uuid4().hex[:6]}"
PROFILE = RUN / "profile"
SETUP = '[Skill "Setup"'
ASKS = ["Explain what an index fund is.", "How do I keep basil alive indoors?", "What should I check before signing a lease on a flat?"]
PLAN = "I have a free afternoon tomorrow. Give me your work plan for it, in steps."
TASK = "Give me a checklist of five things to check before buying a used bike."
GOALS = {"ledger": ("Ledger", "Bookkeeper", "Keep my freelance finances in order: invoices, expenses and taxes", ("invoice", "expense", "tax", "receipt")),
         "spark": ("Spark", "Promoter", "Grow my freelance design business: find new clients and get my work seen", ("client", "portfolio", "post", "lead"))}
HOWDY = re.compile(r"how can i (help|assist)|what can i (do|help)", re.I)
FAILED, RESULTS, OUT = [], {}, [f"# Stage 8 live: {AGENT} {MODEL} {EFFORT}\n"]


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def make(goal, role):
    """What "Suggest instructions and skills" makes for this goal and role (the same generator, run by node)."""
    out = subprocess.run(["node", str(ROOT / "tests" / "generate.mjs"), "--make", goal, role], capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout.strip().splitlines()[-1])


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def chat(cid):
    return next((c for c in chats() if c["Id"] == cid), {"Messages": []})


def prompts(cid=None):
    file = PROFILE / "qa-prompts.jsonl"
    got = [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines() if l.strip()] if file.exists() else []
    return [q for q in got if cid is None or q.get("chat") == cid]


def memory(cid):
    file = PROFILE / "companions" / cid / "memory.json"
    return file.read_text(encoding="utf-8") if file.exists() else ""


def asked(p):
    return js(p, "document.querySelector('.ask-card')?.innerText ?? ''") or ""


def settle(p, cid, answers=(), seconds=600):
    """Runs a chat to the end: the first questions get these answers, later ones are skipped. Returns what was asked."""
    questions, quiet, end = [], 0, time.monotonic() + seconds
    while time.monotonic() < end:
        c = chat(cid)
        if c.get("Running"):
            quiet = 0
            q = asked(p)
            if q and (not questions or questions[-1] != q):
                questions.append(q)
                time.sleep(1)
                send(p, "aiAnswer", id=cid, text=answers[len(questions) - 1] if len(questions) <= len(answers) else "")
            elif not q:  # a question in another tab, or a card the page can't see: skip it
                send(p, "aiAnswer", id=cid, text="")
        elif c["Messages"] and any(m["Role"] == "assistant" for m in c["Messages"]):
            quiet += 1
            if quiet >= 3:
                return questions
        time.sleep(2)
    return questions


def start(p, companion, text):
    before = {c["Id"] for c in chats()}
    send(p, "new")
    time.sleep(1)
    send(p, "aiSend", text=text, home=True, companion=companion)
    return until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before and c["Companion"] == companion), None), 30, .5)


def said(cid, role="assistant"):
    return [m["Text"] for m in chat(cid)["Messages"] if m["Role"] == role]


def record(key, cid, **extra):
    c = chat(cid)
    RESULTS[key] = {"chat": cid, "messages": [{"role": m["Role"], "text": m["Text"]} for m in c["Messages"]], "seconds": c.get("Worked", 0), **extra}
    OUT.extend([f"## {key}", *[f"**{m['Role']}**: {m['Text']}" for m in c["Messages"]], ""])


def chips(text):
    return [l for l in text.strip().splitlines() if l.startswith(">> ")]


def words(text):
    return {w for w in re.findall(r"[a-z]{4,}", text.lower())}


def main():
    PROFILE.mkdir(parents=True)
    (PROFILE / "skills").mkdir()
    allow = [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate")]
    src = (ROOT / "still-ui" / "src" / "crew.tsx").read_text(encoding="utf-8")
    maya = re.search(r'\{ id: "research", name: "Maya".*?job: "((?:[^"\\]|\\.)*)",\s*tone: "((?:[^"\\]|\\.)*)"', src, re.S)
    mates = [{"Id": "maya", "Name": "Maya", "Job": maya[1], "Tone": maya[2], "Crew": "research", "Mode": "default", "Greet": True},
             {"Id": "brief", "Name": "Bea", "Job": "Answers my everyday questions.", "Length": "short", "Mode": "default"},
             {"Id": "deep", "Name": "Dee", "Job": "Answers my everyday questions.", "Length": "detailed", "Mode": "default"}]
    made = {}
    for cid, (name, role, goal, _) in GOALS.items():  # made with the generator, then already chatted with: no Setup, so the plans compare cleanly
        g = made[cid] = make(goal, role)
        mates.append({"Id": cid, "Name": name, "Role": role, "Job": g["job"], "Skills": g["skills"], "Mode": "default"})
        for k in g["skills"]:
            shutil.copy(next((ROOT / "still" / "Assets" / "roles").glob(f"*/skills/{k}.md")), PROFILE / "skills" / f"{k}.md")
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": mates, "AgentsEnabled": True, "AiHarness": AGENT,
        "Permissions": allow, "Width": 1400, "Height": 900}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    started = time.monotonic()
    try:
        send(p, "aiCheck")
        time.sleep(4)
        send(p, "aiAdvanced", on=True)
        send(p, "aiModel", harness=AGENT, model=MODEL, effort=EFFORT)
        pip = make("Find the best price for anything before I buy it, and compare the options", "Scout")
        send(p, "companionSave", id="scout", name="Pip", role="Scout", personality="direct", length="balanced", job=pip["job"], skills=pip["skills"])
        until(lambda: any(c["Id"] == "scout" for c in json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]["Companions"]), 10)

        # 1. Maya speaks first: Setup's first message.
        send(p, "aiKickoff", companion="maya")
        kick = until(lambda: next((c["Id"] for c in chats() if c["Companion"] == "maya"), None), 60, .5)
        questions = settle(p, kick, ["I run a small bakery in Portland. We sell sourdough to six cafes."])
        record("kickoff", kick, questions=questions)
        msgs = chat(kick)["Messages"]
        first = next((m["Text"] for m in msgs if m["Role"] == "assistant"), "")
        last = (said(kick) or [""])[-1]
        before_reply = [m for m in msgs[:next((i for i, m in enumerate(msgs) if m["Role"] == "user"), len(msgs))]]
        asks = len(questions) + sum(l.strip().endswith("?") for m in before_reply if m["Role"] == "assistant" for l in m["Text"].splitlines() if not l.startswith(">> "))
        sent = prompts(kick)
        check(msgs and msgs[0]["Text"] == "Used skill Setup", f"Kickoff: 'Used skill Setup' is the first step ({msgs[0]['Text'] if msgs else None!r})")
        check(sum(q["prompt"].count(SETUP) for q in sent) == 1 and sent and SETUP in sent[0]["prompt"], f"Kickoff: the Setup body is in the first turn once, never again ({[q['prompt'].count(SETUP) for q in sent]})")
        check("Research Maya" in first, f"Kickoff: the first message names her role first ({first[:120]!r})")
        check(not HOWDY.search(first[:200]), "Kickoff: it doesn't open with how can I help")
        check(asks <= 2, f"Kickoff: two questions at most before the user answers ({asks}: {questions})")
        check(2 <= len(chips(last)) <= 3, f"Kickoff: it ends with two or three next steps ({chips(last)})")
        RESULTS["kickoff"]["memory"] = memory("maya")

        # Maya's next chat has no Setup.
        later = start(p, "maya", "What's a simple way to track weekly cafe orders? Three lines.")
        settle(p, later)
        record("maya-second", later)
        check(prompts(later) and not any(SETUP in q["prompt"] for q in prompts(later)), "Her next chat has no Setup text")

        # 2. Pip's first chat is a task: a one-line intro, then the task.
        task = start(p, "scout", TASK)
        settle(p, task)
        record("task-first", task)
        msgs = chat(task)["Messages"]
        reply = "\n".join(said(task))
        steps = [m["Text"] for m in msgs if m["Role"] == "tool"]
        items = [l for l in reply.splitlines() if re.match(r"\s*(\d+[.)]|[-*•]|\[ \])\s+\S", l)]
        check(steps[:1] == ["Used skill Setup"] and sum(SETUP in q["prompt"] for q in prompts(task)) == 1, f"Task first: Setup loads once, as the first step ({steps[:3]})")
        check("Scout Pip" in reply and len(items) >= 5, f"Task first: Scout Pip introduces itself and does the task ({len(items)} list items)")
        check(not HOWDY.search(reply[:200]), "Task first: no how can I help")

        # 3. Short versus Detailed on the same questions.
        lengths = {"brief": [], "deep": []}
        for q in ASKS:
            for cid in lengths:
                c = start(p, cid, q)
                settle(p, c)
                record(f"{cid}: {q}", c)
                lengths[cid].append(len("\n".join(said(c))))
        avg = {k: round(sum(v) / len(v)) for k, v in lengths.items()}
        RESULTS["lengths"] = {"each": lengths, "average": avg}
        check(avg["deep"] >= 1.5 * avg["brief"], f"Detailed replies run at least half again as long as Short ones ({avg})")

        # 4. Two custom companions with different goals, the same task.
        plans = {}
        for cid in GOALS:
            c = start(p, cid, PLAN)
            settle(p, c)
            record(f"plan-{cid}", c, made=made[cid])
            plans[cid] = "\n".join(said(c))
        a, b = (words(plans[k]) for k in GOALS)
        overlap = round(len(a & b) / max(1, len(a | b)), 2)
        own = {k: sum(w in plans[k].lower() for w in GOALS[k][3]) for k in GOALS}
        RESULTS["plans"] = {"overlap": overlap, "own goal words": own}
        check(overlap < .35 and all(n >= 2 for n in own.values()), f"The two plans differ in approach: {overlap:.0%} shared words, each about its own goal ({own})")

        # 5. Nothing from an off-record or an incognito chat is remembered.
        off = start(p, "brief", "Hi Bea.")
        settle(p, off)
        send(p, "chatNoMemory", id=off, on=True)
        send(p, "chatOpen", id=off)
        time.sleep(2)
        send(p, "aiSend", text="Remember that I'm allergic to peanuts.")
        until(lambda: chat(off).get("Running"), 30, .5)
        settle(p, off)
        record("off-record", off)
        before = {w["id"] for w in rpc(p)["windows"]}
        send(p, "incognitoWindow")
        wid = until(lambda: next((w["id"] for w in rpc(p)["windows"] if w["incognito"] and w["id"] not in before), None), 15)
        until(lambda: rpc(p, "shellEval", window=wid, script="!!document.querySelector('[aria-label=Message]')"), 15)
        rpc(p, "shellEval", window=wid, script="window.chrome.webview.postMessage(" + json.dumps({"op": "aiSend", "text": "Remember that my sister Lena lives in Oslo.", "home": True, "companion": "brief"}) + ")")
        until(lambda: rpc(p, "shellEval", window=wid, script="document.querySelectorAll('.ai-msg.is-assistant').length") or 0, 300, 2)
        time.sleep(15)
        mem = memory("brief")
        RESULTS["memory"] = {"bea": mem, "maya": memory("maya")}
        check("peanut" not in mem.lower(), "Nothing from an off-record chat is remembered")
        check("lena" not in mem.lower() and "oslo" not in mem.lower(), "Nothing from an incognito chat is remembered")
        rpc(p, "quit")
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass  # killed below; the results still get written
    finally:
        if p.poll() is None:
            p.kill()
    RESULTS["minutes"] = round((time.monotonic() - started) / 60, 1)
    (RUN / "result.json").write_text(json.dumps({"agent": AGENT, "model": MODEL, "effort": EFFORT, "failed": FAILED, "results": RESULTS}, indent=2), encoding="utf-8")
    (RUN / "transcripts.md").write_text("\n".join(OUT), encoding="utf-8")
    print("->", RUN)
    print(f"{'FAILED ' + str(len(FAILED)) if FAILED else 'PASSED'}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
