/**
 * The live part of the long-press card, per entity kind.
 *
 * Outputs and inputs get a layout of their own: the tile squeezes the state
 * into a switch or a pill, and the card has the room to say it in words and
 * since when. Everything with richer controls of its own — covers, Modbus,
 * templates, irrigation — is shown with the component its tile already uses,
 * so there is one set of controls to keep working, not two.
 */
import React, { useCallback, useState } from 'react';
import clsx from 'clsx';
import { FaLock } from 'react-icons/fa';
import { MdTimer, MdBrightnessHigh } from 'react-icons/md';
import { useTranslation } from '@/hooks/useTranslation';
import { useNow } from '@/hooks/useEntityHistory';
import type { InputEvent } from '@/hooks/useWebSocket';
import RangeSlider from '../RangeSlider';
import { formatDuration, type EntityData } from '../EntityCard';
import { formatAgo, formatClock, inputValueLabel, outputValueLabel } from './format';

/** "od 20:45 · 2 godz. temu", counting while the card is open. */
function Since({ timestamp }: { timestamp: number | null | undefined }) {
  const { t } = useTranslation();
  const now = useNow(!!timestamp);
  if (!timestamp) return <span className="text-sm text-base-content/50">{t('outputs.no_timestamp')}</span>;
  const at = timestamp * 1000;
  return (
    <span className="text-sm text-base-content/60" title={new Date(at).toLocaleString()}>
      {t('entity_card.since', { time: formatClock(at, now) })} · {formatAgo(at, now, t)}
    </span>
  );
}

/** The big state line every body starts with. */
function StateHero({ label, active, timestamp, aside }: {
  label: React.ReactNode;
  active: boolean;
  timestamp: number | null | undefined;
  aside?: React.ReactNode;
}) {
  return (
    <div className="stg-inset p-4 flex items-center gap-4">
      <div className="flex flex-col min-w-0 flex-1">
        <span className={clsx('text-2xl font-semibold', active ? 'text-primary' : 'text-base-content')}>{label}</span>
        <Since timestamp={timestamp} />
      </div>
      {aside}
    </div>
  );
}

/** Output, virtual switch, group, remote output. */
export function OutputCardBody({
  output,
  onToggle,
  onDurationChange,
  onBrightnessChange,
  error = null,
  stateOnly = false,
}: {
  output: EntityData;
  onToggle?: (id: string, name: string, type: string) => void;
  onDurationChange?: (id: string, value: number) => void;
  onBrightnessChange?: (id: string, value: number) => void;
  error?: string | null;
  stateOnly?: boolean;
}) {
  const { t } = useTranslation();
  const isOn = output.state === 'ON';
  const showDuration = output.adjustable_duration && output.adjustable_duration_value != null;
  const showBrightness = output.brightness != null && output.type === 'light' && output.remote;

  const handleDuration = useCallback((v: number) => onDurationChange?.(output.id, v), [onDurationChange, output.id]);
  const handleBrightness = useCallback((v: number) => onBrightnessChange?.(output.id, v), [onBrightnessChange, output.id]);

  return (
    <div className="flex flex-col gap-3">
      <StateHero
        label={outputValueLabel(output.state, t)}
        active={isOn}
        timestamp={output.timestamp}
        aside={!stateOnly && onToggle ? (
          <input
            type="checkbox"
            className="toggle toggle-primary toggle-lg"
            checked={isOn}
            disabled={error !== null}
            onChange={() => onToggle(output.id, output.name, output.type)}
            aria-label={output.name}
          />
        ) : undefined}
      />

      {showBrightness && (
        <RangeSlider
          value={output.brightness!}
          min={0}
          max={255}
          onChange={handleBrightness}
          variant="warning"
          icon={<MdBrightnessHigh className="text-sm text-yellow-500" />}
          formatValue={(v) => `${Math.round((v / 255) * 100)}%`}
          withContainer
        />
      )}

      {showDuration && (
        <RangeSlider
          value={output.adjustable_duration_value!}
          min={output.duration_min ?? 1}
          max={output.duration_max ?? 3600}
          onChange={handleDuration}
          variant="primary"
          icon={<MdTimer className="text-sm" />}
          formatValue={formatDuration}
          withContainer
        />
      )}

      {output.interlock_groups && output.interlock_groups.length > 0 && (
        <div className="flex items-center gap-2 text-sm text-base-content/60">
          <FaLock className="w-3 h-3 shrink-0" />
          <span>{t('outputs.interlock')}:</span>
          <span className="flex flex-wrap gap-1">
            {output.interlock_groups.map(g => <span key={g} className="badge badge-sm badge-outline">{g}</span>)}
          </span>
        </div>
      )}

      {error && <p className="text-sm text-error">{error}</p>}
    </div>
  );
}

/** Local or remote input, event entity or binary sensor. */
export function InputCardBody({ inputEvent }: { inputEvent: InputEvent }) {
  const { t } = useTranslation();
  const s = inputEvent.state;
  const isEvent = s.type === 'input';
  const value = s.state;
  const hasValue = !!value && value !== 'Unknown';
  // Flash for events that arrive while the card is open, not for opening it.
  const [openedAt] = useState(s.timestamp);

  return (
    <div className="flex flex-col gap-3">
      {/* Keyed on the timestamp, so a new click replays the flash even when
          it is the same click type as the last one. */}
      <div key={s.timestamp} className={s.timestamp !== openedAt ? 'animate-[entity-card-flash_1.2s_ease-out]' : undefined}>
        <StateHero
          label={hasValue ? inputValueLabel(value, t) : t('entity_card.no_event_yet')}
          active={hasValue}
          timestamp={hasValue ? s.timestamp : null}
          aside={value === 'long' && inputEvent.duration != null ? (
            <span className="text-lg tabular-nums text-base-content/60">{inputEvent.duration.toFixed(1)} s</span>
          ) : undefined}
        />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-base-content/60">
        <span>{t('inputs.type')}: {isEvent ? t('inputs.event_entity') : t('inputs.binary_sensor')}</span>
        {s.boneio_input && <span>{t('inputs.boneio_input')}: {s.boneio_input}</span>}
      </div>
    </div>
  );
}
