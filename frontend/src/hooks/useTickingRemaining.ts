import { useState, useEffect } from 'react';

/**
 * Seconds left, counting down every second between polls.
 *
 * For a value the server reports as "N seconds remaining" on a poll that
 * comes only every few seconds: shown as it arrives, the alarm's arming
 * countdown jumped 32 → 29 → 26. Each reading restarts the count from what
 * the server said, so the local clock never drifts far from it.
 *
 * @param remainingS - The latest reading; null when nothing is counting.
 * @returns Seconds left, or null when `remainingS` is null.
 */
export function useTickingRemaining(remainingS: number | null | undefined): number | null {
  const [left, setLeft] = useState<number | null>(null);

  useEffect(() => {
    if (remainingS == null) return;
    const readAt = Date.now();
    const tick = () => setLeft(Math.max(0, remainingS - (Date.now() - readAt) / 1000));
    // A quarter-second tick so the whole-second display turns over on time
    // whatever the phase of the poll.
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [remainingS]);

  if (remainingS == null) return null;
  // Until the first tick after a fresh reading, the reading itself.
  return left ?? remainingS;
}
