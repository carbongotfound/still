"""Check overflowing tab lists and new-tab controls using an isolated QA profile.

Run: python tests/desktop/tabs.py artifacts/Still-QA/Still.exe [--baseline]
"""
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'artifacts' / ('tabs-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)
RESULT = {'checks': []}
process = None

def rpc(op='state', **args):
    pipe = r'\\.\pipe\StillQa-' + str(process.pid)
    end = time.monotonic() + 30
    while not ctypes.windll.kernel32.WaitNamedPipeW(pipe, 500):
        if process.poll() is not None or time.monotonic() > end:
            raise RuntimeError('QA pipe unavailable')
        time.sleep(.05)
    with open(pipe, 'r+b', buffering=0) as stream:
        stream.write((json.dumps({'op': op, **args}) + '\n').encode())
        data = b''
        while not data.endswith(b'\n'):
            part = stream.read(65536)
            if not part: raise RuntimeError('QA pipe closed')
            data += part
    value = json.loads(data)
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
