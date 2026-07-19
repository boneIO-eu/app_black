import React, { useRef, useCallback } from "react";
import { FaLightbulb, FaLock, FaWifi } from 'react-icons/fa';
import { HiLightBulb } from 'react-icons/hi';
import { RiOutletLine } from "react-icons/ri";
import { GiValve } from "react-icons/gi";
import { MdTimer, MdBrightnessHigh } from "react-icons/md";
import { formatTimestamp } from '../utils/formatters';

import { ImSwitch } from "react-icons/im";
import { useTranslation } from '@/hooks/useTranslation';
import { suppressNextPointerRelease } from '@/utils/longPress';
import RangeSlider from './RangeSlider';

// Color palette for interlock groups - each group gets a consistent color
const INTERLOCK_COLORS = [
  'bg-red-500',
  'bg-blue-500',
  'bg-green-500',
  'bg-purple-500',
  'bg-orange-500',
  'bg-pink-500',
  'bg-cyan-500',
  'bg-amber-500',
  'bg-lime-500',
  'bg-indigo-500',
];

// Simple hash function to get consistent color for a group name
function getInterlockColor(groupName: string): string {
  let hash = 0;
  for (let i = 0; i < groupName.length; i++) {
    hash = groupName.charCodeAt(i) + ((hash << 5) - hash);
  }
  return INTERLOCK_COLORS[Math.abs(hash) % INTERLOCK_COLORS.length];
}

/**
 * Format duration in seconds for display.
 */
function formatDuration(seconds: number): string {
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }
  if (seconds >= 60) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }
  return `${Math.round(seconds)}s`;
}

/**
 * Common entity data shape used by OutputItem for both outputs and inputs.
 * OutputState satisfies this naturally. For inputs, map InputEvent to this shape.
 */
export interface EntityData {
  id: string;
  name: string;
  state: string;
  type: string;
  timestamp: number | null;
  area?: string | null;
  remote?: boolean;
  // Output-specific (optional)
  interlock_groups?: string[];
  adjustable_duration?: boolean;
  adjustable_duration_value?: number | null;
  duration_min?: number | null;
  duration_max?: number | null;
  brightness?: number | null;
}

interface OutputItemProps {
  output: EntityData;
  onToggle?: (id: string, name: string, type: string) => void;
  onDurationChange?: (id: string, value: number) => void;
  onBrightnessChange?: (id: string, value: number) => void;
  isGrid: boolean;
  error?: string | null;
  stateOnly?: boolean;
  isGroup?: boolean;
  isHighlighted?: boolean;
  onLongPress?: (output: EntityData) => void;
  /** Custom icon slot — overrides the default type-based icon. */
  iconSlot?: React.ReactNode;
  /** Custom action slot — replaces the toggle/badge area entirely. */
  actionSlot?: React.ReactNode;
  /** Title text for hover/accessibility. */
  longPressTitle?: string;
}

// Returns icon component and ON color for given type
function getIconAndOnColor(type: string, isGroup: boolean = false): { Icon: React.ElementType, onColor: string } {
  // For groups with light type, use group light icon
  if (isGroup && type === 'light') {
    return { Icon: HiLightBulb, onColor: 'text-yellow-400' };
  }

  switch (type) {
    case 'valve':
      return { Icon: GiValve, onColor: 'text-blue-500' };
    case 'switch':
      return { Icon: RiOutletLine, onColor: 'text-yellow-400' };
    case 'light':
      return { Icon: FaLightbulb, onColor: 'text-yellow-400' };
    default:
      return { Icon: ImSwitch, onColor: 'text-yellow-400' };
  }
}

/**
 * Reusable entity card component for outputs, inputs, and other entity types.
 *
 * For outputs: uses default icon (lightbulb/valve/switch) and toggle/badge action.
 * For inputs: pass `iconSlot` (⚡ or ◉) and `actionSlot` (state badge) to customize.
 */
const EntityCard: React.FC<OutputItemProps> = ({
  output,
  onToggle,
  onDurationChange,
  onBrightnessChange,
  isGrid,
  error = null,
  stateOnly = false,
  isGroup = false,
  isHighlighted = false,
  onLongPress,
  iconSlot,
  actionSlot,
  longPressTitle,
}) => {
  const { t } = useTranslation();
  const { Icon, onColor } = getIconAndOnColor(output.type, isGroup);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isLongPressRef = useRef(false);

  const handlePressStart = () => {
    if (!onLongPress) return;
    isLongPressRef.current = false;
    longPressTimer.current = setTimeout(() => {
      isLongPressRef.current = true;
      suppressNextPointerRelease();
      onLongPress(output);
    }, 500);
  };

  const handlePressEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  const showDuration = output.adjustable_duration && output.adjustable_duration_value != null;
  const showBrightness = output.brightness != null && output.type === 'light' && output.remote;

  const handleDurationSliderChange = useCallback(
    (value: number) => onDurationChange?.(output.id, value),
    [onDurationChange, output.id],
  );

  const handleBrightnessSliderChange = useCallback(
    (value: number) => onBrightnessChange?.(output.id, value),
    [onBrightnessChange, output.id],
  );

  return (
    <div
      className={`bg-base-100 shadow-sm rounded-lg p-4 transition-all duration-500 select-none flex ${isGrid ? 'flex-col' : 'justify-between items-center'} ${isHighlighted ? 'ring-4 ring-primary shadow-lg shadow-primary/30 scale-[1.02]' : ''} ${onLongPress ? 'cursor-pointer' : ''}`}
      onMouseDown={handlePressStart}
      onMouseUp={handlePressEnd}
      onMouseLeave={handlePressEnd}
      onTouchStart={handlePressStart}
      onTouchEnd={handlePressEnd}
      title={onLongPress ? (longPressTitle || t('outputs.long_press_to_edit')) : undefined}
    >
      <div className={`flex items-center gap-3 ${isGrid ? 'mb-3' : ''}`}>
        {iconSlot || <Icon className={`text-xl ${output.state === 'ON' ? onColor : 'text-gray-400'}`} />}
        <div className="flex flex-col min-w-0">
          <span className="text-lg truncate">{output.name}</span>
          <span className="text-xs text-gray-500 truncate">
            {output.id}
            {output.remote && <FaWifi className="inline ml-1 text-blue-400 shrink-0" title="Remote" />}
          </span>
          <span className="text-xs text-gray-400 truncate">{t('outputs.area_short')}: {output.area || t('outputs.no_area')}</span>
          {output.interlock_groups && output.interlock_groups.length > 0 && (
            <div className="flex items-center gap-1 mt-1">
              <FaLock className="text-xs text-gray-400" />
              {output.interlock_groups.map((group) => (
                <span
                  key={group}
                  className={`text-xs px-1.5 py-0.5 rounded text-white ${getInterlockColor(group)}`}
                  title={`Interlock: ${group}`}
                >
                  {group}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className={`${isGrid ? 'flex-1 flex flex-col items-start' : 'flex flex-col items-end gap-2'}`}>
        {actionSlot ? (
          // Custom action slot (e.g. input state badge)
          actionSlot
        ) : stateOnly ? (
          // State only - show badge instead of toggle
          <span className={`badge ${output.state === 'ON' ? 'badge-success' : 'badge-neutral'}`}>
            {output.state}
          </span>
        ) : (
          // Interactive toggle
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={output.state === 'ON'}
              disabled={error !== null || !onToggle}
              onChange={() => onToggle?.(output.id, output.name, output.type)}
            />
            <div className={`w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 \
                peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer \
                dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white \
                after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white \
                after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 \
                after:transition-all dark:border-gray-600 peer-checked:bg-blue-600`}></div>
          </label>
        )}

        {/* Adjustable duration slider */}
        {showDuration && (
          <RangeSlider
            value={output.adjustable_duration_value!}
            min={output.duration_min ?? 1}
            max={output.duration_max ?? 3600}
            onChange={handleDurationSliderChange}
            variant="primary"
            icon={<MdTimer className="text-sm" />}
            formatValue={formatDuration}
          />
        )}

        {/* Brightness slider for dimmable remote lights */}
        {showBrightness && (
          <RangeSlider
            value={output.brightness!}
            min={0}
            max={255}
            onChange={handleBrightnessSliderChange}
            variant="warning"
            icon={<MdBrightnessHigh className="text-sm text-yellow-500" />}
            formatValue={(v) => `${Math.round((v / 255) * 100)}%`}
          />
        )}

        <p
          className={`text-gray-500 text-xs whitespace-nowrap ${isGrid ? 'mt-auto pt-2' : 'mt-2'}`}
          title={output.timestamp ? undefined : t('outputs.no_timestamp')}
        >
          {formatTimestamp(output.timestamp ?? null)}
        </p>
      </div>
    </div>
  );
};

export default EntityCard;
