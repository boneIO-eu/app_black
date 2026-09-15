import { Link } from 'react-router-dom';
import { useTranslation } from '../hooks/useTranslation';
import DiagnosticsCard from './DiagnosticsCard';
import LogViewer from './LogViewer';

/**
 * Why is this device behaving like this — in one place.
 *
 * The log viewer lived here on its own as "Logi". The support bundle first
 * went into Settings > Security, which was wrong: collecting diagnostics is
 * not a security setting, and someone chasing a fault does not go looking
 * under hardening. They belong together, because they are two halves of the
 * same act — read the log, and if that is not enough, send it to someone.
 *
 * The persistent `logger:` configuration stays in Settings. That is a choice
 * about how this device behaves from now on; the capture window here is about
 * the next ten minutes. Keeping the durable setting and the temporary one in
 * the same control is how a device ends up permanently at debug.
 */
export default function DiagnosticsView() {
  const { t } = useTranslation();

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2">
          🩺 {t('diagnostics.page_title')}
        </h1>
        <p className="text-sm opacity-70 mt-1 max-w-3xl">{t('diagnostics.page_intro')}</p>
      </div>

      <DiagnosticsCard />

      <div className="text-sm">
        <span className="opacity-70">{t('diagnostics.persistent_levels')} </span>
        <Link to="/settings/logger" className="link font-semibold">
          {t('sections.logger')}
        </Link>
      </div>

      <LogViewer />
    </div>
  );
}
