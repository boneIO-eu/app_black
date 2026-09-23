/**
 * In-memory cache for `config.schema.json`.
 *
 * The schema is 434 KB, and it was fetched again on every entry into Settings
 * — and again on the way back from any other page, because leaving unmounts
 * UISettings. It was also fetched with `Cache-Control: no-store`, which tells
 * the browser it may not even keep a copy to revalidate, so each visit paid for
 * the whole body over the wire. On a BeagleBone that is about a second, every
 * time, for a file that had not changed.
 *
 * It cannot change while the app runs: `config.schema.json` is generated
 * offline from `schema.yaml` and shipped inside the package, mounted read-only
 * as a static file. A new schema means a new build, which means a new page
 * load, which starts this module over.
 *
 * So there is no TTL and no invalidation. That is the point, not an oversight.
 *
 * The companion for the config itself is `configCache.ts`; the config does
 * change under us, which is why that one has both.
 */

import axios from '@/api/axios';

/* eslint-disable @typescript-eslint/no-explicit-any */

/** The parsed schema. Its shape is JSON Schema; consumers index into it. */
export type ConfigSchema = Record<string, any>;

const SCHEMA_URL = '/schema/config.schema.json';

let cached: ConfigSchema | null = null;
let inFlight: Promise<ConfigSchema> | null = null;

/**
 * The parsed schema, fetched at most once per page load.
 *
 * Concurrent callers share one request: ConfigEditor and UISettings can both
 * ask before either has an answer.
 *
 * @returns The parsed `config.schema.json`.
 */
export function fetchSchema(): Promise<ConfigSchema> {
  if (cached) return Promise.resolve(cached);
  if (inFlight) return inFlight;

  inFlight = axios
    .get<ConfigSchema>(SCHEMA_URL)
    .then(({ data }) => {
      cached = data;
      inFlight = null;
      return data;
    })
    .catch((err) => {
      // Not cached: a failure here is usually a restart mid-request, and the
      // next entry into Settings should try again rather than inherit it.
      inFlight = null;
      throw err;
    });

  return inFlight;
}

/**
 * Warm the cache without waiting for it.
 *
 * Fire this when something suggests Settings is about to be opened; the fetch
 * then overlaps with the rest of the page instead of blocking the first render.
 */
export function prefetchSchema(): void {
  void fetchSchema().catch(() => {
    // A failed prefetch is not an error — fetchSchema will retry on demand.
  });
}

/** Drop the cached schema. For tests; the app has no reason to call it. */
export function resetSchemaCache(): void {
  cached = null;
  inFlight = null;
}
