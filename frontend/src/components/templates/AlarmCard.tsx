import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { useTickingRemaining } from '@/hooks/useTickingRemaining';
import { FaShieldAlt, FaHome, FaWalking, FaMoon, FaUnlock } from 'react-icons/fa';
import clsx from 'clsx';
import type { AlarmState } from './types';
import { TemplateTile } from './TemplateTile';
import { TILE_BUTTON, TILE_BUTTON_STACKED, type Tone } from './tileStyles';

// Armed is the protected, expected state, not a warning: it gets the app's
// own colour. Amber is for the moments in between, red only for a real alarm.
const TONE: Record<string, Tone> = {
  disarmed: 'neutral',
  armed_home: 'primary',
  armed_away: 'primary',
  armed_night: 'primary',
  arming: 'warning',
  pending: 'warning',
  triggered: 'error',
};

export default function AlarmCard({
  data,
  onCommand,
}: {
  data: AlarmState;
  onCommand: (id: string, command: string, code?: string) => void;
}) {
  const { t } = useTranslation();
  const armingLeft = useTickingRemaining(data.state === 'arming' ? data.arming_remaining_s : null);
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

  const state = (
    <>
      {stateLabel[data.state] || data.state}
      {data.state === 'arming' && armingLeft != null && (
        <span className="ml-1 tabular-nums">{Math.ceil(armingLeft)}s</span>
      )}
    </>
  );

  // Three modes, one look: which one to pick is the owner's call, so none of
  // them is coloured as more urgent than the others.
  const armButtons: [string, string, React.ComponentType<{ className?: string }>][] = [
    ['ARM_HOME', t('templates.arm_home'), FaHome],
    ['ARM_AWAY', t('templates.arm_away'), FaWalking],
    ['ARM_NIGHT', t('templates.arm_night'), FaMoon],
  ];

  let footer: React.ReactNode = null;
  if (!data.allow_frontend_control) {
    footer = <p className="text-xs text-base-content/60">{t('templates.frontend_control_disabled')}</p>;
  } else if (pinDialogCommand) {
    footer = (
      <div className="flex flex-col gap-2">
        <input
          ref={inputRef}
          type="password"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="off"
          aria-label={t('templates.enter_pin')}
          className={clsx('input input-lg w-full text-center tracking-[0.4em]', pinError && 'input-error')}
          placeholder={t('templates.enter_pin')}
          value={pin}
          onChange={(e) => { setPin(e.target.value); setPinError(false); }}
          onKeyDown={(e) => e.key === 'Enter' && handlePinSubmit()}
        />
        <div className="grid grid-cols-2 gap-2">
          <button type="button" className={clsx(TILE_BUTTON, 'btn-ghost')} onClick={handlePinCancel}>
            {t('templates.cancel')}
          </button>
          <button type="button" className={clsx(TILE_BUTTON, 'btn-primary')} onClick={handlePinSubmit}>
            OK
          </button>
        </div>
      </div>
    );
  } else if (isArmed || data.state === 'triggered') {
    footer = (
      <button
        type="button"
        className={clsx(TILE_BUTTON, 'w-full', data.state === 'triggered' ? 'btn-error' : 'btn-primary')}
        onClick={() => handleAction('DISARM')}
      >
        <FaUnlock className="w-4 h-4" />
        {t('templates.disarm')}
      </button>
    );
  } else if (isDisarmed) {
    footer = (
      <div className="grid grid-cols-3 gap-2">
        {armButtons.map(([command, label, Icon]) => (
          <button
            key={command}
            type="button"
            className={TILE_BUTTON_STACKED}
            onClick={() => handleAction(command)}
          >
            <Icon className="w-4 h-4" />
            <span className="text-xs leading-tight text-center">{label}</span>
          </button>
        ))}
      </div>
    );
  }

  return (
    <TemplateTile
      icon={FaShieldAlt}
      tone={TONE[data.state] ?? 'neutral'}
      name={data.name || data.id}
      state={state}
      footer={footer}
    />
  );
}
