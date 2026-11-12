"""Work in a folder: a companion's working folder, where its AI app lists, reads, creates and edits files with Still's tools.

Any AI app gets list_files, read_file, write_file, edit_file and delete_file. Inside the folder it lists, reads, creates
and edits without a card, and replaces or deletes a file it made in that chat. Replacing a file of the user's asks (Not
now, Allow) on Ask more, not on Balanced or Keep going; deleting one always asks, once at a time, and sends it to the
Recycle Bin (the Trash on a Mac). A path with "..", a full path
outside the folder and a link out of it are refused without a card; a full path inside works. A companion with no
folder is told it has none.

A chat can have its own folder over its companion's: the box shows the active one as a chip, one picked before the
chat starts goes with it, the + menu removes it (none in that chat), and a change mid-chat reaches the AI.

Usage: python tests/desktop/folder.py <QA exe>
The fake AI app answers a last line "CALLS: <json list of [tool, arguments]>" by calling each tool in turn through
Still's MCP server and writing each result to results.jsonl as it comes. Deleted files are named still-qa-*.txt, since
they land in the real Recycle Bin or Trash.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import uuid
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, launcher, press_ready, rpc, screens, send, until  # noqa: E402

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
            if tool == "sleep":  # a pause between steps, as a real model takes
                time.sleep(arguments); continue
            # the stream a real AI app prints around a call, so Still shows the step as it does for a real one
            k = "t%d" % time.time_ns()
            say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": k, "name": "mcp__still__" + tool, "input": arguments}]}})
            r = request("tools/call", {"name": tool, "arguments": arguments})["result"]
            say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": k, "is_error": bool(r.get("isError"))}]}})
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


def png(rgb):
    """A one-pixel picture in that colour."""
    chunk = lambda kind, data: len(data).to_bytes(4, "big") + kind + data + zlib.crc32(kind + data).to_bytes(4, "big")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", (1).to_bytes(4, "big") * 2 + bytes([8, 2, 0, 0, 0])) + chunk(b"IDAT", zlib.compress(bytes([0, *rgb]))) + chunk(b"IEND", b"")


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


LONG = "long-chat"


def long_chat():
    """A chat past the 300 messages the interface gets, ending with a turn that read 42 files."""
    messages, k = [], 0
    while len(messages) < 270:
        messages += [{"Role": "user", "Text": f"Question {k}"}, {"Role": "tool", "Text": f"Read notes-{k}.txt"}, {"Role": "tool", "Text": f"Read data-{k}.csv"},
                     {"Role": "assistant", "Text": f"Answer {k}"}]
        k += 1
    messages += [{"Role": "user", "Text": "Read every frame"}] + [{"Role": "tool", "Text": f"Read frames/f{i:02d}.txt"} for i in range(42)]
    messages += [{"Role": "assistant", "Text": "I read all 42 frames."}]
    return {"Id": LONG, "Title": "A long chat", "Harness": "fake", "Companion": "maya", "Started": True, "Updated": "2026-11-01T10:00:00Z", "Messages": messages}


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
    (PROFILE / "ai").mkdir(parents=True)
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([long_chat()]))
    crew = [{"Id": "maya", "Name": "Maya", "Job": "Builder", "Mode": "default", "Folder": str(WORK), "Autonomy": "ask"},
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
        check("Replace mine.txt" in asked.get("text", "") and "Work folder" in asked.get("text", "") and asked.get("buttons") == ["Not now", "Allow"] and "Always" not in asked.get("text", ""),
              f"On Ask more, replacing a file of the user's asks, with no Always ({asked})")
        press(p, "Not now")
        r = got(before, 1)
        check(r and r[0]["error"] and "said no" in r[0]["text"] and read("mine.txt") == "keep me", "Not now keeps the file as it was")
        idle(p, cid)

        # Deleting asks; Allow sends it to the Recycle Bin. Its own file it deletes without asking.
        cid, before = calls(p, cid, [["delete_file", {"path": "still-qa-delete-1.txt"}], ["delete_file", {"path": "made/new.md"}]])
        asked = card(p)
        check("Delete still-qa-delete-1.txt" in asked.get("text", ""), f"Deleting a file of the user's asks ({asked.get('text', '')[:120]!r})")
        press(p, "Allow")
        r = got(before, 2)
        check(r and not r[0]["error"] and not (WORK / "still-qa-delete-1.txt").exists(), f"Allow deletes it ({r[0]['text'][:90] if r else None})")
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

        # Keep going and Balanced: replacing goes ahead, deleting still asks every time.
        send(p, "companionAutonomy", id="maya", level="keepgoing")
        time.sleep(1)
        cid, before = calls(p, cid, [["write_file", {"path": "mine.txt", "content": "auto"}], ["delete_file", {"path": "still-qa-delete-2.txt"}]])
        asked = card(p)
        r = results()[before:]
        check(r and not r[0]["error"] and read("mine.txt") == "auto", "On Keep going replacing a file of the user's goes ahead")
        check("Delete still-qa-delete-2.txt" in asked.get("text", ""), "...but deleting one still asks")
        press(p, "Allow")
        r = got(before, 2)
        check(len(r) > 1 and not r[1]["error"] and not (WORK / "still-qa-delete-2.txt").exists(), "Allow deletes it")
        idle(p, cid)
        send(p, "companionAutonomy", id="maya", level="balanced")
        time.sleep(1)
        cid, before = calls(p, cid, [["write_file", {"path": "mine.txt", "content": "after"}], ["delete_file", {"path": "still-qa-delete-3.txt"}]])
        asked = card(p)
        check(read("mine.txt") == "after" and "Delete still-qa-delete-3.txt" in asked.get("text", ""), "On Balanced too: replacing goes ahead, and deleting asks again")
        press(p, "Not now")
        r = got(before, 2)
        check(len(r) == 2 and r[1]["error"] and (WORK / "still-qa-delete-3.txt").exists(), "Not now keeps it")
        idle(p, cid)
        send(p, "companionAutonomy", id="maya", level="ask")
        audit = [a.get("Result", "") for c in chats() if c["Id"] == cid for a in c.get("Audit", [])]
        check("You said no" in audit and "You allowed it once" in audit and "Done without asking, as Balanced and Keep going allow" in audit,
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

        # A long chat updates in place as steps come in: no row is drawn again (fading in again or folding up), and the
        # view stays on what the user reads further up.
        send(p, "chatOpen", id=LONG)
        until(lambda: js(p, "document.querySelectorAll('.chat-view .ai-turn').length > 100"), 15)
        before = len(results())
        send(p, "aiSend", text="CALLS: " + json.dumps([["sleep", 3]] + [x for _ in range(45) for x in (["read_file", {"path": "notes.txt"}], ["sleep", .05])]))
        until(lambda: js(p, "[...document.querySelectorAll('.chat-view .ai-msg.is-user')].some(m => m.innerText.startsWith('CALLS'))"), 10)
        time.sleep(.8)
        js(p, """(() => {
         const w = [...document.querySelectorAll('.chat-view details.ai-work')].find(d => d.querySelector('summary').innerText.startsWith('42 steps'))
         w.open = true; w.querySelector('details.ai-work-fold').open = true
         window.__rows = [...document.querySelectorAll('.chat-view .chat-column > *')].slice(-60, -2).filter(r => !r.querySelector('.ai-live')) // not the live line, which goes when it's done
         window.__fold = w
         const log = document.querySelector('.chat-view .ai-log')
         log.scrollTop += w.getBoundingClientRect().top - log.getBoundingClientRect().top - 40
         log.dispatchEvent(new Event('scroll'))
        })()""")
        at = lambda: js(p, "Math.round(window.__fold.getBoundingClientRect().top - document.querySelector('.chat-view .ai-log').getBoundingClientRect().top)")
        top = at()
        fold = js(p, "window.__fold.querySelector('details.ai-work-fold summary').innerText.trim()")
        r = got(before, 45, 60)
        idle(p, LONG)
        time.sleep(1)
        kept = js(p, "[window.__rows.length, window.__rows.filter(r => r.isConnected).length, window.__fold.isConnected && window.__fold.open, !!window.__fold.querySelector('details.ai-work-fold[open]')]")
        check(len(r) == 45 and fold == "Read 42 files" and kept and kept[0] > 40 and kept[0] == kept[1], f"A chat past 300 messages draws none of its rows again as 45 steps come in ({len(r)}, {fold!r}, {kept})")
        check(kept and kept[2] and kept[3], "...so the turn the user opened, and its Read 42 files, stay open")
        screens(p, PROFILE, "4-long-chat")
        moved = at()
        check(top is not None and moved is not None and abs(moved - top) <= 2, f"...and the view stays on it while the user reads further up ({top} then {moved})")

        # A companion with no folder.
        cid2, before = calls(p, None, [["list_files", {}]], companion="leo")
        r = got(before, 1)
        check(r and r[0]["error"] and "no working folder" in r[0]["text"] and "request_folder" in r[0]["text"], f"A companion with no folder is told it has none, and how to ask ({r[0]['text'][:90] if r else None})")
        idle(p, cid2)

        # request_folder: a card in the chat. Allow makes it the chat's folder and the companion carries on there.
        frames = RUN / "frames"
        frames.mkdir()
        put(frames / "f01.txt", "one")
        cid2, before = calls(p, cid2, [["request_folder", {"path": str(frames), "why": "to read the frames", "write": True}], ["list_files", {}]])
        asked = card(p)
        text = asked.get("text", "")
        check("request_folder" in (results()[before - 1]["tools"] if before else []) and text.startswith("Let Leo work in ") and "frames?" in text and str(frames) in text and "to read the frames" in text
              and asked.get("buttons") == ["Not now", "Choose another folder", "Allow"], f"Asking for a folder shows a card: Let Leo work in the folder, with the whole path under it ({asked})")
        screens(p, PROFILE, "5-folder-card")
        press(p, "Allow")
        r = got(before, 2)
        own2 = lambda: next((c.get("Folder") for c in chats() if c["Id"] == cid2), None)
        check(len(r) == 2 and not r[0]["error"] and "You work in" in r[0]["text"] and out(r[1]).get("items") == ["f01.txt (3 B)"] and own2() == str(frames),
              f"Allow makes it the chat's folder, and the companion carries on there ({[x['text'][:60] for x in r]}, {own2()!r})")
        check(until(lambda: chip(p, ".chat-view") == "frames", 5), "The chat's box shows the folder")
        idle(p, cid2)

        # A picture it read opens big on a click; Left and Right step through the others it read in this chat, with no flash.
        red, blue = png((255, 0, 0)), png((0, 0, 255))
        (frames / "f01.png").write_bytes(red)
        (frames / "f02.png").write_bytes(blue)
        cid2, before = calls(p, cid2, [["read_file", {"path": "f01.png"}], ["read_file", {"path": "f02.png"}]])
        r = got(before, 2)
        idle(p, cid2)
        data = lambda pic: "data:image/png;base64," + base64.b64encode(pic).decode()
        shown = lambda: js(p, "(d => d && { title: d.querySelector('h2').innerText, src: (d.querySelector('img') || {}).src || '', spinner: !!d.querySelector('[role=status], .animate-spin') })(document.querySelector('.file-preview'))") or {}
        js(p, "document.querySelectorAll('.chat-view .ai-step-picture').forEach(b => { for (let d = b.closest('details'); d; d = d.parentElement.closest('details')) d.open = true })")  # its turn and its Read 2 files, opened as the user would
        rows = js(p, "[...document.querySelectorAll('.chat-view .ai-step-picture')].map(b => b.innerText.trim())") or []
        js(p, "[...document.querySelectorAll('.chat-view .ai-step-picture')].find(b => b.innerText.includes('f01.png')).click()")
        first = until(lambda: (s := shown()).get("src") and s, 10) or {}
        check(len(r) == 2 and rows == ["Read f01.png", "Read f02.png"] and first.get("title") == "f01.png · 1 of 2" and first.get("src") == data(red),
              f"A picture it read opens big on a click ({rows}, {first.get('title')!r}, {first.get('src', '')[:40]!r})")
        screens(p, PROFILE, "3-picture")
        key = lambda k: js(p, f"document.querySelector('.file-preview').dispatchEvent(new KeyboardEvent('keydown', {{ key: '{k}', bubbles: true }}))")
        key("ArrowRight")
        seen = []
        second = until(lambda: (s := shown(), seen.append(s))[0].get("src") == data(blue) and s, 10) or {}
        check(second.get("title") == "f02.png · 2 of 2" and not any(s.get("spinner") or not s.get("src") for s in seen), f"Right steps to the next one, with no spinner or blank in between ({second.get('title')!r}, {len(seen)} looks)")
        key("ArrowRight")
        time.sleep(.5)
        check(shown().get("src") == data(blue), "...and stops at the last")
        key("ArrowLeft")
        check(until(lambda: shown().get("src") == data(red), 10) and shown().get("title") == "f01.png · 1 of 2", "Left steps back")
        key("Escape")
        check(until(lambda: not js(p, "!!document.querySelector('.file-preview')"), 5), "Escape closes it")
        def asked(step, chat):  # posted, then the answer polled for (Windows' script call doesn't wait for a promise)
            js(p, f"""(() => {{ const id = 'probe' + Math.random(); window.__asked = undefined
             const got = e => {{ if (e.detail.id === id) {{ removeEventListener('still-thumb', got); window.__asked = e.detail.data }} }}
             addEventListener('still-thumb', got); window.chrome.webview.postMessage({{ op: 'aiPicture', id, chat: {json.dumps(chat)}, step: {json.dumps(step)} }}) }})()""")
            until(lambda: js(p, "window.__asked !== undefined"), 5)
            return js(p, "window.__asked")
        put(OUTSIDE / "secret.png", "not for the page")
        check(asked("Read f01.png", cid2) == data(red) and asked("Read ../outside/secret.png", cid2) == "" and asked("Read f01.png", "nope") == "",
              "Still only shows a picture its step in that chat names, from the chat's folder")
        idle(p, cid2)

        # Not now leaves it without; Keep going still asks; Still's data, or a folder holding it, and a folder that isn't there are refused without a card.
        send(p, "companionAutonomy", id="leo", level="keepgoing")
        time.sleep(1)
        cid4, before = calls(p, None, [["request_folder", {"path": str(frames), "write": True}]], companion="leo")
        asked = card(p)
        check(asked.get("buttons") == ["Not now", "Choose another folder", "Allow"], "On Keep going it still asks")
        press(p, "Not now")
        r = got(before, 1)
        check(r and r[0]["error"] and "not now" in r[0]["text"] and not next((c.get("Folder") for c in chats() if c["Id"] == cid4), None), f"Not now leaves the chat without a folder ({r[0]['text'][:80] if r else None})")
        idle(p, cid4)
        send(p, "companionAutonomy", id="leo", level="balanced")
        cid4, before = calls(p, cid4, [["request_folder", {"path": str(PROFILE)}], ["request_folder", {"path": str(RUN)}], ["request_folder", {"path": str(RUN / "nowhere")}], ["request_folder", {"path": "frames"}]])
        r = got(before, 4)
        check(len(r) == 4 and all(x["error"] for x in r) and "Still's data" in r[0]["text"] and "Still's data" in r[1]["text"] and "no folder at" in r[2]["text"] and "no folder at" in r[3]["text"] and no_card(p),
              f"Still's data, a folder holding it, a folder that isn't there and a path that isn't whole are refused, with no card ({[x['text'][:50] for x in r]})")
        idle(p, cid4)

        # To see a folder outside its working folder (or with none): a card, then list_files and read_file by full path
        # there, read-only, for the rest of the chat.
        clips = RUN / "clips"
        clips.mkdir()
        put(clips / "take1.txt", "first take")
        cid5, before = calls(p, None, [["request_folder", {"path": str(clips), "why": "to look at the takes"}], ["list_files", {"path": str(clips)}],
                                        ["read_file", {"path": str(clips / "take1.txt")}], ["write_file", {"path": str(clips / "new.txt"), "content": "x"}]], companion="leo")
        asked = card(p)
        text = asked.get("text", "")
        check(text.startswith("Let Leo see ") and "clips?" in text and str(clips) in text and "to look at the takes" in text and asked.get("buttons") == ["Not now", "Allow"],
              f"Asking to see a folder shows a card: Let Leo see it, with Not now and Allow ({asked})")
        screens(p, PROFILE, "6-see-card")
        press(p, "Allow")
        r = got(before, 4)
        check(len(r) == 4 and not r[0]["error"] and "for the rest of this chat" in r[0]["text"] and out(r[1]).get("items") == ["take1.txt (10 B)"] and "first take" in r[2]["text"],
              f"Allow: it lists and reads the folder by full path ({[x['text'][:60] for x in r]})")
        check(len(r) == 4 and r[3]["error"] and "only look" in r[3]["text"] and not (clips / "new.txt").exists(), f"...read-only: writing there is refused ({r[3]['text'][:80] if len(r) == 4 else None})")
        check(not next((c.get("Folder") for c in chats() if c["Id"] == cid5), None), "...and it isn't made the chat's working folder")
        idle(p, cid5)
        cid5, before = calls(p, cid5, [["read_file", {"path": str(clips / "take1.txt")}], ["request_folder", {"path": str(clips)}]])
        r = got(before, 2)
        check(len(r) == 2 and "first take" in r[0]["text"] and "already" in r[1]["text"] and no_card(p), f"...and the next reply still reads there, with no new card ({[x['text'][:50] for x in r]})")
        idle(p, cid5)
        cid6, before = calls(p, None, [["request_folder", {"path": str(clips)}]], companion="leo")
        card(p)
        press(p, "Not now")
        r = got(before, 1)
        check(r and r[0]["error"] and "not now" in r[0]["text"], f"Not now leaves it unable to look, and another chat asks again ({r[0]['text'][:80] if r else None})")
        idle(p, cid6)
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
