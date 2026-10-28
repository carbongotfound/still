"""Phase 5: tabs. Layouts, hover actions, Ctrl+Tab, Ctrl+Alt+arrows, groups, split view, moving a tab to a new window
without a reload, the address bar's learned picks, and frame times while tabs change.

Run: python tests/desktop/tab_tools.py artifacts/Still-QA/Still.exe
Screenshots: docs/agentic/compare/ (tabs-modern-v01, tabs-groups-v01, tabs-split-v01, tabs-recent-v01)
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
RUN = ROOT / "artifacts" / ("tabs-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
OUT = ROOT / "docs" / "agentic" / "compare"
RESULT = {"checks": []}
COLORS = {"a": "#e8f0fe", "b": "#fdeee4", "c": "#e6f4ea", "d": "#f3e8fd"}


def check(ok, name):
    RESULT["checks"].append({"name": name, "passed": bool(ok)})
    print(("PASS " if ok else "FAIL ") + name, flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.strip("/")[:1] or "a"
        body = (f"<!doctype html><meta charset=utf-8><title>Page {name.upper()}</title><body style='margin:0;font:28px system-ui;"
                f"background:{COLORS.get(name, '#fff')};display:grid;place-items:center;height:100vh'>Page {name.upper()}").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{server.server_address[1]}"
IDS = ["a", "b", "c", "d"]


def tabs(process):
    return rpc(process, "tabs")


def state(process):
    return rpc(process)


def active(process):
    return state(process)["activeId"]


def shell(process, script):
    return js(process, script)


def capture(process, name):
    time.sleep(.8)
    rpc(process, "capture", name="shot.png")
    shutil.copy(PROFILE / "shot.png", OUT / f"{name}-v01.png")


# 60 frames a second: under 17.5 ms. On the Mac, WebKit's frame times jitter: about 1 in 10 run 18 to 23 ms even while
# Still's main thread sits idle (measured with `sample`). A dropped frame shows as 33 ms, so there the budget is 25 ms:
# it catches dropped frames, not jitter.
BUDGET = 25 if MAC else 17.5


def frames(process, act):
    """Frame intervals in the shell while act() runs: the 95th percentile and the worst, in ms."""
    shell(process, "window.__frames=[];window.__frameOn=true;(()=>{let last=performance.now();const tick=t=>{window.__frames.push(t-last);last=t;if(window.__frameOn)requestAnimationFrame(tick)};requestAnimationFrame(tick)})()")
    time.sleep(.3)
    act()
    time.sleep(.4)
    values = sorted(json.loads(shell(process, "window.__frameOn=false;JSON.stringify(window.__frames.slice(2))")))
    return values[int(len(values) * .95)] if values else 0, values[-1] if values else 0, len(values)


def main():
    PROFILE.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False,
        "Preferences": {"Theme": "Light", "Width": 1720, "Height": 1080, "TabTearOff": True},
        "Tabs": [{"Id": i, "Title": "Page " + i.upper(), "Url": f"{URL}/{i}"} for i in IDS], "ActiveId": "a"}))
    process = launch(EXE, PROFILE)
    try:
        run(process)
    finally:
        try:
            rpc(process, "quit")
            process.wait(timeout=15)
        except Exception:
            process.kill()
        server.shutdown()
    passed = sum(c["passed"] for c in RESULT["checks"])
    (RUN / "result.json").write_text(json.dumps(RESULT, indent=1))
    print(("PASSED" if passed == len(RESULT["checks"]) else "FAILED") + f" {passed}/{len(RESULT['checks'])} -> {RUN}")
    sys.exit(0 if passed == len(RESULT["checks"]) else 1)


def run(process):
    for i in IDS:  # load every page, so each tab has a live view
        send(process, "select", id=i)
        until(lambda: tabs(process)["windows"][0]["active"] == i and all(t["Id"] != i or t["wired"] for t in tabs(process)["windows"][0]["tabs"]))
    send(process, "select", id="a")
    until(lambda: active(process) == "a")

    # ---- layouts ----
    check(tabs(process)["layout"] == "Classic" and shell(process, "!!document.querySelector('.top-tab-strip')&&!document.querySelector('.browser-sidebar')"),
          "Classic, with tabs on top, is the default")
    send(process, "preference", key="tabLayout", value="Modern")
    check(until(lambda: shell(process, "!!document.querySelector('.browser-sidebar')&&!document.querySelector('.top-tab-strip:not(.modern-strip)')"), 5)
          and tabs(process)["layout"] == "Modern", "Modern puts the tabs down the side")
    check(shell(process, "document.querySelectorAll('.browser-sidebar [data-tab-id]').length") == 4, "The sidebar lists every tab")
    width = shell(process, "Math.round(document.querySelector('.browser-sidebar').getBoundingClientRect().width)")
    send(process, "sidebarResize", width=300)
    check(until(lambda: shell(process, "Math.round(document.querySelector('.browser-sidebar').getBoundingClientRect().width)") == 300, 5) and width == 248,
          "The sidebar resizes and remembers its width")
    capture(process, "tabs-modern")
    rpc(process, "key", key="S", mods="Control, Shift")
    check(until(lambda: tabs(process)["layout"] == "Classic" and shell(process, "!document.querySelector('.browser-sidebar')"), 5), "Ctrl+Shift+S switches back to tabs on top")

    # ---- hover shows only the X; the rest is in the right-click menu ----
    VISIBLE = "[...document.querySelectorAll('[data-tab-id=\"%s\"] button:not(.tab-main)')].filter(b=>{const c=getComputedStyle(b),r=b.getBoundingClientRect();return c.display!=='none'&&c.visibility!=='hidden'&&+c.opacity>.5&&r.width>0}).map(b=>b.getAttribute('aria-label'))"
    def hover_buttons(i):
        r = json.loads(shell(process, "JSON.stringify((r=>({x:r.left+r.width/2,y:r.top+r.height/2}))(document.querySelector('[data-tab-id=\"%s\"]').getBoundingClientRect()))" % i))
        rpc(process, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": r["x"], "y": r["y"]})
        time.sleep(.8 if MAC else .3)  # the Mac first brings Still forward: only the active app gets hover
        return json.loads(shell(process, "JSON.stringify(" + VISIBLE % i + ")"))
    for layout in ["Classic", "Modern"]:
        send(process, "preference", key="tabLayout", value=layout)
        until(lambda: tabs(process)["layout"] == layout, 5)
        time.sleep(.4)
        shown = hover_buttons("b")
        check(shown == ["Close Page B"], f"{layout}: hovering a tab shows exactly one button, the X ({', '.join(shown)})")
        size = shell(process, "(r=>Math.round(r.width)+'x'+Math.round(r.height)+'@'+Math.round(document.querySelector('[data-tab-id=\"b\"]').getBoundingClientRect().right-r.right))(document.querySelector('[data-tab-id=\"b\"] .close-tab').getBoundingClientRect())")
        check(size == "22x22@6", f"{layout}: the X is 22 by 22 at the right edge ({size})")
        rpc(process, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": 2, "y": 600})
        time.sleep(.8 if MAC else .3)  # the Mac first brings Still forward: only the active app gets hover
        on, other = (json.loads(shell(process, "JSON.stringify(" + VISIBLE % i + ")")) for i in "ab")
        check(on == ["Close Page A"] and other == [], f"{layout}: the tab you're on keeps its X; the others show it only on hover ({on}, {other})")
        capture(process, f"tabs-hover-{layout.lower()}")
    send(process, "preference", key="tabLayout", value="Classic")
    until(lambda: tabs(process)["layout"] == "Classic", 5)
    send(process, "pin", id="d")
    until(lambda: any(t["Id"] == "d" and t["Pinned"] for t in state(process)["tabs"]), 5)
    check(hover_buttons("d") == [], "A pinned tab shows only its icon, with no X")
    send(process, "pin", id="d")
    until(lambda: not any(t["Id"] == "d" and t["Pinned"] for t in state(process)["tabs"]), 5)
    def menu(i):
        until(lambda: shell(process, "!document.querySelector('[role=menu]')"), 3)  # the last menu has finished closing
        shell(process, "(t=>{const r=t.getBoundingClientRect();t.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,button:2,clientX:r.left+20,clientY:r.top+10}))})(document.querySelector('[data-tab-id=\"%s\"]'))" % i)
        return until(lambda: json.loads(shell(process, "JSON.stringify([...document.querySelectorAll('[role=menuitem]')].map(i=>i.textContent))")), 3) or []
    def pick(label):
        shell(process, "[...document.querySelectorAll('[role=menuitem]')].find(i=>i.textContent.startsWith(%s)).click()" % json.dumps(label))
    items = menu("b")
    names = ["Pin tab", "Bookmark", "Copy link", "Duplicate", "Close tab"] + ([] if state(process).get("noAi") else ["Open in chat"])
    check(all(any(t.startswith(n) for t in items) for n in names), f"The right-click menu has Pin, Bookmark, Copy link, Open in chat, Duplicate and Close ({' | '.join(items)})")
    check(any(t.startswith("Pin tab") and t.endswith("⇧⌘P" if MAC else "Ctrl Shift P") for t in items) and any(t.startswith("Bookmark") and t.endswith("⌘D" if MAC else "Ctrl D") for t in items),
          "The menu shows the keyboard shortcuts")
    capture(process, "tabs-menu")
    pick("Bookmark")
    check(until(lambda: any(v["Url"] == f"{URL}/b" for v in state(process)["bookmarks"]), 5) and active(process) == "a",
          "Bookmark in the menu saves that tab, not the one you're on")
    menu("b"); pick("Remove bookmark")
    check(until(lambda: not any(v["Url"] == f"{URL}/b" for v in state(process)["bookmarks"]), 5), "Choosing it again removes the bookmark")
    menu("d"); pick("Pin tab")
    check(until(lambda: any(t["Id"] == "d" and t["Pinned"] for t in state(process)["tabs"]), 5), "Pin in the menu pins the tab")
    if any(t["Id"] == "d" and t["Pinned"] for t in state(process)["tabs"]): send(process, "pin", id="d")
    until(lambda: not any(t["Id"] == "d" and t["Pinned"] for t in state(process)["tabs"]), 5)
    rpc(process, "key", key="D", mods="Control")
    check(until(lambda: any(v["Url"] == f"{URL}/a" for v in state(process)["bookmarks"]), 5), "Ctrl+D still bookmarks the page")
    rpc(process, "key", key="D", mods="Control")
    until(lambda: not any(v["Url"] == f"{URL}/a" for v in state(process)["bookmarks"]), 5)

    send(process, "new", url=URL + "/d")
    extra = until(lambda: next((t["Id"] for t in state(process)["tabs"] if t["Id"] not in IDS), None), 5)
    send(process, "select", id="a")
    until(lambda: active(process) == "a")
    shell(process, "document.querySelector('[data-tab-id=\"%s\"]').dispatchEvent(new MouseEvent('auxclick',{bubbles:true,cancelable:true,button:1}))" % extra)
    check(bool(extra) and until(lambda: extra not in tabs(process)["order"], 5), "Middle-click still closes a tab")

    # ---- Ctrl+Tab: most recent first ----
    for i in ["b", "c", "a"]:
        send(process, "select", id=i)
        until(lambda: active(process) == i)
        time.sleep(.05)
    rpc(process, "key", key="Tab", mods="Control")  # no key is really held, so it switches at once
    check(until(lambda: active(process) == "c", 3), "Ctrl+Tab goes back to the tab you used last")
    rpc(process, "key", key="Tab", mods="Control")
    check(until(lambda: active(process) == "a", 3), "Pressing it again flips back")
    send(process, "recent", step=1, held=True)
    check(until(lambda: shell(process, "!!document.querySelector('.recent-switcher')"), 3), "Holding Ctrl shows the recent tabs list")
    order = json.loads(shell(process, "JSON.stringify([...document.querySelectorAll('.recent-item')].map(b=>b.querySelector('.recent-title').firstChild.textContent))"))
    check(order[:3] == ["Page A", "Page C", "Page B"], f"The list is in the order you used them ({', '.join(order)})")
    send(process, "recent", step=1, held=True)
    check(until(lambda: tabs(process)["recentIndex"] == 2 and shell(process, "document.querySelector('.recent-item.is-picked .recent-title').firstChild.textContent") == "Page B", 3),
          "Tab moves down the list")
    capture(process, "tabs-recent")
    rpc(process, "key", key="Escape", mods="None")
    check(until(lambda: not shell(process, "!!document.querySelector('.recent-switcher')"), 3) and active(process) == "a", "Escape closes the list and stays put")
    send(process, "recent", step=1, held=True)
    until(lambda: shell(process, "!!document.querySelector('.recent-switcher')"), 3)
    shell(process, "document.querySelectorAll('.recent-item')[2].click()")
    check(until(lambda: active(process) == "b" and not shell(process, "!!document.querySelector('.recent-switcher')"), 3), "Clicking a tab in the list switches to it")

    # ---- Ctrl+Alt+arrows: strip order ----
    order = tabs(process)["order"]
    rpc(process, "key", key="Right", mods="Control, Alt")
    check(until(lambda: active(process) == order[(order.index("b") + 1) % len(order)], 3), "Ctrl+Alt+Right goes to the next tab")
    rpc(process, "key", key="Left", mods="Control, Alt")
    rpc(process, "key", key="Left", mods="Control, Alt")
    check(until(lambda: active(process) == order[(order.index("b") - 1) % len(order)], 3), "Ctrl+Alt+Left goes to the previous tab")

    # ---- groups ----
    send(process, "select", id="a")
    send(process, "groupNew", id="a")
    group = until(lambda: (g := tabs(process)["groups"]) and g[0], 5)
    check(group and group["Color"] == "blue" and any(t["Group"] == group["Id"] for t in tabs(process)["windows"][0]["tabs"] if t["Id"] == "a"),
          "Add to new group makes a colored group")
    check(until(lambda: shell(process, "document.activeElement?.classList.contains('tab-group-name')"), 3), "The new group asks for a name")
    shell(process, "(()=>{const i=document.querySelector('.tab-group-name');const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(i,'Research');i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))})()")
    check(until(lambda: tabs(process)["groups"][0]["Name"] == "Research" and "Research" in shell(process, "document.querySelector('.tab-group-chip')?.textContent||''"), 3),
          "Naming the group shows it on the chip")
    send(process, "groupAdd", id="c", group=group["Id"])
    check(until(lambda: tabs(process)["order"][:2] == ["a", "c"], 3), "A tab added to a group moves next to it")
    send(process, "groupSet", group=group["Id"], color="green")
    check(until(lambda: shell(process, "document.querySelector('.tab-group')?.dataset.color") == "green", 3), "The group's color changes")
    capture(process, "tabs-groups")
    send(process, "groupSet", group=group["Id"], collapsed=True)
    check(until(lambda: shell(process, "document.querySelectorAll('.tab-group [data-tab-id]').length") == 1 and shell(process, "document.querySelectorAll('.tab-group-icons img, .tab-group-icons svg').length") == 2, 3),
          "Collapsing hides the group's other tabs and shows their icons")
    send(process, "select", id="b")
    check(until(lambda: shell(process, "document.querySelectorAll('.tab-group [data-tab-id]').length") == 0, 3), "A collapsed group keeps only the tab you're on")
    send(process, "groupSet", group=group["Id"], collapsed=False)
    send(process, "reorder", id="b", before="c")
    check(until(lambda: tabs(process)["order"][:3] == ["a", "b", "c"] and next(t for t in tabs(process)["windows"][0]["tabs"] if t["Id"] == "b")["Group"] == group["Id"], 3),
          "Dropping a tab between two of a group's tabs adds it")
    send(process, "groupRemove", id="b")
    check(until(lambda: tabs(process)["order"][:3] == ["a", "c", "b"] and next(t for t in tabs(process)["windows"][0]["tabs"] if t["Id"] == "b")["Group"] == "", 3),
          "Remove from group moves it out past the group")
    send(process, "preference", key="tabLayout", value="Modern")
    until(lambda: shell(process, "!!document.querySelector('.browser-sidebar .tab-group')"), 5)
    capture(process, "tabs-groups-modern")
    send(process, "preference", key="tabLayout", value="Classic")
    send(process, "groupUngroup", group=group["Id"])
    check(until(lambda: not tabs(process)["groups"] or not shell(process, "!!document.querySelector('.tab-group')"), 3)
          and all(t["Group"] == "" for t in tabs(process)["windows"][0]["tabs"]), "Ungroup keeps the tabs and drops the group")

    # ---- split view ----
    send(process, "select", id="a")
    until(lambda: active(process) == "a")
    send(process, "split", id="b", side="right")
    split = until(lambda: (s := tabs(process)["split"]) and s["partner"] == "b" and s["rightVisible"] and s["leftWidth"] and s
                  and abs(s["leftWidth"] - s["rightWidth"]) <= 1 and s, 5)
    check(split and split["left"] == "a" and split["right"] == "b", "Dropping a tab on the right half opens it beside this one")
    check(until(lambda: shell(process, "!!document.querySelector('.split-button.is-on')&&!!document.querySelector('.split-divider')"), 3), "The split button and the divider show")
    capture(process, "tabs-split")
    send(process, "splitRatio", ratio=.3)
    s = until(lambda: (s := tabs(process)["split"]) and abs(s["leftWidth"] / (s["leftWidth"] + s["rightWidth"]) - .3) < .02 and s, 3)
    check(s, "Dragging the divider resizes both sides")
    send(process, "splitRatio", ratio=.5)
    send(process, "splitSwap")
    check(until(lambda: tabs(process)["split"]["left"] == "b" and tabs(process)["split"]["right"] == "a", 3), "Swap sides")
    send(process, "select", id="c")
    check(until(lambda: tabs(process)["split"]["partner"] is None and not tabs(process)["split"]["leftVisible"], 3), "Another tab shows on its own")
    send(process, "select", id="b")
    check(until(lambda: (s := tabs(process)["split"])["partner"] == "a" and s["rightVisible"] and s["leftVisible"], 3), "Going back to either tab shows the pair again")
    p95, worst, count = frames(process, lambda: [send(process, "select", id=i) or time.sleep(.12) for i in ["c", "b", "d", "a", "c", "b"]])
    RESULT["frames_switch"] = {"p95": p95, "worst": worst, "frames": count, "budget": BUDGET}
    check(p95 < BUDGET, f"Switching tabs keeps 60 frames a second (p95 {p95:.1f} ms, worst {worst:.1f} ms, budget {BUDGET:.1f})")
    send(process, "splitEnd")
    check(until(lambda: tabs(process)["split"]["left"] is None and not shell(process, "!!document.querySelector('.split-divider')"), 3), "Separate tabs ends the split")

    # Dragging a tab onto the page: the half under the pointer lights up, and dropping splits.
    send(process, "select", id="a")
    until(lambda: active(process) == "a")
    shell(process, """(()=>{const tab=document.querySelector('[data-tab-id="c"]'),r=tab.getBoundingClientRect(),p=document.querySelector('.page-slot').getBoundingClientRect();
     const at=(type,x,y,buttons)=>tab.dispatchEvent(new PointerEvent(type,{bubbles:true,pointerId:7,button:0,buttons,clientX:x,clientY:y}));
     at('pointerdown',r.left+20,r.top+10,1);at('pointermove',r.left+40,r.top+60,1);at('pointermove',p.left+p.width*.25,p.top+p.height/2,1);
     window.__drop=()=>at('pointerup',p.left+p.width*.25,p.top+p.height/2,0)})()""")
    check(until(lambda: shell(process, "document.querySelector('.split-zone.is-on')?.textContent||''") == "Open on the left", 3), "Dragging a tab over the page lights up that half")
    capture(process, "tabs-split-drop")
    shell(process, "window.__drop()")
    check(until(lambda: (s := tabs(process)["split"])["left"] == "c" and s["right"] == "a" and s["leftVisible"] and s["rightVisible"], 5)
          and not shell(process, "!!document.querySelector('.split-zones')"), "Dropping it there opens it on that side")
    send(process, "openPanel", name="settings")
    check(until(lambda: shell(process, "document.querySelectorAll('.page-snapshot').length") == 2, 5), "A menu over a split view keeps both halves on screen")
    capture(process, "tabs-split-menu")
    send(process, "panel", name="")
    rpc(process, "key", key="Escape", mods="None")
    check(until(lambda: (s := tabs(process)["split"])["leftVisible"] and s["rightVisible"] and rpc(process)["viewport"]["visible"] == "Visible", 5), "Closing it shows both pages again")
    shell(process, "document.querySelector('.split-button').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerType:'mouse'}))")
    items = until(lambda: json.loads(shell(process, "JSON.stringify([...document.querySelectorAll('[role=menuitem]')].map(i=>i.textContent))")), 3) or []
    check(items[:2] == ["Swap sides", "Resize to 50/50"] and items[2:4] == ["Close leftPage C", "Close rightPage A"] and items[-1] == "Separate tabs",
          f"The split button offers Swap, 50/50, Close left, Close right and Separate ({' | '.join(items)})")
    capture(process, "tabs-split-options")
    shell(process, "[...document.querySelectorAll('[role=menuitem]')].find(i=>i.textContent.startsWith('Close left')).click()")
    check(until(lambda: "c" not in tabs(process)["order"] and tabs(process)["split"]["left"] is None and active(process) == "a", 5), "Close left closes that page and ends the split")

    # ---- group operations hold 60 frames a second ----
    send(process, "groupNew", id="b")
    gid = until(lambda: (g := tabs(process)["groups"]) and g[0]["Id"], 3)
    shell(process, "document.activeElement?.blur()")
    p95, worst, count = frames(process, lambda: [send(process, "groupSet", group=gid, collapsed=bool(n % 2 == 0)) or time.sleep(.15) for n in range(6)])
    RESULT["frames_group"] = {"p95": p95, "worst": worst, "frames": count}
    check(p95 < BUDGET, f"Collapsing and expanding a group keeps 60 frames a second (p95 {p95:.1f} ms, worst {worst:.1f} ms, budget {BUDGET:.1f})")
    send(process, "groupUngroup", group=gid)

    # ---- learned picks ----
    send(process, "addressPick", typed="Pa", url=f"{URL}/c")
    send(process, "addressPick", typed="pa", url=f"{URL}/c")
    check(until(lambda: any(p["Typed"] == "pa" and p["Count"] == 2 for p in tabs(process)["picks"]), 3), "The address bar remembers what you picked for what you typed")
    send(process, "new", url=URL + "/d", private=True)
    until(lambda: any(t["Private"] for t in state(process)["tabs"]))
    send(process, "addressPick", typed="pr", url=f"{URL}/d")
    time.sleep(.5)
    check(not any(p["Typed"] == "pr" for p in tabs(process)["picks"]), "Private tabs don't teach it anything")

    # ---- drag a tab out of the window: it opens where it's dropped, without a reload ----
    rpc(process, "evalTab", id="b", script="window.__kept = 7")
    windows = len(tabs(process)["windows"])
    left = state(process)["left"]
    shell(process, """(()=>{const tab=document.querySelector('[data-tab-id="b"]'),r=tab.getBoundingClientRect();
     const at=(type,x,y,buttons,sx,sy)=>tab.dispatchEvent(new PointerEvent(type,{bubbles:true,pointerId:8,button:0,buttons,clientX:x,clientY:y,screenX:sx,screenY:sy}));
     at('pointerdown',r.left+20,r.top+10,1,0,0);at('pointermove',r.left+20,r.top+40,1,0,0);at('pointermove',-40,300,1,%d,380);at('pointerup',-40,300,0,%d,380)})()""" % (left + 300, left + 300))
    torn = until(lambda: (w := tabs(process)["windows"]) and len(w) > windows and any(t["Id"] == "b" and t["wired"] for x in w[1:] for t in x["tabs"]), 10)
    placed = [w for w in state(process)["windows"] if any("/b" in u for u in w["tabs"])]
    check(torn and placed and placed[0]["left"] < left + 300, f"Dragging a tab out of the window opens it where you drop it ({placed[0]['left'] if placed else None})")
    check(rpc(process, "evalTab", id="b", script="window.__kept") == 7, "The torn-off page didn't reload")

    # ---- move a tab to a new window: no reload ----
    send(process, "select", id="d")
    until(lambda: active(process) == "d")
    rpc(process, "evalTab", id="d", script="window.__kept = 42")
    send(process, "moveTab", id="d", window="new")
    moved = until(lambda: any(t["Id"] == "d" and t["wired"] for w in tabs(process)["windows"][1:] for t in w["tabs"]), 10)
    check(moved and not any(t["Id"] == "d" for t in tabs(process)["windows"][0]["tabs"]), "Dragging a tab out opens it in its own window")
    check(rpc(process, "evalTab", id="d", script="window.__kept") == 42, "The page keeps its state: it didn't reload")


if __name__ == "__main__":
    main()
