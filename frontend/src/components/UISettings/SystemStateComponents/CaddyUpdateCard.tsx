import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FaLock, FaSpinner, FaSync } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { SettingsCard, FormActions, NoticeCallout, StatGrid } from '../ui';

interface CaddyTask {
  status: 'idle' | 'running' | 'success' | 'failed';
  started: number | null;
  finished: number | null;
  message: string | null;
}

interface CaddyState {
  supported: boolean;
  pinned?: string;
  configured?: string | null;
  update_available?: boolean;
  task: CaddyTask;
}

const POLL_MS = 3000;

/** ``caddy:2.11.4-alpine@sha256:…`` → ``2.11.4-alpine``. */
function version(image?: string | null): string {
  if (!image) return '—';
  return image.replace(/^caddy:/, '').replace(/@sha256:.*/, '');
}

/**
 * Caddy serves the panel over HTTPS. It sat on ``caddy:2-alpine`` — whatever
 * that meant the day an image was built — so each boneIO release now pins an
 * exact version, and this moves the controller to it. The operator does not
 * pick a version; they pick the moment, because recreating Caddy drops the
 * HTTPS panel for a few seconds — very likely the connection this page came
 * through, so polling carries on through the gap.
 */
export const CaddyUpdateCard: React.FC = () => {
  const { t } = useTranslation();
  const [state, setState] = useState<CaddyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [kick, setKick] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get<CaddyState>('/api/os-update/caddy');
      setState(data);
      return data;
    } catch {
      // Expected while Caddy is being recreated: keep polling.
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const data = await refresh();
      if (!cancelled && (data === null ? kick > 0 : data.task.status === 'running')) {
        timer.current = setTimeout(tick, POLL_MS);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [refresh, kick]);

  const apply = async () => {
    if (!confirm(t('caddy_update.confirm'))) return;
    setError(null);
    try {
      await axios.post('/api/os-update/caddy/apply');
      setKick(k => k + 1);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('caddy_update.failed'));
    }
  };

  if (!state || !state.supported) return null;
  const running = state.task.status === 'running';

  return (
    <SettingsCard
      icon={<FaLock />}
      title={t('caddy_update.title')}
      description={t('caddy_update.description')}
      action={
        running ? (
          <span className="badge badge-info badge-sm gap-1">
            <FaSpinner className="animate-spin" />
            {t('caddy_update.running')}
          </span>
        ) : state.update_available ? (
          <span className="badge badge-success badge-sm font-semibold">
            {t('caddy_update.available')}
          </span>
        ) : null
      }
      footer={
        state.update_available || running ? (
          <FormActions>
            <button className="btn btn-primary btn-sm gap-2" onClick={apply} disabled={running}>
              <FaSync className="text-xs" />
              {t('caddy_update.apply', { version: version(state.pinned) })}
            </button>
          </FormActions>
        ) : undefined
      }
    >
      <div className="space-y-4">
        {error && <NoticeCallout variant="error" message={error} />}
        {running && <NoticeCallout variant="info" message={t('caddy_update.running_hint')} />}
        {state.task.status === 'failed' && (
          <NoticeCallout variant="error" message={`${t('caddy_update.failed')} ${state.task.message ?? ''}`} />
        )}
        {state.task.status === 'success' && !state.update_available && (
          <NoticeCallout variant="success" message={t('caddy_update.done')} />
        )}
        {state.update_available && !running && (
          <NoticeCallout variant="warning" message={t('caddy_update.interruption')} />
        )}
        <StatGrid
          columns={2}
          items={[
            { label: t('caddy_update.current'), mono: true, value: version(state.configured) },
            { label: t('caddy_update.release'), mono: true, value: version(state.pinned) },
          ]}
        />
      </div>
    </SettingsCard>
  );
};

export default CaddyUpdateCard;
