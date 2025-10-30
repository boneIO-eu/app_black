import { useContext, memo, useState, useMemo } from 'react';
import { WebSocketContext } from '../App';
import { formatTimestamp } from '../utils/formatters';
import ViewToggle from './ViewToggle';
import { isModbusDeviceEvent, ModbusDeviceState } from '../hooks/useWebSocket';

// Separate component for individual Modbus device - memoized by device.id and state
const ModbusDeviceItem = memo(({ device, isGrid }: {
  device: ModbusDeviceState;
  isGrid: boolean;
}) => (
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
), (prevProps, nextProps) => {
  // Custom comparison: only re-render if state, timestamp or isGrid changed
  return prevProps.device.id === nextProps.device.id &&
         prevProps.device.state === nextProps.device.state &&
         prevProps.device.timestamp === nextProps.device.timestamp &&
         prevProps.isGrid === nextProps.isGrid;
});

export default function ModbusView() {
  const { modbus_devices } = useContext(WebSocketContext);
  console.log("Modbus devices:", modbus_devices)
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('modbusViewMode');
    return saved ? saved === 'grid' : true;
  });

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

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Modbus Devices</h2>
        <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
      </div>
      
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
                <ModbusDeviceItem key={device.id} device={device} isGrid={isGrid} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

