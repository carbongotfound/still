"""What's New: after an update to a release with highlights (2.10), the first start shows a short popup of them, each
with a title, a line and a screenshot, moved through by arrows, dots or the keyboard, with See everything and Close.
It shows once per release, over a web page too: closed, it stays away on the next start, and Settings > About opens it again. A new
install doesn't get it (setup comes first), and a release without highlights shows nothing.

STILL_QA_VERSION stands in for the update; QA builds only show What's New with STILL_QA_WHATSNEW set.

Run: python tests/desktop/whatsnew.py artifacts/Still-QA/Still.exe
Out: artifacts/whatsnew-*/profile/whatsnew-*.png
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("whatsnew-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
FRESH = RUN / "fresh"
WEB = RUN / "web"
RESULT = {"checks": []}
NOTES = json.loads((ROOT / "still-ui" / "src" / "whatsnew.json").read_text(encoding="utf-8"))["2.10"]
POPUP = ".whatsnew"


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def env(version):
    return {**os.environ, "STILL_QA_WHATSNEW": "1", "STILL_QA_VERSION": version}


def saved(profile=PROFILE):
    for _ in range(50):
        try:
            return json.loads((profile / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.05)
    return {}


def shown(p):
    return js(p, f"!!document.querySelector('{POPUP}')")


def title(p):
    return js(p, f"document.querySelector('{POPUP} .whatsnew-title')?.innerText") or ""


def press(p, label):
    js(p, f"document.querySelector('{POPUP} [aria-label={json.dumps(label)}]')?.click()")
    time.sleep(.6)


def button(p, words):
    return js(p, f"(() => {{ const b = [...document.querySelectorAll('{POPUP} button')].find(b => b.innerText.trim().startsWith({json.dumps(words)})); b?.click(); return !!b }})()")


def main():
    PROFILE.mkdir(parents=True)
    # A profile from before What's New: no SeenVersion yet.
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}],
        "Preferences": {"AgentsEnabled": True, "Companions": CREW}}))

    # 2.0 has no highlights: nothing shows.
    p = launch(EXE, PROFILE, env("2.0.0"))
    try:
        time.sleep(4)
        check(not shown(p), "A release without highlights shows no popup")
    finally:
        rpc(p, "quit")
    time.sleep(1)

    # The update to 2.10: it shows once.
    p = launch(EXE, PROFILE, env("2.10.0"))
    try:
        check(until(lambda: shown(p), 10), "The first start after updating to 2.10 shows What's New")
        until(lambda: js(p, f"[...document.querySelectorAll('{POPUP} img')].every(i => i.complete)"), 5)
        time.sleep(.8)
        rpc(p, "capture", name="whatsnew-1.png")
        head = js(p, f"document.querySelector('{POPUP} .whatsnew-kicker')?.textContent") or ""
        check(head == "What's new in Still 2.10" and title(p) == NOTES[0]["title"] and NOTES[0]["text"] in (js(p, f"document.querySelector('{POPUP}').innerText") or ""),
              f"It opens on the first highlight, with its title and line ({head}; {title(p)})")
        dots = js(p, f"document.querySelectorAll('{POPUP} [role=tab]').length")
        check(3 <= len(NOTES) <= 5 and dots == len(NOTES), f"{len(NOTES)} highlights, one dot each ({dots})")
        img = js(p, f"(() => {{ const i = document.querySelector('{POPUP} img'); return i && [i.naturalWidth, i.getAttribute('src')] }})()") or [0, ""]
        check(img[0] > 0, f"Its screenshot loads ({img})")
        check(js(p, f"getComputedStyle(document.querySelector('{POPUP} .whatsnew-stage')).perspective") not in ("none", None), "The card sits on a 3D stage")
        press(p, "Next")
        check(title(p) == NOTES[1]["title"], "Next moves to the second")
        js(p, f"document.querySelector('{POPUP}').dispatchEvent(new KeyboardEvent('keydown', {{ key: 'ArrowRight', bubbles: true }}))")
        time.sleep(.6)
        check(title(p) == NOTES[2]["title"], "The right arrow key moves on")
        js(p, f"document.querySelector('{POPUP} [role=tab]:last-child')?.click()")
        time.sleep(.6)
        check(title(p) == NOTES[-1]["title"] and js(p, f"document.querySelector('{POPUP} [aria-label=Next]').disabled"), "A dot jumps to its highlight; Next stops at the last")
        for i, n in enumerate(NOTES):
            js(p, f"document.querySelectorAll('{POPUP} [role=tab]')[{i}]?.click()")
            time.sleep(.7)
            loaded = js(p, f"[...document.querySelectorAll('{POPUP} img')].some(i => i.naturalWidth > 0 && i.alt === {json.dumps(n['title'])})")
            if not loaded:
                check(False, f"The screenshot for {n['title']} loads")
        press(p, "Previous")
        check(title(p) == NOTES[-2]["title"], "Previous goes back")
        check(js(p, f"[...document.querySelectorAll('{POPUP} button')].some(b => b.innerText.includes('See everything'))"), "See everything links to the full list")
        check(not any("—" in (n["title"] + n["text"]) for n in NOTES), "No em dashes in the highlights")
        check(button(p, "Close") and until(lambda: not shown(p), 3), "Close closes it")
        check(until(lambda: saved().get("SeenVersion") == "2.10", 5), "and remembers 2.10 as seen")
    finally:
        rpc(p, "quit")
    time.sleep(1)

    # Next start: it stays closed, and Settings > About opens it again.
    p = launch(EXE, PROFILE, env("2.10.0"))
    try:
        time.sleep(4)
        check(not shown(p), "Closed once, it doesn't come back on the next start")
        send(p, "openPanel", name="settings", value="about")
        found = until(lambda: js(p, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.innerText.trim() === \"What's new in 2.10\"); b?.click(); return !!b })()"), 10)
        check(found and until(lambda: shown(p), 5) and title(p) == NOTES[0]["title"], "Settings > About has What's new in 2.10, which opens it again")
        rpc(p, "capture", name="whatsnew-again.png")
        button(p, "Close")
        check(until(lambda: not shown(p), 3) and saved().get("SeenVersion") == "2.10", "Closing it again changes nothing")
        errors = rpc(p).get("shellErrors") or js(p, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(p, "quit")
    time.sleep(1)

    # Updated with a web page open: the popup lifts the interface above the page, like any dialog (2.10.1 fix).
    WEB.mkdir()
    (WEB / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "SeenVersion": "2.0", "ActiveId": "w1",
        "Tabs": [{"Id": "w1", "Title": "Blank", "Url": "about:blank"}], "Preferences": {"AgentsEnabled": True, "Companions": CREW}}))
    p = launch(EXE, WEB, env("2.10.0"))
    try:
        check(until(lambda: shown(p), 10) and until(lambda: rpc(p)["overlay"] is True, 5), f"Over a web page it shows too, above the page (overlay {rpc(p)['overlay']})")
    finally:
        rpc(p, "quit")
    time.sleep(1)

    # A new install of 2.10: setup, not What's New.
    FRESH.mkdir()
    p = launch(EXE, FRESH, env("2.10.0"))
    try:
        until(lambda: js(p, "!!document.querySelector('.welcome.ob')"), 15)
        time.sleep(3)
        check(not shown(p), "A new install gets setup, not What's New")
    finally:
        rpc(p, "quit")
    check(until(lambda: saved(FRESH).get("SeenVersion") == "2.10", 5), "and counts 2.10 as seen")

    RUN.joinpath("result.json").write_text(json.dumps(RESULT, indent=1))
    failed = [c for c in RESULT["checks"] if not c["passed"]]
    print(f"Results: {len(RESULT['checks']) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
