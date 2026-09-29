/**
 * Telling a stale panel, an update in progress and a controller that is down
 * apart.
 *
 * The service worker precaches the whole build and answers every navigation
 * from that cache, so after a firmware update F5 keeps handing out the old
 * panel until the new service worker has downloaded everything — from a
 * BeagleBone busy starting up and running migrations. The old panel's API
 * calls meanwhile succeed against the new server, and it renders its own pages
 * over data it was never written for. Seen going from 1.5 to 1.6: five
 * refreshes of old settings pages before the first-run wizard appeared.
 *
 * Two signals fix that. The server's version, compared with the one this
 * panel was built from, says for certain that the panel is stale. A mark left
 * in this browser when an update was started says that a controller which
 * does not answer is most likely installing it, rather than broken.
 *
 * The mark's key and shape are shared with the 1.5.x panel, which writes it
 * for the update that takes a controller to 1.6: change neither.
 */

import type { HintStorage } from './provisioning';

const MARK_KEY = 'boneio-update';
const RELOAD_KEY = 'boneio-stale-reload';

/** How long after starting an update a silent controller is taken to be installing it. */
export const UPDATE_MARK_TTL_MS = 60 * 60 * 1000;

/** What the browser remembers about an update it started. */
export interface UpdateMark {
  /** Unix milliseconds. */
  startedAt: number;
  /** The version the server reported before the update. */
  fromVersion: string;
  /** The version asked for; null when the server was left to pick the latest. */
  toVersion: string | null;
  /** Set once the controller was seen not answering, i.e. it restarted. */
  wentDown?: boolean;
}

export type PanelState =
  /** Nothing to say. */
  | 'ok'
  /** The server runs another version than this panel was built for. */
  | 'stale_panel'
  /** No answer, and this browser started an update less than an hour ago. */
  | 'updating'
  /** No answer, and nothing known about an update. */
  | 'probably_updating'
  /** Back on the old version after restarting for an update. */
  | 'update_failed';

/** The storage subset used here, so tests can pass a plain fake. */
export interface MarkStorage extends HintStorage {
  removeItem(key: string): void;
}

/**
 * Scope a key to one device.
 *
 * Behind HA ingress several controllers share a browser origin. Same suffix
 * scheme as the provisioning hint and the theme.
 *
 * @param key - Base key.
 * @param basePath - `window.__BONEIO_BASE_PATH__`, absent on direct access.
 */
export function scopedKey(key: string, basePath: string | undefined): string {
  const match = basePath?.match(/\/(proxy\/\d+)\/?$/);
  return match ? `${key}-${match[1].replace('/', '-')}` : key;
}

/** `v1.6.0` and `1.6.0` name the same release; GitHub tags carry the `v`. */
export function normalizeVersion(version: string | null | undefined): string | null {
  if (!version) return null;
  const trimmed = version.trim();
  return trimmed.startsWith('v') ? trimmed.slice(1) : trimmed;
}

/**
 * The update mark, if one was left and has not expired.
 *
 * @param storage - Usually `window.localStorage`.
 * @param basePath - See {@link scopedKey}.
 * @param now - Unix milliseconds.
 */
export function readUpdateMark(
  storage: MarkStorage | undefined,
  basePath: string | undefined,
  now: number,
): UpdateMark | null {
  try {
    const raw = storage?.getItem(scopedKey(MARK_KEY, basePath));
    if (!raw) return null;
    const mark = JSON.parse(raw) as UpdateMark;
    if (typeof mark?.startedAt !== 'number' || typeof mark.fromVersion !== 'string') return null;
    if (now - mark.startedAt > UPDATE_MARK_TTL_MS || mark.startedAt > now + 60_000) return null;
    return mark;
  } catch {
    // Private mode and "block site data" throw; a corrupt value is no mark.
    return null;
  }
}

/** Remember an update this browser is about to start. */
export function writeUpdateMark(
  storage: MarkStorage | undefined,
  basePath: string | undefined,
  mark: UpdateMark,
): void {
  try {
    storage?.setItem(scopedKey(MARK_KEY, basePath), JSON.stringify(mark));
  } catch {
    // Without storage the panel falls back to "probably updating".
  }
}

/** Forget the update: it finished, failed, or never started. */
export function clearUpdateMark(storage: MarkStorage | undefined, basePath: string | undefined): void {
  try {
    storage?.removeItem(scopedKey(MARK_KEY, basePath));
  } catch {
    // Nothing to do.
  }
}

/**
 * Has the update the mark describes arrived?
 *
 * The version asked for when it is known, otherwise anything but the version
 * it started from.
 */
export function updateArrived(mark: UpdateMark, serverVersion: string | null | undefined): boolean {
  const server = normalizeVersion(serverVersion);
  if (!server) return false;
  const wanted = normalizeVersion(mark.toVersion);
  return wanted ? server === wanted : server !== normalizeVersion(mark.fromVersion);
}

/**
 * What the panel should say.
 *
 * @param input.reachable - Whether /api/init answered.
 * @param input.serverVersion - Its version, when it answered.
 * @param input.panelVersion - The version this build was made from; null
 *   skips the stale check (the dev server, whose build has no version).
 * @param input.mark - From {@link readUpdateMark}.
 */
export function panelState(input: {
  reachable: boolean;
  serverVersion: string | null | undefined;
  panelVersion: string | null;
  mark: UpdateMark | null;
}): PanelState {
  const { reachable, serverVersion, panelVersion, mark } = input;
  if (!reachable) return mark ? 'updating' : 'probably_updating';

  const server = normalizeVersion(serverVersion);
  const panel = normalizeVersion(panelVersion);
  if (server && panel && server !== panel) return 'stale_panel';

  if (mark && mark.wentDown && server && !updateArrived(mark, server)
      && server === normalizeVersion(mark.fromVersion)) {
    return 'update_failed';
  }
  return 'ok';
}

/**
 * Whether this tab already reloaded to get rid of a stale panel for this
 * server version. A second reload would not help and a loop would lock the
 * user out, so the caller shows a manual screen instead.
 */
export function alreadyReloadedFor(storage: HintStorage | undefined, serverVersion: string): boolean {
  try {
    return storage?.getItem(RELOAD_KEY) === serverVersion;
  } catch {
    return true;
  }
}

/** Note the reload about to happen, see {@link alreadyReloadedFor}. */
export function noteReloadFor(storage: HintStorage | undefined, serverVersion: string): void {
  try {
    storage?.setItem(RELOAD_KEY, serverVersion);
  } catch {
    // Without sessionStorage alreadyReloadedFor says true: no loop either way.
  }
}
