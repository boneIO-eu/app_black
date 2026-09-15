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
import { writeProvisioningHint } from '@/utils/provisioning';

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
  /** True when the device has no administrator yet and the wizard must run. */
  needs_onboarding: boolean;
  /** True when config.yaml opts this device out of authentication entirely. */
  allow_anonymous?: boolean;
  /** Set when a pre-1.6 web.auth block was migrated into users.json on boot. */
  legacy_migration?: { username: string; used_secret_file: boolean } | null;
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
  /** Re-fetch init data (e.g. after visibility change) */
  refetch: () => Promise<void>;
}

const AppInitContext = createContext<AppInitContextType>({
  data: null,
  isLoading: true,
  isApiAvailable: true,
  needsOnboarding: false,
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

/**
 * Provider that fetches /api/init once on mount and periodically checks availability.
 */
export function AppInitProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AppInitData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isApiAvailable, setIsApiAvailable] = useState(true);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

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
    setIsApiAvailable(false);
    setIsLoading(false);
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchInit();
  }, [fetchInit]);

  // Periodic re-check
  useEffect(() => {
    const interval = setInterval(fetchInit, CHECK_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchInit]);

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
    <AppInitContext.Provider value={{ data, isLoading, isApiAvailable, needsOnboarding, refetch: fetchInit }}>
      {children}
    </AppInitContext.Provider>
  );
}
