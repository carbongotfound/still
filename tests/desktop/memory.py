"""Each companion's memory: remember in one chat, recall in the next, keep one copy of a fact, forget it, and never keep
an off-the-record chat or anything from a private tab. No AI plan is used: a fake agent app (a manifest in Still's
agents folder) connects to Still's MCP server and runs the command on the last line of each prompt:
  REMEMBER: <fact>   calls remember
  RECALL: <words>    calls recall
  FORGET: <words>    calls forget
  KNOW: <file> | <text>  calls update_knowledge
Every tool result goes to results.jsonl, every prompt to prompts.jsonl.

Run: python tests/desktop/memory.py artifacts/Still-QA/Still.exe
Out: artifacts/memory-*/ (memory-page.png, Settings > Memory)
"""
import http.server
import json
import os
from pathlib import Path
import sys
import textwrap
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("memory-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}
SECRET = "Secret Garden Plans"  # a private tab's title


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"<!doctype html><meta charset=utf-8><title>{SECRET}</title><h1>Just for me</h1>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()

FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    with open(os.path.join(here, "prompts.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"prompt": prompt}) + "\n")
    def say(e): print(json.dumps(e), flush=True)
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
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    last = prompt.strip().splitlines()[-1]
    verb, _, rest = last.partition(": ")
    tool = {"REMEMBER": ("remember", "fact"), "RECALL": ("recall", "query"), "FORGET": ("forget", "about"), "KNOW": ("update_knowledge", "file")}.get(verb)
    if tool:
        file, _, text = rest.partition(" | ")
        r = request("tools/call", {"name": tool[0], "arguments": {tool[1]: rest, "kind": "preference"} if tool[0] == "remember" else {"file": file, "text": text} if verb == "KNOW" else {tool[1]: rest}})["result"]
        with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps({"ask": last, "error": bool(r.get("isError")), "text": r["content"][0]["text"]}) + "\n")
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay, done."}]}})
    still.stdin.close()
''')


def facts():
    try:
        return json.loads((PROFILE / "companions" / "maya" / "memory.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def lines(name):
    file = BIN / name
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def ask(process, text, **extra):
    """A new chat with Maya from a new tab; returns the chat and what the tool said."""
    done = len(lines("results.jsonl"))
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
    js(process, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
    send(process, "aiSend", text=text, home=True, companion="maya", **extra)
    chat = until(lambda: next((c for c in chats() if c["Title"] == text and not c.get("Running") and any(m["Role"] == "assistant" for m in c["Messages"])), None), 30)
    until(lambda: len(lines("results.jsonl")) > done, 5)
    time.sleep(.3)
    return chat or {}, (lines("results.jsonl")[done:] or [{}])[0]


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": [{**c, "Crew": "research"} if c["Id"] == "maya" else c for c in CREW], "AgentsEnabled": True, "AiHarness": "fake",
        "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}]}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    process = launch(EXE, PROFILE)
    try:
        until(lambda: js(process, "!!document.body.innerText.length"), 20)

        # Remember in one chat, recall in the next.
        a, said = ask(process, "REMEMBER: Prefers aisle seats on long flights")
        kept = [f for f in facts() if f["Text"] == "Prefers aisle seats on long flights"]
        check(not said.get("error") and len(kept) == 1 and kept[0]["Chat"] == a.get("Id") and kept[0]["Kind"] == "preference" and kept[0]["At"],
              "remember keeps the fact with its kind, date and the chat it came from")
        check(any(f["Kind"] == "chat" and f["Key"] == "chat:" + a.get("Id", "") for f in facts()), "The chat itself is remembered as a past chat")
        b, said = ask(process, "RECALL: seats")
        prompt = lines("prompts.jsonl")[-1]["prompt"]
        check("What you remember about the user" in prompt and "Prefers aisle seats on long flights" in prompt, "The next chat starts out knowing it")
        check("Prefers aisle seats on long flights" in said.get("text", ""), "and recall finds it")

        # One copy of a fact.
        ask(process, "REMEMBER: Prefers aisle seats on long flights.")
        check(sum("aisle seats" in f["Text"] and f["Kind"] != "chat" for f in facts()) == 1, "Remembering it again keeps one copy")

        # Forget.
        _, said = ask(process, "FORGET: aisle seats")
        check("aisle seats" in said.get("text", "") and not any("aisle seats" in f["Text"] and f["Kind"] != "chat" for f in facts()), "forget forgets it")

        # Knowledge files: Maya came with her role's three, empty, and her chats start out with them. update_knowledge
        # rewrites one, keeping its name, and the next chat knows it. Only her own files, and never off the record.
        notes = PROFILE / "companions" / "maya" / "knowledge"
        check(sorted(f.stem for f in notes.glob("*.md")) == ["findings", "market", "sources"], "Maya has her role's three knowledge files")
        check('## Findings (file "findings")' in prompt and "(Empty so far.)" in prompt and "update_knowledge" in prompt, "and her chats start out with them, empty so far")
        _, said = ask(process, "KNOW: findings | - Most suppliers ship in 6 weeks (source: the 2026 survey)")
        body = (notes / "findings.md").read_text(encoding="utf-8")
        check(not said.get("error") and "Findings" in said.get("text", "") and body.startswith("---\nname: Findings\nabout: ") and body.rstrip().endswith("- Most suppliers ship in 6 weeks (source: the 2026 survey)"),
              "update_knowledge rewrites a file, keeping its name and what it holds")
        ask(process, "RECALL: suppliers")
        check("Most suppliers ship in 6 weeks" in lines("prompts.jsonl")[-1]["prompt"], "The next chat starts out knowing it")
        _, said = ask(process, "KNOW: diary | anything")
        check(said.get("error") and "no knowledge file" in said.get("text", "") and not (notes / "diary.md").exists(), "A file that isn't one of hers is refused")
        _, said = ask(process, "KNOW: findings | Allergic to peanuts", noMemory=True)
        check(said.get("error") and "off the record" in said.get("text", "") and "peanuts" not in (notes / "findings.md").read_text(encoding="utf-8"), "An off-the-record chat can't write one")

        # Off the record: from the start, and switched on for a chat that already ran.
        c, said = ask(process, "REMEMBER: Allergic to peanuts", noMemory=True)
        check(said.get("error") and "off the record" in said.get("text", ""), "An off-the-record chat can't remember")
        check("off the record" in lines("prompts.jsonl")[-1]["prompt"], "and its AI is told so")
        check(c.get("NoMemory") and not any("peanuts" in f["Text"] or f["Chat"] == c.get("Id") or f["Key"] == "chat:" + c.get("Id", "") for f in facts()), "Nothing from it is kept, not even the chat")
        d, said = ask(process, "REMEMBER: Loves late night jazz")
        check(any("jazz" in f["Text"] for f in facts()), "A normal chat remembers")
        switch = ".chat-memory button[role=switch]"
        check(until(lambda: js(process, f"document.querySelector('{switch}')?.getAttribute('aria-checked')") == "false", 5), "The chat shows a Don't remember this chat switch")
        js(process, f"document.querySelector('{switch}')?.click()")
        check(until(lambda: any(x["Id"] == d.get("Id") and x.get("NoMemory") for x in chats()), 5) and until(lambda: not any("jazz" in f["Text"] or f["Chat"] == d.get("Id") for f in facts()), 5),
              "Switching it on forgets everything from that chat")

        # Private tabs: nothing from them is kept or handed to the AI.
        send(process, "new", url=f"http://127.0.0.1:{SERVER.server_port}/garden", private=True)
        until(lambda: any(t.get("Private") and t["Title"] == SECRET for t in rpc(process)["tabs"]), 10)
        _, said = ask(process, f"REMEMBER: Planning the {SECRET} party")
        check(said.get("error") and "private tab" in said.get("text", ""), "A fact naming a private tab is refused")
        check(not any(SECRET.lower() in f["Text"].lower() for f in facts()), "and nothing from it is kept, not even the chat's title")
        _, said = ask(process, f"KNOW: findings | The {SECRET} party is on Friday")
        check(said.get("error") and "private tab" in said.get("text", "") and SECRET not in (PROFILE / "companions" / "maya" / "knowledge" / "findings.md").read_text(encoding="utf-8"),
              "and so is a knowledge file naming it")
        _, said = ask(process, "RECALL: garden party")
        check(SECRET not in said.get("text", "") and SECRET not in lines("prompts.jsonl")[-1]["prompt"], "Later chats never see it")
        check(all(SECRET not in "\n".join(p["prompt"].strip().splitlines()[:-1]) for p in lines("prompts.jsonl")), "No prompt carries the private tab, beyond what the user typed")

        # Settings > Memory shows it, and forgetting there works too.
        send(process, "memoryAdd", companion="maya", text="My sister Maya lives in Porto.", kind="person")
        send(process, "openPanel", name="settings", value="memory")
        rows = lambda: js(process, "[...document.querySelectorAll('.memory-row')].map(r => r.innerText)") or []
        check(until(lambda: any("Maya lives in Porto" in r for r in rows()), 10), "Settings > Memory lists what Maya remembers")
        check("Past chats" in (js(process, "document.querySelector('.memory-settings')?.innerText") or ""), "and the past chats")
        time.sleep(.6)
        rpc(process, "capture", name="memory-page.png")
        js(process, "[...document.querySelectorAll('.memory-row')].find(r => r.innerText.includes('Maya'))?.querySelector('[aria-label^=Forget]')?.click()")
        check(until(lambda: not any("Maya" in f["Text"] for f in facts()), 5), "Forget on the Memory page forgets it")
        errors = rpc(process).get("shellErrors") or js(process, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)


if __name__ == "__main__":
    try:
        main()
    finally:
        SERVER.shutdown()
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
