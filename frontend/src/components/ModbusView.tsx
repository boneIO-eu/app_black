import { useContext, memo, useState, useMemo, useEffect } from 'react';
import axios from 'axios';
import { WebSocketContext } from '../App';
import { formatTimestamp } from '../utils/formatters';
import ViewToggle from './ViewToggle';
import { isModbusDeviceEvent, ModbusDeviceState } from '../hooks/useWebSocket';

// Separate component for individual Modbus device - memoized by device.id and state
const ModbusDeviceItem = memo(({ device, isGrid, onValueChange }: {
  device: ModbusDeviceState;
  isGrid: boolean;
  onValueChange: (coordinatorId: string, entityId: string, value: string | number) => void;
}) => {
  const handleSelectChange = async (value: string) => {
    // Extract entity_id from device.id (format: {coordinator_id}{decoded_name})
    // or use decoded_name if it's available
    const entityId = device.id.startsWith(device.coordinator_id) 
      ? device.id.slice(device.coordinator_id.length) 
      : device.id;
    onValueChange(device.coordinator_id, entityId, value);
  };

  const handleSwitchToggle = async (checked: boolean) => {
    if (!device.x_mapping || !device.payload_on || !device.payload_off) {
      return;
    }
    const value = checked ? device.payload_on : device.payload_off;
    // Extract entity_id from device.id (format: {coordinator_id}{decoded_name})
    // or use decoded_name if it's available
    const entityId = device.id.startsWith(device.coordinator_id) 
      ? device.id.slice(device.coordinator_id.length) 
      : device.id;
    onValueChange(device.coordinator_id, entityId, value);
  };

  const handleWriteableSensorChange = async (value: string) => {
    // Extract entity_id from device.id (format: {coordinator_id}{decoded_name})
    const entityId = device.id.startsWith(device.coordinator_id) 
      ? device.id.slice(device.coordinator_id.length) 
      : device.id;
    
    // Convert string to number if possible
    const numValue = parseFloat(value);
    if (!isNaN(numValue)) {
      onValueChange(device.coordinator_id, entityId, numValue);
    } else {
      onValueChange(device.coordinator_id, entityId, value);
    }
  };

  // Check if it's a select or switch (additional entity)
  const isSelect = device.entity_type === 'select' && device.x_mapping;
  const isSwitch = device.entity_type === 'switch' && device.x_mapping && device.payload_on && device.payload_off;
  const isNumber = device.entity_type === 'number'

  // Get current switch state
  const switchChecked = isSwitch && device.state === device.payload_on ? true : false;

  // State for writeable sensor input
  const currentValue = device.state !== null 
    ? (typeof device.state === 'number' ? device.state.toString() : device.state.toString())
    : '';
  const [inputValue, setInputValue] = useState<string>(currentValue);

  // Update input value when device state changes
  useEffect(() => {
    const newValue = device.state !== null 
      ? (typeof device.state === 'number' ? device.state.toString() : device.state.toString())
      : '';
    setInputValue(newValue);
  }, [device.state]);

  // Render select dropdown
  if (isSelect) {
    const options = Object.entries(device.x_mapping || {}).map(([key, label]) => ({
      value: label as string,
      key,
    }));

    return (
      <div
        className={`bg-base-200 shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4' : 'border-l-8'} border-blue-500`}
      >
        <div className={`flex ${isGrid ? 'flex-col gap-3' : 'justify-between items-center'}`}>
          <div>
            <h3 className="font-semibold text-lg">{device.name}</h3>
            <p className="text-sm text-base-content/70">{device.id}</p>
          </div>
          <div className={`${isGrid ? 'w-full' : 'min-w-[200px]'}`}>
            <select
              className="select select-bordered w-full select-sm"
              value={device.state as string || ''}
              onChange={(e) => handleSelectChange(e.target.value)}
            >
              {options.map((option) => (
                <option key={option.key} value={option.value}>
                  {option.value}
                </option>
              ))}
            </select>
            <p className="text-gray-500 text-xs mt-2">
              {formatTimestamp(device?.timestamp ?? null)}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Render toggle switch
  if (isSwitch) {
    return (
      <div
        className={`bg-base-200 shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4' : 'border-l-8'} border-blue-500`}
      >
        <div className={`flex ${isGrid ? 'flex-col gap-3' : 'justify-between items-center'}`}>
          <div>
            <h3 className="font-semibold text-lg">{device.name}</h3>
            <p className="text-sm text-base-content/70">{device.id}</p>
          </div>
          <div className={`${isGrid ? 'w-full' : 'flex flex-col items-end gap-2'}`}>
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
            <p className="text-gray-500 text-xs mt-2">
              {formatTimestamp(device?.timestamp ?? null)}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Render writeable sensor (input field)
  if (isNumber) {
    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      setInputValue(e.target.value);
    };

    const handleInputKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        handleWriteableSensorChange(inputValue);
      }
    };

    return (
      <div
        className={`bg-base-200 shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4' : 'border-l-8'} border-green-500`}
      >
        <div className={`flex ${isGrid ? 'flex-col gap-3' : 'justify-between items-center'}`}>
          <div>
            <h3 className="font-semibold text-lg">{device.name}</h3>
            <p className="text-sm text-base-content/70">{device.id}</p>
          </div>
          <div className={`${isGrid ? 'w-full' : 'min-w-[200px]'}`}>
            <div className="flex gap-2 items-center">
              <input
                type="number"
                step="any"
                className="input input-bordered input-sm flex-1"
                value={inputValue}
                onChange={handleInputChange}
                onKeyPress={handleInputKeyPress}
                placeholder={currentValue || 'Enter value'}
              />
              {device.unit && (
                <span className="text-sm text-base-content/70 whitespace-nowrap">
                  {device.unit}
                </span>
              )}
              <button
                className="btn btn-sm btn-primary"
                onClick={() => handleWriteableSensorChange(inputValue)}
              >
                Set
              </button>
            </div>
            <p className="text-gray-500 text-xs mt-2">
              {formatTimestamp(device?.timestamp ?? null)}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Render regular sensor (numeric/text display)
  return (
    <div
      className={`bg-base-200 shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4' : 'border-l-8'} border-blue-500`}
    >
      <div className={`flex ${isGrid ? 'justify-between items-start' : 'justify-between items-start'}`}>
        <div>
          <h3 className="font-semibold text-lg">{device.name}</h3>
          <p className="text-sm text-base-content/70">{device.id}</p>
        </div>
        <div className='text-right'>
          <div className="flex items-baseline gap-2 justify-end">
            <span className="text-2xl font-mono">
              {device.state !== null 
                ? typeof device.state === 'number' 
                  ? device.state.toFixed(2) 
                  : device.state 
                : 'N/A'}
            </span>
            {device.unit && (
              <span className="text-base-content/70">
                {device.unit}
              </span>
            )}
          </div>
          <p className="text-gray-500 text-xs mt-2">
            {formatTimestamp(device?.timestamp ?? null)}
          </p>
        </div>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison: only re-render if state, timestamp, entity_type, x_mapping or isGrid changed
  return prevProps.device.id === nextProps.device.id &&
         prevProps.device.state === nextProps.device.state &&
         prevProps.device.timestamp === nextProps.device.timestamp &&
         prevProps.device.entity_type === nextProps.device.entity_type &&
         prevProps.device.x_mapping === nextProps.device.x_mapping &&
         prevProps.isGrid === nextProps.isGrid;
});

export default function ModbusView() {
  const { modbus_devices } = useContext(WebSocketContext);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('modbusViewMode');
    return saved ? saved === 'grid' : true;
  });
  const [error, setError] = useState<string | null>(null);

  const validModbusDevices = useMemo(
    () => modbus_devices.filter(isModbusDeviceEvent).map(e => e.state),
    [modbus_devices]
  );

  // Group Modbus devices by device_group - memoized
  const groupedModbusDevices = useMemo(() => {
    return validModbusDevices.reduce((groups, device) => {
      const group = device.device_group || 'Other';
      if (!groups[group]) {
        groups[group] = [];
      }
      groups[group].push(device);
      return groups;
    }, {} as Record<string, ModbusDeviceState[]>);
  }, [validModbusDevices]);

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('modbusViewMode', gridView ? 'grid' : 'list');
  };

  const handleValueChange = async (coordinatorId: string, entityId: string, value: string | number) => {
    try {
      await axios.post(`/api/modbus/${coordinatorId}/${entityId}/set_value`, { value });
      setError(null);
    } catch (err: any) {
      console.error('Error setting modbus value:', err);
      setError(err.response?.data?.detail || 'Failed to set value');
    }
  };

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Modbus Devices</h2>
        <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
      </div>
      
      {error && (
        <div className="alert alert-error mb-4">
          <span>{error}</span>
        </div>
      )}
      
      {/* Grouped Modbus Devices */}
      {Object.keys(groupedModbusDevices).length === 0 ? (
        <div className="text-center py-8 text-base-content/60">
          No Modbus devices configured
        </div>
      ) : (
        Object.entries(groupedModbusDevices).map(([groupName, devices]) => (
          <div key={groupName} className="mb-8">
            <h3 className="text-lg font-semibold mb-3 text-base-content/80">{groupName}</h3>
            <div className={isGrid 
              ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
              : "flex flex-col gap-4"
            }>
              {devices.map((device) => (
                <ModbusDeviceItem 
                  key={device.id} 
                  device={device} 
                  isGrid={isGrid}
                  onValueChange={handleValueChange}
                />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

