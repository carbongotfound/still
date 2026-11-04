"""Adding a model (2.10 Stage 19). The main menu's Add a model, and on the Mac the menu bar's AI > Add a Model…, open
Model settings in one click. It lists every app Still supports, each with its logo, its state on this computer (Logged
in, Installed or Not installed) and Add or Set up, then the Compatible API presets, added right there. A companion's
Model tab lists under Runs on every app that's logged in, from a check that runs when the tab opens, before the side
chat was ever opened. And the words: Model settings, Your models, the Model tab, Model settings… in the message box.

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
APPS = ["Claude", "ChatGPT", "Grok", "Gemini", "OpenCode", "Qwen Code", "GitHub Copilot"] + (["Amp"] if MAC else [])
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


def escape(p):
    js(p, "(document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    time.sleep(.5)


def head(p):
    return js(p, "document.querySelector('.ai-head .ai-title')?.innerText.trim() ?? ''") or ""


def rows(p):
    """Each row of the model list: its name (without the Compatible tag), state, whether its logo is drawn, its buttons."""
    return js(p, """[...document.querySelectorAll('.ai-sidebar .byo-row')].map(r => ({ name: r.querySelector('strong')?.childNodes[0]?.textContent.trim() ?? '',
     state: r.querySelector('.byo-name small')?.innerText.trim() ?? '', logo: !!r.querySelector('.ai-logo svg'), letter: !!r.querySelector('.ai-logo.is-letter'),
     acts: [...r.querySelectorAll(':scope > .byo-act')].map(b => b.innerText.trim()), how: r.querySelector('.byo-how')?.innerText ?? '' }))""") or []


def row(p, name):
    return next((r for r in rows(p) if r["name"] == name), None)


def act(p, name):
    """Clicks a row's Add or Set up."""
    return js(p, f"(() => {{ const r = [...document.querySelectorAll('.ai-sidebar .byo-row')].find(r => r.querySelector('strong')?.childNodes[0]?.textContent.trim() === {json.dumps(name)}); const b = r?.querySelector(':scope > .byo-act'); if (!b) return false; b.click(); return true }})()")


def prefs():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
    except (OSError, ValueError, KeyError):
        return {}


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
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
        "AiHarness": "gemini", "Width": 1360, "Height": 900}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "PATH": str(BIN) + os.pathsep + os.environ.get("PATH", ""), "GEMINI_CLI_HOME": str(RUN / "gemini-home"), "QWEN_HOME": str(RUN / "qwen")}
    p = launch(EXE, PROFILE, env)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)

        # Runs on, before the side chat ever opened: the Model tab asks for a check, and OpenCode (logged in) is offered.
        check(not js(p, "!!document.querySelector('.ai-sidebar')"), "(the side chat hasn't been opened)")
        js(p, f"dispatchEvent(new CustomEvent('still-profile', {{ detail: {{ id: {json.dumps(MATE['Id'])}, tab: 'model' }} }}))")
        options = lambda: js(p, "[...document.querySelectorAll('.profile-panel .companion-select option')].map(o => o.innerText)") or []  # noqa: E731
        got = until(lambda: (o := options()) and "OpenCode" in o and o, 40) or options()
        check(js(p, "document.querySelector('.profile-tablist [aria-selected=true]')?.innerText") == "Model", "A companion's profile has a Model tab")
        check(got[:1] and got[0].startswith("Your model (Gemini)"), f"Runs on starts with Your model ({got[:1]})")
        check("Gemini" in got and "OpenCode" in got, f"Runs on lists every app that's logged in, OpenCode too, checked when the tab opened ({got})")
        check(not any(o.startswith(("Qwen Code", "GitHub Copilot", "Fake missing")) for o in got), f"and not the ones that aren't ({got})")
        js(p, "document.querySelector('.profile-head [aria-label=Close]')?.click()")
        time.sleep(.6)

        # The main menu: Add a model opens Model settings in one click.
        press(p, "[aria-label=Menu]")
        until(lambda: menu_items(p), 5)
        items = menu_items(p)
        check("Add a model" in items and items.index("Add a model") < items.index("Settings"), f"The main menu has Add a model ({items[:5]})")
        menu_item(p, "Add a model")
        check(until(lambda: head(p) == "Model settings", 10), f"Add a model opens the side chat on Model settings ({head(p)!r})")
        check("Your models" in (js(p, "document.querySelector('.ai-pane h4')?.innerText") or ""), "headed Your models")
        rpc(p, "capture", name="models-panel.png")

        if MAC:  # the menu bar: AI > Add a Model…, with the side chat closed first
            js(p, "document.querySelector('.ai-head [aria-label=\"Close chat\"]')?.click()")
            until(lambda: not js(p, "!!document.querySelector('.ai-sidebar')"), 5)
            check(rpc(p, "menu", menu="AI", item="Add a Model…").get("ok"), "The menu bar's AI menu has Add a Model…")
            check(until(lambda: head(p) == "Model settings", 10), f"and it opens Model settings too ({head(p)!r})")

        # Every app in one list, each with its logo, its state and its next step.
        ready = until(lambda: (r := rows(p)) and any(x["name"] == "OpenCode" and x["state"] == "Logged in" for x in r) and r, 30) or rows(p)
        names = [r["name"] for r in ready]
        text = js(p, "document.querySelector('.ai-sidebar')?.innerText") or ""
        check("More agents" not in text and all(n in names for n in APPS) and ("Amp" in names) == MAC,
              f"Every app is listed, none behind More agents{', Amp too' if MAC else ', no Amp on Windows'} ({names})")
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
        act(p, "Fake missing")
        how = until(lambda: (r := row(p, "Fake missing")) and r["how"], 5) or ""
        check("pip install not-a-real-agent" in how and "I installed it" in how, f"Add: the install command, Copy, I installed it ({how!r})")
        act(p, "Fake missing")
        check(until(lambda: not (row(p, "Fake missing") or {}).get("how"), 3), "Add again closes it")

        # DeepSeek: Add fills in the form right here, and saving it (no key) makes it a model in the list.
        act(p, "DeepSeek")
        form = "[...document.querySelectorAll('.ai-sidebar .byo-row')].find(r => r.querySelector('.byo-how .api-form'))"
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

        # The words: Model settings in the side chat and the message box, Your models in Settings.
        js(p, "document.querySelector('.ai-head [aria-label=Back]')?.click()")
        until(lambda: js(p, "!!document.querySelector('.ai-sidebar .mode-chip')"), 10)
        check(js(p, "!!document.querySelector('.ai-head [aria-label=\"Model settings\"]') && !document.querySelector('[aria-label=\"AI settings\"]')"), "The side chat's settings button is Model settings")
        press(p, ".ai-sidebar .mode-chip")
        until(lambda: js(p, "!!document.querySelector('.mode-menu')"), 5)
        last = js(p, "[...document.querySelectorAll('.mode-menu [role=menuitem]')].pop()?.innerText.trim()")
        check(last == "Model settings…", f"The message box's mode menu ends with Model settings… ({last!r})")
        menu_item(p, "Model settings")
        check(until(lambda: js(p, "document.querySelector('.profile-tablist [aria-selected=true]')?.innerText") == "Model", 5), "which opens the companion's Model tab")
        js(p, "document.querySelector('.profile-head [aria-label=Close]')?.click()")
        time.sleep(.6)
        send(p, "openPanel", name="settings", value="models")
        card = until(lambda: js(p, "document.getElementById('set-ai')?.closest('.set-group')?.innerText"), 10) or ""
        check(card.lower().startswith("your models\nmodel settings"), f"Settings → Models: Your models, with Model settings ({card[:40]!r})")
        send(p, "openPanel", name="")
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
