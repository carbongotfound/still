"""Closing tabs never leaves another tab's toolbar or page on screen. Rounds of 10 tabs: 5 pages, a chat tab and 2 of its
companion's background tabs (a fake companion opens them and keeps working in one, reading it and taking screenshots),
then 2 more pages opened after them, and a split. Tabs close in random orders until one is left: the active tab, another one, a half of a split, the
companion's tab, its chat, several fast; between closes a tab is picked, the chat's page opened, a split made or a page opened.
After every close the strip's selected tab, the toolbar, the address bar and every page on screen belong to the active
tab, a companion's background tab is never on screen unless the chat in view shows it beside it, and a chat a close
lands on shows without its companion's page.

Run: python tests/desktop/tabclose_stress.py artifacts/Still-QA/Still.exe [closes] [seed]
Out: artifacts/tabclose-stress-*/result.json
"""
import http.server
import json
from pathlib import Path
import random
import sys
import textwrap
import threading
import time
from urllib.parse import urlparse
import uuid

sys.path.insert(0, str(Path(__file__).parent))
from qa import CREW, ROOT, js, launch, launcher, rpc, send, until  # noqa: E402

EXE = Path(sys.argv[1]).resolve()
CLOSES = int(sys.argv[2]) if len(sys.argv) > 2 else 200
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else random.randrange(1 << 30)
RUN = ROOT / "artifacts" / ("tabclose-stress-" + uuid.uuid4().hex[:8])
FAKE = textwrap.dedent(r'''
    import json, os, re, subprocess, sys, time
    here = os.path.dirname(os.path.abspath(__file__))
    args = sys.argv[1:]
    if args[:1] == ["status"]: print("signed in"); sys.exit(0)
    prompt = sys.stdin.read()
    def say(e): print(json.dumps(e), flush=True)
    say({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()})
    work = re.search(r"WORK(\d+) (\S+)", prompt[-1500:])
    if work:
        # Two background tabs of the chat, then steps in the second until the time is up: a read, and every third a screenshot.
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
        def step(i, tool, targs):
            say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t%d" % i, "name": "mcp__still__" + tool, "input": targs}]}})
            call("tools/call", {"name": tool, "arguments": targs})
            say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t%d" % i}]}})
        url = work.group(2)
        step(0, "open_tab", {"url": url + "bg1", "background": True})
        step(1, "open_tab", {"url": url + "bg2", "background": True})
        end, i = time.time() + int(work.group(1)), 2
        while time.time() < end:
            step(i, "screenshot" if i % 3 == 0 else "read_page", {})
            i += 1
            time.sleep(.3)
        still.stdin.close()
    say({"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}})
''')
# What the interface shows: the strip's selected rows, the toolbar and its address, the address on the page bar beside a chat, split rows.
DOM = """(() => { const q = s => document.querySelector(s), ids = s => [...document.querySelectorAll(s)].map(r => r.getAttribute('data-tab-id'))
 return { sel: ids('.tab-row.is-selected'), bar: !!q('.window-bar'), addr: q('.window-bar .address-input')?.value ?? null,
  nav: q('.page-nav .page-nav-url')?.title ?? null, splitRows: ids('.tab-row.is-split').sort() } })()"""
FAILS, LATE, COUNT = [], [], {"closes": 0, "checks": 0}


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"<!doctype html><title>Page {self.path}</title><p>{self.path}</p>".encode()
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def look(p):
    """The state once it stops changing (up to 5 s): native tabs and views, and the interface."""
    last, seen = None, None
    end = time.monotonic() + 5
    while time.monotonic() < end:
        st, tb, dom = rpc(p), rpc(p, "tabs"), js(p, DOM)
        win = next((w for w in tb["windows"] if w.get("active") == st.get("activeId")), tb["windows"][0])
        seen = (st, tb, dom, {t["Id"] for t in win["tabs"] if t.get("visible")})
        key = json.dumps([st.get("activeId"), st.get("panel"), [(t["Id"], t["ChatId"], t["InChat"], t["Url"]) for t in st["tabs"]], sorted(seen[3]), tb["split"], dom], sort_keys=True, default=str)
        if key == last:
            break
        last = key
        time.sleep(.3)
    return seen


def verify(p, what, landed=False):
    """landed: a close took the active tab away, so Still picked the tab you're on now. A check that fails is looked at
    again for up to 5 s: an interface that catches up late is recorded in LATE (with how long), one that doesn't fails."""
    COUNT["checks"] += 1
    start, first = time.monotonic(), None
    while True:
        st, tb, dom, vis = look(p)
        bad = problems(st, tb, dom, vis, landed)
        if not bad or time.monotonic() - start > 5:
            break
        first = first or bad
        time.sleep(.3)
    if bad:
        FAILS.append({"after": what, "active": (st.get("activeId")), "problems": bad})
        print("FAIL after", what, "->", "; ".join(bad), flush=True)
    elif first:
        LATE.append({"after": what, "seconds": round(time.monotonic() - start, 1), "first": first})
        print(f"LATE after {what}: right after {time.monotonic() - start:.1f} s; first look: {'; '.join(first)}", flush=True)
    return st, tb


def problems(st, tb, dom, vis, landed):
    tabs = {t["Id"]: t for t in st["tabs"]}
    aid = st.get("activeId")
    a = tabs.get(aid) or {}
    split = tb.get("split") or {}
    partner = split.get("partner")
    bad = []
    if st.get("panel"):
        bad.append(f"a panel is open ({st['panel']})")
    if dom["sel"] != [aid]:
        bad.append(f"the strip selects {dom['sel']}, the active tab is {aid}")
    if a.get("InChat"):
        bad.append("the active tab is a companion's background tab")
    if not a.get("ChatId"):  # a page (or the home page): its own toolbar and address, its page, and its split partner
        want = ({aid} if a.get("Url") else set()) | ({partner} if partner else set())
        if not dom["bar"] or dom["nav"] is not None:
            bad.append(f"no toolbar of its own (toolbar {dom['bar']}, chat page bar {dom['nav']!r})")
        if a.get("Url") and urlparse(a["Url"]).path not in (dom["addr"] or ""):
            bad.append(f"the address bar shows {dom['addr']!r}, not {a['Url']}")
        if partner and (tabs.get(partner, {}).get("InChat") or tabs.get(partner, {}).get("ChatId") or {aid, partner} != {split.get("left"), split.get("right")}):
            bad.append(f"its split partner is {partner} ({tabs.get(partner)})")
        if dom["splitRows"] != (sorted([split["left"], split["right"]]) if partner else []):
            bad.append(f"split rows {dom['splitRows']}, split {split}")
    elif dom["nav"] is not None:  # a chat with its companion's page beside it: that page alone, its bar naming it
        if landed:
            bad.append(f"a close landed on the chat and opened its companion's page beside it ({dom['nav']})")
        page = next((t for t in st["tabs"] if t["Url"] == dom["nav"] and (t["InChat"] or t["RunChat"]) == a["ChatId"]), None)
        want = {page["Id"]} if page else set()
        if not page or dom["bar"]:
            bad.append(f"the chat's page bar shows {dom['nav']!r} (toolbar {dom['bar']})")
    else:  # a chat on its own: nothing of a page on screen
        want = set()
        if not dom["bar"]:
            bad.append("a chat on its own has no toolbar")
    if vis != want:
        bad.append(f"on screen {sorted(vis)}, should be {sorted(want)} ({[(tabs.get(i, {}).get('Url'), tabs.get(i, {}).get('InChat')) for i in vis]})")
    return bad


def round_(n, rng, base, bin_):
    profile = RUN / f"round{n}"
    (profile / "agents").mkdir(parents=True)
    (profile / "ai").mkdir(parents=True)
    (profile / "agents" / "fake.json").write_text(json.dumps({"id": "fake", "name": "Fake agent", "enabled": True, "command": str(bin_ / "fakeagent"),
        "detect": ["status"], "expect": "signed in", "run": ["run", "--mcp", "{mcpConfig}"], "resume": ["--resume", "{session}"], "output": "stream-json"}))
    (profile / "ai" / "chats.json").write_text(json.dumps([{"Id": "work", "Title": "Launch prep", "Harness": "fake", "Companion": "maya", "Updated": "2026-11-01T10:00:00Z", "Messages": []}]))
    pages = [{"Id": f"p{i}", "Title": f"Page /p{i}", "Url": f"{base}/p{i}"} for i in range(1, 6)]
    (profile / "state.json").write_text(json.dumps({"UiVersion": 6, "Welcome": False, "Tabs": pages, "ActiveId": "p1",
        "Preferences": {"Companions": [{**c, "Autonomy": "keep"} for c in CREW], "AgentsEnabled": True, "AiHarness": "fake", "Width": 1400, "Height": 900}}))
    p = launch(EXE, profile)
    try:
        until(lambda: (js(p, "document.querySelectorAll('.tab-row').length") or 0) >= 5, 20)
        send(p, "chatOpen", id="work", newTab=True)
        until(lambda: (lambda st: any(t["Id"] == st["activeId"] and t["ChatId"] for t in st["tabs"]))(rpc(p)), 10)
        send(p, "aiSend", text=f"WORK90 {base}/", companion="maya")
        bg = until(lambda: len([t for t in rpc(p)["tabs"] if t["InChat"] == "work"]) == 2, 30)
        if not bg:
            FAILS.append({"after": f"round {n} setup", "problems": ["the companion's 2 background tabs didn't open"]})
            print(f"FAIL round {n} setup: the companion's 2 background tabs didn't open", flush=True)
            return
        verify(p, f"round {n}: the companion opened its 2 background tabs while its chat was in view")
        for i in (6, 7):  # yours, opened after its tabs: further along the list than the strip shows
            send(p, "new", url=f"{base}/p{i}"); time.sleep(.5)
        until(lambda: len(rpc(p)["tabs"]) == 10, 10)
        send(p, "select", id="p3"); time.sleep(.4)
        send(p, "split", id=next(t["Id"] for t in rpc(p)["tabs"] if t["Url"].endswith("/p6")), side="right")
        verify(p, f"round {n}: split p3|p6")
        while COUNT["closes"] < CLOSES:
            st = rpc(p)
            strip = [t for t in st["tabs"] if not t["InChat"]]
            if len(strip) <= 1:
                break
            aid = st["activeId"]
            if rng.random() < .4:  # move around first: another tab, the chat's page, or a new split
                pick = rng.random()
                if pick < .1:
                    send(p, "new", url=f"{base}/n{COUNT['closes']}")
                elif pick < .5:
                    send(p, "select", id=rng.choice(strip)["Id"])
                elif pick < .75 and any(t["ChatId"] for t in strip):
                    send(p, "select", id=next(t["Id"] for t in strip if t["ChatId"])); time.sleep(.3); send(p, "chatPage", on=True)
                else:
                    plain = [t["Id"] for t in strip if t["Url"] and not t["ChatId"]]
                    if len(plain) >= 2:
                        left, right = rng.sample(plain, 2)
                        send(p, "select", id=left); time.sleep(.3); send(p, "split", id=right, side="right")
                time.sleep(.4)
                st = rpc(p); aid = st["activeId"]
                strip = [t for t in st["tabs"] if not t["InChat"]]
            split = rpc(p, "tabs")["split"]
            kinds = ["active", "other", "fast"] + (["split"] if split.get("partner") else []) + (["companion"] if any(t["InChat"] for t in st["tabs"]) or any(t["ChatId"] for t in strip) else [])
            kind = rng.choice(kinds)
            if kind == "active":
                ids = [aid]
            elif kind == "other":
                ids = [rng.choice([t["Id"] for t in strip if t["Id"] != aid] or [aid])]
            elif kind == "split":
                ids = [rng.choice([split["left"], split["right"]])]
            elif kind == "companion":  # the tab it works in, its other tab, or its chat (which takes its pages with it)
                ids = [rng.choice([t["Id"] for t in st["tabs"] if t["InChat"]] + [t["Id"] for t in strip if t["ChatId"]])]
            else:
                ids = rng.sample([t["Id"] for t in strip], min(3, len(strip) - 1))
            for i in ids:
                send(p, "closeTab", id=i)
            COUNT["closes"] += len(ids)
            verify(p, f"round {n}: closed {kind} {ids} ({COUNT['closes']} closes)", landed=aid in ids)
    finally:
        p.kill()


def main():
    rng = random.Random(SEED)
    print("seed", SEED, flush=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    bin_ = RUN / "bin"
    bin_.mkdir(parents=True)
    (bin_ / "fake_agent.py").write_text(FAKE, encoding="utf-8")
    launcher(bin_ / "fakeagent", bin_ / "fake_agent.py")
    n = 0
    while COUNT["closes"] < CLOSES and n < 60:
        n += 1
        round_(n, rng, f"http://127.0.0.1:{server.server_address[1]}", bin_)
    result = {"seed": SEED, "rounds": n, **COUNT, "failed": len(FAILS), "failures": FAILS[:50], "late": LATE}
    (RUN / "result.json").write_text(json.dumps(result, indent=1))
    print(f"{COUNT['closes']} closes in {n} rounds, {COUNT['checks']} checks, {len(FAILS)} failed, {len(LATE)} late (seed {SEED})")
    sys.exit(0 if not FAILS and COUNT["closes"] >= CLOSES else 1)


main()
