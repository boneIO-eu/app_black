/**
 * ConfigContext - provides configuration state across the application.
 *
 * Previously fetched /api/config on startup (0.5-1.3s on BBB) just to extract
 * a few boolean flags. Now reads config metadata from /api/init (via AppInitContext)
 * which is already fetched on startup.
 *
 * The full /api/config is only fetched on-demand (e.g. by UISettings editor).
 */

import { createContext, useContext, useMemo, ReactNode } from 'react';
import { useAppInit } from './AppInitContext';

/** Board versions that support CAN bus (0.5+) */
const CAN_SUPPORTED_VERSIONS = ['0.5', '0.6', '0.7', '0.8', '1.0'];

/** Max inputs per board version */
const MAX_INPUTS: Record<string, number> = {
  '0.2': 52,
  '0.3': 52,
  '0.4': 52,
  '0.5': 49,
  '0.6': 49,
  '0.7': 49,
  '0.8': 49,
  '1.0': 49,
};

interface ConfigContextType {
  /** Whether the 'boneio' section exists in config */
  hasBoneioSection: boolean;
  /** Whether the 'irrigation' section exists and has entries */
  hasIrrigationSection: boolean;
  /** Whether the config is still loading */
  isLoading: boolean;
  /** Hardware board version (e.g., '0.7') or null if not set */
  boardVersion: string | null;
  /** Whether CAN bus is supported on this board version */
  canSupported: boolean;
  /** Maximum number of inputs for this board version */
  maxInputs: number;
  /** Refresh the config state (re-fetches /api/init) */
  refreshConfig: () => Promise<void>;
}

const ConfigContext = createContext<ConfigContextType | undefined>(undefined);

interface ConfigProviderProps {
  children: ReactNode;
}

/**
 * ConfigProvider that derives config state from AppInitContext.
 *
 * No longer makes a separate /api/config call on startup.
 * Config metadata (has_boneio, board_version, has_irrigation) comes
 * from /api/init which is already fetched by AppInitProvider.
 */
export function ConfigProvider({ children }: ConfigProviderProps) {
  const { data: initData, isLoading, refetch } = useAppInit();

  const value = useMemo<ConfigContextType>(() => {
    const boardVersion = initData?.board_version ?? null;
    return {
      hasBoneioSection: initData?.has_boneio ?? false,
      hasIrrigationSection: initData?.has_irrigation ?? false,
      isLoading,
      boardVersion,
      canSupported: boardVersion ? CAN_SUPPORTED_VERSIONS.includes(boardVersion) : true,
      maxInputs: boardVersion && MAX_INPUTS[boardVersion] ? MAX_INPUTS[boardVersion] : 49,
      refreshConfig: refetch,
    };
  }, [initData, isLoading, refetch]);

  return (
    <ConfigContext.Provider value={value}>
      {children}
    </ConfigContext.Provider>
  );
}

export function useConfig() {
  const context = useContext(ConfigContext);
  if (context === undefined) {
    throw new Error('useConfig must be used within a ConfigProvider');
  }
  return context;
}
