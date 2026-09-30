import { useEffect, useState } from 'react';
import { fetchConfig } from '@/api/configCache';
import type { AreaEntity } from '@/types/config';

/**
 * The configured areas, from the shared config cache.
 *
 * Empty until the config arrives, and empty on a device with no areas — the
 * dashboards read both the same way: nothing to group by.
 */
export function useAreas(): AreaEntity[] {
  const [areas, setAreas] = useState<AreaEntity[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchConfig().then((response) => {
      if (cancelled) return;
      const config = (response as { config?: { areas?: unknown } }).config;
      const list = Array.isArray(config?.areas) ? (config.areas as AreaEntity[]) : [];
      setAreas(list.filter((a) => a && typeof a.id === 'string'));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return areas;
}
