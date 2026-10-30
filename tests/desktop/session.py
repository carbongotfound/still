"""Session restore with Composio's Get a key window, which Still opens itself: a temporary window that's never saved.
Each case quits Still and opens it again on the same profile: your tabs come back, the Composio tab doesn't.

  1. Get a key opens its own window, marked temporary; while it's open the saved session is still just your tabs.
  2. Close it, then quit: your tabs come back.
  3. Quit with it still open (your window closes first, the old bug): it closes with Still, and your tabs come back.
  4. Two normal windows and the Get a key window, closed one after another like the taskbar's Close all windows: both
     normal windows come back with their own tabs, and the Composio one doesn't.
  5. A private window open while your windows close (it closes last) doesn't replace them either.

Run: python tests/desktop/session.py artifacts/Still-QA/Still.exe
Out: artifacts/session-*/ (result.json)
"""
import http.server
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("session-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
CHECKS = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"<!doctype html><title>Page {self.path}</title><p>{self.path}".encode()
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{SERVER.server_port}"
KEYPAGE = BASE + "/composio-get-a-key"
ENV = {**os.environ, "STILL_QA_COMPOSIO_PAGE": KEYPAGE}


def check(ok, name):
    CHECKS.append({"name": name, "passed": bool(ok)}); print(("PASS " if ok else "FAIL ") + name, flush=True)


def start():
    return launch(EXE, PROFILE, ENV)


def windows(p):
    return rpc(p).get("windows") or []


def saved():
    """The saved session's tabs as (window, url), straight from state.json."""
    data = json.loads((PROFILE / "state.json").read_text(encoding="utf-8-sig"))
    return [(t.get("Window", 0), t["Url"]) for t in data["Tabs"]]


def get_a_key(p):
    before = len(windows(p))
    send(p, "pluginLink", to="key")
    until(lambda: len(windows(p)) == before + 1 and any(KEYPAGE in w["tabs"] for w in windows(p)), 15)
    return next((w for w in windows(p) if KEYPAGE in w["tabs"]), None)


def quit_and_wait(p, op="quit"):
    rpc(p, op)
    return until(lambda: p.poll() is not None, 30)


def urls(p):
    return [list(w["tabs"]) for w in windows(p)]


MINE = [BASE + "/inbox", BASE + "/notes"]
PROFILE.mkdir(parents=True)
(PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Width": 1280, "Height": 800},
    "Tabs": [{"Id": "t1", "Title": "Inbox", "Url": MINE[0]}, {"Id": "t2", "Title": "Notes", "Url": MINE[1]}], "ActiveId": "t1"}))

p = start()
try:
    # 1 and 2: open Get a key, close it, quit.
    popup = get_a_key(p)
    check(popup and popup.get("temporary") and popup["tabs"] == [KEYPAGE], f"Get a key opens Composio's page in its own temporary window ({popup})")
    time.sleep(1.5)  # past the save timer
    check([u for _, u in saved()] == MINE, f"While it's open, the saved session is still just your tabs ({saved()})")
    rpc(p, "closeWindow", id=popup["id"] if popup else "")
    check(until(lambda: len(windows(p)) == 1, 10) and urls(p) == [MINE], f"Closing it just closes it ({urls(p)})")
    check(quit_and_wait(p) and [u for _, u in saved()] == MINE, f"Quit: the session has your tabs and not Composio's ({saved()})")
    p = start()
    check(until(lambda: urls(p) == [MINE], 15), f"Opened again: your tabs are back, without Composio's ({urls(p)})")

    # 3: quit with the Get a key window still open: your window closes first, the popup after it.
    popup = get_a_key(p)
    check(popup and popup.get("temporary"), "Get a key opens again")
    check(quit_and_wait(p), "Quitting with it open closes it too, and Still exits")
    check([u for _, u in saved()] == MINE, f"The popup closing last doesn't replace your tabs ({saved()})")
    p = start()
    check(until(lambda: urls(p) == [MINE], 15), f"Opened again: your tabs are back, without Composio's ({urls(p)})")

    # 4: two normal windows plus Get a key, closed one after another (Still's first window first).
    send(p, "moveTab", id="t2", window="new")
    check(until(lambda: sorted(map(tuple, urls(p))) == [(MINE[0],), (MINE[1],)], 15), f"Notes moves to a second window ({urls(p)})")
    get_a_key(p)
    check(len(windows(p)) == 3, "and Get a key opens a third, temporary one")
    check(quit_and_wait(p, "closeAll"), "Closing every window one after another quits Still")
    check(sorted(saved()) == [(0, MINE[0]), (1, MINE[1])], f"Both normal windows are saved, each with its own tabs, and Composio's isn't ({saved()})")
    p = start()
    check(until(lambda: sorted(map(tuple, urls(p))) == [(MINE[0],), (MINE[1],)], 20), f"Opened again: both windows come back with their tabs ({urls(p)})")
    check(not any(KEYPAGE in w["tabs"] or w.get("temporary") for w in windows(p)), "and no Composio window or tab")

    # 5: a private window that closes last.
    send(p, "incognitoWindow")
    check(until(lambda: any(w["incognito"] for w in windows(p)), 15), "A private window opens")
    check(quit_and_wait(p, "closeAll"), "Closing every window, the private one last, quits Still")
    check(sorted(saved()) == [(0, MINE[0]), (1, MINE[1])], f"The private window closing last doesn't replace your windows ({saved()})")
finally:
    if p.poll() is None:
        try:
            rpc(p, "closeAll")
        except Exception:
            pass
        until(lambda: p.poll() is not None, 15) or p.kill()

passed = sum(c["passed"] for c in CHECKS)
(RUN / "result.json").write_text(json.dumps({"checks": CHECKS}, indent=1))
print(("PASSED" if passed == len(CHECKS) else "FAILED") + f" {passed}/{len(CHECKS)} -> {RUN}")
sys.exit(0 if passed == len(CHECKS) else 1)
