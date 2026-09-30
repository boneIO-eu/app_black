/**
 * One-line hint under a boneIO pin select (input or output).
 *
 * Shows how many pins are still free. The "all used" warning appears only
 * when nothing is selected and nothing is left to pick — an item that already
 * owns its pin is not in trouble just because the rest are taken.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface PinAvailabilityHintProps {
  /** Pins not used by any other item (the current pin counts as available). */
  available: string[];
  /** Every pin the board has. */
  total: number;
  /** Pin selected in the form, if any. */
  current: string | undefined;
  /** Message shown when there is nothing left to choose. */
  allUsedMessage: string;
}

const PinAvailabilityHint: React.FC<PinAvailabilityHintProps> = ({
  available,
  total,
  current,
  allUsedMessage,
}) => {
  const { t } = useTranslation();

  const free = current
    ? available.filter((pin) => pin.toUpperCase() !== current.toUpperCase()).length
    : available.length;

  if (!current && free === 0) {
    return (
      <label className="label">
        <span className="label-text-alt text-warning whitespace-normal">{allUsedMessage}</span>
      </label>
    );
  }

  return (
    <label className="label">
      <span className="label-text-alt">{t('common.pins_free', { free, total })}</span>
    </label>
  );
};

export default PinAvailabilityHint;
