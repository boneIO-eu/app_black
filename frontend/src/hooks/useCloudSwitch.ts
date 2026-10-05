/**
 * Follow the PWA switch from "registration on" to "the new address answers".
 *
 * Switching the PWA on swaps Caddy's compose template and recreates the
 * container. With `web.expose: proxy` that container is the only way into the
 * panel, so for about half a minute nothing answers — the controller itself
 * keeps running. Every request in that window fails at the network level,
 * and here that means "still switching", not "broken".
 *
 * The backend's `serving` says when Caddy is up on the cloud template. That
 * is not yet proof this browser can reach the registered name: a router with
 * DNS rebinding protection drops answers pointing at a LAN address, and the
 * name then never resolves. So once the backend says serving, the browser
 * tries the name itself, and only a name it reached is offered as the place
 * to go. The probe waits for `serving` on purpose — asking earlier can leave
 * a failed lookup in the resolver's cache for minutes.
 *
 * With `web.expose: proxy` the address this page came from does not come back
 * at all: the cloud template is the only way in. So once the status endpoint
 * has been silent for a while, the browser asks the new name directly instead
 * of waiting out the timeout on an origin that is gone.
 */

import { useEffect, useState } from 'react';
import axios from '@/api/axios';

export type CloudSwitchPhase =
  | 'idle'
  /** Registration running, Caddy not yet serving the certificate. */
  | 'switching'
  /** Caddy serving; the browser is trying the new address. */
  | 'probing'
  /** The new address answered from this browser. */
  | 'ready'
  /** Caddy serves, but this browser cannot reach the new address. */
  | 'unreachable'
  /** Never got to serving within the time a switch takes. */
  | 'timeout';

export interface CloudSwitch {
  phase: CloudSwitchPhase;
  /** Where the panel is now, e.g. https://blk239bb2.black.boneio.app:8443 */
  url: string | null;
  /** The backend's last registration error, for the timeout case. */
  error: string | null;
}

interface CloudStatus {
  serving?: boolean;
  url?: string | null;
  last_error?: string | null;
}

const POLL_MS = 3_000;
/** A switch takes ~40 s on a BeagleBone; DNS and the certificate add a few. */
const GIVE_UP_MS = 180_000;
const PROBE_ATTEMPTS = 4;
const PROBE_TIMEOUT_MS = 5_000;
/** Silence from the old origin after which the new name is asked directly. */
const DIRECT_PROBE_AFTER_MS = 30_000;

/**
 * Whether this browser can open `url` at all: name resolves, TLS completes.
 *
 * `no-cors` because the new address is another origin and does not answer
 * CORS for this one. The response is opaque, and that is enough: a fetch
 * that resolves reached a server, one that rejects did not.
 */
export async function probeReachable(url: string, timeoutMs = PROBE_TIMEOUT_MS): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    await fetch(new URL('/api/init', url).toString(), {
      mode: 'no-cors',
      cache: 'no-store',
      credentials: 'omit',
      signal: controller.signal,
    });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** Whether `url` is the origin this page is already on. */
export function isCurrentOrigin(url: string, location: Pick<Location, 'origin'> = window.location): boolean {
  try {
    return new URL(url).origin === location.origin;
  } catch {
    return false;
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * @param active - True once registration has been switched on and started.
 */
export function useCloudSwitch(active: boolean): CloudSwitch {
  const [state, setState] = useState<CloudSwitch>({ phase: 'idle', url: null, error: null });

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    (async () => {
      const deadline = Date.now() + GIVE_UP_MS;
      let status: CloudStatus | null = null;
      let lastError: string | null = null;
      // Known before the switch: the backend reports it as soon as the domain
      // is registered, while this origin still answers.
      let knownUrl: string | null = null;
      let silentSince: number | null = null;

      while (!cancelled && Date.now() < deadline) {
        try {
          const { data } = await axios.get<CloudStatus>('/api/cloud/status', { timeout: POLL_MS * 2 });
          lastError = data?.last_error ?? null;
          knownUrl = data?.url ?? knownUrl;
          silentSince = null;
          if (data?.serving && data.url) {
            status = data;
            break;
          }
        } catch {
          // The proxy this request went through is being recreated — or, with
          // expose: proxy, is gone for good and the panel lives at knownUrl.
          silentSince ??= Date.now();
          if (
            knownUrl && !isCurrentOrigin(knownUrl)
            && Date.now() - silentSince >= DIRECT_PROBE_AFTER_MS
            && await probeReachable(knownUrl)
          ) {
            if (!cancelled) setState({ phase: 'ready', url: knownUrl, error: null });
            return;
          }
        }
        await sleep(POLL_MS);
      }
      if (cancelled) return;
      if (!status?.url) {
        setState({ phase: 'timeout', url: knownUrl, error: lastError });
        return;
      }

      const url = status.url;
      if (isCurrentOrigin(url)) {
        setState({ phase: 'ready', url, error: null });
        return;
      }
      setState({ phase: 'probing', url, error: null });
      for (let attempt = 0; attempt < PROBE_ATTEMPTS && !cancelled; attempt++) {
        if (await probeReachable(url)) {
          if (!cancelled) setState({ phase: 'ready', url, error: null });
          return;
        }
        await sleep(POLL_MS);
      }
      if (!cancelled) setState({ phase: 'unreachable', url, error: null });
    })();

    return () => {
      cancelled = true;
    };
  }, [active]);

  // Switching from the moment registration is on; the effect only reports
  // what comes after that.
  return active && state.phase === 'idle' ? { phase: 'switching', url: null, error: null } : state;
}
