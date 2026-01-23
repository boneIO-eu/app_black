import { useState, useEffect } from 'react';
import axios from '@/api/axios';

/**
 * Hook to check if Node-RED is available via nginx reverse proxy.
 * Checks the /nodered-status endpoint which returns JSON with availability info.
 * This endpoint only exists when nginx proxy is configured.
 */
export function useNodeRedAvailability() {
  const [isNodeRedAvailable, setIsNodeRedAvailable] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const checkNodeRedAvailability = async () => {
      try {
        const response = await axios.get('/nodered-status', {
          headers: { 'Cache-Control': 'no-cache' },
        });
        
        const header = response.headers['x-nodered-available'];
        if (header === 'true') {
          setIsNodeRedAvailable(true);
        } else {
          // Fallback: check JSON response
          setIsNodeRedAvailable(response.data.available === true);
        }
      } catch (error) {
        // Endpoint doesn't exist - nginx proxy not configured
        setIsNodeRedAvailable(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkNodeRedAvailability();
  }, []);

  return { isNodeRedAvailable, isLoading };
}
