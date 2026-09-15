import { useCallback, useEffect, useState } from 'react';
import type { AxiosError } from 'axios';
import api from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';

/**
 * A support bundle the owner can send, and the capture window that makes it
 * worth reading.
 *
 * Warranty diagnosis otherwise means giving the vendor a shell on a device in
 * someone's home, which is a permanent credential in exchange for an
 * occasional question. Most cases need the configuration, the logs around the
 * failure and whether the broker and containers are up — all of which fit in a
 * file the owner emails.
 *
 * The capture window exists because almost nobody runs with debug on, so the
 * logs in a bundle collected cold say nothing about the fault. It closes
 * itself: an idle controller logs around twenty MQTT publishes a second at
 * debug level, so one left open buries the history someone will want later.
 *
 * The download is deliberately two steps — the summary of what is inside, then
 * the button. The file carries the whole configuration and the device log, and
 * someone about to email that should know it before they do, not after.
 */

interface CaptureState {
  active: boolean;
  seconds_remaining: number;
  started: number | null;
}

function errorMessage(err: unknown, fallback: string): string {
  return (err as AxiosError<{ detail?: string }>)?.response?.data?.detail || fallback;
}

export default function DiagnosticsCard() {
  const { t } = useTranslation();

  const [capture, setCapture] = useState<CaptureState | null>(null);
  const [minutes, setMinutes] = useState(10);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<CaptureState>('/api/diagnostics/capture');
      setCapture(data);
    } catch {
      setCapture({ active: false, seconds_remaining: 0, started: null });
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  // While a window is open the remaining time is the whole point of the
  // display, so it ticks rather than waiting for the next page load.
  useEffect(() => {
    if (!capture?.active) return;
    const id = setInterval(() => {
      setCapture(prev => {
        if (!prev?.active) return prev;
        const remaining = prev.seconds_remaining - 1;
        return remaining <= 0
          ? { active: false, seconds_remaining: 0, started: null }
          : { ...prev, seconds_remaining: remaining };
      });
    }, 1000);
    return () => clearInterval(id);
  }, [capture?.active]);

  const startCapture = async () => {
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post<CaptureState>('/api/diagnostics/capture', { minutes });
      setCapture(data);
    } catch (err) {
      setError(errorMessage(err, t('diagnostics.capture_failed')));
    } finally {
      setBusy(false);
    }
  };

  const stopCapture = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete<CaptureState>('/api/diagnostics/capture');
      setCapture(data);
    } catch (err) {
      setError(errorMessage(err, t('diagnostics.capture_failed')));
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    setDownloading(true);
    setError(null);
    try {
      const response = await api.get('/api/diagnostics/bundle', { responseType: 'blob' });
      // The filename carries the device name and a timestamp, so an inbox with
      // several of these stays sortable.
      const disposition = String(response.headers['content-disposition'] ?? '');
      const match = disposition.match(/filename="([^"]+)"/);
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = match?.[1] ?? 'boneio-diagnostics.tar.gz';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorMessage(err, t('diagnostics.download_failed')));
    } finally {
      setDownloading(false);
    }
  };

  const remaining = capture?.seconds_remaining ?? 0;
  const clock = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`;

  return (
    <div className="border border-base-300 rounded-xl p-4 space-y-4">
      <div>
        <h3 className="font-semibold">{t('diagnostics.title')}</h3>
        <p className="text-sm opacity-70 mt-1 max-w-3xl">{t('diagnostics.intro')}</p>
      </div>

      <div className="rounded-lg bg-base-200/60 p-3 text-sm">
        <p className="font-medium">{t('diagnostics.contains_title')}</p>
        <ul className="list-disc list-inside opacity-80 mt-1 space-y-0.5">
          <li>{t('diagnostics.contains_config')}</li>
          <li>{t('diagnostics.contains_logs')}</li>
          <li>{t('diagnostics.contains_status')}</li>
        </ul>
        <p className="mt-2 opacity-80">{t('diagnostics.excluded')}</p>
        <p className="mt-1 opacity-80">{t('diagnostics.privacy')}</p>
      </div>

      {capture?.active ? (
        <div className="alert alert-warning">
          <span>{t('diagnostics.capture_active', { time: clock })}</span>
          <button className="btn btn-sm btn-outline" onClick={() => void stopCapture()} disabled={busy}>
            {t('diagnostics.capture_stop')}
          </button>
        </div>
      ) : (
        <div>
          <p className="text-sm font-medium">{t('diagnostics.capture_title')}</p>
          <p className="text-xs opacity-70 mt-1 max-w-3xl">{t('diagnostics.capture_help')}</p>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <select
              className="select select-bordered select-sm"
              value={minutes}
              onChange={e => setMinutes(Number(e.target.value))}
              aria-label={t('diagnostics.capture_length')}
            >
              {[5, 10, 15, 30].map(value => (
                <option key={value} value={value}>
                  {t('diagnostics.capture_minutes', { count: value })}
                </option>
              ))}
            </select>
            <button className="btn btn-sm btn-outline" onClick={() => void startCapture()} disabled={busy}>
              {t('diagnostics.capture_start')}
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-sm text-error">{error}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-sm btn-primary" onClick={() => void download()} disabled={downloading}>
          {downloading ? t('diagnostics.building') : t('diagnostics.download')}
        </button>
        <span className="text-xs opacity-60">{t('diagnostics.build_time')}</span>
      </div>
    </div>
  );
}
