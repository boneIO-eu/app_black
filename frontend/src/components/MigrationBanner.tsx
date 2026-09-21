import { useLocation, useNavigate } from 'react-router-dom';
import { FaExclamationTriangle, FaArrowRight } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';
import { useMigrations } from '../hooks/useMigrations';

/**
 * Global banner displayed when system migrations need attention.
 *
 * Three states, and the difference between them matters. A device with
 * migrations pending has simply not applied them yet, and will on the next
 * start. A device whose helper *refused* one will refuse it again on every
 * start, for as long as whatever it objected to is true — that is not news
 * about a queue, it is a device that has quietly stopped receiving system
 * hardening, and it needs somebody to go and read what the helper said.
 *
 * Before this, both arrived in the same blue box saying "N pending".
 *
 * The helper's own words are shown rather than a message of our own. It writes
 * its refusals to be read by whoever has to act on them, and a paraphrase here
 * would drift from them with the first change to either side.
 *
 * Hidden on the /system page since the full panel is already shown there.
 */
export default function MigrationBanner() {
  const { t } = useTranslation();
  const { status } = useMigrations(15000);
  const location = useLocation();
  const navigate = useNavigate();

  if (!status) return null;
  const failed = status.status === 'error';
  if (status.pending_count === 0 && !status.bootstrap_required && !failed) return null;
  if (location.pathname === '/system') return null;

  const bootstrap = status.bootstrap_required;
  const alertClass = failed ? 'alert-error' : bootstrap ? 'alert-warning' : 'alert-info';
  const message = failed
    ? t('migrations.banner_failed')
    : bootstrap
      ? t('migrations.banner_bootstrap_required')
      : t('migrations.banner_pending', { count: status.pending_count });

  return (
    <div
      className={`alert ${alertClass} py-2 px-4 rounded-none flex items-start gap-2 text-sm`}
    >
      <FaExclamationTriangle className="h-4 w-4 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <span>{message}</span>
        {/* Wrapped, not truncated: a refusal that explains itself in two
            sentences is useless with the second one cut off. */}
        {failed && status.last_error && (
          <p className="mt-1 text-xs opacity-90 break-words">{status.last_error}</p>
        )}
      </div>
      <button
        className="btn btn-xs btn-outline shrink-0"
        onClick={() => navigate('/system')}
      >
        {t('migrations.open_panel')}
        <FaArrowRight className="h-3 w-3" />
      </button>
    </div>
  );
}
