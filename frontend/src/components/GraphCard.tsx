/**
 * GraphCard — reusable sensor card with sparkline chart.
 *
 * Displays a sensor name, current value + unit, timestamp,
 * and a sparkline chart showing value history over time.
 *
 * Can be used in SensorView, ModbusView, or any future view
 * that needs to display numeric sensor data with a mini chart.
 */
import { memo } from 'react';
import { formatTimestamp } from '../utils/formatters';
import Sparkline, { type HistoryPoint } from './Sparkline';

export interface GraphCardProps {
  /** Sensor/entity unique ID */
  id: string;
  /** Display name */
  name: string;
  /** Current value (numeric or string) */
  value: number | string | null;
  /** Unit of measurement (e.g. °C, V, %) */
  unit?: string | null;
  /** Timestamp of last update (unix seconds) */
  timestamp?: number | null;
  /** History points for sparkline */
  historyPoints?: HistoryPoint[];
  /** Whether to render in grid (compact) or list (horizontal) mode */
  isGrid: boolean;
  /** Border accent color CSS class (default: border-emerald-500) */
  accentColor?: string;
  /** Sparkline stroke color (default: #10b981 — emerald-500) */
  strokeColor?: string;
  /** Sparkline fill color (default: semi-transparent emerald) */
  fillColor?: string;
  /** Optional subtitle below the name (e.g. sensor id) */
  subtitle?: string;
}

/** Format a numeric/string value for display */
function formatValue(value: number | string | null): string {
  if (value === null || value === undefined) return 'N/A';
  if (typeof value === 'number') return value.toFixed(2);
  return value;
}

function GraphCardBase({
  id,
  name,
  value,
  unit,
  timestamp,
  historyPoints = [],
  isGrid,
  accentColor = 'border-emerald-500',
  strokeColor = '#10b981',
  fillColor = 'rgba(16, 185, 129, 0.10)',
  subtitle,
}: GraphCardProps) {
  const hasChart = historyPoints.length > 1;

  // Grid layout — compact card with chart below
  if (isGrid) {
    return (
      <div
        className={`overflow-hidden rounded-lg border-l-4 ${accentColor} bg-base-200 p-4 shadow-sm transition-all duration-300 ${hasChart ? 'min-h-[166px]' : 'min-h-[88px]'} h-full flex flex-col`}
      >
        <div className="grid grid-cols-[1fr_auto] gap-4 min-h-[78px]">
          <div className="min-w-0">
            <h3 className="font-semibold text-lg leading-tight truncate">
              {name}
            </h3>
            <p className="mt-1 text-sm text-base-content/65 leading-5 line-clamp-2 break-all min-h-[40px]">
              {subtitle ?? id}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <div className="flex items-baseline justify-end gap-2">
              <span className="text-2xl font-mono leading-none">
                {formatValue(value)}
              </span>
              {unit && (
                <span className="text-base-content/70 text-sm">{unit}</span>
              )}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              {formatTimestamp(timestamp ?? null)}
            </p>
          </div>
        </div>

        {hasChart && (
          <div className="mt-auto overflow-hidden rounded-md border border-base-content/8 bg-base-100/65 px-2 py-1.5">
            <div className="relative h-[48px] w-full overflow-hidden opacity-90">
              <Sparkline
                points={historyPoints}
                strokeColor={strokeColor}
                fillColor={fillColor}
              />
            </div>
          </div>
        )}
      </div>
    );
  }

  // List layout — horizontal card with inline chart
  return (
    <div
      className={`relative overflow-hidden bg-base-200 shadow-sm rounded-lg p-4 border-l-8 ${accentColor} min-h-[84px] transition-all duration-300`}
    >
      <div className="relative z-10 flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-lg">{name}</h3>
          <p className="text-sm text-base-content/70">{subtitle ?? id}</p>
        </div>
        {hasChart && (
          <div className="relative h-[56px] w-[180px] shrink-0 overflow-hidden opacity-85">
            <Sparkline
              points={historyPoints}
              strokeColor={strokeColor}
              fillColor={fillColor}
            />
          </div>
        )}
        <div className="text-right shrink-0">
          <div className="flex items-baseline gap-2 justify-end">
            <span className="text-2xl font-mono">
              {formatValue(value)}
            </span>
            {unit && (
              <span className="text-base-content/70">{unit}</span>
            )}
          </div>
          <p className="text-gray-500 text-xs mt-2">
            {formatTimestamp(timestamp ?? null)}
          </p>
        </div>
      </div>
    </div>
  );
}

function areEqual(prev: GraphCardProps, next: GraphCardProps): boolean {
  const prevLast = prev.historyPoints?.[prev.historyPoints.length - 1];
  const nextLast = next.historyPoints?.[next.historyPoints.length - 1];

  return (
    prev.id === next.id &&
    prev.name === next.name &&
    prev.value === next.value &&
    prev.unit === next.unit &&
    prev.timestamp === next.timestamp &&
    prev.isGrid === next.isGrid &&
    prev.accentColor === next.accentColor &&
    (prev.historyPoints?.length ?? 0) === (next.historyPoints?.length ?? 0) &&
    prevLast?.timestamp === nextLast?.timestamp &&
    prevLast?.value === nextLast?.value
  );
}

const GraphCard = memo(GraphCardBase, areEqual);

export default GraphCard;
