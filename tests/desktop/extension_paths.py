"""What an extension's manifest names stays inside the extension's folder. Windows only: the Mac has no extensions.

Run: python tests/desktop/extension_paths.py artifacts/Still-QA/Still.exe
"""
import json
from pathlib import Path
import shutil
import struct
import sys
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).parent))
from qa import js, launch, rpc, send, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("extension-paths-" + uuid.uuid4().hex[:8])
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
EXTENSIONS = PROFILE / "Extensions"
OUTSIDE = RUN / "outside"
FAILED = []


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def png():
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b"")


def extension(name, worker, **more):
    """An unpacked extension: a worker that answers, and a page that asks it."""
    folder = RUN / name
    folder.mkdir(parents=True)
    manifest = {"manifest_version": 3, "name": name, "version": "1", "background": {"service_worker": worker}, **more}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "icon.png").write_bytes(png())
    (folder / "page.html").write_text("<!doctype html><title>asking</title><script src=page.js></script>", encoding="utf-8")
    (folder / "page.js").write_text("const ask = () => chrome.runtime.sendMessage('ping', r => { void chrome.runtime.lastError; if (r) document.title = r; else setTimeout(ask, 300) }); ask()", encoding="utf-8")
    if worker and isinstance(worker, str) and ".." not in worker and ":" not in worker and "\\" not in worker:
        target = folder / worker.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("chrome.runtime.onMessage.addListener((m, s, reply) => reply('pong'))", encoding="utf-8")
    return folder


def stray():
    return [p.name for p in OUTSIDE.rglob("*")] + [p.name for p in RUN.glob("*.js")] + [p.name for p in PROFILE.glob("*.js")] + [p.name for p in PROFILE.glob("still-adapter*")]


def install(process, folder):
    before = set(EXTENSIONS.glob("*.path")) if EXTENSIONS.exists() else set()
    send(process, "openPanel", name="extensions")
    answer = rpc(process, "stageExtension", path=str(folder))
    check(answer.get("ok"), f"{folder.name}: a manifest that stays in its folder reaches review ({answer})")
    send(process, "extensionInstall")
    found = until(lambda: set(EXTENSIONS.glob("*.path")) - before, 30)
    check(bool(found), f"{folder.name}: it installs")
    return found.pop() if found else None


def main():
    OUTSIDE.mkdir(parents=True)
    process = None
    try:
        process = launch(EXE, PROFILE)

        for name, worker in [
            ("up", "../../outside/sw.js"),
            ("up-deep", "js/../../../outside/sw.js"),
            ("rooted", str(OUTSIDE / "sw.js").replace("\\", "/")),
            ("backslash", "..\\..\\outside\\sw.js"),
            ("stream", "bg.js:hidden"),
            ("empty", ""),
            ("not-text", 1),
        ]:
            answer = rpc(process, "stageExtension", path=str(extension(name, worker)))
            check("error" in answer and "ok" not in answer, f"Review refuses a worker named {name} ({answer})")
            send(process, "extensionInstall")
        check(not stray(), f"Nothing was written outside any folder ({stray()})")
        check(not (EXTENSIONS.exists() and list(EXTENSIONS.glob("*.path"))), "And nothing was installed")

        plain = install(process, extension("plain", "js/bg.js", icons={"32": "icon.png"}))
        quoted = install(process, extension("quoted", "js/it's.js"))
        for path, name in [(plain, "bg"), (quoted, "quoted")]:
            ident = path.stem
            send(process, "new", url=f"chrome-extension://{ident}/page.html")
            answered = until(lambda: rpc(process, "eval", script="document.title") == "pong", 15)
            check(bool(answered), f"An extension's adapted worker ({name}) still runs and answers")
        folder = Path(plain.read_text().strip())
        wrapper = folder / "js" / "still-adapter-sw.js"
        check(wrapper.exists() and "/js/bg.js" in wrapper.read_text(), "The adapter sits next to the original worker")
        check(json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["background"]["service_worker"] == "js/still-adapter-sw.js", "And the manifest points to it")

        # An extension already installed, whose manifest later names a file outside its folder.
        ident = plain.stem
        send(process, "extensionPin", id=ident)
        check(until(lambda: js(process, "!!document.querySelector('img.ext-icon')"), 10), "A pinned extension shows the icon inside its folder")
        rpc(process, "quit")
        process.wait(timeout=20)
        (OUTSIDE / "outside.png").write_bytes(png())
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        manifest["icons"] = {"32": str(OUTSIDE / "outside.png")}
        manifest["background"]["service_worker"] = "../../outside/late.js"
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        process = launch(EXE, PROFILE)
        check(bool(until(lambda: js(process, "!!document.querySelector('[aria-label=\"plain\"]')"), 15)), "After a restart the pinned extension is still there")
        check(not js(process, "!!document.querySelector('img.ext-icon')"), "But an icon outside its folder isn't read")
        send(process, "extensionAction", id=ident)
        until(lambda: False, 2)
        check(not (OUTSIDE / "late.js").exists() and not list(OUTSIDE.glob("still-adapter*")), f"And its worker isn't written outside ({stray()})")
    finally:
        if process and process.poll() is None:
            process.kill()
    print(f"{len(FAILED)} failed")
    if not FAILED:
        shutil.rmtree(RUN, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


main()
