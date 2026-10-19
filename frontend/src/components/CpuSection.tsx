import { useCallback, useEffect, useState } from 'react';
import type { AxiosError } from 'axios';
import { FaMicrochip, FaArrowsRotate, FaListUl, FaMagnifyingGlass } from 'react-icons/fa6';
import api from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import { SettingsPage, SettingsCard, FormActions, NoticeCallout } from './UISettings/ui';
import { cn } from '@/lib/utils';
import { cpuSummary, type CpuReport } from './cpuSummary';

interface BoneioReport {
  threads: { native_id: number; name: string; percent: number }[];
  hot_thread: string | null;
  stacks: { stack: string; count: number }[];
  tasks: { name: string; count: number }[];
}

const BREAKDOWN = ['user', 'system', 'iowait', 'irq', 'softirq'] as const;

function detailOf(err: unknown, fallback: string): string {
  const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
}

/**
 * What holds the processor, for the owner whose CPU sensor shows 100%.
 *
 * Measured on request, never in the background: a process scan costs about
 * 300 ms of CPU on a BeagleBone. The boneIO details — threads and the code the
 * busiest one was seen in — are for support and load only when asked for.
 */
export default function CpuSection() {
  const { t } = useTranslation();
  const [report, setReport] = useState<CpuReport | null>(null);
  const [boneio, setBoneio] = useState<BoneioReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get<CpuReport>('/api/diagnostics/cpu', { timeout: 30000 });
      setReport(response.data);
    } catch (err) {
      setError(detailOf(err, t('diagnostics.cpu_load_failed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // Measuring on entry is the point of the section; load sets state only
    // after the request, the spinner flag aside.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const explain = async () => {
    setExplaining(true);
    setError(null);
    try {
      const response = await api.get<BoneioReport>('/api/diagnostics/cpu/boneio', { timeout: 30000 });
      setBoneio(response.data);
    } catch (err) {
      setError(detailOf(err, t('diagnostics.cpu_load_failed')));
    } finally {
      setExplaining(false);
    }
  };

  const summary = report ? cpuSummary(report) : null;
  const headline =
    summary?.kind === 'service'
      ? t('diagnostics.cpu_headline_service', { label: summary.label, pct: Math.round(summary.percent) })
      : summary?.kind === 'interrupts'
        ? t('diagnostics.cpu_headline_interrupts')
        : t('diagnostics.cpu_headline_idle');

  return (
    <SettingsPage>
      {error && <NoticeCallout variant="error" message={error} />}

      <SettingsCard
        icon={<FaMicrochip />}
        title={t('diagnostics.cpu_now_title')}
        description={t('diagnostics.cpu_now_desc')}
        action={
          <button
            className="btn btn-ghost btn-sm gap-2"
            onClick={() => void load()}
            disabled={loading}
            aria-label={t('diagnostics.cpu_refresh')}
          >
            <FaArrowsRotate className={cn(loading && 'animate-spin')} />
          </button>
        }
      >
        {report ? (
          <div className="space-y-3">
            <NoticeCallout
              variant={summary?.kind === 'idle' ? 'success' : 'warning'}
              message={headline}
            />
            <progress
              className={cn(
                'progress w-full',
                report.busy >= 90 ? 'progress-error' : report.busy >= 50 ? 'progress-warning' : 'progress-primary',
              )}
              value={report.busy}
              max={100}
            />
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-[13px]">
              {BREAKDOWN.map(field => (
                <div key={field} className="contents">
                  <dt>{t(`diagnostics.cpu_${field}`)}</dt>
                  <dd className="tabular-nums text-right">{report.breakdown[field].toFixed(1)}%</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : (
          <span className="loading loading-spinner loading-sm" />
        )}
      </SettingsCard>

      {report && (
        <SettingsCard
          icon={<FaListUl />}
          title={t('diagnostics.cpu_services_title')}
          description={t('diagnostics.cpu_services_desc')}
        >
          {report.services.length === 0 ? (
            <p className="text-[13px] text-base-content/60">{t('diagnostics.cpu_services_none')}</p>
          ) : (
            <ul className="divide-y divide-base-content/10">
              {report.services.map(service => (
                <li key={service.label} className="flex items-center gap-3 py-2 text-[13px]">
                  <span className="font-mono min-w-0 flex-1 break-all">{service.label}</span>
                  <span className="tabular-nums text-base-content/70 shrink-0 w-16 text-right">
                    {service.percent.toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
          {report.processes.length > 0 && (
            <details className="mt-3 text-[13px]">
              <summary className="cursor-pointer text-base-content/70">{t('diagnostics.cpu_processes')}</summary>
              <table className="table table-xs mt-2">
                <tbody>
                  {report.processes.map(process => (
                    <tr key={process.pid}>
                      <td className="tabular-nums">{process.pid}</td>
                      <td className="font-mono break-all">{process.name}</td>
                      <td className="font-mono break-all text-base-content/60">{process.label}</td>
                      <td className="tabular-nums text-right">{process.percent.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </SettingsCard>
      )}

      <SettingsCard
        icon={<FaMagnifyingGlass />}
        title={t('diagnostics.cpu_boneio_title')}
        description={t('diagnostics.cpu_boneio_desc')}
        footer={
          <FormActions>
            <button className="btn btn-outline btn-sm gap-2" onClick={() => void explain()} disabled={explaining}>
              {explaining && <span className="loading loading-spinner loading-xs" />}
              {t('diagnostics.cpu_boneio_run')}
            </button>
          </FormActions>
        }
      >
        {boneio && (
          <div className="space-y-3 text-[13px]">
            <ul className="divide-y divide-base-content/10">
              {boneio.threads.filter(thread => thread.percent > 0).map(thread => (
                <li key={thread.native_id} className="flex items-center gap-3 py-1.5">
                  <span className="font-mono min-w-0 flex-1 break-all">{thread.name}</span>
                  <span className="tabular-nums text-base-content/70 shrink-0 w-16 text-right">
                    {thread.percent.toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
            {boneio.stacks.length > 0 && (
              <div>
                <p className="text-base-content/70 mb-1">
                  {t('diagnostics.cpu_boneio_stacks', { thread: boneio.hot_thread ?? '' })}
                </p>
                {boneio.stacks.slice(0, 3).map(stack => (
                  <pre key={stack.stack} className="bg-base-200 rounded p-2 overflow-x-auto text-[12px] mb-2">
                    {`${stack.count}×\n${stack.stack}`}
                  </pre>
                ))}
              </div>
            )}
            {boneio.tasks.length > 0 && (
              <details>
                <summary className="cursor-pointer text-base-content/70">{t('diagnostics.cpu_boneio_tasks')}</summary>
                <ul className="mt-1 font-mono text-[12px]">
                  {boneio.tasks.map(task => (
                    <li key={task.name}>{task.count} × {task.name}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </SettingsCard>
    </SettingsPage>
  );
}
