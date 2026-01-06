import { useState } from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface PowerResult {
  status: string;
  message: string;
}

export const useDevicePower = () => {
  const { t } = useTranslation();
  const [isRebooting, setIsRebooting] = useState(false);
  const [rebootResult, setRebootResult] = useState<PowerResult | null>(null);
  const [isShuttingDown, setIsShuttingDown] = useState(false);
  const [shutdownResult, setShutdownResult] = useState<PowerResult | null>(null);

  const rebootDevice = async () => {
    if (!confirm(t('settings.confirm_reboot'))) {
      return;
    }

    setIsRebooting(true);
    setRebootResult(null);

    try {
      const response = await fetch('/api/reboot', {
        method: 'POST',
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('settings.reboot_failed'));
      }

      const data = await response.json();
      setRebootResult({ status: 'success', message: data.message || t('settings.device_rebooting') });
    } catch (err: any) {
      setRebootResult({ status: 'error', message: err.message || t('settings.reboot_failed') });
      setIsRebooting(false);
    }
  };

  const shutdownDevice = async () => {
    if (!confirm(t('settings.confirm_shutdown'))) {
      return;
    }

    setIsShuttingDown(true);
    setShutdownResult(null);

    try {
      const response = await fetch('/api/shutdown', {
        method: 'POST',
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('settings.shutdown_failed'));
      }

      const data = await response.json();
      setShutdownResult({ status: 'success', message: data.message || t('settings.device_shutting_down') });
    } catch (err: any) {
      setShutdownResult({ status: 'error', message: err.message || t('settings.shutdown_failed') });
      setIsShuttingDown(false);
    }
  };

  return {
    isRebooting,
    rebootResult,
    isShuttingDown,
    shutdownResult,
    rebootDevice,
    shutdownDevice,
  };
};
