import { useCallback, useEffect, useState } from 'react';
import axios from '@/api/axios';

/**
 * Status of a single pending migration.
 */
export interface PendingMigration {
  version: string;
  description: string;
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
  applied: string[];
  last_error: string | null;
}

/**
 * Hook to fetch system migration status from the backend.
 *
 * Polls every 10s so the banner disappears automatically once the user
 * completes bootstrap or applies pending migrations elsewhere.
 */
export function useMigrations(pollIntervalMs: number = 10000) {
  const [status, setStatus] = useState<MigrationStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await axios.get<MigrationStatus>('/api/migrations/status');
      setStatus(data);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch migration status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    if (pollIntervalMs > 0) {
      const id = setInterval(fetchStatus, pollIntervalMs);
      return () => clearInterval(id);
    }
  }, [fetchStatus, pollIntervalMs]);

  return { status, loading, error, refresh: fetchStatus };
}
