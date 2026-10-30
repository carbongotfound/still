"""Files in the message box: + > Add files, a drop on the box (it lights up) and a paste each add a chip with the file's
icon, name and size; x removes one; too big says why and adds nothing. Sending names them to the AI, which reads each
with read_attachment: text as text, a PDF's text, an image as an image. The sent message shows them, a follow-up from
the chat's own box works too, and deleting the chat deletes the files. A fake agent app reads every id in the prompt.

Run: python tests/desktop/attach.py artifacts/Still-QA/Still.exe
Out: artifacts/attach-*/ (attach-*.png in the profile folder)
"""
import base64
import json
from pathlib import Path
import re
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("attach-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []
NOTES = "Launch checklist\n- Book the venue\n- Send invites by Friday\n"
# A one-page PDF with a line of real text (Helvetica, uncompressed), so its text has to come out of the PDF.
PDF_OBJECTS = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def pdf(text):
    stream = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET".encode()
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(PDF_OBJECTS, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + (b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream" if body is None else body.encode()) + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n".encode() + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, time
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
    ids = re.findall(r"id ([a-f0-9]{16})\)", prompt) + (["0123456789abcdef"] if "TRY A BAD ID" in prompt else [])
    for i in ids:
        r = request("tools/call", {"name": "read_attachment", "arguments": {"id": i}})["result"]
        c = r["content"][0]
        with open(os.path.join(here, "results.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": i, "error": bool(r.get("isError")), "type": c["type"], "text": c.get("text", ""), "mime": c.get("mimeType"), "data": len(c.get("data", ""))}) + "\n")
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Read them."}]}})
    still.stdin.close()
''')


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def lines(name):
    file = BIN / name
    return [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def files_js(spec):
    """JS for a DataTransfer holding files; spec is [(name, type, base64 bytes or a size of zeros)]."""
    parts = []
    for name, kind, body in spec:
        data = f"Uint8Array.from(atob('{body}'), c => c.charCodeAt(0))" if isinstance(body, str) else f"new Uint8Array({body})"
        parts.append(f"t.items.add(new File([{data}], {json.dumps(name)}, {{ type: {json.dumps(kind)} }}))")
    return "(() => { const t = new DataTransfer(); " + "; ".join(parts) + "; return t })()"


def chips(p, box):
    return js(p, f"[...document.querySelectorAll('{box} .composer .file-chip')].map(c => c.innerText.replace(/\\s+/g, ' ').trim())") or []


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake"},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.home-compose textarea')"), 10)
        time.sleep(.4)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        home = ".home-compose"

        # + opens a menu that starts with Add files.
        js(p, f"document.querySelector('{home} .composer-add').dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }}))")
        first = until(lambda: js(p, "document.querySelector('[role=menu] [role=menuitem]')?.innerText.replace(/\\s+/g, ' ').trim()"), 5) or ""
        check(first.startswith("Add files"), f"+ opens a menu that starts with Add files ({first!r})")
        rpc(p, "capture", name="attach-menu.png")
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); document.querySelector('[role=menu]')?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
        until(lambda: not js(p, "!!document.querySelector('[role=menu]')"), 3)

        # Dragging files over the box lights it up; dropping adds a chip per file with its icon, name and size.
        drop = files_js([("notes.txt", "text/plain", base64.b64encode(NOTES.encode()).decode()), ("brief.pdf", "application/pdf", base64.b64encode(pdf("Quarterly revenue grew 12 percent")).decode())])
        js(p, f"window.__drop = {drop}; document.querySelector('{home} .composer').dispatchEvent(new DragEvent('dragover', {{ bubbles: true, cancelable: true, dataTransfer: window.__drop }}))")
        check(until(lambda: js(p, f"!!document.querySelector('{home} .composer.is-drop .composer-drop')"), 3), "Dragging files over the box lights it up and says Drop to attach")
        rpc(p, "capture", name="attach-drop.png")
        js(p, f"document.querySelector('{home} .composer').dispatchEvent(new DragEvent('drop', {{ bubbles: true, cancelable: true, dataTransfer: window.__drop }}))")
        got = until(lambda: len(chips(p, home)) == 2 and chips(p, home), 10) or chips(p, home)
        check(got == [f"notes.txt {len(NOTES.encode())} B", "brief.pdf " + js(p, "(n => n < 1024 ? n + ' B' : (n / 1024).toFixed(1) + ' KB')(window.__drop.files[1].size)")] and not js(p, f"!!document.querySelector('{home} .composer.is-drop')"),
              f"Dropping adds a chip per file with its name and size, and the highlight goes ({got})")
        check(js(p, f"[...document.querySelectorAll('{home} .file-chip .file-icon svg')].length") == 2, "Each chip has the file's icon")

        # Paste an image.
        js(p, f"document.querySelector('{home} textarea').dispatchEvent(new ClipboardEvent('paste', {{ bubbles: true, cancelable: true, clipboardData: {files_js([('dot.png', 'image/png', base64.b64encode(PNG).decode())])} }}))")
        got = until(lambda: len(chips(p, home)) == 3 and chips(p, home), 10) or chips(p, home)
        check(got[-1:] == [f"dot.png {len(PNG)} B"], f"Pasting an image adds it too ({got})")

        # Too big: says why, adds nothing.
        js(p, f"document.querySelector('{home} .composer').dispatchEvent(new DragEvent('drop', {{ bubbles: true, cancelable: true, dataTransfer: {files_js([('huge.png', 'image/png', 6 * 1024 * 1024)])} }}))")
        toast = until(lambda: js(p, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.innerText).join(' ')"), 5) or ""
        check("huge.png is 6.0 MB. Images can be up to 5 MB." in toast and len(chips(p, home)) == 3, f"A file that's too big says why and isn't added ({toast!r})")

        # x removes one.
        js(p, f"document.querySelector('{home} .file-chip button[aria-label=\"Remove dot.png\"]').click()")
        check(until(lambda: len(chips(p, home)) == 2, 3), "x removes a file")
        js(p, f"document.querySelector('{home} textarea').dispatchEvent(new ClipboardEvent('paste', {{ bubbles: true, cancelable: true, clipboardData: {files_js([('dot.png', 'image/png', base64.b64encode(PNG).decode())])} }}))")
        until(lambda: len(chips(p, home)) == 3, 10)
        rpc(p, "capture", name="attach-chips.png")

        # Send: the AI is told about each file and reads it.
        js(p, f"(t => {{ Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(t, 'What should I do first?'); t.dispatchEvent(new Event('input', {{ bubbles: true }})) }})(document.querySelector('{home} textarea'))")
        js(p, f"document.querySelector('{home} textarea').dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}))")
        until(lambda: len(lines("results.jsonl")) >= 3, 30)
        prompt = (lines("prompts.jsonl") or [{}])[-1].get("prompt", "")
        check(re.search(r'\[Still\] The user attached 3 files: "notes.txt" \(' + str(len(NOTES.encode())) + r' B, id [a-f0-9]{16}\); "brief.pdf" \([\d.]+ (B|KB), id [a-f0-9]{16}\); "dot.png" \(' + str(len(PNG)) + r' B, id [a-f0-9]{16}\)\. Read each with read_attachment', prompt),
              "The AI is told the files' names, sizes and ids, and to read them")
        read = {r["id"]: r for r in lines("results.jsonl")}
        by = {name: read.get(i, {}) for name, i in re.findall(r'"([^"]+)" \([^,]+, id ([a-f0-9]{16})\)', prompt)}
        check(by.get("notes.txt", {}).get("type") == "text" and "Send invites by Friday" in by["notes.txt"].get("text", ""), "A text file reaches the AI as its text")
        check("Quarterly revenue grew 12 percent" in by.get("brief.pdf", {}).get("text", ""), f"A PDF reaches it as the PDF's text ({by.get('brief.pdf', {}).get('text', '')[:120]!r})")
        check(by.get("dot.png", {}).get("type") == "image" and by["dot.png"].get("mime") == "image/png" and by["dot.png"].get("data", 0) > 50, "An image reaches it as an image")
        chat = until(lambda: next((c for c in chats() if not c.get("Running") and any(m["Role"] == "assistant" for m in c["Messages"])), None), 20) or {}
        sent = next((m for m in chat.get("Messages", []) if m["Role"] == "user"), {})
        check(chat.get("Title") == "What should I do first?", f"The chat is titled with what the user typed, not Still's note ({chat.get('Title')!r})")
        check(sent.get("Text") == "What should I do first?" and [f["Name"] for f in sent.get("Files") or []] == ["notes.txt", "brief.pdf", "dot.png"], "The message keeps what was attached")
        check(not chips(p, home) or not js(p, f"!!document.querySelector('{home}')"), "Sending empties the box")
        shown = until(lambda: js(p, "[...document.querySelectorAll('.ai-msg.is-user .msg-files .file-chip')].map(c => c.innerText.replace(/\\s+/g, ' ').trim())"), 10) or []
        check(len(shown) == 3 and shown[0] == f"notes.txt {len(NOTES.encode())} B", f"The chat shows them under the message ({shown})")
        rpc(p, "capture", name="attach-sent.png")

        # A follow-up from the chat's own box, with only a file: it says what to do with it, and a bad id fails cleanly.
        box = ".chat-view"
        until(lambda: js(p, f"!!document.querySelector('{box} .composer textarea')"), 10)
        done = len(lines("results.jsonl"))
        js(p, f"document.querySelector('{box} .composer').dispatchEvent(new DragEvent('drop', {{ bubbles: true, cancelable: true, dataTransfer: {files_js([('plan.md', 'text/markdown', base64.b64encode(b'# Plan\\nShip it').decode())])} }}))")
        check(until(lambda: chips(p, box) == ["plan.md 15 B"], 10), "The chat's own box takes files too")
        js(p, f"(t => {{ Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(t, 'TRY A BAD ID'); t.dispatchEvent(new Event('input', {{ bubbles: true }})) }})(document.querySelector('{box} textarea'))")
        js(p, f"document.querySelector('{box} textarea').dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}))")
        until(lambda: len(lines("results.jsonl")) >= done + 2, 30)
        later = lines("results.jsonl")[done:]
        check(any(r["type"] == "text" and "Ship it" in r["text"] for r in later), "and the AI reads a file sent from there")
        check(any(r["error"] and "No attachment has that id" in r["text"] for r in later), "An id that isn't an attachment is refused")
        sent_ids = [f["Id"] for c in chats() for m in c["Messages"] for f in m.get("Files") or []]
        check(len(sent_ids) == 4 and all((PROFILE / "ai" / "attachments" / i).is_dir() for i in sent_ids), f"Still keeps each file in the profile's ai/attachments ({len(sent_ids)})")

        # Deleting the chat deletes its files.
        until(lambda: not next((c for c in chats() if c.get("Running")), None), 15)
        send(p, "aiDeleteChat", id=chat.get("Id", ""))
        check(until(lambda: not any((PROFILE / "ai" / "attachments" / i).exists() for i in sent_ids), 5), "Deleting the chat deletes its files")
        # A file attached but never sent is cleared the next time Still starts.
        rpc(p, "quit")
        until(lambda: p.poll() is not None, 15)
        p = launch(EXE, PROFILE)
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        check(until(lambda: not any((PROFILE / "ai" / "attachments").iterdir()), 5), "A file that was never sent is gone after a restart")
    finally:
        try:
            rpc(p, "quit")
        except (RuntimeError, OSError):
            pass
        until(lambda: p.poll() is not None, 15)
        if p.poll() is None:
            p.kill()
    print(f"\n{len(FAILED)} failed" if FAILED else "\nAll attach checks passed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
