"""Companion evals: the same small tasks before and after a change, through a real signed-in agent app (uses that
plan). One task of each kind: research, a browser action, writing, remembering a preference, a vague follow-up and a
tool failure, each with a companion hired from the crew (so it has its role's skills). A local test site serves the
pages. Nothing is approved and questions are skipped (best judgment). Run it by hand only.

Run: python tests/desktop/evals.py artifacts/Still-QA/Still.exe <label> [claude] [model] [effort]
Writes artifacts/evals-<label>-<id>/result.json and transcripts.md. Score them with the rubric in docs/2.10-progress.md.
"""
import http.server
import json
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import launch, rpc, send, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXE = Path(sys.argv[1]).resolve()
LABEL = sys.argv[2] if len(sys.argv) > 2 else "run"
AGENT = sys.argv[3] if len(sys.argv) > 3 else "claude"
MODEL = sys.argv[4] if len(sys.argv) > 4 else "haiku"
EFFORT = sys.argv[5] if len(sys.argv) > 5 else "low"
RUN = ROOT / "artifacts" / f"evals-{LABEL}-{uuid.uuid4().hex[:6]}"
PROFILE = RUN / "profile"
HITS = []


class Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        HITS.append(self.path)
        status, body = 200, ""
        if url.path == "/shop":
            body = ("<title>Lamp shop</title><h1>Desk lamps</h1><ul>"
                    "<li>Red lamp: $29 <a href='/wishlist?add=red'><button>Save to wishlist</button></a></li>"
                    "<li>Blue lamp: $39 <a href='/wishlist?add=blue'><button>Save to wishlist</button></a></li>"
                    "<li>Green lamp: $45 <a href='/wishlist?add=green'><button>Save to wishlist</button></a></li></ul>")
        elif url.path == "/wishlist":
            item = urllib.parse.parse_qs(url.query).get("add", ["nothing"])[0]
            body = f"<title>Wishlist</title><h1>Saved the {item} lamp to your wishlist</h1>"
        elif url.path == "/report":
            status, body = 500, "<title>500 Internal Server Error</title><h1>Internal Server Error</h1><p>The server couldn't complete the request.</p>"
        else:
            status, body = 404, "<title>Not found</title><h1>Not found</h1>"
        data = ("<!doctype html><meta charset=utf-8>" + body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
SITE = f"http://127.0.0.1:{SERVER.server_port}"
SAY = " Don't ask me anything: assume what you need and say what you assumed."

# id: (kind, companion role, first message, the skill that fits or "" for none)
TASKS = {
    "research": ("research", "research", "Compare Plausible and Umami for a 3-person team's web analytics: license, self-hosting needs and the cheapest cloud plan's price. "
                 "A short table, then your pick, with a source for each claim.", "option-compare"),
    "browser": ("browser action", "growth", f"Open {SITE}/shop, tell me what the blue lamp costs, and save it to my wishlist there.", ""),
    "writing": ("writing", "marketing", "Our bakery's sourdough subscription starts 1 November: four loaves a month for $36, pickup or delivery within 5 km. "
                "Write an X post under 280 characters and a short Instagram caption.", "post-set"),
    "memory": ("remembering a preference", "planner", "For everything from now on: keep my plans to five lines or fewer and use 24-hour times. Please remember that.", ""),
    "followup": ("vague follow-up", "sales", "Draft a follow-up email after today's demo with Priya, the ops lead at Acme. She liked the reporting but worried about setup time.", "follow-up"),
    "failure": ("tool failure", "engineer", f"Summarize the report at {SITE}/report for me.", ""),
}
LATER = {  # the second turn: memory in a new chat with the same companion, the follow-up in the same chat
    "memory2": ("planner", "Plan my tomorrow: gym first thing, two hours on the Q3 report, and the dentist at 3 in the afternoon.", "plan-tomorrow"),
    "followup2": ("sales", "shorter, and warmer", "follow-up"),
}


def premades():
    src = (ROOT / "still-ui" / "src" / "crew.tsx").read_text(encoding="utf-8")
    found = re.findall(r'\{ id: "(\w+)", name: "(\w+)".*?job: "((?:[^"\\]|\\.)*)",\s*tone: "((?:[^"\\]|\\.)*)"', src, re.S)
    return [{"Id": i, "Name": n, "Job": j, "Tone": t, "Crew": i, "Mode": "default"} for i, n, j, t in found]


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def prompts():
    file = PROFILE / "qa-prompts.jsonl"
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines() if l.strip()] if file.exists() else []


def settle(process, seconds=900):
    def done():
        now = chats()
        for x in now:
            if x.get("Running"):
                send(process, "aiAnswer", id=x["Id"], text="")  # a question is skipped: best judgment
        return now and not any(x.get("Running") for x in now)
    return until(done, seconds, 5)


def start(process, companion, text):
    before = {x["Id"] for x in chats()}
    send(process, "new")
    time.sleep(1)
    send(process, "aiSend", text=text + SAY, home=True, companion=companion)
    return until(lambda: next((x["Id"] for x in chats() if x["Id"] not in before and x["Companion"] == companion), None), 30, .5)


def main():
    PROFILE.mkdir(parents=True)
    allow = [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate", "interact")]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": premades(), "AgentsEnabled": True, "AiHarness": AGENT,
        "Permissions": allow, "Width": 1400, "Height": 900}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    ids, started = {}, time.monotonic()
    try:
        send(process, "aiCheck")
        time.sleep(4)  # the model list loads in the background
        send(process, "aiAdvanced", on=True)
        send(process, "aiModel", harness=AGENT, model=MODEL, effort=EFFORT)
        for key, (_, role, text, _) in TASKS.items():
            ids[key] = start(process, role, text)
        settle(process)
        ids["memory2"] = start(process, LATER["memory2"][0], LATER["memory2"][1])
        settle(process)
        send(process, "chatOpen", id=ids["followup"])
        until(lambda: any(t.get("ChatId") == ids["followup"] for t in rpc(process)["tabs"]), 10)
        time.sleep(1)
        send(process, "aiSend", text=LATER["followup2"][1])
        ids["followup2"] = ids["followup"]
        until(lambda: next((x for x in chats() if x["Id"] == ids["followup"]), {}).get("Running"), 30, .5)
        settle(process)
        rpc(process, "quit")
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass  # killed below; the results still get written
    finally:
        if process.poll() is None:
            process.kill()
    by_id = {x["Id"]: x for x in chats()}
    sent = prompts()
    results, out = {}, [f"# Evals: {LABEL} ({AGENT} {MODEL} {EFFORT})\n"]
    for key, chat_id in ids.items():
        chat = by_id.get(chat_id or "", {"Messages": [], "Worked": 0})
        first = next((p["prompt"] for p in sent if p["chat"] == chat_id), "")
        kind, fits = (TASKS[key][0], TASKS[key][3]) if key in TASKS else (TASKS[key[:-1]][0] + " (second turn)", LATER[key][2])
        msgs = chat["Messages"]
        if key == "followup":  # the first turn only: the second is reported as followup2
            cut = next((i for i, m in enumerate(msgs) if m["Role"] == "user" and m["Text"].startswith("shorter")), len(msgs))
            msgs = msgs[:cut]
        elif key == "followup2":
            msgs = chat["Messages"][next((i for i, m in enumerate(chat["Messages"]) if m["Role"] == "user" and m["Text"].startswith("shorter")), 0):]
        steps = [m["Text"] for m in msgs if m["Role"] == "tool"]
        answer = "\n\n".join(m["Text"] for m in msgs if m["Role"] == "assistant")
        r = results[key] = {"kind": kind, "companion": chat.get("Companion"), "fits": fits, "promptChars": len(first), "skillBodies": first.count("[Skill \""),
                            "steps": steps, "skills": [s for s in steps if "skill" in s.lower()], "answer": answer, "seconds": chat.get("Worked", 0)}
        out += [f"## {key}: {kind} ({r['companion']})", f"First-turn prompt: {r['promptChars']} characters, {r['skillBodies']} skill bodies. Skill that fits: {fits or 'none'}.",
                "Steps: " + ("; ".join(steps) or "none"), "", answer or "(no reply)", ""]
    results["site"] = {"wishlist": [h for h in HITS if h.startswith("/wishlist")], "report": [h for h in HITS if h.startswith("/report")], "shop": [h for h in HITS if h.startswith("/shop")]}
    (RUN / "result.json").write_text(json.dumps({"label": LABEL, "agent": AGENT, "model": MODEL, "effort": EFFORT, "minutes": round((time.monotonic() - started) / 60, 1), "results": results}, indent=2), encoding="utf-8")
    (RUN / "transcripts.md").write_text("\n".join(out), encoding="utf-8")
    for key, r in results.items():
        if key != "site":
            print(f"{key}: {r['promptChars']} chars, {r['skillBodies']} skill bodies, skills {r['skills']}, {len(r['steps'])} steps, {r['seconds']}s, {len(r['answer'])} chars reply")
    print("site:", results["site"])
    print("->", RUN)


main()
