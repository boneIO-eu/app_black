import { useContext, useState, useMemo } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { WebSocketContext } from '../App';
import ViewToggle from './ViewToggle';
import GraphCard from './GraphCard';
import { isSensorEvent, SensorState } from '../hooks/useWebSocket';
import { useSensorHistory } from '../hooks/useSensorHistory';

/** Sensor group definition with display metadata */
interface SensorGroup {
  key: string;
  label: string;
  icon: string;
  accentColor: string;
  strokeColor: string;
  fillColor: string;
  sensors: SensorState[];
}

const SYSTEM_IDS = new Set(['cpu_usage', 'memory_usage', 'disk_usage']);

/**
 * Classify a sensor into a group key based on its ID and properties.
 *
 * Groups:
 *  - adc: ADC analog sensors
 *  - board: Board sensors (INA219 power monitor + temperature sensors)
 *  - system: CPU/Memory/Disk usage
 *  - other: Everything else
 */
function classifySensor(sensor: SensorState): string {
  const idLower = sensor.id.toLowerCase();

  if (idLower.startsWith('adc') || idLower.includes('_adc')) return 'adc';
  if (idLower.includes('ina219') || idLower.includes('ina_219')) return 'board';
  if (SYSTEM_IDS.has(idLower)) return 'system';
  if (
    sensor.unit === '°C' ||
    idLower.includes('temperature') ||
    idLower.includes('temp')
  )
    return 'board';
  return 'other';
}

/** Group metadata (order matters — determines display order) */
const GROUP_META: Record<string, { icon: string; accentColor: string; strokeColor: string; fillColor: string }> = {
  adc:    { icon: '⚡', accentColor: 'border-amber-500',   strokeColor: '#f59e0b', fillColor: 'rgba(245, 158, 11, 0.10)' },
  board:  { icon: '🔌', accentColor: 'border-blue-500',    strokeColor: '#3b82f6', fillColor: 'rgba(59, 130, 246, 0.10)' },
  system: { icon: '🖥️', accentColor: 'border-violet-500',  strokeColor: '#8b5cf6', fillColor: 'rgba(139, 92, 246, 0.10)' },
  other:  { icon: '📊', accentColor: 'border-emerald-500', strokeColor: '#10b981', fillColor: 'rgba(16, 185, 129, 0.10)' },
};

/** Display order for groups */
const GROUP_ORDER = ['adc', 'board', 'system', 'other'];

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

  // Group sensors by category
  const sensorGroups = useMemo<SensorGroup[]>(() => {
    const buckets: Record<string, SensorState[]> = {};

    for (const sensor of validSensors) {
      const group = classifySensor(sensor);
      if (!buckets[group]) buckets[group] = [];
      buckets[group].push(sensor);
    }

    return GROUP_ORDER
      .filter(key => buckets[key]?.length)
      .map(key => {
        const meta = GROUP_META[key];
        return {
          key,
          label: t(`sensors.groups.${key}`) || key,
          icon: meta.icon,
          accentColor: meta.accentColor,
          strokeColor: meta.strokeColor,
          fillColor: meta.fillColor,
          sensors: buckets[key],
        };
      });
  }, [validSensors, t]);

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
        <div className="space-y-6">
          {sensorGroups.map(group => (
            <section key={group.key}>
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-base-content/80">
                <span>{group.icon}</span>
                {group.label}
                <span className="text-xs font-normal text-base-content/50">
                  ({group.sensors.length})
                </span>
              </h3>
              <div className={isGrid
                ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
                : "flex flex-col gap-4"
              }>
                {group.sensors.map(sensor => (
                  <GraphCard
                    key={sensor.id}
                    id={sensor.id}
                    name={sensor.name}
                    value={sensor.state}
                    unit={sensor.unit}
                    timestamp={sensor.timestamp}
                    historyPoints={historyMap.get(sensor.id) || []}
                    isGrid={isGrid}
                    accentColor={group.accentColor}
                    strokeColor={group.strokeColor}
                    fillColor={group.fillColor}
                    attributes={sensor.attributes}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
