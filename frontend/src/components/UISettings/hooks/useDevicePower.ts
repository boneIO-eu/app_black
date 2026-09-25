import { useState } from 'react';
import axios from '@/api/axios';
import type { AxiosError } from 'axios';
import { useTranslation } from '@/hooks/useTranslation';

type ApiError = AxiosError<{ detail?: string }>;

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
      const { data } = await axios.post('/api/reboot');
      setRebootResult({ status: 'success', message: data.message || t('settings.device_rebooting') });
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setRebootResult({ status: 'error', message: apiErr.message || t('settings.reboot_failed') });
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
      const { data } = await axios.post('/api/shutdown');
      setShutdownResult({ status: 'success', message: data.message || t('settings.device_shutting_down') });
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      setShutdownResult({ status: 'error', message: apiErr.message || t('settings.shutdown_failed') });
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
