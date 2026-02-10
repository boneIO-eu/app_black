/**
 * Resolves the base path for API and WebSocket requests.
 *
 * Priority:
 * 1. VITE_API_URL env variable (development mode)
 * 2. window.__BONEIO_BASE_PATH__ (injected by reverse proxy, e.g. HA ingress addon)
 * 3. Empty string (direct access on device)
 */

declare global {
  interface Window {
    __BONEIO_BASE_PATH__?: string;
  }
}

export function getBasePath(): string {
  // Dev mode: explicit env variable takes priority
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) {
    return envUrl;
  }

  // Proxy mode: injected by nginx sub_filter
  if (typeof window !== 'undefined' && window.__BONEIO_BASE_PATH__) {
    return window.__BONEIO_BASE_PATH__;
  }

  // Direct access: empty base path (same origin)
  return '';
}
