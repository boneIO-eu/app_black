import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '../hooks/useTranslation';

/**
 * Standing warning for a device running with `web.auth.allow_anonymous`.
 *
 * Deliberately not dismissible. The setting means anyone who can reach the
 * device on the network can reconfigure and reboot it, which is a state the
 * owner should be reminded of every time they look at the panel — not
 * something they can click away once and forget.
 */
export default function AnonymousAccessBanner() {
  const { t } = useTranslation();
  const { data } = useAppInit();

  if (!data?.allow_anonymous) return null;

  return (
    <div className="alert alert-error rounded-none text-sm" role="alert">
      <span>
        <strong>{t('security.anonymous_title')}</strong> {t('security.anonymous_body')}
      </span>
    </div>
  );
}
