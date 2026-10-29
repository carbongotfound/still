"""Still's seven companions at real work: one task in each one's field, all at once, through a real signed-in agent app
(uses that plan). Each is hired from the crew, so its prompt carries its role setup (still/Assets/roles). Rivet gets a
working folder to build in. Questions are skipped (best judgment); nothing is ever approved, so nothing can be sent.
Run it by hand only.

Run: python tests/desktop/roles_live.py artifacts/Still-QA/Still.exe [claude] [model] [crew id ...]  (ids: only those)
"""
import json
from pathlib import Path
import re
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import launch, rpc, send, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXE = Path(sys.argv[1]).resolve()
AGENT = sys.argv[2] if len(sys.argv) > 2 else "claude"
MODEL = sys.argv[3] if len(sys.argv) > 3 else ""
ONLY = sys.argv[4:]
RUN = ROOT / "artifacts" / ("roles-live-" + AGENT + "-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
WORK = RUN / "rivet-work"
SAY = " Don't ask me anything: assume what you need and say what you assumed."
TASKS = {
    "closer": ("Prep me for a sales call tomorrow with Plausible Analytics (plausible.io). I sell a customer-feedback widget for small SaaS teams. Make the one-page brief: what they do, "
               "who they sell to, anything recent, which of their pains my product could solve, three questions to ask, and a follow-up email to send after the call.",
               lambda a, c: "http" in a and "draft" in a.lower()),
    "scout": ("We're a 10-person startup hiring our first junior frontend developer (React, remote, Europe). Write the job post and a fair scorecard with five weighted criteria, "
              "and save the scorecard as a CSV file.", lambda a, c: any(f.suffix == ".csv" for f in c["files"])),
    "chief": ("Plan my tomorrow. Fixed: a design review 10:00-11:00 and an investor call with a seed fund 14:00-14:30. To do: finish the Q3 report (about three hours), reply to 12 emails, "
              "prep the investor call and take a 30-minute walk. I work 9:00-18:00. Give me the schedule, most important first, and a two-minute brief for the investor call.",
              lambda a, c: "14:00" in a and "10:00" in a),
    "marketer": ("Our neighborhood bakery is launching a sourdough subscription: four loaves a month for $36, pickup or delivery within 5 km, starting 1 November. Turn it into a post "
                 "for X (under 280 characters), a LinkedIn post, an Instagram caption and a short newsletter blurb.", lambda a, c: a.lower().count("draft") >= 3 or a.count("```") >= 6),
    "fixer": ("Four tickets came in overnight. Sort them and draft the replies.\n1. Maya: 'I was charged twice for my October invoice, please fix ASAP.'\n"
              "2. Tom: 'How do I change my account email?'\n3. Priya: 'Export to CSV gives an empty file since yesterday's update. Our weekly report is due today.'\n"
              "4. Lee: 'Export is broken for me too, the file has headers but no rows.'", lambda a, c: "urgent" in a.lower() and "draft" in a.lower()),
    "builder": ("Build a tip calculator as one HTML file in your working folder: bill amount, tip percent (10, 15, 20 or custom) and number of people, showing the tip and the total per "
                "person, rounded to cents. Open it in a tab and test it: three normal cases and one edge case (0 people or an empty bill). Report what you tested and what happened.",
                lambda a, c: any(WORK.glob("*.html")) and any(s.startswith("Opened file:") for s in c["steps"]) and not any("http" in s for s in c["steps"] if s.startswith(("Opened", "Went to")))),
    "researcher": ("Which is the better pick for a small team's web analytics today: Plausible, Umami or Matomo? Compare license, self-hosting needs, cookies and privacy, and the "
                   "price of the cheapest cloud plan, in one table, then give your pick. Cite a source for every claim.", lambda a, c: len(set(re.findall(r"https?://[^\s)\]>]+", a))) >= 4),
}


def premades():
    """Name, job and tone of each of Still's seven, read from crew.tsx so this never drifts from the app."""
    src = (ROOT / "still-ui" / "src" / "crew.tsx").read_text(encoding="utf-8")
    found = re.findall(r'\{ id: "(\w+)", name: "(\w+)".*?job: "((?:[^"\\]|\\.)*)",\s*tone: "((?:[^"\\]|\\.)*)"', src, re.S)
    return [{"Id": i, "Name": n, "Job": j, "Tone": t, "Crew": i, "Mode": "default", "Folder": str(WORK) if i == "builder" else ""} for i, n, j, t in found]


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def main():
    WORK.mkdir(parents=True)
    PROFILE.mkdir()
    crew = premades()
    assert [c["Id"] for c in crew] == list(TASKS), [c["Id"] for c in crew]
    crew = [c for c in crew if not ONLY or c["Id"] in ONLY]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": AGENT,
        "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}], "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    results, started = {}, time.monotonic()
    try:
        send(process, "aiCheck")
        if MODEL:
            time.sleep(3)  # the model list loads in the background
            send(process, "aiAdvanced", on=True)
            send(process, "aiModel", harness=AGENT, model=MODEL)
        for c in crew:  # each in its own new tab, all running at once
            send(process, "new")
            time.sleep(1)
            send(process, "aiSend", text=TASKS[c["Id"]][0] + SAY, home=True, companion=c["Id"])
            until(lambda: any(x["Companion"] == c["Id"] for x in chats()), 20, .5)

        def done():
            now = {x["Companion"]: x for x in chats()}
            for x in now.values():
                if x["Running"]:
                    send(process, "aiAnswer", id=x["Id"], text="")  # a question is skipped: best judgment
            return len(now) == len(crew) and not any(x["Running"] for x in now.values())
        until(done, 1500, 10)
        for c in crew:
            chat = next((x for x in chats() if x["Companion"] == c["Id"]), {"Messages": [], "Worked": 0, "Id": "-"})
            replies = [m["Text"] for m in chat["Messages"] if m["Role"] == "assistant"]
            files = [f for f in (PROFILE / "library" / chat["Id"]).glob("*")] if (PROFILE / "library" / chat["Id"]).exists() else []
            got = {"name": c["Name"], "task": TASKS[c["Id"]][0], "answer": "\n\n".join(replies), "seconds": chat["Worked"], "running": chat.get("Running"),
                   "steps": [m["Text"] for m in chat["Messages"] if m["Role"] == "tool"], "files": files}
            got["passed"] = bool(replies) and TASKS[c["Id"]][1](got["answer"], got)
            got["files"] = [f.name for f in files] + ["rivet-work/" + f.name for f in WORK.glob("*")] * (c["Id"] == "builder")
            results[c["Id"]] = got
        rpc(process, "quit")
        process.wait(timeout=15)
    finally:
        if process.poll() is None:
            process.kill()
        (RUN / "result.json").write_text(json.dumps({"agent": AGENT, "model": MODEL, "minutes": round((time.monotonic() - started) / 60, 1), "results": results}, indent=2))
        for k, r in results.items():
            print(("PASS " if r["passed"] else "FAIL ") + f"{r['name']} ({r['seconds']}s, {len(r['steps'])} steps, files {r['files']})")
        print("->", RUN)


main()
