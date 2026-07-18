import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import 'uplot/dist/uPlot.min.css'

import App from './App.tsx'

// Register service worker with periodic update check (every hour).
// onNeedRefresh forces a page reload when a new SW with fresh assets is available,
// preventing stale cache from serving references to deleted hashed files.
registerSW({
  immediate: true,
  onNeedRefresh() {
    window.location.reload()
  },
  onRegisteredSW(_swUrl, r) {
    r && setInterval(async () => { await r.update() }, 60 * 60 * 1000)
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
      <App />
  </StrictMode>,
)
