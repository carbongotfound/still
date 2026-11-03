"""API providers end to end against the local fake model server (tests/desktop/fakemodels.py), never a real provider:
adding one, the key kept out of every file but its own store, Test connection, chats with tools, a question and an
approval through Still's MCP server, Stop, the step cap, a rate limit, a refused key, model fallback, trimming,
spending and the monthly limit, Anthropic-compatible too, incognito, and no key prompts for people on a plan.

Run: python tests/desktop/apiproviders.py artifacts/Still-QA/Still.exe
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from fakemodels import Fake  # noqa: E402
from qa import CREW, MAC, js, launch, rpc, send, text, until  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts" / ("apiproviders-" + uuid.uuid4().hex[:8])
EXE = Path(sys.argv[1]).resolve()
PROFILE = RUN / "profile"
RESULT = {"exe": str(EXE), "checks": []}
K1 = "sk-fake-" + uuid.uuid4().hex + "WXYZ"
K2 = "sk-ant-fake-" + uuid.uuid4().hex + "QRST"
WRONG = "sk-wrong-" + uuid.uuid4().hex + "ZZZZ"


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def prefs():
    try:
        return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
    except (OSError, ValueError, KeyError):
        return {}


def provider(name):
    return next((p for p in prefs().get("ApiProviders") or [] if p["Name"] == name), None)


FORMS = {}


def save(p, name, **changes):
    """Settings' form, as the shell sends it: every field each time."""
    form = FORMS.setdefault(name, {"kind": "openai", "name": name, "url": "", "key": "", "models": [], "priceIn": 3, "priceOut": 15, "limit": 0, "context": 0})
    form.update(changes)
    known = provider(name)
    send(p, "apiSave", id=known["Id"] if known else "", **form)
    form["key"] = ""


def chat_text(p):
    return js(p, "[...document.querySelectorAll('.ai-msg, .ai-note, .chat-error, .ai-error')].map(e => e.innerText).join('\\n')") or text(p)


def idle(p, seconds=60):
    return until(lambda: not js(p, "!!document.querySelector('[aria-label=Stop]')"), seconds)


def ask(p, words, seconds=30, until_text=None):
    send(p, "aiSend", text=words)
    time.sleep(.3)
    if until_text:
        return until(lambda: (t := text(p)) and until_text in t and t, seconds)
    idle(p, seconds)
    return text(p)


def picker(p):
    """The AI picker in the chat panel's AI settings, after a recheck."""
    send(p, "aiCheck")
    time.sleep(1.5)
    js(p, "document.querySelector('[aria-label=\"AI settings\"]')?.click()")
    shown = until(lambda: js(p, "document.querySelector('.ai-picker')?.innerText"), 10) or ""
    until(lambda: js(p, "document.querySelector('.ai-head [aria-label=Back]')?.click(), !document.querySelector('.ai-head [aria-label=Back]')"), 10)
    return shown


def secrets_on_disk():
    """Every file in the profile holding a key in plain text (UTF-8 or UTF-16), apart from its own store."""
    found = []
    for f in PROFILE.rglob("*"):
        if not f.is_file() or f.parent.name == "api-keys":
            continue
        try:
            data = f.read_bytes()
        except OSError:
            continue
        for k in (K1, K2, WRONG):
            if k.encode() in data or k.encode("utf-16-le") in data:
                found.append(f"{f.relative_to(PROFILE)}: {k[:10]}")
    return found


def main():
    fake = Fake(key=K1)
    ant = Fake(key=K2)
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True,
        "Permissions": [{"Site": "", "Action": a, "Companion": "", "Mode": "always"} for a in ("read", "navigate")]},
        "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = {**os.environ, "OPENAI_API_KEY": "sk-env-not-real", "ANTHROPIC_API_KEY": "sk-env-not-real", "STILL_QA_TITLES": "1"}
    p = launch(EXE, PROFILE, env)
    try:
        # People on a plan never see a key prompt.
        send(p, "aiToggle")
        send(p, "aiCheck")
        shown = until(lambda: (t := text(p)) and "More agents" in t and t, 30) or ""
        check("Gemini" in shown and "API provider" not in shown and "Needs a key" not in shown and "No API key needed" in shown, "The AI picker lists Gemini and asks nobody for a key")
        send(p, "openPanel", name="settings", value="models")
        page = until(lambda: (t := text(p)) and "Add an API provider" in t and t, 15) or ""
        check("Add an API provider" in page and "your provider bills you per use" in page and "Signing in with a plan doesn't need this" in page, "Settings → Models has API providers, saying who bills and that plans don't need it")

        # Adding one: the key goes to its store, the models come from the provider's list.
        save(p, "Fake OpenAI", url=fake.url + "/v1", key=K1)
        added = until(lambda: (q := provider("Fake OpenAI")) and len(q["Models"]) == 3 and q, 20)
        check(added and [m["Id"] for m in added["Models"]] == ["fake-small", "fake-large", "plain-model"], "Adding a provider loads its model list")
        pid = added["Id"] if added else ""
        card = until(lambda: (t := text(p)) and "Key ending in WXYZ" in t and t, 10) or ""
        check("Compatible" in card and "Verified" not in card and "Supported" not in card and "Tested" not in card, "It's labelled Compatible, nothing more")
        check(K1 not in card and K1 not in (js(p, "document.documentElement.outerHTML") or ""), "The interface shows only the key's last four characters")
        store = PROFILE / "api-keys" / (pid + ".dpapi")
        check(MAC or (store.exists() and K1.encode() not in store.read_bytes()), "The key is kept encrypted in its own file")
        check(not secrets_on_disk(), "No file in the profile holds the key")

        # Test connection: every check, then a model that won't call tools.
        send(p, "apiTest", id=pid, model="fake-small")
        tested = until(lambda: js(p, "document.querySelectorAll('.api-checks li').length >= 6 && [...document.querySelectorAll('.api-checks li')].map(l => (l.dataset.ok ? '+' : '-') + l.innerText)"), 30) or []
        check(len(tested) == 6 and all(t.startswith("+") for t in tested), "Test connection passes address, key, model, streaming, tools and effort: " + "; ".join(tested))
        probe = [r for r in fake.requests if "still_test" in r["tools"]]
        check(probe and probe[0]["effort"] == "low" and probe[0]["stream"], "It sends one small streamed request with the test tool and low effort")
        send(p, "apiTest", id=pid, model="plain-model")
        plain = until(lambda: js(p, "[...document.querySelectorAll('.api-checks li')].find(l => l.innerText.startsWith('Tools') && !l.dataset.ok)?.innerText"), 30)
        check(plain and "can't use your tabs" in plain and until(lambda: (provider("Fake OpenAI") or {}).get("NoTools"), 5), "A model that never calls tools is caught, and the provider can chat but not use tabs")
        send(p, "apiTest", id=pid, model="fake-small")
        check(until(lambda: (q := provider("Fake OpenAI")) and not q["NoTools"], 30), "Testing a tool-calling model clears that")
        check(until(lambda: (q := provider("Fake OpenAI")) and q["Models"][0]["Efforts"] and not q["Models"][1]["Efforts"], 5), "Effort levels show only once Test connection confirmed them, per model")

        # A chat: streamed reply, the plan line gone, cost per reply and chat.
        send(p, "aiHarness", harness=pid)
        send(p, "aiNew")
        t = ask(p, "hello", until_text="Hello from the fake model.") or ""
        check("Hello from the fake model." in t, "A chat streams the provider's reply")
        usage = until(lambda: js(p, "document.querySelector('.ai-usage')?.innerText"), 10) or ""
        check("Last reply:" in usage and "This chat:" in usage and "about $" in usage and "plan" not in usage, "The chat shows tokens and cost per reply and per chat, and no plan line: " + usage)

        check("Fake OpenAI\nUses your API key" in picker(p), "The picker says it uses your API key")

        # Tools run through Still's own MCP server, and the chat resumes from its transcript.
        idle(p)
        t = ask(p, "Which tabs?\nCALL list_tabs {}", until_text="Done. Result:") or ""
        check("Done. Result:" in t and "Looked at open tabs" in t, "A tool call runs through Still's tools and shows as a step")
        transcripts = list((PROFILE / "ai" / "chats").rglob("api-*.json"))
        convo = json.loads(transcripts[0].read_text(encoding="utf-8")) if transcripts else {}
        check(len(transcripts) == 1 and any(m.get("role") == "tool" for m in convo.get("messages", [])) and convo.get("in", 0) > 0, "The chat's transcript, tool calls and totals included, is kept in its folder")
        mine = [r for r in fake.requests if "Which tabs?" in r["user"]]
        check(mine and mine[0]["messages"] >= 3, "The second message brings the conversation so far")

        # A question and an approval, the same cards as for the apps.
        idle(p)
        send(p, "aiSend", text='CALL ask_user {"question": "Red or blue?", "options": ["Red", "Blue"]}')
        check(until(lambda: "Red or blue?" in (js(p, "document.querySelector('[aria-label=\"Question from your AI\"]')?.innerText") or ""), 20), "ask_user shows its question in the chat")
        send(p, "aiAnswer", text="Blue")
        check(until(lambda: "The user answered: Blue" in (text(p) or ""), 20), "and the answer goes back to the model")
        idle(p)
        send(p, "aiSend", text='CALL open_tab {"url": "' + fake.url + '/page"}\nCALL click {"text": "Press me"}')
        card = " ".join(until(lambda: js(p, "[...document.querySelectorAll('.approve-card .approve-steps li')].map(e => e.innerText)"), 30) or [])
        check("Press me" in card and "127.0.0.1" in card, "A click waits on the approval card, naming the step and the site")
        js(p, "[...document.querySelectorAll('.approve-card button')].find(b => b.innerText.trim() === 'Allow once')?.click()")
        check(until(lambda: any(t["Title"] == "Pressed" for t in rpc(p)["tabs"]), 20), "Allow once lets the click run")
        idle(p)

        # Stop, the step cap and a rate limit.
        send(p, "aiSend", text="SLOW please")
        until(lambda: "word3" in text(p), 20)
        started = time.monotonic()
        send(p, "aiStop")
        gone = idle(p, 5)
        took = time.monotonic() - started
        check(gone and took < 1.5 and "Stopped." in text(p), "Stop ends a streaming reply at once (%.2fs)" % took)
        before = len(fake.requests)
        t = ask(p, "LOOP forever", 120, until_text="Stopped after 40 steps") or ""
        check("Stopped after 40 steps in one reply" in t and len(fake.requests) - before <= 41, "A reply stops after 40 steps, with a note")
        idle(p)
        started = time.monotonic()
        t = ask(p, "RATE limited", 60, until_text="is limiting requests") or ""
        check("is limiting requests. Trying again at" in t, "A rate limit says when it will try again")
        t = until(lambda: (x := text(p)) and "still limiting requests" in x and x, 40) or ""
        check("Try again after" in t and time.monotonic() - started >= 13, "After two waits it stops and says when to try (%.0fs)" % (time.monotonic() - started))
        idle(p)

        # A model it doesn't offer falls back to the first, with a note.
        save(p, "Fake OpenAI", models=["fake-small", "gone-model"])
        until(lambda: len((provider("Fake OpenAI") or {}).get("Models", [])) == 2, 10)
        send(p, "aiAdvanced", on=True)
        send(p, "aiCheck")
        time.sleep(1)
        send(p, "aiModel", harness=pid, model="gone-model", effort="")
        until(lambda: prefs().get("AiModels", {}).get(pid) == "gone-model", 10)
        t = ask(p, "hello again", until_text="so this ran on fake-small") or ""
        check("gone-model isn't available at Fake OpenAI, so this ran on fake-small" in t, "A model the provider doesn't have falls back to its first, saying so")
        idle(p)
        send(p, "aiModel", harness=pid, model="", effort="")
        send(p, "aiAdvanced", on=False)

        # Trimming: past 70% of the context, the oldest turns give way to a note.
        first = next((r for r in fake.requests if r["user"].endswith("hello")), None)
        save(p, "Fake OpenAI", models=["fake-small", "fake-large", "plain-model"], context=int(((first or {"chars": 40000})["chars"] / 4 + 2500) / .7))
        time.sleep(1)
        send(p, "aiNew")
        for i in range(5):
            ask(p, "Turn %d: " % i + "lorem ipsum " * 250, 30)
        body = json.dumps(fake.last)
        check("Turn 4" in body and "Earlier parts of this chat were left out" in body and fake.last["messages"][0]["role"] == "user", "Long chats leave out their oldest turns, keeping the first message")

        # Spending and the monthly limit.
        send(p, "openPanel", name="settings", value="models")
        spend = until(lambda: (t := text(p)) and "This month:" in t and t, 10) or ""
        check("about $" in spend and "chats $" in spend and "chat titles $" in spend and "tests $" in spend, "Settings shows this month's tokens and estimate, by chats, titles and tests")
        save(p, "Fake OpenAI", limit=0.0001)
        check(until(lambda: "Paused for this month" in text(p), 10), "Reaching the monthly limit pauses the provider")
        t = ask(p, "hello?", until_text="spending reached your limit") or ""  # Settings, open beside it, says "the estimate reached your limit"
        check("this month's spending reached your limit of $0" in t, "and a chat says so instead of calling it")
        save(p, "Fake OpenAI", limit=0)
        idle(p)

        # A refused key: the chat and the picker say so, Replace fixes it.
        save(p, "Fake OpenAI", key=WRONG)
        t = ask(p, "hello once more", until_text="Key not accepted") or ""
        check("Key not accepted. Replace it in Settings" in t and WRONG not in t, "A refused key says so, without the key")
        check("Fake OpenAI\nAPI provider · Key not accepted" in picker(p), "and the picker marks the provider")
        send(p, "apiTest", id=pid, model="fake-small")
        bad = until(lambda: js(p, "[...document.querySelectorAll('.api-checks li')].find(l => l.innerText.startsWith('Key'))?.innerText"), 20) or ""
        check("Not accepted" in bad, "Test connection fails at the key")
        save(p, "Fake OpenAI", key=K1)
        send(p, "apiTest", id=pid, model="fake-small")
        check(until(lambda: js(p, "document.querySelectorAll('.api-checks li[data-ok]').length") == 6, 30), "Replacing the key fixes it")
        time.sleep(1)

        # Test connection names the failing part: a model the provider doesn't list, then an address where nothing answers.
        row = lambda name: js(p, f"[...document.querySelectorAll('.api-checks li')].find(l => l.innerText.startsWith('{name}'))?.innerText") or ""
        save(p, "Fake OpenAI", models=["fake-small", "gone-model"])
        send(p, "apiTest", id=pid, model="gone-model")
        check(until(lambda: "Pick one it offers" in row("Model"), 30), "Test connection fails at a model the provider doesn't have")
        time.sleep(1)
        save(p, "Fake OpenAI", url="http://127.0.0.1:9/v1")
        send(p, "apiTest", id=pid, model="fake-small")
        check(until(lambda: "Couldn't reach" in row("Address"), 45), "and at an address where nothing answers")
        time.sleep(1)
        save(p, "Fake OpenAI", url=fake.url + "/v1", models=["fake-small", "fake-large", "plain-model"])

        # Anthropic-compatible: tools, streaming and a resumed chat with tool results.
        save(p, "Fake Anthropic", kind="anthropic", url=ant.url + "/v1", key=K2)
        aid = (until(lambda: (q := provider("Fake Anthropic")) and q["Models"] and q, 20) or {}).get("Id", "")
        send(p, "aiHarness", harness=aid)
        send(p, "aiNew")
        t = ask(p, "CALL list_tabs {}", until_text="Done. Result:") or ""
        idle(p)
        t = ask(p, "Again\nCALL list_tabs {}", 30) or ""
        reqs = [r for r in ant.requests if r["kind"] == "anthropic" and r["keyOk"]]
        check(len(reqs) >= 4 and t.count("Done. Result:") >= 2, "An Anthropic-compatible provider runs tools and resumes with their results")
        send(p, "apiTest", id=aid, model=(provider("Fake Anthropic") or {"Models": [{"Id": ""}]})["Models"][0]["Id"])
        check(until(lambda: js(p, "document.querySelectorAll('.api-checks li[data-ok]').length") == 6, 30) and any((r.get("thinking") or {}).get("budget_tokens") for r in ant.requests),
              "Its Test connection passes too, effort sent as a thinking budget")

        # Incognito: no transcript on disk, and each turn brings the chat so far.
        before = set(PROFILE.rglob("api-*.json"))
        wins = {w["id"] for w in rpc(p)["windows"]}
        send(p, "incognitoWindow")
        wid = until(lambda: next((w["id"] for w in rpc(p)["windows"] if w["incognito"] and w["id"] not in wins), None), 15)
        until(lambda: rpc(p, "shellEval", window=wid, script="!!document.querySelector('[aria-label=Message]')"), 15)
        time.sleep(.5)
        post = lambda op, **a: rpc(p, "shellEval", window=wid, script="window.chrome.webview.postMessage(" + json.dumps({"op": op, **a}) + ")")
        post("aiSend", text="Secret plans one", home=True)
        until(lambda: any("Secret plans one" in r["user"] for r in ant.requests), 20)
        time.sleep(2)
        post("aiSend", text="Secret plans two")
        until(lambda: any("Secret plans two" in r["user"] for r in ant.requests), 20)
        time.sleep(1)
        second = next((r for r in ant.requests if "Secret plans two" in r["user"]), {})
        check(set(PROFILE.rglob("api-*.json")) == before and not any("Secret plans" in f.read_text(encoding="utf-8", errors="replace") for f in PROFILE.rglob("api-*.json")),
              "An incognito API chat writes no transcript")
        check("Secret plans one" in second.get("user", ""), "Its next turn brings the chat so far instead")
        note = rpc(p, "shellEval", window=wid, script="document.querySelector('.chat-incognito')?.innerText") or ""
        check("Still writes none of it to disk" in note and "still get what's sent to them" in note, "Its note says the provider still gets what's sent")
        post("closeWindow")

        # Keys stay out of every file, and removing one deletes it.
        check(not secrets_on_disk(), "No file in the profile holds any key: " + "; ".join(secrets_on_disk()[:3]))
        send(p, "apiKeyRemove", id=aid)
        check(until(lambda: not (PROFILE / "api-keys" / (aid + ".dpapi")).exists(), 10) or MAC, "Remove deletes the key")
        check("Fake Anthropic\nAPI provider · Needs a key\nAdd key" in picker(p), "and the picker asks for one")
        send(p, "apiDelete", id=aid)
        check(until(lambda: provider("Fake Anthropic") is None, 10), "Deleting a provider removes it")
        check(not list((PROFILE / "ai" / "titles").rglob("api-*.json")), "Chat titles leave no transcript behind")
        check(not rpc(p)["shellErrors"], "No interface JavaScript errors")
        rpc(p, "quit")
        p.wait(timeout=15)
    except Exception as error:
        RESULT["error"] = repr(error)
        print("ERROR " + repr(error), flush=True)
        try:
            rpc(p, "capture", name="failure.png")
        except Exception:  # noqa: BLE001
            pass
    finally:
        if p.poll() is None:
            p.kill()
        fake.stop()
        ant.stop()


try:
    main()
finally:
    RESULT["passed"] = "error" not in RESULT and all(c["passed"] for c in RESULT["checks"])
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
    print(("PASSED " if RESULT["passed"] else "FAILED ") + str(sum(c["passed"] for c in RESULT["checks"])) + "/" + str(len(RESULT["checks"])) + " -> " + str(RUN), flush=True)
    sys.exit(0 if RESULT["passed"] else 1)
