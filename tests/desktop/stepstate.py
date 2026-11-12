"""A step says it happened only once it did. A fake model (fakemodels.py) calls click on a local page, through Still's real
permission card: while the card is open, after Not now, after Stop, and after Allow. Also the Make your own form's words
before a name is typed.

Run: python tests/desktop/stepstate.py artifacts/Still-QA/Still.exe
"""
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from fakemodels import Fake  # noqa: E402
from qa import press_ready, CREW, js, launch, rpc, send, text, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("stepstate-" + uuid.uuid4().hex[:8])
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
FAILED = []
KEY = "sk-fake-" + uuid.uuid4().hex


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def prefs():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
    except (OSError, ValueError, KeyError):
        return {}


def row(p):
    """The last turn's work: its latest step's words, every step, and which state it shows (a done turn folds, so textContent)."""
    return json.loads(js(p, """JSON.stringify((() => {
        const g = [...document.querySelectorAll('.chat-view .ai-work')].pop()
        if (!g) return null
        const steps = [...g.querySelectorAll('.ai-step-line')].map(e => e.textContent)
        return { line: steps[steps.length - 1] ?? '', steps, tick: !!g.querySelector('.ai-steps-state.is-done'), failed: !!g.querySelector('.ai-steps-state.is-failed'), spinning: !!g.querySelector('.ai-work-row.is-live') }
    })())""") or "null")


def card(p):
    return js(p, "!!document.querySelector('.approve-card .approve-steps li')")


def press(p, words):
    return press_ready(p, f"[...document.querySelectorAll('.approve-card button')].find(b => b.innerText.trim() === {json.dumps(words)})")


def idle(p):
    return until(lambda: not js(p, "!!document.querySelector('[aria-label=Stop]')"), 30)


def main():
    fake = Fake(key=KEY)
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True,
        "Permissions": [{"Site": "", "Action": a, "Companion": "", "Mode": m} for a, m in (("read", "always"), ("navigate", "always"), ("interact", "chat"))]},  # a chat with no companion clicks without asking now: this one asks
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        send(p, "aiToggle")
        send(p, "apiSave", id="", kind="openai", name="Fake", url=fake.url + "/v1", key=KEY, models=[], priceIn=0, priceOut=0, limit=0, context=0)
        provider = until(lambda: next((q for q in prefs().get("ApiProviders") or [] if q["Models"]), None), 20)
        check(provider, "A fake provider is set up")
        send(p, "aiHarness", harness=provider["Id"])
        send(p, "aiNew")
        click = 'CALL open_tab {"url": "' + fake.url + '/page"}\nCALL click {"text": "Press me"}'

        # The card is open: nothing has been clicked yet.
        send(p, "aiSend", text="Deny this\n" + click)
        check(until(lambda: card(p), 30), "A click waits on the permission card")
        time.sleep(.5)
        r = row(p)
        check(r and r["line"] == "Clicking “Press me”" and r["spinning"] and not r["tick"], f"While the card is open the step is still going ({r})")
        check("Clicked" not in text(p), "and nothing says Clicked")

        # Not now.
        check(press(p, "Not now"), "Not now is pressed")
        idle(p)
        r = until(lambda: (x := row(p)) and x["failed"] and x, 15)
        check(r and r["line"] == "Didn't click “Press me”" and not r["tick"], f"After Not now the step says it didn't happen, with no tick ({r})")
        check("Clicked" not in text(p), "and nothing says Clicked")
        check(not any(t["Title"] == "Pressed" for t in rpc(p)["tabs"]), "and the page wasn't clicked")

        # Stop while the card is open.
        send(p, "aiNew")
        send(p, "aiSend", text="Stop this\n" + click)
        check(until(lambda: card(p), 30), "The card is open again")
        send(p, "aiStop")
        idle(p)
        r = until(lambda: (x := row(p)) and x["failed"] and x, 15)
        check(r and r["line"] == "Stopped clicking “Press me”" and not r["tick"], f"Stop during the card: the step says it stopped, with no tick ({r})")
        check("Clicked" not in text(p), "and nothing says Clicked")
        check(not any(t["Title"] == "Pressed" for t in rpc(p)["tabs"]), "and the page wasn't clicked")

        # Allow: now it did happen.
        send(p, "aiNew")
        send(p, "aiSend", text="Allow this\n" + click)
        check(until(lambda: card(p), 30), "The card is open a third time")
        check(press(p, "Allow"), "Allow is pressed")
        check(until(lambda: any(t["Title"] == "Pressed" for t in rpc(p)["tabs"]), 20), "The click runs")
        idle(p)
        r = until(lambda: (x := row(p)) and x["tick"] and x, 15)
        check(r and r["line"] == "Clicked “Press me”" and not r["failed"], f"Only now it says Clicked, with a tick ({r})")

        # Allowed, and the click reaches the button, which does nothing: no Clicked and no tick.
        send(p, "aiNew")
        send(p, "aiSend", text="Allow this\n" + click.replace("Press me", "Do nothing"))
        check(until(lambda: card(p), 30), "The card is open for a button that does nothing")
        check(press(p, "Allow"), "Allow is pressed")
        idle(p)
        r = until(lambda: (x := row(p)) and x["failed"] and x, 15)
        check(r and r["line"] == "No change after clicking “Do nothing”" and not r["tick"], f"A click that changed nothing says so, with no tick ({r})")
        check("Clicked “Do nothing”" not in text(p), "and nothing says Clicked")

        # Make your own, before a name is typed.
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.mate-switch-more[aria-label=\"Hire a companion\"]')"), 10)
        js(p, "document.querySelector('.mate-switch-more[aria-label=\"Hire a companion\"]').click()")
        until(lambda: js(p, "!!document.querySelector('.companion-library')"), 5)
        js(p, "[...document.querySelectorAll('.library-more .role-head')].find(e => e.innerText.includes('Make your own'))?.click()")
        hint = until(lambda: js(p, "[...document.querySelectorAll('.profile-panel textarea')].map(t => t.placeholder).find(t => t.includes('inside Still'))"), 10) or ""
        check(hint.startswith("What your companion does for you inside Still."), f"With no name the form reads right ({hint[:50]})")
        words = js(p, "document.querySelector('.profile-panel').innerText") or ""
        check("they does" not in hint and "they talks" not in words and "they thinks" not in words, "and no line reads they does or they talks")
    finally:
        if p.poll() is None:
            p.kill()
        fake.stop()
        shutil.rmtree(RUN, ignore_errors=True)
    print(f"{len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)


main()
