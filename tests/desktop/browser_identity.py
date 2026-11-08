"""What a page is told about this browser: the real engine's version and Still's own name, never a fixed old version or
another browser's name. With --google, one load of Gmail's address on a throwaway profile, to read what Google says.

Run: python tests/desktop/browser_identity.py artifacts/Still-QA/Still.exe [--google]
"""
import http.server
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
SEEN = []
FAILED = []


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/who":  # the icon request after it is Still's own, under Still's own name
            SEEN.append(self.headers.get("User-Agent", ""))
        body = b"<!doctype html><title>Who</title>Who am I"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = Path(tempfile.mkdtemp(prefix="still-who-"))
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False}), encoding="utf-8")
    p = launch(EXE, profile, {**os.environ, "STILL_QA_POS": os.environ.get("STILL_QA_POS", "-1800,80")})
    try:
        send(p, "new", url=f"http://127.0.0.1:{server.server_port}/who")
        until(lambda: SEEN and rpc(p, "eval", script="document.title") == "Who", 20)
        agent = rpc(p, "eval", script="navigator.userAgent") or ""
        print("User agent:", agent)
        check(SEEN and SEEN[-1] == agent, "What a server is told and what a page reads are the same")
        if MAC:
            real = plistlib.load(open("/Applications/Safari.app/Contents/Info.plist", "rb"))["CFBundleShortVersionString"]
            check(f"Version/{real} " in agent, f"The Mac says the Safari version it really has ({real})")
            check(re.search(r"Still/\d", agent), "...and Still's own name")
            check("Chrome" not in agent and "Edg" not in agent, "...and no other browser's")
        else:
            brands = rpc(p, "eval", script="(navigator.userAgentData?.brands ?? []).map(b => b.brand + ' ' + b.version).join(', ')") or ""
            print("Brands:", brands)
            version = re.search(r"Chrome/(\d+)", agent)
            check(version and f"Edg/{version.group(1)}" in agent, "Windows says what its engine is, unchanged by Still")
            check(version and f" {version.group(1)}" in brands, "...in its brands too")
        if "--google" in sys.argv:
            send(p, "navigate", url="https://mail.google.com/")
            until(lambda: "google." in (rpc(p, "eval", script="location.host") or "") and rpc(p, "eval", script="document.readyState") == "complete", 40)
            time.sleep(6)
            words = rpc(p, "eval", script="document.body.innerText") or ""
            print("Google landed on:", rpc(p, "eval", script="location.origin + location.pathname"))
            hits = [line.strip()[:160] for line in words.splitlines() if re.search(r"browser|supported|update|upgrade", line, re.I)]
            print("Lines about browsers:", hits[:6])
            check(not any(re.search(r"(no longer|not|isn't|n't) (be )?supported", h, re.I) for h in hits), "Google's page says nothing about an unsupported browser")
    finally:
        try:
            rpc(p, "quit")
            p.wait(timeout=20)
        except Exception:
            p.kill()
        time.sleep(1)
        shutil.rmtree(profile, ignore_errors=True)
        server.shutdown()
    print("FAILED " + str(FAILED) if FAILED else "PASSED")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
