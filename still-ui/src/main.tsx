import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { Mascot, MascotSheet, MascotStage, type MascotState } from './Mascot'
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
  const { state = 'idle', gesture = '', size = 320, looks = [{}] } = (e as CustomEvent<{ state?: MascotState; gesture?: string; size?: number; looks?: Partial<Look>[] }>).detail ?? {}
  root.render(<div className="mascot-reel">{looks.map((l, i) => <Mascot key={i} look={{ ...DEFAULT_LOOK, ...l }} state={state} size={size} gesture={gesture} gestureAt={gesture ? Date.now() : 0} />)}<MascotStage /></div>)
})
