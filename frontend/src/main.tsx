import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import 'uplot/dist/uPlot.min.css'

import App from './App.tsx'

// Register service worker after initial load to avoid competing with
// critical /api/init and /api/config requests on BBB's single-threaded backend.
// The updateSW callback is stored globally so a UI toast can trigger the update
// when the user is ready, instead of force-reloading mid-session.
let _updateSW: ((reloadPage?: boolean) => Promise<void>) | null = null;

/** Trigger pending SW update. Call from a "New version available" toast. */
export function applySwUpdate() {
  _updateSW?.(true);
}

const sw = registerSW({
  onNeedRefresh() {
    // A new SW with fresh assets is available.
    // Instead of force-reloading, log and let the next natural navigation pick it up.
    // TODO: Replace with a toast/banner component calling applySwUpdate()
    console.info('[SW] New version available — will apply on next page load');
  },
  onRegisteredSW(_swUrl, r) {
    r && setInterval(async () => { await r.update() }, 60 * 60 * 1000)
  },
})
_updateSW = sw;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
      <App />
  </StrictMode>,
)
