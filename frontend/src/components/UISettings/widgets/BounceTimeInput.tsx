/**
 * GPIO debounce time in milliseconds, 1–1000.
 *
 * The field can be emptied while typing a new value — an empty field writes
 * nothing, and leaving it empty shows the stored value again. Above the
 * maximum the value is capped as it is typed, so a save never sees it; below
 * the minimum it is raised when the field loses focus.
 */
import React from 'react';
import { NumericInput } from '@/components/ui/NumericInput';
import { convertTimeperiodToMilliseconds } from '../helpers/configSchemaUtils';

export const BOUNCE_TIME_MIN_MS = 1;
export const BOUNCE_TIME_MAX_MS = 1000;

interface BounceTimeInputProps {
  /** Stored bounce_time: a number of ms, a string like "120ms", or unset. */
  value: unknown;
  /** Called with the new value in milliseconds. */
  onChange: (ms: number) => void;
  /** Shown when nothing is stored. */
  defaultMs: number;
  id?: string;
}

const BounceTimeInput: React.FC<BounceTimeInputProps> = ({ value, onChange, defaultMs, id }) => {
  const stored = value === undefined || value === null || value === ''
    ? defaultMs
    : convertTimeperiodToMilliseconds(value);

  return (
    <NumericInput
      id={id}
      value={stored}
      min={BOUNCE_TIME_MIN_MS}
      max={BOUNCE_TIME_MAX_MS}
      placeholder={String(defaultMs)}
      onChange={(v) => {
        if (v !== '') onChange(v);
      }}
    />
  );
};

export default BounceTimeInput;
