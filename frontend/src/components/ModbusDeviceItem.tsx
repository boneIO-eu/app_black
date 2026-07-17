import { memo, useEffect, useState } from 'react';
import { formatTimestamp } from '../utils/formatters';
import { ModbusDeviceState } from '../hooks/useWebSocket';
import { useTranslation } from '../hooks/useTranslation';
import { ModbusHistoryPoint } from '../hooks/useModbusHistory';
import Sparkline from './Sparkline';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export interface ModbusDeviceItemProps {
  device: ModbusDeviceState;
  isGrid: boolean;
  historyPoints?: ModbusHistoryPoint[];
  onValueChange: (coordinatorId: string, entityId: string, value: string | number) => void;
  /** Card border accent color class (default: border-blue-500) */
  accentColor?: string;
  /** Sparkline stroke color (default: #0284c7) */
  strokeColor?: string;
  /** Sparkline fill color (default: semi-transparent blue) */
  fillColor?: string;
}

function extractEntityId(device: ModbusDeviceState): string {
  let entityId = device.id.startsWith(device.coordinator_id)
    ? device.id.slice(device.coordinator_id.length)
    : device.id;

  if (entityId.startsWith('_')) {
    entityId = entityId.slice(1);
  }

  return entityId;
}

function ModbusDeviceItemBase({ device, isGrid, historyPoints, onValueChange, accentColor = 'border-blue-500', strokeColor = '#0284c7', fillColor = 'rgba(96, 165, 250, 0.10)' }: ModbusDeviceItemProps) {
  const { t } = useTranslation();

  const handleSelectChange = (value: string) => {
    onValueChange(device.coordinator_id, extractEntityId(device), value);
  };

  const handleSwitchToggle = (checked: boolean) => {
    if (!device.payload_on || !device.payload_off) {
      return;
    }

    const value = checked ? device.payload_on : device.payload_off;
    onValueChange(device.coordinator_id, extractEntityId(device), value);
  };

  const handleWriteableSensorChange = (value: string) => {
    const numValue = parseFloat(value);
    if (!Number.isNaN(numValue)) {
      onValueChange(device.coordinator_id, extractEntityId(device), numValue);
      return;
    }

    onValueChange(device.coordinator_id, extractEntityId(device), value);
  };

  const isSelect = device.entity_type === 'select' && device.x_mapping;
  const isSwitch = device.entity_type === 'switch' && device.x_mapping && device.payload_on && device.payload_off;
  const isNumber = device.entity_type === 'number';

  const switchChecked = Boolean(isSwitch && device.state === device.payload_on);

  const currentValue = device.state !== null && device.state !== undefined ? device.state.toString() : '';
  const [inputValue, setInputValue] = useState<string>(currentValue);

  useEffect(() => {
    setInputValue(currentValue);
  }, [currentValue]);

  if (isSelect) {
    const options = Object.entries(device.x_mapping || {}).map(([key, label]) => ({
      value: label as string,
      key,
    }));

    return (
      <div className={`bg-base-100 shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4 min-h-[88px] h-full' : 'border-l-8 min-h-[72px]'} ${accentColor} transition-all duration-300`}>
        <div className={`flex ${isGrid ? 'flex-col gap-3' : 'justify-between items-center'}`}>
          <div>
            <h3 className="font-semibold text-lg">{device.custom_label || device.name}</h3>
            <p className="text-sm text-base-content/70">{device.id}</p>
          </div>
          <div 
            className={`${isGrid ? 'w-full' : 'w-[280px] shrink-0'}`}
            onMouseDown={(e) => e.stopPropagation()}
            onMouseUp={(e) => e.stopPropagation()}
            onTouchStart={(e) => e.stopPropagation()}
            onTouchEnd={(e) => e.stopPropagation()}
          >
            <Select value={(device.state as string) || undefined} onValueChange={handleSelectChange}>
              <SelectTrigger size="sm" className="w-full">
                <SelectValue placeholder="—" />
              </SelectTrigger>
              <SelectContent>
                {options.map((option) => (
                  <SelectItem key={option.key} value={option.value}>
                    {option.value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className={`text-gray-500 text-xs mt-2 ${!isGrid ? 'text-right' : ''}`}>{formatTimestamp(device?.timestamp ?? null)}</p>
          </div>
        </div>
      </div>
    );
  }

  if (isSwitch) {
    return (
      <div className={`bg-base-100 shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4 min-h-[88px] h-full' : 'border-l-8 min-h-[72px]'} ${accentColor} transition-all duration-300`}>
        <div className={`flex ${isGrid ? 'flex-col gap-3' : 'justify-between items-center'}`}>
          <div>
            <h3 className="font-semibold text-lg">{device.custom_label || device.name}</h3>
            <p className="text-sm text-base-content/70">{device.id}</p>
          </div>
          <div 
            className={`${isGrid ? 'w-full' : 'flex flex-col items-end gap-2'}`}
            onMouseDown={(e) => e.stopPropagation()}
            onMouseUp={(e) => e.stopPropagation()}
            onTouchStart={(e) => e.stopPropagation()}
            onTouchEnd={(e) => e.stopPropagation()}
          >
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={switchChecked}
                onChange={(e) => handleSwitchToggle(e.target.checked)}
              />
              <div className={`w-11 h-6 bg-gray-200 peer-focus:outline-hidden peer-focus:ring-4 \
                peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer \
                dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white \
                after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white \
                after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 \
                after:transition-all dark:border-gray-600 peer-checked:bg-blue-600`}></div>
            </label>
            <p className="text-gray-500 text-xs mt-2">{formatTimestamp(device?.timestamp ?? null)}</p>
          </div>
        </div>
      </div>
    );
  }

  if (isNumber) {
    const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        handleWriteableSensorChange(inputValue);
      }
    };

    const formatPlaceholder = (value: string | number | null) => {
      if (value === null || value === undefined) return t('modbus_view.enter_value');
      const numValue = typeof value === 'string' ? parseFloat(value) : value;
      if (Number.isNaN(numValue)) return t('modbus_view.enter_value');

      if (device.step && device.step < 1) {
        return numValue.toFixed(1);
      }
      return value.toString();
    };

    const isValueChanged = () => {
      if (inputValue === '') return false;
      const inputNum = parseFloat(inputValue);
      const currentNum = parseFloat(currentValue);
      return !Number.isNaN(inputNum) && !Number.isNaN(currentNum) && inputNum !== currentNum;
    };

    return (
      <div className={`bg-base-100 shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4 min-h-[88px] h-full' : 'border-l-8 min-h-[72px]'} ${accentColor} transition-all duration-300`}>
        <div className={`flex ${isGrid ? 'flex-col gap-3' : 'justify-between items-center'}`}>
          <div>
            <h3 className="font-semibold text-lg">{device.custom_label || device.name}</h3>
            <p className="text-sm text-base-content/70">{device.id}</p>
          </div>
          <div 
            className={`${isGrid ? 'w-full' : 'w-[280px] shrink-0'}`}
            onMouseDown={(e) => e.stopPropagation()}
            onMouseUp={(e) => e.stopPropagation()}
            onTouchStart={(e) => e.stopPropagation()}
            onTouchEnd={(e) => e.stopPropagation()}
          >
            <div className="flex gap-2 items-center">
              <input
                type="number"
                step={device.step || 1}
                className="input input-sm flex-1"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder={formatPlaceholder(device.state)}
              />
              {device.unit && <span className="text-sm text-base-content/70 whitespace-nowrap">{device.unit}</span>}
              <button
                className="btn btn-sm btn-primary"
                disabled={!isValueChanged()}
                onClick={() => handleWriteableSensorChange(inputValue)}
              >
                {t('modbus_view.set_button')}
              </button>
            </div>
            <p className={`text-gray-500 text-xs mt-2 ${!isGrid ? 'text-right' : ''}`}>{formatTimestamp(device?.timestamp ?? null)}</p>
          </div>
        </div>
      </div>
    );
  }

  const isLoading = device.state === null;
  const points = historyPoints || [];

  if (isGrid) {
    if (!device.unit) {
      return (
        <div className={`bg-base-100 shadow-sm rounded-lg p-4 border-l-4 min-h-[88px] h-full ${accentColor} transition-all duration-300`}>
          <div className="flex justify-between items-start">
            <div>
              <h3 className="font-semibold text-lg">{device.custom_label || device.name}</h3>
              <p className="text-sm text-base-content/70 break-all">{device.id}</p>
            </div>
            <div className="text-right shrink-0">
              <div className="flex items-baseline gap-2 justify-end">
                {isLoading ? (
                  <span className="inline-block h-8 w-20 bg-base-300 rounded animate-pulse" />
                ) : (
                  <span className="text-2xl font-mono">
                    {typeof device.state === 'number' ? device.state.toFixed(2) : device.state}
                  </span>
                )}
                {device.unit && <span className="text-base-content/70">{device.unit}</span>}
              </div>
              <p className="text-gray-500 text-xs mt-2">
                {isLoading ? (
                  <span className="inline-block h-3 w-12 bg-base-300 rounded animate-pulse" />
                ) : (
                  formatTimestamp(device?.timestamp ?? null)
                )}
              </p>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className={`overflow-hidden rounded-lg border-l-4 ${accentColor} bg-base-100 p-4 shadow-sm transition-all duration-300 min-h-[166px] h-full flex flex-col`}>
        <div className="grid grid-cols-[1fr_auto] gap-4 min-h-[78px]">
          <div className="min-w-0">
            <h3 className="font-semibold text-lg leading-tight truncate">{device.custom_label || device.name}</h3>
            <p className="mt-1 text-sm text-base-content/65 leading-5 line-clamp-2 break-all min-h-[40px]">{device.id}</p>
          </div>
          <div className="shrink-0 text-right">
            <div className="flex items-baseline justify-end gap-2">
              {isLoading ? (
                <span className="inline-block h-8 w-20 rounded bg-base-300 animate-pulse" />
              ) : (
                <span className="text-2xl font-mono leading-none">
                  {typeof device.state === 'number' ? device.state.toFixed(2) : device.state}
                </span>
              )}
              {device.unit && (
                <span className="text-base-content/70 text-sm">
                  {device.unit}
                </span>
              )}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              {isLoading ? (
                <span className="inline-block h-3 w-12 rounded bg-base-300 animate-pulse" />
              ) : (
                formatTimestamp(device?.timestamp ?? null)
              )}
            </p>
          </div>
        </div>

        <div className="mt-auto overflow-hidden rounded-md border border-base-content/8 bg-base-100/65 px-2 py-1.5">
          <div className="relative h-[48px] w-full overflow-hidden opacity-90">
            <Sparkline points={points} strokeColor={strokeColor} fillColor={fillColor} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden bg-base-100 shadow-sm rounded-lg p-4 border-l-8 min-h-[84px] ${accentColor} transition-all duration-300`}>
      <div className="relative z-10 flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-lg">{device.custom_label || device.name}</h3>
          <p className="text-sm text-base-content/70">{device.id}</p>
        </div>
        {device.unit && (
          <div className="relative h-[56px] w-[180px] shrink-0 overflow-hidden opacity-85">
            <Sparkline points={points} strokeColor={strokeColor} fillColor={fillColor} />
          </div>
        )}
        <div className="text-right shrink-0">
          <div className="flex items-baseline gap-2 justify-end">
            {isLoading ? (
              <span className="inline-block h-8 w-20 bg-base-300 rounded animate-pulse" />
            ) : (
              <span className="text-2xl font-mono">
                {typeof device.state === 'number' ? device.state.toFixed(2) : device.state}
              </span>
            )}
            {device.unit && <span className="text-base-content/70">{device.unit}</span>}
          </div>
          <p className="text-gray-500 text-xs mt-2">
            {isLoading ? (
              <span className="inline-block h-3 w-12 bg-base-300 rounded animate-pulse" />
            ) : (
              formatTimestamp(device?.timestamp ?? null)
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

function areEqual(prevProps: ModbusDeviceItemProps, nextProps: ModbusDeviceItemProps) {
  const prevHistory = prevProps.historyPoints || [];
  const nextHistory = nextProps.historyPoints || [];
  const prevHistoryLast = prevHistory[prevHistory.length - 1];
  const nextHistoryLast = nextHistory[nextHistory.length - 1];

  return prevProps.device.id === nextProps.device.id
    && prevProps.device.name === nextProps.device.name
    && prevProps.device.custom_label === nextProps.device.custom_label
    && prevProps.device.state === nextProps.device.state
    && prevProps.device.timestamp === nextProps.device.timestamp
    && prevProps.device.entity_type === nextProps.device.entity_type
    && JSON.stringify(prevProps.device.x_mapping || {}) === JSON.stringify(nextProps.device.x_mapping || {})
    && prevProps.device.payload_on === nextProps.device.payload_on
    && prevProps.device.payload_off === nextProps.device.payload_off
    && prevProps.isGrid === nextProps.isGrid
    && prevProps.accentColor === nextProps.accentColor
    && prevHistory.length === nextHistory.length
    && prevHistoryLast?.timestamp === nextHistoryLast?.timestamp
    && prevHistoryLast?.value === nextHistoryLast?.value;
}

const ModbusDeviceItem = memo(ModbusDeviceItemBase, areEqual);

export default ModbusDeviceItem;
