"""Skills from a link: a GitHub repository or an npm package, against a fake GitHub and npm (STILL_QA_SKILL_HUB).

Look shows each SKILL.md found, with its name and description read the way such files write them, and says what won't
come over: commands it runs, the other files in its folder, a file too big to bring. Only the ticked ones are added, as
skills that keep where they came from, also after an edit. Nothing but the SKILL.md files is ever fetched. A sub-folder
or a SKILL.md link brings just that skill, a package brings its own, a second look marks what's already added, and a
wrong link, a missing or private repository, GitHub's limit and a repository without skills each say so.

Run: python tests/desktop/skill_import.py <QA exe> [--shots]   (--shots keeps a picture of the list in artifacts/)
"""
import http.server
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).parent))
from qa import js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
FAILED = []
SEEN = []

PLAIN = """---
name: "Plain notes"
description: >
  Turns rough notes into a tidy summary.
  Keeps every number.
---

# Plain notes

1. Read the notes.
2. Write the summary.
"""
RUNNER = """---
name: runner
description: Runs the helper first
allowed-tools: Bash, Read
---

Run this before anything:

```bash
helper doctor --json
```
"""
TIDY = """---
name: tidy
description: 'Tidies a table'
---

Sort the rows, then remove the empty ones.
"""
KIT = [("skills/plain/SKILL.md", len(PLAIN)), ("skills/runner/SKILL.md", len(RUNNER)), ("skills/runner/scripts/run.sh", 40),
       ("skills/runner/reference.md", 300), ("skills/big/SKILL.md", 200_000), ("README.md", 900)]
FILES = {"raw.githubusercontent.com/acme/kit/HEAD/skills/plain/SKILL.md": PLAIN, "raw.githubusercontent.com/acme/kit/main/skills/plain/SKILL.md": PLAIN,
         "raw.githubusercontent.com/acme/kit/HEAD/skills/runner/SKILL.md": RUNNER, "raw.githubusercontent.com/acme/kit/main/skills/runner/SKILL.md": RUNNER,
         "cdn.jsdelivr.net/npm/@acme/skills@1.2.0/skills/tidy/SKILL.md": TIDY}


def tree(entries):
    return {"sha": "abc", "truncated": False, "tree": [{"path": p, "type": "blob", "size": s} for p, s in entries] + [{"path": "skills", "type": "tree"}]}


class Hub(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(self.path.lstrip("/"))
        SEEN.append(path)
        status, body = 404, {"message": "Not Found"}
        if path in ("api.github.com/repos/acme/kit/git/trees/HEAD?recursive=1", "api.github.com/repos/acme/kit/git/trees/main?recursive=1"):
            status, body = 200, tree(KIT)
        elif path == "api.github.com/repos/acme/empty/git/trees/HEAD?recursive=1":
            status, body = 200, tree([("README.md", 10)])
        elif path.startswith("api.github.com/repos/acme/limited/"):
            status, body = 403, {"message": "API rate limit exceeded"}
        elif path == "data.jsdelivr.com/v1/packages/npm/@acme/skills/resolved":
            status, body = 200, {"type": "npm", "name": "@acme/skills", "version": "1.2.0"}
        elif path == "data.jsdelivr.com/v1/packages/npm/@acme/skills@1.2.0?structure=flat":
            status, body = 200, {"files": [{"name": "/package.json", "size": 40}, {"name": "/skills/tidy/SKILL.md", "size": len(TIDY)}]}
        elif path in FILES:
            status, body = 200, FILES[path]
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8" if isinstance(body, str) else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def click(p, selector):
    return js(p, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.click(); return !!e }})()")


def click_text(p, selector, words):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(selector)})].find(e => e.innerText.trim().includes({json.dumps(words)})); e?.click(); return !!e }})()")


def type_into(p, selector, value):
    return js(p, f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {json.dumps(value)})
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); e.focus(); return true }})()""")


def look(p, link):
    """Looks at a link without the dialog and returns what Still found."""
    js(p, "window.__found = []; if (!window.__listening) { window.__listening = true; window.chrome.webview.addEventListener('message', e => { if (e.data?.kind === 'skillImport') __found.push(e.data) }) }")
    send(p, "skillImportLook", link=link)
    return until(lambda: js(p, "window.__found.length ? window.__found[0] : null"), 20) or {}


def rows(p):
    return js(p, "[...document.querySelectorAll('.skill-import-row')].map(r => ({ text: r.innerText, on: r.querySelector('input[type=checkbox]').checked }))") or []


def main():
    hub = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hub)
    threading.Thread(target=hub.serve_forever, daemon=True).start()
    profile = Path(tempfile.mkdtemp(prefix="still-skillimport-")).resolve()
    skills = profile / "skills"
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"AgentsEnabled": True,
        "Companions": [{"Id": "nora", "Name": "Nora", "Job": "Researcher"}]}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}), encoding="utf-8")
    p = launch(EXE, profile, {**os.environ, "STILL_QA_SKILL_HUB": f"http://127.0.0.1:{hub.server_address[1]}"})
    try:
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.home-rail')"), 20)
        time.sleep(.4)
        js(p, "dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))")
        click(p, ".home-rail-item[aria-label='Skills & plugins']")
        until(lambda: js(p, "!!document.querySelector(\".home-page[aria-label='Skills & plugins']\")"), 5)

        # The dialog: look at a repository, see what's there and what won't come over.
        check(click_text(p, ".plug-all", "Add from a link") and until(lambda: js(p, "!!document.querySelector('.skill-dialog [aria-label=\"Skills link\"]')"), 5),
              "Skills & plugins has Add from a link, which asks for a link")
        type_into(p, ".skill-dialog [aria-label='Skills link']", "https://github.com/acme/kit")
        click_text(p, ".skill-dialog button[type=submit]", "Look")
        found = until(lambda: (r := rows(p)) and len(r) == 2 and r, 20) or rows(p)
        names = [r["text"].split("\n")[0] for r in found]
        check(names == ["Plain notes", "runner"], f"Look lists the two skills it can bring, not the one too big to bring: {names}")
        plain = found[0]["text"] if found else ""
        runner = found[1]["text"] if len(found) > 1 else ""
        check("Turns rough notes into a tidy summary. Keeps every number." in plain, "A quoted name and a description on the lines under it read right")
        check("runs commands on your computer" in runner and "2 more files" in runner, "The one that runs commands says so, and that its other files stay behind")
        check("runs commands" not in plain and "more file" not in plain, "The plain one has no such notes")
        check(all(r["on"] for r in found) and "From github.com/acme/kit" in (js(p, "document.querySelector('.skill-import-list')?.innerText") or ""),
              "Both start ticked, under where they're from")
        if "--shots" in sys.argv:
            shot = (rpc(p, "capture", name="skill-import.png") or {}).get("path")
            if shot:
                (Path(__file__).resolve().parents[2] / "artifacts").mkdir(exist_ok=True)
                shutil.copy(shot, Path(__file__).resolve().parents[2] / "artifacts" / "skill-import.png")
        click_text(p, ".skill-import-row button", "Show steps")
        check(until(lambda: "Write the summary" in (js(p, "document.querySelector('.skill-import-body')?.innerText") or ""), 5), "Show steps shows a skill's text before it's added")
        js(p, "[...document.querySelectorAll('.skill-import-row')][1].querySelector('input[type=checkbox]').click()")
        check(until(lambda: click_text(p, ".skill-dialog button", "Add skill"), 5), "Unticking one leaves Add skill")
        added = skills / "plain-notes.md"
        check(until(lambda: added.exists(), 10), "Add saves the ticked skill")
        text = added.read_text(encoding="utf-8") if added.exists() else ""
        check("source: github.com/acme/kit" in text and "2. Write the summary." in text and "name: Plain notes" in text, "as a skill that keeps where it came from")
        check(not any("runner" in f.name for f in skills.glob("*.md")), "and not the unticked one")
        check(not any(s.endswith(("run.sh", "reference.md", "README.md")) or "skills/big/" in s for s in SEEN), "Only SKILL.md files were ever fetched: no scripts or other files")
        check(until(lambda: "From github.com/acme/kit" in (js(p, "[...document.querySelectorAll('.skill-row')].find(r => r.innerText.includes('Plain notes'))?.innerText") or ""), 5),
              "Its row on the page says where it's from")

        # A second look marks what's already added.
        again = look(p, "github.com/acme/kit")
        first = (again.get("skills") or [{}])[0]
        check(first.get("added") and "Already added from here." in first.get("notes", []), "Looking again marks the one already added")

        # An edit keeps where it came from.
        send(p, "skillSave", id="plain-notes", name="Plain notes", description="Mine now", when="", body="Changed steps.")
        check(until(lambda: "Changed steps." in added.read_text(encoding="utf-8") and "source: github.com/acme/kit" in added.read_text(encoding="utf-8"), 5), "Editing it keeps where it came from")

        # Just one skill: a sub-folder link, or a link to its SKILL.md.
        one = look(p, "https://github.com/acme/kit/tree/main/skills/plain")
        check([k["name"] for k in one.get("skills", [])] == ["Plain notes"] and one.get("source") == "github.com/acme/kit/skills/plain", f"A sub-folder link brings just that skill ({one.get('source')})")
        blob = look(p, "https://github.com/acme/kit/blob/main/skills/runner/SKILL.md")
        check([k["name"] for k in blob.get("skills", [])] == ["runner"], "and so does a link to its SKILL.md")

        # npm: the package's own skills, at its newest version.
        pkg = look(p, "npm:@acme/skills")
        check(pkg.get("source") == "npm: @acme/skills@1.2.0" and [k["name"] for k in pkg.get("skills", [])] == ["tidy"] and pkg["skills"][0]["description"] == "Tidies a table",
              f"An npm package brings its skills at its newest version ({pkg.get('source')})")
        send(p, "skillImportAdd", keys=[0, 0, 7])
        tidy = skills / "tidy.md"
        check(until(lambda: tidy.exists(), 10) and "source: npm: @acme/skills@1.2.0" in tidy.read_text(encoding="utf-8"), "Adding it saves it once, from npm, and a key it didn't find does nothing")
        check(look(p, "https://www.npmjs.com/package/@acme/skills").get("source") == "npm: @acme/skills@1.2.0", "An npmjs.com link works too")

        # Each wrong link says what's wrong, and leaves nothing to add.
        for link, words, what in [("https://github.com/acme/missing", "Couldn't find that on GitHub", "A missing or private repository"),
                                  ("github.com/acme/limited", "limiting requests", "GitHub's limit"),
                                  ("github.com/acme/empty", "No skills there", "A repository without skills"),
                                  ("https://example.com/skills", "Paste a GitHub link", "A link that isn't GitHub or npm"),
                                  ("https://github.com/acme/kit/tree/main/../../x", "doesn't look right", "A link that climbs out of the repository")]:
            said = look(p, link)
            check(words in said.get("error", "") and not said.get("skills"), f"{what} says so: {said.get('error', '')[:70]!r}")
        before = sorted(f.name for f in skills.glob("*.md"))
        send(p, "skillImportAdd", keys=[0])
        time.sleep(1)
        check(sorted(f.name for f in skills.glob("*.md")) == before, "After a failed look, Add adds nothing")
        errors = rpc(p).get("shellErrors") or []
        check(not errors, "No interface errors" + (f": {errors[:1]}" if errors else ""))
    finally:
        try:
            rpc(p, "quit")
            p.wait(timeout=20)
        except Exception:
            p.kill()
        time.sleep(1)
        hub.shutdown()
        shutil.rmtree(profile, ignore_errors=True)
    print("FAILED " + str(FAILED) if FAILED else "PASSED")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
