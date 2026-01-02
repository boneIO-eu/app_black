import React from "react";
import { FaLightbulb, FaLock } from 'react-icons/fa';
import { HiLightBulb } from 'react-icons/hi';
import { RiOutletLine } from "react-icons/ri";
import { GiValve } from "react-icons/gi";
import { formatTimestamp } from '../utils/formatters';
import { OutputState } from "@/hooks/useWebSocket";
import { ImSwitch } from "react-icons/im";
import { useTranslation } from '@/hooks/useTranslation';

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

interface OutputItemProps {
  output: OutputState;
  onToggle?: (id: string, name: string, type: string) => void;
  isGrid: boolean;
  error: string | null;
  stateOnly?: boolean;
  isGroup?: boolean;
  isHighlighted?: boolean;
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

const OutputItem: React.FC<OutputItemProps> = ({
  output,
  onToggle,
  isGrid,
  error,
  stateOnly = false,
  isGroup = false,
  isHighlighted = false,
}) => { 
  const { t } = useTranslation();
  const { Icon, onColor } = getIconAndOnColor(output.type, isGroup);
  
  return (
    <div className={`bg-base-100 shadow-sm rounded-lg p-4 transition-all duration-500 ${isGrid ? '' : 'flex justify-between items-center'} ${isHighlighted ? 'ring-4 ring-primary shadow-lg shadow-primary/30 scale-[1.02]' : ''}`}>
      <div className={`flex items-center gap-3 ${isGrid ? 'mb-3' : ''}`}>
        <Icon className={`text-xl ${output.state === 'ON' ? onColor : 'text-gray-400'}`} />
        <div className="flex flex-col">
          <span className="text-lg">{output.name}</span>
          <span className="text-xs text-gray-500">{output.id}</span>
          <span className="text-xs text-gray-400">{t('outputs.area_short')}: {output.area || t('outputs.no_area')}</span>
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
      <div className={`${isGrid ? '' : 'flex flex-col items-end gap-2'}`}>
        {stateOnly ? (
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
        <p className="text-gray-500 text-xs mt-2">
          {formatTimestamp(output.timestamp ?? null)}
        </p>
      </div>
    </div>
  );
};

export default OutputItem;
