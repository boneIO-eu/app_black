import React from 'react';
import { FaExclamationTriangle } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface HardwareError {
  type: string;
  expander_type?: string;
  sensor_type?: string;
  id: string;
  name?: string;
  address?: number;
  error: string;
  message: string;
}

interface HardwareErrorsProps {
  errors: HardwareError[];
}

const HardwareErrors: React.FC<HardwareErrorsProps> = ({ errors }) => {
  const { t } = useTranslation();

  if (errors.length === 0) {
    return null;
  }

  // Separate CAN sudoers errors from hardware errors
  const canSudoersErrors = errors.filter(err => err.type === 'can_sudoers');
  const hwErrors = errors.filter(err => err.type !== 'can_sudoers');

  return (
    <>
      {/* CAN Sudoers Error */}
      {canSudoersErrors.length > 0 && (
        <div className="alert alert-warning">
          <FaExclamationTriangle />
          <div className="flex-1">
            <h3 className="font-bold">{t('can_sudoers.error_title')}</h3>
            <p className="text-sm mt-1">{t('can_sudoers.error_description')}</p>
            <p className="text-sm mt-1 font-mono opacity-70">{canSudoersErrors[0].message}</p>
          </div>
          <a href="/system" className="btn btn-sm btn-outline">
            {t('can_sudoers.fix_button')}
          </a>
        </div>
      )}

      {/* Hardware Errors */}
      {hwErrors.length > 0 && (
        <div className="alert alert-error">
          <FaExclamationTriangle />
          <div className="flex-1">
            <h3 className="font-bold">{t('system_update.hardware_errors_title')}</h3>
            <div className="text-sm mt-2 space-y-1">
              {hwErrors.map((err, idx) => (
                <div key={idx} className="font-mono">
                  {err.type === 'expander' ? (
                    <span>
                      {err.expander_type} {err.id} (0x{err.address?.toString(16)}): {err.error}
                    </span>
                  ) : err.type === 'output' ? (
                    <span>
                      Output {err.id} ({err.name}): {err.error}
                    </span>
                  ) : err.type === 'sensor' ? (
                    <span>
                      {err.sensor_type?.toUpperCase()} {err.name} (0x{err.address?.toString(16)}): {err.error}
                    </span>
                  ) : err.type === 'display' ? (
                    <span>
                      {err.name} (0x{err.address?.toString(16)}): {err.error}
                    </span>
                  ) : (
                    <span>{err.message}</span>
                  )}
                </div>
              ))}
            </div>
            <div className="text-sm mt-2">{t('system_update.hardware_errors_hint')}</div>
          </div>
        </div>
      )}
    </>
  );
};

export default HardwareErrors;
