/**
 * AppInitContext - Single /api/init call that replaces multiple startup requests.
 *
 * Previously the frontend fired 5+ separate API calls on page load:
 *   GET /api/version (x3), GET /api/auth/required, GET /api/pwa_name, GET /api/cloud/status (x2)
 *
 * Now all of this data comes from a single GET /api/init call and is distributed
 * via React context to all consumers (Navigation, BottomNav, useAuth, etc.).
 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import axios from '@/api/axios';
import { prefetchConfig } from '@/api/configCache';
import { writeProvisioningHint } from '@/utils/provisioning';
import {
  clearUpdateMark,
  noteReachability,
  panelState as computePanelState,
  readUpdateMark,
  updateArrived,
  writeUpdateMark,
  type PanelState,
} from '@/utils/updateGuard';

interface CloudStatus {
  enabled: boolean;
  domain?: string | null;
  cloud_config_active?: boolean;
  compose_writable?: boolean;
  last_error?: string | null;
}

interface AppInitData {
  version: string;
  name: string;
  /** Withheld from unauthenticated callers — see _may_see_serial in routes/system.py. */
  serial_no?: string;
  serial_override?: string | null;
  auth_required: boolean;
  /** True when the device has no administrator yet and the wizard must run. */
  needs_onboarding: boolean;
  /** True when config.yaml opts this device out of authentication entirely. */
  allow_anonymous?: boolean;
  /** Set when a pre-1.6 web.auth block was migrated into users.json on boot. */
  /** The device was set up under a pre-1.6 release, so it already has a
   *  configuration: the wizard drops the steps that assume a blank one. */
  configured_before?: boolean;
  pwa_name: string | null;
  pwa_default: string | null;
  pwa_max_length: number;
  cloud: CloudStatus;
  has_boneio: boolean;
  board_version: string | null;
  has_irrigation: boolean;
  /** Whether the config has any template (thermostat, alarm, gate, irrigation).
   *  Absent from firmware older than the panel. */
  has_templates?: boolean;
  /** Whether latitude and longitude are configured. */
  has_location: boolean;
}

interface AppInitContextType {
  /** All init data, null while loading */
  data: AppInitData | null;
  /** Whether the init fetch is still in progress */
  isLoading: boolean;
  /** Whether the API is available */
  isApiAvailable: boolean;
  /**
   * True once /api/init has reported an unprovisioned device, and stays true
   * for the life of the page.
   *
   * Latched on purpose. `data.needs_onboarding` flips to false the instant the
   * wizard creates the account, and this provider re-polls /api/init on a
   * timer, so a consumer gating on the raw flag would unmount the wizard
   * part-way through and strand the user. The wizard finishes by reloading the
   * page, which is what clears this.
   */
  needsOnboarding: boolean;
  /**
   * What the panel has to say before anything else: a stale build, an update
   * in progress, a failed one. See utils/updateGuard.ts.
   */
  panelState: PanelState;
  /** Go on despite `stale_panel`, or acknowledge `update_failed`. */
  dismissPanelState: () => void;
  /** Re-fetch init data (e.g. after visibility change) */
  refetch: () => Promise<void>;
}

const AppInitContext = createContext<AppInitContextType>({
  data: null,
  isLoading: true,
  isApiAvailable: true,
  needsOnboarding: false,
  panelState: 'ok',
  dismissPanelState: () => {},
  refetch: async () => {},
});

/**
 * Hook to access initialization data fetched from /api/init.
 */
export function useAppInit() {
  return useContext(AppInitContext);
}

/**
 * Decide whether the first-run wizard should be on screen.
 *
 * Monotonic on purpose: once /api/init has reported an unprovisioned device,
 * this stays true no matter what later polls say. `needs_onboarding` clears the
 * instant the wizard creates the administrator, and this provider re-polls
 * /api/init on a timer, so a consumer gating on the raw flag would unmount the
 * wizard part-way through and strand the user with the import and summary
 * steps unreachable. The wizard finishes with a page reload, which resets it.
 *
 * @param previous - Latch value so far.
 * @param initData - Freshly fetched /api/init payload.
 */
export function latchNeedsOnboarding(
  previous: boolean,
  initData: { needs_onboarding?: boolean } | null | undefined,
): boolean {
  return previous || Boolean(initData?.needs_onboarding);
}

const MAX_RETRIES = 2;
const RETRY_DELAY = 1000;
const CHECK_INTERVAL = 30000;
/** While the panel is blocked on a controller that is coming back. */
const BLOCKED_CHECK_INTERVAL = 5000;
/** Remembers, for this tab, a server version the user chose to go on with. */
const STALE_BYPASS_KEY = 'boneio-stale-bypass';

/** The version this build was made for; null on the dev server, which has none. */
const PANEL_VERSION: string | null = import.meta.env.DEV ? null : (__APP_VERSION__ || null);

function sessionGet(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * Provider that fetches /api/init once on mount and periodically checks availability.
 */
export function AppInitProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AppInitData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isApiAvailable, setIsApiAvailable] = useState(true);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [panelState, setPanelState] = useState<PanelState>('ok');

  const updatePanelState = useCallback((reachable: boolean, serverVersion: string | null) => {
    const basePath = window.__BONEIO_BASE_PATH__;
    const now = Date.now();
    let mark = readUpdateMark(window.localStorage, basePath, now);
    if (mark) {
      const next = noteReachability(mark, reachable, now);
      if (next !== mark) writeUpdateMark(window.localStorage, basePath, next);
      mark = next;
    }
    if (mark && reachable && updateArrived(mark, serverVersion)) {
      clearUpdateMark(window.localStorage, basePath);
      mark = null;
    }
    let state = computePanelState({ reachable, serverVersion, panelVersion: PANEL_VERSION, mark });
    if (state === 'stale_panel' && serverVersion && sessionGet(STALE_BYPASS_KEY) === serverVersion) {
      state = 'ok';
    }
    setPanelState(state);
  }, []);

  const dismissPanelState = useCallback(() => {
    clearUpdateMark(window.localStorage, window.__BONEIO_BASE_PATH__);
    const serverVersion = data?.version;
    if (panelState === 'stale_panel' && serverVersion) {
      try {
        window.sessionStorage.setItem(STALE_BYPASS_KEY, serverVersion);
      } catch {
        // Without sessionStorage the bypass lasts until the next poll.
      }
    }
    setPanelState('ok');
  }, [data?.version, panelState]);

  const fetchInit = useCallback(async () => {
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const { data: initData } = await axios.get('/api/init');
        setData(prev => {
          // Avoid re-render if data hasn't changed (periodic re-fetch)
          if (prev && JSON.stringify(prev) === JSON.stringify(initData)) return prev;
          return initData;
        });
        setNeedsOnboarding(prev => latchNeedsOnboarding(prev, initData));
        // Remember this for the next cold start, so the first paint knows
        // whether to draw the app shell or stay quiet for the wizard.
        writeProvisioningHint(
          window.localStorage,
          window.__BONEIO_BASE_PATH__,
          Boolean(initData?.needs_onboarding),
        );
        updatePanelState(true, initData?.version ?? null);
        setIsApiAvailable(true);
        setIsLoading(false);
        // Warm /api/config cache in background so UISettings loads instantly
        prefetchConfig();
        return;
      } catch {
        if (attempt < MAX_RETRIES) {
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
        }
      }
    }
    // All retries exhausted
    updatePanelState(false, null);
    setIsApiAvailable(false);
    setIsLoading(false);
  }, [updatePanelState]);

  // Initial fetch
  useEffect(() => {
    fetchInit();
  }, [fetchInit]);

  // Periodic re-check, more often while the panel waits for the controller
  const blocked = !isApiAvailable || panelState === 'stale_panel';
  useEffect(() => {
    const interval = setInterval(fetchInit, blocked ? BLOCKED_CHECK_INTERVAL : CHECK_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchInit, blocked]);

  // Re-check when page becomes visible (PWA returning from background)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchInit();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [fetchInit]);

  return (
    <AppInitContext.Provider
      value={{ data, isLoading, isApiAvailable, needsOnboarding, panelState, dismissPanelState, refetch: fetchInit }}
    >
      {children}
    </AppInitContext.Provider>
  );
}
