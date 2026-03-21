import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'

import App from './App.tsx'

// Register service worker with periodic update check (every hour)
registerSW({ immediate: true, onRegisteredSW(_swUrl, r) {
  r && setInterval(async () => { await r.update() }, 60 * 60 * 1000)
}})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
      <App />
  </StrictMode>,
)
