"""Closing a tab closes that tab and no other: a quick double-click on a tab's X closes just that tab (the second click
lands on its row while it animates out and names a tab that is gone, which closes nothing, not the active tab), and a
close with no id still closes the active tab, as Ctrl+W does. And a tab group shown in two places (P2 between two of
its tabs) loses no row: closing its first tab leaves the strip showing exactly the tabs that are open, no copies.

Run: python tests/desktop/tabclose.py artifacts/Still-QA/Still.exe
Out: artifacts/tabclose-*/result.json
"""
import http.server
import json
from pathlib import Path
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, rpc, send  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("tabclose-" + uuid.uuid4().hex[:8])
CHECKS = []


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"<!doctype html><title>Page {self.path}</title>".encode()
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def check(ok, name):
    CHECKS.append({"name": name, "passed": bool(ok)}); print(("PASS " if ok else "FAIL ") + name)


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
threading.Thread(target=server.serve_forever, daemon=True).start()
profile = RUN / "profile"; profile.mkdir(parents=True)
seeded = [{"Id": f"s{i}", "Title": f"P{i}", "Url": f"data:text/html,<title>P{i}</title>", "Group": "g1" if i in (1, 3) else ""} for i in range(1, 6)]
(profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Width": 1280, "Height": 800},
    "Tabs": seeded, "ActiveId": "s2", "Groups": [{"Id": "g1", "Name": "Work", "Color": "blue"}]}))
p = launch(EXE, profile)
try:
    strip = lambda: js(p, "[...document.querySelectorAll('.tab-row')].map(r => r.getAttribute('data-tab-id'))") or []  # noqa: E731
    open_ids = lambda: [t["Id"] for t in rpc(p).get("tabs", [])]  # noqa: E731
    for _ in range(50):
        if len(strip()) == 5:
            break
        time.sleep(.2)
    time.sleep(.6)
    send(p, "closeTab", id="s1"); time.sleep(1); send(p, "closeTab", id="s4"); time.sleep(1)
    check(strip() == open_ids() == ["s2", "s3", "s5"], f"a group in two places: closing its first tab leaves no copy on screen ({strip()} on screen, {open_ids()} open)")
    for i in range(5):
        send(p, "new", url=f"http://127.0.0.1:{server.server_address[1]}/{i}")
    time.sleep(1.5)
    ids = lambda: [t["Id"] for t in rpc(p).get("tabs", [])]
    before, active = ids(), rpc(p).get("activeId")
    target = next(t for t in before if t != active)
    # A double-click on a tab's X: the second click lands on its row while it animates out and asks to close a tab that is gone.
    send(p, "closeTab", id=target); send(p, "closeTab", id=target); time.sleep(1)
    check([t for t in before if t not in ids()] == [target] and rpc(p).get("activeId") == active, "closing a tab twice (a double-click on its X) closes only that tab")
    before = ids()
    active = rpc(p).get("activeId")
    send(p, "closeTab"); time.sleep(.8)
    check(active not in ids() and len(ids()) == len(before) - 1, "a close with no id closes the active tab")
finally:
    p.kill()
(RUN / "result.json").write_text(json.dumps(CHECKS, indent=1))
print(f"{sum(c['passed'] for c in CHECKS)}/{len(CHECKS)} passed")
sys.exit(0 if all(c["passed"] for c in CHECKS) else 1)
