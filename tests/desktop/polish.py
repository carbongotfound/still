"""Phase 6: polish. The keyboard table, then an accessibility and dark-mode pass over the main screens: every control
has a name, keyboard focus shows a ring, and text meets 4.5:1 contrast (3:1 for large text) in light and dark.

Run: python tests/desktop/polish.py artifacts/Still-QA/Still.exe
Screenshots: docs/agentic/compare/polish-<screen>-<theme>-v01.png
"""
import http.server
import json
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, js, launch, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("polish-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
OUT = ROOT / "docs" / "agentic" / "compare"
RESULT = {"checks": [], "audit": {}}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><meta charset=utf-8><title>Garden notes</title><body style='font:18px system-ui;margin:40px'><h1>Garden notes</h1><p>Tomatoes like sun."
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{server.server_address[1]}/garden"

# Runs in the interface. Colors go through a 1x1 canvas, so oklch, color-mix and named colors all resolve to sRGB.
AUDIT = r"""(() => {
 const cv = document.createElement('canvas'); cv.width = cv.height = 1; const cx = cv.getContext('2d', {willReadFrequently: true});
 const rgba = c => { cx.clearRect(0, 0, 1, 1); cx.fillStyle = 'rgba(0,0,0,0)'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1); const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255] };
 const over = (top, under) => [0, 1, 2].map(i => top[i] * top[3] + under[i] * (1 - top[3])).concat(1);
 const lum = c => { const f = v => (v /= 255) <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]) };
 const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) };
 const base = rgba(getComputedStyle(document.body).getPropertyValue('--background').trim() || 'white');
 const hidden = el => !!el.closest('[aria-hidden=true], .sr-only, [inert]');
 const shown = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth && s.visibility === 'visible' };
 const overlays = [...document.querySelectorAll('[role=dialog], [role=alertdialog], [role=menu]')].filter(o => !hidden(o) && shown(o));
 const scope = overlays.length ? overlays : [document.body];
 const within = el => scope.some(s => s.contains(el));
 const what = el => (el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '') + ' "' + (el.textContent || '').trim().slice(0, 40) + '"');
 // What's behind an element: its own and its ancestors' backgrounds, stacked. Gradients and images can't be judged.
 const behind = el => { const layers = []; let opacity = 1;
  for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const s = getComputedStyle(e); opacity *= +s.opacity;
   if (s.backgroundImage !== 'none') return null;
   const c = rgba(s.backgroundColor); if (c[3] > 0) { layers.push(c); if (c[3] > .99) break } }
  let bg = layers.length && layers[layers.length - 1][3] > .99 ? layers.pop() : base;
  while (layers.length) bg = over(layers.pop(), bg);
  return { bg, opacity } };
 const contrast = [], unnamed = [], noRing = [], images = [];
 let texts = 0;
 for (const el of document.querySelectorAll('body *')) {
  if (!within(el) || hidden(el) || !shown(el)) continue;
  if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
  if (el.closest('[disabled], [aria-disabled=true], [data-disabled]')) continue;
  const node = [...el.childNodes].find(n => n.nodeType === 3 && n.textContent.trim()), range = document.createRange(); range.selectNodeContents(node);
  const r = range.getBoundingClientRect(); if (!r.width || !r.height) continue;
  const hit = document.elementFromPoint(Math.min(innerWidth - 1, r.left + r.width / 2), Math.min(innerHeight - 1, r.top + r.height / 2));
  if (!hit || !(el.contains(hit) || hit.contains(el))) continue; // covered by something else
  const s = getComputedStyle(el), b = behind(el); if (!b) continue;
  let fg = rgba(s.color); if (fg[3] === 0 || b.opacity === 0) continue; fg = [fg[0], fg[1], fg[2], fg[3] * b.opacity]; // skips text that's invisible until hover
  const size = parseFloat(s.fontSize), large = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700), need = large ? 3 : 4.5;
  const got = ratio(over(fg, b.bg), b.bg); texts++;
  if (got < need) contrast.push(what(el) + ' ' + got.toFixed(2) + ':1');
 }
 const controls = 'button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=menuitem], [role=menuitemradio], [role=menuitemcheckbox], [role=tab], [role=switch], [role=checkbox], [role=option], [role=slider], [role=combobox], [role=separator][tabindex]';
 const name = el => [el.getAttribute('aria-label'), (el.getAttribute('aria-labelledby') || '').split(' ').map(id => document.getElementById(id)?.textContent || '').join(''), el.textContent,
  el.getAttribute('title'), el.labels ? [...el.labels].map(l => l.textContent).join('') : '', el.getAttribute('placeholder'), el.getAttribute('alt')].some(v => (v || '').trim());
 const list = [...document.querySelectorAll(controls)].filter(el => within(el) && !hidden(el) && shown(el));
 for (const el of list) if (!name(el)) unnamed.push(what(el) + ' ' + el.outerHTML.slice(0, 120));
 for (const img of document.querySelectorAll('img')) if (within(img) && !hidden(img) && shown(img) && !img.hasAttribute('alt')) images.push(img.outerHTML.slice(0, 100));
 const before = document.activeElement;
 const look = e => [e, e.parentElement, e.parentElement?.parentElement].filter(Boolean).map(x => { const s = getComputedStyle(x); return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 ? s.outlineColor + s.outlineWidth : '') + '|' + s.boxShadow + '|' + s.borderColor }).join(';');
 const still = document.head.appendChild(Object.assign(document.createElement('style'), { textContent: '*, *::before, *::after { transition: none !important; animation: none !important; }' }));
 // Focus only shows while the shell has it: after selecting a tab the page has it, and that screen's rings are checked in the other theme.
 const focusable = document.hasFocus() ? list.filter(el => el.tabIndex >= 0 && !el.disabled).slice(0, 120) : [];
 for (const el of focusable) {
  const other = focusable.find(x => x !== el && !x.contains(el) && !el.contains(x)); if (other) other.focus({ preventScroll: true }); else document.activeElement?.blur?.();
  const idle = look(el);
  el.focus({ preventScroll: true, focusVisible: true }); if (document.activeElement !== el) continue;
  const editing = el.closest('.is-editing'); // the address bar while you type: its ring is already up, from before this check
  if (look(el) === idle && !(editing && getComputedStyle(editing).boxShadow !== 'none')) noRing.push(what(el) + ' ' + (el.getAttribute('aria-label') || el.className.toString().slice(0, 40)));
 }
 still.remove(); before?.focus?.({ preventScroll: true }); document.activeElement?.blur?.();
 return JSON.stringify({ texts, controls: list.length, contrast, unnamed, noRing, images });
})()"""


def audit(process, screen, theme):
    time.sleep(.6)  # let springs settle
    found = json.loads(js(process, AUDIT))
    RESULT["audit"][f"{screen}-{theme}"] = found
    rpc(process, "capture", name="shot.png")
    shutil.copy(PROFILE / "shot.png", OUT / f"polish-{screen}-{theme.lower()}-v01.png")
    print(f"  {screen} ({theme}): {found['texts']} texts, {found['controls']} controls; contrast {len(found['contrast'])}, unnamed {len(found['unnamed'])}, no ring {len(found['noRing'])}", flush=True)
    return found


def toast_says(process, words):
    return until(lambda: words in js(process, "[...document.querySelectorAll('[data-sonner-toast]')].map(t => t.innerText).join(' | ')"), 4)


def key(process, name, mods="Control"):
    return rpc(process, "key", key=name, mods=mods).get("ok")


def close(process):
    key(process, "Escape", "None")
    until(lambda: rpc(process)["panel"] == "" and not js(process, "!!document.querySelector('[role=dialog]')"), 5)


def keyboard(process):
    send(process, "openPanel", name="shortcuts", value="")
    listed = until(lambda: js(process, "document.querySelector('.shortcuts-scroll')?.innerText || ''"), 5) or ""
    close(process)
    windows = ("Ctrl T", "Ctrl Shift A", "Ctrl Shift K", "Ctrl K", "Esc", "Ctrl .", "Ctrl Enter", "Ctrl Tab", "Ctrl J")
    mac = ("⌘T", "⇧⌘A", "⇧⌘K", "⌘K", "Esc", "⌘.", "⌘Enter", "⌃Tab", "⌥⌘L")  # the Mac menu bar's spelling
    for keys in (mac if MAC else windows):
        check(keys in listed, f"Keyboard shortcuts lists {keys}")

    count = len(rpc(process)["tabs"])
    check(key(process, "T") and until(lambda: len(rpc(process)["tabs"]) == count + 1, 5), "Ctrl+T opens a new tab")
    check(until(lambda: rpc(process)["panel"] == "address" and js(process, "!!document.activeElement?.matches('input, textarea')"), 5),
          "The new tab opens with the address box focused, so you can type right away")
    check(key(process, "Escape", "None") and until(lambda: rpc(process)["panel"] == "", 5), "Esc closes it")
    check(key(process, "K") and until(lambda: rpc(process)["panel"] != "", 5), "Ctrl+K opens the command box")
    key(process, "Escape", "None")
    until(lambda: rpc(process)["panel"] == "", 5)
    check(key(process, "K", "Control, Shift") and toast_says(process, "Nothing is running right now."), "Ctrl+Shift+K says when nothing is running")
    check(key(process, "OemPeriod") and toast_says(process, "Nothing is running in this chat."), "Ctrl+. says when nothing is running")
    was = js(process, "!!document.querySelector('.ai-sidebar')")
    check(key(process, "A", "Control, Shift") and until(lambda: js(process, "!!document.querySelector('.ai-sidebar')") != was, 5), "Ctrl+Shift+A opens and closes the chat")
    key(process, "A", "Control, Shift")
    until(lambda: js(process, "!!document.querySelector('.ai-sidebar')") == was, 5)
    check(js(process, "document.querySelector('.top-new-tab')?.title.includes('Ctrl+T')"), "The new tab button's tooltip shows Ctrl+T")


def screens(process, theme):
    send(process, "preference", key="theme", value=theme)
    until(lambda: js(process, "document.documentElement.classList.contains('dark')") == (theme == "Dark"), 5)
    found = []
    send(process, "select", id="page")
    until(lambda: rpc(process)["activeId"] == "page", 5)
    found.append(audit(process, "page", theme))
    send(process, "new")
    until(lambda: js(process, "!!document.querySelector('.home-rail')"), 10)
    found.append(audit(process, "home", theme))
    send(process, "select", id="page")
    send(process, "openPanel", name="settings", value="")
    until(lambda: js(process, "!!document.querySelector('.settings-tabs')"), 5)
    pages = js(process, "JSON.stringify([...document.querySelectorAll('.settings-tabs [role=tab]')].map(t => t.innerText.trim()))")
    for i, page in enumerate(json.loads(pages)):
        js(process, f"document.querySelectorAll('.settings-tabs [role=tab]')[{i}].dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, button: 0}}))")
        until(lambda: js(process, f"document.querySelectorAll('.settings-tabs [role=tab]')[{i}].getAttribute('data-state') === 'active'"), 3)
        found.append(audit(process, "settings-" + page.lower().replace(" & ", "-").replace(" ", "-"), theme))
    close(process)
    for pane in ("history", "shortcuts"):
        send(process, "openPanel", name=pane, value="")
        until(lambda: rpc(process)["panel"] == pane, 5)
        found.append(audit(process, pane, theme))
        close(process)
    send(process, "aiToggle")
    if until(lambda: js(process, "!!document.querySelector('.ai-sidebar')"), 5):
        found.append(audit(process, "chat", theme))
        send(process, "aiToggle")
        until(lambda: not js(process, "!!document.querySelector('.ai-sidebar')"), 5)
    send(process, "preference", key="tabLayout", value="Modern")
    until(lambda: js(process, "!!document.querySelector('.browser-sidebar')"), 5)
    found.append(audit(process, "modern", theme))
    send(process, "preference", key="tabLayout", value="Classic")
    until(lambda: not js(process, "!!document.querySelector('.browser-sidebar')"), 5)
    return found


def main():
    PROFILE.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Theme": "Light", "Width": 1720, "Height": 1080},
        "Tabs": [{"Id": "page", "Title": "Garden notes", "Url": URL}], "ActiveId": "page",
        "History": [{"Title": "Garden notes", "Url": URL, "At": "2026-10-27T09:00:00Z"}]}))
    process = launch(EXE, PROFILE)
    try:
        until(lambda: any(t["Id"] == "page" and t["ready"] for t in rpc(process)["tabs"]), 20)
        keyboard(process)
        for theme in ("Light", "Dark"):
            found = screens(process, theme)
            check(not any(f["unnamed"] for f in found), f"{theme}: every control has a name")
            check(not any(f["images"] for f in found), f"{theme}: every image has alt text")
            check(not any(f["noRing"] for f in found), f"{theme}: keyboard focus shows a ring on every control")
            check(not any(f["contrast"] for f in found), f"{theme}: text meets 4.5:1 (3:1 when large)")
        errors = rpc(process).get("shellErrors") or js(process, "window.__shellErrors")
        check(not errors, "No interface errors" + (f" ({errors})" if errors else ""))
    finally:
        rpc(process, "quit")
        process.wait(timeout=20)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=1))
    failed = [c for c in RESULT["checks"] if not c["passed"]]
    print(("PASSED" if not failed else "FAILED") + f" {len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])} -> {RUN}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
