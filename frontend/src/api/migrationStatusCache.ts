/**
 * Shared cache for /api/migrations/status.
 *
 * Two components ask for the migration status, and on a settings page both are
 * mounted: the global banner that Layout renders above the page, and the
 * migrations section itself. Each owned a fetch and a poll timer.
 *
 * The count is worse than "two components" suggests, because Layout is
 * rendered inside every route element rather than once above the router — so
 * every navigation remounts the banner and asks again. One visit to
 * /settings/timezone measured five calls: the first mount and the navigation
 * remount, each doubled by StrictMode, plus a poll tick landing in the middle.
 *
 * Same shape as configCache and securityPostureCache: an in-flight promise
 * callers join rather than duplicate, a short freshness window, and an explicit
 * invalidate for the actions that change the answer.
 */

import axios from '@/api/axios';
import type { MigrationStatus } from '@/hooks/useMigrations';

interface MigrationStatusCache {
  data: MigrationStatus | null;
  promise: Promise<MigrationStatus> | null;
  timestamp: number;
  generation: number;
}

const cache: MigrationStatusCache = {
  data: null,
  promise: null,
  timestamp: 0,
  generation: 0,
};

/**
 * How long a status stays fresh.
 *
 * Deliberately below the shortest poll interval a consumer asks for (10s), so
 * the window only ever collapses the burst — the StrictMode double mount, the
 * remount a navigation causes, and the second consumer arriving on the same
 * screen — and never swallows a poll tick. The poll is what makes the banner
 * disappear once migrations are applied from somewhere else, so it has to keep
 * reaching the device.
 */
const CACHE_TTL = 8 * 1000;

function doFetch(): Promise<MigrationStatus> {
  if (cache.promise) {
    return cache.promise;
  }
  const gen = cache.generation;
  cache.promise = axios
    .get<MigrationStatus>('/api/migrations/status')
    .then(({ data }) => {
      // Discard a response whose generation was invalidated while in flight,
      // so a fetch started before an apply cannot overwrite the result of one
      // started after it.
      if (cache.generation === gen) {
        cache.data = data;
        cache.timestamp = Date.now();
      }
      cache.promise = null;
      return data;
    })
    .catch(err => {
      cache.promise = null;
      throw err;
    });
  return cache.promise;
}

/**
 * Read the migration status, joining an in-flight request or reusing a fresh
 * answer.
 *
 * Rejects the way axios does when the request fails — the banner decides what
 * an unknown status means, and it must not render as "nothing pending".
 */
export function fetchMigrationStatus(): Promise<MigrationStatus> {
  if (cache.data && Date.now() - cache.timestamp < CACHE_TTL) {
    return Promise.resolve(cache.data);
  }
  return doFetch();
}

/** Drop the cached status so the next read goes to the device. */
export function invalidateMigrationStatus(): void {
  cache.data = null;
  cache.promise = null;
  cache.timestamp = 0;
  cache.generation++;
}
