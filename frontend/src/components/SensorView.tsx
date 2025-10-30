import { useContext, memo, useState, useMemo } from 'react';
import { WebSocketContext } from '../App';
import { formatTimestamp } from '../utils/formatters';
import ViewToggle from './ViewToggle';
import { isSensorEvent, SensorState } from '../hooks/useWebSocket';

// Separate component for individual sensor - memoized by sensor.id and state                       
const SensorItem = memo(({ sensor, isGrid }: {
  sensor: SensorState;
  isGrid: boolean;
}) => (
  <div
    className={`bg-base-200  shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4' : 'border-l-8'} border-emerald-500`}
  >
    <div className={`flex ${isGrid ? 'justify-between items-start' : 'justify-between items-start'}`}>
      <div>
        <h3 className="font-semibold text-lg">{sensor.name}</h3>
        <p className="text-sm text-base-content/70">{sensor.id}</p>
      </div>
      <div className='text-right'>
        <div className="flex items-baseline gap-2 justify-end">
          <span className="text-2xl font-mono">
            {sensor.state !== null 
              ? typeof sensor.state === 'number' 
                ? sensor.state.toFixed(2) 
                : sensor.state 
              : 'N/A'}
          </span>
          {sensor.unit && (
            <span className="text-base-content/70">
              {sensor.unit}
            </span>
          )}
        </div>
        <p className="text-gray-500 text-xs mt-2">
          {formatTimestamp(sensor?.timestamp ?? null)}
        </p>
      </div>
    </div>
  </div>
), (prevProps, nextProps) => {
  // Custom comparison: only re-render if state, timestamp or isGrid changed
  return prevProps.sensor.id === nextProps.sensor.id &&
         prevProps.sensor.state === nextProps.sensor.state &&
         prevProps.sensor.timestamp === nextProps.sensor.timestamp &&
         prevProps.isGrid === nextProps.isGrid;
});

export default function SensorView() {
  const { sensors } = useContext(WebSocketContext);
  console.log("Sensors:", sensors)
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('sensorViewMode');
    return saved ? saved === 'grid' : true;
  });

  // Memoize sensor extraction to avoid recalculations
  const validSensors = useMemo(
    () => sensors.filter(isSensorEvent).map(e => e.state),
    [sensors]
  );

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('sensorViewMode', gridView ? 'grid' : 'list');
  };

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">System Sensors</h2>
        <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
      </div>
      
      {validSensors.length === 0 ? (
        <div className="text-center py-8 text-base-content/60">
          No system sensors configured
        </div>
      ) : (
        <div className={isGrid 
          ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
          : "flex flex-col gap-4"
        }>
          {validSensors.map((sensor) => (
            <SensorItem key={sensor.id} sensor={sensor} isGrid={isGrid} />
          ))}
        </div>
      )}
    </div>
  );
}
