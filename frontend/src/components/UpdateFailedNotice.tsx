import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '@/hooks/useTranslation';

/**
 * An update that brought the controller back on its old version.
 *
 * A notice over the working panel rather than a screen in front of it: the
 * old version runs fine, and the logs that say why are in that panel.
 */
const UpdateFailedNotice = () => {
  const { panelState, data, dismissPanelState } = useAppInit();
  const { t } = useTranslation();
  if (panelState !== 'update_failed') return null;
  return (
    <div className="fixed bottom-4 inset-x-4 z-50 mx-auto max-w-xl">
      <div role="alert" className="alert alert-error shadow-lg">
        <div>
          <h3 className="font-bold">{t('panel_guard.failed_title')}</h3>
          <div className="text-sm">{t('panel_guard.failed_body', { version: data?.version ?? '' })}</div>
        </div>
        <button onClick={dismissPanelState} className="btn btn-sm btn-ghost">
          {t('panel_guard.dismiss')}
        </button>
      </div>
    </div>
  );
};

export default UpdateFailedNotice;
