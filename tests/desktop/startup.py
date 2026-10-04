"""Compare opening a closed app, first visible window, and running-instance link dispatch.

Run with two QA executables: python tests/desktop/startup.py baseline.exe changed.exe
Runs are sequential; each app gets its own isolated profile and only loopback traffic.
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
RUN = ROOT / "artifacts" / ("startup-" + uuid.uuid4().hex); RUN.mkdir(parents=True)
RESULT = []
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'<title>Startup fixture</title><input id="draft">'
        self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass
SERVER = http.server.ThreadingHTTPServer(('127.0.0.1',0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:' + str(SERVER.server_port)
def rpc(p, op='state', **args):
    pipe = r'\\.\pipe\StillQa-' + str(p.pid)
    end = time.monotonic() + 15
    while not ctypes.windll.kernel32.WaitNamedPipeW(pipe,500):
        if p.poll() is not None or time.monotonic()>end: raise RuntimeError('No QA pipe')
        time.sleep(.05)
    with open(pipe,'r+b',buffering=0) as f:
        f.write((json.dumps({'op':op,**args})+'\n').encode()); data=b''
        while not data.endswith(b'\n'): data+=f.read(65536)
    return json.loads(data)
def visible(pid):
    found=[]
    @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(hwnd, _):
        owner=wintypes.DWORD();ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and ctypes.windll.user32.IsWindowVisible(hwnd):found.append(hwnd)
        return True
    ctypes.windll.user32.EnumWindows(visit,0)
    return bool(found)
def ready(p, url):
    s=rpc(p)
    ok=any(t['Id']==s['activeId'] and t['ready'] and not t['Loading'] and url in t['Url'] for t in s['tabs'])
    return ok and rpc(p,'shellEval',script="!!document.querySelector('[aria-label=\"Downloads\"]')")
def wait(fn, seconds=40):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if fn():return
        time.sleep(.03)
    raise AssertionError('Timed out')
process=None
try:
    for index, arg in enumerate(a for a in sys.argv[1:] if not a.startswith('--')):
        exe=Path(arg).resolve(); profile=RUN/('profile-'+str(index));profile.mkdir()
        (profile/'state.json').write_text(json.dumps({'UiVersion':3,'Welcome':False}))
        samples=[]
        for cycle in range(4):
            url=URL+'/closed-'+str(cycle)
            environment=os.environ.copy()
            if '--cold-bundle' in sys.argv: environment['DOTNET_BUNDLE_EXTRACT_BASE_DIR']=str(RUN/('bundle-'+str(index)))
            start=time.monotonic(); process=subprocess.Popen([str(exe),'--qa','--profile',str(profile),url],env=environment)
            wait(lambda:visible(process.pid)); shown=time.monotonic()-start
            wait(lambda:(profile/'qa-pipe.txt').exists() and (profile/'qa-pipe.txt').read_text(encoding='utf-8-sig').endswith(str(process.pid)))
            wait(lambda:ready(process,url)); usable=time.monotonic()-start
            s=rpc(process); samples.append({'cycle':cycle,'window_seconds':round(shown,3),'usable_seconds':round(usable,3),'stages':s.get('startup')})
            print(str(index)+' / '+str(cycle)+': '+json.dumps(samples[-1]),flush=True)
            link=URL+'/running-'+str(cycle); start=time.monotonic()
            sender=subprocess.Popen([str(exe),'--qa','--profile',str(profile),link],env=environment);wait(lambda:ready(process,link));sender.wait(timeout=10)
            samples[-1]['link_seconds']=round(time.monotonic()-start,3)
            rpc(process,'quit');process.wait(timeout=15);process=None
            time.sleep(.5)
        RESULT.append({'exe':str(exe),'samples':samples})
finally:
    if process is not None and process.poll() is None:
        try:rpc(process,'quit');process.wait(timeout=10)
        except Exception:process.terminate()
    SERVER.shutdown(); (RUN/'results.json').write_text(json.dumps(RESULT,indent=2)); print('Results: '+str(RUN/'results.json'),flush=True)
