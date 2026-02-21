import { useState, useRef, useEffect } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { FaShieldAlt } from 'react-icons/fa';
import type { AlarmState } from './types';

const STATE_BADGE: Record<string, string> = {
  disarmed: 'badge-success',
  armed_home: 'badge-warning',
  armed_away: 'badge-error',
  armed_night: 'badge-info',
  arming: 'badge-warning animate-pulse',
  pending: 'badge-warning animate-pulse',
  triggered: 'badge-error animate-pulse',
};

export default function AlarmCard({
  data,
  onCommand,
}: {
  data: AlarmState;
  onCommand: (id: string, command: string, code?: string) => void;
}) {
  const { t } = useTranslation();
  const [pinDialogCommand, setPinDialogCommand] = useState<string | null>(null);
  const [pin, setPin] = useState('');
  const [pinError, setPinError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const stateLabel: Record<string, string> = {
    disarmed: t('templates.disarmed'),
    armed_home: t('templates.armed_home'),
    armed_away: t('templates.armed_away'),
    armed_night: t('templates.armed_night'),
    arming: t('templates.arming'),
    pending: t('templates.pending'),
    triggered: t('templates.triggered'),
  };

  const isArmed = data.state.startsWith('armed');
  const isDisarmed = data.state === 'disarmed';

  const needsCode = (command: string) => {
    if (command === 'DISARM') return data.code_required;
    return data.code_required && data.code_arm_required;
  };

  const handleAction = (command: string) => {
    if (needsCode(command)) {
      setPinDialogCommand(command);
      setPin('');
      setPinError(false);
    } else {
      onCommand(data.id, command);
    }
  };

  const handlePinSubmit = () => {
    if (!pin.trim()) {
      setPinError(true);
      return;
    }
    if (pinDialogCommand) {
      onCommand(data.id, pinDialogCommand, pin);
    }
    setPinDialogCommand(null);
    setPin('');
    setPinError(false);
  };

  const handlePinCancel = () => {
    setPinDialogCommand(null);
    setPin('');
    setPinError(false);
  };

  useEffect(() => {
    if (pinDialogCommand && inputRef.current) {
      inputRef.current.focus();
    }
  }, [pinDialogCommand]);

  return (
    <div className="rounded-xl bg-base-100 shadow-sm px-4 py-6 max-w-xs w-full">
      {/* Header row: icon + name + state badge */}
      <div className="flex items-center gap-2">
        <FaShieldAlt className={`h-4 w-4 shrink-0 ${isArmed ? 'text-error' : 'text-success'}`} />
        <span className="font-medium text-sm truncate flex-1">{data.name || data.id}</span>
        <span className={`badge badge-sm ${STATE_BADGE[data.state] || 'badge-ghost'}`}>
          {stateLabel[data.state] || data.state}
          {data.state === 'arming' && data.arming_remaining_s != null && (
            <span className="ml-1 tabular-nums">{Math.ceil(data.arming_remaining_s)}s</span>
          )}
        </span>
      </div>

      {/* PIN dialog */}
      {pinDialogCommand && (
        <div className="mt-3 flex flex-col gap-2">
          <input
            ref={inputRef}
            type="password"
            inputMode="numeric"
            pattern="[0-9]*"
            className={`input input-sm input-bordered w-full text-center tracking-widest ${pinError ? 'input-error' : ''}`}
            placeholder="PIN"
            value={pin}
            onChange={(e) => { setPin(e.target.value); setPinError(false); }}
            onKeyDown={(e) => e.key === 'Enter' && handlePinSubmit()}
          />
          <div className="flex gap-1.5">
            <button className="btn btn-xs btn-ghost flex-1" onClick={handlePinCancel}>
              {t('templates.cancel') || 'Cancel'}
            </button>
            <button className="btn btn-xs btn-primary flex-1" onClick={handlePinSubmit}>
              OK
            </button>
          </div>
        </div>
      )}

      {/* Controls */}
      {data.allow_frontend_control && !pinDialogCommand && (
        <div className="flex gap-2 mt-4">
          {isArmed || data.state === 'triggered' ? (
            <button
              className="btn btn-sm h-auto py-2 btn-success flex-1"
              onClick={() => handleAction('DISARM')}
            >
              {t('templates.disarm')}
            </button>
          ) : isDisarmed ? (
            <>
              <button
                className="btn btn-sm h-auto py-2 btn-warning flex-1 leading-tight"
                onClick={() => handleAction('ARM_HOME')}
              >
                {t('templates.arm_home')}
              </button>
              <button
                className="btn btn-sm h-auto py-2 btn-error flex-1 leading-tight"
                onClick={() => handleAction('ARM_AWAY')}
              >
                {t('templates.arm_away')}
              </button>
              <button
                className="btn btn-sm h-auto py-2 btn-info flex-1 leading-tight"
                onClick={() => handleAction('ARM_NIGHT')}
              >
                {t('templates.arm_night')}
              </button>
            </>
          ) : null}
        </div>
      )}

      {!data.allow_frontend_control && (
        <p className="text-[10px] text-base-content/40 mt-1">
          {t('templates.frontend_control_disabled')}
        </p>
      )}
    </div>
  );
}
