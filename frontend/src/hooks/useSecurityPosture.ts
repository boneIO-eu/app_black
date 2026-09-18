/**
 * The device's security posture, as the backend sees it.
 *
 * Each consumer — the Settings section, the sidebar badge, the prompt after an
 * update — fetches its own copy. They agree because the backend computes the
 * answer rather than any of them doing it, which is the whole reason the
 * posture is a backend model and not a pile of frontend conditions.
 *
 * Read-only accounts never see this. The endpoint refuses them (a list of
 * what is unlocked is a shopping list), so asking would only produce 403s in
 * the console.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchSecurityPosture,
  invalidateSecurityPosture,
} from '../api/securityPostureCache';
import { useAuth } from './useAuth';

export type Severity = 'critical' | 'warning' | 'info';
export type CheckState = 'ok' | 'failed' | 'unknown';

export interface SecurityCheck {
  id: string;
  title: string;
  severity: Severity;
  state: CheckState;
  detail: string;
  remedy: string;
  /** A device-specific fact, shown as sent — never translated. */
  context?: string;
  /** Bare name = Settings section; `system:<anchor>` = System page. */
  settings_section: string | null;
}

export interface SecuritySummary {
  failed: number;
  /**
   * Failures worth interrupting someone about — critical and warning only.
   * INFO is advice that applies to almost every device, and a badge that is
   * always red is a badge nobody reads.
   */
  actionable: number;
  critical: number;
  warning: number;
  info: number;
  worst: Severity | null;
}

export interface SecurityPosture {
  checks: SecurityCheck[];
  summary: SecuritySummary;
}

export function useSecurityPosture() {
  const { isAdmin } = useAuth();
  const [fetched, setFetched] = useState<SecurityPosture | null>(null);
  const [settled, setSettled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Derived rather than stored, so nothing is written to state before the
  // first await — a synchronous setState inside the mount effect is what
  // makes React re-render in a cascade.
  const posture = isAdmin ? fetched : null;
  const loading = isAdmin && !settled;

  /**
   * Read the posture. Goes through the shared cache, so the three components
   * that want it on the same screen cost one request rather than three.
   *
   * `force` is what the "check again" button passes: after fixing something,
   * a cached answer is exactly the wrong one to show.
   */
  const load = useCallback(async (force: boolean) => {
    if (!isAdmin) return;
    if (force) invalidateSecurityPosture();
    try {
      const data = await fetchSecurityPosture();
      setFetched(data);
      setError(null);
    } catch {
      // A posture that cannot be fetched must not turn into a green tick, so
      // it stays null and every consumer renders "unknown".
      setFetched(null);
      setError('unavailable');
    } finally {
      setSettled(true);
    }
  }, [isAdmin]);

  const refresh = useCallback(() => load(true), [load]);

  useEffect(() => {
    // Fetching on mount is the external-system synchronisation this rule is
    // meant to permit. It fires anyway because it cannot see that every
    // setState in `refresh` happens after an await, so there is no cascade to
    // avoid. Same false positive as in useMigrations.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(false);
  }, [load]);

  return { posture, loading, error, refresh };
}
