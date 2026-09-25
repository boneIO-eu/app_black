import React, { useEffect, useRef } from 'react';
import clsx from 'clsx';
import { FaBackspace, FaCheck } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { TILE_BUTTON } from './tileStyles';

/** Longest PIN the pad takes; the settings form stores up to eight digits. */
const MAX_DIGITS = 12;

/**
 * An on-screen keypad for the alarm's PIN, the way a wall panel has one.
 *
 * Digits only, shown as dots. The code is still sent whole, when OK is
 * pressed: sending it a digit at a time would only let the controller —
 * or anyone watching the replies — learn which digits were right.
 *
 * Buttons rather than a text field, so the phone's own keyboard never sees
 * the PIN: keyboards learn and suggest what is typed into them. A physical
 * keyboard still works — digits, Backspace, Enter, Escape.
 */
export default function PinPad({
  value,
  onChange,
  onSubmit,
  onCancel,
  message,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  /** Error or lockout line under the dots. */
  message?: React.ReactNode;
  /** While codes are locked: nothing can be typed or sent. */
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);

  // Focus the pad so a physical keyboard types into it straight away.
  useEffect(() => {
    ref.current?.focus();
  }, []);

  const press = (digit: string) => {
    if (disabled || value.length >= MAX_DIGITS) return;
    onChange(value + digit);
  };
  const erase = () => {
    if (!disabled) onChange(value.slice(0, -1));
  };
  const submit = () => {
    if (!disabled && value.length > 0) onSubmit();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (/^[0-9]$/.test(e.key)) press(e.key);
    else if (e.key === 'Backspace') erase();
    else if (e.key === 'Enter') submit();
    else if (e.key === 'Escape') onCancel();
    else return;
    e.preventDefault();
    e.stopPropagation();
  };

  const key = 'btn h-12 min-h-12 text-lg font-medium tabular-nums';

  return (
    <div
      ref={ref}
      tabIndex={0}
      onKeyDown={onKeyDown}
      role="group"
      aria-label={t('templates.enter_pin')}
      className="flex flex-col gap-2 outline-none"
    >
      {/* The dots, or what to do when there are none yet. */}
      <div
        className={clsx(
          'h-11 flex items-center justify-center rounded-[var(--radius-field)] border border-base-content/15 bg-base-100',
          message && !disabled && 'border-error',
        )}
        aria-live="polite"
      >
        {value.length > 0 ? (
          <span className="text-2xl tracking-[0.35em] leading-none" aria-label={t('templates.pin_digits', { n: value.length })}>
            {'•'.repeat(value.length)}
          </span>
        ) : (
          <span className="text-sm text-base-content/50">{t('templates.enter_pin')}</span>
        )}
      </div>
      {message && <p className={clsx('text-xs text-center', disabled ? 'text-warning' : 'text-error')}>{message}</p>}

      <div className="grid grid-cols-3 gap-2">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(d => (
          <button key={d} type="button" className={key} onClick={() => press(d)} disabled={disabled}>
            {d}
          </button>
        ))}
        <button
          type="button"
          className={clsx(key, 'btn-ghost')}
          onClick={erase}
          disabled={disabled || value.length === 0}
          aria-label={t('templates.pin_backspace')}
          title={t('templates.pin_backspace')}
        >
          <FaBackspace className="w-5 h-5" />
        </button>
        <button type="button" className={key} onClick={() => press('0')} disabled={disabled}>
          0
        </button>
        <button
          type="button"
          className={clsx(key, 'btn-primary')}
          onClick={submit}
          disabled={disabled || value.length === 0}
          aria-label="OK"
        >
          <FaCheck className="w-4 h-4" />
        </button>
      </div>
      <button type="button" className={clsx(TILE_BUTTON, 'btn-ghost')} onClick={onCancel}>
        {t('templates.cancel')}
      </button>
    </div>
  );
}
