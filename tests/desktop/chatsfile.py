"""A chats.json Still can't read loses nothing: the file is kept as it was next to it, the attachments stay, Still says so
once, and new chats go to a new file that the next start reads as usual.

Run: python tests/desktop/chatsfile.py artifacts/Still-QA/Still.exe
Out: artifacts/chatsfile-*/
"""
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
import qa

EXE = Path(sys.argv[1]).resolve()
RUN = Path(__file__).resolve().parents[2] / "artifacts" / f"chatsfile-{uuid.uuid4().hex[:8]}"
FAKE = r'''
import json, sys, time
if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
sys.stdin.read()
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay."}]}}), flush=True)
'''
BROKEN = b'[{"Id": "old1", "Title": "Old chat", "Messages": [{"Role": "user", "Text": "Words from the old chat.'
results = []


def check(ok, name):
    results.append({"name": name, "ok": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def kept():
    return sorted((PROFILE / "ai").glob("chats.json.broken-*"))


def quit(process):
    try: qa.rpc(process, "quit")
    except RuntimeError: pass
    try: process.wait(timeout=20)
    except Exception: process.kill()


shutil.rmtree(RUN, ignore_errors=True)
PROFILE = RUN / "profile"; (PROFILE / "ai" / "attachments" / "att1").mkdir(parents=True); (PROFILE / "agents").mkdir()
bin_ = RUN / "bin"; bin_.mkdir(); (bin_ / "fake_agent.py").write_text(FAKE, encoding="utf-8"); qa.launcher(bin_ / "fakeagent", bin_ / "fake_agent.py")
(PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(bin_ / "fakeagent"),
    "detect": ["status"], "expect": "signed in", "run": ["run"], "output": "stream-json"}))
(PROFILE / "ai" / "chats.json").write_bytes(BROKEN)
(PROFILE / "ai" / "attachments" / "att1" / "plan.md").write_text("# Plan", encoding="utf-8")
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}],
    "Preferences": {"AiHarness": "fake", "AgentsEnabled": True, "Companions": qa.CREW}}))

process = qa.launch(EXE, PROFILE)
try:
    said = qa.until(lambda: "couldn't read your saved chats" in qa.text(process), 10, .1)
    check(said, "Still says once that it couldn't read the saved chats")
    check(len(kept()) == 1 and kept()[0].read_bytes() == BROKEN, f"The unreadable file is kept as it was, next to it ({[k.name for k in kept()]})")
    check((PROFILE / "ai" / "attachments" / "att1" / "plan.md").exists(), "Its attachments stay")
    qa.send(process, "aiSend", text="A new chat after the bad file", home=True, companion="maya")
    def saved():
        try: return [c for c in json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8")) if any("A new chat after the bad file" in m.get("Text", "") for m in c["Messages"])]
        except (OSError, ValueError): return []
    check(qa.until(saved, 20), "A new chat is saved to a new chats.json")
    check(len(kept()) == 1 and kept()[0].read_bytes() == BROKEN and (PROFILE / "ai" / "attachments" / "att1" / "plan.md").exists(), "The kept file and the attachments are untouched by the save")
finally:
    quit(process)

process = qa.launch(EXE, PROFILE)
try:
    time.sleep(2)
    check("couldn't read your saved chats" not in qa.text(process), "The next start reads the new file and says nothing")
    check(saved(), "The new chat is still there")
    check(len(kept()) == 1, "No second copy is kept")
finally:
    quit(process)

(RUN / "results.json").write_text(json.dumps(results, indent=1))
failed = [r for r in results if not r["ok"]]
print(f"{'FAILED' if failed else 'PASSED'} {len(results) - len(failed)}/{len(results)} -> {RUN}")
sys.exit(1 if failed else 0)
