"""Still's companions got people's names (Jonah, Talia, Nora, Leo, Ivan, Maya) and the fixer left. A profile from before
moves over on start: each old role becomes its new one, with the new name unless the user renamed it, the job and
personality Still gave it (keeping what the user added after "For me:"), and the fixer's chats and memory go to the
planner. Without a planner, the fixer becomes it.

Run: python tests/desktop/renames.py artifacts/Still-QA/Still.exe
"""
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, launch, rpc, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("renames-" + uuid.uuid4().hex[:8])
FAILED = []
# What the library gave Zest and Bloom before the renames.
ZEST_JOB = ("A deal closer for the user's sales. Learns what the user sells and to whom, researches leads and companies from public information, preps a "
            "one-page brief before each call, drafts outreach and follow-ups in the user's voice, and keeps a simple pipeline table with a next step and a "
            "date for every deal. Never sends, books or posts anything without asking first, and never makes up a number.")
BLOOM_JOB = ("A scout for the user's hiring. Turns a role into a clear job post and a fair scorecard, finds candidates from public profiles and portfolios, "
             "ranks them against the scorecard using only what they shared publicly, drafts personal outreach, and keeps a shortlist up to date. Leaves every "
             "decision to the user, points out bias when it creeps in, and never sends anything without asking.")
BLOOM_TONE = "Warm and perceptive. Says in one line why someone fits, and is honest about the gaps."
FIXER_LOOK = '{"color":"#86d0c8","shape":"squat","prop":"headset","accessory":""}'


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def seed(profile, companions, chats=(), memory=None):
    (profile / "ai").mkdir(parents=True)
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": companions, "NamesChecked": True},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    (profile / "ai" / "chats.json").write_text(json.dumps(list(chats)))
    for who, facts in (memory or {}).items():
        (profile / "companions" / who).mkdir(parents=True)
        (profile / "companions" / who / "memory.json").write_text(json.dumps([{"Id": f"{who}{i}", "Text": t, "Kind": "fact", "Chat": "", "Key": k} for i, (t, k) in enumerate(facts)]))


def start(profile):
    p = launch(EXE, profile)
    rpc(p, "quit")
    until(lambda: p.poll() is not None, 20)
    return {c["Id"]: c for c in json.loads((profile / "state.json").read_text())["Preferences"]["Companions"]}


def main():
    team = RUN / "team"
    seed(team, [
        {"Id": "z1", "Name": "Zest", "Crew": "closer", "Job": ZEST_JOB + "\n\nFor me: Focus on bakeries.", "Tone": "Bold and upbeat. Talks in next steps and dates, and gets straight to what moves the deal."},
        {"Id": "b1", "Name": "Blossom", "Crew": "scout", "Job": BLOOM_JOB, "Tone": BLOOM_TONE},
        {"Id": "m1", "Name": "Mallow", "Crew": "fixer", "Look": FIXER_LOOK, "Job": "Support.", "Routines": [{"Id": "fixer", "Text": "Sort my queue.", "Time": "09:00", "Days": [1], "On": True}]},
        {"Id": "n1", "Name": "Noon", "Crew": "chief", "Job": "My own words."}],
        chats=[{"Id": "c1", "Title": "Refund", "Companion": "m1", "Messages": [{"Role": "user", "Text": "Help with a refund"}, {"Role": "assistant", "Text": "On it."}]},
               {"Id": "c2", "Title": "Team", "Companion": "z1", "Messages": [{"Role": "ask", "Text": "Can you check?", "Who": "z1", "To": "m1", "Status": "replied"}]}],
        memory={"m1": [("Ships from Lisbon.", ""), ("Likes to be called Sam.", "name")], "n1": [("Likes to be called Sammy.", "name"), ("Has two cats.", "")]})
    got = start(team)
    check(sorted(got) == ["b1", "n1", "z1"], f"The fixer is gone; the other three stay ({sorted(got)})")
    z, b, n = got.get("z1", {}), got.get("b1", {}), got.get("n1", {})
    check(z.get("Name") == "Jonah" and z.get("Crew") == "sales", f"Zest is now Jonah, Sales ({z.get('Name')}, {z.get('Crew')})")
    check(z.get("Job", "").startswith("Sales for the user.") and z.get("Job", "").endswith("\n\nFor me: Focus on bakeries."), "with today's job, keeping what the user added")
    check(b.get("Name") == "Blossom" and b.get("Crew") == "growth", "A name the user gave stays; the scout is now Growth")
    check(b.get("Job", "").startswith("Growth for the user's product.") and b.get("Tone") == "Curious and upbeat. Talks in numbers and bets, and celebrates small wins.",
          "and a scout's hiring job and personality become Growth's")
    check(n.get("Name") == "Nora" and n.get("Crew") == "planner" and n.get("Job") == "My own words.", "Noon is now Nora, Planner, and a job the user wrote stays")
    chats = {c["Id"]: c for c in json.loads((team / "ai" / "chats.json").read_text())}
    check(chats["c1"]["Companion"] == "n1" and chats["c2"]["Messages"][0].get("To") == "n1", "The fixer's chats and the exchanges with it go to Nora")
    facts = [f["Text"] for f in json.loads((team / "companions" / "n1" / "memory.json").read_text())]
    check("Ships from Lisbon." in facts and "Has two cats." in facts and "Likes to be called Sammy." in facts and "Likes to be called Sam." not in facts,
          f"Nora remembers what the fixer did, and keeps her own when both had one ({facts})")
    check(not (team / "companions" / "m1").exists(), "The fixer's folder is gone")

    alone = RUN / "alone"
    seed(alone, [{"Id": "m1", "Name": "Mallow", "Crew": "fixer", "Look": FIXER_LOOK, "Job": "Support.", "Routines": [{"Id": "fixer", "Text": "Sort my queue.", "Time": "09:00", "Days": [1], "On": True}]}],
         memory={"m1": [("Ships from Lisbon.", "")]})
    m = start(alone).get("m1", {})
    check(m.get("Name") == "Nora" and m.get("Crew") == "planner" and not m.get("Look") and not m.get("Routines"),
          f"Without a planner the fixer becomes Nora, with Nora's look and none of its support routine ({m.get('Name')}, {m.get('Crew')}, {m.get('Look')!r})")
    check((alone / "companions" / "m1" / "memory.json").exists(), "and keeps its memory")

    again = start(team)
    check(sorted(again) == ["b1", "n1", "z1"] and again["z1"]["Name"] == "Jonah", "Starting again changes nothing")
    print(f"\n{len(FAILED)} failed" if FAILED else "\nAll renames checks passed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
