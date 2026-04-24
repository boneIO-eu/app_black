import { useLocation, useNavigate } from 'react-router-dom';
import { FaExclamationTriangle, FaArrowRight } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';
import { useMigrations } from '../hooks/useMigrations';

/**
 * Global banner displayed when system migrations need attention.
 *
 * Visible only when ``bootstrap_required`` is true or pending_count > 0.
 * Hidden on the /system page since the full panel is already shown there.
 */
export default function MigrationBanner() {
  const { t } = useTranslation();
  const { status } = useMigrations(15000);
  const location = useLocation();
  const navigate = useNavigate();

  if (!status) return null;
  if (status.pending_count === 0 && !status.bootstrap_required) return null;
  if (location.pathname === '/system') return null;

  const bootstrap = status.bootstrap_required;
  const alertClass = bootstrap ? 'alert-warning' : 'alert-info';
  const message = bootstrap
    ? t('migrations.banner_bootstrap_required')
    : t('migrations.banner_pending', { count: status.pending_count });

  return (
    <div
      className={`alert ${alertClass} py-2 px-4 rounded-none flex items-center gap-2 text-sm`}
    >
      <FaExclamationTriangle className="h-4 w-4 shrink-0" />
      <span className="flex-1">{message}</span>
      <button
        className="btn btn-xs btn-outline"
        onClick={() => navigate('/system')}
      >
        {t('migrations.open_panel')}
        <FaArrowRight className="h-3 w-3" />
      </button>
    </div>
  );
}
