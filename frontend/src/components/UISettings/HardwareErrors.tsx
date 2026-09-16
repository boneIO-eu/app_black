import React from 'react';
import { FaExclamationTriangle } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { SettingsCard } from './ui';

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

  // Filter out legacy can_sudoers errors (now handled by migration system)
  const hwErrors = errors.filter(err => err.type !== 'can_sudoers');

  if (hwErrors.length === 0) {
    return null;
  }

  return (
    <SettingsCard
      variant="danger"
      icon={<FaExclamationTriangle />}
      title={t('system_update.hardware_errors_title')}
      description={t('system_update.hardware_errors_hint')}
    >
      <div className="stg-inset divide-y divide-base-content/8">
        {hwErrors.map((err, idx) => (
          <div key={idx} className="flex items-start gap-2.5 p-3 font-mono text-xs">
            <span className="text-error shrink-0 mt-px">•</span>
            <span className="min-w-0 break-words text-base-content/80">
              {err.type === 'expander' ? (
                <>
                  {err.expander_type} {err.id} (0x{err.address?.toString(16)}): {err.error}
                </>
              ) : err.type === 'output' ? (
                <>
                  Output {err.id} ({err.name}): {err.error}
                </>
              ) : err.type === 'sensor' ? (
                <>
                  {err.sensor_type?.toUpperCase()} {err.name} (0x{err.address?.toString(16)}): {err.error}
                </>
              ) : err.type === 'display' ? (
                <>
                  {err.name} (0x{err.address?.toString(16)}): {err.error}
                </>
              ) : (
                err.message
              )}
            </span>
          </div>
        ))}
      </div>
    </SettingsCard>
  );
};

export default HardwareErrors;
