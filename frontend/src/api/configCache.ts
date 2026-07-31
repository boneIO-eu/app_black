/**
 * Lightweight in-memory cache for /api/config responses.
 *
 * Previously, ConfigContext fetched /api/config on every app startup, so the
 * data was already warm when UISettings loaded. After the optimization that
 * moved config metadata into /api/init, UISettings does a cold fetch on entry
 * which takes ~1-1.5s on BBB.
 *
 * Strategy (optimized for slow BBB hardware):
 * - `prefetchConfig()` — fires a background request to warm the cache
 * - `fetchConfig()` — returns cached data instantly, or awaits in-flight request
 * - `invalidateConfigCache()` — clears stale data AND immediately starts a
 *   background refetch so the cache is warm again before the next consumer
 *   needs it.
 *
 * Race condition protection:
 *   A generation counter ensures that stale responses from cancelled fetches
 *   never overwrite fresh data. Each invalidate bumps the generation; only
 *   the response matching the current generation is allowed to write to cache.
 */

import axios from '@/api/axios';

interface ConfigCache {
  data: Record<string, unknown> | null;
  promise: Promise<Record<string, unknown>> | null;
  timestamp: number;
  /** Monotonic counter — incremented on every invalidation. */
  generation: number;
}

const cache: ConfigCache = {
  data: null,
  promise: null,
  timestamp: 0,
  generation: 0,
};

/** Cache TTL in milliseconds (5 minutes). */
const CACHE_TTL = 5 * 60 * 1000;

/**
 * Internal fetch that populates the cache.
 * Uses a generation guard so stale responses from previous invalidations
 * are discarded instead of overwriting newer data.
 */
function doFetch(): Promise<Record<string, unknown>> {
  if (cache.promise) {
    return cache.promise;
  }
  const gen = cache.generation;
  cache.promise = axios
    .get('/api/config')
    .then(({ data }) => {
      // Only write to cache if no newer invalidation happened while in flight
      if (cache.generation === gen) {
        cache.data = data;
        cache.timestamp = Date.now();
      }
      cache.promise = null;
      return data;
    })
    .catch(() => {
      cache.promise = null;
      return {} as Record<string, unknown>;
    });
  return cache.promise;
}

/**
 * Prefetch /api/config in the background.
 * Call after successful /api/init to warm the cache before user visits settings.
 * Non-blocking — errors are silently ignored.
 */
export function prefetchConfig(): void {
  if (cache.data && Date.now() - cache.timestamp < CACHE_TTL) {
    return; // Already cached and fresh
  }
  doFetch();
}

/**
 * Fetch /api/config, using cache if available.
 * Returns the full config response data.
 */
export async function fetchConfig(): Promise<Record<string, unknown>> {
  // Return cached data if fresh
  if (cache.data && Date.now() - cache.timestamp < CACHE_TTL) {
    return cache.data;
  }
  // Fetch (or join in-flight request)
  return doFetch();
}

/**
 * Invalidate the config cache and immediately start a background refetch.
 *
 * On BBB, /api/config takes ~1-1.5s. By refetching right after a save,
 * the cache is warm again before the user navigates back to settings.
 * The refetch is non-blocking — callers are not delayed.
 *
 * Bumps the generation counter so any in-flight fetch from a previous
 * generation is discarded when it resolves (prevents stale data).
 */
export function invalidateConfigCache(): void {
  cache.data = null;
  cache.promise = null;
  cache.timestamp = 0;
  cache.generation++;
  // Immediately start background refetch so cache is warm for next access
  doFetch();
}
