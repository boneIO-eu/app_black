import { useEffect, useRef, useState } from 'react';
import type { AxiosError } from 'axios';
import { Link } from 'react-router-dom';
import { FaLifeRing } from 'react-icons/fa';
import api from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import { useCaptureWindow } from '../hooks/useCaptureWindow';

/**
 * Support actions, out of the way until asked for.
 *
 * These lived as a card above the log: a screen of explanation standing
 * between the reader and the thing they came to the page for. The log is the
 * page. Everything here is occasional — you open a capture window once while
 * chasing a fault, and download a bundle once when you give up and ask for
 * help — so it belongs behind a menu, the way Home Assistant keeps its log
 * actions in a header menu rather than on the page.
 *
 * The explanation of what the bundle contains stays with the button rather
 * than moving to a tooltip. Someone about to email their whole configuration
 * should read that before they click, not after.
 */

function errorMessage(err: unknown, fallback: string): string {
  return (err as AxiosError<{ detail?: string }>)?.response?.data?.detail || fallback;
}

export default function DiagnosticsMenu() {
  const { t } = useTranslation();
  const { state: capture, clock, busy, open, close } = useCaptureWindow();

  const [isOpen, setIsOpen] = useState(false);
  const [minutes, setMinutes] = useState(10);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onClick = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [isOpen]);

  const download = async () => {
    setDownloading(true);
    setError(null);
    try {
      const response = await api.get('/api/diagnostics/bundle', { responseType: 'blob' });
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
      setIsOpen(false);
    } catch (err) {
      setError(errorMessage(err, t('diagnostics.download_failed')));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        className={`btn btn-sm gap-2 ${capture.active ? 'btn-warning' : 'btn-outline'}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <FaLifeRing className="w-3.5 h-3.5" />
        {t('diagnostics.menu')}
        {/* The countdown rides on the button, so a window left open is visible
            without opening the menu to find it. */}
        {capture.active && <span className="font-mono">{clock}</span>}
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-1 z-50 w-[22rem] max-w-[90vw] bg-base-100 border border-base-content/20 rounded-lg shadow-xl p-4 space-y-4">
          <div>
            <h3 className="font-semibold text-sm">{t('diagnostics.capture_title')}</h3>
            <p className="text-xs opacity-70 mt-1">{t('diagnostics.capture_help')}</p>
            {capture.active ? (
              <div className="flex items-center justify-between gap-2 mt-2 rounded bg-warning/15 px-2 py-1.5">
                <span className="text-xs">
                  {t('diagnostics.capture_active', { time: clock })}
                </span>
                <button
                  className="btn btn-xs btn-outline"
                  onClick={() => void close()}
                  disabled={busy}
                >
                  {t('diagnostics.capture_stop')}
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 mt-2">
                <select
                  className="select select-bordered select-xs"
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
                  className="btn btn-xs btn-outline"
                  onClick={() => void open(minutes)}
                  disabled={busy}
                >
                  {t('diagnostics.capture_start')}
                </button>
              </div>
            )}
          </div>

          <div className="border-t border-base-content/10 pt-3">
            <h3 className="font-semibold text-sm">{t('diagnostics.title')}</h3>
            <p className="text-xs opacity-70 mt-1">{t('diagnostics.intro')}</p>
            <ul className="list-disc list-inside text-xs opacity-80 mt-2 space-y-0.5">
              <li>{t('diagnostics.contains_config')}</li>
              <li>{t('diagnostics.contains_logs')}</li>
              <li>{t('diagnostics.contains_status')}</li>
            </ul>
            <p className="text-xs opacity-70 mt-2">{t('diagnostics.excluded')}</p>
            <p className="text-xs opacity-70 mt-1">{t('diagnostics.privacy')}</p>
            <button
              className="btn btn-sm btn-primary w-full mt-3"
              onClick={() => void download()}
              disabled={downloading}
            >
              {downloading ? t('diagnostics.building') : t('diagnostics.download')}
            </button>
            {error && <p className="text-xs text-error mt-2">{error}</p>}
          </div>

          <div className="border-t border-base-content/10 pt-3 text-xs">
            <span className="opacity-70">{t('diagnostics.persistent_levels')} </span>
            <Link to="/settings/logger" className="link font-semibold" onClick={() => setIsOpen(false)}>
              {t('sections.logger')}
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
