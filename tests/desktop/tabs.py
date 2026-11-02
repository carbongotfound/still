"""Check overflowing tab lists and new-tab controls using an isolated QA profile, then the Still app tab: chats and the
home's pages open in place in the tab in view, with its own Back and Forward, and tabs only grow when asked to.

Run: python tests/desktop/tabs.py artifacts/Still-QA/Still.exe [--baseline]
"""
import http.server
import json
from pathlib import Path
import random
import subprocess
import sys
import threading
import time
import uuid
import qa  # the Windows pipe, or the Mac's socket
from mcp_client import Mcp, call_async

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'artifacts' / ('tabs-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)
RESULT = {'checks': []}
process = None

def rpc(op='state', **args):
    value = qa.rpc(process, op, **args)
    if isinstance(value, dict) and 'error' in value: raise RuntimeError(str(value))
    return value

def evaluate(script): return rpc('shellEval', script=script)
def shown_layout(): return evaluate("document.querySelector('.browser-sidebar')?'Modern':'Classic'")
def send(op, **args): evaluate('chrome.webview.postMessage(' + json.dumps({'op':op, **args}) + ')')
def wait(fn, seconds=20):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if fn(): return
        time.sleep(.05)
    raise AssertionError('Timed out')
def settled(fn, seconds=3):
    try: wait(fn, seconds)
    except AssertionError: pass
    return fn()
def check(ok, name):
    RESULT['checks'].append({'name':name, 'passed':bool(ok)})
    print(('PASS ' if ok else 'FAIL ') + name, flush=True)
    if not ok: raise AssertionError(name)

CONTROL = """(() => {
 const b=[...document.querySelectorAll('.browser-sidebar .sidebar-link')].find(e=>e.textContent.includes('New tab'))??document.querySelector('.top-tab-strip [aria-label="New tab"]');
 if(!b)return {visible:false};
 if(b.closest('.browser-sidebar')){if(!window.__reveal)return {visible:true};b.scrollIntoView({block:'nearest',behavior:'instant'})} // Modern: New tab scrolls with the list
 const r=b.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
 return {visible: x>=0&&y>=0&&x<innerWidth&&y<innerHeight&&b.contains(document.elementFromPoint(x,y)),x,y};
})()"""

SELECTED = """(() => {
 const e=document.querySelector('.is-selected');
 const v=e?.closest('.top-tab-list, [data-slot="scroll-area-viewport"]');
 if(!v)return false;
 const r=e.getBoundingClientRect(),p=v.getBoundingClientRect();
 return r.top>=p.top-1&&r.bottom<=p.bottom+1&&r.left>=p.left-1&&r.right<=p.right+1;
})()"""

INLINE = """(() => {
 const b=[...document.querySelectorAll('.browser-sidebar .sidebar-link')].find(e=>e.textContent.includes('New tab'))??document.querySelector('.top-tab-strip [aria-label="New tab"]');
 if(b?.closest('.browser-sidebar'))return true; // Modern: New tab sits at the top of the sidebar, not in the list
 const v=b?.closest('.top-tab-list, [data-slot="scroll-area-viewport"]');
 const last=[...v?.querySelectorAll('[data-tab-id]')??[]].at(-1);
 if(!v||!last)return false;
 const r=b.getBoundingClientRect(),p=last.getBoundingClientRect();
 const gap=v.matches('.top-tab-list')?r.left-p.right:r.top-p.bottom;
 return gap>=-1&&gap<=16; // the button sits 12px after the last tab; sub-pixel layout can round past it
})()"""

def wheel_to_new():
    for _ in range(30):
        if evaluate(CONTROL)['visible']: return
        point=evaluate("(()=>{const v=document.querySelector('.top-tab-list, [data-slot=\"scroll-area-viewport\"]'),r=v.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
        rpc('shellCdp',method='Input.dispatchMouseEvent',parameters={'type':'mouseWheel',**point,'deltaX':0,'deltaY':600})
        time.sleep(.1)
    raise AssertionError('Mouse wheel cannot reach inline New tab control')

def click_new():
    evaluate('window.__reveal=true'); control = evaluate(CONTROL); evaluate('window.__reveal=false')
    check(control['visible'], 'New tab control remains visible and receives pointer input')
    count = len(rpc()['tabs'])
    for kind in ['mousePressed','mouseReleased']:
        rpc('shellCdp',method='Input.dispatchMouseEvent',parameters={'type':kind,'x':control['x'],'y':control['y'],'button':'left','clickCount':1})
    wait(lambda: len(rpc()['tabs']) == count + 1)
    rpc('key',key='Escape',mods='None')
    wait(lambda: evaluate(SELECTED))

# The Still app tab. A stand-in AI app: answers at once, or stays busy for two minutes when asked to.
FAKE = r'''
import json, os, sys, time
if sys.argv[1:2] == ["status"]: print("signed in"); sys.exit(0)
prompt = sys.stdin.read()
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-%d" % time.time_ns()}), flush=True)
if "STAY-BUSY" in prompt:
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pid.txt"), "w").write(str(os.getpid()))
    time.sleep(120)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Okay."}]}}), flush=True)
'''
CHATS = ['chat1', 'chat2', 'chat3', 'chat4']
MISSED = []
PAGES = {'': '.home-compose', 'chats': 'section[aria-label="Chat History"]', 'companions': 'section[aria-label="Companions"]',
         'library': 'section[aria-label="Library"]', 'skills': 'section[aria-label="Skills & plugins"]'}

class Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>Site</title><p>A page."
        self.send_response(200); self.send_header('Content-Type', 'text/html'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass

def tabs_now(): return rpc()['tabs']
def active_tab(): s = rpc(); return next(t for t in s['tabs'] if t['Id'] == s['activeId'])
def spot_of(t): return 'chat:' + t['ChatId'] if t.get('ChatId') else 'home:' + (t.get('Home') or '')
def on_screen():
    """What the interface shows: a chat (by its first line) or a home page. Two at once is a mix-up."""
    return evaluate("(() => { const log = document.querySelector('.ai-log')?.innerText ?? '', seen = " + json.dumps(CHATS) + ".filter(c => log.includes('Words from ' + c + '.'))"
                    "; const pages = Object.entries(" + json.dumps(PAGES) + ").filter(([, s]) => document.querySelector(s)).map(([p]) => 'home:' + p)"
                    "; return seen.length || pages.length || !log ? [...seen.map(c => 'chat:' + c), ...pages] : ['chat:?'] })()")
def at(where, seconds=10):
    shows = [where] if where.startswith('home:') or where[5:] in CHATS else ['chat:?']  # a chat this test didn't write
    try: wait(lambda: spot_of(active_tab()) == where and on_screen() == shows, seconds)
    except AssertionError: return False
    return True
def click(selector, text=''):
    return evaluate("(() => { const e = [...document.querySelectorAll(" + json.dumps(selector) + ")].find(e => e.innerText.includes(" + json.dumps(text) + ")); e?.click(); return !!e })()")
def history_click(chat):
    """Chat History from wherever the app tab is (the chat sidebar, the browser sidebar or the home rail), then a chat in it."""
    went = click('.chat-side-nav button', 'Chat History') or click('.browser-sidebar .sidebar-link', 'Chat history') or click('.home-rail-item[aria-label="Chats"]')
    if not went or not at('home:chats'): MISSED.append(f'history from {spot_of(active_tab())} ({went}, {on_screen()})'); return False
    settled(lambda: click('.history-open', 'Chat ' + chat[-1]), 10)  # just after starting, the list may still be loading
    return at('chat:' + chat) or bool(MISSED.append(f'{chat} from history: {spot_of(active_tab())}, {on_screen()}'))

def app_tab():
    global process
    profile = RUN / 'app-profile'; (profile / 'ai').mkdir(parents=True); (profile / 'agents').mkdir()
    bin_ = RUN / 'bin'; bin_.mkdir(); (bin_ / 'fake_agent.py').write_text(FAKE, encoding='utf-8'); qa.launcher(bin_ / 'fakeagent', bin_ / 'fake_agent.py')
    (profile / 'agents' / 'fake.json').write_text(json.dumps({'id': 'fake', 'name': 'Fake agent', 'enabled': True, 'command': str(bin_ / 'fakeagent'),
        'detect': ['status'], 'expect': 'signed in', 'run': ['run'], 'output': 'stream-json'}))
    (profile / 'ai' / 'chats.json').write_text(json.dumps([{'Id': c, 'Title': 'Chat ' + c[-1], 'Harness': 'fake', 'Started': True, 'Companion': 'maya', 'Updated': f'2026-10-0{c[-1]}T10:00:00Z',
        'Messages': [{'Role': 'user', 'Text': f'Words from {c}.'}, {'Role': 'assistant', 'Text': 'Okay.'}]} for c in CHATS]))
    (profile / 'state.json').write_text(json.dumps({'UiVersion': 6, 'Welcome': False, 'ActiveId': 'app', 'Tabs': [{'Id': 'app', 'Title': 'New tab', 'Url': ''}],
        'Preferences': {'TabLayout': 'Classic', 'AiHarness': 'fake', 'AgentsEnabled': True, 'Companions': qa.CREW}}))
    site = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Site); threading.Thread(target=site.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{site.server_port}'
    process = qa.launch(Path(sys.argv[1]), profile)
    wait(lambda: at('home:'), 30)

    # Ten history clicks in each layout, from the browser sidebar, the chat sidebar and the home rail: no new tabs.
    for layout in ['Classic', 'Modern']:
        send('preference', key='tabLayout', value=layout); wait(lambda: shown_layout() == layout)
        count = len(tabs_now())
        done = sum(history_click(CHATS[i % 4]) for i in range(10))
        check(done == 10 and len(tabs_now()) == count, f'{layout}: ten history clicks open each chat in the same tab ({done}/10, {len(tabs_now())} tabs, was {count}, {MISSED})')

    # A scripted run of 50 steps: home pages, chats, Back and Forward. The tab and the screen always agree with the script.
    send('preference', key='tabLayout', value='Classic'); wait(lambda: shown_layout() == 'Classic')
    count, roll, mixups = len(tabs_now()), random.Random(210), []
    here, back, forward = spot_of(active_tab()), [], []
    for step in range(50):
        move = roll.choice(['home', 'chat', 'chat', 'back', 'forward'])
        if move == 'back' and back: forward.append(here); here = back.pop(); send('back')
        elif move == 'forward' and forward: back.append(here); here = forward.pop(); send('forward')
        else:
            to = 'home:' + roll.choice(list(PAGES)) if move in ('home', 'back', 'forward') else 'chat:' + roll.choice(CHATS)
            if to != here: back.append(here); forward.clear(); here = to
            if to.startswith('chat:'): send('chatOpen', id=to[5:])
            else: send('appHome', view=to[5:] or 'home')
        if not at(here): mixups.append(f'{step} {move}: wanted {here}, tab {spot_of(active_tab())}, screen {on_screen()}')
        if back and not active_tab()['appBack']: mixups.append(f'{step}: Back is off')  # the tab also remembers places from before the run
    check(not mixups and len(tabs_now()) == count, f'50 steps of navigation: no mix-ups, no new tabs ({mixups[:3]}, {len(tabs_now())} tabs)')

    # Open in new tab, by middle click and from the menu, still makes a tab; a chat open in a tab is focused, not shown twice.
    send('chatOpen', id='chat1'); at('chat:chat1'); send('appHome', view='chats'); at('home:chats')
    app = rpc()['activeId']
    evaluate("[...document.querySelectorAll('.history-open')].find(e => e.innerText.includes('Chat 2')).dispatchEvent(new MouseEvent('auxclick', { button: 1, bubbles: true }))")
    check(settled(lambda: len(tabs_now()) == count + 1) and any(t.get('ChatId') == 'chat2' for t in tabs_now()), 'A middle click opens a chat in a tab of its own')
    send('select', id=app); at('home:chats')
    evaluate("(() => { const e = [...document.querySelectorAll('.history-open')].find(e => e.innerText.includes('Chat 3')), r = e.getBoundingClientRect();"
             " e.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, clientX: r.x + 8, clientY: r.y + 8 })) })()")
    wait(lambda: click('[role=menuitem]', 'Open in new tab'))
    check(settled(lambda: len(tabs_now()) == count + 2) and any(t.get('ChatId') == 'chat3' for t in tabs_now()), "The menu's Open in new tab opens a chat in a tab of its own")
    send('select', id=app); at('home:chats')
    click('.history-open', 'Chat 2')
    own = next(t['Id'] for t in tabs_now() if t.get('ChatId') == 'chat2')
    check(settled(lambda: rpc()['activeId'] == own) and len(tabs_now()) == count + 2 and spot_of(next(t for t in tabs_now() if t['Id'] == app)) == 'home:chats',
          'Opening a chat that has its own tab goes to that tab, and the Still tab stays where it was')

    # From a web page, the home's pages and chats go to the Still tab used last, not a new one.
    send('select', id=app); at('home:chats')
    send('new', url=url + '/page'); wait(lambda: active_tab()['Url'].startswith(url))
    web, count = rpc()['activeId'], len(tabs_now())
    send('appHome', view='library')
    check(settled(lambda: rpc()['activeId'] == app and at('home:library', 3)) and len(tabs_now()) == count, 'From a web page, Library opens in the Still tab used last')
    send('select', id=web); wait(lambda: rpc()['activeId'] == web)
    send('chatOpen', id='chat4')
    check(settled(lambda: rpc()['activeId'] == app and at('chat:chat4', 3)) and len(tabs_now()) == count, 'From a web page, a chat opens in that Still tab too')
    send('back'); check(at('home:library'), 'Back in the Still tab goes to the page before')
    send('forward'); check(at('chat:chat4'), 'Forward goes to the chat again')

    # A running chat keeps running while the tab goes elsewhere and back.
    send('appHome', view='home'); at('home:')
    send('aiSend', text='STAY-BUSY for a while', home=True, companion='maya')
    pid = int(qa.until(lambda: (bin_ / 'pid.txt').exists() and (bin_ / 'pid.txt').read_text(), 30) or 0)
    running = active_tab().get('ChatId')
    check(pid and running, f'A chat started from the home runs in the Still tab ({running})')
    send('appHome', view='chats'); at('home:chats')
    click('.history-open', 'Chat 1'); at('chat:chat1')
    send('back'); at('home:chats'); send('back')
    check(at('chat:' + str(running)) and qa.alive(pid), 'Opening other chats in place and coming back leaves the running chat running')
    send('aiStop', id=running)

    # An AI app's tab stays in the AI group while the Still tab moves around.
    agent = Mcp(Path(sys.argv[1]).resolve(), 'Probe', profile)
    pending = call_async(agent, 'open_tab', url=url + '/agent')
    if qa.until(lambda: 'Probe' in evaluate('document.body.innerText'), 30): send('agentAnswer', allow=True)
    ok, text = pending.get(timeout=60)
    if not ok and 'Allow' in text: ok, text = agent.call('open_tab', url=url + '/agent')  # the user counted as away: it was told to call again
    opened = qa.until(lambda: next((t['Id'] for t in tabs_now() if t['Url'].endswith('/agent')), None), 20)
    send('select', id=app); count = len(tabs_now())
    moved = sum(history_click(c) for c in CHATS)
    grouped = evaluate(f"!!document.querySelector('[aria-label=\"AI tabs\"] [data-tab-id=\"{opened}\"]')")
    check(ok and opened and grouped and moved == 4 and len(tabs_now()) == count, f'An AI app\'s tab stays in the AI group after the Still tab moves ({ok} {text[:80]}, grouped {grouped})')
    agent.proc.kill()
    check(not rpc()['shellErrors'], 'No interface JavaScript errors in the Still tab run')
    rpc('quit'); process.wait(timeout=15); site.shutdown()

try:
    profile = RUN / 'profile'; profile.mkdir()
    count = 10 if '--baseline' in sys.argv else 3
    fixture = [{'Id':'tab-'+str(i),'Title':'Fixture '+str(i),'Url':''} for i in range(count)]
    (profile/'state.json').write_text(json.dumps({'UiVersion':6,'Welcome':False,'ActiveId':fixture[-1]['Id'],
        'Preferences':{'TabLayout':'Modern'},'Tabs':fixture}))
    process = subprocess.Popen([str(Path(sys.argv[1]).resolve()),'--qa','--profile',str(profile)])
    wait(lambda: (profile/'qa-pipe.txt').exists(),40)
    wait(lambda: evaluate(CONTROL)['visible'])
    # Small windows reproduce the user's roughly ten-tab threshold.
    evaluate("document.querySelector('.browser-shell').style.height='500px'")
    time.sleep(.3)
    if '--baseline' in sys.argv:
        RESULT['sidebar_control'] = evaluate(CONTROL)
        send('preference',key='tabLayout',value='Classic')
        wait(lambda: evaluate("!!document.querySelector('.top-tab-list')"))
        RESULT['top_control'] = evaluate(CONTROL)
        print(json.dumps(RESULT),flush=True)
    else:
        wait(lambda: evaluate(INLINE))
        check(evaluate(INLINE), 'Sidebar New tab sits immediately after three tabs')
        send('preference',key='tabLayout',value='Classic')
        wait(lambda: shown_layout()=='Classic' and evaluate(CONTROL)['visible'] and evaluate(INLINE))
        check(True, 'Top New tab sits immediately after three tabs')
        send('preference',key='tabLayout',value='Modern')
        wait(lambda: shown_layout()=='Modern' and evaluate(CONTROL)['visible'] and evaluate(INLINE))
        for _ in range(22): click_new()
        check(len(rpc()['tabs']) == 25, 'Sidebar creates 25 tabs through the visible button')
        check(settled(lambda: evaluate(INLINE)), 'Sidebar New tab stays inside the scrolling list after 25 tabs')  # tabs animate in
        evaluate("document.querySelector('.browser-shell').style.height='340px'")
        wait(lambda: evaluate(CONTROL)['visible'] and evaluate(SELECTED))
        check(True, 'Shrinking the window reveals the last tab and inline button')
        evaluate("document.querySelector('.browser-shell').style.height='500px'")
        send('preference',key='tabLayout',value='Classic')
        wait(lambda: evaluate("!!document.querySelector('.top-tab-list')"))
        wait(lambda: evaluate(SELECTED))
        for _ in range(5): click_new()
        check(len(rpc()['tabs']) == 30, 'Top layout creates 30 tabs through the visible button')
        check(settled(lambda: evaluate(INLINE)), 'Top New tab stays inside the scrolling list after 30 tabs')  # tabs animate in
        for layout in ['Modern','Classic']:
            send('preference',key='tabLayout',value=layout)
            wait(lambda: shown_layout() == layout)
            send('select',id='tab-0')
            wait(lambda: rpc()['activeId']=='tab-0' and evaluate(SELECTED))
            wheel_to_new()
            check(evaluate(CONTROL)['visible'] and evaluate(INLINE), layout + ' mouse wheel reaches the inline New tab button')
            identifier=rpc()['tabs'][-1]['Id']
            send('select',id=identifier)
            wait(lambda: rpc()['activeId']==identifier and evaluate(SELECTED) and evaluate(CONTROL)['visible'])
            check(True, layout + ' reveals first and last selected tabs')
        rpc('key',key='T',mods='Control')
        wait(lambda: len(rpc()['tabs']) == 31)
        rpc('key',key='Escape',mods='None')
        check(True, 'Ctrl T creates another tab past 30')
        check(not rpc()['shellErrors'], 'No interface JavaScript errors')
        rpc('quit'); process.wait(timeout=15)
        saved=json.loads((profile/'state.json').read_text(encoding='utf-8-sig'))
        check(len(saved['Tabs'])==31,'All 31 tabs save on exit')
        app_tab()
        RESULT['passed']=True
except Exception as error:
    RESULT['passed']=False; RESULT['error']=str(error)
    if process is not None and process.poll() is None:
        try:
            RESULT['state']=rpc()
            RESULT['geometry']=evaluate("(()=>{const s=document.querySelector('.is-selected'),v=s?.closest('.top-tab-list,[data-slot=\"scroll-area-viewport\"]');return {control:"+CONTROL+",selected:s?.getBoundingClientRect().toJSON(),viewport:v?.getBoundingClientRect().toJSON(),scrollTop:v?.scrollTop,scrollLeft:v?.scrollLeft}})()")
        except Exception: pass
    raise
finally:
    if process is not None and process.poll() is None:
        try: rpc('quit'); process.wait(timeout=10)
        except Exception: process.terminate()
    (RUN/'results.json').write_text(json.dumps(RESULT,indent=2))
    print('Results: '+str(RUN/'results.json'),flush=True)
