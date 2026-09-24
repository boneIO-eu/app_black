import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FaLinux, FaPowerOff, FaSearch, FaSpinner, FaSync } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { useDevicePower } from '../hooks/useDevicePower';
import { SettingsCard, FormActions, NoticeCallout, CodeBlock, StatGrid, ToggleRow } from '../ui';

interface OsPackage {
  name: string;
  from: string | null;
  to: string;
}

interface KernelReport {
  status: 'ok' | 'repaired' | 'problem';
  kernel: string | null;
  running: string;
  message: string | null;
}

interface OsUpdateRun {
  mode: 'check' | 'upgrade';
  started: number;
  finished: number | null;
  result: 'running' | 'success' | 'failed' | 'problem';
  step: string | null;
  message: string | null;
  packages: OsPackage[];
  kernel: KernelReport | null;
}

interface AutoUpdateState {
  installed: boolean;
  configured: boolean;
  enabled: boolean;
  last_run: string | null;
  last_packages_at: string | null;
  last_packages: string[];
}

interface OsUpdateState {
  supported: boolean;
  autoupdate?: AutoUpdateState;
  message?: string;
  running?: boolean;
  last?: OsUpdateRun | null;
  reboot_required?: boolean;
  reboot_reasons?: string[];
  kernel?: KernelReport;
  free_mb?: number;
  min_free_mb?: number;
}

const POLL_MS = 3000;

/**
 * Seconds per package on a BeagleBone, measured on the dev controller
 * (2026-09-24): 161 packages — a new kernel, systemd, OpenSSH, python3.13,
 * docker.io — took 1770 s from apt-get update to the kernel check, most of it
 * dpkg configuring one package after another. The shown range runs to 1.5x
 * that, because a kernel's initramfs rebuild alone takes minutes.
 */
const SECONDS_PER_PACKAGE = 11;

/** What a check found still to install, or null when no check has run since. */
function pendingPackages(state: OsUpdateState | null): OsPackage[] | null {
  const last = state?.last;
  return last && last.mode === 'check' && last.result === 'success' ? last.packages : null;
}

/** Rough duration of an upgrade, as a [low, high] range in minutes. */
function estimateMinutes(count: number): [number, number] {
  const low = Math.max(5, Math.ceil((count * SECONDS_PER_PACKAGE) / 60));
  return [low, Math.ceil(low * 1.5)];
}

/** The API's ``detail``, when the request got that far. */
function apiDetail(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : undefined;
}

/**
 * The operating system under boneIO: Debian packages and the kernel.
 *
 * Updating boneIO never touched these, so a controller shipped a year ago was
 * stuck on what it left the factory with. The panel only asks for a check or
 * an upgrade; the helper decides everything apt does. The device never
 * restarts by itself — when a restart is needed this card says so and why, and
 * refuses to offer it when the kernel the next boot would load is not ready.
 */
export const OsUpdateCard: React.FC = () => {
  const { t } = useTranslation();
  const { isRebooting, rebootResult, rebootDevice } = useDevicePower();
  const [state, setState] = useState<OsUpdateState | null>(null);
  const [log, setLog] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [showPackages, setShowPackages] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The unit is started with --no-block, so the first reads after a start can
  // still see it inactive. Keep polling for a moment instead of stopping there.
  const watchUntil = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get<OsUpdateState>('/api/os-update/state');
      setState(data);
      if (data.running || data.last?.result === 'running') {
        const { data: logData } = await axios.get<{ log: string }>('/api/os-update/log');
        setLog(logData.log);
      }
      return data;
    } catch (err) {
      setError(apiDetail(err) || t('os_update.state_failed'));
      return null;
    }
  }, [t]);

  // Poll while a run is in progress; stop as soon as it is not.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const data = await refresh();
      if (!cancelled && (data?.running || Date.now() < watchUntil.current)) {
        timer.current = setTimeout(tick, POLL_MS);
      } else if (!cancelled && data?.last) {
        // One last read, so the finished run's log is on screen.
        const { data: logData } = await axios.get<{ log: string }>('/api/os-update/log');
        if (!cancelled) setLog(logData.log);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [refresh, starting]);

  const [switching, setSwitching] = useState(false);
  const setAutoUpdate = async (enabled: boolean) => {
    setError(null);
    setSwitching(true);
    try {
      await axios.post('/api/os-update/autoupdate', { enabled });
      await refresh();
    } catch (err) {
      setError(apiDetail(err) || t('os_update.autoupdate_failed'));
    } finally {
      setSwitching(false);
    }
  };

  const start = async (mode: 'check' | 'upgrade') => {
    if (mode === 'upgrade') {
      const pending = pendingPackages(state);
      const message = pending
        ? t('os_update.confirm_upgrade_known', {
            count: pending.length,
            min: estimateMinutes(pending.length)[0],
            max: estimateMinutes(pending.length)[1],
          })
        : t('os_update.confirm_upgrade_unknown');
      if (!confirm(`${message}\n\n${t('os_update.interruptions')}\n\n${t('os_update.confirm_backup')}`)) return;
    }
    setError(null);
    setStarting(true);
    try {
      await axios.post(`/api/os-update/${mode}`);
      watchUntil.current = Date.now() + 15000;
    } catch (err) {
      setError(apiDetail(err) || t('os_update.start_failed'));
    } finally {
      // Toggling re-arms the polling effect for the run just started.
      setStarting(false);
    }
  };

  if (state && !state.supported) {
    return (
      <SettingsCard icon={<FaLinux />} title={t('os_update.title')}>
        <NoticeCallout variant="info" message={t('os_update.unsupported')} />
      </SettingsCard>
    );
  }

  const running = Boolean(state?.running);
  const last = state?.last ?? null;
  const packages = last?.packages ?? [];
  const kernelProblem = state?.kernel?.status === 'problem';
  const lowSpace =
    state?.free_mb !== undefined && state.min_free_mb !== undefined && state.free_mb < state.min_free_mb;
  const formatTime = (ts?: number | null) => (ts ? new Date(ts * 1000).toLocaleString() : '—');
  const pending = pendingPackages(state);
  const [estimateLow, estimateHigh] = estimateMinutes(pending?.length ?? 0);
  const kernelPending = Boolean(pending?.some(p => p.name.startsWith('linux-image')));

  return (
    <SettingsCard
      icon={<FaLinux />}
      title={t('os_update.title')}
      description={t('os_update.description')}
      action={
        running ? (
          <span className="badge badge-info badge-sm gap-1">
            <FaSpinner className="animate-spin" />
            {t('os_update.running')}
          </span>
        ) : packages.length > 0 && last?.mode === 'check' ? (
          <span className="badge badge-success badge-sm font-semibold">
            {t('os_update.available', { count: packages.length })}
          </span>
        ) : null
      }
      footer={
        <FormActions>
          <button
            className="btn btn-ghost btn-sm gap-2"
            onClick={() => start('check')}
            disabled={running || starting || !state}
          >
            <FaSearch className="text-xs" />
            {t('os_update.check')}
          </button>
          <button
            className="btn btn-primary btn-sm gap-2"
            onClick={() => start('upgrade')}
            disabled={running || starting || !state || lowSpace}
          >
            <FaSync className="text-xs" />
            {t('os_update.upgrade')}
          </button>
        </FormActions>
      }
    >
      <div className="space-y-4">
        {error && <NoticeCallout variant="error" message={error} />}

        {kernelProblem && (
          <NoticeCallout
            variant="error"
            title={t('os_update.kernel_problem_title')}
            message={`${t('os_update.kernel_problem')} ${state?.kernel?.message ?? ''}`}
          />
        )}

        {state?.reboot_required && !kernelProblem && (
          <NoticeCallout
            variant="warning"
            title={t('os_update.reboot_required')}
            message={
              <>
                <p>{t('os_update.reboot_required_hint')}</p>
                {state.reboot_reasons && state.reboot_reasons.length > 0 && (
                  <p className="font-mono text-xs mt-1">{state.reboot_reasons.join(' · ')}</p>
                )}
                {rebootResult && <p className="mt-1">{rebootResult.message}</p>}
              </>
            }
            action={
              <button
                className="btn btn-warning btn-sm gap-2"
                onClick={rebootDevice}
                disabled={isRebooting || running}
              >
                {isRebooting ? <FaSpinner className="animate-spin" /> : <FaPowerOff />}
                {t('os_update.reboot_now')}
              </button>
            }
          />
        )}

        {running && last?.mode === 'upgrade' && (
          <NoticeCallout variant="info" message={t('os_update.interruptions_now')} />
        )}

        {!running && pending && pending.length > 0 && (
          <NoticeCallout
            variant="warning"
            title={t('os_update.estimate', {
              count: pending.length,
              min: estimateLow,
              max: estimateHigh,
            })}
            message={
              <>
                <p>{t('os_update.interruptions')}</p>
                {kernelPending && <p className="mt-1">{t('os_update.kernel_pending')}</p>}
              </>
            }
          />
        )}

        {lowSpace && (
          <NoticeCallout
            variant="warning"
            message={t('os_update.low_space', { free: state?.free_mb ?? 0, needed: state?.min_free_mb ?? 0 })}
          />
        )}

        {last?.result === 'failed' && !running && (
          <NoticeCallout variant="error" message={`${t('os_update.failed')} ${last.message ?? ''}`} />
        )}

        {last?.kernel?.status === 'repaired' && (
          <NoticeCallout variant="info" message={`${t('os_update.kernel_repaired')} ${last.kernel.message ?? ''}`} />
        )}

        {state?.autoupdate?.configured && (
          <ToggleRow
            checked={state.autoupdate.enabled}
            onChange={setAutoUpdate}
            busy={switching}
            disabled={switching || !state.autoupdate.installed}
            label={t('os_update.autoupdate')}
            description={
              <>
                {t('os_update.autoupdate_hint')}
                {state.autoupdate.last_run && (
                  <span className="block mt-1 font-mono text-xs">
                    {t('os_update.autoupdate_last_run', { when: state.autoupdate.last_run })}
                    {state.autoupdate.last_packages.length > 0 &&
                      ` · ${t('os_update.autoupdate_last_packages', {
                        when: state.autoupdate.last_packages_at ?? '',
                        packages: state.autoupdate.last_packages.join(', '),
                      })}`}
                  </span>
                )}
              </>
            }
          />
        )}

        <StatGrid
          columns={3}
          items={[
            {
              label: t('os_update.last_run'),
              value: last ? `${t(`os_update.mode_${last.mode}`)} · ${formatTime(last.finished ?? last.started)}` : '—',
            },
            {
              label: t('os_update.kernel'),
              mono: true,
              value: state?.kernel?.running ?? '—',
            },
            {
              label: t('os_update.free_space'),
              mono: true,
              value: state?.free_mb !== undefined ? `${state.free_mb} MB` : '—',
            },
          ]}
        />

        {last && last.mode === 'check' && last.result === 'success' && packages.length === 0 && (
          <NoticeCallout variant="success" message={t('os_update.up_to_date')} />
        )}

        {packages.length > 0 && (
          <div>
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              onClick={() => setShowPackages(v => !v)}
            >
              {showPackages ? '▾' : '▸'}{' '}
              {last?.mode === 'upgrade'
                ? t('os_update.installed_packages', { count: packages.length })
                : t('os_update.pending_packages', { count: packages.length })}
            </button>
            {showPackages && (
              <div className="stg-inset overflow-x-auto mt-2 max-h-64">
                <table className="table table-xs">
                  <tbody>
                    {packages.map(p => (
                      <tr key={p.name}>
                        <td className="font-mono">{p.name}</td>
                        <td className="font-mono text-base-content/60">{p.from ?? t('os_update.new_package')}</td>
                        <td className="font-mono">{p.to}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {log && (running || last) && (
          <CodeBlock label={running && last?.step ? `${t('os_update.log')} — ${last.step}` : t('os_update.log')} maxHeight="14rem">
            {log}
          </CodeBlock>
        )}
      </div>
    </SettingsCard>
  );
};

export default OsUpdateCard;
