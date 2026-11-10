"""Work in a folder: a companion's working folder, where its AI app lists, reads, creates and edits files with Still's tools.

Any AI app gets list_files, read_file, write_file, edit_file and delete_file. Inside the folder it lists, reads, creates
and edits without a card, and replaces or deletes a file it made in that chat. Replacing a file of the user's asks (Deny,
Allow in this chat, Allow once) unless the companion is on Keep going; deleting one always asks and sends it to the
Recycle Bin (the Trash on a Mac). Allow in this chat stops the asking in that folder. A path with "..", a full path
outside the folder and a link out of it are refused without a card; a full path inside works. A companion with no
folder is told it has none.

A chat can have its own folder over its companion's: the box shows the active one as a chip, one picked before the
chat starts goes with it, the + menu removes it (none in that chat), and a change mid-chat reaches the AI.

Usage: python tests/desktop/folder.py <QA exe>
The fake AI app answers a last line "CALLS: <json list of [tool, arguments]>" by calling each tool in turn through
Still's MCP server and writing each result to results.jsonl as it comes. Deleted files are named still-qa-*.txt, since
they land in the real Recycle Bin or Trash.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, launcher, press_ready, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("folder-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
WORK = RUN / "Work folder"
OUTSIDE = RUN / "outside"
FAILED = []

FAKE = textwrap.dedent(r'''
    import json, os, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    last = next((l for l in reversed(prompt.strip().splitlines()) if l.strip()), "")
    if last.startswith("CALLS: "):
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
        tools = [t["name"] for t in request("tools/list", {})["result"]["tools"]]
        for tool, arguments in json.loads(last[7:]):
            r = request("tools/call", {"name": tool, "arguments": arguments})["result"]
            with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"tool": tool, "tools": tools, "error": bool(r.get("isError")), "text": r["content"][0].get("text", "")}) + "\n")
        still.stdin.close()
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}})
''')


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def results():
    f = BIN / "results.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def calls(p, cid, todo, companion="maya"):
    """Sends one message with these tool calls and returns the chat and how many results there were before."""
    before = len(results())
    if cid is None:
        known = {c["Id"] for c in chats()}
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        send(p, "aiSend", text="CALLS: " + json.dumps(todo), home=True, companion=companion)
        cid = until(lambda: next((c["Id"] for c in chats() if c["Id"] not in known), None), 20)
    else:
        send(p, "aiSend", text="CALLS: " + json.dumps(todo))
    return cid, before


def got(before, n, seconds=30):
    return until(lambda: (r := results()[before:]) and len(r) >= n and r, seconds) or results()[before:]


def out(r):
    try:
        return json.loads(r["text"])
    except (KeyError, TypeError, ValueError):
        return {}


def card(p, seconds=20):
    return until(lambda: js(p, "(c => c && { text: c.innerText, buttons: [...c.querySelectorAll('.approve-actions button')].map(b => b.innerText.trim()) })(document.querySelector('.chat-view .approve-card'))"), seconds) or {}


def no_card(p):
    return not js(p, "!!document.querySelector('.chat-view .approve-card')")


def press(p, words):
    return press_ready(p, f"[...document.querySelectorAll('.chat-view .approve-card .approve-actions button')].find(b => b.innerText.trim() === {json.dumps(words)})")


def idle(p, cid):
    return until(lambda: (c := next((c for c in chats() if c["Id"] == cid), None)) and not c.get("Running"), 30)


def read(name):
    return (WORK / name).read_bytes().decode("utf-8")


def put(path, text):
    path.write_bytes(text.encode("utf-8"))  # as given: no \r\n on Windows


def chip(p, box):
    """The folder chip in a box, or None."""
    return js(p, f"(b => b && b.checkVisibility() ? b.innerText.trim() : null)(document.querySelector('{box} .folder-chip'))")


def prompt_of(cid):
    """The last prompt Still sent for a chat (QA builds log them)."""
    file = PROFILE / "qa-prompts.jsonl"
    lines = [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines() if l.strip()] if file.exists() else []
    return next((l["prompt"] for l in reversed(lines) if l.get("chat") == cid), "")


def link(at, to):
    """A link out of the folder: a junction on Windows (no admin needed), a symbolic link on the Mac."""
    if MAC:
        os.symlink(to, at)
    else:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(at), str(to)], check=True, capture_output=True)


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (WORK / "sub").mkdir(parents=True)
    put(WORK / "sub" / "data.csv", "a,b\n1,2\n")
    put(WORK / "notes.txt", "hello\nworld\n")
    (WORK / "crlf.txt").write_bytes(b"\xef\xbb\xbfone\r\ntwo\r\n")
    put(WORK / "twice.txt", "a\na\n")
    put(WORK / "mine.txt", "keep me")
    for i in (1, 2, 3):
        put(WORK / f"still-qa-delete-{i}.txt", str(i))
    OUTSIDE.mkdir()
    put(OUTSIDE / "secret.txt", "secret")
    link(WORK / "door", OUTSIDE)
    crew = [{"Id": "maya", "Name": "Maya", "Job": "Builder", "Mode": "default", "Folder": str(WORK), "Autonomy": "balanced"},
            {"Id": "leo", "Name": "Leo", "Job": "Researcher", "Mode": "default", "Autonomy": "balanced"}]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": crew, "AgentsEnabled": True, "AiHarness": "fake",
        "Width": 1300, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        send(p, "aiCheck")
        time.sleep(2)

        # Listing and reading, by a path in the folder or a full path inside it.
        cid, before = calls(p, None, [["list_files", {}], ["list_files", {"path": "sub"}], ["read_file", {"path": "notes.txt"}], ["read_file", {"path": str(WORK / "sub" / "data.csv")}]])
        r = got(before, 4)
        check(r and all(t in r[0]["tools"] for t in ["list_files", "read_file", "write_file", "edit_file", "delete_file"]), "The AI is offered the five folder tools")
        items = out(r[0]).get("items", []) if r else []
        check(items[:2] == ["door/", "sub/"] and "notes.txt (12 B)" in items and "mine.txt (7 B)" in items, f"list_files lists the folder, folders first, files with their size ({items})")
        check(len(r) > 1 and out(r[1]).get("items") == ["data.csv (8 B)"], f"...and a folder in it ({r[1]['text'][:120] if len(r) > 1 else None})")
        check(len(r) > 2 and out(r[2]).get("text") == "hello\nworld\n", "read_file reads a file")
        check(len(r) > 3 and out(r[3]).get("text") == "a,b\n1,2\n", "...and a full path inside the folder works")
        check(no_card(p), "None of that asks")
        idle(p, cid)

        # Creating, editing, and replacing its own file: no card.
        cid, before = calls(p, cid, [["write_file", {"path": "made/new.md", "content": "one"}], ["write_file", {"path": "made/new.md", "content": "two"}],
                                     ["edit_file", {"path": "twice.txt", "old": "a", "new": "b"}], ["edit_file", {"path": "twice.txt", "old": "a", "new": "b", "all": True}],
                                     ["edit_file", {"path": "notes.txt", "old": "world", "new": "there"}], ["edit_file", {"path": "crlf.txt", "old": "one\ntwo", "new": "1\n2"}]])
        r = got(before, 6)
        check(len(r) == 6 and not r[0]["error"] and "Created made/new.md" in r[0]["text"] and "Replaced made/new.md" in r[1]["text"] and read("made/new.md") == "two",
              "write_file creates a file (folders on the way too) and replaces its own without asking")
        check(len(r) > 3 and r[2]["error"] and "2 times" in r[2]["text"] and "in 2 places" in r[3]["text"] and read("twice.txt") == "b\nb\n",
              "edit_file won't guess between two matches, and all=true changes both")
        check(len(r) > 4 and not r[4]["error"] and read("notes.txt") == "hello\nthere\n", "edit_file edits a file of the user's without asking")
        check(len(r) > 5 and not r[5]["error"] and (WORK / "crlf.txt").read_bytes() == b"\xef\xbb\xbf1\r\n2\r\n", "...keeping its line endings and byte order mark")
        check(no_card(p), "None of that asks either")
        idle(p, cid)

        # Replacing a file of the user's asks; Deny keeps it.
        cid, before = calls(p, cid, [["write_file", {"path": "mine.txt", "content": "changed"}]])
        asked = card(p)
        check("Replace mine.txt" in asked.get("text", "") and "Work folder" in asked.get("text", "") and asked.get("buttons") == ["Deny", "Allow in this chat", "Allow once"],
              f"Replacing a file of the user's asks, with no Always ({asked})")
        press(p, "Deny")
        r = got(before, 1)
        check(r and r[0]["error"] and "said no" in r[0]["text"] and read("mine.txt") == "keep me", "Deny keeps the file as it was")
        idle(p, cid)

        # Deleting asks; Allow once sends it to the Recycle Bin. Its own file it deletes without asking.
        cid, before = calls(p, cid, [["delete_file", {"path": "still-qa-delete-1.txt"}], ["delete_file", {"path": "made/new.md"}]])
        asked = card(p)
        check("Delete still-qa-delete-1.txt" in asked.get("text", ""), f"Deleting a file of the user's asks ({asked.get('text', '')[:120]!r})")
        press(p, "Allow once")
        r = got(before, 2)
        check(r and not r[0]["error"] and not (WORK / "still-qa-delete-1.txt").exists(), f"Allow once deletes it ({r[0]['text'][:90] if r else None})")
        check(len(r) > 1 and not r[1]["error"] and not (WORK / "made" / "new.md").exists(), "A file it made in this chat it deletes without asking")
        idle(p, cid)

        # Blocked without a card: "..", a full path outside, a link out of the folder, the folder itself.
        blocked = [["read_file", {"path": "../outside/secret.txt"}], ["read_file", {"path": str(OUTSIDE / "secret.txt")}], ["read_file", {"path": "sub/../../outside/secret.txt"}],
                   ["read_file", {"path": "door/secret.txt"}], ["list_files", {"path": "door"}], ["write_file", {"path": "door/new.txt", "content": "x"}],
                   ["delete_file", {"path": "door/secret.txt"}], ["write_file", {"path": ".", "content": "x"}]]
        if not MAC:
            blocked.append(["write_file", {"path": "mine.txt:hidden", "content": "x"}])
        cid, before = calls(p, cid, blocked)
        r = got(before, len(blocked))
        texts = [x["text"][:80] for x in r]
        check(len(r) == len(blocked) and all(x["error"] for x in r) and "secret" not in json.dumps(texts), f"Paths out of the folder are refused ({texts})")
        check(len(r) > 3 and "link" in r[3]["text"] and "outside" in r[1]["text"], "...saying why: outside the folder, or a link to somewhere else")
        check(no_card(p) and (OUTSIDE / "secret.txt").exists() and not (OUTSIDE / "new.txt").exists(), "...with no card, and nothing outside changed")
        idle(p, cid)

        # Keep going: replacing goes ahead, deleting still asks. Allow in this chat stops the asking, on Balanced too.
        send(p, "companionAutonomy", id="maya", level="keepgoing")
        time.sleep(1)
        cid, before = calls(p, cid, [["write_file", {"path": "mine.txt", "content": "auto"}], ["delete_file", {"path": "still-qa-delete-2.txt"}]])
        asked = card(p)
        r = results()[before:]
        check(r and not r[0]["error"] and read("mine.txt") == "auto", "On Keep going replacing a file of the user's goes ahead")
        check("Delete still-qa-delete-2.txt" in asked.get("text", ""), "...but deleting one still asks")
        press(p, "Allow in this chat")
        r = got(before, 2)
        check(len(r) > 1 and not r[1]["error"] and not (WORK / "still-qa-delete-2.txt").exists(), "Allow in this chat deletes it")
        idle(p, cid)
        send(p, "companionAutonomy", id="maya", level="balanced")
        time.sleep(1)
        cid, before = calls(p, cid, [["write_file", {"path": "mine.txt", "content": "after"}], ["delete_file", {"path": "still-qa-delete-3.txt"}]])
        r = got(before, 2)
        check(len(r) == 2 and not any(x["error"] for x in r) and read("mine.txt") == "after" and not (WORK / "still-qa-delete-3.txt").exists() and no_card(p),
              "After Allow in this chat, that chat replaces and deletes in the folder without asking, on Balanced too")
        idle(p, cid)
        audit = [a.get("Result", "") for c in chats() if c["Id"] == cid for a in c.get("Audit", [])]
        check("You said no" in audit and "You allowed it once" in audit and any("Keep going" in a for a in audit) and "You allowed changes in this folder for this chat" in audit,
              f"The chat's log says how each change was allowed ({audit})")

        # A chat's own folder: the box shows the active one; one picked before the chat starts goes with it.
        other = RUN / "Other folder"
        other.mkdir()
        put(other / "plan.md", "plan")
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        check(until(lambda: chip(p, ".home-compose") == "Work folder", 5), f"Before a chat starts, the box shows its companion's folder ({chip(p, '.home-compose')!r})")
        send(p, "chatFolder", path=str(other))
        check(until(lambda: chip(p, ".home-compose") == "Other folder", 5), f"...or the folder picked for the new chat ({chip(p, '.home-compose')!r})")
        known = {c["Id"] for c in chats()}
        before = len(results())
        send(p, "aiSend", text="CALLS: " + json.dumps([["list_files", {}]]), home=True, companion="maya")
        cid3 = until(lambda: next((c["Id"] for c in chats() if c["Id"] not in known), None), 20)
        r = got(before, 1)
        own = lambda: next((c.get("Folder") for c in chats() if c["Id"] == cid3), None)
        check(r and out(r[0]).get("items") == ["plan.md (4 B)"] and own() == str(other), f"The chat starts in that folder ({r[0]['text'][:90] if r else None}, {own()!r})")
        check(until(lambda: chip(p, ".chat-view") == "Other folder", 5), f"The chat's box shows it ({chip(p, '.chat-view')!r})")
        idle(p, cid3)

        # Removed from the + menu: no folder in this chat, though its companion has one, and the AI hears so.
        js(p, "document.querySelector('.chat-view .composer-add').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' }))")
        until(lambda: js(p, "!!document.querySelector('[role=menu]')"), 5)
        items = js(p, "[...document.querySelectorAll('[role=menuitem]')].map(i => i.innerText.trim())") or []
        check("Change folder…" in items and "Remove folder from this chat" in items, f"The + menu changes or removes the chat's folder ({items})")
        js(p, "[...document.querySelectorAll('[role=menuitem]')].find(i => i.innerText.includes('Remove folder')).click()")
        check(until(lambda: chip(p, ".chat-view") is None and own() == "", 5), f"Remove takes the folder out of this chat ({chip(p, '.chat-view')!r}, {own()!r})")
        cid3, before = calls(p, cid3, [["list_files", {}]])
        r = got(before, 1)
        check(r and r[0]["error"] and "no working folder" in r[0]["text"] and "took away your working folder" in prompt_of(cid3), "The AI can't reach files there now, and is told so")
        idle(p, cid3)

        # Back to a folder, given straight as the picker would: the chip and the AI follow.
        send(p, "chatFolder", chat=cid3, path=str(WORK))
        check(until(lambda: chip(p, ".chat-view") == "Work folder", 5), "Changing it shows in the chip at once")
        cid3, before = calls(p, cid3, [["list_files", {"path": "sub"}]])
        r = got(before, 1)
        check(r and not r[0]["error"] and f"changed your working folder to {WORK}" in prompt_of(cid3), "...and the AI works there, told of the change")
        idle(p, cid3)

        # A companion with no folder.
        cid2, before = calls(p, None, [["list_files", {}]], companion="leo")
        r = got(before, 1)
        check(r and r[0]["error"] and "no working folder" in r[0]["text"], f"A companion with no folder is told it has none ({r[0]['text'][:90] if r else None})")
        idle(p, cid2)
        errors = rpc(p).get("shellErrors") or []
        check(not errors, "No interface errors" + (f": {errors[:1]}" if errors else ""))
    finally:
        try:
            rpc(p, "quit")
            p.wait(timeout=20)
        except Exception:
            p.kill()
        time.sleep(1)
        try:
            (WORK / "door").unlink() if MAC else os.rmdir(WORK / "door")  # the link, not what it points to
        except OSError:
            pass
        shutil.rmtree(RUN, ignore_errors=True)
    print("FAILED " + str(FAILED) if FAILED else "PASSED")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
