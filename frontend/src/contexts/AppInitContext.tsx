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

interface CloudStatus {
  enabled: boolean;
  domain?: string | null;
  cloud_config_active?: boolean;
  compose_writable?: boolean;
  last_error?: string | null;
}

interface AppInitData {
  version: string;
  serial_no: string;
  serial_override?: string | null;
  auth_required: boolean;
  pwa_name: string;
  pwa_default: string;
  pwa_max_length: number;
  cloud: CloudStatus;
}

interface AppInitContextType {
  /** All init data, null while loading */
  data: AppInitData | null;
  /** Whether the init fetch is still in progress */
  isLoading: boolean;
  /** Whether the API is available */
  isApiAvailable: boolean;
  /** Re-fetch init data (e.g. after visibility change) */
  refetch: () => Promise<void>;
}

const AppInitContext = createContext<AppInitContextType>({
  data: null,
  isLoading: true,
  isApiAvailable: true,
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

/**
 * Provider that fetches /api/init once on mount and periodically checks availability.
 */
export function AppInitProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AppInitData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isApiAvailable, setIsApiAvailable] = useState(true);

  const fetchInit = useCallback(async () => {
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const { data: initData } = await axios.get('/api/init');
        setData(initData);
        setIsApiAvailable(true);
        setIsLoading(false);
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
    <AppInitContext.Provider value={{ data, isLoading, isApiAvailable, refetch: fetchInit }}>
      {children}
    </AppInitContext.Provider>
  );
}
