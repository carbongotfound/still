import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { MascotSheet, MascotStage } from './Mascot'

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
