/**
 * ConfigContext - provides configuration state across the application.
 * 
 * This context checks if the 'boneio' section exists in the configuration
 * and exposes this information to components that need it (e.g., Navigation).
 */

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import axios from '@/api/axios';
import { useAuth } from '@/hooks/useAuth';

interface ConfigContextType {
  /** Whether the 'boneio' section exists in config */
  hasBoneioSection: boolean;
  /** Whether the config is still loading */
  isLoading: boolean;
  /** Refresh the config state */
  refreshConfig: () => Promise<void>;
}

const ConfigContext = createContext<ConfigContextType | undefined>(undefined);

interface ConfigProviderProps {
  children: ReactNode;
}

export function ConfigProvider({ children }: ConfigProviderProps) {
  const [hasBoneioSection, setHasBoneioSection] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
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
    } catch (error) {
      console.error('Failed to load config:', error);
      setHasBoneioSection(false);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, isAuthRequired]);

  useEffect(() => {
    refreshConfig();
  }, [refreshConfig]);

  return (
    <ConfigContext.Provider value={{ hasBoneioSection, isLoading, refreshConfig }}>
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
