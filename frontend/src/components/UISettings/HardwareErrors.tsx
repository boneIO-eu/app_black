import React from 'react';
import { FaExclamationTriangle } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface HardwareError {
  type: string;
  expander_type?: string;
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

  return (
    <div className="alert alert-error">
      <FaExclamationTriangle />
      <div className="flex-1">
        <h3 className="font-bold">{t('system_update.hardware_errors_title')}</h3>
        <div className="text-sm mt-2 space-y-1">
          {errors.map((err, idx) => (
            <div key={idx} className="font-mono">
              {err.type === 'expander' ? (
                <span>
                  {err.expander_type} {err.id} (0x{err.address?.toString(16)}): {err.error}
                </span>
              ) : err.type === 'output' ? (
                <span>
                  Output {err.id} ({err.name}): {err.error}
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
  );
};

export default HardwareErrors;
