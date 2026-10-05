import { useCallback, useEffect, useState } from 'react';
import type { AxiosError } from 'axios';
import { FaHardDrive, FaDocker, FaBroom, FaArrowsRotate } from 'react-icons/fa6';
import api from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import { SettingsPage, SettingsCard, FormActions, NoticeCallout } from './UISettings/ui';
import { cn } from '@/lib/utils';

interface DockerImage {
  tags: string[];
  size: number;
  in_use: boolean;
}

interface DiskReport {
  root: { total: number; used: number; free: number };
  nodered_backups: { size: number; count: number };
  supported: boolean;
  message?: string;
  images?: DockerImage[] | null;
  journal?: number | null;
  apt_cache?: number | null;
}

type CleanTarget = 'docker' | 'apt';

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function detailOf(err: unknown, fallback: string): string {
  const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
}

/**
 * What fills the controller's disk, and the two clean-ups that are safe.
 *
 * A fixed list rather than a file browser. What grows on `/` is known —
 * Docker images left behind by Node-RED and Caddy updates, the apt cache, the
 * Node-RED backups — and the `boneio` account cannot read most of it, so the
 * sizes come from the system helper. A browser would need that helper to list
 * and delete any path as root, which is the hole the helpers exist to close.
 *
 * The journal is shown but not cleaned: journald caps it at 24 MB.
 */
export default function DiskSection() {
  const { t } = useTranslation();
  const [report, setReport] = useState<DiskReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [cleaning, setCleaning] = useState<CleanTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freed, setFreed] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The helper runs du and docker as root: a few seconds on a BeagleBone.
      const response = await api.get<DiskReport>('/api/diagnostics/disk', { timeout: 120000 });
      setReport(response.data);
    } catch (err) {
      setError(detailOf(err, t('diagnostics.disk_load_failed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const clean = async (target: CleanTarget) => {
    setCleaning(target);
    setError(null);
    setFreed(null);
    try {
      const response = await api.post<{ freed: number }>(
        `/api/diagnostics/disk/clean/${target}`, null, { timeout: 360000 },
      );
      setFreed(t('diagnostics.disk_freed', { size: formatBytes(response.data.freed) }));
      await load();
    } catch (err) {
      setError(detailOf(err, t('diagnostics.disk_clean_failed')));
    } finally {
      setCleaning(null);
    }
  };

  const root = report?.root;
  const usedPct = root ? Math.round((root.used / root.total) * 100) : 0;
  const images = report?.images ?? [];
  const unused = images.filter(image => !image.in_use).reduce((sum, image) => sum + image.size, 0);
  const busy = loading || cleaning !== null;

  return (
    <SettingsPage>
      {error && <NoticeCallout variant="error" message={error} />}
      {freed && <NoticeCallout variant="success" message={freed} />}
      {report && !report.supported && report.message && (
        <NoticeCallout variant="warning" message={report.message} />
      )}

      <SettingsCard
        icon={<FaHardDrive />}
        title={t('diagnostics.disk_root_title')}
        description={t('diagnostics.disk_root_desc')}
        action={
          <button
            className="btn btn-ghost btn-sm gap-2"
            onClick={() => void load()}
            disabled={busy}
            aria-label={t('diagnostics.disk_refresh')}
          >
            <FaArrowsRotate className={cn(loading && 'animate-spin')} />
          </button>
        }
      >
        {root ? (
          <div className="space-y-2">
            <progress
              className={cn(
                'progress w-full',
                usedPct >= 90 ? 'progress-error' : usedPct >= 75 ? 'progress-warning' : 'progress-primary',
              )}
              value={root.used}
              max={root.total}
            />
            <p className="text-[13px] text-base-content/70">
              {t('diagnostics.disk_root_usage', {
                used: formatBytes(root.used),
                total: formatBytes(root.total),
                free: formatBytes(root.free),
                pct: usedPct,
              })}
            </p>
          </div>
        ) : (
          <span className="loading loading-spinner loading-sm" />
        )}
      </SettingsCard>

      {report?.supported && (
        <SettingsCard
          icon={<FaDocker />}
          title={t('diagnostics.disk_images_title')}
          description={t('diagnostics.disk_images_desc')}
          footer={
            <FormActions hint={t('diagnostics.disk_images_unused', { size: formatBytes(unused) })}>
              <button
                className="btn btn-warning btn-sm gap-2"
                onClick={() => void clean('docker')}
                disabled={busy || unused === 0}
              >
                {cleaning === 'docker' ? <span className="loading loading-spinner loading-xs" /> : <FaBroom />}
                {t('diagnostics.disk_images_prune')}
              </button>
            </FormActions>
          }
        >
          {report.images === null ? (
            <p className="text-[13px] text-base-content/60">{t('diagnostics.disk_images_none')}</p>
          ) : (
            <ul className="divide-y divide-base-content/10">
              {images.map((image, index) => (
                <li key={image.tags[0] ?? index} className="flex items-center gap-3 py-2 text-[13px]">
                  <span className="font-mono min-w-0 flex-1 break-all">
                    {image.tags[0] ?? t('diagnostics.disk_image_untagged')}
                  </span>
                  <span
                    className={cn(
                      'badge badge-sm shrink-0',
                      image.in_use ? 'badge-success badge-soft' : 'badge-warning badge-soft',
                    )}
                  >
                    {image.in_use ? t('diagnostics.disk_image_in_use') : t('diagnostics.disk_image_unused')}
                  </span>
                  <span className="tabular-nums text-base-content/70 shrink-0 w-16 text-right">
                    {formatBytes(image.size)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SettingsCard>
      )}

      {report && (
        <SettingsCard
          icon={<FaBroom />}
          title={t('diagnostics.disk_other_title')}
          description={t('diagnostics.disk_other_desc')}
          footer={
            report.supported ? (
              <FormActions>
                <button
                  className="btn btn-outline btn-sm gap-2"
                  onClick={() => void clean('apt')}
                  disabled={busy || !report.apt_cache}
                >
                  {cleaning === 'apt' && <span className="loading loading-spinner loading-xs" />}
                  {t('diagnostics.disk_apt_clean')}
                </button>
              </FormActions>
            ) : undefined
          }
        >
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-[13px]">
            {report.supported && (
              <>
                <dt>{t('diagnostics.disk_apt_cache')}</dt>
                <dd className="tabular-nums text-right">{formatBytes(report.apt_cache ?? 0)}</dd>
                <dt>
                  {t('diagnostics.disk_journal')}
                  <span className="block text-base-content/50 text-[12px]">{t('diagnostics.disk_journal_hint')}</span>
                </dt>
                <dd className="tabular-nums text-right">{formatBytes(report.journal ?? 0)}</dd>
              </>
            )}
            <dt>
              {t('diagnostics.disk_backups')}
              <span className="block text-base-content/50 text-[12px]">
                {t('diagnostics.disk_backups_hint', { count: report.nodered_backups.count })}
              </span>
            </dt>
            <dd className="tabular-nums text-right">{formatBytes(report.nodered_backups.size)}</dd>
          </dl>
        </SettingsCard>
      )}
    </SettingsPage>
  );
}
