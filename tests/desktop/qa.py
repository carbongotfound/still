"""Helpers for driving a QA build of Still over its test pipe (a Unix socket on the Mac)."""
import ctypes
import json
import sys
import time
from pathlib import Path

MAC = sys.platform == "darwin"


def rpc(process, op="state", **args):
    if MAC:
        return mac_rpc(process, {"op": op, **args})
    pipe = r"\\.\pipe\StillQa-" + str(process.pid)
    end = time.monotonic() + 15
    while not ctypes.windll.kernel32.WaitNamedPipeW(pipe, 500):
        if time.monotonic() > end or process.poll() is not None:
            raise RuntimeError("QA pipe unavailable")
        time.sleep(.05)
    with open(pipe, "r+b", buffering=0) as stream:
        stream.write((json.dumps({"op": op, **args}) + "\n").encode())
        response = b""
        while not response.endswith(b"\n"):
            part = stream.read(65536)
            if not part:
                raise RuntimeError("QA pipe closed")
            response += part
    return json.loads(response)


def mac_rpc(process, request):
    """The Mac's test channel: the socket whose path Still wrote to qa-pipe.txt in the profile it was started with."""
    import socket
    end = time.monotonic() + 15
    while True:
        try:
            with socket.socket(socket.AF_UNIX) as stream:
                stream.connect((profile_of(process) / "qa-pipe.txt").read_text().strip())
                stream.sendall((json.dumps(request) + "\n").encode())
                response = b""
                while not response.endswith(b"\n"):
                    part = stream.recv(65536)
                    if not part:
                        raise RuntimeError("QA pipe closed")
                    response += part
            return json.loads(response)
        except OSError:
            if time.monotonic() > end or process.poll() is not None:
                raise RuntimeError("QA pipe unavailable")
            time.sleep(.05)


def profile_of(process):
    """The --profile a Still was started with (Popen keeps its arguments; otherwise ps shows them)."""
    import subprocess
    args = [str(a) for a in getattr(process, "args", None) or subprocess.run(["ps", "-o", "command=", "-p", str(process.pid)], capture_output=True, text=True).stdout.split()]
    return Path(args[args.index("--profile") + 1]) if "--profile" in args else Path.home() / "Library" / "Application Support" / "Still"


def launcher(path, script):
    """A command the AI-app manifests can run: path.cmd on Windows, an executable shell script at path on the Mac.
    script is the Python file it runs (isolated, with the arguments passed on)."""
    path = Path(path)
    if MAC:
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{script}" "$@"\n')
        path.chmod(0o755)
    else:
        path.with_suffix(".cmd").write_text(f'@"{sys.executable}" -I "{script}" %*\r\n')


def send(process, op, **args):
    """Posts a message to the native side as the interface would."""
    rpc(process, "shellEval", script="window.chrome.webview.postMessage(" + json.dumps({"op": op, **args}) + ")")


def text(process):
    return rpc(process, "shellEval", script="document.body.innerText")


def js(process, script):
    return rpc(process, "shellEval", script=script)


def until(predicate, seconds=20, step=.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    return None


def companions_page(process, seconds=10):
    """Opens the Companions page from the Companions chip on the home page (the side rail has no button for it)."""
    return until(lambda: js(process, "(() => { if (document.querySelector('.mate-grid')) return true; const chip = [...document.querySelectorAll('.home-chips button')].find(b => b.innerText.includes('Companions'));"
                            " (chip ?? document.querySelector('.home-rail-item[aria-label=\"New chat\"]'))?.click(); return false })()"), seconds, .3)


def alive(pid):
    if MAC:  # a zombie counts as gone, as an exit code does on Windows
        import subprocess
        return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()[:1] not in ("", "Z")
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


START = 120  # seconds a QA build gets to come up: a first start on Windows waits on WebView2, 18 to 25 s here and more on a busy PC


def press_ready(process, find, seconds=5):
    """Clicks a button once it takes clicks: a card's buttons wait a moment after their meaning changes. find: JS for the button."""
    return until(lambda: js(process, f"(b => {{ if (!b || b.disabled) return false; b.click(); return true }})({find})"), seconds, .05)


def until_started(process, seconds=START):
    """Waits until a Still that was just started answers on its test pipe, has a tab and has drawn its interface.
    A slow start is waited out. One that exits or never comes up fails with the reason, and one that hangs is closed."""
    end = time.monotonic() + seconds
    for what, probe in (("its first tab", lambda: rpc(process).get("tabs")),
                        ("its interface", lambda: rpc(process, "shellEval", script="document.body.innerText.length > 0") is True)):
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"Still exited (code {process.returncode}) while starting, waiting for {what}")
            try:
                if probe():
                    break
            except (OSError, RuntimeError, ValueError):
                pass  # no pipe yet, or it closed mid-start: try again
            if time.monotonic() > end:
                process.kill()
                raise RuntimeError(f"Still didn't start within {seconds} s, waiting for {what}")
            time.sleep(.2)
    return process


def launch(exe, profile, env=None):
    """Starts Still on a test profile and waits until it's ready."""
    import subprocess
    return until_started(subprocess.Popen([str(Path(exe).resolve()), "--qa", "--profile", str(profile), "--profiles-root", str(profile)], env=env))


# The companions Still used to start with. Tests that talk to them bring them along (setup makes your own now).
CREW = [{"Id": "maya", "Name": "Maya", "Job": "An all-round coworker: researches, compares options and gets things done on the web."},
        {"Id": "nora", "Name": "Nora", "Job": "A careful researcher: reads several sources, checks the facts and cites them."},
        {"Id": "jonah", "Name": "Jonah", "Job": "A savvy shopper: finds the best price, compares deals and reviews, and never buys without asking."},
        {"Id": "rosa", "Name": "Rosa", "Job": "An organizer: handles email, calendars, documents and online busywork."}]

ROOT = Path(__file__).resolve().parents[2]
SIZES = ((1720, 1080), (1280, 800))


def shots(exe, name, version, setup, preferences=None):
    """Captures one screen at two sizes in light and dark, into docs/agentic/compare as <name>-<version>-<theme>-<width>.png."""
    import shutil
    import uuid
    out = ROOT / "docs" / "agentic" / "compare"
    out.mkdir(parents=True, exist_ok=True)
    for theme in ("Light", "Dark"):
        for width, height in SIZES:
            profile = ROOT / "artifacts" / ("shot-" + uuid.uuid4().hex[:8]) / "profile"
            profile.mkdir(parents=True)
            (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False,
                "Preferences": {"Theme": theme, "Width": width, "Height": height, **(preferences or {})},
                "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
            process = launch(exe, profile)
            try:
                setup(process)
                time.sleep(.8)  # let springs settle
                rpc(process, "capture", name="shot.png")
                shutil.copy(profile / "shot.png", out / f"{name}-{version}-{theme.lower()}-{width}.png")
            finally:
                rpc(process, "quit")
                process.wait(timeout=15)
