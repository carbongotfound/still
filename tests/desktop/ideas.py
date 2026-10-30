"""The new tab's "Try one of these": up to three concrete tasks from what Still knows, each saying why: a project the
companion remembers, an open tab (never a private one), then its role matched to the user's work. They change as the
context does: close the tab and its card goes. (Unit tests for every source: still-ui/tests/suggestions.test.ts.)

Run: python tests/desktop/ideas.py artifacts/Still-QA/Still.exe
Out: artifacts/ideas-*/ (ideas-*.png in the profile folder)
"""
import http.server
import json
from pathlib import Path
import sys
import threading
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("ideas-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
FAILED = []


class Pages(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        title = {"/plan": "Quarterly plan", "/bank": "Secret bank statement"}.get(self.path, "Page")
        body = f"<title>{title}</title><h1>{title}</h1>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def cards(p):
    return js(p, "[...document.querySelectorAll('.home-ideas .home-idea')].map(b => b.dataset.kind + ': ' + b.querySelector('b').innerText + ' / ' + b.querySelector('small').innerText)") or []


def tab_id(p, path):
    return next((t.get("Id") for w in rpc(p, "tabs").get("windows", []) for t in w["tabs"] if (t.get("Url") or "").endswith(path)), None)


def home(p):
    send(p, "new")
    until(lambda: js(p, "!!document.querySelector('.home-compose textarea')"), 15)


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Pages)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{server.server_port}"
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": [{**CREW[0], "Crew": "research"}] + CREW[1:], "AgentsEnabled": True, "Interests": ["Research"]},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        home(p)
        got = until(lambda: len(cards(p)) == 3 and cards(p), 10) or cards(p)
        check(all(c.startswith("role: ") for c in got) and got[0].endswith("/ You work on research") and "Maya's role: Research" in got[1], f"With nothing open yet: the role's tasks, the user's work first, each saying why ({got})")

        send(p, "new", url=site + "/bank", private=True)
        until(lambda: tab_id(p, "/bank"), 15)
        send(p, "new", url=site + "/plan")
        until(lambda: tab_id(p, "/plan"), 15)
        home(p)
        got = until(lambda: any(c.startswith("tab: Sum up Quarterly") for c in cards(p)) and cards(p), 10) or cards(p)
        check("tab: Sum up Quarterly plan / Open in your tabs" in got, f"An open tab becomes a card ({got})")
        check(not any("Secret" in c or "bank" in c for c in got), "A private tab never does")

        send(p, "memoryAdd", companion="maya", text="Launching the spring catalog on May 3.", kind="project")
        got = until(lambda: (cards(p)[:1] or [""])[0].startswith("project: ") and cards(p), 10) or cards(p)
        check(got[:1] == ["project: Next step: Launching the spring catalog on May 3 / From Maya's memory"], f"A project the companion remembers comes first, as soon as it's remembered ({got})")
        check(len(got) == 3, "Three at most")
        rpc(p, "capture", name="ideas-home.png")

        send(p, "closeTab", id=tab_id(p, "/plan"))
        check(until(lambda: not any(c.startswith("tab: ") for c in cards(p)), 10), f"Close the tab and its card goes ({cards(p)})")
    finally:
        try:
            rpc(p, "quit")
        except (RuntimeError, OSError):
            pass
        until(lambda: p.poll() is not None, 15)
        if p.poll() is None:
            p.kill()
        server.shutdown()
    print(f"\n{len(FAILED)} failed" if FAILED else "\nAll ideas checks passed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
