"""Your models and every Model settings link (2.10 Stages 19 and 20).

- Every Model settings link, clicked for real, opens Settings, Models with Your models (the list of every app and adding
  one) right there, no side panel: the companion's Runs on picker, the main menu's Add a model (and on the Mac the menu
  bar's AI > Add a Model…), the message box's mode menu, model picker and effort picker, the side chat's Model settings
  button and its mode menu, a chat tab's menu and its details row, Setup's Pick another model, and the settings search.
- Main and More agents: Claude, ChatGPT, Grok and Gemini always show; OpenCode, Qwen Code, GitHub Copilot, DeepSeek
  Harness, Amp (Mac only), other agents and the API presets wait under More agents, in Your models and in the message
  box's model picker.
- Your models lists each app with its logo, its state on this computer (Logged in, Installed or Not installed) and Add or
  Set up, and DeepSeek and Other compatible API, added right there.
- Runs on, in a companion's Model tab: a styled picker with logos, checked when the tab opens (before the side chat was
  ever opened), listing only what can run: never an app that's Not installed or needs a sign-in.
- Still's own pages (New tab, Chat History, Companions, Skills, Library) show no scrollbar, and the wheel and the keys
  still scroll them.

No AI runs and nothing signs in: fake Gemini (signed in with Google), OpenCode (lists a model), Qwen Code (no sign-in
saved) and GitHub Copilot (no status command) on PATH, and a manifest app that isn't installed. The real apps on this
computer show as they are: the test never clicks their rows, their Set up or a Sign in. DeepSeek is saved with no key,
which sends nothing.

Run: python tests/desktop/models.py artifacts/Still-QA/Still.exe
Out: artifacts/models-*/
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("models-" + uuid.uuid4().hex[:8])
PROFILE, BIN = RUN / "profile", RUN / "bin"
FAKE = 'import sys\na = sys.argv[1:]\nif a[:1] == ["--version"]: print("1.0.0")\nelif a[:1] == ["models"]: print("anthropic/claude-sonnet-4")\n'
MATE = CREW[0]
MAIN = ["Claude", "ChatGPT", "Grok", "Gemini"]
MORE = ["OpenCode", "Qwen Code", "GitHub Copilot", "DeepSeek Harness"] + (["Amp"] if MAC else [])
APPS = MAIN + MORE
CANT_SAY = ("GitHub Copilot", "DeepSeek Harness", "Amp")  # no status command: installed is as far as Still can tell
results = []


def check(ok, name):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def press(p, sel):
    """Radix menus open on pointerdown."""
    return js(p, f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return false; e.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }})); return true }})()")


def menu_item(p, words):
    return js(p, f"""(() => {{ const e = [...document.querySelectorAll('[role=menuitem]')].find(e => e.innerText.trim().startsWith({json.dumps(words)})); if (!e) return false
     e.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }})); e.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, button: 0, pointerType: 'mouse' }})); e.click(); return true }})()""")


def menu_items(p):
    return js(p, "[...document.querySelectorAll('[role=menuitem]')].map(e => e.innerText.split('\\n')[0].trim())") or []


def click_text(p, sel, words):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(sel)})].find(e => e.innerText.trim().startsWith({json.dumps(words)})); e?.click(); return !!e }})()")


def escape(p):
    js(p, "(document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    time.sleep(.5)


def settings_models(p):
    """Settings is open on Models with Your models (every app, and adding one) right there."""
    return "Model" in (js(p, "document.querySelector('.set-nav-item[aria-current=page]')?.innerText") or "") and js(p, "!!document.querySelector('#set-ai .byo .byo-row')")


def close_settings(p):
    escape(p)
    return until(lambda: not js(p, "!!document.querySelector('.settings-dialog, .set-shell')"), 4)


def link(p, where, open_it, ok=None):
    """Clicks a Model settings link for real, then checks where it went."""
    close_settings(p)
    went = open_it()
    landed = until(ok or (lambda: settings_models(p)), 8)
    check(went and landed, f"{where} opens Settings, Models with Your models ({went}, {landed})")
    close_settings(p)


def from_menu(p, sel, words="Model settings"):
    def go():
        escape(p)
        if not press(p, sel) or not until(lambda: js(p, "!!document.querySelector('[role=menu][data-state=open]')"), 3):
            return False
        return menu_item(p, words)
    return go


def rows(p):
    """Each row of Your models: its name (without the Compatible tag), state, whether its logo is drawn, its buttons."""
    return js(p, """[...document.querySelectorAll('#set-ai .byo-row')].map(r => ({ name: r.querySelector('strong')?.childNodes[0]?.textContent.trim() ?? '',
     state: r.querySelector('.byo-name small')?.innerText.trim() ?? '', logo: !!r.querySelector('.ai-logo svg'), letter: !!r.querySelector('.ai-logo.is-letter'),
     acts: [...r.querySelectorAll(':scope > .byo-act')].map(b => b.innerText.trim()), how: r.querySelector('.byo-how')?.innerText ?? '' }))""") or []


def row(p, name):
    return next((r for r in rows(p) if r["name"] == name), None)


def act(p, name):
    """Clicks a row's Add or Set up."""
    return js(p, f"(() => {{ const r = [...document.querySelectorAll('#set-ai .byo-row')].find(r => r.querySelector('strong')?.childNodes[0]?.textContent.trim() === {json.dumps(name)}); const b = r?.querySelector(':scope > .byo-act'); if (!b) return false; b.click(); return true }})()")


def prefs():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
    except (OSError, ValueError, KeyError):
        return {}


def runs_on(p):
    """Opens the companion's Model tab and its Runs on picker; returns its items."""
    js(p, f"dispatchEvent(new CustomEvent('still-profile', {{ detail: {{ id: {json.dumps(MATE['Id'])}, tab: 'model' }} }}))")
    until(lambda: js(p, "!!document.querySelector('.profile-panel .runs-on')"), 10)
    press(p, ".profile-panel .runs-on")
    until(lambda: js(p, "!!document.querySelector('.runs-on-menu[data-state=open]')"), 3)
    return js(p, "[...document.querySelectorAll('.runs-on-menu [role=menuitem]')].map(e => e.innerText.trim())") or []


def close_panel(p):
    escape(p)
    js(p, "document.querySelector('.profile-head [aria-label=Close]')?.click()")
    until(lambda: not js(p, "!!document.querySelector('.profile-panel')"), 3)


def no_scrollbar(p):
    """New tab in a short window: no scrollbar, no gutter for one; the wheel and the keyboard scroll it."""
    page = "document.querySelector('.home-main')"
    if not MAC:
        rpc(p, "shellCdp", method="Emulation.setDeviceMetricsOverride", parameters={"width": 0, "height": 360, "deviceScaleFactor": 0, "mobile": False})
    time.sleep(.6)
    look = js(p, f"(m => m && [getComputedStyle(m).scrollbarWidth, m.offsetWidth - m.clientWidth, m.scrollHeight > m.clientHeight + 40])({page})") or []
    check(look[:2] == ["none", 0], f"New tab shows no scrollbar and keeps no room for one ({look})")
    if MAC:
        return
    try:
        check(look[2:] == [True], "(in a short window it has more to scroll)")
        mouse = lambda kind, x, y, **more: rpc(p, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": kind, "x": x, "y": y, **more})  # noqa: E731
        js(p, f"{page}.scrollTop = 0")
        x, y = js(p, f"(r => [r.left + 12, r.top + 60])({page}.getBoundingClientRect())")
        mouse("mouseWheel", x, y, deltaX=0, deltaY=240)
        wheel = until(lambda: js(p, f"{page}.scrollTop") > 0 and js(p, f"{page}.scrollTop"), 3)
        check(wheel, f"The wheel scrolls it ({wheel}px)")
        js(p, f"{page}.scrollTop = 0; document.activeElement?.blur()")
        mouse("mousePressed", x, y, button="left", buttons=1, clickCount=1)  # a click on the page itself, then the keys
        mouse("mouseReleased", x, y, button="left", buttons=0, clickCount=1)
        for kind in ("rawKeyDown", "keyUp"):
            rpc(p, "shellCdp", method="Input.dispatchKeyEvent", parameters={"type": kind, "key": "PageDown", "code": "PageDown", "windowsVirtualKeyCode": 34})
        keys = until(lambda: js(p, f"{page}.scrollTop") > 0 and js(p, f"{page}.scrollTop"), 3)
        check(keys, f"and so does Page Down ({keys}px)")
    finally:
        rpc(p, "shellCdp", method="Emulation.clearDeviceMetricsOverride", parameters={})
        js(p, f"{page}.scrollTop = 0")


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    (BIN / "fake.py").write_text(FAKE)
    for cli in ("gemini", "opencode", "qwen", "copilot"):
        launcher(BIN / cli, BIN / "fake.py")
    google = RUN / "gemini-home" / ".gemini"  # signed in with Google, as Gemini CLI saves it
    google.mkdir(parents=True)
    (google / "settings.json").write_text('{"security": {"auth": {"selectedType": "oauth-personal"}}}')
    (google / "oauth_creds.json").write_text("{}")
    (RUN / "qwen").mkdir()  # Qwen Code with no sign-in saved
    (PROFILE / "agents" / "fake-missing.json").write_text(json.dumps({"id": "fake-missing", "enabled": True, "name": "Fake missing",
        "command": str(BIN / "not-installed"), "install": "pip install not-a-real-agent", "run": ["run"]}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": [MATE], "AgentsEnabled": True,
        "AiHarness": "gemini", "AiModels": {"api-local20": "m-1"}, "Width": 1360, "Height": 900,
        "ApiProviders": [{"Id": "api-local20", "Kind": "openai", "Name": "Local box", "Url": "http://127.0.0.1:9/v1", "NoKey": True, "Models": [{"Id": "m-1", "Efforts": ["low", "high"]}]}]}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([{"Id": "c-m", "Title": "Trip plan", "Harness": "gemini", "Companion": MATE["Id"], "Started": True,
        "Updated": "2026-11-01T10:00:00Z", "Messages": [{"Role": "user", "Text": "Plan a trip"}, {"Role": "assistant", "Text": "Where to?"}]}]))
    env = {**os.environ, "PATH": str(BIN) + os.pathsep + os.environ.get("PATH", ""), "GEMINI_CLI_HOME": str(RUN / "gemini-home"), "QWEN_HOME": str(RUN / "qwen")}
    p = launch(EXE, PROFILE, env)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)

        # Runs on, before the side chat ever opened: the Model tab asks for a check, and OpenCode (logged in) is offered.
        check(not js(p, "!!document.querySelector('.ai-sidebar')"), "(the side chat hasn't been opened)")
        got = until(lambda: (o := runs_on(p)) and "OpenCode" in o and o, 40) or runs_on(p)
        check(js(p, "document.querySelector('.profile-tablist [aria-selected=true]')?.innerText") == "Model", "A companion's profile has a Model tab")
        check(js(p, "!document.querySelector('.profile-panel select, .profile-panel .companion-select')") and js(p, "!!document.querySelector('.profile-panel .runs-on .ai-logo')"),
              "Runs on is a styled picker with the app's logo, not a native list")
        check(not any("Your model" in g for g in got) and got[-1:] == ["Model settings…"], f"No Your model header, and Model settings… at the bottom ({got})")
        check("Gemini" in got and "OpenCode" in got, f"Runs on lists the apps that are logged in, OpenCode too, checked when the tab opened ({got})")
        check(not any(o.startswith(("Qwen Code", "Fake missing")) for o in got), f"and not one that needs a sign-in or isn't installed ({got})")
        check(js(p, "[...document.querySelectorAll('.runs-on-menu [role=menuitem]:not(.ai-pick-settings)')].every(e => e.querySelector('.ai-logo svg') || e.innerText.startsWith('Local box') && e.querySelector('.ai-logo.is-letter'))"), "each with its logo (an API provider with no logo of its own: its letter)")
        menu_item(p, "Model settings")
        check(until(lambda: settings_models(p) and not js(p, "!!document.querySelector('.profile-panel')"), 8), "Runs on's Model settings… opens Settings, Models with Your models, the panel closed")
        rpc(p, "capture", name="models-settings.png")

        # Your models, right in Settings: no Open button, no side panel to jump to.
        card = js(p, "document.getElementById('set-ai')?.closest('.set-group')?.innerText") or ""
        check(card.lower().startswith("your models") and "Model settings" not in card.split("\n")[1] and not js(p, "!!document.querySelector('.ai-sidebar')"),
              f"Settings, Models opens on Your models, with the list right there ({card[:60]!r})")
        # Main and More agents.
        shown = [r["name"] for r in rows(p)]
        fold = js(p, "document.querySelector('#set-ai .byo-more')?.innerText.trim()") or ""
        check(all(n in shown for n in MAIN) and not any(n in shown for n in MORE + ["DeepSeek", "Other compatible API", "Fake missing"]) and fold.startswith("More agents"),
              f"Claude, ChatGPT, Grok and Gemini show; the rest wait under More agents ({shown}, {fold!r})")
        js(p, "document.querySelector('#set-ai .byo-more')?.click()")
        ready = until(lambda: (r := rows(p)) and any(x["name"] == "OpenCode" and x["state"] == "Logged in" for x in r) and r, 30) or rows(p)
        names = [r["name"] for r in ready]
        check(all(n in names for n in APPS) and ("Amp" in names) == MAC and names.index("OpenCode") > max(names.index(n) for n in MAIN),
              f"More agents opens OpenCode, Qwen Code, GitHub Copilot, DeepSeek Harness{', Amp' if MAC else ' (no Amp on Windows)'} after the main four ({names})")
        check(names[-2:] == ["DeepSeek", "Other compatible API"], f"then the Compatible API presets: DeepSeek and any other ({names[-2:]})")
        check(ready and all(r["logo"] and not r["letter"] for r in ready if r["name"] in APPS + ["DeepSeek"]), "Each app and DeepSeek shows its own logo, never a letter")
        # The real apps answer later than the fakes: each check is the app's own status command or files.
        step = {"Logged in": [], "Installed": ["Set up"], "Not installed": ["Add"]}
        wrong = lambda rs: [(r["name"], r["state"], r["acts"]) for r in rs if r["name"] in APPS and (r["state"] not in step or r["acts"] != step[r["state"]])]  # noqa: E731
        ready = until(lambda: (r := rows(p)) and not wrong(r) and r, 40) or rows(p)
        clis, bad = [r for r in ready if r["name"] in APPS], wrong(ready)
        check(len(clis) == len(APPS) and not bad, f"Each app is Logged in, Installed (Set up) or Not installed (Add) ({[(r['name'], r['state']) for r in clis]}; wrong: {bad})")
        mine = {r["name"]: (r["state"], r["acts"]) for r in ready}
        check(mine.get("Gemini") == ("Logged in", []) and mine.get("OpenCode") == ("Logged in", []), f"Gemini and OpenCode are logged in ({mine.get('Gemini')}, {mine.get('OpenCode')})")
        check(mine.get("Qwen Code") == ("Installed", ["Set up"]), f"Qwen Code with no sign-in: Installed, Set up ({mine.get('Qwen Code')})")
        check(mine.get("GitHub Copilot") == ("Installed", ["Set up"]), f"GitHub Copilot, which can't say: Installed, Set up ({mine.get('GitHub Copilot')})")
        check(mine.get("Fake missing") == ("Not installed", ["Add"]), f"An app that isn't there: Not installed, Add ({mine.get('Fake missing')})")
        check(mine.get("DeepSeek") == ("API · Not added", ["Add"]) and (mine.get("Other compatible API") or ("", []))[1] == ["Add"], "The API presets: Not added, Add")

        # Set up and Add open the next step in place. Only opened: nothing in them is clicked.
        act(p, "Qwen Code")
        how = until(lambda: (r := row(p, "Qwen Code")) and r["how"], 5) or ""
        check("Run this in" in how and "\nqwen\n" in how and "Copy" in how and "I signed in" in how, f"Qwen Code's Set up: the command to sign in, Copy, I signed in ({how!r})")
        act(p, "GitHub Copilot")
        how = until(lambda: (r := row(p, "GitHub Copilot")) and r["how"], 5) or ""
        check("copilot login" in how and not (row(p, "Qwen Code") or {}).get("how"), f"GitHub Copilot's Set up: copilot login, and one step open at a time ({how!r})")
        if mine.get("DeepSeek Harness", ("",))[0] == "Not installed":
            act(p, "DeepSeek Harness")
            how = until(lambda: (r := row(p, "DeepSeek Harness")) and r["how"], 5) or ""
            check("npm install -g @deepseek-ai/dsh" in how, f"DeepSeek Harness's Add: DeepSeek's own install command ({how!r})")
        act(p, "Fake missing")
        how = until(lambda: (r := row(p, "Fake missing")) and r["how"], 5) or ""
        check("pip install not-a-real-agent" in how and "I installed it" in how, f"Add: the install command, Copy, I installed it ({how!r})")
        act(p, "Fake missing")
        check(until(lambda: not (row(p, "Fake missing") or {}).get("how"), 3), "Add again closes it")

        # DeepSeek: Add fills in the form right here, and saving it (no key) makes it a model in the list.
        act(p, "DeepSeek")
        form = "[...document.querySelectorAll('#set-ai .byo-row')].find(r => r.querySelector('.byo-how .api-form'))"
        values = until(lambda: js(p, f"[...({form})?.querySelectorAll('.byo-how input') ?? []].map(i => i.value)"), 5) or []
        check(values[:4] == ["DeepSeek", "https://api.deepseek.com", "", "deepseek-flash, deepseek-v4-pro"] and "1000000" in values,
              f"DeepSeek's Add opens the API form filled in, the key left to you ({values})")
        check(not js(p, f"!!({form})?.querySelector('.api-presets')"), "with no Start from row: it's DeepSeek's own")
        rpc(p, "capture", name="models-deepseek.png")
        js(p, f"[...({form}).querySelectorAll('button')].find(b => b.innerText.trim() === 'Add provider').click()")
        saved = until(lambda: next((x for x in prefs().get("ApiProviders", []) if x.get("Name") == "DeepSeek"), None), 15) or {}
        check(saved.get("Url") == "https://api.deepseek.com" and saved.get("NoKey") is True, f"It saves as a Compatible API with no key ({ {k: saved.get(k) for k in ('Url', 'NoKey')} })")
        after = until(lambda: (r := rows(p)) and any(x["name"] == "DeepSeek" and x["state"] == "Compatible API, no key" for x in r) and r, 15) or rows(p)
        check([r["name"] for r in after].count("DeepSeek") == 1 and not any(r["state"] == "API · Not added" for r in after),
              f"and it's in the list as a model, the preset gone ({[(r['name'], r['state']) for r in after][-4:]})")
        act(p, "Other compatible API")
        values = until(lambda: js(p, f"[...({form})?.querySelectorAll('.byo-how input') ?? []].map(i => i.value)"), 5) or []
        check(values and not any(values) and not js(p, f"!!({form})?.querySelector('.api-presets')"), f"Other compatible API opens an empty form ({values})")
        js(p, f"[...({form}).querySelectorAll('button')].find(b => b.innerText.trim() === 'Cancel').click()")
        check(until(lambda: not js(p, f"!!({form})"), 3), "Cancel closes it")
        check(js(p, "!!document.querySelector('#set-apis .api-providers')") and not js(p, "[...document.querySelectorAll('#set-apis button')].some(b => b.innerText.trim() === 'Add an API provider')"),
              "API providers has no second Add button: adding one is in Your models")
        states = {r["name"]: r["state"] for r in rows(p)}
        close_settings(p)

        # Runs on again, once every app has answered: only what's logged in (or can't say), never Not installed or a sign-in.
        got = runs_on(p)
        listed = [g for g in got if g != "Model settings…"]
        bad = [g for g in listed if g in states and not (states[g] == "Logged in" or (states[g] == "Installed" and g in CANT_SAY) or states[g].startswith("Compatible API"))]
        check(listed and not bad, f"Runs on, against Your models: each one is logged in, can't say, or an API added ({[(g, states.get(g)) for g in listed]}; wrong: {bad})")
        close_panel(p)

        # Every other Model settings link, clicked for real.
        def main_menu():
            press(p, "[aria-label=Menu]")
            until(lambda: menu_items(p), 5)
            items = menu_items(p)
            check("Add a model" in items and items.index("Add a model") < items.index("Settings"), f"The main menu has Add a model ({items[:5]})")
            return menu_item(p, "Add a model")
        link(p, "The main menu's Add a model", main_menu)
        if MAC:
            link(p, "The menu bar's AI > Add a Model…", lambda: rpc(p, "menu", menu="AI", item="Add a Model…").get("ok"))
        send(p, "new")
        until(lambda: js(p, "!!document.querySelector('.home-compose .composer')"), 10)
        time.sleep(.5)
        no_scrollbar(p)
        link(p, "New tab: the mode menu's Model settings…", from_menu(p, ".home-compose [aria-label='Companion and mode']"))
        send(p, "aiAdvanced", on=True)
        until(lambda: js(p, "!!document.querySelector(\".home-compose [aria-label='Effort']\")"), 8)
        # The model picker: the same split, More agents opening in place.
        press(p, ".home-compose [aria-label='Model']")
        until(lambda: js(p, "!!document.querySelector('.ai-model-menu[data-state=open]')"), 3)
        first = js(p, "[...document.querySelectorAll('.ai-model-menu [role=menuitem]')].map(e => e.innerText.trim().split('\\n')[0])") or []
        check(all(n in first for n in MAIN) and "More agents" in first and "OpenCode" not in first and first[-1:] == ["Model settings…"],
              f"The message box's model picker: the main four, More agents, Model settings… last ({first})")
        menu_item(p, "More agents")
        opened = until(lambda: (o := js(p, "[...document.querySelectorAll('.ai-model-menu[data-state=open] [role=menuitem]')].map(e => e.innerText.trim().split('\\n')[0])")) and "OpenCode" in o and o, 3) or []
        check("OpenCode" in opened and "DeepSeek Harness" in opened and opened.index("OpenCode") > opened.index("More agents"), f"More agents opens the others in place, the menu staying open ({opened})")
        escape(p)
        link(p, "New tab: the model picker's Model settings…", from_menu(p, ".home-compose [aria-label='Model']"))
        send(p, "aiHarness", harness="api-local20")  # a model with efforts; nothing is sent to it
        until(lambda: js(p, "!!document.querySelector(\".home-compose [aria-label='Effort']\")"), 8)
        link(p, "New tab: the effort picker's Model settings…", from_menu(p, ".home-compose [aria-label='Effort']"))
        send(p, "aiHarness", harness="gemini")
        send(p, "aiAdvanced", on=False)
        until(lambda: not js(p, "!!document.querySelector(\".home-compose [aria-label='Model']\")"), 5)
        send(p, "aiToggle")
        until(lambda: js(p, "!!document.querySelector(\".ai-sidebar [aria-label='Companion and mode']\")"), 10)
        link(p, "The side chat's Model settings button", lambda: js(p, "(() => { const b = document.querySelector('.ai-head [aria-label=\"Model settings\"]'); b?.click(); return !!b })()"))
        link(p, "The side chat's mode menu", from_menu(p, ".ai-sidebar [aria-label='Companion and mode']"))
        send(p, "aiToggle")
        # A chat in a tab: its menu and the details row.
        send(p, "chatOpen", id="c-m", newTab=True)
        until(lambda: js(p, "!!document.querySelector('.chat-side-profile, .chat-info-row')"), 10)
        if not js(p, "!!document.querySelector('.chat-info-row')"):
            js(p, "document.querySelector('[aria-label=\"Chat details\"]')?.click()")
        link(p, "A chat tab's details row", lambda: js(p, "(() => { const b = document.querySelector('.chat-info-row[title=\"Model settings\"]'); b?.click(); return !!b })()"))
        link(p, "A chat tab's menu, Model settings", from_menu(p, ".chat-side-profile"))
        # Setup, for an app that isn't installed (a fake): Pick another model.
        send(p, "select", id="home")  # off the chat tab, so the side chat can open
        until(lambda: rpc(p).get("activeId") == "home", 10)
        send(p, "aiHarness", harness="fake-missing")
        if not js(p, "!!document.querySelector('.ai-sidebar')"):
            send(p, "aiToggle")
        until(lambda: js(p, "!!document.querySelector('.ai-sidebar')"), 5)
        send(p, "aiNew")  # a new chat runs on the app just picked
        until(lambda: "Let's get Fake missing" in (js(p, "document.querySelector('.ai-sidebar')?.innerText") or ""), 10)
        link(p, "Setup's Pick another model", lambda: click_text(p, ".ai-sidebar button", "Pick another model"))
        send(p, "aiHarness", harness="gemini")
        if js(p, "!!document.querySelector('.ai-sidebar')"):
            send(p, "aiToggle")

        # The settings search: Your models, with the words people use.
        send(p, "openPanel", name="settings", value="general")
        until(lambda: js(p, "!!document.querySelector('[aria-label=\"Search settings\"]')"), 8)
        js(p, """(() => { const i = document.querySelector('[aria-label="Search settings"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, 'model settings')
         i.dispatchEvent(new Event('input', { bubbles: true })) })()""")
        hit = until(lambda: js(p, "[...document.querySelectorAll('.set-result strong')].map(e => e.innerText)"), 5) or []
        check("Your models" in hit, f"Searching settings for model settings finds Your models ({hit})")
        clicked = js(p, "(() => { const b = [...document.querySelectorAll('.set-result')].find(b => b.innerText.startsWith('Your models')); b?.click(); return !!b })()")
        check(clicked and until(lambda: js(p, "!!document.querySelector('#set-ai .byo-row')") and "Models" in (js(p, "document.querySelector('.set-title')?.innerText") or ""), 5),
              "and picking it shows Your models on the Models page")
        close_settings(p)
    finally:
        try:
            rpc(p, "quit")
        except RuntimeError:
            pass
        try:
            p.wait(timeout=20)
            exited = True
        except Exception:
            p.kill()
            exited = False
    check(exited, "Quit ends Still")
    print(f"{'PASSED' if all(results) else 'FAILED'} {sum(results)}/{len(results)} -> {RUN}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
