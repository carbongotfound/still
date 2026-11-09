"""The Permissions button: Allow, Ask or Block for each permission on the active tab's site, applied at once and kept.

Checks: the toolbar has it in place of split view's button; its menu lists eleven permissions for the site; Block, Allow
and Ask for the camera reach the engine (refused, granted with no bar, asked in the bar); the dot while the camera or
location is on; pop-ups blocked, asked, allowed; sound muted; USB hidden; everything kept after a restart; a private
tab's choices stay out of the profile; Reset; the settings link. Media is the engine's fake camera and microphone. On the
Mac no camera, microphone or location is used (only their choices are checked), and the kinds WebKit has no way to answer
for show as not available.

Run: python tests/desktop/sitepermissions.py artifacts/Still-QA/Still.exe [shots folder]
     python tests/desktop/sitepermissions.py artifacts/Still-QA-before/Still.exe [shots folder] --before  (the old toolbar)
"""
import http.server
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, press_ready, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else ROOT / "artifacts" / "sitepermissions-shots"
BEFORE = "--before" in sys.argv
RUN = ROOT / "artifacts" / ("sitepermissions-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
FAILED = []
os.environ["STILL_QA_BROWSER_ARGS"] = "--use-fake-device-for-media-stream"


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def site():
    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<!doctype html><title>Studio check</title><h1>Studio check</h1><p>Camera, microphone and the rest.</p>"
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/"


def start():
    if not (PROFILE / "state.json").exists():
        PROFILE.mkdir(parents=True)
        (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Theme": "Light", "Width": 1280, "Height": 820},
            "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    return launch(EXE, PROFILE)


def shot(p, name):
    time.sleep(.8)
    rpc(p, "capture", name=name)
    if (PROFILE / name).exists():
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copy(PROFILE / name, OUT / name)


def page(p, script):
    return rpc(p, "eval", script=script)


def wait_page(p, script, seconds=10):
    """Runs script (which sets window.__r once it's done) and waits for the answer."""
    page(p, "window.__r = undefined;" + script)
    return until(lambda: page(p, "window.__r === undefined ? null : String(window.__r)"), seconds)


def tab(p):
    s = rpc(p)
    return next(t for t in s["tabs"] if t["Id"] == s["activeId"])


def bar(p):
    """The permission bar's words while it asks, else ''."""
    return js(p, "document.querySelector('.permission-wrap.is-open .permission-bar')?.innerText || ''") or ""


def answer(p, allow):
    press_ready(p, "[...document.querySelectorAll('.permission-wrap.is-open .permission-bar button')].find(b => b.textContent === '%s')" % ("Allow" if allow else "Block"))
    until(lambda: not bar(p), 5)


def go(p, url, private=False):
    send(p, "new", url=url, private=private)
    until(lambda: tab(p)["Url"].startswith(url) and not tab(p)["Loading"], 15)
    time.sleep(.5)


def open_menu(p):
    # The button toggles the menu, and a press can be lost while the toolbar redraws (a pop-up's tab coming and going on
    # the Mac): press again until it's open.
    shown = lambda: js(p, "document.querySelectorAll('.perm-row').length === 11 && !document.querySelector('.perm-seg button:disabled')")
    for _ in range(3):
        if js(p, "!document.querySelector('.perm-menu[data-state=open]')"):
            js(p, "document.querySelector('.perm-button')?.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' }))")
        if until(shown, 4):
            return True
        close_menu(p)
    return False


def close_menu(p):
    js(p, "document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    until(lambda: js(p, "!document.querySelector('.perm-menu')"), 5)


def states(p):
    return js(p, "Object.fromEntries([...document.querySelectorAll('.perm-seg')].map(g => [g.getAttribute('aria-label'), g.querySelector('[aria-checked=true]')?.dataset.state]))") or {}


def set_state(p, label, state):
    js(p, f"document.querySelector('.perm-seg[aria-label=\"{label}\"] [data-state={state}]').click()")
    return until(lambda: states(p).get(label) == state, 10)


def back(p, url):
    """Back to the site's own tab after a pop-up opened."""
    send(p, "select", id=next(t["Id"] for t in rpc(p)["tabs"] if t["Url"].startswith(url) and "popup" not in t["Url"] and not t["Private"]))
    until(lambda: "popup" not in tab(p)["Url"], 5)


# Later than a click's reach, so no pop-up here counts as a person's (on the Mac a script Still runs counts as a click).
POPUP = "setTimeout(() => window.open('/popup'), 1500)"


def camera(p, kind="video"):
    return wait_page(p, f"navigator.mediaDevices.getUserMedia({{ {kind}: true }}).then(s => {{ window.__s = s; window.__r = 'granted' }}, e => window.__r = e.name)", 8)


def before():
    p = start()
    try:
        go(p, site())
        check(js(p, "!!document.querySelector('.split-button')"), "The old toolbar has the split view button")
        shot(p, "before-toolbar.png")
    finally:
        rpc(p, "quit"); p.wait(timeout=20)


def main():
    url = site()
    p = start()
    try:
        go(p, url)
        check(not js(p, "!!document.querySelector('.split-button')"), "Split view's toolbar button is gone")
        check(js(p, "!!document.querySelector('.perm-button')"), "The toolbar has a Permissions button")
        check(open_menu(p), "Its menu lists the eleven permissions")
        head = js(p, "document.querySelector('.perm-head strong')?.textContent")
        check(head == "127.0.0.1", f"The menu names the site ({head})")
        check(set(states(p).values()) == {"Ask"}, "Everything starts on Ask")
        shot(p, "menu.png")

        if MAC:  # the choices only: no camera, microphone or location is used there
            check(set_state(p, "Camera", "Allow") and set_state(p, "Camera", "Deny"), "Camera: Allow and Block are kept")
        else:
            set_state(p, "Camera", "Deny")
            check(camera(p) == "NotAllowedError" and not bar(p), "Camera on Block: the site is refused, with no bar")
            set_state(p, "Camera", "Allow")
            check(camera(p) == "granted" and not bar(p), "Camera on Allow: the site gets it, with no bar")
            close_menu(p)
            check(until(lambda: "camera" in (tab(p).get("InUse") or ""), 5), "Still knows the camera is on")
            check(until(lambda: js(p, "!!document.querySelector('.perm-dot')"), 5), "The Permissions button shows a dot")
            check("camera" in (js(p, "document.querySelector('.perm-button').getAttribute('aria-label')") or ""), "The button says the camera is in use")
            shot(p, "in-use.png")
            open_menu(p)
            check(js(p, "[...document.querySelectorAll('.perm-label')].some(l => l.textContent === 'CameraIn use')"), "The menu marks the camera In use")
            shot(p, "menu-in-use.png")
            close_menu(p)
            page(p, "window.__s.getTracks().forEach(t => t.stop())")
            check(until(lambda: not tab(p).get("InUse") and js(p, "!document.querySelector('.perm-dot')"), 5), "The dot goes once the camera is off")

            open_menu(p)
            set_state(p, "Location", "Allow")
            page(p, "window.__w = navigator.geolocation.watchPosition(() => {}, () => {})")
            check(until(lambda: "location" in (tab(p).get("InUse") or ""), 5), "Location in use while the site watches it")
            page(p, "navigator.geolocation.clearWatch(window.__w)")
            check(until(lambda: "location" not in (tab(p).get("InUse") or ""), 5), "and not once it stops")

            set_state(p, "Camera", "Ask")
            page(p, "navigator.mediaDevices.getUserMedia({ video: true }).then(() => window.__r = 'granted', e => window.__r = e.name)")
            asked = until(lambda: bar(p), 8)
            check(asked and "camera" in asked, "Camera on Ask: Still's bar asks")
            if asked:
                answer(p, False)

        tabs = len(rpc(p)["tabs"])
        set_state(p, "Pop-ups", "Deny")
        page(p, POPUP)
        time.sleep(2.5)
        check(len(rpc(p)["tabs"]) == tabs and not bar(p), "Pop-ups on Block: none opens, and nothing asks")
        set_state(p, "Pop-ups", "Ask")
        page(p, POPUP)
        asked = until(lambda: bar(p), 6)
        check(asked and "pop-ups" in asked, "Pop-ups on Ask: the bar offers them")
        if asked:
            answer(p, False)
        if MAC:  # a script Still runs counts as a person's click there
            page(p, "window.open('/popup')")
            check(until(lambda: len(rpc(p)["tabs"]) == tabs + 1, 5) and not bar(p), "Pop-ups on Ask: one a person starts opens, with no bar")
            back(p, url)
            open_menu(p)
            tabs += 1
        set_state(p, "Pop-ups", "Allow")
        page(p, POPUP)
        check(until(lambda: len(rpc(p)["tabs"]) == tabs + 1, 6), "Pop-ups on Allow: it opens")
        back(p, url)
        open_menu(p)

        set_state(p, "Autoplay and sound", "Deny")
        check(until(lambda: tab(p)["muted"], 5), "Sound on Block: the tab is muted at once")
        set_state(p, "Autoplay and sound", "Ask")
        check(until(lambda: not tab(p)["muted"], 5), "Back on Ask: sound again")

        if not MAC:  # no USB there
            set_state(p, "USB devices", "Deny")
        set_state(p, "Microphone", "Allow")
        set_state(p, "Pop-ups", "Deny")
        set_state(p, "Autoplay and sound", "Deny")
        close_menu(p)
        send(p, "reload")
        time.sleep(1.5)
        check(page(p, "typeof navigator.usb") == "undefined", "USB on Block: the site can't see USB devices")

        go(p, url, private=True)
        open_menu(p)
        check("Private" in (js(p, "document.querySelector('.perm-head small')?.textContent") or ""), "In a private tab the menu says it's forgotten")
        set_state(p, "Pop-ups" if MAC else "Notifications", "Allow")  # the Mac has no notifications to allow
        close_menu(p)
    finally:
        rpc(p, "quit"); p.wait(timeout=20)

    saved = json.loads((PROFILE / "state.json").read_text(encoding="utf-8-sig"))["Preferences"].get("SitePermissions", {})
    origin = url.rstrip("/")
    # The Mac keeps the camera's and microphone's choices too; Windows leaves them to WebView2.
    mine = {"Camera": "Deny", "Microphone": "Allow", "Popups": "Deny", "Autoplay": "Deny"} if MAC else {"Usb": "Deny", "Popups": "Deny", "Autoplay": "Deny"}
    check(saved.get(origin) == mine, f"Still's own choices are saved ({saved})")
    check("Notifications" not in json.dumps(saved), "A private tab's choice isn't saved")

    p = start()
    try:
        go(p, url)
        open_menu(p)
        s = states(p)
        want = {"Microphone": "Allow", "Pop-ups": "Deny", "Autoplay and sound": "Deny", "Camera": "Deny"} | ({} if MAC else {"USB devices": "Deny", "Notifications": "Ask"})
        check(all(s.get(k) == v for k, v in want.items()), f"After a restart every choice is still there ({s})")
        check(tab(p)["muted"], "The blocked site starts muted")
        if not MAC:
            check(camera(p, "audio") == "granted" and not bar(p), "The microphone is still allowed after the restart")
        check(page(p, "typeof navigator.usb") == "undefined", "USB still hidden after the restart")
        shot(p, "menu-saved.png")

        js(p, "[...document.querySelectorAll('.perm-menu [role=menuitem]')].find(i => i.textContent.includes('Reset'))?.click()")
        check(until(lambda: set(states(p).values()) == {"Ask"}, 8), "Reset puts everything back on Ask")
        check(until(lambda: not tab(p)["muted"], 5), "and unmutes the site")
        if MAC:  # the choice only, for the settings page below
            set_state(p, "Microphone", "Allow")
            close_menu(p)
        else:
            page(p, "navigator.mediaDevices.getUserMedia({ audio: true }).then(() => window.__r = 'granted', e => window.__r = e.name)")
            asked = until(lambda: bar(p), 8)
            check(asked and "microphone" in asked, "After Reset the microphone asks again")
            if asked:
                answer(p, True)
        open_menu(p)
        js(p, "[...document.querySelectorAll('.perm-menu [role=menuitem]')].find(i => i.textContent.includes('All site settings'))?.click()")
        check(until(lambda: js(p, "document.body.innerText.includes('Website permissions')"), 8), "All site settings opens Privacy & security")
        check(until(lambda: js(p, "document.body.innerText.includes('Microphone · Allow')"), 8), "where the site's choices are listed")
        shot(p, "settings.png")
        errors = js(p, "JSON.stringify(window.__errors || [])")
        check(errors in (None, "[]"), f"No script errors ({errors})")
    finally:
        rpc(p, "quit"); p.wait(timeout=20)


if __name__ == "__main__":
    try:
        before() if BEFORE else main()
    finally:
        shutil.rmtree(RUN, ignore_errors=True)
    print("ALL PASSED" if not FAILED else f"{len(FAILED)} FAILED", flush=True)
    sys.exit(1 if FAILED else 0)
