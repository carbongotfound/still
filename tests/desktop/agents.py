"""Regression checks for the controls other AI apps use: --cli, --mcp, approval, block, the switch, private tabs, temp.

Run: python tests/desktop/agents.py artifacts/Still-QA/Still.exe [--update-snapshot]
`--cli` always talks to the default profile, so only its offline behavior (help, as= required) runs here;
the rest goes through `--mcp --profile`, which shares the same call path (McpServer.Call) with a fresh profile.
"""
import http.server
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("agents-" + uuid.uuid4().hex)
RUN.mkdir(parents=True)
EXE = Path(sys.argv[1]).resolve()
SNAPSHOT = Path(__file__).with_name("fixtures") / "cli-help.txt"
RESULT = {"exe": str(EXE), "checks": []}

def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("<!doctype html><title>Agent fixture " + self.path + "</title><p>" + self.path).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass

SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:" + str(SERVER.server_port)

from qa import MAC, rpc, until_started  # noqa: E402  (the Windows pipe, or the Mac's socket)

def send(process, op, **args):
    rpc(process, "shellEval", script="window.chrome.webview.postMessage(" + json.dumps({"op": op, **args}) + ")")

def shell_text(process):
    return rpc(process, "shellEval", script="document.body.innerText")

def until(predicate, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.2)
    return None

from mcp_client import Mcp as McpClient, call_async  # noqa: E402

def Mcp(name, profile):
    return McpClient(EXE, name, profile)

def kill_qa_windows():
    """Temp windows are started by Still itself; close every process of this QA executable."""
    if sys.platform == "darwin":
        subprocess.run(["pkill", "-9", "-f", str(EXE)], capture_output=True)
        return
    path = str(EXE).replace("'", "''")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Get-CimInstance Win32_Process -Filter \"Name='Still.exe'\" | Where-Object {{ $_.ExecutablePath -eq '{path}' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"],
                   capture_output=True)

process = None
clients = []
try:
    # --cli: offline behavior only (it always targets the default profile).
    helped = subprocess.run([str(EXE), "--cli", "help"], capture_output=True, timeout=60)
    text = helped.stdout.decode("utf-8").replace("\r\n", "\n")
    if "--update-snapshot" in sys.argv or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(text, encoding="utf-8", newline="\n")
        print("Wrote " + str(SNAPSHOT))
    snapshot = SNAPSHOT.read_text(encoding="utf-8")
    if sys.platform == "darwin":  # the same help, under the Mac app's name
        snapshot = snapshot.replace("Usage: Still.exe ", "Usage: Still ", 1)
    check(helped.returncode == 0 and text == snapshot, "--cli help output is unchanged")
    anonymous = subprocess.run([str(EXE), "--cli", "list_tabs"], capture_output=True, timeout=60)
    check(anonymous.returncode == 2 and "say who you are with as=" in anonymous.stdout.decode("utf-8"), "--cli without as= is refused")

    profile = RUN / "profile"
    profile.mkdir()
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AgentsEnabled": True},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": URL + "/home"}], "ActiveId": "home"}))
    process = subprocess.Popen([str(EXE), "--qa", "--profile", str(profile), "--profiles-root", str(profile)])
    until_started(process)
    until(lambda: any(t["ready"] for t in rpc(process)["tabs"]), 30)

    # A new caller is asked about; Allow lets it in.
    first = Mcp("Probe One", profile); clients.append(first)
    pending = call_async(first, "list_tabs")
    check(until(lambda: "Probe One" in shell_text(process)), "Approval bar appears for a new caller")
    send(process, "agentAnswer", allow=True)
    ok, text = pending.get(timeout=60)
    if not ok and "Allow" in text:  # the user counted as away: the agent was told to call again
        ok, text = first.call("list_tabs")
    check(ok and "/home" in text, "Allowed caller can list tabs")

    # Private tabs never reach agents.
    send(process, "new", url=URL + "/private-tab", private=True)
    until(lambda: any(t["Private"] for t in rpc(process)["tabs"]))
    ok, text = first.call("list_tabs")
    check(ok and "/home" in text and "private-tab" not in text, "Private tabs are hidden from list_tabs")

    # "temp" opens a throwaway window the caller is already allowed in.
    ok, text = first.call("open_tab", seconds=90, url=URL + "/temp-tab", profile="temp")
    listed_ok, listed = first.call("list_tabs", seconds=60, profile="temp")
    check(ok and listed_ok and "temp-tab" in listed, "profile=temp opens a temporary window")
    ok, text = first.call("list_tabs")
    check(ok and "temp-tab" not in text, "The temporary window is separate from the profile")

    # Block holds for the rest of the session.
    second = Mcp("Probe Two", profile); clients.append(second)
    pending = call_async(second, "list_tabs")
    until(lambda: "Probe Two" in shell_text(process))
    send(process, "agentAnswer", allow=False)
    ok, text = pending.get(timeout=60)
    if not ok and "Allow" in text:  # the user counted as away: the answer applies to the next call
        ok, text = second.call("list_tabs", seconds=20)
    check(not ok and "blocked this agent" in text, "Block refuses the caller")
    until(lambda: "Probe Two" not in shell_text(process), 5)  # the bar's exit animation
    started = time.monotonic()
    ok, text = second.call("list_tabs", seconds=20)
    check(not ok and "blocked this agent" in text and time.monotonic() - started < 5 and "Probe Two" not in shell_text(process),
          "Block persists for the session without asking again")

    # Settings' prompt for other agent apps names this system's shell and how to run Still from it.
    send(process, "openPanel", name="settings", value="models")
    read = "(() => { const d = document.querySelector('#set-dev details'); if (!d) return ''; d.open = true; return d.querySelectorAll('pre')[1]?.innerText ?? '' })()"
    prompt = until(lambda: rpc(process, "shellEval", script=read), 10) or ""
    shell, other, run = ("Terminal", "PowerShell", '"') if MAC else ("PowerShell", "Terminal", '& "')
    lines = prompt.splitlines()
    check(f"from the terminal ({shell})" in prompt and other not in prompt and len(lines) > 1 and lines[1].startswith(run) and '" --cli <tool> as=' in lines[1],
          f"The terminal prompt in Settings is for {shell} ({lines[:2]})")

    # The per-profile switch refuses everyone with the existing message.
    send(process, "preference", key="agents", value="false")
    time.sleep(1)
    ok, text = first.call("list_tabs")
    check(not ok and text.startswith("AI control is turned off."), "Switch off refuses agents with the existing message")
    check(not rpc(process)["shellErrors"], "No interface JavaScript errors")
    rpc(process, "quit")
    process.wait(timeout=15)
except Exception as error:
    RESULT["error"] = repr(error)
    print("ERROR " + repr(error), flush=True)
finally:
    for client in clients:
        client.close()
    if process and process.poll() is None:
        process.kill()
    kill_qa_windows()
    SERVER.shutdown()
    RESULT["passed"] = "error" not in RESULT and all(c["passed"] for c in RESULT["checks"])
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
    print(("PASSED " if RESULT["passed"] else "FAILED ") + str(sum(c["passed"] for c in RESULT["checks"])) + "/" + str(len(RESULT["checks"])), flush=True)
    sys.exit(0 if RESULT["passed"] else 1)
