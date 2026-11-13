"""The side panel's Chat history: a button in its header opens a searchable list of recent chats, each with its title,
its companion and when it was last used, a spinner on a chat at work. Arrows and Enter pick one, which opens in that tab's
side panel only; Esc closes the list and leaves the panel open. Clicks and keys are real input. A fake app stands in for
the AI.

Run: python tests/desktop/chat_history_panel.py artifacts/Still-QA/Still.exe
Out: artifacts/chat-history-panel-*/ (kept when something fails), artifacts/screens/chat-history-panel-*.png
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys
import textwrap
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, screens, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("chat-history-panel-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []
FAKE = textwrap.dedent(r'''
    import json, re, sys, time
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    tail = sys.stdin.read()[-1500:]
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    slow = re.search(r"SLOW(\d+)", tail)
    if slow: time.sleep(int(slow.group(1)))
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}})
''')
PANEL = ".ai-sidebar .ai-log"
BUTTON = '.ai-head button[aria-label="Chat history"]'
KEYS = {"ArrowDown": 40, "ArrowUp": 38, "Enter": 13, "Escape": 27}


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        FAILED.append(label)


def chat(id, title, companion, hours):
    when = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"Id": id, "Title": title, "Harness": "fake", "Companion": companion, "Updated": when,
            "Messages": [{"Role": "user", "Text": f"{title} question"}, {"Role": "assistant", "Text": f"{title} answer"}]}


def click(p, sel):
    at = js(p, f"(r => r && [r.x + r.width / 2, r.y + r.height / 2])(document.querySelector({json.dumps(sel)})?.getBoundingClientRect())")
    for kind in ("mousePressed", "mouseReleased"):
        rpc(p, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": at[0], "y": at[1], "button": "left", "buttons": 1 if kind == "mousePressed" else 0, "clickCount": 1})
    time.sleep(.5)


def key(p, name):
    for kind in ("rawKeyDown", "keyUp"):
        rpc(p, "shellCdp", method="Input.dispatchKeyEvent", parameters={"type": kind, "key": name, "code": name, "windowsVirtualKeyCode": KEYS[name]})
    time.sleep(.35)


def type_(p, words):
    rpc(p, "shellCdp", method="Input.insertText", parameters={"text": words})
    time.sleep(.4)


def rows(p):
    """The list as shown: each row's chat, title, time, and whether it has a companion face, a spinner, the check, the selection."""
    return js(p, """[...document.querySelectorAll('.chat-picker [data-chat]')].map(r => ({ id: r.dataset.chat, title: r.querySelector('b')?.textContent,
        time: r.querySelector('small')?.textContent ?? null, face: !!r.querySelector('.mascot, canvas'),
        spinner: !!r.querySelector('[data-slot=spinner]'), current: r.dataset.checked === 'true', selected: r.getAttribute('aria-selected') === 'true' }))""") or []


def picker_open(p):
    return js(p, "!!document.querySelector('.chat-picker')")


def panel_title(p):
    return js(p, "document.querySelector('.ai-sidebar .ai-title')?.textContent ?? ''")


def focused(p):
    return js(p, "(a => a?.getAttribute('aria-label') ?? a?.tagName ?? '')(document.activeElement)")


def main():
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    BIN.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    crew = [c["Id"] for c in CREW]
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([chat("lamps", "Desk lamps", crew[0], 1), chat("chairs", "Office chairs", crew[1 % len(crew)], 5),
        chat("trip", "Lisbon trip", crew[0], 30), chat("taxes", "Tax receipts", crew[2 % len(crew)], 24 * 9)]))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake", "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "a", "Title": "A", "Url": "about:blank"}, {"Id": "b", "Title": "B", "Url": "about:blank"}], "ActiveId": "a"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        send(p, "aiToggle")
        check(until(lambda: js(p, f"!!document.querySelector({json.dumps(BUTTON)})"), 10), "The side panel's header has a Chat history button")
        icons = js(p, "[...document.querySelectorAll('.ai-head button[aria-label]:not(.ai-head-buddy)')].map(b => b.getAttribute('aria-label')).join(',')")
        check(icons == "Open as a tab,Chat history,New chat,Model settings,Close chat", f"...beside expand, new chat, settings and close ({icons})")

        click(p, BUTTON)
        check(until(lambda: picker_open(p), 3), "A click opens the list")
        check(focused(p) == "Search chats", f"...its search box ready to type in (focus on {focused(p)!r})")
        r = rows(p)
        check([x["title"] for x in r] == ["Desk lamps", "Office chairs", "Lisbon trip", "Tax receipts"], f"Recent chats, newest first ({[x['title'] for x in r]})")
        check(all(x["face"] for x in r) and [x["time"] for x in r] == ["1h", "5h", "1d", "9d"], f"...each with its companion and when it was last used ({[(x['face'], x['time']) for x in r]})")
        heads = js(p, "[...document.querySelectorAll('.chat-picker [cmdk-group-heading]')].map(h => h.textContent)")
        check(heads[0] == "Today" and heads[-1] == "Earlier", f"...in day groups as on the Chat History page ({heads})")
        screens(p, PROFILE, "chat-history-panel-list")

        type_(p, "chai")
        check([x["title"] for x in rows(p)] == ["Office chairs"], f"Typing searches the titles ({[x['title'] for x in rows(p)]})")
        type_(p, "zzz")
        check(not rows(p) and "No chats match" in (js(p, "document.querySelector('.chat-picker')?.innerText ?? ''") or ""), "No match says so")

        key(p, "Escape")
        check(not picker_open(p) and js(p, "!!document.querySelector('.ai-sidebar')"), "Esc closes the list, the side panel stays open")
        check(focused(p) == "Chat history", f"...and puts focus back on its button ({focused(p)!r})")

        click(p, BUTTON)
        until(lambda: picker_open(p), 3)
        check(rows(p) and rows(p)[0]["selected"], "Open again, the search is empty and the first chat is selected")
        key(p, "ArrowDown")
        key(p, "ArrowDown")
        sel = [x["title"] for x in rows(p) if x["selected"]]
        check(sel == ["Lisbon trip"], f"Arrow keys move the selection ({sel})")
        key(p, "ArrowUp")
        check([x["title"] for x in rows(p) if x["selected"]] == ["Office chairs"], "...up and down")
        key(p, "Enter")
        check(until(lambda: not picker_open(p) and panel_title(p) == "Office chairs" and "Office chairs answer" in (js(p, f"document.querySelector('{PANEL}')?.innerText ?? ''") or ""), 5),
              f"Enter opens it in the side panel and closes the list ({panel_title(p)!r})")
        click(p, BUTTON)
        until(lambda: picker_open(p), 3)
        check([x["title"] for x in rows(p) if x["current"]] == ["Office chairs"], "The list marks the chat the panel shows")
        click(p, ".ai-sidebar [role=textbox]")  # the message box, below the list
        check(until(lambda: not picker_open(p), 2), "A click outside closes the list")

        # Another tab: its panel keeps its own chat, and a chat picked there opens there only.
        send(p, "select", id="b")
        check(until(lambda: rpc(p)["activeId"] == "b", 5) and until(lambda: panel_title(p) != "Office chairs", 3), f"Tab B's side panel doesn't show tab A's pick ({panel_title(p)!r})")
        click(p, BUTTON)
        until(lambda: picker_open(p), 3)
        click(p, '.chat-picker [data-chat="trip"]')
        check(until(lambda: panel_title(p) == "Lisbon trip", 5), "A click on a chat opens it in tab B's panel")
        send(p, "aiSend", text="WORKING SLOW25", companion=crew[0])
        time.sleep(1.5)
        send(p, "select", id="a")
        check(until(lambda: rpc(p)["activeId"] == "a", 5) and until(lambda: panel_title(p) == "Office chairs", 3), f"Back in tab A, its panel still shows its own pick ({panel_title(p)!r})")

        click(p, BUTTON)
        check(until(lambda: picker_open(p) and any(x["spinner"] for x in rows(p)), 5), "A chat at work shows a spinner in the list")
        r = rows(p)
        check([x["title"] for x in r if x["spinner"]] == ["Lisbon trip"] and next(x for x in r if x["title"] == "Lisbon trip")["time"] is None,
              f"...in place of its time, the others keep theirs ({[(x['title'], x['spinner'], x['time']) for x in r]})")
        screens(p, PROFILE, "chat-history-panel-working")
        click(p, BUTTON)
        check(until(lambda: not picker_open(p), 2), "Its button closes the list again")

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
