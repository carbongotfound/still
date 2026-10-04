"""Windows/WebView2 regression checks. Uses only fresh profiles and loopback fixtures.

Run: python tests/desktop/performance.py path/to/Still.exe [--baseline]
Results and profiles are retained in ignored artifacts/performance-* directories.
"""
import ctypes
from ctypes import wintypes
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("performance-" + uuid.uuid4().hex)
RUN.mkdir(parents=True)
BASELINE = "--baseline" in sys.argv
EXE = Path(sys.argv[1]).resolve()
RESULT = {"baseline": BASELINE, "exe": str(EXE), "checks": []}

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'''<!doctype html><title>Still performance fixture</title>
        <input id="draft"><textarea id="notes"></textarea><button id="push" onclick="history.pushState({},'', '?step=2')">History</button>
        <script>window.loads=(Number(sessionStorage.loads)||0)+1;sessionStorage.loads=loads;
        window.marker=Math.random();window.buffer=new Uint8Array(32*1024*1024);buffer.fill(7);
        window.ticks=0;setInterval(()=>ticks++,100);</script>'''
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
def site(index):
    return "http://site" + str(index) + ".localhost:" + str(SERVER.server_port)

def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        raise AssertionError(name)

def rpc(process, op="state", **args):
    pipe = r"\\.\pipe\StillQa-" + str(process.pid)
    end = time.monotonic() + 15
    while not ctypes.windll.kernel32.WaitNamedPipeW(pipe, 500):
        if time.monotonic() > end or process.poll() is not None:
            raise RuntimeError("QA pipe unavailable")
        time.sleep(.05)
    with open(pipe, "r+b", buffering=0) as stream:
        stream.write((json.dumps({"op": op, **args}) + "\n").encode())
        response = b""
        while not response.endswith(b"\n"):
            part = stream.read(65536)
            if not part:
                raise RuntimeError("QA pipe closed")
            response += part
    value = json.loads(response)
    if isinstance(value, dict) and "error" in value:
        raise RuntimeError(str(value))
    return value

def wait(process, predicate, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        state = rpc(process)
        if predicate(state):
            return state
        time.sleep(.1)
    raise AssertionError("Timed out: " + json.dumps(state)[:1200])

def active_ready(state):
    return any(t["Id"] == state["activeId"] and t["ready"] and not t["Loading"] for t in state["tabs"])

def send(process, op, **args):
    rpc(process, "shellEval", script="window.chrome.webview.postMessage(" + json.dumps({"op": op, **args}) + ")")

class ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD), ("exe", wintypes.WCHAR * 260)]

class MemoryCounters(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in
                ("peak", "working", "pagedPeak", "paged", "nonpagedPeak", "nonpaged", "pagefile", "pagefilePeak", "private")]

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]

def memory(pid):
    snap = kernel.CreateToolhelp32Snapshot(2, 0)
    entry = ProcessEntry(); entry.dwSize = ctypes.sizeof(entry)
    parents = {}
    try:
        more = kernel.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            parents[entry.pid] = entry.parent
            more = kernel.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snap)
    owned = {pid}
    while True:
        children = {p for p, parent in parents.items() if parent in owned}
        if children <= owned:
            break
        owned |= children
    working = private = count = 0
    for child in owned:
        handle = kernel.OpenProcess(0x410, False, child)
        if not handle:
            continue
        try:
            counters = MemoryCounters(); counters.size = ctypes.sizeof(counters)
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.size):
                count += 1; working += counters.working; private += counters.private
        finally:
            kernel.CloseHandle(handle)
    return {"working_mb": round(working / 1048576, 1), "private_mb": round(private / 1048576, 1), "processes": count}

process = None
try:
    profile = RUN / "profile"
    profile.mkdir()
    (profile / "state.json").write_text(json.dumps({"UiVersion": 3, "Welcome": False,
        "Preferences": {"MemorySaver": True}, "Tabs": [{"Id": "restored", "Title": "Restored", "Url": URL + "/restored"}], "ActiveId": "restored"}))
    started = time.monotonic()
    process = subprocess.Popen([str(EXE), "--qa", "--profile", str(profile), URL + "/launch"])
    for _ in range(300):
        if (profile / "qa-pipe.txt").exists():
            break
        if process.poll() is not None:
            raise RuntimeError("App exited: " + str(process.returncode))
        time.sleep(.05)
    state = wait(process, active_ready)
    RESULT["startup_stages"] = state.get("startup")
    RESULT["startup_seconds"] = round(time.monotonic() - started, 3)
    check(len(state["tabs"]) == 2 and not state["tabs"][0]["ready"], "Launch link leaves restored tabs unloaded")
    links = []
    for i in range(3):
        started = time.monotonic()
        child = subprocess.Popen([str(EXE), "--qa", "--profile", str(profile), site(i) + "/outside-" + str(i)])
        state = wait(process, lambda s: active_ready(s) and any(t["Id"] == s["activeId"] and ("outside-" + str(i)) in t["Url"] for t in s["tabs"]))
        links.append(round(time.monotonic() - started, 3))
        child.wait(timeout=10)
        check(child.returncode == 0, "External link sender exits successfully " + str(i))
    RESULT["link_seconds"] = links
    draft_tab = state["activeId"]
    marker = rpc(process, "eval", script="document.querySelector('#draft').value='unsaved draft';document.querySelector('#notes').value='private notes';document.querySelector('#push').click();document.cookie='stillFixture=kept;path=/;max-age=3600';localStorage.setItem('stillFixture','kept');window.marker")
    for i in range(3):
        send(process, "new", url=site(i+3) + "/memory-" + str(i))
        state = wait(process, lambda s: active_ready(s) and any(t["Id"] == s["activeId"] and ("memory-" + str(i)) in t["Url"] for t in s["tabs"]))
    RESULT["loaded_memory"] = memory(process.pid)
    print("Loaded memory: " + str(RESULT["loaded_memory"]), flush=True)
    time.sleep(75)
    state = rpc(process)
    RESULT["idle_memory"] = memory(process.pid)
    print("Idle memory: " + str(RESULT["idle_memory"]), flush=True)
    if not BASELINE:
        check(all(t.get("suspended") for t in state["tabs"] if t["ready"] and t["Id"] != state["activeId"]), "Idle background renderers suspend")
        check(RESULT["idle_memory"]["working_mb"] < RESULT["loaded_memory"]["working_mb"] * .8, "Resident memory drops by at least 20 percent")
        # Keep the activity check separate from the idle-page benchmark: a live video/call
        # can share a renderer with sleeping tabs, which intentionally prevents its trim.
        send(process,"new",url=site(8)+"/media")
        state=wait(process,lambda s:active_ready(s) and any(t["Id"]==s["activeId"] and "/media" in t["Url"] for t in s["tabs"]))
        media_tab=state["activeId"]
        rpc(process,"eval",script="window.peer=new RTCPeerConnection();let canvas=document.createElement('canvas');canvas.width=32;canvas.height=32;let video=document.createElement('video');video.muted=true;video.srcObject=canvas.captureStream(1);document.body.append(video);video.play();")
        send(process,"new",url=site(9)+"/foreground")
        state=wait(process,lambda s:active_ready(s) and any(t["Id"]==s["activeId"] and "/foreground" in t["Url"] for t in s["tabs"]))
        time.sleep(75)
        state=rpc(process)
        check(not next(t for t in state['tabs'] if t['Id']==media_tab)['suspended'], "Media and WebRTC background tab stays awake")
        RESULT['media_memory']=memory(process.pid)
    send(process, "select", id=draft_tab)
    wait(process, lambda s: active_ready(s) and s["activeId"] == draft_tab)
    kept = rpc(process, "eval", script="({draft:document.querySelector('#draft').value,notes:document.querySelector('#notes').value,marker:window.marker,loads:window.loads,step:location.search,cookie:document.cookie.includes('stillFixture=kept'),storage:localStorage.getItem('stillFixture')})")
    check(kept["draft"] == "unsaved draft" and kept["notes"] == "private notes" and kept["marker"] == marker and kept["loads"] == 1 and kept["step"] == "?step=2", "Forms, JavaScript state and navigation history survive wake without reload")
    check(kept['cookie'] and kept['storage']=='kept', "Cookies and local storage survive wake")
    if not BASELINE:
        send(process,'preference',key='memory',value='false')
        state=wait(process,lambda s:all(not t.get('suspended') for t in s['tabs']))
        check(all(t['memory']=='Normal' for t in state['tabs'] if t['ready']), "Disabling memory saver resumes every tab at normal target")
    check(not rpc(process)["shellErrors"], "No interface JavaScript errors")
    rpc(process, "quit")
    process.wait(timeout=15)
    saved = json.loads((profile / "state.json").read_text(encoding="utf-8-sig"))
    check(any(t["Id"] == draft_tab for t in saved["Tabs"]), "Session saves tabs on exit")
    RESULT["passed"] = True
except Exception as error:
    RESULT["passed"] = False
    RESULT["error"] = str(error)
    raise
finally:
    (RUN / "results.json").write_text(json.dumps(RESULT, indent=2))
    print("Results: " + str(RUN / "results.json"), flush=True)
    if process is not None and process.poll() is None:
        try:
            rpc(process, "quit")
            process.wait(timeout=10)
        except Exception:
            process.terminate()
    SERVER.shutdown()
