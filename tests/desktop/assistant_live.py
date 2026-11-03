"""Assistant Ruth, through a real signed-in agent app (uses that plan; Claude Haiku at low effort by default), with
Maya (Research) and Jonah (Sales) on the team: ten everyday requests she should handle herself (nine or more with no
handoff passes), then one request with a research part and a sales part she should route. Pages can be read, nothing
is approved or sent, and questions are skipped. Run it by hand only.

Run: python tests/desktop/assistant_live.py artifacts/Still-QA/Still.exe [claude] [model] [effort]
Writes artifacts/assistant-live-<id>/result.json and transcripts.md.
"""
import json
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import launch, rpc, send, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXE = Path(sys.argv[1]).resolve()
AGENT = sys.argv[2] if len(sys.argv) > 2 else "claude"
MODEL = sys.argv[3] if len(sys.argv) > 3 else "haiku"
EFFORT = sys.argv[4] if len(sys.argv) > 4 else "low"
RUN = ROOT / "artifacts" / f"assistant-live-{uuid.uuid4().hex[:6]}"
PROFILE = RUN / "profile"
SIMPLE = ["What's a polite way to decline a meeting invite? Two sentences.",
          "What time is 3:30 pm in New York in London, on a normal day in March?",
          "Plan my afternoon: a 2 pm call, a report due at 5 and a 30-minute gym slot. Keep it short.",
          "Rewrite this to sound friendlier: \"Send me the report by Friday.\"",
          "What does EBITDA stand for? One line.",
          "Suggest a subject line for an email moving our Thursday call to Friday.",
          "Remind me every weekday at 9:00 to check my calendar.",
          "Look up what the Python 'walrus operator' is, in two lines with a source link.",
          "What's 18% of 2,450?",
          "Draft a two-line reminder to my team that timesheets are due today."]
ROUTE = ("I have a first call with Plausible Analytics (plausible.io) next week. I need a full prospect brief with a source for every claim (product, "
         "pricing, team, recent news and competitors), and a three-email outreach sequence to send before the call. Don't send anything.")
FAILED, RESULTS, OUT = [], {}, [f"# Stage 10 live, Assistant Ruth: {AGENT} {MODEL} {EFFORT}\n"]


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def crew(*ids):
    """Name, job and tone of Still's companions, read from crew.tsx so this never drifts from the app."""
    src = (ROOT / "still-ui" / "src" / "crew.tsx").read_text(encoding="utf-8")
    found = {i: (n, j, t) for i, n, j, t in re.findall(r'\{ id: "(\w+)", name: "(\w+)".*?job: "((?:[^"\\]|\\.)*)",\s*tone: "((?:[^"\\]|\\.)*)"', src, re.S)}
    return [{"Id": i, "Name": found[i][0], "Job": found[i][1], "Tone": found[i][2], "Crew": i, "Mode": "default"} for i in ids]


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def chat(cid):
    return next((c for c in chats() if c["Id"] == cid), {"Messages": []})


def handoffs(c):
    return [(m["Role"], m.get("To"), m.get("Status")) for m in c["Messages"] if m["Role"] in ("ask", "tell")]


def start(p, text):
    before = {c["Id"] for c in chats()}
    send(p, "new")
    time.sleep(1)
    send(p, "aiSend", text=text, home=True, companion="assistant")
    return until(lambda: next((c["Id"] for c in chats() if c["Id"] not in before and not c.get("From")), None), 30, .5)


def finish(p, ids, seconds):
    """Runs the chats to the end; a question is skipped (best judgment), and nothing is ever approved."""
    def done():
        now = [c for c in chats() if c["Id"] in ids or c.get("From") in ids]
        for c in now:
            if c.get("Running"):
                send(p, "aiAnswer", id=c["Id"], text="")
        return len([c for c in now if c["Id"] in ids]) == len(ids) and not any(c.get("Running") for c in now)
    return until(done, seconds, 5)


def record(key, cid):
    c = chat(cid)
    kids = [k for k in chats() if k.get("From") == cid]
    RESULTS[key] = {"chat": cid, "seconds": c.get("Worked", 0), "handoffs": handoffs(c), "messages": [{"role": m["Role"], "text": m["Text"]} for m in c["Messages"]],
                    "children": [{"companion": k["Companion"], "title": k["Title"], "messages": [{"role": m["Role"], "text": m["Text"]} for m in k["Messages"]]} for k in kids]}
    OUT.extend([f"## {key}", *[f"**{m['Role']}**: {m['Text']}" for m in c["Messages"]], *[f"> child {k['Companion']}: {k['Title']}" for k in kids], ""])


def main():
    PROFILE.mkdir(parents=True)
    allow = [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate")]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew("assistant", "research", "sales"), "AgentsEnabled": True,
        "AiHarness": AGENT, "Permissions": allow, "Width": 1400, "Height": 900}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    started = time.monotonic()
    try:
        send(p, "aiCheck")
        time.sleep(4)
        send(p, "aiAdvanced", on=True)
        send(p, "aiModel", harness=AGENT, model=MODEL, effort=EFFORT)

        # Ten everyday requests, all at once: she should handle them herself.
        ids = [start(p, t) for t in SIMPLE]
        check(all(ids), "Ten chats start")
        finish(p, [i for i in ids if i], 900)
        direct = 0
        for n, (cid, text) in enumerate(zip(ids, SIMPLE)):
            record(f"simple-{n + 1}", cid)
            c = chat(cid)
            answered = any(m["Role"] == "assistant" and m["Text"].strip() for m in c["Messages"])
            direct += answered and not handoffs(c)
            print(f"  {n + 1}. {'direct' if not handoffs(c) else 'handed off ' + str(handoffs(c))}{'' if answered else ' (no answer)'}: {text}", flush=True)
        check(direct >= 9, f"Nine or more of ten everyday requests answered with no handoff ({direct})")
        first = next((json.loads(l)["prompt"] for l in (PROFILE / "qa-prompts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()), "") if (PROFILE / "qa-prompts.jsonl").exists() else ""
        check("You're the user's personal assistant in Still" in first, "Her prompt carries her brief")

        # One request with a research part and a sales part: she routes it and returns one answer.
        tops = len([c for c in chats() if not c.get("From")])
        route = start(p, ROUTE)
        finish(p, [route], 900)
        record("route", route)
        c = chat(route)
        to = sorted({h[1] for h in handoffs(c)})
        answer = "\n\n".join(m["Text"] for m in c["Messages"] if m["Role"] == "assistant")
        check(bool(to) and set(to) <= {"research", "sales"}, f"She hands parts to her team, and only her team ({handoffs(c)})")
        check(len([k for k in chats() if not k.get("From")]) == tops + 1, "History gains one chat for the request")
        check("http" in answer and re.search(r"(?i)subject|hi |hello|dear", answer), f"One answer with sources and the outreach draft ({len(answer)} chars)")
        check(not any(m["Role"] == "tool" and re.search(r"(?i)\bsent\b", m["Text"]) for m in c["Messages"]), "Nothing was sent")
        rpc(p, "quit")
        p.wait(timeout=15)
    finally:
        if p.poll() is None:
            p.kill()
        (RUN / "result.json").write_text(json.dumps({"agent": AGENT, "model": MODEL, "effort": EFFORT, "minutes": round((time.monotonic() - started) / 60, 1), "failed": FAILED,
                                                     "results": RESULTS}, indent=2), encoding="utf-8")
        (RUN / "transcripts.md").write_text("\n".join(OUT), encoding="utf-8")
        print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'ALL PASSED'} -> {RUN}")


main()
