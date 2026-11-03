import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { Mascot, MascotSheet, MascotStage, loadEngine, type MascotState, type Tier } from './Mascot'
import { DEFAULT_LOOK, type Look } from './look'

const root = createRoot(document.getElementById('root')!)
root.render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// The mascot gallery, every mascot in every state, for screenshots and their still pictures (tests/desktop/mascots.py).
document.addEventListener('still-mascot-sheet', () => {
  (window as unknown as { chrome: { webview: { postMessage(m: unknown): void } } }).chrome.webview.postMessage({ op: 'bounds', x: 0, y: 0, width: 1, height: 1, viewportWidth: innerWidth })
  root.render(<StrictMode><MascotSheet /><MascotStage /></StrictMode>)
})

// A row of big mascots in one state or gesture, posed frame by frame for the GIFs in docs/agentic/mascot (tests/desktop/mascots.py).
document.addEventListener('still-mascot-reel', e => {
  const { state = 'idle', gesture = '', size = 320, looks = [{}], follow = false, tier } = (e as CustomEvent<{ state?: MascotState; gesture?: string; size?: number; looks?: Partial<Look>[]; follow?: boolean; tier?: Tier }>).detail ?? {}
  root.render(<div className="mascot-reel">{looks.map((l, i) => <Mascot key={i} look={{ ...DEFAULT_LOOK, ...l }} state={state} size={size} tier={tier} follow={follow} gesture={gesture} gestureAt={gesture ? Date.now() : 0} />)}<MascotStage /></div>)
})

// Where each look's prop goes into its body or a nub, over every state and gesture (tests/desktop/mascots.py): one list
// per look in window.__clashes, empty when it never does.
document.addEventListener('still-mascot-clashes', async e => {
  const looks = (e as CustomEvent<Partial<Look>[]>).detail ?? [], w = window as unknown as { __clashes?: string[][] }
  delete w.__clashes
  const m = await loadEngine()
  for (;;) {
    const got = looks.map(l => m ? m.clashes({ ...DEFAULT_LOOK, ...l }) : [])
    if (!got.includes(null)) { w.__clashes = got as string[][]; return }
    await new Promise(r => setTimeout(r, 200)) // the props are loading
  }
})
