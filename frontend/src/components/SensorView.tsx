import { useContext, useState, useMemo } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { WebSocketContext } from '../App';
import ViewToggle from './ViewToggle';
import GraphCard from './GraphCard';
import { isSensorEvent, SensorState } from '../hooks/useWebSocket';
import { useSensorHistory } from '../hooks/useSensorHistory';

export default function SensorView() {
  const { t } = useTranslation();
  const { sensors, modbus_devices } = useContext(WebSocketContext);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('sensorViewMode');
    return saved ? saved === 'grid' : true;
  });

  // Extract non-modbus sensors
  const validSensors = useMemo(
    () => {
      const modbusIds = new Set(modbus_devices.map(md => md.entity_id));
      return sensors
        .filter(isSensorEvent)
        .filter(e => !modbusIds.has(e.entity_id))
        .map(e => e.state);
    },
    [sensors, modbus_devices]
  );

  // Track history for sparkline charts
  const historyMap = useSensorHistory(validSensors);

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('sensorViewMode', gridView ? 'grid' : 'list');
  };

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">{t('sensors.view_title')}</h2>
        <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
      </div>
      
      {validSensors.length === 0 ? (
        <div className="text-center py-8 text-base-content/60">
          {t('sensors.no_sensors')}
        </div>
      ) : (
        <div className={isGrid 
          ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
          : "flex flex-col gap-4"
        }>
          {validSensors.map((sensor: SensorState) => (
            <GraphCard
              key={sensor.id}
              id={sensor.id}
              name={sensor.name}
              value={sensor.state}
              unit={sensor.unit}
              timestamp={sensor.timestamp}
              historyPoints={historyMap.get(sensor.id) || []}
              isGrid={isGrid}
            />
          ))}
        </div>
      )}
    </div>
  );
}
