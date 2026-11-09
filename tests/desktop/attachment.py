"""A file a site sends as an attachment downloads, even when Still could show it (a 3D model sent as plain text), as in
other browsers: it doesn't open in the tab. Local pages only; the file goes to the test's own folder.

Run: python tests/desktop/attachment.py <Still.exe or Still.app/Contents/MacOS/Still>
"""
import http.server
import json
from pathlib import Path
import shutil
import sys
import threading
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("attachment-" + uuid.uuid4().hex[:8])
FOLDER = RUN / "downloads"
BODY = b"solid fixture\nendsolid fixture\n"
FAILED = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Disposition", 'attachment; filename="fixture.stl"')
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *_):
        pass


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    (RUN / "profile").mkdir(parents=True)
    FOLDER.mkdir()
    (RUN / "profile" / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"DownloadFolder": str(FOLDER)}}), encoding="utf-8")
    process = launch(EXE, RUN / "profile")
    try:
        send(process, "navigate", url=f"http://127.0.0.1:{server.server_port}/fixture.stl")
        done = until(lambda: next((d for d in rpc(process)["downloads"] if d["status"] == "Completed"), None), 15)
        saved = Path(done["Path"]) if done else FOLDER  # Windows test builds save to the profile's own folder
        check(bool(done) and RUN in saved.parents and saved.is_file() and saved.read_bytes() == BODY, "A text file sent as an attachment downloads")
        shown = rpc(process, "eval", script="document.body ? document.body.innerText : ''") or ""
        check("solid fixture" not in shown, "...and doesn't open in the tab")
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
        server.shutdown()
        shutil.rmtree(RUN, ignore_errors=True)
    print(f"{'FAILED ' + str(len(FAILED)) if FAILED else 'PASSED'}", flush=True)
    sys.exit(1 if FAILED else 0)


main()
