import { useTranslation } from '../hooks/useTranslation';
import { Loader2 } from 'lucide-react';
import { useStartupStatus } from '../hooks/useStartupStatus';

/**
 * Banner displayed at the top of the page during backend startup.
 * 
 * Shows the current startup step (e.g. "Connecting to MQTT...")
 * with a spinner, and slides away once the backend reports complete.
 */
export default function StartupBanner() {
  const { t } = useTranslation();
  const { isStarting, statusKey } = useStartupStatus();

  if (!isStarting) {
    return null;
  }

  const statusMap: Record<string, string> = {
    initializing: t('startup.initializing'),
    starting_gpio: t('startup.starting_gpio'),
    connecting_mqtt: t('startup.connecting_mqtt'),
    ha_discovery: t('startup.ha_discovery'),
  };

  const displayMessage = statusMap[statusKey] || t('startup.initializing');

  return (
    <div className="alert alert-info py-2 px-4 rounded-none flex items-center gap-2 text-sm animate-fade-in">
      <Loader2 className="h-4 w-4 animate-spin shrink-0" />
      <span>{displayMessage}</span>
    </div>
  );
}
