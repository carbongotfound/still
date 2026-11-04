"""An AI app Still started never outlives a Still that crashed: Windows ends it with Still (a Job Object), the Mac at the
next start (the runs it lists under the profile). Nothing else is touched: a listed number now used by another process stays.

Run: python tests/desktop/orphans.py artifacts/Still-QA/Still.exe
Out: artifacts/orphans-*/
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
import qa

EXE = Path(sys.argv[1]).resolve()
RUN = Path(__file__).resolve().parents[2] / "artifacts" / f"orphans-{uuid.uuid4().hex[:8]}"
FAKE = r'''
import json, os, sys, time
if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
open(os.environ["ORPHANS_PID"], "w").write(str(os.getpid()))
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-1"}), flush=True)
time.sleep(600)  # a long run, still going when Still dies
'''
results = []


def check(ok, name):
    results.append({"name": name, "ok": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def alive(pid):
    if qa.MAC:
        return subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0
    return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout


shutil.rmtree(RUN, ignore_errors=True)
PROFILE = RUN / "profile"; PROFILE.mkdir(parents=True); (PROFILE / "agents").mkdir()
bin_ = RUN / "bin"; bin_.mkdir(); (bin_ / "fake_agent.py").write_text(FAKE, encoding="utf-8"); qa.launcher(bin_ / "fakeagent", bin_ / "fake_agent.py")
(PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(bin_ / "fakeagent"),
    "detect": ["status"], "expect": "signed in", "run": ["run"], "output": "stream-json"}))
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}],
    "Preferences": {"AiHarness": "fake", "AgentsEnabled": True, "Companions": qa.CREW}}))
marker = RUN / "agent.pid"
env = dict(os.environ, ORPHANS_PID=str(marker))
bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])

process = qa.launch(EXE, PROFILE, env)
try:
    qa.send(process, "aiSend", text="Take your time.", home=True, companion="maya")
    check(qa.until(lambda: marker.exists() and marker.read_text(), 20), "The AI app is running")
    agent = int(marker.read_text())
    listed = PROFILE / "running-ai.txt"
    if qa.MAC:
        check(listed.exists() and str(agent) in listed.read_text().split(), "The Mac lists the run under the profile")
        # A crash can leave a number the system has since given to something else: Still must leave that one alone.
        listed.write_text(listed.read_text() + f"\n{bystander.pid} 12345")
finally:
    process.kill(); process.wait(timeout=20)  # a crash: no chance to end anything
(PROFILE / "qa-pipe.txt").unlink(missing_ok=True)

process = qa.launch(EXE, PROFILE, env)
try:
    check(qa.until(lambda: not alive(agent), 10), "After the crash, the AI app is gone by the next start")
    check(bystander.poll() is None and alive(bystander.pid), "Another process with a listed number is never touched")
    if qa.MAC:
        check(not (PROFILE / "running-ai.txt").exists(), "The list is cleared")
finally:
    try: qa.rpc(process, "quit")
    except RuntimeError: pass
    try: process.wait(timeout=20)
    except Exception: process.kill()
    bystander.kill()
    if alive(agent): subprocess.run(["kill", "-9", str(agent)] if qa.MAC else ["taskkill", "/F", "/PID", str(agent)], capture_output=True)

(RUN / "results.json").write_text(json.dumps(results, indent=1))
failed = [r for r in results if not r["ok"]]
print(f"{'FAILED' if failed else 'PASSED'} {len(results) - len(failed)}/{len(results)} -> {RUN}")
sys.exit(1 if failed else 0)
