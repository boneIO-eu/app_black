import React from "react";
import { FaLightbulb } from 'react-icons/fa';
import { RiOutletLine } from "react-icons/ri";
import { GiValve } from "react-icons/gi";
import { formatTimestamp } from '../utils/formatters';
import { OutputState } from "@/hooks/useWebSocket";

interface OutputItemProps {
  output: OutputState;
  onToggle: (id: string, name: string, type: string) => void;
  isGrid: boolean;
  error: string | null;
}

// Returns icon component and ON color for given type
function getIconAndOnColor(type: string): { Icon: React.ElementType, onColor: string } {
  switch (type) {
    case 'valve':
      return { Icon: GiValve, onColor: 'text-blue-500' };
    case 'switch':
      return { Icon: RiOutletLine, onColor: 'text-yellow-400' };
    case 'light':
      return { Icon: FaLightbulb, onColor: 'text-yellow-400' };
    default:
      return { Icon: FaLightbulb, onColor: 'text-yellow-400' };
  }
}

const OutputItem: React.FC<OutputItemProps> = ({
  output,
  onToggle,
  isGrid,
  error,
}) => { 
  const { Icon, onColor } = getIconAndOnColor(output.type);
  return (
  <div className={`bg-base-100 shadow-sm rounded-lg p-4 ${isGrid ? '' : 'flex justify-between items-center'}`}>
    <div className={`flex items-center gap-3 ${isGrid ? 'mb-3' : ''}`}>
      <Icon className={`text-xl ${output.state === 'ON' ? onColor : 'text-gray-400'}`} />
      <span className="text-lg">{output.name}</span>
    </div>
    <div className={`${isGrid ? '' : 'flex flex-col items-end gap-2'}`}>
      <label className="relative inline-flex items-center cursor-pointer">
        <input
          type="checkbox"
          className="sr-only peer"
          checked={output.state === 'ON'}
          disabled={error !== null}
          onChange={() => onToggle(output.id, output.name, output.type)}
        />
        <div className={`w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 \
          peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer \
          dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white \
          after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white \
          after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 \
          after:transition-all dark:border-gray-600 peer-checked:bg-blue-600`}></div>
      </label>
      <p className="text-gray-500 text-xs mt-2">
        {formatTimestamp(output.timestamp ?? null)}
      </p>
    </div>
  </div>
)};

export default OutputItem;
