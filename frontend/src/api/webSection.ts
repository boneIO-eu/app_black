/**
 * Change part of the `web` section without losing the rest of it.
 *
 * `PUT /api/config/web` replaces the whole section, so a caller that wants to
 * flip one setting has to send every other one back as stored. Whatever is
 * missing from the body is gone from config.yaml: drop `expose` and the panel
 * comes back on the LAN at the next start, drop `cloud` and the backend reads
 * it as PWA switched off — it stops registration and puts the local Caddy
 * template back.
 *
 * The section is read fresh from the device rather than from the config
 * cache, so what gets merged into is what is saved, not a copy from before
 * the last change.
 */

import type { AxiosRequestConfig } from 'axios';
import axios from '@/api/axios';

export type WebSection = Record<string, unknown>;

/** What GET /api/config answers: the sections sit under `config`. */
interface ConfigResponse {
  config?: Record<string, unknown>;
}

/**
 * Read the stored `web` section, apply `change` to it and save the result.
 *
 * @param change Gets the section as stored and returns the whole section to
 *   save — spread the argument into it.
 * @param options Passed to the PUT, e.g. a longer timeout.
 * @returns The body of the PUT response.
 */
export async function updateWebSection<T = Record<string, unknown>>(
  change: (web: WebSection) => WebSection,
  options?: AxiosRequestConfig,
): Promise<T> {
  const { data } = await axios.get<ConfigResponse>('/api/config');
  const stored = data?.config?.web;
  const web = stored && typeof stored === 'object' ? (stored as WebSection) : {};
  const { data: saved } = await axios.put<T>('/api/config/web', change(web), options);
  return saved;
}
