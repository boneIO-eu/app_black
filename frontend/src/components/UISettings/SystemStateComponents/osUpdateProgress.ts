/**
 * Whether an OS update is still going, from what the helper reports.
 *
 * Two sources can disagree: the run's own record (``last.result``) and
 * ``systemctl is-active`` on its unit (``running``). The helper reads the unit
 * as stopped on any systemctl error or timeout, which is likely exactly while
 * dpkg replaces systemd on a busy single core. Trusting one such read stopped
 * the card polling mid-upgrade, left the log frozen and offered the buttons
 * again. A record that says running is now believed for a while even when the
 * unit does not show; only past that is the run taken as interrupted.
 */

export type RunPhase = 'idle' | 'running' | 'unconfirmed' | 'interrupted';

export const POLL_MS = 3000;

/** Between reads while the record and the unit disagree. */
export const UNCONFIRMED_POLL_MS = 12_000;

/** How long the record is believed without the unit, in browser time. */
export const INTERRUPTED_AFTER_MS = 60_000;

/** Between retries after a failed read, while a run may be in progress. */
export const READ_RETRY_MS = [5000, 10_000, 20_000, 30_000];

export interface RunReport {
  running?: boolean;
  last?: { result: string } | null;
}

/**
 * The phase a state read puts the run in.
 *
 * Args:
 *   report: The state the helper returned.
 *   now: ``Date.now()`` of this read.
 *   missingSince: When reads first saw the record running without the unit,
 *     or null. Browser time on both sides — never the device's clock.
 *
 * Returns:
 *   The phase, and the ``missingSince`` to pass to the next read.
 */
export function assessRun(
  report: RunReport,
  now: number,
  missingSince: number | null,
): { phase: RunPhase; missingSince: number | null } {
  if (report.running) return { phase: 'running', missingSince: null };
  if (report.last?.result !== 'running') return { phase: 'idle', missingSince: null };
  const since = missingSince ?? now;
  return {
    phase: now - since < INTERRUPTED_AFTER_MS ? 'unconfirmed' : 'interrupted',
    missingSince: since,
  };
}

/**
 * When to read the state again.
 *
 * Args:
 *   phase: The phase from the last successful read.
 *   watching: Inside the moment right after a start, when the unit may not
 *     show yet.
 *   failures: Failed reads in a row since the last successful one.
 *
 * Returns:
 *   Milliseconds until the next read, or null to stop polling.
 */
export function nextPollDelay(phase: RunPhase, watching: boolean, failures: number): number | null {
  const active = phase !== 'idle' || watching;
  if (failures > 0) {
    return active ? READ_RETRY_MS[Math.min(failures, READ_RETRY_MS.length) - 1] : null;
  }
  if (phase === 'running' || watching) return POLL_MS;
  if (phase === 'unconfirmed' || phase === 'interrupted') return UNCONFIRMED_POLL_MS;
  return null;
}
