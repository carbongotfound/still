"""Setup's Connect step: "Use an API instead" takes a Compatible API (OpenAI- or Claude-compatible) by its base URL, a
model and an optional key, and tests it right there, against the local fake model server, never a real provider.
A keyless server needs no key; one that asks for a key says so; with the key it passes. The key goes to the same
store as Settings', the field empties, and the key never shows in the interface or any other file. It's labelled
Compatible, nothing more, and becomes the AI.

Run: python tests/desktop/setupapi.py artifacts/Still-QA/Still.exe
"""
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from fakemodels import Fake  # noqa: E402
from qa import CREW, MAC, ROOT, js, launch, rpc, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("setupapi-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
RESULT = {"checks": []}
KEY = "sk-ant-fake-" + uuid.uuid4().hex + "QRST"
FORM = ".ob-api-form"


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


def click(p, selector):
    return js(p, f"(() => {{ const e = document.querySelector({json.dumps(selector)}); e?.click(); return !!e }})()")


def type_into(p, selector, value):
    return js(p, f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false
     const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value').set; set.call(e, {json.dumps(value)})
     e.dispatchEvent(new Event('input', {{ bubbles: true }})); return true }})()""")


def pick(p, label, option):
    js(p, f"document.querySelector('{FORM} [aria-label={json.dumps(label)}]').dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }}))")
    # It has to be in front to be picked. An open list turns pointer events off on the body, setup screen included, so a
    # plain hit test goes through the screen and a click by script reaches an option hidden behind it: turn them on to look.
    return until(lambda: js(p, f"""(() => {{ const o = [...document.querySelectorAll('[role=option]')].find(o => o.innerText.trim() === {json.dumps(option)}); if (!o) return false
      const r = o.getBoundingClientRect(), off = document.body.style.pointerEvents; document.body.style.pointerEvents = 'auto'
      const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); document.body.style.pointerEvents = off
      if (!o.contains(top)) return false; o.click(); return true }})()"""), 5)


def read(f):
    try:
        return f.read_bytes()
    except OSError:  # the browser's own lock files
        return b""


def prefs():
    for _ in range(50):
        try:
            return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))["Preferences"]
        except (OSError, ValueError, KeyError):
            time.sleep(.05)
    return {}


def checks(p):
    """The test's results under the form, once it's done: [ok, part, text]."""
    return until(lambda: not js(p, f"!!document.querySelector('{FORM} button[type=submit] [data-slot=spinner], {FORM} button[type=submit] .animate-spin')")
                 and js(p, f"[...document.querySelectorAll('{FORM} .api-checks li')].map(l => [!!l.dataset.ok, l.querySelector('b').innerText, l.innerText])"), 30) or []


def test(p, url, model, key=""):
    type_into(p, f"{FORM} input[placeholder^='https://']", url)
    type_into(p, f"{FORM} input[placeholder^=\"The model\"]", model)
    type_into(p, f"{FORM} input[type=password]", key)
    time.sleep(.3)
    before = js(p, f"document.querySelector('{FORM} .api-checks')?.getAttribute('aria-label') + ' ' + document.querySelectorAll('{FORM} .api-checks li').length")
    click(p, f"{FORM} button[type=submit]")
    time.sleep(1)
    return checks(p), before


def main():
    open_server = Fake(key="")
    keyed = Fake(key=KEY)
    PROFILE.mkdir(parents=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": True, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}],
        "Preferences": {"AgentsEnabled": True, "Companions": CREW, "AiHarness": "gone"}}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: "A little less work" in (js(p, "document.querySelector('.ob-talk')?.innerText ?? ''") or ""), 20)
        time.sleep(2.5)
        click(p, ".ob-next")
        check(until(lambda: js(p, "Number(document.querySelector('.ob-dots')?.getAttribute('aria-valuenow') ?? 0)") == 2, 6), "Setup reaches Connect")
        time.sleep(1.6)
        until(lambda: js(p, "(() => { const d = document.querySelector('.ob-api'); if (d && !d.open) d.querySelector('summary').click(); return !!d?.open })()"), 5)
        form = until(lambda: js(p, f"document.querySelector('{FORM}')?.offsetParent && document.querySelector('{FORM}').innerText"), 5) or ""
        check(all(w in form for w in ("Kind", "Base URL", "Model", "API key", "Test connection", "Compatible")) and "Tested" not in form and "Verified" not in form,
              "Use an API instead shows Kind, Base URL, Model, an optional API key and Test connection, labelled Compatible")
        check("Optional" in (js(p, f"document.querySelector('{FORM} input[type=password]')?.placeholder") or ""), "The key says it's optional")

        # An OpenAI-compatible server that needs no key.
        got, _ = test(p, open_server.url + "/v1", "fake-small")
        check(len(got) == 6 and all(ok for ok, _, _ in got), "Test connection passes every check right there: " + "; ".join(t for _, _, t in got))
        check(any(part == "Key" and "None needed." in t for _, part, t in got), "Without a key, the key check says none is needed")
        q = next(iter(prefs().get("ApiProviders") or []), {})
        check(q.get("NoKey") and q.get("Kind") == "openai" and q.get("Url") == open_server.url + "/v1" and [m["Id"] for m in q.get("Models", [])] == ["fake-small"],
              f"It's saved as a keyless OpenAI-compatible provider with that model ({q.get('Name')})")
        check(prefs().get("AiHarness") == q.get("Id"), "and becomes the AI")

        # A Claude-compatible server that asks for a key: first without one, then with it.
        check(pick(p, "Kind", "Claude-compatible"), "The Kind list shows in front of the setup screen, and Claude-compatible can be picked")
        got, _ = test(p, keyed.url + "/v1", "fake-large")
        check(any(part == "Key" and not ok and "asks for a key" in t for ok, part, t in got), "A server that wants a key says so: " + "; ".join(t for _, _, t in got))
        got, _ = test(p, keyed.url + "/v1", "fake-large", KEY)
        check(len(got) == 6 and all(ok for ok, _, _ in got) and any(part == "Key" and "Accepted." in t for _, part, t in got), "With the key it passes: " + "; ".join(t for _, _, t in got))
        q = next(iter(prefs().get("ApiProviders") or []), {})
        check(len(prefs().get("ApiProviders") or []) == 1 and q.get("Kind") == "anthropic" and not q.get("NoKey"), "The same provider is now Claude-compatible, with a key")
        check(js(p, f"document.querySelector('{FORM} input[type=password]')?.value") == "" and "Saved" in (js(p, f"document.querySelector('{FORM} input[type=password]')?.placeholder") or ""),
              "The key field empties and says the key is saved")
        store = PROFILE / "api-keys" / (q.get("Id", "") + ".dpapi")
        check(MAC or (store.exists() and KEY.encode() not in store.read_bytes()), "The key is kept encrypted in Settings' key store")
        check(KEY not in (js(p, "document.documentElement.outerHTML") or ""), "The key never shows in the interface")
        leaks = [str(f.relative_to(RUN)) for f in RUN.rglob("*") if f.is_file() and f.parent.name != "api-keys" and f.suffix not in (".png", ".mp4")
                 and (KEY.encode() in (b := read(f)) or KEY.encode("utf-16-le") in b)]
        check(not leaks, f"No other file holds the key, logs included ({leaks})")
        check(prefs().get("AiHarness") == q.get("Id"), "It stays the AI")
        rpc(p, "capture", name="setup-api.png")
        errors = rpc(p).get("shellErrors") or js(p, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(p, "quit")
        open_server.stop()
        keyed.stop()
        RUN.joinpath("result.json").write_text(json.dumps(RESULT, indent=1))
    failed = [c for c in RESULT["checks"] if not c["passed"]]
    print(f"Results: {len(RESULT['checks']) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
