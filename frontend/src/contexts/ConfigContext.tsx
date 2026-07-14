/**
 * ConfigContext - provides configuration state across the application.
 *
 * This context checks if the 'boneio' section exists in the configuration
 * and exposes this information to components that need it (e.g., Navigation).
 */

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import axios from '@/api/axios';
import { useAuth } from '@/hooks/useAuth';

/** Board versions that support CAN bus (0.5+) */
const CAN_SUPPORTED_VERSIONS = ['0.5', '0.6', '0.7', '0.8', '1.0'];

/** Board versions that use DS2482 I2C bridge for 1-Wire (no GPIO 1-Wire) */
const DS2482_VERSIONS = ['1.0'];

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
  /** Whether this board uses DS2482 I2C bridge for 1-Wire (true = no GPIO 1-Wire) */
  ds2482Supported: boolean;
  /** Maximum number of inputs for this board version */
  maxInputs: number;
  /** Refresh the config state */
  refreshConfig: () => Promise<void>;
}

const ConfigContext = createContext<ConfigContextType | undefined>(undefined);

interface ConfigProviderProps {
  children: ReactNode;
}

export function ConfigProvider({ children }: ConfigProviderProps) {
  const [hasBoneioSection, setHasBoneioSection] = useState(false);
  const [hasIrrigationSection, setHasIrrigationSection] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [boardVersion, setBoardVersion] = useState<string | null>(null);
  const [canSupported, setCanSupported] = useState(true);
  const [ds2482Supported, setDs2482Supported] = useState(false);
  const [maxInputs, setMaxInputs] = useState(49);
  const { isAuthenticated, isAuthRequired } = useAuth();

  const refreshConfig = useCallback(async () => {
    // Don't fetch config if auth is required but user is not authenticated
    if (isAuthRequired && !isAuthenticated) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      const { data } = await axios.get('/api/config');
      // Check if 'boneio' section exists in config
      const hasBoneio = data?.config?.boneio !== undefined;
      setHasBoneioSection(hasBoneio);

      // Extract board version and compute capabilities
      const version = data?.config?.boneio?.version
        ? String(data.config.boneio.version)
        : null;
      setBoardVersion(version);
      setCanSupported(version ? CAN_SUPPORTED_VERSIONS.includes(version) : true);
      setDs2482Supported(version ? DS2482_VERSIONS.includes(version) : false);
      setMaxInputs(version && MAX_INPUTS[version] ? MAX_INPUTS[version] : 49);

      // Check for irrigation controllers:
      // 1. Direct `irrigation:` section in YAML
      // 2. Template entries with `platform: irrigation`
      const irrigationDirect = data?.config?.irrigation;
      const templates: any[] = data?.config?.template || [];
      const irrigationFromTemplates = templates.filter(
        (t: any) => t?.platform === 'irrigation'
      );
      const hasIrrigation =
        (Array.isArray(irrigationDirect) && irrigationDirect.length > 0) ||
        irrigationFromTemplates.length > 0;
      setHasIrrigationSection(hasIrrigation);
    } catch (error) {
      console.error('Failed to load config:', error);
      setHasBoneioSection(false);
      setHasIrrigationSection(false);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, isAuthRequired]);

  useEffect(() => {
    refreshConfig();
  }, [refreshConfig]);

  return (
    <ConfigContext.Provider value={{
      hasBoneioSection,
      hasIrrigationSection,
      isLoading,
      boardVersion,
      canSupported,
      ds2482Supported,
      maxInputs,
      refreshConfig,
    }}>
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
