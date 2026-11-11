"""Switching chats: each opens at its end (where a running chat's live step is), or where you scrolled up to in it
yourself, in the side panel and on the full chat page alike. A fake app stands in for the AI.

Run: python tests/desktop/chat_switch.py artifacts/Still-QA/Still.exe
Out: artifacts/chat-switch-*/
"""
import json
from pathlib import Path
import shutil
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("chat-switch-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []
FAKE = textwrap.dedent(r'''
    import json, os, re, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    tail = sys.stdin.read()[-1500:]
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    slow = re.search(r"SLOW(\d+)", tail)
    if slow:
        open(os.path.join(here, "slow-started"), "w").close()
        time.sleep(int(slow.group(1)))
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Answered " + re.findall(r"WORD\w+", tail)[-1] if "WORD" in tail else "Done."}]}})
''')
PANEL, PAGE = ".ai-sidebar .ai-log", ".chat-view[data-mode=tab] .ai-log"


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        FAILED.append(label)


def long_chat(id, title):
    words = "The lamp throws a warm light across the desk, with no glare on the screen and a base that stays put. "
    messages = []
    for n in range(30):
        messages += [{"Role": "user", "Text": f"{title} question {n}"}, {"Role": "assistant", "Text": f"{title} answer {n}. " + words * 4}]
    return {"Id": id, "Title": title, "Harness": "fake", "Companion": "maya", "Updated": "2026-11-01T10:00:00Z", "Messages": messages}


def where(p, view):
    """The view's scroll: how far down, how far it goes, and whether the live step is in sight."""
    return json.loads(js(p, f"""(el => el ? JSON.stringify({{ top: Math.round(el.scrollTop), end: Math.round(el.scrollHeight - el.clientHeight),
        live: (l => !!l && l.getBoundingClientRect().top >= el.getBoundingClientRect().top - 1 && l.getBoundingClientRect().bottom <= el.getBoundingClientRect().bottom + 1)(el.querySelector('.ai-live')) }}) : 'null')(document.querySelector('{view}'))""") or "null")


def at_end(w):
    return bool(w) and w["end"] > 400 and w["end"] - w["top"] < 8


def shows(p, view, title):
    return js(p, f"(el => !!el && el.innerText.includes({json.dumps(title + ' answer 29')}))(document.querySelector('{view}'))")


def open_in_panel(p, id, title):
    send(p, "aiOpenChat", id=id)
    ok = until(lambda: shows(p, PANEL, title), 10)
    time.sleep(.6)
    return ok


def scroll_to(p, view, top):
    """As the user would: the view moves, and its scroll event follows."""
    js(p, f"document.querySelector('{view}').scrollTop = {top}")
    time.sleep(.4)


def main():
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    BIN.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([long_chat("lamps", "Lamps"), long_chat("chairs", "Chairs")]))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake", "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        send(p, "aiToggle")
        until(lambda: js(p, f"!!document.querySelector('{PANEL}')"), 10)

        check(open_in_panel(p, "lamps", "Lamps") and at_end(where(p, PANEL)), f"A chat opens in the side panel at its end ({where(p, PANEL)})")
        scroll_to(p, PANEL, 300)
        check(open_in_panel(p, "chairs", "Chairs") and at_end(where(p, PANEL)), f"Having scrolled up in another chat, the next one still opens at its end ({where(p, PANEL)})")
        check(open_in_panel(p, "lamps", "Lamps") and abs(where(p, PANEL)["top"] - 300) <= 2, f"Back to the first, it's where you scrolled up to ({where(p, PANEL)})")

        send(p, "chatOpen", id="lamps")
        check(until(lambda: shows(p, PAGE, "Lamps"), 10) and until(lambda: abs((where(p, PAGE) or {"top": -99})["top"] - 300) <= 2, 3), f"...and on its full chat page too ({where(p, PAGE)})")
        scroll_to(p, PAGE, 10 ** 6)
        send(p, "chatOpen", id="chairs")
        check(until(lambda: shows(p, PAGE, "Chairs"), 10) and until(lambda: at_end(where(p, PAGE)), 3), f"The other chat's page opens at its end ({where(p, PAGE)})")
        send(p, "chatOpen", id="lamps")
        check(until(lambda: shows(p, PAGE, "Lamps"), 10) and until(lambda: at_end(where(p, PAGE)), 3), f"Scrolled back down to its end, the first opens there again ({where(p, PAGE)})")

        # A running chat opens at its live step, however often you go away and come back.
        send(p, "new", url="about:blank")
        time.sleep(1)
        if not js(p, f"!!document.querySelector('{PANEL}')"):
            send(p, "aiToggle")
        open_in_panel(p, "chairs", "Chairs")
        send(p, "aiSend", text="WORDRUN SLOW25", companion="maya")
        check(until(lambda: (BIN / "slow-started").exists(), 30) and until(lambda: where(p, PANEL)["live"], 10), f"The chat works, its live step in sight ({where(p, PANEL)})")
        for n in range(3):
            open_in_panel(p, "lamps", "Lamps")
            check(at_end(where(p, PANEL)), f"Away {n + 1}: the other chat opens at its end ({where(p, PANEL)})")
            open_in_panel(p, "chairs", "Chairs")
            w = where(p, PANEL)
            check(at_end(w) and w["live"], f"Back {n + 1}: the running chat opens at its live step ({w})")
        check(until(lambda: shows(p, PANEL, "Answered WORDRUN") or "Answered WORDRUN" in (js(p, f"document.querySelector('{PANEL}').innerText") or ""), 40), "The run finishes")
        time.sleep(1)
        check(at_end(where(p, PANEL)), f"...with its answer in sight ({where(p, PANEL)})")
        open_in_panel(p, "lamps", "Lamps")
        open_in_panel(p, "chairs", "Chairs")
        check(at_end(where(p, PANEL)), f"The chat's own scrolling to its answer isn't kept as yours ({where(p, PANEL)})")

        errors = rpc(p).get("shellErrors")
        check(not errors, f"No interface errors ({errors})" if errors else "No interface errors")
    except Exception as ex:
        check(False, f"The run finished ({type(ex).__name__}: {ex})")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
    if FAILED:
        print(f"FAILED {len(FAILED)}: {FAILED} -> {RUN}")
    else:
        print("PASSED")
        shutil.rmtree(RUN, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
