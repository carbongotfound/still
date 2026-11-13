"""A companion at work in a tab: the tab keeps its site icon, and the companion's face sits on the icon's bottom-right
corner, about 60% of its size, ringed in the tab's own colour. Two companions in one tab: the last one active, with +1.
A page without an icon keeps the default one. The badge goes when the work is done. Checked in light and dark, on
an active and an inactive tab, and at 150% scale (on Windows; the Mac's screen is 200%). A fake app stands in for the
AI; its companions read the tab through Still's tools.

Run: python tests/desktop/tab_badge.py artifacts/Still-QA/Still.exe
Out: artifacts/tab-badge-*/ (kept when something fails), artifacts/screens/tab-badge-*.png
"""
import http.server
import json
from pathlib import Path
import shutil
import struct
import sys
import textwrap
import threading
import time
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, screens, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
RUN = ROOT / "artifacts" / ("tab-badge-" + uuid.uuid4().hex[:8])
PROFILE = RUN / "profile"
BIN = RUN / "bin"
FAILED = []
FAKE = textwrap.dedent(r'''
    import json, re, subprocess, sys, time
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    work = re.search(r"WORK(\d+) (\w+)", prompt[-1500:])
    if work:
        # Reads the tab over and over until the time is up.
        server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
        still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        n = 0
        def call(method, params):
            global n
            n += 1
            still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params}) + "\n").encode()); still.stdin.flush()
            for line in still.stdout:
                try: m = json.loads(line)
                except ValueError: continue
                if m.get("id") == n: return m
        call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
        still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
        end, i = time.time() + int(work.group(1)), 0
        while time.time() < end:
            say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t%d" % i, "name": "mcp__still__read_page", "input": {"tabId": work.group(2)}}]}})
            call("tools/call", {"name": "read_page", "arguments": {"tabId": work.group(2)}})
            say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t%d" % i}]}})
            i += 1
            time.sleep(.4)
        still.stdin.close()
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}})
''')
# One tab's icon as shown: the site icon or the default one, the badge's face, its ring, its count and label, and the
# colour behind the tab (the strip, or the selected tab's own).
ICON = """(id => { const row = document.querySelector(`.tab-row[data-tab-id="${id}"]`); if (!row) return null
 const box = e => e && (r => ({ x: r.x, y: r.y, w: r.width, h: r.height }))(e.getBoundingClientRect())
 const fav = row.querySelector('.tab-letter > img.tab-favicon'), badge = row.querySelector('.tab-agent'), face = badge?.querySelector('.mascot')
 const behind = row.classList.contains('is-selected') ? row.querySelector('.selected-tab') : row.closest('.top-tab-strip, .browser-sidebar')
 return { fav: fav && fav.complete && fav.naturalWidth > 0 && getComputedStyle(fav).visibility !== 'hidden' ? box(fav) : null,
  globe: !fav && !!row.querySelector('.tab-letter > svg'), face: box(face), file: face?.querySelector('img')?.naturalWidth ?? 0,
  ring: badge ? getComputedStyle(badge).boxShadow : null, fill: badge ? getComputedStyle(badge).backgroundColor : null,
  behind: behind ? getComputedStyle(behind).backgroundColor : null, count: badge?.querySelector('b')?.textContent ?? null, title: badge?.title ?? null } })"""


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    if not ok:
        FAILED.append(label)


def png(size, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class Site(http.server.BaseHTTPRequestHandler):
    PAGES = {"/blue": b'<!doctype html><link rel="icon" href="/icon.png"><title>Blue site</title><p>A page with an icon.</p>',
             "/plain": b"<!doctype html><title>Plain page</title><p>A page without one.</p>", "/icon.png": png(32, (37, 99, 235))}

    def do_GET(self):
        body = self.PAGES.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "image/png" if self.path.endswith(".png") else "text/html")
        self.send_header("Content-Length", str(len(body or b"")))
        self.end_headers()
        self.wfile.write(body or b"")

    def log_message(self, *_):
        pass


def icon(p, tab):
    return js(p, f"({ICON})({json.dumps(tab)})") or {}


def badge_ok(p, tab, at):
    """The site icon stays, the face sits on its bottom-right corner at about 60% of its size, ringed in the colour behind the tab."""
    i = icon(p, tab)
    fav, face = i.get("fav"), i.get("face")
    check(fav is not None, f"{at}: the site icon stays")
    if not (fav and face):
        check(False, f"{at}: the companion's badge shows ({i})")
        return i
    ratio = face["w"] / fav["w"]
    check(.55 <= ratio <= .7, f"{at}: the badge is about 60% of the icon ({face['w']:.1f} of {fav['w']:.1f}px, {ratio:.0%})")
    right, bottom = face["x"] + face["w"], face["y"] + face["h"]
    check(face["x"] > fav["x"] + fav["w"] / 2 and face["y"] > fav["y"] + fav["h"] / 2 and fav["x"] + fav["w"] - 1 <= right <= fav["x"] + fav["w"] + 6 and fav["y"] + fav["h"] - 1 <= bottom <= fav["y"] + fav["h"] + 6,
          f"{at}: on the icon's bottom-right corner (icon {fav}, badge {face})")
    check(i["ring"] == f"{i['behind']} 0px 0px 0px 1px" and i["fill"] == i["behind"], f"{at}: a 1px ring in the tab's colour ({i['ring']}; behind the tab {i['behind']})")
    return i


def main():
    site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{site.server_address[1]}"
    (PROFILE / "agents").mkdir(parents=True)
    BIN.mkdir(parents=True)
    (BIN / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(BIN / "fakeagent", BIN / "fake_agent.py")
    (PROFILE / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(BIN / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    (PROFILE / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": CREW, "AgentsEnabled": True, "AiHarness": "fake",
        "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}], "Width": 1400, "Height": 900},
        "Tabs": [{"Id": "a", "Title": "Blue site", "Url": url + "/blue"}, {"Id": "b", "Title": "Plain page", "Url": url + "/plain"}, {"Id": "c", "Title": "Home", "Url": "about:blank"}], "ActiveId": "c"}))
    p = launch(EXE, PROFILE)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        for tab in ("a", "b", "c"):  # tabs restored in the background load when first shown
            send(p, "select", id=tab)
            until(lambda: rpc(p)["activeId"] == tab, 5)
            time.sleep(1.5)
        check(until(lambda: icon(p, "a").get("fav") and icon(p, "b").get("globe"), 20), f"The tabs show the site's icon, and the default one for a page without ({icon(p, 'a')}, {icon(p, 'b')})")
        check(not icon(p, "a").get("face"), "No badge before a companion works there")

        # Maya reads tab A from the side panel of tab C: A is an inactive tab.
        send(p, "aiToggle")
        send(p, "aiSend", text="WORK80 a", companion="maya")
        check(until(lambda: icon(p, "a").get("face"), 15), "A companion at work in a tab puts its badge on the tab's icon")
        check(icon(p, "a").get("count") is None and icon(p, "a").get("title") == "Maya is using this tab", f"...Maya's, alone ({icon(p, 'a').get('title')!r})")
        for theme in ("Light", "Dark"):
            send(p, "preference", key="theme", value=theme)
            time.sleep(.8)
            badge_ok(p, "a", f"{theme}, inactive tab")
        screens(p, PROFILE, "tab-badge-inactive")

        # Nora on tab B, a page without an icon: the default icon stays, and her badge goes when she's done.
        send(p, "aiNew")
        time.sleep(.5)
        send(p, "aiSend", text="WORK8 b", companion="nora")
        check(until(lambda: icon(p, "b").get("face"), 15), "A page without an icon gets the badge too")
        b = icon(p, "b")
        check(b.get("globe") and b.get("title") == "Nora is using this tab", f"...on the default icon, as usual ({b.get('globe')}, {b.get('title')!r})")
        check(until(lambda: not icon(p, "b").get("face"), 30) and icon(p, "b").get("globe"), "When she's done the badge goes, the default icon stays")
        check(icon(p, "a").get("title") == "Maya is using this tab", "...while Maya's stays on her tab")

        # Nora joins Maya on tab A: the last one active, and +1.
        send(p, "aiSend", text="WORK25 a", companion="nora")
        check(until(lambda: icon(p, "a").get("count") == "+1", 15), f"Two companions in one tab: one face and +1 ({icon(p, 'a').get('count')!r})")
        a = icon(p, "a")
        check(a.get("title") in ("Maya and 1 more are using this tab", "Nora and 1 more are using this tab"), f"...the last one active, and one more ({a.get('title')!r})")
        check(a.get("fav") is not None, "...with the site icon still there")
        screens(p, PROFILE, "tab-badge-two")

        send(p, "select", id="a")
        check(until(lambda: rpc(p)["activeId"] == "a", 5), "Tab A in front")
        for theme in ("Light", "Dark"):
            send(p, "preference", key="theme", value=theme)
            time.sleep(.8)
            badge_ok(p, "a", f"{theme}, active tab")
        screens(p, PROFILE, "tab-badge-active")

        if MAC:
            dpr = js(p, "devicePixelRatio")
            check(icon(p, "a").get("file", 0) >= 10 * dpr, f"At the Mac's {dpr:.0%} the badge uses a sharp enough picture ({icon(p, 'a').get('file')}w)")
        else:
            for scale in (1.5,):
                rpc(p, "shellCdp", method="Emulation.setDeviceMetricsOverride", parameters={"width": 0, "height": 0, "deviceScaleFactor": scale, "mobile": False})
                time.sleep(.8)
                for theme in ("Light", "Dark"):
                    send(p, "preference", key="theme", value=theme)
                    time.sleep(.8)
                    badge_ok(p, "a", f"{theme}, {scale:.0%}")
                    rpc(p, "capture", name="scaled.png")
                    (ROOT / "artifacts" / "screens" / f"tab-badge-active-{int(scale * 100)}-{theme.lower()}.png").write_bytes((PROFILE / "scaled.png").read_bytes())
                check(js(p, "devicePixelRatio") == scale and until(lambda: icon(p, "a").get("file", 0) >= 10 * scale, 5), f"At {scale:.0%} the badge uses a sharp enough picture ({icon(p, 'a').get('file')}w)")
            rpc(p, "shellCdp", method="Emulation.clearDeviceMetricsOverride", parameters={})
            send(p, "preference", key="theme", value="Light")

        check(until(lambda: not icon(p, "a").get("face"), 100), "When both are done the badge goes")
        check(icon(p, "a").get("fav") is not None, "...and the site icon stays")
        errors = rpc(p).get("shellErrors")
        check(not errors, f"No interface errors ({errors})" if errors else "No interface errors")
    except Exception as ex:
        check(False, f"The run finished ({type(ex).__name__}: {ex})")
    finally:
        rpc(p, "quit")
        p.wait(timeout=20)
        site.shutdown()
    if FAILED:
        print(f"FAILED {len(FAILED)}: {FAILED} -> {RUN}")
    else:
        print("PASSED")
        shutil.rmtree(RUN, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
