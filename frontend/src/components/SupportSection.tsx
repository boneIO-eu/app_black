import { useState } from 'react';
import type { AxiosError } from 'axios';
import { FaDownload, FaStopwatch, FaFileLines } from 'react-icons/fa6';
import api from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import { useCaptureWindow } from '../hooks/useCaptureWindow';
import LoggerSettingsDialog from './LoggerSettingsDialog';
import {
  SettingsPage,
  SettingsCard,
  FormActions,
  NoticeCallout,
} from './UISettings/ui';

/**
 * Everything you reach for when the log alone has not answered the question.
 *
 * This was a dropdown beside the page title. It held three unrelated things —
 * a temporary capture window, a support bundle, and a link out to the
 * persistent log levels — stacked in a 22rem panel that closed if you clicked
 * anywhere. Each is now a card in a section of its own, which is also what
 * makes the log levels editable in place rather than a trip to Settings.
 */
/**
 * What actually went wrong, when the response body is a Blob.
 *
 * The bundle is fetched with `responseType: 'blob'`, so axios hands back the
 * error body as a Blob too — reading `.detail` off it is always undefined and
 * every failure came out as the same generic sentence. Reading the blob costs
 * one await and turns "could not collect the bundle" into the reason.
 */
async function errorMessage(err: unknown, fallback: string): Promise<string> {
  const axiosErr = err as AxiosError<unknown>;

  if (axiosErr?.code === 'ECONNABORTED') return fallback;

  const data = axiosErr?.response?.data;
  if (data instanceof Blob) {
    try {
      const text = await data.text();
      const parsed = JSON.parse(text) as { detail?: string };
      if (parsed?.detail) return parsed.detail;
    } catch {
      // Not JSON — nothing better to say than the fallback.
    }
  } else if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail?: string }).detail;
    if (detail) return detail;
  }

  return fallback;
}

export default function SupportSection() {
  const { t } = useTranslation();
  const { state: capture, clock, busy, open, close } = useCaptureWindow();

  const [minutes, setMinutes] = useState(10);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loggerOpen, setLoggerOpen] = useState(false);

  const download = async () => {
    setDownloading(true);
    setError(null);
    try {
      // The shared axios instance times out after 5s, which is right for the
      // small calls the panel makes and wrong for this one: the device collects a
      // config, a log and the state of MQTT, Docker and the network before it
      // answers, measured at ~5.2s on a BeagleBone. It aborted just short of
      // returning, every time, and reported it as a collection failure.
      const response = await api.get('/api/diagnostics/bundle', {
        responseType: 'blob',
        timeout: 120000,
      });
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
      setError(await errorMessage(err, t('diagnostics.download_failed')));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <SettingsPage>
      {/* Capture window — temporary by design. */}
      <SettingsCard
        icon={<FaStopwatch />}
        title={t('diagnostics.capture_title')}
        description={t('diagnostics.capture_help')}
        footer={
          capture.active ? (
            <FormActions hint={t('diagnostics.capture_active', { time: clock })}>
              <button
                className="btn btn-warning btn-sm"
                onClick={() => void close()}
                disabled={busy}
              >
                {t('diagnostics.capture_stop')}
              </button>
            </FormActions>
          ) : (
            <FormActions>
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
              <button
                className="btn btn-primary btn-sm"
                onClick={() => void open(minutes)}
                disabled={busy}
              >
                {t('diagnostics.capture_start')}
              </button>
            </FormActions>
          )
        }
      >
        {capture.active && (
          <NoticeCallout
            variant="warning"
            message={t('diagnostics.capture_active', { time: clock })}
          />
        )}
      </SettingsCard>

      {/* The persistent levels, edited here rather than linked to. */}
      <SettingsCard
        icon={<FaFileLines />}
        title={t('sections.logger')}
        description={t('diagnostics.logger_card_desc')}
        footer={
          <FormActions>
            <button className="btn btn-outline btn-sm" onClick={() => setLoggerOpen(true)}>
              {t('diagnostics.logger_open')}
            </button>
          </FormActions>
        }
      />

      {/* Support bundle. The explanation stays with the button: someone about
          to email their whole configuration should read it before they click,
          not after. */}
      <SettingsCard
        icon={<FaDownload />}
        title={t('diagnostics.title')}
        description={t('diagnostics.intro')}
        footer={
          <FormActions>
            <button
              className="btn btn-primary btn-sm gap-2"
              onClick={() => void download()}
              disabled={downloading}
            >
              {downloading ? (
                <>
                  <span className="loading loading-spinner loading-xs" />
                  {t('diagnostics.building')}
                </>
              ) : (
                <>
                  <FaDownload />
                  {t('diagnostics.download')}
                </>
              )}
            </button>
          </FormActions>
        }
      >
        <div className="space-y-3">
          <div className="stg-inset p-3.5">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-base-content/50 mb-1.5">
              {t('diagnostics.contains_title')}
            </h4>
            <ul className="list-disc list-inside text-[13px] text-base-content/75 space-y-0.5">
              <li>{t('diagnostics.contains_config')}</li>
              <li>{t('diagnostics.contains_logs')}</li>
              <li>{t('diagnostics.contains_status')}</li>
            </ul>
          </div>
          <NoticeCallout
            variant="neutral"
            message={
              <>
                <span className="block">{t('diagnostics.excluded')}</span>
                <span className="block mt-1">{t('diagnostics.privacy')}</span>
              </>
            }
          />
          {error && <NoticeCallout variant="error" message={error} />}
        </div>
      </SettingsCard>

      <LoggerSettingsDialog open={loggerOpen} onOpenChange={setLoggerOpen} />
    </SettingsPage>
  );
}
