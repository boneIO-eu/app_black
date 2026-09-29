/**
 * AppInitContext - Single /api/init call that replaces multiple startup requests.
 *
 * Previously the frontend fired 5+ separate API calls on page load:
 *   GET /api/version (x3), GET /api/auth/required, GET /api/pwa_name, GET /api/cloud/status (x2)
 *
 * Now all of this data comes from a single GET /api/init call and is distributed
 * via React context to all consumers (Navigation, DrawerSide, useAuth, etc.).
 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import axios from '@/api/axios';
import { prefetchConfig } from '@/api/configCache';
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
  serial_no: string;
  serial_override?: string | null;
  auth_required: boolean;
  pwa_name: string;
  pwa_default: string;
  pwa_max_length: number;
  cloud: CloudStatus;
  has_boneio: boolean;
  board_version: string | null;
  has_irrigation: boolean;
}

interface AppInitContextType {
  /** All init data, null while loading */
  data: AppInitData | null;
  /** Whether the init fetch is still in progress */
  isLoading: boolean;
  /** Whether the API is available */
  isApiAvailable: boolean;
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
      value={{ data, isLoading, isApiAvailable, panelState, dismissPanelState, refetch: fetchInit }}
    >
      {children}
    </AppInitContext.Provider>
  );
}
