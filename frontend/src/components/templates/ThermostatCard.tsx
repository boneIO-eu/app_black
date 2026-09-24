import { useTranslation } from '@/hooks/useTranslation';
import { FaPowerOff, FaMinus, FaPlus, FaThermometerHalf } from 'react-icons/fa';
import clsx from 'clsx';
import type { ThermostatState } from './types';
import { TemplateTile } from './TemplateTile';
import { TILE_BUTTON, type Tone } from './tileStyles';

export default function ThermostatCard({
  data,
  onSetMode,
  onSetTemp,
}: {
  data: ThermostatState;
  onSetMode: (id: string, mode: string) => void;
  onSetTemp: (id: string, temp: number) => void;
}) {
  const { t } = useTranslation();
  const isOff = data.mode === 'off';
  const isHeating = data.action === 'heating';

  const tone: Tone = isOff ? 'neutral' : isHeating ? 'warning' : 'info';
  const state = isOff ? t('templates.off') : isHeating ? t('templates.heating') : t('templates.idle');

  return (
    <TemplateTile
      icon={FaThermometerHalf}
      tone={tone}
      name={data.name || data.id}
      state={state}
      // Off, the footer's own "Turn on" is the way back; a second power
      // button beside the name would only say the same thing twice.
      action={isOff ? undefined : (
        <button
          type="button"
          className="btn btn-ghost btn-circle w-11 h-11 min-h-11"
          onClick={() => onSetMode(data.id, 'off')}
          title={t('templates.turn_off')}
          aria-label={t('templates.turn_off')}
        >
          <FaPowerOff className="w-4 h-4" />
        </button>
      )}
      footer={
        isOff ? (
          <button type="button" className={clsx(TILE_BUTTON, 'w-full')} onClick={() => onSetMode(data.id, 'heat')}>
            <FaPowerOff className="w-4 h-4" />
            {t('templates.turn_on')}
          </button>
        ) : (
          <div className="grid grid-cols-[2.75rem_1fr_2.75rem] items-center gap-2">
            <button
              type="button"
              className={clsx(TILE_BUTTON, 'px-0')}
              onClick={() => onSetTemp(data.id, data.target_temperature - 0.5)}
              aria-label={`${t('templates.target')} −0.5°`}
            >
              <FaMinus className="w-3.5 h-3.5" />
            </button>
            <div className="flex flex-col items-center leading-tight">
              <span className="text-lg font-semibold tabular-nums">{data.target_temperature.toFixed(1)}°</span>
              <span className="text-xs text-base-content/60">{t('templates.target')}</span>
            </div>
            <button
              type="button"
              className={clsx(TILE_BUTTON, 'px-0')}
              onClick={() => onSetTemp(data.id, data.target_temperature + 0.5)}
              aria-label={`${t('templates.target')} +0.5°`}
            >
              <FaPlus className="w-3.5 h-3.5" />
            </button>
          </div>
        )
      }
    >
      {/* The reading is the thing you came to see, so it is the largest text on the tile. */}
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold tabular-nums leading-none">
          {data.current_temperature != null ? `${data.current_temperature.toFixed(1)}°` : '—'}
        </span>
        <span className="text-sm text-base-content/60">{t('templates.now')}</span>
      </div>
    </TemplateTile>
  );
}
