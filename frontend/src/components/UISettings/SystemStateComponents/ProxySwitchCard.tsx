import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FaExchangeAlt, FaSpinner, FaSync } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { SettingsCard, FormActions, NoticeCallout, StatGrid } from '../ui';

interface SwitchRecord {
  state: 'running' | 'done' | 'failed' | 'rolled_back' | null;
  step: string | null;
  error: string | null;
  attempts: number;
  running: boolean;
  log: string;
}

interface ProxyState {
  supported: boolean;
  mode?: 'container' | 'native';
  installed?: string | null;
  candidate?: string | null;
  switch?: SwitchRecord | null;
}

const POLL_MS = 5000;

/**
 * Where Caddy, which serves the panel over HTTPS, runs: as a container, or as
 * the system service. The controller moves itself a few minutes after start
 * (up to three runs); this shows how that went and lets an administrator ask
 * again. The switch recreates Caddy, so the panel drops for a moment and
 * polling carries on through the gap.
 */
export const ProxySwitchCard: React.FC = () => {
  const { t } = useTranslation();
  const [state, setState] = useState<ProxyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [kick, setKick] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get<ProxyState>('/api/proxy/state', { timeout: 30_000 });
      setState(data);
      return data;
    } catch {
      return null; // Expected while Caddy is being switched.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const data = await refresh();
      if (!cancelled && (data === null ? kick > 0 : data.switch?.running === true)) {
        timer.current = setTimeout(tick, POLL_MS);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [refresh, kick]);

  const start = async () => {
    if (!confirm(t('proxy_switch.confirm'))) return;
    setError(null);
    try {
      await axios.post('/api/proxy/switch', null, { timeout: 30_000 });
      setKick(k => k + 1);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('proxy_switch.start_failed'));
    }
  };

  if (!state || !state.supported) return null;
  const record = state.switch;
  const running = record?.running === true;
  const native = state.mode === 'native';
  const failed = record?.state === 'failed' || record?.state === 'rolled_back';

  return (
    <SettingsCard
      icon={<FaExchangeAlt />}
      title={t('proxy_switch.title')}
      description={t('proxy_switch.description')}
      action={
        running ? (
          <span className="badge badge-info badge-sm gap-1">
            <FaSpinner className="animate-spin" />
            {t('proxy_switch.running')}
          </span>
        ) : null
      }
      footer={
        !native ? (
          <FormActions>
            <button className="btn btn-primary btn-sm gap-2" onClick={start} disabled={running}>
              <FaSync className="text-xs" />
              {failed ? t('proxy_switch.retry') : t('proxy_switch.start')}
            </button>
          </FormActions>
        ) : undefined
      }
    >
      <div className="space-y-4">
        {error && <NoticeCallout variant="error" message={error} />}
        {running && <NoticeCallout variant="info" message={t('proxy_switch.running_hint')} />}
        {failed && !running && (
          <NoticeCallout
            variant="error"
            message={`${t(`proxy_switch.state_${record?.state}`)} ${record?.error ?? ''}`}
          />
        )}
        <StatGrid
          columns={2}
          items={[
            {
              label: t('proxy_switch.mode'),
              value: native ? t('proxy_switch.mode_native') : t('proxy_switch.mode_container'),
            },
            native
              ? { label: t('proxy_switch.version'), mono: true, value: state.installed ?? '—' }
              : {
                  label: t('proxy_switch.attempts'),
                  mono: true,
                  value: `${record?.attempts ?? 0}/3`,
                },
          ]}
        />
        {record?.log && (
          <div>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => setShowLog(!showLog)}>
              {showLog ? '▾' : '▸'} {t('proxy_switch.log')}
            </button>
            {showLog && (
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-base-200 p-2 text-xs">{record.log}</pre>
            )}
          </div>
        )}
      </div>
    </SettingsCard>
  );
};

export default ProxySwitchCard;
