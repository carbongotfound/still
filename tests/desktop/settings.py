"""Settings: a left nav (General, Appearance, Companions, Models, Skills & plugins, Privacy & permissions, Shortcuts,
About), search that jumps to any setting and lights it up, grouped cards that save as you change them, and the old
page names (memory, plugins, permissions…) still landing on the right page. Then Chat titles under Models: the model
it names is the one the namer runs, Off keeps the first message, and the default is the AI's quickest model.

No AI plan is used: exchange.py's fake agent answers, and logs each prompt with the arguments it ran with.

Run: python tests/desktop/settings.py artifacts/Still-QA/Still.exe
Out: artifacts/settings-*/ (settings-*.png)
"""
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402
import exchange as X  # noqa: E402  its fake agent: what it says comes from plan.json; it logs prompts and arguments
import welcome as W  # noqa: E402  type_into

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("settings-" + uuid.uuid4().hex[:8])
BIN = X.BIN = RUN / "bin"
PROFILE = RUN / "profile"
FAILED = []
PAGES = ["General", "Appearance", "Companions", "Models", "Skills & plugins", "Privacy & permissions", "Shortcuts", "About"]
NAMER = "Write a title for a chat that starts with the message below"


def check(ok, name):
    print(("PASS " if ok else "FAIL ") + name, flush=True)
    if not ok:
        FAILED.append(name)


def shot(p, name):
    time.sleep(.8)
    rpc(p, "capture", name=name)
    if (PROFILE / name).exists():
        shutil.copy(PROFILE / name, RUN / name)


def page(p):
    return js(p, "document.querySelector('.set-title')?.innerText ?? ''") or ""


def nav(p, label):
    return js(p, f"(() => {{ const b = [...document.querySelectorAll('.set-nav-item')].find(b => b.innerText.trim() === {json.dumps(label)}); b?.click(); return !!b }})()")


def search(p, words):
    W.type_into(p, ".set-search input", words)
    return until(lambda: js(p, "[...document.querySelectorAll('.set-result')].map(r => r.querySelector('strong').innerText + ' · ' + r.querySelector('span').innerText)") or
                 js(p, "document.querySelector('.set-empty')?.innerText"), 3)


def lit(p, row):
    """The row a search jumped to: lit up, and on screen, with the dialog itself left where it was (its title in view)."""
    return until(lambda: js(p, f"(() => {{ const r = document.getElementById({json.dumps('set-' + row)}); if (!r?.classList.contains('set-flash')) return false; const b = r.getBoundingClientRect(), m = document.querySelector('.set-main').getBoundingClientRect(); return b.top >= m.top - 1 && b.bottom <= m.bottom + 1 && !document.querySelector('.settings-dialog').scrollTop }})()"), 3)


def escape(p):
    """Esc as a person presses it: Still's window takes it before the page and hands it to the shell."""
    rpc(p, "key", key="Escape", mods="None")
    time.sleep(.3)


def pick(p, label, option):
    """Picks an option from one of Settings' dropdowns."""
    js(p, f"document.querySelector('[aria-label={json.dumps(label)}]').dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }}))")
    return until(lambda: js(p, f"(() => {{ const o = [...document.querySelectorAll('[role=option]')].find(o => o.innerText.trim() === {json.dumps(option)}); o?.click(); return !!o }})()"), 5)


def options(p, label):
    """A dropdown's options, each after the group it's in (the AI), as "group: option"."""
    js(p, f"document.querySelector('[aria-label={json.dumps(label)}]').dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }}))")
    return until(lambda: js(p, "[...document.querySelectorAll('[role=option]')].map(o => { const g = o.closest('[role=group]')?.querySelector('[data-slot=select-label]')?.innerText.trim(); return (g ? g + ': ' : '') + o.innerText.trim() })"), 5) or []


def prefs():
    for _ in range(50):
        try:
            return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
        except (OSError, ValueError, KeyError):
            time.sleep(.1)
    return {}


def chats():
    for _ in range(50):
        try:
            return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.1)
    return []


def namings():
    return [q for q in X.prompts() if q["prompt"].startswith(NAMER)]


def new_chat(p, text):
    before = {c["Id"] for c in chats()}
    send(p, "new")
    until(lambda: js(p, "!!document.querySelector('.home-compose [aria-label=Message]')"), 10)
    send(p, "aiSend", text=text, home=True)
    return until(lambda: next((c for c in chats() if c["Id"] not in before), None), 10) or {}


def title_of(id):
    return next((c["Title"] for c in chats() if c["Id"] == id), "")


def main():
    BIN.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(X.FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json",
        "model": ["--model", "{model}"], "models": ["quick-1", "big-2"]}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": [{**CREW[0], "Crew": "research"}], "AgentsEnabled": True, "AiHarness": "fake",
        "Width": 1280, "Height": 860}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    X.plan({"nobody": [{"text": "Porto weekend plan"}, {"text": "\"Lisbon food list.\""}], "Maya": [{"text": "Sure."}]})
    p = launch(EXE, PROFILE, env={**os.environ, "STILL_QA_TITLES": "1"})  # test builds only name chats by default when asked to
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        send(p, "aiToggle"); send(p, "aiToggle")  # any AI op loads each AI's models in the background

        # The layout: a nav with every page, General first; each page is one click away.
        send(p, "openPanel", name="settings")
        until(lambda: js(p, "!!document.querySelector('.set-shell')"), 10)
        items = js(p, "[...document.querySelectorAll('.set-nav-item')].map(b => b.innerText.trim())") or []
        check(items == PAGES, f"The nav lists every page in order ({items})")
        check(page(p) == "General" and js(p, "document.querySelector('.set-nav-item[aria-current=page]')?.innerText.trim()") == "General", "It opens on General")
        check("save as you" in (js(p, "document.querySelector('.settings-dialog [data-slot=dialog-description]')?.innerText") or ""), "and says changes save as you make them")
        shot(p, "settings-general.png")
        saves, empty = [], []
        for label in PAGES:
            nav(p, label)
            until(lambda: page(p) == label, 3)
            if not js(p, "!!document.querySelector('.set-main .set-card')"):
                empty.append(label)
            saves += js(p, "[...document.querySelectorAll('.set-main button')].map(b => b.innerText.trim()).filter(t => /^(save|apply)$/i.test(t))") or []
            if label in ("Models", "Privacy & permissions", "Companions"):
                shot(p, "settings-" + label.split()[0].lower() + ".png")
        check(not empty, f"Every page opens with one click from the nav and shows its cards ({empty or 'all'})")
        check(not saves, f"No Save buttons: changes apply right away ({saves})")

        # Search: finds a setting by name or by a word about it, and jumps to it lit up.
        found = search(p, "dark")
        check(found and found[0] == "Theme · Appearance", f"Searching dark finds Theme, under Appearance ({found})")
        shot(p, "settings-search.png")
        W.key(p, "Enter")
        check(until(lambda: page(p) == "Appearance", 3) and lit(p, "theme"), "Enter jumps to the first one, lit up")
        check(not js(p, "document.querySelector('.set-search input').value"), "and clears the search")
        found = search(p, "chat titles")
        check("Chat titles · Models" in (found or []), f"Chat titles is found under Models ({found})")
        js(p, "[...document.querySelectorAll('.set-result')].find(r => r.innerText.includes('Chat titles'))?.click()")
        check(until(lambda: page(p) == "Models", 3) and lit(p, "titles"), "Clicking a result jumps to it")
        found = search(p, "logins")
        check("Passwords · Privacy & permissions" in (found or []), f"Searching logins finds Passwords ({found})")
        found = search(p, "private window" if MAC else "private tab")  # the Mac names it Private window
        check(any(f.endswith("· Shortcuts") for f in found or []), f"and shortcuts are found too ({found})")
        js(p, "document.querySelector('.set-result')?.click()")
        check(until(lambda: page(p) == "Shortcuts", 3) and until(lambda: js(p, "!!document.querySelector('.shortcut-row.set-flash')"), 3), "a shortcut jumps to its key")
        found = search(p, "zzqx")
        check(isinstance(found, str) and "Nothing matches" in found, "A search with no match says so")
        escape(p)
        check(until(lambda: not js(p, "document.querySelector('.set-search input')?.value"), 3) and js(p, "!!document.querySelector('.set-shell')"), "Escape clears the search and keeps Settings open")
        escape(p)
        check(until(lambda: not js(p, "!!document.querySelector('.set-shell')"), 5), "a second Escape closes it")

        # The old page names still land on their page.
        for old, label in (("memory", "Companions"), ("plugins", "Skills & plugins"), ("permissions", "Privacy & permissions"), ("ai", "Models")):
            send(p, "openPanel", name="settings", value=old)
            check(until(lambda: page(p) == label, 5), f"Opening Settings on {old} shows {label}")
            if old == "memory":
                check(until(lambda: js(p, "!!document.querySelector('#set-memory .memory-settings')"), 3), "Companions holds what they remember")

        # Chat titles: the quickest model by default, any model of the connected AIs, or Off.
        nav(p, "Models")
        until(lambda: page(p) == "Models", 3)
        check(js(p, "document.querySelector('[aria-label=\"Chat titles\"]')?.innerText.trim()") == "Quickest model", "Chat titles starts on the quickest model")
        listed = until(lambda: (o := options(p, "Chat titles")) and "Fake agent: big-2" in o and o, 15) or []
        shot(p, "settings-titles.png")
        check(listed[:1] == ["Quickest model"] and "Fake agent: quick-1" in listed and "Fake agent: big-2" in listed and listed[-1:] == ["Off (use first message)"], f"It lists every model of the connected AIs under its AI, and Off ({listed})")
        escape(p)
        check(js(p, "!!document.querySelector('.set-shell')") and not js(p, "document.querySelectorAll('[role=option]').length"), "Escape in the open list closes just the list")
        check(pick(p, "Chat titles", "big-2") and until(lambda: prefs().get("ChatTitles") == "fake/big-2", 5), "Picking big-2 saves it at once")
        reads = lambda: " ".join((js(p, "document.querySelector('[aria-label=\"Chat titles\"]')?.innerText") or "").split())
        check(until(lambda: reads() == "Fake agent · big-2", 3), f"and it reads Fake agent · big-2 ({reads()!r})")
        escape(p)
        until(lambda: not js(p, "!!document.querySelector('.set-shell')"), 5)

        first = new_chat(p, "can you help me plan a weekend in porto with my sister")
        check(until(lambda: title_of(first.get("Id")) == "Porto weekend plan", 15), f"A new chat is named by the model ({title_of(first.get('Id'))})")
        ran = namings()
        check(len(ran) == 1 and "--model big-2" in " ".join(ran[0]["args"]), f"on big-2, the model picked in Settings ({[r['args'] for r in ran]})")
        check("can you help me plan a weekend in porto" in (ran[0]["prompt"] if ran else ""), "from its first message")
        check(until(lambda: "Porto weekend plan" in (js(p, "document.body.innerText") or ""), 5), "and its tab shows the new name")

        send(p, "preference", key="chatTitles", value="off")
        until(lambda: prefs().get("ChatTitles") == "off", 5)
        second = new_chat(p, "second message stays as the title")
        time.sleep(4)
        check(title_of(second.get("Id")) == "second message stays as the title" and len(namings()) == 1, "Off keeps the first message, and nothing is asked to name it")

        send(p, "openPanel", name="settings", value="models")
        until(lambda: page(p) == "Models", 5)
        check(pick(p, "Chat titles", "Quickest model") and until(lambda: prefs().get("ChatTitles") == "", 5), "Quickest model goes back to the default")
        escape(p)
        third = new_chat(p, "where should we eat in lisbon")
        check(until(lambda: title_of(third.get("Id")) == "Lisbon food list", 15), f"The quickest model names it, without quotes or a full stop ({title_of(third.get('Id'))})")
        ran = namings()
        check(len(ran) == 2 and "--model" not in ran[1]["args"], "on the AI's quickest model (this one has no quicker one than its default)")
    finally:
        rpc(p, "quit")
        until(lambda: p.poll() is not None, 15)
    print(f"\n{len(FAILED)} failed" if FAILED else "\nAll settings checks passed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
