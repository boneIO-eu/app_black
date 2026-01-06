import React from 'react';
import {
  FaPowerOff,
  FaSpinner,
  FaCheck,
  FaExclamationTriangle,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface TurnOffOutputsSectionProps {
  outputs: any[];
  isTurningOff: boolean;
  turnOffProgress: number;
  turnOffResult: { status: string; message: string } | null;
  onTurnOffAll: () => void;
}

export const TurnOffOutputsSection: React.FC<TurnOffOutputsSectionProps> = ({
  outputs,
  isTurningOff,
  turnOffProgress,
  turnOffResult,
  onTurnOffAll,
}) => {
  const { t } = useTranslation();

  const activeOutputsCount = outputs.filter(
    (o) => o.state === 'ON' || o.state === 'on' || o.state === true
  ).length;

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h3 className="card-title">
          <FaPowerOff />
          {t('system_update.turn_off_all_outputs')}
        </h3>
        <p className="text-sm opacity-70 mb-4">
          {t('system_update.turn_off_description')}
        </p>
        <div className="card-actions">
          <button
            className="btn btn-warning"
            onClick={onTurnOffAll}
            disabled={isTurningOff || activeOutputsCount === 0}
          >
            {isTurningOff ? (
              <>
                <FaSpinner className="animate-spin" />
                {t('system_update.turning_off')}
              </>
            ) : (
              <>
                <FaPowerOff />
                {t('system_update.turn_off_all_outputs')} ({activeOutputsCount})
              </>
            )}
          </button>
        </div>

        {isTurningOff && (
          <div className="mt-4">
            <progress
              className="progress progress-warning w-full"
              value={turnOffProgress}
              max="100"
            ></progress>
          </div>
        )}

        {turnOffResult && (
          <div
            className={`alert ${turnOffResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-4`}
          >
            {turnOffResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
            <span>{turnOffResult.message}</span>
          </div>
        )}
      </div>
    </div>
  );
};
