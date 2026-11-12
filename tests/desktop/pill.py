"""The pill over a page an AI drives, paused for a sign-in ("Sign in, then hand it back", Hand back, Open chat, Stop), on a
white page, a dark page and a busy picture, light and dark, at each scale asked (on Windows through WebView2's
--force-device-scale-factor, so the interface really renders at that scale on this display; the window itself stays at
the display's own scale):
- Still's own surface and border tokens (no tint) and a soft shadow; Hand back filled in the accent (--pop with --ink),
  Open chat quiet (no fill), Stop a calm icon button (an SVG square) muted red until hover, then full red; its tooltip "Stop";
- the title in normal weight, the subtitle muted; the chevron, the face, the text and the pill on one center line; the
  same padding at both ends; a subtitle too long for its room ends in an ellipsis, with the whole line as its tooltip;
- the face is a file drawn for its size at this scale (within 10%: at 200% the 32px face takes the largest file, 60px),
  and nothing moves the pill by a transform (which isn't snapped to pixels, so it blurs the text and edges);
- Windows, in the real window (PrintWindow, physical pixels): round the pill's ends the page meets it through in-between
  pixels (smoothed, not stair-stepped), there's a shadow under it on the white page, and the window that draws that over
  the page takes no clicks.
A fake agent app opens each page from the side chat and reads it, so no AI plan is used and nothing signs in.

Run: python tests/desktop/pill.py artifacts/Still-QA/Still.exe [--scales 1,1.5] [--shots DIR]
--shots DIR saves pill-<os>-<scale>-<theme>-<page>.png (the pill and round it) and the same at 400% (-x4).
"""
import ctypes
import http.server
import json
import os
import socket
from pathlib import Path
import sys
import textwrap
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, MAC, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
SHOTS = Path(sys.argv[sys.argv.index("--shots") + 1]) if "--shots" in sys.argv else None
SCALES = [float(s) for s in sys.argv[sys.argv.index("--scales") + 1].split(",")] if "--scales" in sys.argv else [1, 1.5]
FAILS, PASSES = [], [0]
GROUP = [""]
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)

FORM = ('<form onsubmit="return false"><label>Email<input name=username autocomplete=username placeholder="Email"></label>'
        '<label>Password<input type=password name=password autocomplete=current-password placeholder="Password"></label><button>Sign in</button></form>')
BUSY = """<canvas id=c></canvas><script>const c = document.getElementById('c'), k = c.getContext('2d'); c.width = innerWidth; c.height = innerHeight
let s = 7; const r = () => (s = s * 16807 % 2147483647) / 2147483647
for (let i = 0; i < 900; i++) { k.fillStyle = `hsl(${r() * 360} ${50 + r() * 50}% ${25 + r() * 60}%)`; k.beginPath(); k.arc(r() * c.width, r() * c.height, 4 + r() * 46, 0, 7); k.fill() }
for (let i = 0; i < 300; i++) { k.strokeStyle = `hsl(${r() * 360} 80% 60%)`; k.lineWidth = 1 + r() * 3; k.beginPath(); k.moveTo(r() * c.width, r() * c.height); k.lineTo(r() * c.width, r() * c.height); k.stroke() }</script>"""
PAGES = {
    "white": ("body{margin:0;background:#fff;color:#111}", ""),
    "dark": ("body{margin:0;background:#0d0d0f;color:#eee}", ""),
    "busy": ("body{margin:0;background:#222;color:#fff}canvas{position:fixed;inset:0}form{position:relative;background:#000a;padding:16px}", BUSY),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.strip("/").split("?")[0]
        style, extra = PAGES.get(name, PAGES["white"])
        body = (f"<!doctype html><title>Sign in</title><style>{style}form{{display:grid;gap:10px;width:280px;margin:60px auto;font:15px system-ui}}"
                f"input{{display:block;width:100%;padding:8px;font:inherit}}</style>{extra}{FORM}").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class Server6(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6


OTHER = "[::1]" if MAC else "127.0.0.2"  # a third site: macOS has no 127.0.0.2
SERVERS = [http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler), Server6(("::1", 0), Handler) if MAC else http.server.ThreadingHTTPServer(("127.0.0.2", 0), Handler)]
for s in SERVERS:
    threading.Thread(target=s.serve_forever, daemon=True).start()
# Maya as in the launch video: her role's look (shipped heads, a file for each size) and Keep going, the default, so a
# new site doesn't stop for an OK (the QA crew is on Ask more for the suites that test asking).
MAYA = [dict(c, Crew="research", Autonomy="keepgoing") if c["Id"] == "maya" else c for c in CREW]
# Three hosts, so no page counts as a site already signed in to.
URLS = {"white": f"http://127.0.0.1:{SERVERS[0].server_port}/white", "dark": f"http://localhost:{SERVERS[0].server_port}/dark",
        "busy": f"http://{OTHER}:{SERVERS[1].server_port}/busy"}

# The fake AI app: "OPEN: <url>" opens the page and reads it (a sign-in page pauses the run), then reads it again until
# it isn't a sign-in page any more (Still holds each read up to 40 s while the tab is the user's).
FAKE = textwrap.dedent(r'''
    import json, subprocess, sys, time
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    last = sys.stdin.read().strip().splitlines()[-1]
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    server = json.load(open(args[args.index("--mcp") + 1]))["mcpServers"]["still"]
    still = subprocess.Popen([server["command"]] + server["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = 0
    def request(method, params):
        global n
        n += 1
        still.stdin.write((json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params}) + "\n").encode()); still.stdin.flush()
        for line in still.stdout:
            try: m = json.loads(line)
            except ValueError: continue
            if m.get("id") == n: return m
    def call(i, name, arguments):
        say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tu%d" % i, "name": "mcp__still__" + name, "input": arguments}]}})
        r = request("tools/call", {"name": name, "arguments": arguments})["result"]
        say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu%d" % i, "is_error": bool(r.get("isError"))}]}})
        return r["content"][0].get("text", "")
    request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fake", "version": "1"}})
    still.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); still.stdin.flush()
    if last.startswith("OPEN: "):
        tab = json.loads(call(0, "open_tab", {"url": last[6:].strip(), "background": False})).get("tabId", "")  # in the main strip, as in the report: Open chat shows
        for i in range(1, 8):
            if "This is a sign-in page" not in call(i, "read_page", {"tabId": tab}) and i > 1: break
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay, done."}]}})
    still.stdin.close()
''')

# The pill, measured: its colors and their tokens, the buttons, the type, the center lines, the padding at its ends, the
# face's file, and whether its box sits on whole device pixels.
LOOK = r"""(() => { const pill = document.querySelector('.page-control'); if (!pill) return null
 const cs = e => getComputedStyle(e), box = e => e.getBoundingClientRect(), dpr = devicePixelRatio
 const token = n => { const k = document.createElement('i'); k.style.color = `var(${n})`; pill.append(k); const c = cs(k).color; k.remove(); return c }
 const q = s => pill.querySelector(s), take = q('.page-take'), chat = q('.page-chat'), stop = q('.page-stop'), more = q('.page-more'), head = q('.page-head')
 const face = head && head.querySelector('img'), b = q('.page-control-text b'), small = q('.page-control-text small'), p = box(pill)
 const mid = e => e && (r => r.top + r.height / 2)(box(e))
 const ends = [...pill.children].filter(e => box(e).width), first = ends[0], last = ends[ends.length - 1]
 return { dpr, rect: [p.left, p.top, p.width, p.height], state: pill.dataset.state, text: pill.innerText.replace(/\s+/g, ' ').trim(),
  bg: cs(pill).backgroundColor, popover: token('--popover'), border: cs(pill).borderTopColor, line: token('--border'), shadow: cs(pill).boxShadow,
  take: take && { bg: cs(take).backgroundColor, ink: cs(take).color, pop: token('--pop'), inkToken: token('--ink'), label: take.innerText.trim() },
  chat: chat && { bg: cs(chat).backgroundColor, label: chat.innerText.trim() },
  stop: stop && { bg: cs(stop).backgroundColor, color: cs(stop).color, red: token('--destructive'), title: stop.title, svg: !!stop.querySelector('svg'), bitmap: !!stop.querySelector('img, canvas') },
  type: b && { weight: cs(b).fontWeight, sub: cs(small).color, muted: token('--muted-foreground') },
  centers: { pill: mid(pill), more: mid(more), head: mid(head), text: b && (box(b).top + box(small).bottom) / 2 },
  pad: first && [box(first).left - p.left, p.right - box(last).right],
  face: face && { file: (face.currentSrc || face.src).split('/').pop(), natural: face.naturalWidth, shown: +(box(face).width * dpr).toFixed(2) },
  moved: (() => { const m = []; for (let e = pill; e && e !== document.body; e = e.parentElement) { const s = cs(e); if (s.transform !== 'none' || s.translate !== 'none' || s.scale !== 'none') m.push(e.className) } return m })() } })()"""


def check(ok, name):
    if ok:
        PASSES[0] += 1
    else:
        FAILS.append(f"[{GROUP[0]}] {name}")
    print(("PASS " if ok else "FAIL ") + f"[{GROUP[0]}] {name}", flush=True)


def look(p):
    raw = js(p, "JSON.stringify(" + LOOK + ")")
    return json.loads(raw) if raw and raw != "null" else None


def near(a, b, d=.75):
    return a is not None and b is not None and abs(a - b) <= d


def hover(p, selector):
    at = js(p, f"(r => r && [r.x + r.width / 2, r.y + r.height / 2])(document.querySelector({json.dumps(selector)})?.getBoundingClientRect())")
    if at:
        rpc(p, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": at[0], "y": at[1]})
        time.sleep(.35)
    return at


if not MAC:
    import ctypes.wintypes as wt
    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    for f, res, args in ((user32.GetDC, ctypes.c_void_p, [ctypes.c_void_p]), (user32.ReleaseDC, ctypes.c_int, [ctypes.c_void_p, ctypes.c_void_p]),
                         (gdi32.CreateCompatibleDC, ctypes.c_void_p, [ctypes.c_void_p]), (gdi32.CreateCompatibleBitmap, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
                         (gdi32.SelectObject, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_void_p]), (gdi32.DeleteObject, ctypes.c_int, [ctypes.c_void_p]),
                         (gdi32.DeleteDC, ctypes.c_int, [ctypes.c_void_p]), (user32.PrintWindow, ctypes.c_int, [wt.HWND, ctypes.c_void_p, ctypes.c_uint]),
                         (gdi32.GetDIBits, ctypes.c_int, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]),
                         (user32.ChildWindowFromPointEx, wt.HWND, [wt.HWND, wt.POINT, ctypes.c_uint]), (user32.WindowFromPoint, wt.HWND, [wt.POINT]),
                         (user32.GetWindowLongPtrW, ctypes.c_ssize_t, [wt.HWND, ctypes.c_int]), (user32.GetWindowRect, wt.BOOL, [wt.HWND, ctypes.c_void_p]),
                         (user32.ClientToScreen, wt.BOOL, [wt.HWND, ctypes.c_void_p]), (user32.IsWindowVisible, wt.BOOL, [wt.HWND]),
                         (user32.GetWindowThreadProcessId, wt.DWORD, [wt.HWND, ctypes.c_void_p])):
        f.restype, f.argtypes = res, args

    def main_window(pid):
        found = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def each(hwnd, _):
            owner, r = wt.DWORD(), wt.RECT()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd) and user32.GetWindowRect(hwnd, ctypes.byref(r)):
                found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
            return True
        user32.EnumWindows(each, 0)
        return max(found)[1]

    def window_picture(hwnd):
        """The window as Windows composes it, child windows and regions included, in physical pixels; and where its
        client area starts in it."""
        r, o = wt.RECT(), wt.POINT(0, 0)
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        user32.ClientToScreen(hwnd, ctypes.byref(o))
        w, h = r.right - r.left, r.bottom - r.top
        screen = user32.GetDC(None)
        dc, bmp = gdi32.CreateCompatibleDC(screen), gdi32.CreateCompatibleBitmap(screen, w, h)
        was = gdi32.SelectObject(dc, bmp)
        user32.PrintWindow(hwnd, dc, 2)  # PW_RENDERFULLCONTENT: what DirectComposition draws too
        header = (ctypes.c_int32 * 10)(40, w, -h, 1 | 32 << 16, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(dc, bmp, 0, h, buf, header, 0)
        gdi32.SelectObject(dc, was)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, screen)
        return Image.frombuffer("RGBX", (w, h), buf, "raw", "BGRX", 0, 1).convert("RGB"), (o.x - r.left, o.y - r.top)

    def shell_origin(top, rect, dpr):
        """Where the shell's CSS (0, 0) is, in the window picture and on screen: its web view sits a few pixels into the
        client area (the window's frame). Found as the window under the pill: the page's hole lets the point through to
        the shell's view, and the rim takes no hits."""
        r, c, o = wt.RECT(), wt.POINT(0, 0), wt.POINT(0, 0)
        user32.GetWindowRect(top, ctypes.byref(r))
        user32.ClientToScreen(top, ctypes.byref(c))
        x, y, w, h = [v * dpr for v in rect]
        user32.ClientToScreen(user32.WindowFromPoint(wt.POINT(int(c.x + x + w / 2), int(c.y + y + h / 2))), ctypes.byref(o))
        return (o.x - r.left, o.y - r.top), (o.x, o.y)

    def lum(px):
        return .2126 * px[0] + .7152 * px[1] + .0722 * px[2]

    def smooth_ends(img, rect, off, dpr, fill):
        """Of the rows through the pill's round ends, how many cross from the page to the pill through a pixel only partly
        covered (25-75% of the way from the page just outside to the pill's fill): about half or more on a smoothed edge,
        next to none on a stair-stepped one."""
        x, y, w, h = [v * dpr for v in rect]
        x, y, r = x + off[0], y + off[1], h / 2
        soft = rows = 0
        for row in range(int(y + 2), int(y + h - 2)):
            dy = abs(row + .5 - (y + r))
            if dy < r * .3 or dy >= r:
                continue
            dx = r - (r * r - dy * dy) ** .5  # how far in from the box's side the curve is on this row
            for edge, step in ((x + dx, 1), (x + w - dx, -1)):
                start = int(edge) - step * 4
                line = [img.getpixel((start + step * k, row)) for k in range(9)]
                span = [f - o for o, f in zip(line[0], fill)]
                n2 = sum(s * s for s in span)
                if n2 < 80 ** 2:
                    continue
                rows += 1
                soft += any(.25 < sum((c - o) * s for c, o, s in zip(px, line[0], span)) / n2 < .75 for px in line)
        return soft, rows

    def shadow_under(img, rect, off, dpr):
        """Brightness 3, 6 and 12 px under the pill's middle, then the page's own 30 px above it (past the shadow)."""
        x, y, w, h = [v * dpr for v in rect]
        cx, top, bottom = int(x + off[0] + w / 2), y + off[1], y + off[1] + h
        return [round(lum(img.getpixel((cx, int(bottom + d * dpr))))) for d in (3, 6, 12)] + [round(lum(img.getpixel((cx, int(top - 30 * dpr)))))]


def pass_at(scale):
    run = ROOT / "artifacts" / ("pill-" + uuid.uuid4().hex[:8])
    profile, bin_ = run / "profile", run / "bin"
    (profile / "agents").mkdir(parents=True)
    bin_.mkdir(parents=True)
    (bin_ / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(bin_ / "fakeagent", bin_ / "fake_agent.py")
    (profile / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(bin_ / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "output": "stream-json"}))
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Preferences": {"Companions": MAYA, "AgentsEnabled": True, "AiHarness": "fake",
        "Permissions": [{"Site": "", "Action": "interact", "Companion": "", "Mode": "always"}]}, "Tabs": [{"Id": "home", "Title": "Home", "Url": "about:blank"}], "ActiveId": "home"}))
    env = dict(os.environ)
    if scale != 1 and not MAC:
        env["STILL_QA_BROWSER_ARGS"] = f" --force-device-scale-factor={scale}"
    p = launch(EXE, profile, env)
    try:
        until(lambda: js(p, "!!document.body.innerText.length"), 20)
        send(p, "aiToggle")
        until(lambda: js(p, "!!document.querySelector('.ai-sidebar [aria-label=Message]')"), 10)
        for name, url in URLS.items():
            GROUP[0] = f"{scale * 100:.0f}% {name}"
            send(p, "aiSend", text="OPEN: " + url)
            paused = until(lambda: (lambda l: l and l["state"] == "signin" and l)(look(p)), 25)
            check(paused, "The run pauses on the sign-in page and the pill asks to sign in: " + ((paused or {}).get("text", "")))
            if not paused:
                continue
            for theme in ("Dark", "Light"):
                GROUP[0] = f"{scale * 100:.0f}% {name} {theme}"
                send(p, "preference", key="theme", value=theme)
                until(lambda: js(p, "document.documentElement.classList.contains('dark')") == (theme == "Dark"), 5)
                time.sleep(.8)
                one(p, scale, name, theme)
            js(p, "document.querySelector('.page-take')?.click()")  # hand it back: the held read returns and the run ends
            check(until(lambda: not js(p, "!!document.querySelector('.page-control')"), 20), "Hand back lets the run finish and the pill goes")
    finally:
        try:
            rpc(p, "quit")
        except Exception:
            pass
        try:
            p.wait(15)
        except Exception:
            p.kill()


def one(p, scale, name, theme):
    l = look(p)
    if not l:
        check(False, "The pill is up")
        return
    if name == "white":  # the look doesn't depend on the page: checked on the first one, in each theme
        check(l["bg"] == l["popover"] and l["border"] == l["line"], f"Still's own surface and border: {l['bg']} (--popover {l['popover']}), {l['border']} (--border {l['line']})")
        check("rgba(0, 0, 0" in l["shadow"] and "px" in l["shadow"], f"A soft shadow: {l['shadow']}")
        t = l["take"] or {}
        check(t.get("label") == "Hand back" and t.get("bg") == t.get("pop") and t.get("ink") == t.get("inkToken"), f"Hand back is filled in the accent: {t}")
        c = l["chat"] or {}
        check(c.get("label") == "Open chat" and c.get("bg") in ("rgba(0, 0, 0, 0)", "transparent"), f"Open chat is quiet (no fill): {c}")
        s = l["stop"] or {}
        check(s.get("svg") and not s.get("bitmap") and s.get("bg") in ("rgba(0, 0, 0, 0)", "transparent") and s.get("color") != s.get("red") and s.get("title") == "Stop",
              f"Stop: an SVG square, no fill, muted red, tooltip Stop: {s}")
        hover(p, ".page-stop")
        hot = (look(p) or {}).get("stop") or {}
        check(hot.get("color") == hot.get("red"), f"and full red on hover: {hot.get('color')} ({hot.get('red')})")
        rpc(p, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": 5, "y": 5})
        ty = l["type"] or {}
        check(ty.get("weight") == "400" and ty.get("sub") == ty.get("muted"), f"Title in normal weight, subtitle muted: {ty}")
        ce = l["centers"]
        check(all(near(ce[k], ce["pill"]) for k in ("more", "head", "text")), f"Chevron, face and text on the pill's center line: {ce}")
        check(l["pad"] and near(l["pad"][0], l["pad"][1], .5), f"The same padding at both ends: {l['pad']}")
        f = l["face"] or {}
        check(f and f["shown"] / 1.1 - .5 <= f["natural"] <= f["shown"] * 1.1 + .5, f"The face is a file drawn for its size, within 10%: {f.get('file')} ({f.get('natural')} px shown at {f.get('shown')})")
        check(not l["moved"], f"Nothing moves the pill by a transform: {l['moved']}")
        # A subtitle with too little room: an ellipsis, and the whole line as its tooltip.
        js(p, "document.querySelector('.page-control-text').style.maxWidth = '120px'")
        time.sleep(.2)
        hover(p, ".page-control-text small")
        cut = json.loads(js(p, "JSON.stringify((s => [s.scrollWidth > s.clientWidth, getComputedStyle(s).textOverflow, s.title, s.innerText])(document.querySelector('.page-control-text small')))"))
        check(cut[0] and cut[1] == "ellipsis" and cut[2] == cut[3], f"A long subtitle ends in an ellipsis with the whole line as its tooltip: {cut}")
        js(p, "document.querySelector('.page-control-text').style.maxWidth = ''")
        rpc(p, "shellCdp", method="Input.dispatchMouseEvent", parameters={"type": "mouseMoved", "x": 5, "y": 5})
        time.sleep(.3)
        l = look(p) or l
    tag = f"{'mac' if MAC else 'win'}-{scale * 100:.0f}-{theme.lower()}-{name}"
    if MAC:
        if SHOTS:
            rpc(p, "capture", name=f"pill-{tag}.png")
        return
    top = main_window(p.pid)
    img, _ = window_picture(top)
    dpr, rect = l["dpr"], l["rect"]
    off, origin = shell_origin(top, rect, dpr)
    x, y, w, h = [v * dpr for v in rect]
    if name in ("white", "dark"):  # where the page and the pill differ enough to see the edge
        soft, rows = smooth_ends(img, rect, off, dpr, tuple(int(float(v)) for v in l["bg"][l["bg"].index("(") + 1:-1].split(",")[:3]))
        if rows:
            check(rows >= 8 and soft >= rows * .35, f"Round the pill's ends the page meets it through partly covered pixels on {soft} of {rows} rows")
    if name == "white":
        under = shadow_under(img, rect, off, dpr)
        check(under[0] <= under[1] <= under[2] and under[0] < under[3] - 3 and under[3] >= 250,
              f"A shadow under the pill on the white page, fading (brightness 3, 6, 12 px below, then the page above it): {under}")
        below = wt.POINT(int(origin[0] + x + w / 2), int(origin[1] + y + h + 6 * dpr))
        hit = user32.WindowFromPoint(below)
        layered = bool(user32.GetWindowLongPtrW(hit, -20) & 0x80000)  # GWL_EXSTYLE, WS_EX_LAYERED
        check(hit and not layered, "The shadow over the page takes no clicks: the page gets them")
    if SHOTS:
        pad = 40 * dpr
        box = (int(off[0] + x - pad), int(off[1] + y - pad), int(off[0] + x + w + pad), int(off[1] + y + h + pad))
        crop = img.crop(box)
        crop.save(SHOTS / f"pill-{tag}.png")
        end = img.crop((int(off[0] + x - 8 * dpr), int(off[1] + y - 8 * dpr), int(off[0] + x + h + 16 * dpr), int(off[1] + y + h + 14 * dpr)))
        end.resize((end.width * 4, end.height * 4), Image.NEAREST).save(SHOTS / f"pill-{tag}-x4.png")


for s in SCALES:
    pass_at(s)
print(f"\n{PASSES[0]} passed, {len(FAILS)} failed")
for f in FAILS:
    print("  FAIL", f)
sys.exit(1 if FAILS else 0)
