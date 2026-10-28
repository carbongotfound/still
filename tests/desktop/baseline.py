"""Performance baseline for docs/agentic/PERF.md: cold start, idle RAM with 1 and 10 tabs, tab-switch latency.

Run: python tests/desktop/baseline.py artifacts/Still-QA/Still.exe [runs]
Each run uses a fresh profile and loopback pages. Prints one JSON object with medians.
"""
import ctypes
from ctypes import wintypes
import http.server
import json
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
EXE = Path(sys.argv[1]).resolve()
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 3

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("<!doctype html><title>Baseline " + self.path + "</title><p>" + self.path).encode()
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
    return json.loads(response)

def until(predicate, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise TimeoutError("timed out")

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

def working_mb(pid):
    """Resident memory of Still and every process under it (WebView2 browser, renderers, GPU)."""
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
    while (children := {p for p, parent in parents.items() if parent in owned}) - owned:
        owned |= children
    total = 0
    for child in owned:
        handle = kernel.OpenProcess(0x410, False, child)
        if handle:
            counters = MemoryCounters(); counters.size = ctypes.sizeof(counters)
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.size):
                total += counters.working
            kernel.CloseHandle(handle)
    return round(total / 1048576, 1)

def ready(process, tab):
    return any(t["Id"] == tab and t["ready"] and not t["Loading"] for t in rpc(process)["tabs"])

def launch(tabs):
    profile = ROOT / "artifacts" / ("baseline-" + uuid.uuid4().hex) / "profile"
    profile.mkdir(parents=True)
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"MemorySaver": True},
        "Tabs": [{"Id": "t%d" % i, "Title": "Tab %d" % i, "Url": URL + "/tab-%d" % i} for i in range(tabs)], "ActiveId": "t0"}))
    started = time.monotonic()
    process = subprocess.Popen([str(EXE), "--qa", "--profile", str(profile), "--profiles-root", str(profile)])
    until(lambda: (profile / "qa-pipe.txt").exists() or process.poll() is not None)
    until(lambda: ready(process, "t0"))
    return process, time.monotonic() - started

# Shell-side timing: from asking for the tab until the strip shows it selected (native round trip + render).
SWITCH = """(() => { const id = %s, start = performance.now(); window.__switch = null;
 window.chrome.webview.postMessage({op: 'select', id});
 const tick = () => document.querySelector('.tab-row.is-selected[data-tab-id="' + id + '"]') ? (window.__switch = performance.now() - start) : requestAnimationFrame(tick);
 tick(); })()"""

def switch(process, tab):
    rpc(process, "shellEval", script=SWITCH % json.dumps(tab))
    return float(until(lambda: (v := rpc(process, "shellEval", script="String(window.__switch)")) != "null" and v, 10))

result = {"exe": str(EXE), "runs": RUNS, "cold_start_s": [], "idle_1_tab_mb": [], "idle_10_tabs_mb": [], "switch_ms": []}
try:
    for _ in range(RUNS):
        process, seconds = launch(1)
        result["cold_start_s"].append(round(seconds, 3))
        time.sleep(75)
        result["idle_1_tab_mb"].append(working_mb(process.pid))
        rpc(process, "quit"); process.wait(timeout=15)

        process, _ = launch(10)
        for i in range(1, 10):  # visit every tab once so all ten pages really load
            rpc(process, "shellEval", script="window.chrome.webview.postMessage(" + json.dumps({"op": "select", "id": "t%d" % i}) + ")")
            until(lambda: ready(process, "t%d" % i))
        for i in range(20):
            result["switch_ms"].append(round(switch(process, "t%d" % (i % 10)), 1))
        time.sleep(75)
        result["idle_10_tabs_mb"].append(working_mb(process.pid))
        rpc(process, "quit"); process.wait(timeout=15)
finally:
    SERVER.shutdown()
for key in ("cold_start_s", "idle_1_tab_mb", "idle_10_tabs_mb", "switch_ms"):
    result[key + "_median"] = statistics.median(result[key]) if result[key] else None
print(json.dumps(result, indent=2))
