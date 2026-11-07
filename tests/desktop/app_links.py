"""Links to other apps, and links that start Still. Windows only: the Mac opens apps without a command line.

The launcher is built here and run beside a stub Still.exe in a test folder, so no link ever reaches the real Still: it's never
given a lone web link, which would go to the open window. Needs Visual Studio's C compiler.

Run: python tests/desktop/app_links.py artifacts/Still-QA/Still.exe
"""
import http.server
import json
from multiprocessing.connection import Listener
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import urllib.parse
import time
import uuid
import winreg

sys.path.insert(0, str(Path(__file__).parent))
from qa import ROOT, js, launch, press_ready, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("app-links-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
SCHEME = "still-qa-probe"
KEY = "Software\\Classes\\" + SCHEME
PIPE = "still-qa-links-" + uuid.uuid4().hex[:8]
FAILED = []
STUB = r"""
#include <windows.h>
#include <shellapi.h>
int WINAPI wWinMain(HINSTANCE a, HINSTANCE b, PWSTR c, int d) {
 int argc; LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
 WCHAR name[MAX_PATH + 8]; DWORD wrote; GetModuleFileNameW(NULL, name, MAX_PATH); lstrcatW(name, L".new");
 HANDLE f = CreateFileW(name, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
 for (int i = 1; i < argc; i++) { WriteFile(f, argv[i], lstrlenW(argv[i]) * 2, &wrote, NULL); WriteFile(f, L"\n", 2, &wrote, NULL); }
 CloseHandle(f);
 WCHAR done[MAX_PATH + 8]; GetModuleFileNameW(NULL, done, MAX_PATH); lstrcatW(done, L".args"); MoveFileW(name, done);
 return 0;
}
"""


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def build_launcher(folder):
    folder.mkdir(parents=True)
    vcvars = next(Path("C:/Program Files/Microsoft Visual Studio").glob("*/*/VC/Auxiliary/Build/vcvars64.bat"), None)
    if not vcvars:
        check(False, "Needs Visual Studio's C compiler to build the launcher")
        return False
    shutil.copy(ROOT / "launcher" / "StillOpen.c", folder)
    (folder / "Still.c").write_text(STUB, encoding="utf-8")
    # The same launcher on a pipe of the test's own: the real Still's pipe is never touched.
    (folder / "HandOver.c").write_text(rf'#define LINK_PIPE L"\\\\.\\pipe\\{PIPE}-%s"' + "\n" + (ROOT / "launcher" / "StillOpen.c").read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "make.bat").write_text(f"""@call "{vcvars}" >nul
@cd /d "{folder}"
@cl /nologo /O1 /MT /W3 StillOpen.c /link /SUBSYSTEM:WINDOWS user32.lib shell32.lib shlwapi.lib advapi32.lib
@cl /nologo /O1 /MT /W3 Still.c /link /SUBSYSTEM:WINDOWS user32.lib shell32.lib
@cl /nologo /O1 /MT /W3 HandOver.c /link /SUBSYSTEM:WINDOWS user32.lib shell32.lib shlwapi.lib advapi32.lib
""", encoding="utf-8")
    out = subprocess.run(["cmd", "/c", str(folder / "make.bat")], capture_output=True, text=True, errors="replace")
    built = (folder / "StillOpen.exe").exists() and (folder / "Still.exe").exists()
    check(built, "The launcher builds" + ("" if built else ": " + out.stdout[-400:]))
    return built


def launcher_gives(folder, tail):
    """What Still.exe gets when the launcher starts with this command line. Never a lone web link: see the top of this file."""
    result = folder / "Still.exe.args"
    result.unlink(missing_ok=True)
    subprocess.run(f'"{folder / "StillOpen.exe"}" {tail}', timeout=20)
    if not until(result.exists, 10):
        return None
    return result.read_bytes().decode("utf-16-le").splitlines()


def hands_over(folder):
    """With a Still of this user listening, a web link goes down its pipe. A holder that's another user can't be run here: no second account."""
    link = "https://example.invalid/handed"
    got = []
    with Listener(rf"\\.\pipe\{PIPE}-{os.environ['USERNAME']}", family="AF_PIPE") as server:
        def take():
            with server.accept() as conn:
                got.append(conn.recv_bytes())
        reader = threading.Thread(target=take, daemon=True)
        reader.start()
        (folder / "Still.exe.args").unlink(missing_ok=True)
        subprocess.run([str(folder / "HandOver.exe"), link], timeout=20)
        reader.join(10)
    check(got == [link.encode()], f"A web link goes to a Still of this user ({got})")
    check(not (folder / "Still.exe.args").exists(), "...and doesn't start another one")


def launcher_checks():
    folder = RUN / "launcher"
    if not build_launcher(folder):
        return
    hands_over(folder)
    html = r"C:\some folder\page.html"
    for tail, want, name in [
        ('"stillurl:one"', ["--link", "stillurl:one"], "A link is one address"),
        (f'"{html}"', ["--link", html], "So is a file, spaces and all"),
        ("", [], "With nothing, nothing"),
        ('"stillurl:one" --profile C:\\elsewhere', [], "A link that breaks out of its quotes passes nothing on"),
        ('"https://example.invalid/" --profile C:\\elsewhere --mcp', [], "A web link that does the same: nothing"),
        ('stillurl:one --temp', [], "Without quotes: nothing"),
        ('"stillurl:one\\"two"', [], "A quote inside the link: nothing"),
    ]:
        got = launcher_gives(folder, tail)
        check(got == want, f"{name} ({got})")


def link_args(process):
    for given, want, name in [
        (["--link", "https://example.invalid/"], ["https://example.invalid/"], "--link keeps the address"),
        (["--link", "C:\\some folder\\page.html"], ["C:\\some folder\\page.html"], "--link keeps a file"),
        (["--link", "--mcp"], [], "--link never takes a setting"),
        (["--link", "https://example.invalid/", "--profile", "C:\\elsewhere"], [], "--link with anything after it gives nothing"),
        (["--link"], [], "--link alone gives nothing"),
        (["--qa", "--profile", "p"], ["--qa", "--profile", "p"], "Other starts are as they were"),
    ]:
        got = rpc(process, "linkArgs", args=given)
        check(got == want, f"{name} ({got})")


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>Links</title><p>Links</p><a id=go style='display:block;width:200px;height:40px;background:#ccc'>Open</a>"
        if self.path.startswith("/frame"):
            body = b"<!doctype html><title>Frame</title><script>location.href = decodeURIComponent(location.search.slice(1))</script>"
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


def bar(process):
    return js(process, "document.querySelector('.permission-wrap.is-open .permission-bar')?.innerText ?? ''") or ""


def app_link(process):
    """A real app registered for a throwaway link type, the way any app registers itself."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log = RUN / "probe.jsonl"
    probe = RUN / "probe.py"
    probe.write_text(f"import json, sys\nopen({str(log)!r}, 'a', encoding='utf-8').write(json.dumps(sys.argv[1:]) + '\\n')\n", encoding="utf-8")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Still QA probe")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY + "\\shell\\open\\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{pythonw}" -I "{probe}" "%1"')
    try:
        send(process, "new", url=f"http://127.0.0.1:{server.server_port}/")
        until(lambda: rpc(process, "eval", script="document.title") == "Links", 20)

        def go(link):
            rpc(process, "eval", script=f"location.href = {json.dumps(link)}")

        def click(link):
            at = rpc(process, "eval", script=f"(a => (a.href = {json.dumps(link)}, (r => [r.x + 20, r.y + 10])(a.getBoundingClientRect())))(document.querySelector('#go'))")
            for kind in ("mousePressed", "mouseReleased"):
                rpc(process, "pageCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": at[0], "y": at[1], "button": "left", "clickCount": 1})

        def answer(word):
            press_ready(process, f"[...document.querySelectorAll('.permission-wrap.is-open .permission-bar button')].find(b => b.innerText.trim() === {json.dumps(word)})")

        click(f'{SCHEME}:one" --evil "two three')
        check(until(lambda: "wants to" in bar(process), 15, .02), "An app link asks first")
        check(js(process, "[...document.querySelectorAll('.permission-wrap.is-open .permission-bar button')].find(b => b.innerText.trim() === 'Allow').disabled") is True, "Allow doesn't take a click the moment the bar appears")
        check(not log.exists(), "...and nothing started yet")
        answer("Allow")
        check(until(log.exists, 15), "Allow starts the app")
        args = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        check(len(args) == 1 and "%22" in args[0] and '"' not in args[0] and "%20" in args[0], f"The app gets one argument, whatever the link said ({args})")

        click(f"{SCHEME}:plain/path?a=b&c=d#e")
        check(until(lambda: len(log.read_text(encoding="utf-8").splitlines()) == 2, 15), "On that site a click doesn't ask again")
        args = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        check(args == [f"{SCHEME}:plain/path?a=b&c=d#e"], f"An ordinary link gets there as it was ({args})")

        go(f"{SCHEME}:scripted")
        check(until(lambda: "wants to" in bar(process), 15), "A link nobody clicked asks, even on an allowed site")
        answer("Block")
        until(lambda: "wants to" not in bar(process), 5)
        check(len(log.read_text(encoding="utf-8").splitlines()) == 2, "...and Block starts nothing")

        frame = f"http://localhost:{server.server_port}/frame?" + urllib.parse.quote(f"{SCHEME}:framed", safe="")
        rpc(process, "eval", script=f"document.body.insertAdjacentHTML('beforeend', '<iframe src=\"{frame}\"></iframe>')")
        said = until(lambda: bar(process) if "wants to" in bar(process) else "", 15) or ""
        check("localhost" in said and "127.0.0.1" not in said, f"Another site's frame asks in its own name ({said[:80]!r})")
        answer("Allow")
        check(until(lambda: len(log.read_text(encoding="utf-8").splitlines()) == 3, 15), "...and Allow is for that one link")
        rpc(process, "eval", script="document.querySelector('iframe').remove()")

        send(process, "forgetAppLinks")
        time.sleep(.5)
        click(f"{SCHEME}:again")
        check(until(lambda: "wants to" in bar(process), 15), "After forgetting, the site asks again")
        answer("Block")
        until(lambda: "wants to" not in bar(process), 5)

        go('stillurl:one" --temp "two')
        time.sleep(2)
        check("wants to" not in bar(process), "A link to Still's own link type is refused without asking")
    finally:
        server.shutdown()
        for sub in ("\\shell\\open\\command", "\\shell\\open", "\\shell", ""):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY + sub)
            except OSError:
                pass
    with_key = True
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY))
    except OSError:
        with_key = False
    check(not with_key, "The test's link type is gone again")


def main():
    RUN.mkdir(parents=True)
    launcher_checks()
    process = launch(EXE, PROFILE)
    try:
        link_args(process)
        app_link(process)
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
    print(("FAILED " if FAILED else "PASSED ") + f"{len(FAILED)} failed -> {RUN}")
    if not FAILED:
        shutil.rmtree(RUN, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


main()
