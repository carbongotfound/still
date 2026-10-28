"""Helpers for driving a QA build of Still over its test pipe."""
import ctypes
import json
import time
from pathlib import Path


def rpc(process, op="state", **args):
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


def alive(pid):
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def launch(exe, profile, env=None):
    """Starts Still on a test profile and waits until its first tab exists."""
    import subprocess
    process = subprocess.Popen([str(Path(exe).resolve()), "--qa", "--profile", str(profile), "--profiles-root", str(profile)], env=env)
    until(lambda: (profile / "qa-pipe.txt").exists() or process.poll() is not None, 30)
    until(lambda: rpc(process).get("tabs"), 30)
    until(lambda: rpc(process, "shellEval", script="document.body.innerText.length"), 30)  # the interface has rendered
    return process


ROOT = Path(__file__).resolve().parents[2]
SIZES = ((1720, 1080), (1280, 800))


def shots(exe, name, version, setup, preferences=None, reference=None):
    """Captures one screen at the brief's two sizes in light and dark, into docs/agentic/compare as
    <name>-<version>-<theme>-<width>.png, plus <name>-<version>.png: the light 1720 shot beside the reference."""
    import shutil
    import uuid
    out = ROOT / "docs" / "agentic" / "compare"
    out.mkdir(parents=True, exist_ok=True)
    for theme in ("Light", "Dark"):
        for width, height in SIZES:
            profile = ROOT / "artifacts" / ("shot-" + uuid.uuid4().hex[:8]) / "profile"
            profile.mkdir(parents=True)
            (profile / "state.json").write_text(json.dumps({"UiVersion": 5, "Welcome": False,
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
    if reference:
        from PIL import Image
        mine, theirs = Image.open(out / f"{name}-{version}-light-1720.png"), Image.open(reference)
        theirs = theirs.resize((round(theirs.width * mine.height / theirs.height), mine.height))
        both = Image.new("RGB", (mine.width + theirs.width + 16, mine.height), "white")
        both.paste(theirs, (0, 0))
        both.paste(mine, (theirs.width + 16, 0))
        both.save(out / f"{name}-{version}.png")
