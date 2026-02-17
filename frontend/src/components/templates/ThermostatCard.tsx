import { useTranslation } from '@/hooks/useTranslation';
import { FaPowerOff, FaFire, FaMinus, FaPlus } from 'react-icons/fa';
import type { ThermostatState } from './types';

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

  return (
    <div className="rounded-xl bg-base-100 shadow-sm px-4 py-6 flex items-center gap-3 max-w-xs w-full">
      {/* Power toggle */}
      <button
        className={`btn btn-circle btn-sm ${isOff ? 'btn-ghost opacity-40' : isHeating ? 'btn-error' : 'btn-primary'}`}
        onClick={() => onSetMode(data.id, isOff ? 'heat' : 'off')}
        title={isOff ? t('templates.turn_on') : t('templates.turn_off')}
      >
        {isOff ? <FaPowerOff className="h-3.5 w-3.5" /> : <FaFire className="h-3.5 w-3.5" />}
      </button>

      {/* Name + current temp */}
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm truncate">{data.name || data.id}</p>
        <p className="text-xs text-base-content/50">
          {data.current_temperature != null ? `${data.current_temperature.toFixed(1)}°C` : '—'}
          {isHeating && <span className="text-red-500 ml-1.5">{t('templates.heating')}</span>}
          {!isHeating && !isOff && <span className="ml-1.5">{t('templates.idle')}</span>}
          {isOff && <span className="ml-1.5">{t('templates.off')}</span>}
        </p>
      </div>

      {/* Target temperature control */}
      {!isOff && (
        <div className="flex items-center gap-1.5">
          <button
            className="btn btn-xs btn-circle btn-ghost"
            onClick={() => onSetTemp(data.id, data.target_temperature - 0.5)}
          >
            <FaMinus className="h-2.5 w-2.5" />
          </button>
          <span className="text-sm font-bold tabular-nums w-12 text-center">
            {data.target_temperature.toFixed(1)}°
          </span>
          <button
            className="btn btn-xs btn-circle btn-ghost"
            onClick={() => onSetTemp(data.id, data.target_temperature + 0.5)}
          >
            <FaPlus className="h-2.5 w-2.5" />
          </button>
        </div>
      )}
    </div>
  );
}
