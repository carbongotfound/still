"""One real task through a real, signed-in agent app (uses a little of that plan): "open example.com and tell me its
title", then a follow-up that needs the same session. Run it by hand only.

Run: python tests/desktop/live.py artifacts/Still-QA/Still.exe claude [model]
"""
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import launch, rpc, send, text, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXE = Path(sys.argv[1]).resolve()
AGENT = sys.argv[2]
MODEL = sys.argv[3] if len(sys.argv) > 3 else {"claude": "haiku"}.get(AGENT, "")
RUN = ROOT / "artifacts" / ("live-" + AGENT + "-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
PROFILE.mkdir(parents=True)
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AgentsEnabled": True, "AiHarness": AGENT},
    "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
result = {"agent": AGENT, "model": MODEL}
process = launch(EXE, PROFILE)
try:
    send(process, "aiToggle")
    send(process, "aiCheck")
    if MODEL:
        time.sleep(3)  # the model list loads in the background
        send(process, "aiAdvanced", on=True)  # without Advanced, the companion's mode picks the model
        send(process, "aiModel", harness=AGENT, model=MODEL)
    started = time.monotonic()
    send(process, "aiSend", text="Open example.com and tell me its title.")
    first = until(lambda: "Example Domain" in text(process) and not rpc(process, "shellEval", script="!!document.querySelector('[aria-label=Stop]')"), 240, 1)
    result["first_seconds"] = round(time.monotonic() - started, 1)
    chats = json.loads((PROFILE / "ai" / "chats.json").read_text())
    session = chats[0]["Session"]
    send(process, "aiSend", text="What was that title again? Reply with only the title.")
    until(lambda: json.loads((PROFILE / "ai" / "chats.json").read_text())[0]["Messages"][-1]["Role"] == "assistant"
          and len(json.loads((PROFILE / "ai" / "chats.json").read_text())[0]["Messages"]) > len(chats[0]["Messages"]) + 1, 240, 1)
    after = json.loads((PROFILE / "ai" / "chats.json").read_text())[0]
    result.update(first=bool(first), resumed=after["Session"] == session and after["Started"], answer=after["Messages"][-1]["Text"],
                  steps=[m["Text"] for m in after["Messages"] if m["Role"] == "tool"], error=rpc(process, "shellEval", script="document.querySelector('[role=alert]')?.innerText ?? ''"))
    result["passed"] = result["first"] and result["resumed"] and "Example Domain" in result["answer"]
    rpc(process, "capture", name="live.png")
    rpc(process, "quit")
    process.wait(timeout=15)
finally:
    if process.poll() is None:
        process.kill()
    (RUN / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), "\n->", RUN)
