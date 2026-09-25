import React, { useState } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { useTickingRemaining } from '@/hooks/useTickingRemaining';
import { useNow } from '@/hooks/useEntityHistory';
import { FaShieldAlt, FaHome, FaWalking, FaMoon, FaUnlock } from 'react-icons/fa';
import clsx from 'clsx';
import type { AlarmCommandResult, AlarmState } from './types';
import { TemplateTile } from './TemplateTile';
import PinPad from './PinPad';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
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
  embedded = false,
}: {
  data: AlarmState;
  /** Resolves to why a code was refused, so the pad can say so. */
  onCommand: (id: string, command: string, code?: string) => Promise<AlarmCommandResult | void> | void;
  /** Inside the long-press card, which shows the name itself. */
  embedded?: boolean;
}) {
  const { t } = useTranslation();
  const armingLeft = useTickingRemaining(data.state === 'arming' ? data.arming_remaining_s : null);
  // Seconds the controller will not look at codes for, counting down between
  // polls. Shown on the pad and on the tile, so the owner knows it is not
  // their PIN that has stopped working.
  // Two sources: the poll, and the 429 that announced the lock — the latter
  // straight away, and on firmware whose poll does not report it at all.
  const polledLeft = useTickingRemaining(data.code_locked_s ?? null);
  const [lock, setLock] = useState<{ until: number; seconds: number } | null>(null);
  const now = useNow(lock != null);
  // Capped at the announced length: until the first tick `now` is as old as
  // the card, which would otherwise add that age to the countdown.
  const localLeft = lock ? Math.min(lock.seconds, Math.max(0, (lock.until - now) / 1000)) : 0;
  const lockedLeft = Math.max(polledLeft ?? 0, localLeft);
  const isLocked = lockedLeft > 0;
  const [pinDialogCommand, setPinDialogCommand] = useState<string | null>(null);
  const [pin, setPin] = useState('');
  const [pinError, setPinError] = useState<'invalid_code' | 'code_required' | 'error' | null>(null);

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
      setPinError(null);
    } else {
      onCommand(data.id, command);
    }
  };

  const handlePinSubmit = async () => {
    if (!pinDialogCommand || !pin) return;
    const command = pinDialogCommand;
    const code = pin;
    // Cleared at once: the digits should not sit in the pad while the
    // request is in flight, nor be there to resend after a refusal.
    setPin('');
    const result = await onCommand(data.id, command, code);
    if (result && !result.ok) {
      // The pad stays open: after a wrong code to try again, during a
      // lockout to wait it out.
      if (result.reason === 'locked') {
        const seconds = result.retryAfter ?? 30;
        setLock({ until: Date.now() + seconds * 1000, seconds });
        setPinError(null);
      } else {
        setPinError(result.reason);
      }
      return;
    }
    setPinDialogCommand(null);
    setPinError(null);
  };

  const handlePinCancel = () => {
    setPinDialogCommand(null);
    setPin('');
    setPinError(null);
  };

  const pinMessage = isLocked
    ? t('templates.pin_locked', { s: Math.ceil(lockedLeft) })
    : pinError === 'invalid_code'
      ? t('templates.pin_invalid')
      : pinError === 'error'
        ? t('templates.pin_error')
        : pinError === 'code_required'
          ? t('templates.enter_pin')
          : undefined;

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

  const commandLabel: Record<string, string> = {
    DISARM: t('templates.disarm'),
    ARM_HOME: t('templates.arm_home'),
    ARM_AWAY: t('templates.arm_away'),
    ARM_NIGHT: t('templates.arm_night'),
  };

  return (
    <>
      <TemplateTile
        embedded={embedded}
        icon={FaShieldAlt}
        tone={TONE[data.state] ?? 'neutral'}
        name={data.name || data.id}
        state={state}
        footer={footer}
      >
        {/* A line of its own, not a suffix on the state: at phone width the
            state is truncated, and this is the part that must not be cut. */}
        {isLocked && (
          <p className="text-sm text-warning">{t('templates.pin_locked_short', { s: Math.ceil(lockedLeft) })}</p>
        )}
      </TemplateTile>

      {/* The PIN pad gets a window of its own rather than taking over the
          tile: the tile keeps its size, and on a phone the window comes up
          from the bottom, where the thumb already is. */}
      <Dialog open={pinDialogCommand != null} onOpenChange={(open) => !open && handlePinCancel()}>
        <DialogContent maxWidthClass="sm:max-w-xs" className="gap-4">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-center sm:justify-start gap-2">
              <FaShieldAlt className="w-4 h-4 text-base-content/60" />
              {pinDialogCommand ? commandLabel[pinDialogCommand] ?? pinDialogCommand : ''}
            </DialogTitle>
            <DialogDescription>
              {data.name || data.id} · {state}
            </DialogDescription>
          </DialogHeader>
          <PinPad
            value={pin}
            onChange={(v) => { setPin(v); setPinError(null); }}
            onSubmit={handlePinSubmit}
            onCancel={handlePinCancel}
            message={pinMessage}
            disabled={isLocked}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
