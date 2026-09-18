import { useCallback, useEffect, useState } from 'react';
import {
  fetchMigrationStatus,
  invalidateMigrationStatus,
} from '@/api/migrationStatusCache';

/**
 * Status of a single pending migration.
 */
export interface PendingMigration {
  version: string;
  description: string;
}

/**
 * Status of a single applied migration.
 */
export interface AppliedMigration {
  version: string;
  description: string;
  module_name: string;
}

/**
 * Full migration status returned by /api/migrations/status.
 */
export interface MigrationStatus {
  status: 'ok' | 'bootstrap_required' | 'pending' | 'error';
  bootstrap_required: boolean;
  helper_installed: boolean;
  pending_count: number;
  pending: PendingMigration[];
  applied: AppliedMigration[];
  last_error: string | null;
}

/**
 * Hook to fetch system migration status from the backend.
 *
 * Reads through the shared cache in migrationStatusCache, so the components
 * that want the status on the same screen — the banner Layout puts above every
 * page and the migrations section itself — cost one request between them
 * rather than one each. The burst that mattered was at startup: the banner
 * mounts, the app settles its init and auth state and mounts it again, and
 * StrictMode doubles both, which measured as four requests inside the first
 * 600 ms of a page load.
 *
 * Polls so the banner disappears on its own once bootstrap is done or pending
 * migrations are applied from somewhere else. The poll still reaches the
 * device: the cache's freshness window is deliberately shorter than the
 * shortest interval asked for here.
 */
export function useMigrations(pollIntervalMs: number = 10000) {
  const [status, setStatus] = useState<MigrationStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Read the status, through the cache unless `force` says otherwise.
   *
   * `force` is what `refresh` passes. After bootstrapping the helper or
   * applying migrations, a cached answer is the one from before the thing the
   * user just did — so those paths have to reach the device.
   */
  const load = useCallback(async (force: boolean) => {
    if (force) invalidateMigrationStatus();
    try {
      const data = await fetchMigrationStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : null;
      setError(message || 'Failed to fetch migration status');
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(() => load(true), [load]);

  useEffect(() => {
    // Fetching on mount is the external-system synchronisation this rule is
    // meant to permit. It fires anyway because it cannot see that every
    // setState in `load` happens after an await, so there is no cascade to
    // avoid. Same false positive as in useSecurityPosture.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(false);
    if (pollIntervalMs > 0) {
      const id = setInterval(() => void load(false), pollIntervalMs);
      return () => clearInterval(id);
    }
  }, [load, pollIntervalMs]);

  return { status, loading, error, refresh };
}
