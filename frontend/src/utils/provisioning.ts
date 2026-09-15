/**
 * Remembering whether a device already has an administrator.
 *
 * Without this the app cannot tell, on the very first paint, whether it is
 * about to show the dashboard or the first-run wizard — so it shows the full
 * navigation shell to everyone and swaps it for the wizard once /api/init
 * answers. On an unprovisioned device that reads as the real UI flashing up
 * and vanishing, which is the worst possible first impression and is longer,
 * not shorter, on a BeagleBone than on a developer's machine.
 *
 * The hint is a convenience, never a decision: what actually gates the wizard
 * is `needs_onboarding` from /api/init, and a stale or absent hint only costs
 * a different loading screen.
 */

const HINT_KEY = 'boneio-provisioned';

/** The subset of Storage used here, so tests can pass a plain fake. */
export interface HintStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/**
 * Scope the key to one device.
 *
 * Behind HA ingress several controllers share a browser origin, so an
 * unscoped key would let the first device answer for all of them. Mirrors the
 * suffix scheme in ThemeChanger.
 *
 * @param basePath - `window.__BONEIO_BASE_PATH__`, absent on direct access.
 */
export function provisioningHintKey(basePath: string | undefined): string {
  const match = basePath?.match(/\/(proxy\/\d+)\/?$/);
  return match ? `${HINT_KEY}-${match[1].replace('/', '-')}` : HINT_KEY;
}

/**
 * Whether this browser has seen this device provisioned before.
 *
 * False whenever we do not know — an unread key, a browser that refuses
 * storage — so an uncertain first paint errs towards the quiet loading screen
 * rather than flashing a shell the visitor may not be entitled to see yet.
 */
export function readProvisioningHint(
  storage: HintStorage | undefined,
  basePath: string | undefined,
): boolean {
  try {
    return storage?.getItem(provisioningHintKey(basePath)) === '1';
  } catch {
    // Private mode and "block site data" both throw rather than return null.
    return false;
  }
}

/**
 * Record what /api/init just reported.
 *
 * @param needsOnboarding - The freshly fetched flag.
 */
export function writeProvisioningHint(
  storage: HintStorage | undefined,
  basePath: string | undefined,
  needsOnboarding: boolean,
): void {
  try {
    storage?.setItem(provisioningHintKey(basePath), needsOnboarding ? '0' : '1');
  } catch {
    // Nothing to do: the hint is optional by design.
  }
}
