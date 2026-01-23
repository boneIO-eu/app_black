import { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useAuth } from './useAuth';

export function useDeviceName() {
  const [deviceName, setDeviceName] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { isAuthenticated, isAuthRequired } = useAuth();

  useEffect(() => {
    const fetchDeviceName = async () => {
      // Don't fetch if auth is required but user is not authenticated
      if (isAuthRequired && !isAuthenticated) {
        setIsLoading(false);
        return;
      }

      try {
        const response = await axios.get('/api/name');
        setDeviceName(response.data.name);
      } catch (error) {
        console.error('Failed to fetch device name:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchDeviceName();
  }, [isAuthenticated, isAuthRequired]);

  return { deviceName, isLoading };
}
