import React from 'react';
import {
  FaRedo,
  FaPowerOff,
  FaSpinner,
  FaCheck,
  FaExclamationTriangle,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface PowerSectionProps {
  isRebooting: boolean;
  rebootResult: { status: string; message: string } | null;
  isShuttingDown: boolean;
  shutdownResult: { status: string; message: string } | null;
  onReboot: () => void;
  onShutdown: () => void;
}

export const PowerSection: React.FC<PowerSectionProps> = ({
  isRebooting,
  rebootResult,
  isShuttingDown,
  shutdownResult,
  onReboot,
  onShutdown,
}) => {
  const { t } = useTranslation();

  return (
    <>
      {/* Reboot Device Section */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h3 className="card-title">
            <FaRedo />
            {t('settings.reboot_device')}
          </h3>
          <p className="text-sm opacity-70 mb-4">
            {t('settings.reboot_description')}
          </p>
          <div className="card-actions">
            <button
              className="btn btn-warning"
              onClick={onReboot}
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
              className={`alert ${rebootResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-4`}
            >
              {rebootResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
              <span>{rebootResult.message}</span>
            </div>
          )}
          <div className="alert alert-error mt-4">
            <FaExclamationTriangle />
            <div className="text-sm">
              <p>{t('settings.reboot_warning')}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Shutdown Device Section */}
      <div className="card bg-base-200">
        <div className="card-body">
          <h3 className="card-title">
            <FaPowerOff />
            {t('settings.shutdown_device')}
          </h3>
          <p className="text-sm opacity-70 mb-4">
            {t('settings.shutdown_description')}
          </p>
          <div className="card-actions">
            <button
              className="btn btn-error"
              onClick={onShutdown}
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
              className={`alert ${shutdownResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-4`}
            >
              {shutdownResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
              <span>{shutdownResult.message}</span>
            </div>
          )}
          <div className="alert alert-warning mt-4">
            <FaExclamationTriangle />
            <div className="text-sm">
              <p>{t('settings.shutdown_warning')}</p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
