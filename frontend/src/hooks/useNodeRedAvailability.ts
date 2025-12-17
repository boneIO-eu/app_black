import { useState, useEffect } from 'react';

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
        const response = await fetch('/nodered-status', {
          method: 'GET',
          cache: 'no-cache',
        });
        
        if (response.ok) {
          const header = response.headers.get('X-NodeRed-Available');
          if (header === 'true') {
            setIsNodeRedAvailable(true);
          } else {
            // Fallback: check JSON response
            const data = await response.json();
            setIsNodeRedAvailable(data.available === true);
          }
        } else {
          setIsNodeRedAvailable(false);
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
