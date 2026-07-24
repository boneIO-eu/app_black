import { useState, useEffect } from 'react';
import axios from '@/api/axios';

/**
 * Global cache for Node-RED availability.
 * Shared across all hook instances to avoid duplicate API calls
 * from Navigation + SystemState rendering simultaneously.
 */
let _cachedAvailability: boolean | null = null;
let _cachePromise: Promise<boolean> | null = null;

async function fetchAvailability(): Promise<boolean> {
  // If a request is already in-flight, reuse it (deduplication)
  if (_cachePromise) {
    return _cachePromise;
  }

  _cachePromise = (async () => {
    try {
      // Fast endpoint — only checks file existence, no docker subprocess
      const response = await axios.get('/api/nodered/available', {
        timeout: 3000,
      });
      const available = response.data?.available === true;
      _cachedAvailability = available;
      return available;
    } catch {
      // Fallback: check reverse proxy endpoint
      try {
        const fallbackResponse = await axios.get('/nodered-status', {
          timeout: 3000,
        });
        const header = fallbackResponse.headers['x-nodered-available'];
        const available = header === 'true' || fallbackResponse.data?.available === true;
        _cachedAvailability = available;
        return available;
      } catch {
        _cachedAvailability = false;
        return false;
      }
    } finally {
      // Allow re-fetch after 60 seconds
      setTimeout(() => {
        _cachePromise = null;
      }, 60_000);
    }
  })();

  return _cachePromise;
}

/**
 * Hook to check if Node-RED is available.
 *
 * Uses a fast backend endpoint (`/api/nodered/available`) that only checks
 * if docker-compose.yaml exists (no subprocess). Result is cached globally
 * so multiple components (Navigation, SystemState) share the same value
 * without duplicate API calls.
 */
export function useNodeRedAvailability() {
  const [isNodeRedAvailable, setIsNodeRedAvailable] = useState<boolean>(
    _cachedAvailability ?? false,
  );
  const [isLoading, setIsLoading] = useState<boolean>(_cachedAvailability === null);

  useEffect(() => {
    // If we already have a cached result, use it immediately
    if (_cachedAvailability !== null) {
      setIsNodeRedAvailable(_cachedAvailability);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    fetchAvailability().then((available) => {
      if (!cancelled) {
        setIsNodeRedAvailable(available);
        setIsLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return { isNodeRedAvailable, isLoading };
}
