import { useState } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
  FaPowerOff,
  FaRedo,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

/**
 * Section for rebooting and shutting down the device.
 */
export default function DeviceControlSection() {
  const { t } = useTranslation();
  const [isRebooting, setIsRebooting] = useState(false);
  const [rebootResult, setRebootResult] = useState<{ status: string; message: string } | null>(null);
  const [isShuttingDown, setIsShuttingDown] = useState(false);
  const [shutdownResult, setShutdownResult] = useState<{ status: string; message: string } | null>(null);

  const rebootDevice = async () => {
    if (!confirm(t('settings.confirm_reboot'))) return;
    setIsRebooting(true);
    setRebootResult(null);
    try {
      const { data } = await axios.post('/api/reboot');
      setRebootResult({ status: 'success', message: data.message || t('settings.device_rebooting') });
    } catch (err: any) {
      setRebootResult({ status: 'error', message: err.message || t('settings.reboot_failed') });
      setIsRebooting(false);
    }
  };

  const shutdownDevice = async () => {
    if (!confirm(t('settings.confirm_shutdown'))) return;
    setIsShuttingDown(true);
    setShutdownResult(null);
    try {
      const { data } = await axios.post('/api/shutdown');
      setShutdownResult({ status: 'success', message: data.message || t('settings.device_shutting_down') });
    } catch (err: any) {
      setShutdownResult({ status: 'error', message: err.message || t('settings.shutdown_failed') });
      setIsShuttingDown(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Reboot Device Section */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6">
          <h3 className="card-title text-base gap-2">
            <FaRedo className="text-warning" />
            {t('settings.reboot_device')}
          </h3>
          <p className="text-sm opacity-70 mb-4">
            {t('settings.reboot_description')}
          </p>
          <div className="card-actions">
            <button
              className="btn btn-warning btn-sm"
              onClick={rebootDevice}
              disabled={isRebooting}
            >
              {isRebooting ? (
                <>
                  <FaSpinner className="animate-spin" />
                  {t('settings.rebooting')}
                </>
              ) : (
                <>
                  <FaRedo />
                  {t('settings.reboot_device')}
                </>
              )}
            </button>
          </div>
          {rebootResult && (
            <div
              className={`alert ${rebootResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-4 text-sm`}
            >
              {rebootResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
              <span>{rebootResult.message}</span>
            </div>
          )}
          <div className="alert alert-error mt-4 text-sm">
            <FaExclamationTriangle />
            <div>
              <p>{t('settings.reboot_warning')}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Shutdown Device Section */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6">
          <h3 className="card-title text-base gap-2">
            <FaPowerOff className="text-error" />
            {t('settings.shutdown_device')}
          </h3>
          <p className="text-sm opacity-70 mb-4">
            {t('settings.shutdown_description')}
          </p>
          <div className="card-actions">
            <button
              className="btn btn-error btn-sm"
              onClick={shutdownDevice}
              disabled={isShuttingDown}
            >
              {isShuttingDown ? (
                <>
                  <FaSpinner className="animate-spin" />
                  {t('settings.shutting_down')}
                </>
              ) : (
                <>
                  <FaPowerOff />
                  {t('settings.shutdown_device')}
                </>
              )}
            </button>
          </div>
          {shutdownResult && (
            <div
              className={`alert ${shutdownResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-4 text-sm`}
            >
              {shutdownResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
              <span>{shutdownResult.message}</span>
            </div>
          )}
          <div className="alert alert-warning mt-4 text-sm">
            <FaExclamationTriangle />
            <div>
              <p>{t('settings.shutdown_warning')}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
