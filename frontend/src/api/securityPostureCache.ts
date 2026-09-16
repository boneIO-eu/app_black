/**
 * Shared cache for /api/security/posture.
 *
 * Three components ask for the posture, and on the security page all three
 * are mounted at once: the section itself, the sidebar badge under Access,
 * and the post-update prompt. Each used to fire its own request, so opening
 * the page cost three round trips for one answer.
 *
 * That matters more than the count suggests. The endpoint re-reads and parses
 * config.yaml on every call (~260 ms on a BBB) and does it synchronously, so
 * the three do not overlap — they queue, and the spinner stays up for the sum
 * of them plus whatever else was waiting behind.
 *
 * Same shape as configCache: an in-flight promise callers join rather than
 * duplicate, a short freshness window, and an explicit invalidate for the
 * "check again" button, which must see the current state rather than the one
 * from before the thing it just fixed.
 */

import axios from '@/api/axios';
import type { SecurityPosture } from '@/hooks/useSecurityPosture';

interface PostureCache {
  data: SecurityPosture | null;
  promise: Promise<SecurityPosture> | null;
  timestamp: number;
  generation: number;
}

const cache: PostureCache = {
  data: null,
  promise: null,
  timestamp: 0,
  generation: 0,
};

/**
 * How long a posture stays fresh.
 *
 * Deliberately short. The posture answers "what is still unlocked", and the
 * usual reason to look at it twice is that something was just changed — so
 * this is only long enough to collapse the burst of mounts that happens when
 * a page opens, not to keep an answer around.
 */
const CACHE_TTL = 15 * 1000;

function doFetch(): Promise<SecurityPosture> {
  if (cache.promise) {
    return cache.promise;
  }
  const gen = cache.generation;
  cache.promise = axios
    .get<SecurityPosture>('/api/security/posture')
    .then(({ data }) => {
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
 * Read the posture, joining an in-flight request or reusing a fresh answer.
 *
 * Rejects the way axios does when the request fails — callers decide what an
 * unknown posture means, and a failed check must never read as a pass.
 */
export function fetchSecurityPosture(): Promise<SecurityPosture> {
  if (cache.data && Date.now() - cache.timestamp < CACHE_TTL) {
    return Promise.resolve(cache.data);
  }
  return doFetch();
}

/** Drop the cached posture so the next read goes to the device. */
export function invalidateSecurityPosture(): void {
  cache.data = null;
  cache.promise = null;
  cache.timestamp = 0;
  cache.generation++;
}
