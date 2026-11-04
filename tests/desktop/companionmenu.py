"""Stage 17: the companion panel and the look editor.
- No markings: a look saved with one (2.10 before Stage 17) draws the same as without it on all five bodies, opens and
  saves without it, and leaves the saved file without it; the editor has no Marking section or marking color.
- AI settings: the panel's name menu (what they run on, then the others), its ... menu and the message box's mode menu,
  model picker and effort picker (Advanced) each open that companion's AI tab: the app, the default mode, the model and
  effort for each mode, and the key. In view without scrolling, from the new tab page and the side chat.
- The ... menu: every item works (AI settings, Edit look, Rename, Duplicate, Introduce yourself again, Open chat in a tab
  or Chat with, Clear chat, Close panel, Fire, and Reset for a built-in one), the panel's menus and confirms open above it, and Clear chat and Fire ask
  first and can be undone, and so does Reset. Every other button in the panel does something.
- Classic looks: every built-in companion (Jonah, Talia, Nora, Leo, Ivan, Maya, Ruth) and a hired one open with every
  tab working; a change in any tab, a start look or a team look moves them to the new style and Save keeps it; Cancel
  puts the classic look back byte for byte.
No AI runs and nothing signs in: a fake agent app (a manifest in Still's agents folder) and a keyless local API box.

Run: python tests/desktop/companionmenu.py artifacts/Still-QA/Still.exe
"""
import base64
import io
import json
import os
import sys
import textwrap
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa import MAC, ROOT, companions_page, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("companionmenu-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
RESULT = {"checks": []}
FORM_SHAPE = {"pebble": "round", "column": "tall", "block": "block", "gumdrop": "gumdrop", "bean": "bean"}
LOCAL, KEYED = "api-local17", "api-keyed17"


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


FAKE = textwrap.dedent(r'''
    import json, sys
    if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
    sys.stdin.read()
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False}), flush=True)
''')
ROLE = {"sales": ("#f7a26a", "tall"), "growth": ("#f2a5c4", "gumdrop"), "planner": ("#a6cf9c", "block"), "marketing": ("#f6d56a", "round"),
        "engineer": ("#8cc3ee", "bump"), "research": ("#c0a3ec", "lean"), "assistant": ("#2fa496", "crest")}
BUILT_IN = [("jonah", "Jonah", "Sales", "sales"), ("talia", "Talia", "Growth", "growth"), ("nora", "Nora", "Planner", "planner"), ("leo", "Leo", "Marketing", "marketing"),
            ("ivan", "Ivan", "Engineer", "engineer"), ("maya", "Maya", "Research", "research"), ("ruth", "Ruth", "Assistant", "assistant")]
def classic(k):
    return json.dumps({"color": ROLE[k][0], "shape": ROLE[k][1], "prop": "", "accessory": ""}, separators=(",", ":"))


MARKED = '{"v":2,"color":"#a6cf9c","shape":"block","prop":"","accessory":"bow","form":"block","second":"#4f8a4a","marking":"mask","mark":"#4a5263","eye":"sleepy","mouth":"smile","top":"cap","finish":"gloss"}'
UNMARKED = '{"v":2,"color":"#a6cf9c","shape":"block","prop":"","accessory":"bow","form":"block","second":"#4f8a4a","eye":"sleepy","mouth":"smile","top":"cap","finish":"gloss"}'
NIKOLA = '{"color":"#8cc3ee","shape":"round","prop":"","accessory":""}'


def state():
    for _ in range(50):  # Still swaps the file in atomically, so a read can land mid-swap
        try:
            return json.loads((PROFILE / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.05)
    return {}


def mates():
    return {c["Name"]: c for c in state().get("Preferences", {}).get("Companions", [])}


def chats():
    try:
        return json.loads((PROFILE / "ai" / "chats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def click(p, sel):
    return js(p, f"(() => {{ const e = document.querySelector({json.dumps(sel)}); e?.click(); return !!e }})()")


def click_text(p, sel, words):
    return js(p, f"(() => {{ const e = [...document.querySelectorAll({json.dumps(sel)})].find(e => e.innerText.trim().includes({json.dumps(words)})); e?.click(); return !!e }})()")


def press(p, sel):
    """Radix menus and selects open on pointerdown."""
    return js(p, f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return false; e.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }})); if (e.getAttribute('role') !== 'combobox') e.click(); return true }})()")


def menu_item(p, words, role="menuitem"):
    """Picks an item of the open menu or select, the way a pointer does."""
    return js(p, f"""(() => {{ const e = [...document.querySelectorAll('[role={role}]')].find(e => e.innerText.trim().startsWith({json.dumps(words)})); if (!e) return false
     e.dispatchEvent(new PointerEvent('pointerdown', {{ bubbles: true, button: 0, pointerType: 'mouse' }})); e.dispatchEvent(new PointerEvent('pointerup', {{ bubbles: true, button: 0, pointerType: 'mouse' }})); e.click(); return true }})()""")


def escape(p):
    js(p, "(document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    time.sleep(.4)


def popup_on_top(p, sel):
    """The open pop-up (menu, select list or confirm) is drawn above the panel, and fully in the window."""
    return js(p, f"""(() => {{ const m = document.querySelector({json.dumps(sel)}); if (!m) return 'none'
     let z = 0; for (let e = m; e && e !== document.body; e = e.parentElement) {{ const v = parseInt(getComputedStyle(e).zIndex); if (!isNaN(v)) z = Math.max(z, v) }}
     const panel = document.querySelector('.profile-panel'), pz = panel ? parseInt(getComputedStyle(panel).zIndex) : -1, r = m.getBoundingClientRect()
     return z > pz && r.top >= 0 && r.bottom <= innerHeight + 1 && r.height > 0 ? 'ok' : `z ${{z}} vs panel ${{pz}}, ${{Math.round(r.top)}}..${{Math.round(r.bottom)}} of ${{innerHeight}}` }})()""")


def in_view(p, item_sel, words):
    """An item of the open pop-up is shown whole, without scrolling: inside the list's visible box and the window."""
    return js(p, f"""(() => {{ const e = [...document.querySelectorAll({json.dumps(item_sel)})].find(e => e.innerText.trim().startsWith({json.dumps(words)})); if (!e) return 'missing'
     const r = e.getBoundingClientRect(); let ok = r.height > 0 && r.top >= 0 && r.bottom <= innerHeight + 1
     for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {{ const s = getComputedStyle(a); if (/(auto|scroll|hidden)/.test(s.overflowY)) {{ const b = a.getBoundingClientRect(); ok = ok && r.top >= b.top - 1 && r.bottom <= b.bottom + 1 }} }}
     return ok ? 'ok' : 'cut off' }})()""")


def panel_tab(p):
    return js(p, "document.querySelector('.profile-tablist [aria-selected=true]')?.innerText")


def open_panel(p, name):
    """name's panel, from the Companions page."""
    escape(p)
    if js(p, "!!document.querySelector('.profile-panel')"):
        click(p, ".profile-head [aria-label=Close]")
        until(lambda: not js(p, "!!document.querySelector('.profile-panel')"), 3)
    send(p, "new")
    time.sleep(.6)
    companions_page(p)
    until(lambda: click(p, f".mate-portrait[aria-label='Edit {name}']"), 5)
    return until(lambda: js(p, f"document.querySelector('.profile-switch b')?.innerText === {json.dumps(name)}"), 5)


def ai_tab_ok(p, name):
    text = js(p, "document.querySelector('.profile-panel [role=tabpanel][data-state=active]')?.innerText") or ""
    return panel_tab(p) == "AI" and js(p, "document.querySelector('.profile-switch b')?.innerText") == name and all(w in text for w in ("Runs on", "Default mode"))


def engine(p):
    js(p, "document.dispatchEvent(new CustomEvent('still-mascot-clashes', { detail: [] }))")
    until(lambda: js(p, "!!window.__clashes"), 30)
    if MAC:
        path = next(f for f in rpc(p, "served")["files"] if "companion3d" in f)
        chunk = js(p, f"new URL({json.dumps(path)}, location.origin + '/').href")
    else:
        chunk = js(p, "performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('companion3d'))")
    js(p, f"import({json.dumps(chunk)}).then(m => window.__m = m)")
    return until(lambda: js(p, "!!window.__m"), 10)


def picture(p, look):
    from PIL import Image
    for _ in range(80):
        url = js(p, f"window.__m.picture({json.dumps(look)}, 'idle', 240, 'full', false, 0.35)")
        if url:
            return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
        time.sleep(.25)
    return None


def markings(p):
    from PIL import ImageChops
    engine(p)
    for form, shape in FORM_SHAPE.items():
        base = {"v": 2, "color": "#f39079", "shape": shape, "prop": "", "accessory": "", "form": form, "second": "#7a4a88", "eye": "round", "mouth": "smile", "top": "none", "finish": "matte"}
        picture(p, base)
        plain, worst = picture(p, base), {}
        for m in ("belly", "mask", "tips", "freckles"):
            img = picture(p, {**base, "marking": m, "mark": "#4a5263"})
            worst[m] = -1 if img is None or plain is None else sum(1 for v in ImageChops.difference(plain, img).convert("L").getdata() if v > 8)
        check(all(0 <= v <= 40 for v in worst.values()), f"{form}: a look saved with a belly, mask, tips or freckles marking draws the same as one without ({worst} px differ, 40 at most)")


def editor(p, name):
    open_panel(p, name)
    click_text(p, ".profile-stage-actions button", "Edit look")
    return until(lambda: js(p, "!!document.querySelector('.look-dialog .look-stage .mascot canvas, .look-dialog .look-stage .mascot img')"), 8)


def look_tab(p, name):
    click_text(p, ".look-tabs [role=tab]", name)
    time.sleep(.35)


def done_editor(p, button):
    click_text(p, ".look-dialog .look-foot button", button)
    until(lambda: not js(p, "!!document.querySelector('.look-dialog')"), 3)


def no_marking_ui(p):
    return js(p, "!document.querySelector(\".look-dialog [aria-label='Marking'], .look-dialog [aria-label='Marking color'], .look-dialog [data-option=belly], .look-dialog [data-option=mask], .look-dialog [data-option=tips], .look-dialog [data-option=freckles]\") && ![...document.querySelectorAll('.look-dialog .look-heading')].some(h => /marking/i.test(h.innerText))")


def marked(p):
    check(editor(p, "Mara"), "A companion saved with a marking opens and its look editor draws it")
    look_tab(p, "Colors")
    clean = no_marking_ui(p)
    for _ in range(8):
        click_text(p, ".look-surprise button", "Surprise me")
        time.sleep(.15)
        clean = clean and no_marking_ui(p)
    check(clean, "Colors has no Marking section or marking color, before or after Surprise me")
    click(p, ".look-foot button[aria-label=Undo]")
    done_editor(p, "Cancel")


def name_menu(p):
    open_panel(p, "Nikola")
    press(p, ".profile-switch")
    until(lambda: js(p, "!!document.querySelector('[role=menu]')"), 3)
    items = js(p, "[...document.querySelectorAll('[role=menu] [role=menuitem]')].map(e => e.innerText.trim().split('\\n')[0])") or []
    line = js(p, "document.querySelector('[role=menu] .profile-menu-two small')?.innerText") or ""
    check(popup_on_top(p, "[role=menu]") == "ok", f"The name menu opens above the panel, in view ({popup_on_top(p, '[role=menu]')})")
    check(items[:1] == ["AI settings"] and "Jonah" in items and "Local box" in line, f"The name menu: AI settings first, with what they run on ({line}), then the other companions ({items})")
    menu_item(p, "AI settings")
    check(until(lambda: ai_tab_ok(p, "Nikola"), 3), "AI settings in the name menu opens Nikola's AI tab")
    text = js(p, "document.querySelector('.profile-panel [role=tabpanel][data-state=active]')?.innerText") or ""
    check("Model and effort for each mode" in text and "No key needed" in text and js(p, "document.querySelectorAll('.profile-panel .tier-row').length") == 3,
          "The AI tab: the app, the default mode, the model and effort for Quick, Everyday and Thorough, and the key (none needed for this box)")
    press(p, ".profile-panel .tier-row [role=combobox]")
    until(lambda: js(p, "!!document.querySelector('[role=listbox]')"), 3)
    check(popup_on_top(p, "[role=listbox]") == "ok", f"A mode's model list opens above the panel ({popup_on_top(p, '[role=listbox]')})")
    escape(p)
    # a provider that needs a key: Add key goes to Settings, Models
    open_panel(p, "Zia")
    press(p, ".profile-switch")
    until(lambda: js(p, "!!document.querySelector('[role=menu]')"), 3)
    menu_item(p, "AI settings")
    until(lambda: ai_tab_ok(p, "Zia"), 3)
    row = js(p, "document.querySelector('.profile-key')?.innerText") or ""
    click_text(p, ".profile-key button", "Add key")
    went = until(lambda: "Model" in (js(p, "document.querySelector('.set-nav-item[aria-current=page]')?.innerText") or "") and not js(p, "!!document.querySelector('.profile-panel')"), 5)
    check("No key yet" in row and went, f"A provider that needs a key: the AI tab says No key yet, and Add key opens Settings, Models ({row!r}, {went}, tab {panel_tab(p)})")
    escape(p)
    until(lambda: not js(p, "!!document.querySelector('.settings-dialog')"), 3)


def composer(p):
    """AI settings… at the bottom of the message box's menus: the companion picked there, on its AI tab."""
    def from_menu(where, label, sel, item_sel, role, name):
        escape(p)
        press(p, sel)
        until(lambda: js(p, f"!!document.querySelector('[role={'menu' if role == 'menuitem' else 'listbox'}]')"), 3)
        seen = in_view(p, item_sel, "AI settings")
        menu_item(p, "AI settings", role)
        ok = until(lambda: ai_tab_ok(p, name), 4)
        check(seen == "ok" and ok, f"{where}: AI settings… at the bottom of the {label}, in view ({seen}), opens {name}'s AI tab")
        click(p, ".profile-head [aria-label=Close]")
        until(lambda: not js(p, "!!document.querySelector('.profile-panel')"), 3)

    escape(p)
    send(p, "new")
    until(lambda: js(p, "!!document.querySelector('.home-compose .composer')"), 10)
    time.sleep(.5)
    from_menu("New tab", "mode menu", ".home-compose [aria-label='Companion and mode']", "[role=menu] [role=menuitem]", "menuitem", "Nikola")
    send(p, "aiAdvanced", on=True)
    until(lambda: js(p, "!!document.querySelector(\".home-compose [aria-label='Effort']\")"), 8)
    from_menu("New tab", "model picker", ".home-compose [aria-label='Model']", "[role=listbox] [role=option]", "option", "Nikola")
    from_menu("New tab", "effort picker", ".home-compose [aria-label='Effort']", "[role=listbox] [role=option]", "option", "Nikola")
    send(p, "aiAdvanced", on=False)
    until(lambda: not js(p, "!!document.querySelector(\".home-compose [aria-label='Model']\")"), 5)
    send(p, "aiToggle")
    until(lambda: js(p, "!!document.querySelector(\".ai-sidebar [aria-label='Companion and mode']\")"), 10)
    who = (js(p, "document.querySelector('.ai-head-buddy')?.getAttribute('aria-label')") or "").replace("'s profile", "")
    from_menu("Side chat", "mode menu", ".ai-sidebar [aria-label='Companion and mode']", "[role=menu] [role=menuitem]", "menuitem", who)
    send(p, "aiToggle")


def more_menu(p):
    def more():
        until(lambda: not js(p, "!!document.querySelector('[role=menu], [role=alertdialog][data-state=open]')"), 2)  # the last one fades out (Escape now would close the panel)
        press(p, ".profile-head [aria-label=More]")
        return until(lambda: js(p, "!!document.querySelector('[role=menu][data-state=open]')"), 3)

    def items():
        return js(p, "[...document.querySelectorAll('[role=menu] [role=menuitem]')].map(e => e.innerText.trim())") or []

    open_panel(p, "Nikola")
    more()
    got = items()
    check(popup_on_top(p, "[role=menu]") == "ok", f"The ... menu opens above the panel, in view ({popup_on_top(p, '[role=menu]')})")
    check(got == ["AI settings", "Edit look", "Rename", "Duplicate", "Introduce yourself again", "Open chat in a tab", "Clear chat", "Close panel", "Fire Nikola"], f"The ... menu's items ({got})")
    menu_item(p, "AI settings")
    check(until(lambda: ai_tab_ok(p, "Nikola"), 3), "... AI settings opens the AI tab")
    more()
    menu_item(p, "Edit look")
    check(until(lambda: js(p, "!!document.querySelector('.look-dialog')"), 5), "... Edit look opens the look editor")
    done_editor(p, "Cancel")
    more()
    menu_item(p, "Rename")
    check(until(lambda: js(p, "document.activeElement?.matches('.profile-panel input') && document.activeElement.value === 'Nikola' && document.activeElement.selectionEnd - document.activeElement.selectionStart === 6"), 3)
          and panel_tab(p) == "General", "... Rename goes to General with the name selected")
    more()
    menu_item(p, "Duplicate")
    check(until(lambda: "Nikola 2" in mates(), 5) and until(lambda: js(p, "document.querySelector('.profile-switch b')?.innerText") == "Nikola 2", 3), "... Duplicate makes Nikola 2 and opens them")
    check(mates()["Nikola 2"].get("Setup") == "pending", "A copy introduces itself in its first chat")
    open_panel(p, "Mara")
    more()
    menu_item(p, "Introduce yourself again")
    asked = until(lambda: mates()["Mara"].get("Setup") == "pending", 5)
    more()
    check(asked and "Introduce yourself again" not in items(), "... Introduce yourself again: their next chat starts with Setup, and the item goes until then")
    escape(p)
    open_panel(p, "Nikola 2")
    # Fire: asks first (above the panel), Keep keeps them, Undo brings them back, then they go
    opened = more()
    picked = menu_item(p, "Fire Nikola 2")
    asked = until(lambda: js(p, "!!document.querySelector('[role=alertdialog][data-state=open]')"), 3)
    time.sleep(.4)
    check(asked and popup_on_top(p, "[role=alertdialog][data-state=open]") == "ok", f"... Fire asks first, above the panel ({opened}, {picked}, {items()}, {popup_on_top(p, '[role=alertdialog][data-state=open]')})")
    click_text(p, "[role=alertdialog][data-state=open] button", "Keep Nikola 2")
    time.sleep(.5)
    check("Nikola 2" in mates() and js(p, "!!document.querySelector('.profile-panel')"), "Keep Nikola 2 keeps them")
    more()
    menu_item(p, "Fire Nikola 2")
    until(lambda: js(p, "!!document.querySelector('[role=alertdialog][data-state=open]')"), 3)
    click_text(p, "[role=alertdialog][data-state=open] button", "Fire Nikola 2")
    undo = until(lambda: click_text(p, "[data-sonner-toast] button", "Undo"), 4)
    time.sleep(7)
    check(undo and "Nikola 2" in mates(), "Fire, then Undo: Nikola 2 stays")
    open_panel(p, "Nikola 2")
    more()
    menu_item(p, "Fire Nikola 2")
    until(lambda: js(p, "!!document.querySelector('[role=alertdialog][data-state=open]')"), 3)
    click_text(p, "[role=alertdialog][data-state=open] button", "Fire Nikola 2")
    check(until(lambda: "Nikola 2" not in mates(), 12), "Fire, left alone: Nikola 2 goes")
    # Clear chat: asks first, Undo keeps the chat, then it goes
    open_panel(p, "Nikola")
    more()
    menu_item(p, "Clear chat")
    asked = until(lambda: "Numbers check" in (js(p, "document.querySelector('[role=alertdialog][data-state=open]')?.innerText") or ""), 3)
    time.sleep(.4)
    check(asked and popup_on_top(p, "[role=alertdialog][data-state=open]") == "ok", f"... Clear chat asks first, naming the chat, above the panel ({asked}, {popup_on_top(p, '[role=alertdialog][data-state=open]')})")
    click_text(p, "[role=alertdialog][data-state=open] button", "Delete chat")
    undo = until(lambda: click_text(p, "[data-sonner-toast] button", "Undo"), 4)
    time.sleep(7)
    check(undo and any(c["Id"] == "c-nik" for c in chats()), "Clear chat, then Undo: the chat stays")
    more()
    menu_item(p, "Open chat in a tab")
    opened = until(lambda: not js(p, "!!document.querySelector('.profile-panel')") and js(p, "[...document.querySelectorAll('.tab-main')].some(t => t.getAttribute('aria-label')?.includes('Numbers check'))"), 6)
    check(opened, "... Open chat in a tab opens the chat in its own tab and closes the panel")
    open_panel(p, "Nikola")
    more()
    menu_item(p, "Clear chat")
    until(lambda: js(p, "!!document.querySelector('[role=alertdialog][data-state=open]')"), 3)
    click_text(p, "[role=alertdialog][data-state=open] button", "Delete chat")
    check(until(lambda: not any(c["Id"] == "c-nik" for c in chats()), 14), "Clear chat, left alone: the chat goes")
    # No chat yet: Chat with, and Close panel
    open_panel(p, "Zia")
    more()
    got = items()
    check("Chat with Zia" in got and "Clear chat" not in got and "Open chat in a tab" not in got, f"With no chat yet: Chat with Zia, and nothing to clear ({got})")
    menu_item(p, "Chat with Zia")
    check(until(lambda: not js(p, "!!document.querySelector('.profile-panel')") and "Ask Zia" in (js(p, "document.querySelector('.home-compose [aria-label=Message]')?.getAttribute('aria-placeholder')") or ""), 6),
          "... Chat with Zia closes the panel and picks Zia on the new tab page")
    open_panel(p, "Zia")
    more()
    menu_item(p, "Close panel")
    check(until(lambda: not js(p, "!!document.querySelector('.profile-panel')"), 3), "... Close panel closes it")


def reset(p):
    """A built-in companion's Reset: asks first, puts their start back, and Undo keeps what they had."""
    def pick():
        open_panel(p, "Jonah")
        press(p, ".profile-head [aria-label=More]")
        until(lambda: js(p, "!!document.querySelector('[role=menu][data-state=open]')"), 3)
        menu_item(p, "Reset to how Jonah started")
        return until(lambda: js(p, "!!document.querySelector('[role=alertdialog][data-state=open]')"), 3)

    asked = pick()
    click_text(p, "[role=alertdialog][data-state=open] button", "Reset")
    undo = until(lambda: click_text(p, "[data-sonner-toast] button", "Undo"), 4)
    time.sleep(1.5)
    check(asked and undo and mates()["Jonah"].get("Instructions") == "Be brief.", "... Reset asks first, and Undo keeps what Jonah had")
    pick()
    click_text(p, "[role=alertdialog][data-state=open] button", "Reset")
    check(until(lambda: mates()["Jonah"].get("Instructions") == "" and mates()["Jonah"].get("Name") == "Jonah", 10), "... Reset, left alone: Jonah is back to how they started")


SKIP = ("folder", "Close", "Fire", "Delete", "Forget", "Remove", "Reset", "Share")  # a system dialog, closing, destroying (checked above), or the clipboard


def sweep(p):
    """Every other button in the panel does something: the page changes, or Still is told."""
    open_panel(p, "Nikola")
    js(p, """window.__sent = 0; const w = window.chrome?.webview ?? window.webkit?.messageHandlers?.still
     if (w && !w.__wrapped) { const post = w.postMessage.bind(w); w.postMessage = m => { window.__sent++; return post(m) }; w.__wrapped = true }""")
    dead, tried = [], 0
    for tab in ("General", "Skills & plugins", "Routines", "Files", "Memory", "AI"):
        click_text(p, ".profile-tablist [role=tab]", tab)
        time.sleep(.5)
        labels = js(p, "[...document.querySelectorAll('.profile-panel [role=tabpanel][data-state=active] button:not([disabled])')].filter(b => b.offsetParent).map((b, i) => (b.getAttribute('aria-label') || b.innerText.trim().split('\\n')[0] || 'button') + '#' + i)") or []
        for label in labels:
            name, i = label.rsplit("#", 1)
            if any(s.lower() in name.lower() for s in SKIP):
                continue
            tried += 1
            js(p, """window.__muts = 0; window.__obs?.disconnect(); window.__obs = new MutationObserver(l => window.__muts += l.length)
             window.__obs.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true }); window.__was = window.__sent""")
            js(p, f"[...document.querySelectorAll('.profile-panel [role=tabpanel][data-state=active] button:not([disabled])')].filter(b => b.offsetParent)[{i}]?.click()")
            time.sleep(.5)
            if not js(p, "window.__muts > 0 || window.__sent > window.__was"):
                dead.append(f"{tab}: {name}")
            for _ in range(3):  # whatever it opened closes again; the panel stays
                if js(p, "!!document.querySelector(\"[role=menu][data-state=open], [role=alertdialog][data-state=open], [role=listbox], [data-slot=dialog-content]\")"):
                    escape(p)
            if not js(p, "!!document.querySelector('.profile-panel')"):
                open_panel(p, "Nikola")
            click_text(p, ".profile-tablist [role=tab]", tab)
            time.sleep(.2)
    check(tried >= 10 and not dead, f"Each of the panel's {tried} other buttons does something (dead: {dead})")


def classic_looks(p):
    for _, name, role, _ in BUILT_IN + [("nikola", "Nikola", "Analyst", "")]:
        before = mates()[name]["Look"]
        editor(p, name)
        disabled = js(p, "[...document.querySelectorAll('.look-tabs [role=tab]')].filter(t => t.disabled).map(t => t.innerText)")
        shown = {}
        for tab, group in (("Body", "Body"), ("Colors", "Body color"), ("Face", "Eyes"), ("Extras", "On top"), ("Start", "Starting looks")):
            look_tab(p, tab)
            shown[tab] = js(p, f"!!document.querySelector(\".look-body [aria-label='{group}'] [role=radio]\")")
        still_classic = js(p, "!!document.querySelector('.look-classic')")
        done_editor(p, "Cancel")
        check(disabled == [] and all(shown.values()) and still_classic and mates()[name]["Look"] == before,
              f"{role} {name}: every tab opens and works on the classic look; looking changes nothing ({disabled}, {shown})")
    # A change in each tab moves the look to the new style; Save keeps it
    picks = [("Leo", "Colors", ".look-colors[aria-label='Body color'] [aria-label='Mint']", lambda s: s.get("color") == "#93d6bd" and s.get("form") == "pebble" and s.get("top") == "antennae"),
             ("Jonah", "Body", ".look-dialog [data-option=block]", lambda s: s.get("form") == "block" and s.get("color") == "#f7a26a"),
             ("Ruth", "Face", ".look-dialog [data-option=sleepy]", lambda s: s.get("eye") == "sleepy" and s.get("color") == "#2fa496"),
             ("Nora", "Extras", ".look-dialog [data-option=tuft]", lambda s: s.get("top") == "tuft" and s.get("color") == "#a6cf9c"),
             ("Nikola", "Start", ".look-dialog [aria-label='Starting looks'] [aria-label='Coral pebble']", lambda s: s.get("color") == "#f39079" and s.get("form") == "pebble")]
    for name, tab, sel, ok in picks:
        editor(p, name)
        look_tab(p, tab)
        click(p, sel)
        time.sleep(.4)
        moved = not js(p, "!!document.querySelector('.look-classic')") and js(p, "!!document.querySelector('.look-surprise')")
        done_editor(p, "Save look")
        until(lambda: '"v":2' in mates()[name]["Look"], 5)
        saved = json.loads(mates()[name]["Look"])
        editor(p, name)
        again = not js(p, "!!document.querySelector('.look-classic')")
        done_editor(p, "Cancel")
        check(moved and ok(saved) and again and "marking" not in saved, f"{name}: a change in {tab} moves to the new style, keeping their colors and features; Save keeps it ({saved})")
    # A team look: one change, then it saves
    editor(p, "Maya")
    look_tab(p, "Start")
    click(p, ".look-dialog [data-team=research]")
    time.sleep(.3)
    held = js(p, "document.querySelector('.look-save').disabled")
    look_tab(p, "Face")
    click(p, ".look-dialog [data-option=wide]")
    time.sleep(.3)
    done_editor(p, "Save look")
    check(held and until(lambda: json.loads(mates()["Maya"]["Look"]).get("eye") == "wide" and json.loads(mates()["Maya"]["Look"]).get("v") == 2, 5), "Maya: a team look, one change, and Save keeps it")
    # Cancel puts the classic look back exactly
    before = mates()["Ivan"]["Look"]
    editor(p, "Ivan")
    look_tab(p, "Body")
    click(p, ".look-dialog [data-option=gumdrop]")
    look_tab(p, "Colors")
    click(p, ".look-colors[aria-label='Body color'] [aria-label='Poppy']")
    time.sleep(.3)
    changed = not js(p, "!!document.querySelector('.look-classic')")
    done_editor(p, "Cancel")
    time.sleep(.8)
    editor(p, "Ivan")
    back = js(p, "!!document.querySelector('.look-classic')")
    done_editor(p, "Cancel")
    check(changed and back and mates()["Ivan"]["Look"] == before, "Ivan: changes, then Cancel: the classic look comes back byte for byte")


def main():
    BIN.mkdir(parents=True)
    (PROFILE / "agents").mkdir(parents=True)
    (PROFILE / "ai").mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE)
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run"], "output": "stream-json"}))
    team = [{"Id": i, "Name": n, "Role": r, "Crew": k, "Job": f"{r} for the user.", "Look": classic(k), "Setup": "done", "Instructions": "Be brief." if i == "jonah" else ""} for i, n, r, k in BUILT_IN]
    hired = [{"Id": "nikola", "Name": "Nikola", "Role": "Analyst", "Job": "Checks numbers.", "Look": NIKOLA, "Ai": LOCAL, "Setup": "done"},
             {"Id": "zia", "Name": "Zia", "Role": "Writer", "Job": "Writes.", "Look": NIKOLA, "Ai": KEYED, "Setup": "done"},
             {"Id": "mara", "Name": "Mara", "Role": "Designer", "Job": "Draws.", "Look": MARKED, "Setup": "done"}]
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "ActiveId": "w1", "Tabs": [{"Id": "w1", "Title": "New tab", "Url": ""}],
        "Preferences": {"Width": 1260, "Height": 860, "AgentsEnabled": True, "Companions": hired[:1] + team + hired[1:], "AiHarness": LOCAL, "AiModels": {LOCAL: "m-1"},
            "ApiProviders": [{"Id": LOCAL, "Kind": "openai", "Name": "Local box", "Url": "http://127.0.0.1:9/v1", "NoKey": True, "Models": [{"Id": "m-1", "Efforts": ["low", "high"]}, {"Id": "m-2", "Efforts": []}]},
                             {"Id": KEYED, "Kind": "openai", "Name": "Keyed box", "Url": "http://127.0.0.1:9/v1", "Models": [{"Id": "k-1", "Efforts": []}]}]}}))
    (PROFILE / "ai" / "chats.json").write_text(json.dumps([{"Id": "c-nik", "Title": "Numbers check", "Harness": LOCAL, "Companion": "nikola", "Started": True, "Updated": "2026-11-01T10:00:00Z",
        "Messages": [{"Role": "user", "Text": "Do these add up?"}, {"Role": "assistant", "Text": "They do."}]}]))
    p = launch(EXE, PROFILE)
    try:
        send(p, "aiCheck")
        until(lambda: js(p, "!!document.querySelector('.composer')"), 30)
        time.sleep(1.5)
        for part in (markings, marked, name_menu, composer, more_menu, sweep, classic_looks, reset):
            if os.environ.get("PARTS") and part.__name__ not in os.environ["PARTS"].split(","):
                continue
            try:
                part(p)
            except Exception as e:  # one part failing doesn't hide the others
                check(False, f"{part.__name__} ran through ({type(e).__name__}: {e})")
                escape(p)
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
    mara = next((c for c in state().get("Preferences", {}).get("Companions", []) if c["Name"] == "Mara"), {})
    check(mara.get("Look") == UNMARKED, f"Mara's saved look loses its marking, the rest as it was ({mara.get('Look')})")


if __name__ == "__main__":
    try:
        main()
    finally:
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "result.json").write_text(json.dumps(RESULT, indent=2))
        failed = [c["name"] for c in RESULT["checks"] if not c["passed"]]
        print(("PASSED " if not failed else "FAILED ") + f"{len(RESULT['checks']) - len(failed)}/{len(RESULT['checks'])}", "->", RUN)
