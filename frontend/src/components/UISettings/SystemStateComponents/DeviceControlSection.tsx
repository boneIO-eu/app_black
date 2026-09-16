import { useState } from 'react';
import {
  FaSpinner,
  FaPowerOff,
  FaRedo,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import { SettingsPage, SettingsCard, FormActions, NoticeCallout } from '../ui';

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
    <SettingsPage>
      {/* Reboot */}
      <SettingsCard
        icon={<FaRedo />}
        title={t('settings.reboot_device')}
        description={t('settings.reboot_description')}
        footer={
          <FormActions>
            <button
              className="btn btn-warning btn-sm gap-2"
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
          </FormActions>
        }
      >
        <div className="space-y-3">
          <NoticeCallout variant="warning" message={t('settings.reboot_warning')} />
          {rebootResult && (
            <NoticeCallout
              variant={rebootResult.status === 'success' ? 'success' : 'error'}
              message={rebootResult.message}
            />
          )}
        </div>
      </SettingsCard>

      {/* Shutdown */}
      <SettingsCard
        variant="danger"
        icon={<FaPowerOff />}
        title={t('settings.shutdown_device')}
        description={t('settings.shutdown_description')}
        footer={
          <FormActions>
            <button
              className="btn btn-error btn-sm gap-2"
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
          </FormActions>
        }
      >
        <div className="space-y-3">
          <NoticeCallout variant="error" message={t('settings.shutdown_warning')} />
          {shutdownResult && (
            <NoticeCallout
              variant={shutdownResult.status === 'success' ? 'success' : 'error'}
              message={shutdownResult.message}
            />
          )}
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
