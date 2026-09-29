import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '@/hooks/useTranslation';
import { NoticeCallout } from '@/components/UISettings/ui';

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
    <div className="fixed bottom-4 inset-x-4 z-50 mx-auto max-w-xl bg-base-100 rounded-box shadow-lg">
      <NoticeCallout
        variant="error"
        title={t('panel_guard.failed_title')}
        message={t('panel_guard.failed_body', { version: data?.version ?? '' })}
        action={
          <button onClick={dismissPanelState} className="btn btn-sm btn-ghost">
            {t('panel_guard.dismiss')}
          </button>
        }
      />
    </div>
  );
};

export default UpdateFailedNotice;
