"""Companion memory 2.10: provenance, versions, corrections, recall that finds the right things and nothing else, real
forgetting, chat summaries, versioned knowledge files, change notes for open chats, every Settings control checked on
disk, failed writes, a corrupt file, migration from before 2.10, and Setup run exactly once. No AI plan is used: a fake
agent app (a manifest in Still's agents folder) connects to Still's MCP server and runs the tool calls on the last line
of each prompt ("TOOLS64: " and base64 JSON, so the user's message never holds the words it saves), emitting each call
and its result like Claude Code does. It answers a chat-summary prompt with BIN/summary.txt, and a last line with
FAILNOW fails the run. NOSESSION: it reports no session, so the next turn starts a new one.

Run: python tests/desktop/recall.py artifacts/Still-QA/Still.exe   (Mac: the bundle's binary)
Out: artifacts/recall-*/ (memory-settings.png, result.json)
"""
import base64
import json
import os
from pathlib import Path
import stat
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("recall-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


FAKE = textwrap.dedent(r'''
    import base64, json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    last = prompt.strip().splitlines()[-1]
    summary = "Summarize this chat between the user and you" in prompt
    with open(os.path.join(here, "summaries.jsonl" if summary else "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt, "last": last}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
    if summary:
        file = os.path.join(here, "summary.txt")
        say({"type": "system", "subtype": "init", "session_id": "sum-%d" % time.time_ns()})
        say({"type": "assistant", "message": {"content": [{"type": "text", "text": open(file, encoding="utf-8").read() if os.path.exists(file) else '{"goal":[{"text":"Talk things through","msgs":[1]}]}'}]}})
        sys.exit(0)
    if "NOSESSION" not in last: say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    if "FAILNOW" in last:
        print("failed on purpose", file=sys.stderr, flush=True); sys.exit(3)
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
    out = []
    if "TOOLS64: " in last:
        for i, c in enumerate(json.loads(base64.b64decode(last.split("TOOLS64: ", 1)[1]).decode("utf-8"))):
            a = c.get("arguments", {})
            if a.get("version") == "READ":
                r = request("tools/call", {"name": "read_knowledge", "arguments": {"file": a.get("file", "")}})["result"]
                try: a["version"] = json.loads(r["content"][0]["text"]).get("version", "")
                except ValueError: a["version"] = ""
            say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tu%d" % i, "name": "mcp__still__" + c["name"], "input": a}]}})
            r = request("tools/call", {"name": c["name"], "arguments": a})["result"]
            say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu%d" % i, "is_error": bool(r.get("isError"))}]}})
            out.append({"name": c["name"], "error": bool(r.get("isError")), "text": r["content"][0].get("text", "")})
    with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"last": last, "results": out}) + "\n")
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay, done."}]}})
    still.stdin.close()
''')


def tools(*calls, say=""):
    """The user's message: words they say (optional), then the calls for the fake."""
    return (say + " " if say else "") + "TOOLS64: " + base64.b64encode(json.dumps([{"name": n, "arguments": a} for n, a in calls]).encode()).decode()


def read(rel, default=None):
    try:
        return json.loads((PROFILE / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def mem(c, everything=False):
    return [f for f in read(f"companions/{c}/memory.json", []) if everything or f.get("Status", "active") == "active"]


def summaries(c):
    return (read(f"companions/{c}/summaries.json", {}) or {}).get("List", [])


def chats():
    return read("ai/chats.json", [])


def companion(c):
    return next((x for x in (read("state.json", {}) or {}).get("Preferences", {}).get("Companions", []) if x["Id"] == c), {})


def lines(name):
    file = BIN / name
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


LAST = {"prompt": ""}


def prompt():
    """The prompt of the last message chat() sent."""
    return LAST["prompt"]


def memory_section(p):
    """What reached the prompt from memory: the lines under the header, up to the blank line."""
    head = "What you remember about the user from before"
    if head not in p:
        return ""
    return p.split(head, 1)[1].split("\n", 1)[1].split("\n\n", 1)[0]


def chat(process, text, who="maya", new=True, wait=40, **extra):
    """Sends a message (a new chat, or the open one) and waits for the run to end. Returns the chat and the calls' results."""
    asked, done = len(lines("prompts.jsonl")), len(lines("results.jsonl"))
    before = {c["Id"] for c in chats()}
    if new:
        send(process, "new")
        until(lambda: js(process, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
        js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        send(process, "aiSend", text=text, home=True, companion=who, **extra)
    else:
        send(process, "aiSend", text=text, **extra)
    mine = lambda: next((p for p in lines("prompts.jsonl")[asked:] if p["last"].strip() == text.strip()), None)
    LAST["prompt"] = (until(mine, wait) or {}).get("prompt", "")
    def ended():
        for c in chats():
            if (c["Id"] not in before or not new) and any(m["Role"] == "user" and m["Text"] == text for m in c["Messages"]) and not c.get("Running"):
                return c
    found = until(ended, wait) or {}
    until(lambda: len(lines("results.jsonl")) > done or "FAILNOW" in text, 5)
    time.sleep(.3)
    return found, ((lines("results.jsonl")[done:] or [{}])[-1]).get("results", [])


def toast(process, words, seconds=8):
    return until(lambda: words in (js(process, "document.body.innerText") or ""), seconds)


# 50 things Talia knows: 10 the questions below need, two profile items that always come, and 38 about other things.
NEEDED = [("Can you call my mother this weekend?", "Mom lives in Lisbon and likes calls on Sundays"),
          ("Plan a vacation for August", "Takes a trip to Japan every spring"),
          ("Find a gym near the office", "Climbs at a bouldering gym three times a week"),
          ("What should I get my sister?", "Sister Lina loves pottery and green tea"),
          ("Is this snack safe given my allergy?", "Allergic to peanuts and cashews"),
          ("Draft a note to my boss", "Boss Priya runs the design studio"),
          ("Set a budget for the kitchen renovation", "Kitchen renovation budget is 12000 euros"),
          ("Remind me about the dentist", "Dentist appointment every six months at Smile Clinic"),
          ("Which vehicle should I rent?", "Drives an electric car and needs charging spots"),
          ("Help with my daughter's homework", "Daughter Mia is in fifth grade")]
FILLER = ["Plays the cello in a community orchestra", "Reads science fiction before bed", "Grows basil on the balcony", "Supports a football club from Porto",
          "Collects vintage postcards", "Runs a small newsletter about urban sketching", "Learning Japanese with flashcards", "Keeps a sourdough starter named Bubbles",
          "Prefers trains over buses for commuting", "Watches documentaries about volcanoes", "Uses a mechanical keyboard with brown switches", "Volunteers at an animal shelter monthly",
          "Owns a grey cat called Pixel", "Likes jazz records from the sixties", "Paints watercolor landscapes", "Plays chess online most evenings",
          "Bikes along the river on weekends", "Writes poetry in a paper notebook", "Fixes old radios as a hobby", "Follows formula one races",
          "Brews kombucha at home", "Bakes croissants for friends", "Studies astronomy with a small telescope", "Keeps succulents on the windowsill",
          "Does crossword puzzles with a pen", "Knits scarves in winter", "Plays board games on Friday nights", "Swims laps at the public pool",
          "Listens to history podcasts", "Restores wooden furniture", "Speaks Portuguese and Spanish", "Rides a vintage scooter",
          "Practices calligraphy", "Builds model trains", "Hikes mountain trails in autumn", "Photographs street art", "Plays tennis badly", "Sings in a choir"]
UNRELATED = ["What is the capital of Peru?", "Convert 30 inches into centimeters", "Explain how photosynthesis works"]


def talia_fixture():
    now = "2026-10-01T10:00:00Z"
    facts = [{"Id": "p0000001", "Text": "Goes by Sam", "Kind": "profile", "Key": "name"}, {"Id": "p0000002", "Text": "Wants short replies without bullet lists", "Kind": "profile"}]
    facts += [{"Id": f"n{i:07d}", "Text": t, "Kind": "fact"} for i, (_, t) in enumerate(NEEDED)] + [{"Id": f"f{i:07d}", "Text": t, "Kind": "fact"} for i, t in enumerate(FILLER)]
    return [{**f, "At": now, "Created": now, "Chat": "", "Msg": -1, "Guessed": False, "Source": "settings", "Subject": "", "Status": "active", "Supersedes": "", "SupersededBy": "", "V": 2, "Key": f.get("Key", "")} for f in facts]


def write(rel, text):
    p = PROFILE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    # Before 2.10: Leo's memory has a past chat and a guessed fact; Nora's file is broken, with a good backup.
    old = "2026-09-01T10:00:00Z"
    write("companions/leo/memory.json", json.dumps([{"Id": "a1a1a1a1", "Text": "Likes window seats", "Kind": "preference", "At": old, "Chat": "", "Key": "", "Guessed": False},
        {"Id": "b2b2b2b2", "Text": "Booked a Lisbon trip: the hotel is sorted", "Kind": "chat", "At": old, "Chat": "abc", "Key": "chat:abc", "Guessed": False},
        {"Id": "c3c3c3c3", "Text": "Works at a bakery", "Kind": "fact", "At": old, "Chat": "old1", "Key": "", "Guessed": True}]))
    write("companions/nora/memory.json", "{ this isn't json")
    write("companions/nora/memory.json.bak", json.dumps([{"Id": "d4d4d4d4", "Text": "Reads the footnotes first", "Kind": "preference", "At": old, "Chat": "", "Key": "", "Guessed": False, "V": 2, "Source": "settings", "Status": "active"}]))
    write("companions/talia/memory.json", json.dumps(talia_fixture()))
    hhmm = time.strftime("%H:%M")
    joined = "## How you work\nCheck two sources.\n\n## When you join the team\nSay hello and ask three questions.\n\n## Standards\nCite every source."
    team = [{**c, "Crew": "research", "Instructions": joined} if c["Id"] == "maya" else {**c, "Greet": True, "Routines": [{"Id": "r1", "Text": "Morning check NOSESSION", "Time": hhmm, "Days": list(range(7)), "On": True}]} if c["Id"] == "jonah" else c for c in CREW]
    team += [{"Id": "leo", "Name": "Leo", "Job": "Travel"}, {"Id": "talia", "Name": "Talia", "Job": "Helper", "Greet": False}, {"Id": "ivan", "Name": "Ivan", "Job": "Writer", "Greet": True}]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": team, "AgentsEnabled": True, "AiHarness": "fake",
        "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}]}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "STILL_QA_SUMMARIES": "2"}
    process = launch(EXE, PROFILE, env)
    try:
        until(lambda: js(process, "!!document.body.innerText.length"), 20)

        # Migration and a corrupt file.
        leo = until(lambda: (m := read("companions/leo/memory.json", [])) and all(f.get("V") == 2 for f in m) and m, 10) or []
        check(leo and not any(f["Kind"] == "chat" for f in leo), "Migration: an old past-chat line leaves the memory items")
        legacy = next((s for s in summaries("leo") if s["Chat"] == "abc"), {})
        check(legacy.get("Legacy") and "Lisbon" in legacy.get("Text", ""), "and becomes a legacy chat summary, marked unchecked")
        seats = next((f for f in leo if f["Text"] == "Likes window seats"), {})
        bakery = next((f for f in leo if f["Text"] == "Works at a bakery"), {})
        check(seats.get("Source") == "settings" and not seats.get("Guessed") and bakery.get("Source") == "inferred" and bakery.get("Guessed") and bakery.get("Status") == "active",
              "A user-added item becomes confirmed, a guessed one stays inferred")
        kept = list((PROFILE / "companions" / "nora").glob("memory.corrupt-*.json"))
        check(kept and kept[0].read_text(encoding="utf-8") == "{ this isn't json", "A corrupt memory file is moved aside as memory.corrupt-<time>.json, untouched")
        check(toast(process, "memory file couldn't be read"), "and the user is told")
        send(process, "memoryAdd", companion="nora", text="Likes tables more than charts")
        nora = until(lambda: len(mem("nora")) == 2 and mem("nora"), 5) or []
        check(any(f["Text"] == "Reads the footnotes first" for f in nora), "The backup is loaded, never replaced with an empty list")
        send(process, "memoryCapture", companion="maya", on=True)  # saves the companions
        ivan, jonah, talia = (until(lambda: companion(x).get("Setup"), 5) and companion(x) for x in ("ivan", "jonah", "talia"))
        check(ivan.get("Setup") == "pending" and jonah.get("Setup") == "pending" and talia.get("Setup") == "done" and "Greet" not in ivan and companion("maya").get("Setup") in ("done", ""),
              "Greet true becomes Setup pending, false or missing becomes done")

        # Remember with where it came from; recall and open_memory_source give the source.
        a, said = chat(process, tools(("remember", {"fact": "Prefers aisle seats on long flights", "kind": "preference"})))
        aisle = next((f for f in mem("maya") if f["Text"] == "Prefers aisle seats on long flights"), {})
        check(not said[0]["error"] and aisle.get("Chat") == a.get("Id") and aisle.get("Msg") == 0 and aisle.get("Source") == "chat" and aisle.get("V") == 2 and aisle.get("Created"),
              "remember keeps the chat and message it came from, as said by the user")
        check(not any(f["Kind"] == "chat" for f in mem("maya", True)), "A finished chat no longer becomes a memory item")
        _, said = chat(process, tools(("recall", {"query": "aisle seats"}), ("open_memory_source", {"id": aisle.get("Id", "")})))
        got = json.loads(said[0]["text"]) if said and not said[0]["error"] else {}
        hit = (got.get("memories") or [{}])[0]
        check(hit.get("id") == aisle.get("Id") and "said by the user in the chat" in hit.get("source", "") and "message 1" in hit.get("source", ""), "recall says where each item came from")
        src = json.loads(said[1]["text"]) if len(said) > 1 and not said[1]["error"] else {}
        check(any(m["n"] == 1 and m["who"] == "user" and "TOOLS64" in m["text"] for m in src.get("messages", [])), "open_memory_source returns the original message")
        _, said = chat(process, tools(("recall", {"query": "submarine volcano tax"})))
        check(said and "Nothing in memory matches" in said[0]["text"] and '"memories":[]' in said[0]["text"].replace(" ", ""), "Nothing above the threshold: recall says so")

        # The three corrections, near-duplicates, numbers and negation, a long fact.
        _, said = chat(process, tools(("remember", {"fact": "Uses Chrome as main browser", "slot": "browser"})))
        chrome = next((f for f in mem("maya") if "Chrome" in f["Text"]), {})
        _, said = chat(process, tools(("remember", {"fact": "Now uses Still as main browser, after Chrome", "slot": "browser"})))
        both = mem("maya", True)
        old_c = next((f for f in both if f["Id"] == chrome.get("Id")), {})
        new_c = next((f for f in both if f["Text"].startswith("Now uses Still")), {})
        check(old_c.get("Status") == "superseded" and old_c.get("SupersededBy") == new_c.get("Id") and new_c.get("Supersedes") == old_c.get("Id") and new_c.get("Status") == "active",
              "\"I used to use Chrome; now I use Still\": the Chrome item is superseded and kept as history")
        chat(process, "What do I use to browse?")
        check("Now uses Still" in prompt() and "Uses Chrome as main browser" not in prompt(), "and only the new one reaches the next prompt")
        chat(process, tools(("remember", {"fact": "Prefers short answers in chat", "kind": "preference"}), ("remember", {"fact": "Prefers detailed research reports", "kind": "preference"})))
        prefs = [f for f in mem("maya") if f["Text"] in ("Prefers short answers in chat", "Prefers detailed research reports")]
        check(len(prefs) == 2 and not any(f.get("Supersedes") for f in prefs), "\"Short answers, but detailed research reports\" are two preferences, neither replacing the other")
        chat(process, tools(("remember", {"fact": "Owns Project A", "subject": "Sarah", "kind": "person"}), ("remember", {"fact": "Owns Project B", "subject": "Sam", "kind": "person"}),
                            ("remember", {"fact": "Owns Project C", "subject": "Sam", "kind": "person"})))
        owners = {(f["Subject"], f["Text"]) for f in mem("maya") if f["Text"].startswith("Owns Project")}
        check(owners == {("Sarah", "Owns Project A"), ("Sam", "Owns Project B"), ("Sam", "Owns Project C")}, "\"Sarah owns Project A; Sam owns Project B\": separate subjects, never merged (nor B and C)")
        chat(process, tools(("remember", {"fact": "Drinks coffee at work"}), ("remember", {"fact": "Drinks coffee at work."}), ("remember", {"fact": "Drinks no coffee at work"}),
                            ("remember", {"fact": "Has 2 kids"}), ("remember", {"fact": "Has 3 kids"})))
        texts = [f["Text"] for f in mem("maya")]
        check(sum(t.startswith("Drinks coffee at work") for t in texts) == 1, "The same thing said again is one item")
        check("Drinks no coffee at work" in texts and "Has 2 kids" in texts and "Has 3 kids" in texts, "Different numbers or a negation are never merged")
        chat(process, tools(("remember", {"fact": "Lives in Lisbon"})))
        _, said = chat(process, tools(("remember", {"fact": "Lives in Porto, not Lisbon", "kind": "correction"})))
        lisbon = next((f for f in mem("maya", True) if f["Text"] == "Lives in Lisbon"), {})
        check(lisbon.get("Status") == "superseded" and any(f["Text"] == "Lives in Porto, not Lisbon" and f["Kind"] == "correction" and not f["Guessed"] for f in mem("maya")),
              "A correction is confirmed and wins over what it corrects")
        _, said = chat(process, tools(("remember", {"fact": "Travels a lot for work " * 20})))
        check(said and said[0]["error"] and "300 at most" in said[0]["text"] and not any("Travels a lot" in f["Text"] for f in mem("maya", True)), "A long fact is refused with an explicit length error, never cut")

        # Secrets by their shape; ordinary sentences pass.
        secrets = ["Card 4111 1111 1111 1111 for the trip", "IBAN GB82 WEST 1234 5698 7654 32", "Token ghp_aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z",
                   "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U", "-----BEGIN RSA PRIVATE KEY----- MIIEow",
                   "Backup code Ab3xQ9zL2mN8pR4tV7wY1kJ6", "The wifi password is hunter22", "AKIAIOSFODNN7EXAMPLE is the work key"]
        harmless = ["Keeps API keys in a password manager", "Card numbers are on the back of the card", "Order number 12345 arrives Friday"]
        _, said = chat(process, tools(*[("remember", {"fact": s}) for s in secrets + harmless]))
        check(len(said) == len(secrets) + len(harmless) and all(r["error"] and "Still never keeps those" in r["text"] for r in said[:len(secrets)]), "Unlabeled card numbers, IBANs, tokens, JWTs and keys are refused")
        check(all(not r["error"] for r in said[len(secrets):]), "\"API keys\" or \"card numbers are on the back\" pass")
        step = until(lambda: next((c for c in chats() if any("TOOLS64" in m["Text"] for m in c["Messages"] if m["Role"] == "user") and any(m["Role"] == "tool" and m["Text"] == "Didn't save to memory" for m in c["Messages"])), None), 5)
        check(step, "A refused remember shows as Didn't save to memory, not Saved")

        # Forget: empty refused, more than three returns the matches, by id forgets every version, and tombstones hold.
        chat(process, tools(*[("remember", {"fact": t}) for t in ("Grows tomatoes in the garden", "Garden party on Saturday", "Garden gate needs paint", "Garden hose is broken")]))
        _, said = chat(process, tools(("forget", {}), ("forget", {"about": "garden"})))
        check(said and said[0]["error"] and "Say what to forget" in said[0]["text"], "forget with no id and no words is refused")
        many = json.loads(said[1]["text"]) if len(said) > 1 and not said[1]["error"] else {}
        check(len(many.get("matches", [])) == 4 and not many.get("forgot") and sum("arden" in f["Text"] for f in mem("maya")) == 4, "More than three matches: nothing goes, the matches come back to confirm")
        _, said = chat(process, tools(("forget", {"id": new_c.get("Id", "")})))
        tombs = read("companions/maya/forgotten.json", [])
        check(not any("browser" in f["Text"] for f in mem("maya", True)) and len(tombs) >= 2 and "Chrome" not in json.dumps(tombs), "Forgetting by id forgets every version; the tombstones hold no text")
        _, said = chat(process, tools(("remember", {"fact": "Uses Chrome as main browser"})))
        check(said and said[0]["error"] and "asked you to forget" in said[0]["text"] and not any("Chrome" in f["Text"] for f in mem("maya", True)), "A forgotten item isn't saved again by the AI on its own")
        (BIN / "summary.txt").write_text(json.dumps({"decisions": [{"text": "Uses Chrome as main browser", "msgs": [1]}, {"text": "Keep the garden plan simple", "msgs": [2]}]}), encoding="utf-8")
        s1, _ = chat(process, "Let's talk about the garden NOSESSION")
        chat(process, "And the gate NOSESSION", new=False)
        summary = until(lambda: next((s for s in summaries("maya") if s["Chat"] == s1.get("Id")), None), 20) or {}
        check(summary and "garden plan" in json.dumps(summary) and "Chrome" not in json.dumps(summary), "A summary rewrite drops a line matching a forgotten item")
        _, said = chat(process, tools(("remember", {"fact": "Uses Chrome as main browser"}), say="I use Chrome as main browser again, remember that"))
        check(said and not said[0]["error"] and any(f["Text"] == "Uses Chrome as main browser" for f in mem("maya")), "Said again deliberately by the user: saved")

        # Settings: an edit is a new version; the page shows source, inferred and earlier versions.
        porto = next((f for f in mem("maya") if f["Text"].startswith("Lives in Porto")), {})
        send(process, "memoryEdit", companion="maya", id=porto.get("Id", ""), text="Lives in Porto since 2024")
        edited = until(lambda: next((f for f in mem("maya") if f["Text"] == "Lives in Porto since 2024"), None), 5) or {}
        check(edited.get("Supersedes") == porto.get("Id") and edited.get("Source") == "settings" and any(f["Id"] == porto.get("Id") and f["Status"] == "superseded" for f in mem("maya", True)),
              "An edit in Settings makes a new version, the old one kept as history")
        chat(process, tools(("remember", {"fact": "Seems to shop late at night", "guessed": True})))
        send(process, "openPanel", name="settings", value="memory")
        page = lambda: js(process, "document.querySelector('.memory-settings')?.innerText") or ""
        until(lambda: "Lives in Porto since 2024" in page(), 10)
        check("Added by the user in Settings" in page() and "Said by the user in the chat" in page(), "Settings > Memory shows where each item came from")
        check("Guessed, not confirmed" in page(), "and marks inferred items")
        js(process, "[...document.querySelectorAll('.memory-item')].find(r => r.innerText.includes('Porto since'))?.querySelector('[aria-label^=\"Earlier versions\"]')?.click()")
        check(until(lambda: "Lives in Porto, not Lisbon" in (js(process, "document.querySelector('.memory-versions')?.innerText") or ""), 5), "and its earlier versions")
        check("Past chats" in page() and "Keep the garden plan simple" in page() and js(process, "!!document.querySelector('[aria-label^=\"Open chat\"]')"), "Chat summaries show, with Open chat")
        check("Don't remember this chat" in page() and "incognito window" in page(), "The page explains the two switches")
        time.sleep(.5)
        rpc(process, "capture", name="memory-settings.png")
        js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")

        # Retrieval over 50 items: unrelated questions bring only the pinned profile items, related ones the right item.
        for q in UNRELATED:
            chat(process, q, who="talia")
            got = memory_section(prompt())
            check(got.count("\n- ") + got.startswith("- ") == 2 and "Goes by Sam" in got and "short replies" in got, f"Unrelated ({q}): only the two pinned items")
        right = 0
        for q, want in NEEDED:
            chat(process, q, who="talia")
            got = memory_section(prompt())
            right += want in got
            if len(got) > 1500:
                check(False, f"Budget over 1500 characters for: {q}")
        check(right >= 9, f"Related questions bring the right item in at least 9 of 10 ({right}/10), aliases included")
        check(all(len(memory_section(p["prompt"])) <= 1500 for p in lines("prompts.jsonl")), "Memory in a prompt stays within about 1,500 characters")
        v, _ = chat(process, "Let's plan the kitchen renovation NOSESSION", who="talia")
        chat(process, "ok, continue that NOSESSION", new=False)
        check("Kitchen renovation budget" in memory_section(prompt()), "A vague follow-up finds what fits the chat so far")

        # Knowledge: an index in the prompt, the body on demand, versions, revisions, undo and reset.
        chat(process, "Anything in your notes?")
        p = prompt()
        check('Findings (file "findings", version ' in p and "read_knowledge" in p and "empty so far" in p, "The prompt lists the knowledge files with versions, not their text")
        long = "Notes on suppliers.\n" + "\n".join(f"- Supplier {i} ships in {i % 9 + 2} weeks" for i in range(200)) + "\n- Zebra Tiles in Ghent is the only one with blue glaze"
        _, said = chat(process, tools(("update_knowledge", {"file": "findings", "text": long, "version": "READ"})))
        check(said and not said[0]["error"] and len(long) > 4000, "update_knowledge with the version it read works")
        _, said = chat(process, tools(("read_knowledge", {"file": "findings"})))
        body = json.loads(said[0]["text"]).get("text", "") if said and not said[0]["error"] else ""
        check("Zebra Tiles in Ghent" in body and body.index("Zebra") > 4000, "read_knowledge finds a fact past character 4,000")
        check("Zebra Tiles" not in prompt(), "and the prompt never carried the body")
        stale = json.loads(said[0]["text"]).get("version", "") if said and not said[0]["error"] else ""
        _, said = chat(process, tools(("update_knowledge", {"file": "findings", "text": "First change", "version": stale}), ("update_knowledge", {"file": "findings", "text": "Second change", "version": stale})))
        disk = (PROFILE / "companions/maya/knowledge/findings.md").read_text(encoding="utf-8")
        check(len(said) == 2 and not said[0]["error"] and said[1]["error"] and "changed since you read it" in said[1]["text"] and "First change" in said[1]["text"] and "First change" in disk and "Second change" not in disk,
              "Two updates from the same version: the second is refused with the current text, nothing is lost")
        revs = list((PROFILE / "companions/maya/knowledge/.revisions/findings").glob("*.md"))
        check(len(revs) == 2, "Each write keeps a revision")
        send(process, "knowledgeUndo", companion="maya", file="findings")
        check(until(lambda: "Zebra Tiles" in (PROFILE / "companions/maya/knowledge/findings.md").read_text(encoding="utf-8"), 5), "Undo brings back the version before")

        # Change notes: an open chat hears about changes made elsewhere, once, and never the text of what was removed.
        a, _ = chat(process, "Let's keep going here")
        send(process, "memoryAdd", companion="maya", text="Prefers tea over coffee")
        chat(process, tools(("remember", {"fact": "Has a dog named Biscuit"})))  # another chat
        send(process, "aiOpenChat", id=a.get("Id", ""))
        send(process, "chatOpen", id=a.get("Id", ""))
        time.sleep(.5)
        chat(process, "Next step please", new=False)
        p = prompt()
        check("[Still] Since your last turn" in p and "Prefers tea over coffee" in p and "Biscuit" in p, "An open chat's next turn hears what changed in Settings and in another chat")
        chat(process, "And the one after", new=False)
        check("Since your last turn" not in prompt(), "once")
        tea = next((f for f in mem("maya") if "tea over coffee" in f["Text"]), {})
        send(process, "memoryForget", companion="maya", id=tea.get("Id", ""))
        until(lambda: not any("tea over" in f["Text"] for f in mem("maya")), 5)
        chat(process, "Then what", new=False)
        p = prompt()
        check("Disregard" in p and tea.get("Id", "-") in p and "tea over coffee" not in p.split("[Still] Since your last turn", 1)[-1], "A forget tells it to disregard, naming the id, never the text")
        send(process, "memoryAdd", companion="maya", text="Prefers tea over coffee")  # added in Settings: the tombstone clears
        check(until(lambda: any("tea over coffee" in f["Text"] for f in mem("maya")), 5), "Added again in Settings: saved")

        # Summaries: two user turns, a cancelled or failed run is never done, off the record none, delete takes it.
        (BIN / "summary.txt").write_text(json.dumps({"goal": [{"text": "Book a table for Friday", "msgs": [1]}], "done": [{"text": "Booked the table", "msgs": [3]}]}), encoding="utf-8")
        f1, _ = chat(process, "Book a table for Friday NOSESSION")
        chat(process, "FAILNOW", new=False)
        failed = until(lambda: next((s for s in summaries("maya") if s["Chat"] == f1.get("Id")), None), 20) or {}
        items = failed.get("Items", [])
        check(items and not any(i["Field"] == "done" for i in items) and any(i["Field"] == "open" and i["Text"] == "Not finished: Booked the table" for i in items) and any(i["Msgs"] == [1] for i in items),
              "A failed run is never summarized as done; each line links its messages")
        o1, _ = chat(process, "Plan a picnic NOSESSION", noMemory=True)
        chat(process, "With sandwiches NOSESSION", new=False)
        time.sleep(4)
        check(not any(s["Chat"] == o1.get("Id") for s in summaries("maya")), "An off-the-record chat is never summarized")
        send(process, "aiDeleteChat", id=f1.get("Id", ""))
        check(until(lambda: not any(s["Chat"] == f1.get("Id") for s in summaries("maya")), 5), "Deleting a chat deletes its summary")
        send(process, "chatSummaries", on=False)
        x1, _ = chat(process, "Talk about shoes NOSESSION")
        chat(process, "Running shoes NOSESSION", new=False)
        time.sleep(4)
        check(not any(s["Chat"] == x1.get("Id") for s in summaries("maya")) and (read("state.json", {}) or {}).get("Preferences", {}).get("ChatSummaries") == "off", "Summaries off: none written")
        send(process, "chatSummaries", on=True)
        check(until(lambda: any(s["Chat"] == x1.get("Id") for s in summaries("maya")), 20), "Back on: the chat is summarized")
        chat(process, tools(("remember", {"fact": "Runs in trail shoes"})), new=False)
        send(process, "memoryForgetChat", companion="maya", chat=x1.get("Id", ""))
        check(until(lambda: not any(s["Chat"] == x1.get("Id") for s in summaries("maya")) and not any("trail shoes" in f["Text"] for f in mem("maya", True)), 5)
              and x1.get("Id") in (read("companions/maya/summaries.json", {}) or {}).get("Skip", {}), "Forget this chat: its summary and what was learned in it go, and it isn't summarized again")

        # Failed writes: a memory file that can't be written is reported, never as remembered.
        target = PROFILE / "companions/rosa"
        chat(process, tools(("remember", {"fact": "Likes early meetings"})), who="rosa")
        if MAC:
            os.chmod(target, stat.S_IRUSR | stat.S_IXUSR)
        else:
            os.chmod(target / "memory.json", stat.S_IREAD)
        before = (target / "memory.json").read_bytes()
        _, said = chat(process, tools(("remember", {"fact": "Likes late lunches"})), who="rosa")
        check(said and said[0]["error"] and "couldn't save" in said[0]["text"] and (target / "memory.json").read_bytes() == before, "A failed write makes remember fail, and the file is unchanged")
        send(process, "memoryAdd", companion="rosa", text="Likes long walks")
        check(toast(process, "couldn't") and (target / "memory.json").read_bytes() == before, "Settings reports it too")
        os.chmod(target, stat.S_IRWXU) if MAC else os.chmod(target / "memory.json", stat.S_IREAD | stat.S_IWRITE)
        _, said = chat(process, tools(("remember", {"fact": "Likes late lunches"})), who="rosa")
        check(said and not said[0]["error"], "and works again once it can")

        # Capture off: nothing new is kept, what's there is still read.
        send(process, "memoryCapture", companion="rosa", on=False)
        _, said = chat(process, tools(("remember", {"fact": "Drives to work"}), ("recall", {"query": "lunches"})), who="rosa")
        check(said and said[0]["error"] and "turned off memory" in said[0]["text"] and "late lunches" in said[1]["text"] and until(lambda: companion("rosa").get("Capture") is False, 5),"Capture off: remember is refused, recall still works")
        send(process, "memoryCapture", companion="rosa", on=True)

        # Setup: once, in the first regular chat; never routines or delegated runs; Introduce yourself again.
        routine = until(lambda: next((c for c in chats() if c.get("Companion") == "jonah" and c.get("Routine")), None), 45) or {}
        until(lambda: not any(c.get("Running") for c in chats() if c.get("Routine")), 20)
        rp = next((x["prompt"] for x in lines("prompts.jsonl") if "Morning check" in x["last"]), "")
        check(routine and "Used skill" not in json.dumps(routine.get("Messages", [])) and "first chat with the user" not in rp and companion("jonah").get("Setup") == "pending",
              "A routine never runs Setup or changes its state")
        chat(process, tools(("ask_companion", {"name": "Jonah", "message": "Say hi NOSESSION"})), wait=60)
        child = next((x["prompt"] for x in lines("prompts.jsonl") if "Say hi NOSESSION" in x["prompt"] and "TOOLS64" not in x["last"]), "")
        check(child and "first chat with the user" not in child and companion("jonah").get("Setup") == "pending", "A delegated run never runs Setup or changes its state")
        i1, said = chat(process, tools(("remember", {"fact": "Wants weekly summaries on Mondays"})), who="ivan")
        p = prompt()
        check("This is your first chat with the user" in p and "Their message below is your first task" in p and any(m["Role"] == "tool" and m["Text"].startswith("Used skill") for m in i1.get("Messages", [])),
              "The first regular chat runs Setup, with an activation note that says what Still knows")
        ivan = until(lambda: companion("ivan").get("Setup") == "done" and companion("ivan"), 5) or {}
        check(ivan.get("SetupAt") and ivan.get("SetupVersion") and ivan.get("SetupChat") == i1.get("Id"), "Setup is done after the first reply, with its time and version")
        i2, _ = chat(process, "Hello again", who="ivan")
        check("first chat with the user" not in prompt() and not any(m["Role"] == "tool" and m["Text"].startswith("Used skill") for m in i2.get("Messages", [])), "The next chat doesn't run it again")
        check("When you join the team" not in prompt(), "and no join text reaches the prompt")

        # Controls, each checked on disk.
        send(process, "personalizationClear", companion="ivan")
        check(until(lambda: not any("weekly summaries" in f["Text"] for f in mem("ivan", True)), 5) and companion("ivan").get("Length") in ("balanced", None), "Clear personalization forgets what Setup learned")
        send(process, "memoryAdd", companion="ivan", text="Likes plain fonts")
        send(process, "memoryClear", companion="maya")
        check(until(lambda: mem("maya", True) == [] and summaries("maya") == [], 5) and "Zebra Tiles" in (PROFILE / "companions/maya/knowledge/findings.md").read_text(encoding="utf-8") and any(c.get("Companion") == "maya" for c in chats()),
              "Clear memory: every item and summary go; knowledge and chats stay")
        chat(process, "What do you know about me?")
        check(not memory_section(prompt()) and "Biscuit" not in prompt(), "and later prompts carry none of it")
        send(process, "knowledgeReset", companion="maya")
        check(until(lambda: "Zebra" not in (PROFILE / "companions/maya/knowledge/findings.md").read_text(encoding="utf-8"), 5), "Reset knowledge files: back to the role's empty seeds")
        send(process, "memoryResetAll", companion="ivan")
        check(until(lambda: mem("ivan", True) == [] and companion("ivan").get("Setup") == "pending" and all(not c.get("Session") for c in chats() if c.get("Companion") == "ivan"), 5),
              "Reset everything: items, summaries and Setup, and its sessions are dropped")

        # Introduce yourself again; the join section's diff.
        send(process, "companionSetupAgain", companion="talia")
        check(until(lambda: companion("talia").get("Setup") == "pending", 5), "Introduce yourself again sets Setup back to pending")
        chat(process, "Hi there", who="talia")
        check("first chat with the user" in prompt() or "introduce yourself again" in prompt(), "and the next chat runs it")
        send(process, "instructionsJoin", companion="maya", apply=True)
        ins = until(lambda: "join the team" not in companion("maya").get("Instructions", "x") and companion("maya").get("Instructions"), 5) or ""
        check(ins == "## How you work\nCheck two sources.\n\n## Standards\nCite every source.", "Accepting the diff removes only the join section")
        errors = rpc(process).get("shellErrors") or js(process, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        try:
            rpc(process, "quit")
            process.wait(timeout=30)
        except Exception as ex:  # noqa: BLE001
            print("quit:", ex)

    # After a restart: memory and Setup stay as they were.
    process = launch(EXE, PROFILE, env)
    try:
        until(lambda: js(process, "!!document.body.innerText.length"), 20)
        chat(process, "Back after a restart", who="talia")
        check("first chat with the user" not in prompt() and companion("talia").get("Setup") == "done", "A restart never reruns Setup")
        check(any("short replies" in f["Text"] for f in mem("talia")), "and keeps memory")
    finally:
        try:
            rpc(process, "quit")
            process.wait(timeout=30)
        except Exception as ex:  # noqa: BLE001
            print("quit:", ex)


if __name__ == "__main__":
    try:
        main()
    finally:
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
