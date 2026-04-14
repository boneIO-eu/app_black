import { useState, useEffect, useCallback, useRef } from 'react';
import axios from '@/api/axios';

const CHECK_INTERVAL = 30000; // 30 seconds
const MAX_RETRIES = 2; // retry up to 2 times before marking unavailable
const RETRY_DELAY = 1000; // 1 second between retries

/**
 * Hook that monitors API availability with retry logic and
 * automatic re-check when the page regains visibility (e.g. after
 * the phone was in the background).
 */
export function useApiAvailability() {
  const [isApiAvailable, setIsApiAvailable] = useState(true);
  const [isChecking, setIsChecking] = useState(true);
  const [nextCheckTime, setNextCheckTime] = useState<Date>(new Date(Date.now() + CHECK_INTERVAL));
  const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const setupInterval = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    intervalRef.current = setInterval(() => {
      checkApiAvailability();
    }, CHECK_INTERVAL);
  }, []);

  const checkApiAvailability = useCallback(async () => {
    setIsChecking(true);

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        await axios.get('/api/version');
        // Success — mark available immediately, no artificial delay
        setIsApiAvailable(true);
        setIsChecking(false);
        setNextCheckTime(new Date(Date.now() + CHECK_INTERVAL));
        return;
      } catch {
        // If we still have retries left, wait and try again
        if (attempt < MAX_RETRIES) {
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
        }
      }
    }

    // All retries exhausted — API is unavailable
    setIsApiAvailable(false);
    setIsChecking(false);
    setNextCheckTime(new Date(Date.now() + CHECK_INTERVAL));
  }, []);

  // Manual check function that also resets the interval
  const checkNow = useCallback(async () => {
    await checkApiAvailability();
    setupInterval();
  }, [checkApiAvailability, setupInterval]);

  useEffect(() => {
    // Initial check
    checkApiAvailability();
    // Set up periodic interval
    setupInterval();

    // Re-check immediately when page becomes visible again (e.g. PWA
    // returning from background on mobile). This prevents the brief
    // "API unavailable" flash caused by a stale first request.
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        checkApiAvailability();
        setupInterval(); // reset interval so next check is a full period away
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [checkApiAvailability, setupInterval]);

  return { 
    isApiAvailable, 
    isChecking, 
    nextCheckTime,
    nextCheckInMs: Math.max(0, nextCheckTime.getTime() - Date.now()),
    checkNow
  };
}
