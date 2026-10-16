/**
 * How many AI proposals wait for approval, for the Settings menu's badge.
 *
 * Admin only, like the queue itself: the endpoint refuses anyone else, so
 * asking would only fill the console with 403s. Polled once a minute - an
 * agent files a proposal from outside the panel, so nothing here would know.
 */
import { useEffect, useState } from 'react';
import axios from '@/api/axios';
import { useAuth } from './useAuth';

const POLL_MS = 60_000;
/** Sent by the proposals page after approving or rejecting one. */
export const PROPOSALS_CHANGED = 'boneio:proposals-changed';

export function usePendingProposals(): number {
  const { isAdmin } = useAuth();
  const [pending, setPending] = useState(0);

  useEffect(() => {
    if (!isAdmin) return;
    let alive = true;
    const load = async () => {
      try {
        const { data } = await axios.get('/api/proposals/count');
        if (alive) setPending(data.pending ?? 0);
      } catch {
        // An older controller has no queue; no badge is the right answer.
      }
    };
    void load();
    const timer = window.setInterval(load, POLL_MS);
    window.addEventListener(PROPOSALS_CHANGED, load);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener(PROPOSALS_CHANGED, load);
    };
  }, [isAdmin]);

  return isAdmin ? pending : 0;
}
