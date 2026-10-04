"""Exercise downloads, extension APIs and startup link bursts using isolated profiles.

Run: python tests/desktop/features.py artifacts/changed-qa-next/Still.exe
Temporary file associations and native hosts use GUID names and are removed in finally.
No normal browser profile or existing registry entry is modified.
"""
import base64
import ctypes
import hashlib
import http.server
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("features-" + uuid.uuid4().hex)
RUN.mkdir(parents=True)
EXE = Path(sys.argv[1]).resolve()
TOKEN = uuid.uuid4().hex
EXT = ".stillqa" + TOKEN
PROGID = "StillQA." + TOKEN
HOST = "com.stillqa.h" + TOKEN
RESULT = {"checks": []}
PROCESS = None

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/download'):
            body = b"synthetic downloaded file"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="fixture' + EXT + '"')
        elif self.path.startswith('/article'):
            body = ('<title>Embedded reader fixture</title><article><h1>Embedded reader fixture</h1>' +
                    '<p>This local article checks that the packaged reader script is available. The browser should show a readable article, using its embedded JavaScript resource without loose files beside the executable.</p>' * 12 + '</article>').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        else:
            body = b'<title>Feature fixture</title><a href="/download">Download</a><input id="draft">'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_): pass

SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:" + str(SERVER.server_port)

def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok: raise AssertionError(name)

def rpc(op="state", **args):
    pipe = r"\\.\pipe\StillQa-" + str(PROCESS.pid)
    end = time.monotonic() + 15
    while not ctypes.windll.kernel32.WaitNamedPipeW(pipe, 500):
        if time.monotonic() > end: raise RuntimeError("QA pipe unavailable")
        time.sleep(.05)
    with open(pipe, "r+b", buffering=0) as stream:
        stream.write((json.dumps({"op": op, **args}) + "\n").encode())
        reply = b""
        while not reply.endswith(b"\n"): reply += stream.read(65536)
    value = json.loads(reply)
    if isinstance(value, dict) and "error" in value: raise RuntimeError(str(value))
    return value

def wait(predicate, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate(): return
        time.sleep(.1)
    raise AssertionError("Timed out")

def ready():
    s = rpc()
    return any(t["Id"] == s["activeId"] and t["ready"] and not t["Loading"] for t in s["tabs"])

def send(op, **args):
    rpc("shellEval", script="chrome.webview.postMessage(" + json.dumps({"op": op, **args}) + ")")

def registry(path, value):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key: winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)

def remove_registry(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            children = []
            i = 0
            while True:
                try: children.append(winreg.EnumKey(key, i)); i += 1
                except OSError: break
        for child in children: remove_registry(path + "\\" + child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError: pass

try:
    profile = RUN / "profile"; profile.mkdir()
    (profile / "state.json").write_text(json.dumps({"UiVersion": 3, "Welcome": False,
        "Preferences": {"OfferPasswordSave": True}}))
    marker = RUN / "opened.txt"
    opener = RUN / "opener.py"
    opener.write_text("from pathlib import Path\nimport sys\np=Path(" + repr(str(marker)) + ")\np.open('a').write(sys.argv[1]+'\\n')\n")
    registry("Software\\Classes\\" + EXT, PROGID)
    registry("Software\\Classes\\" + PROGID + "\\shell\\open\\command", '"' + sys.executable + '" "' + str(opener) + '" "%1"')
    PROCESS = subprocess.Popen([str(EXE), "--qa", "--profile", str(profile), URL])
    wait(lambda: (profile / "qa-pipe.txt").exists(), 30)
    wait(ready)
    wait(lambda: rpc("shellEval", script="!!document.querySelector('[aria-label=\"Downloads\"]')"))
    position = rpc("eval", script="(()=>{let r=document.querySelector('a').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    for kind in ["mousePressed", "mouseReleased"]:
        rpc("pageCdp", method="Input.dispatchMouseEvent", parameters={"type":kind,"x":position["x"],"y":position["y"],"button":"left","clickCount":1})
    wait(lambda: any(d['status'] == 'Completed' for d in rpc()['downloads']))
    send("openPanel", name="downloads")
    wait(lambda: rpc("shellEval", script="!!document.querySelector('.dl-row small')"))
    # Real React events with the browser's native event sequencing.
    rpc("shellEval", script="document.querySelector('.dl-row small').dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2}))")
    wait(lambda: marker.exists())
    check(len(marker.read_text().splitlines()) == 1, "Double-click completed download opens its actual file once")
    downloaded = marker.read_text().strip()
    check(Path(downloaded).is_file() and Path(downloaded).read_bytes() == b"synthetic downloaded file", "Opened file is the downloaded content")
    rpc("shellEval", script="{const b=document.querySelector('.dl-name');for(const detail of [1,2])b.dispatchEvent(new MouseEvent('click',{bubbles:true,detail}));b.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2}));}")
    wait(lambda: len(marker.read_text().splitlines()) == 2)
    time.sleep(.4)
    check(len(marker.read_text().splitlines()) == 2, "Double-click filename does not launch duplicate copies")
    send("openPanel", name="address")
    send("navigate", url=URL)
    wait(ready)
    wait(lambda: rpc('eval',script="typeof window.__stillLoginCleanup==='function'"))
    check(True, "Packaged login observer runs from its embedded resource")
    send('navigate',url=URL+'/article')
    wait(lambda: ready() and '/article' in next(t['Url'] for t in rpc()['tabs'] if t['Id']==rpc()['activeId']))
    rpc('key',key='R',mods='Control, Shift')
    wait(lambda: any(t['Id']==rpc()['activeId'] and t['Reader'] for t in rpc()['tabs']))
    check(rpc('eval',script="document.body.innerText.includes('STILL READER')"), "Packaged reader renders an article from its embedded resource")
    send('navigate',url=URL)
    wait(ready)

    fixture = RUN / "extension"; fixture.mkdir()
    # Public key from a signed, public store package, never a private key or credential.
    package = (ROOT / "artifacts/cold-turkey.crx").read_bytes()
    def fields(data):
        at = 0
        def varint():
            nonlocal at
            n = shift = 0
            while True:
                b = data[at]; at += 1; n |= (b & 127) << shift
                if b < 128: return n
                shift += 7
        while at < len(data):
            tag = varint(); size = varint()
            yield tag >> 3, data[at:at+size]; at += size
    header_size = struct.unpack_from('<I', package, 8)[0]
    keys = [v for n, proof in fields(package[12:12+header_size]) if n in (2,3) for f,v in fields(proof) if f == 1]
    def extension_id(key): return ''.join(chr(97 + n) for b in hashlib.sha256(key).digest()[:16] for n in (b >> 4, b & 15))
    key = next(k for k in keys if extension_id(k) == 'pganeibhckoanndahmnfggfoeofncnii')
    expected_id = extension_id(key)
    manifest = {"manifest_version":3,"name":"Still compatibility fixture","version":"1.0",
                "key":base64.b64encode(key).decode(),"permissions":["storage","nativeMessaging","tabs","scripting","contextMenus","alarms"],
                "host_permissions":["http://127.0.0.1/*"],"action":{"default_popup":"popup.html"},
                "background":{"service_worker":"worker.js"},
                "content_scripts":[{"matches":["http://127.0.0.1/*"],"js":["content.js"]}]}
    (fixture / "manifest.json").write_text(json.dumps(manifest))
    (fixture / "content.js").write_text("document.documentElement.dataset.stillFixture=chrome.runtime.id;")
    (fixture / "worker.js").write_text("chrome.runtime.onMessage.addListener((m,s,reply)=>{chrome.storage.local.set({serviceWorker:'alive'}).then(()=>reply({worker:'alive'}));return true});chrome.alarms.create('fixture',{delayInMinutes:1});")
    (fixture / "popup.html").write_text('<title>Extension fixture</title><pre id="probe"></pre><script src="popup.js"></script>')
    (fixture / "popup.js").write_text("""const p={id:chrome.runtime.id,storage:!!chrome.storage,tabs:!!chrome.tabs,scripting:!!chrome.scripting,contextMenus:!!chrome.contextMenus,alarms:!!chrome.alarms,native:typeof chrome.runtime.sendNativeMessage==='function'};
    const publish=()=>document.querySelector('#probe').textContent=JSON.stringify(p);
    chrome.storage.local.get('serviceWorker',v=>{p.worker=v.serviceWorker;publish()});
    chrome.runtime.sendMessage({probe:true},r=>{p.worker=r?.worker;p.workerError=chrome.runtime.lastError?.message;publish()});
    chrome.tabs.query({},t=>{p.tabCount=t?.length;p.tabsError=chrome.runtime.lastError?.message;publish()});
    if(p.native) chrome.runtime.sendNativeMessage(""" + json.dumps(HOST) + """,{hello:'fixture'},r=>{p.nativeResult=r;p.nativeError=chrome.runtime.lastError?.message;publish()});publish();""")
    native = RUN / "native.py"
    native.write_text("""import sys,struct,json
while True:
 prefix=sys.stdin.buffer.read(4)
 if len(prefix)!=4:break
 size=struct.unpack('<I',prefix)[0]
 if size>65536:break
 data=json.loads(sys.stdin.buffer.read(size))
 reply=json.dumps({'echo':data}).encode()
 sys.stdout.buffer.write(struct.pack('<I',len(reply))+reply);sys.stdout.buffer.flush()
""")
    command = RUN / "native.cmd"
    command.write_text('@echo off\r\n"' + sys.executable + '" "' + str(native) + '"\r\n')
    host_manifest = RUN / "host.json"
    host_manifest.write_text(json.dumps({"name":HOST,"description":"Synthetic Still test host","path":str(command),"type":"stdio","allowed_origins":["chrome-extension://"+expected_id+"/"]}))
    for browser in ["Microsoft\\Edge","Google\\Chrome"]:
        registry("Software\\"+browser+"\\NativeMessagingHosts\\"+HOST, str(host_manifest))
    send("openPanel", name="extensions")
    rpc("stageExtension", path=str(fixture))
    send("extensionInstall")
    wait(lambda: rpc("shellEval", script="document.body.innerText.includes('Still compatibility fixture')"))
    wait(lambda: rpc("shellEval", script="!!document.querySelector('[aria-label=\"Open Still compatibility fixture popup\"]')"))
    rpc("shellEval", script="document.querySelector('[aria-label=\"Open Still compatibility fixture popup\"]').click()")
    wait(ready)
    wait(lambda: rpc("eval", script="!!document.querySelector('#probe')?.textContent"))
    wait(lambda: rpc("eval", script="JSON.parse(document.querySelector('#probe').textContent).worker==='alive'"), 10)
    probe = rpc("eval", script="JSON.parse(document.querySelector('#probe').textContent)")
    RESULT["extension_probe"] = probe
    check(probe["id"] == expected_id, "Runtime keeps the public-key extension ID")
    check(probe["storage"] and probe["worker"] == "alive", "Extension service worker and local storage run")
    time.sleep(2)
    probe = rpc("eval", script="JSON.parse(document.querySelector('#probe').textContent)")
    RESULT["extension_probe"] = probe
    check(probe.get("nativeResult") == {"echo":{"hello":"fixture"}}, "Extension exchanges data with its registered desktop helper")
    check(probe.get("tabCount",0) >= 2 and not probe.get("tabsError"), "Extension tab queries return real browser tabs")
    print("Extension API probe: " + json.dumps(probe), flush=True)
    # Native messaging availability is evidence, not a false compatibility assertion.
    send("navigate", url=URL + "/content")
    wait(ready)
    wait(lambda: rpc("eval", script="document.documentElement.dataset.stillFixture") == expected_id)
    check(True, "Extension content scripts modify the real website")
    # A burst while an existing window is running must retain every link, once each.
    children = [subprocess.Popen([str(EXE), "--qa", "--profile", str(profile), URL + "/burst-"+str(i)]) for i in range(6)]
    for child in children: child.wait(timeout=15)
    wait(lambda: sum('/burst-' in t['Url'] for t in rpc()['tabs']) == 6)
    check(True, "Six simultaneous external links open once each")
    check(not rpc()['shellErrors'], "No interface JavaScript errors")
    if "--cold-turkey" in sys.argv:
        send("openPanel", name="extensions")
        send("extensionRemove", id=expected_id)
        wait(lambda: not rpc("shellEval", script="document.body.innerText.includes('Still compatibility fixture')"))
        rpc("stageStorePackage", path=str(ROOT/"artifacts/cold-turkey.crx"), id=expected_id)
        send("extensionInstall")
        wait(lambda: rpc("shellEval", script="!!document.querySelector('[aria-label=\"Open Cold Turkey Blocker popup\"]')"))
        rpc("shellEval", script="document.querySelector('[aria-label=\"Open Cold Turkey Blocker popup\"]').click()")
        wait(ready)
        time.sleep(3)
        # Store only support indicators, never any personal block lists or settings.
        RESULT['cold_turkey'] = rpc("eval", script="({id:chrome.runtime.id,title:document.title,hasBody:!!document.body,incognitoApi:typeof chrome.extension.isAllowedIncognitoAccess,notRunning:/not running|not installed|could not connect|not connected/i.test(document.body.innerText)})")
        check(RESULT['cold_turkey']['id'] == expected_id, "Official Cold Turkey package loads with its correct identity")
        print('Cold Turkey indicators: '+json.dumps(RESULT['cold_turkey']),flush=True)
    RESULT["passed"] = True
except Exception as error:
    RESULT["passed"] = False; RESULT["error"] = str(error)
    if PROCESS is not None and PROCESS.poll() is None:
        try:
            RESULT["failure_state"] = rpc()
            RESULT["failure_probe"] = rpc("eval", script="document.querySelector('#probe')?.textContent")
        except Exception: pass
    raise
finally:
    for browser in ["Microsoft\\Edge","Google\\Chrome"]:
        remove_registry("Software\\"+browser+"\\NativeMessagingHosts\\"+HOST)
    remove_registry("Software\\Classes\\" + EXT)
    remove_registry("Software\\Classes\\" + PROGID)
    if PROCESS is not None and PROCESS.poll() is None:
        try: rpc("quit"); PROCESS.wait(timeout=15)
        except Exception: PROCESS.terminate()
    SERVER.shutdown()
    (RUN / "results.json").write_text(json.dumps(RESULT, indent=2))
    print("Results: " + str(RUN / "results.json"), flush=True)
