"""The message box's row (attach, the companion and mode chip, model, effort, send) stays inside the box at any width,
and Gemini and OpenCode show their logos like the other AI apps.

A keyless Compatible API with a long model name and confirmed efforts, in Advanced, so the row carries every control.
Each message box on screen (the new tab page's and the side chat's) is set to widths from 220 to 1000 pixels; at each,
every control must sit inside the box and nothing overlaps; a narrow box puts model and effort on a line of their own.

Run: python tests/desktop/composer.py artifacts/Still-QA/Still.exe
Out: artifacts/composer-*/composer-<width>.png
"""
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("composer-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
RESULT = {"checks": []}
MODEL = "a-very-long-local-model-name-that-keeps-going-q4"
WIDTHS = (220, 260, 320, 400, 520, 720, 1000)


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


# For each message box: set its width (never wider than its column, as a real window would), then every control's box against the message box's, and the controls against
# each other. Returns [width, label, problems] rows.
SET = "[...document.querySelectorAll('.composer')].forEach(c => { c.style.width = c.style.maxWidth = ''; c.style.width = c.style.maxWidth = Math.min(%d, c.parentElement.clientWidth) + 'px'; c.style.minWidth = '0' })"
MEASURE = """[...document.querySelectorAll('.composer')].filter(c => c.offsetParent).map(c => {
 const box = c.getBoundingClientRect(), row = c.querySelector('[data-slot=input-group-addon][data-align=block-end]')
 const kids = [...row.children].filter(k => !k.classList.contains('composer-gap') && k.getBoundingClientRect().width > 0)
 const name = k => k.getAttribute('aria-label') || k.className.split(' ')[0], bad = []
 kids.forEach(k => { const r = k.getBoundingClientRect()
  if (r.left < box.left - .5 || r.right > box.right + .5) bad.push(name(k) + ' outside (' + Math.round(r.left - box.left) + '..' + Math.round(r.right - box.left) + ' of ' + Math.round(box.width) + ')')
  if (r.bottom > box.bottom + .5) bad.push(name(k) + ' below the box') })
 kids.forEach((a, j) => kids.slice(j + 1).forEach(b => { const x = a.getBoundingClientRect(), y = b.getBoundingClientRect()
  if (x.right > y.left + .5 && y.right > x.left + .5 && x.bottom > y.top + .5 && y.bottom > x.top + .5) bad.push(name(a) + ' overlaps ' + name(b)) }))
 return [Math.round(box.width), c.closest('.ai-sidebar') ? 'side chat' : 'new tab', bad]
})"""


def main():
    PROFILE.mkdir(parents=True)
    pid = "api-" + uuid.uuid4().hex[:8]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}],
        "Preferences": {"AgentsEnabled": True, "Companions": CREW, "AiHarness": pid, "AiAdvanced": True, "AiModels": {pid: MODEL}, "AiEfforts": {pid: ""},
            "ApiProviders": [{"Id": pid, "Kind": "openai", "Name": "Local box", "Url": "http://127.0.0.1:9/v1", "NoKey": True,
                              "Models": [{"Id": MODEL, "Efforts": ["low", "medium", "high"]}]}]}}))
    p = launch(EXE, PROFILE)
    try:
        send(p, "aiCheck")
        until(lambda: js(p, "!!document.querySelector('.composer [aria-label=Effort]')"), 30)
        send(p, "aiToggle")
        both = until(lambda: js(p, "[...document.querySelectorAll('.composer')].filter(c => c.offsetParent && c.querySelector('[aria-label=Effort]')).length") == 2, 20)
        check(both, "Both message boxes (new tab and side chat) show attach, companion, model, effort and send")
        check("Default effort" in (js(p, "document.querySelector('.composer [aria-label=Effort]')?.innerText") or ""), "The effort picker reads Default effort")
        problems = []
        for w in WIDTHS:
            js(p, SET % w)
            time.sleep(.25)
            rows = js(p, MEASURE) or []
            for width, where, bad in rows:
                if bad:
                    problems.append(f"{where} at {width}px: {'; '.join(bad)}")
            if w in (220, 320, 1000):
                time.sleep(.2)
                rpc(p, "capture", name=f"composer-{w}.png")
        check(not problems, "Every control stays inside the box at " + ", ".join(map(str, WIDTHS)) + " px" + (": " + " | ".join(problems[:6]) if problems else ""))
        js(p, "[...document.querySelectorAll('.composer')].forEach(c => { c.style.width = c.style.maxWidth = c.style.minWidth = '' })")
        time.sleep(.25)
        whole = js(p, "[...document.querySelectorAll('.composer [aria-label=Effort] .truncate')].filter(e => e.offsetParent).map(e => e.scrollWidth <= e.clientWidth + 1)") or []
        check(whole and all(whole), f"At the window's own widths, Default effort reads in full in both boxes ({whole})")
        for w in (220, 320):
            js(p, SET % w)
            time.sleep(.25)
            labels = js(p, """[...document.querySelectorAll('.composer')].filter(c => c.offsetParent).map(c => {
             const fit = e => e && e.scrollWidth <= e.clientWidth + 1, effort = c.querySelector('[aria-label=Effort] .truncate'), model = c.querySelector('[aria-label=Model] .truncate')
             const row = s => c.querySelector(s)?.getBoundingClientRect().top
             return [fit(effort), model && getComputedStyle(model).textOverflow, row('[aria-label=Effort]') > row('[aria-label=Send]')] })""") or []
            check(labels and all(e and m == "ellipsis" and below for e, m, below in labels),
                  f"At {w}px the model and effort move to their own line: Default effort reads in full, the model name ends in an ellipsis ({labels})")
        js(p, "[...document.querySelectorAll('.composer')].forEach(c => { c.style.width = ''; c.style.maxWidth = ''; c.style.minWidth = '' })")

        # Logos: the AI list in the side chat's settings, with More agents open. Only read: nothing here is clicked but More agents.
        js(p, "document.querySelector('[aria-label=\"AI settings\"]')?.click()")
        until(lambda: js(p, "!!document.querySelector('.byo-row')"), 10)
        js(p, "document.querySelector('.byo-more')?.click()")
        time.sleep(.4)
        logos = js(p, "Object.fromEntries([...document.querySelectorAll('.byo-row')].map(r => [r.querySelector('strong')?.innerText ?? '', r.querySelector('.ai-logo.is-letter') ? 'letter' : (r.querySelector('.ai-logo path')?.getAttribute('d') || '').slice(0, 9)]))") or {}
        gem = next((v for k, v in logos.items() if k.startswith("Gemini")), None)
        oc = next((v for k, v in logos.items() if k.startswith("OpenCode")), None)
        check(gem and gem.startswith("M20.616"), f"Gemini shows its logo ({gem})")
        check(oc and oc.startswith("M16 6H8"), f"OpenCode shows its logo ({oc})")
        check(all(v != "letter" for k, v in logos.items() if k.split(" ")[0] in ("Claude", "ChatGPT", "Grok", "Gemini", "OpenCode")), f"No built-in AI app falls back to a letter ({logos})")
        errors = rpc(p).get("shellErrors") or js(p, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(p, "quit")
        RUN.joinpath("result.json").write_text(json.dumps(RESULT, indent=1))
    failed = [c for c in RESULT["checks"] if not c["passed"]]
    print(f"Results: {len(RESULT['checks']) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
