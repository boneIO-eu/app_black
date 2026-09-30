import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FaLinux, FaPowerOff, FaSearch, FaSpinner, FaSync } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { useDevicePower } from '../hooks/useDevicePower';
import { SettingsCard, FormActions, NoticeCallout, CodeBlock, StatGrid, ToggleRow } from '../ui';
import { assessRun, nextPollDelay, type RunPhase } from './osUpdateProgress';

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
  /** What ``apt-get clean`` would free; the helper clears it when short. */
  apt_cache_mb?: number;
}

/**
 * How long the panel keeps saying "starting" after the helper accepted a run
 * without the state showing it yet. Past this the state is trusted again.
 */
const START_GRACE_MS = 20_000;

/**
 * Every call here runs the Python system helper through sudo on a BeagleBone:
 * 2-3 s idle and over the axios default of 5 s while an upgrade or a first boot
 * has the CPU. Timing out then showed an error for a request that succeeded.
 */
const HELPER_TIMEOUT = { timeout: 30_000 };

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
  // A failed state read, apart from ``error``: the next good read clears it.
  const [readError, setReadError] = useState<string | null>(null);
  const [phase, setPhase] = useState<RunPhase>('idle');
  // When reads first saw the run's record without its unit; see osUpdateProgress.
  const missingSince = useRef<number | null>(null);
  const failedReads = useRef(0);
  // The run the operator just asked for, from the click until the state shows
  // it. Starting one takes the helper several seconds on a BeagleBone — longer
  // with apt already busy — and without this the card sat unchanged meanwhile.
  const [pendingMode, setPendingMode] = useState<'check' | 'upgrade' | null>(null);
  // ``last.started`` when the button was clicked: the device's own clock, so a
  // new run is told apart without comparing it to the browser's.
  const pendingSince = useRef<number | null>(null);
  const [pollToken, setPollToken] = useState(0);
  const [showPackages, setShowPackages] = useState(false);
  // null follows the run: open while it goes or when it went wrong, folded
  // once it succeeded. The operator's own click wins until the next start.
  const [showLog, setShowLog] = useState<boolean | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The unit is started with --no-block, so the first reads after a start can
  // still see it inactive. Keep polling for a moment instead of stopping there.
  const watchUntil = useRef(0);
  // Reads overlap on a slow device; only the newest may set the state, or a
  // read from before the start lands late and shows the card idle again.
  const readSeq = useRef(0);

  const phaseRef = useRef<RunPhase>('idle');

  // The log is extra: failing to read it must not count as a failed state read.
  const readLog = useCallback(async () => {
    try {
      const { data } = await axios.get<{ log: string }>('/api/os-update/log', HELPER_TIMEOUT);
      setLog(data.log);
    } catch {
      // Keep the log already shown; the next poll tries again.
    }
  }, []);

  const refresh = useCallback(async () => {
    const seq = ++readSeq.current;
    try {
      const { data } = await axios.get<OsUpdateState>('/api/os-update/state', HELPER_TIMEOUT);
      if (seq !== readSeq.current) return data;
      setState(data);
      setReadError(null);
      if (data.running || data.last?.result === 'running') await readLog();
      return data;
    } catch (err) {
      setReadError(apiDetail(err) || t('os_update.state_failed'));
      return null;
    }
  }, [t, readLog]);

  // Poll while a run may be in progress, which includes a record saying it is
  // when the unit briefly does not show, and failed reads mid-run.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const data = await refresh();
      if (cancelled) return;
      const now = Date.now();
      let current = phaseRef.current;
      if (data) {
        failedReads.current = 0;
        const assessed = assessRun(data, now, missingSince.current);
        missingSince.current = assessed.missingSince;
        current = assessed.phase;
        phaseRef.current = current;
        setPhase(current);
      } else {
        failedReads.current += 1;
      }
      const delay = nextPollDelay(current, now < watchUntil.current, failedReads.current);
      if (delay !== null) {
        timer.current = setTimeout(tick, delay);
      } else if (data?.last) {
        // One last read, so the finished run's log is on screen.
        await readLog();
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [refresh, readLog, pollToken]);

  // The state has caught up with the click: the run shows, or already finished.
  useEffect(() => {
    if (!pendingMode || !state) return;
    if (state.running || (state.last?.started ?? null) !== pendingSince.current) {
      setPendingMode(null);
    }
  }, [state, pendingMode]);

  const [switching, setSwitching] = useState(false);
  const setAutoUpdate = async (enabled: boolean) => {
    setError(null);
    setSwitching(true);
    try {
      await axios.post('/api/os-update/autoupdate', { enabled }, HELPER_TIMEOUT);
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
    pendingSince.current = state?.last?.started ?? null;
    setPendingMode(mode);
    try {
      await axios.post(`/api/os-update/${mode}`, null, HELPER_TIMEOUT);
      watchUntil.current = Date.now() + 15000;
      // A new run: an older record's grace period does not carry over to it.
      missingSince.current = null;
      setShowLog(null);
      // Re-arms the polling effect for the run just started.
      setPollToken(n => n + 1);
      setTimeout(() => setPendingMode(current => (current === mode ? null : current)), START_GRACE_MS);
    } catch (err) {
      setPendingMode(null);
      setError(apiDetail(err) || t('os_update.start_failed'));
    }
  };

  if (state && !state.supported) {
    return (
      <SettingsCard icon={<FaLinux />} title={t('os_update.title')}>
        <NoticeCallout variant="info" message={t('os_update.unsupported')} />
      </SettingsCard>
    );
  }

  // "Unconfirmed" still counts as running: the record says so and the unit only
  // failed to show, which happens while dpkg replaces systemd.
  const running = phase === 'running' || phase === 'unconfirmed';
  const interrupted = phase === 'interrupted';
  const last = state?.last ?? null;
  const busy = running || pendingMode !== null;
  const activeMode = pendingMode ?? (running ? last?.mode ?? null : null);
  // A disabled daisyUI button fades to near nothing; the one doing the work
  // stays readable, so the card looks busy rather than broken.
  const activeButton = 'disabled:text-base-content/70 disabled:border-base-content/20';
  const packages = last?.packages ?? [];
  const kernelProblem = state?.kernel?.status === 'problem';
  // The threshold is for starting a run; during one apt uses the space itself.
  const shortOfSpace =
    !busy && state?.free_mb !== undefined && state.min_free_mb !== undefined && state.free_mb < state.min_free_mb;
  const aptCache = state?.apt_cache_mb ?? 0;
  const lowSpace = shortOfSpace && (state?.free_mb ?? 0) + aptCache < (state?.min_free_mb ?? 0);
  const clearsCache = shortOfSpace && !lowSpace;
  const upgradeDone = !busy && last?.mode === 'upgrade' && last.result === 'success';
  const formatTime = (ts?: number | null) => (ts ? new Date(ts * 1000).toLocaleString() : '—');
  const pending = pendingPackages(state);
  const [estimateLow, estimateHigh] = estimateMinutes(pending?.length ?? 0);
  const kernelPending = Boolean(pending?.some(p => p.name.startsWith('linux-image')));
  // A successful run's log is kept for after the restart, when something may
  // turn out wrong, but folded: its last line still names the kernel from
  // before it, next to a tile that shows the new one.
  const logWorthShowing =
    running ||
    interrupted ||
    last?.result === 'failed' ||
    last?.result === 'problem' ||
    last?.kernel?.status === 'problem';
  const logOpen = showLog ?? logWorthShowing;

  return (
    <SettingsCard
      icon={<FaLinux />}
      title={t('os_update.title')}
      description={t('os_update.description')}
      action={
        busy ? (
          <span className="badge badge-info badge-sm gap-1">
            <FaSpinner className="animate-spin" />
            {pendingMode && !running ? t('os_update.starting') : t('os_update.running')}
          </span>
        ) : interrupted ? (
          <span className="badge badge-error badge-sm font-semibold">{t('os_update.interrupted_badge')}</span>
        ) : packages.length > 0 && last?.mode === 'check' ? (
          <span className="badge badge-success badge-sm font-semibold">
            {t('os_update.available', { count: packages.length })}
          </span>
        ) : null
      }
      footer={
        <FormActions>
          <button
            className={`btn btn-outline btn-sm gap-2 ${activeMode === 'check' ? activeButton : ''}`}
            onClick={() => start('check')}
            // A check would overwrite the interrupted run's record and log;
            // only an upgrade finishes what it left half-installed.
            disabled={busy || !state || interrupted}
          >
            {activeMode === 'check' ? <FaSpinner className="text-xs animate-spin" /> : <FaSearch className="text-xs" />}
            {activeMode === 'check' ? t('os_update.checking') : t('os_update.check')}
          </button>
          <button
            className={`btn btn-primary btn-sm gap-2 ${activeMode === 'upgrade' ? activeButton : ''}`}
            onClick={() => start('upgrade')}
            disabled={busy || !state || lowSpace}
          >
            {activeMode === 'upgrade' ? <FaSpinner className="text-xs animate-spin" /> : <FaSync className="text-xs" />}
            {activeMode === 'upgrade' ? t('os_update.upgrading') : t('os_update.upgrade')}
          </button>
        </FormActions>
      }
    >
      <div className="space-y-4">
        {(error || readError) && <NoticeCallout variant="error" message={error || readError || ''} />}

        {interrupted && (
          <NoticeCallout
            variant="error"
            title={t('os_update.interrupted_title')}
            message={
              <>
                <p>{t('os_update.interrupted', { step: last?.step ?? '—' })}</p>
                <p className="mt-1">{t('os_update.interrupted_hint')}</p>
              </>
            }
          />
        )}

        {kernelProblem && (
          <NoticeCallout
            variant="error"
            title={t('os_update.kernel_problem_title')}
            message={`${t('os_update.kernel_problem')} ${state?.kernel?.message ?? ''}`}
          />
        )}

        {upgradeDone && (
          <NoticeCallout
            variant="success"
            message={
              <>
                <p>{t('os_update.upgrade_done', { when: formatTime(last?.finished), count: packages.length })}</p>
                {state?.reboot_required && <p className="mt-1">{t('os_update.upgrade_done_reboot')}</p>}
              </>
            }
          />
        )}

        {/* Mid-run the reasons are half-known: the kernel check comes last and
            may still say not to restart. */}
        {state?.reboot_required && !kernelProblem && !running && (
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
                disabled={isRebooting || running || interrupted}
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

        {clearsCache && (
          <NoticeCallout
            variant="info"
            message={t('os_update.low_space_cache', {
              free: state?.free_mb ?? 0,
              needed: state?.min_free_mb ?? 0,
              cache: aptCache,
            })}
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
              value: !last
                ? '—'
                : last.finished
                  ? `${t(`os_update.mode_${last.mode}`)} · ${formatTime(last.finished)}`
                  : `${t(`os_update.mode_${last.mode}`)} · ${t('os_update.started_at', { when: formatTime(last.started) })}`,
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
          <div>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => setShowLog(!logOpen)}>
              {logOpen ? '▾' : '▸'}{' '}
              {running && last?.step ? `${t('os_update.log')} — ${last.step}` : t('os_update.last_log')}
            </button>
            {logOpen && (
              <CodeBlock className="mt-2" maxHeight="14rem">
                {log}
              </CodeBlock>
            )}
          </div>
        )}
      </div>
    </SettingsCard>
  );
};

export default OsUpdateCard;
