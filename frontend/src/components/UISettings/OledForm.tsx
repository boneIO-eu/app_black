import React, { useState, useCallback } from 'react';
import { Plus, Trash2, GripVertical, Monitor, Moon, Thermometer } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';

interface OledFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Available OLED screen types with their icons and descriptions.
 */
const AVAILABLE_SCREENS = [
  { id: 'uptime', icon: '⏱️' },
  { id: 'network', icon: '🌐' },
  { id: 'ina219', icon: '⚡' },
  { id: 'cpu', icon: '💻' },
  { id: 'disk', icon: '💾' },
  { id: 'memory', icon: '🧠' },
  { id: 'swap', icon: '🔄' },
  { id: 'outputs', icon: '💡' },
  { id: 'inputs', icon: '🔘' },
  { id: 'extra_sensors', icon: '🌡️' },
  { id: 'web', icon: '📱' },
] as const;

const SENSOR_TYPES = ['modbus', 'dallas'] as const;

/**
 * Custom form for OLED display section configuration.
 * 
 * Fields:
 * - enabled: boolean toggle
 * - screens: ordered list of screen types
 * - extra_screen_sensors: list of sensor references
 * - screensaver_timeout: timeout string (e.g. "60s", "0")
 */
const OledForm: React.FC<OledFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  const handleChange = useCallback((field: string, value: any) => {
    onChange({ ...data, [field]: value });
  }, [data, onChange]);

  // Current screens list
  const screens: string[] = data?.screens || ['uptime', 'network', 'ina219', 'cpu', 'disk', 'memory', 'swap', 'outputs'];

  // Available screens not yet added
  const unusedScreens = AVAILABLE_SCREENS.filter(s => !screens.includes(s.id));

  // Extra screen sensors
  const extraSensors: any[] = data?.extra_screen_sensors || [];

  // Screensaver timeout
  const screensaverTimeout = data?.screensaver_timeout || '60s';

  // --- Screen list management ---

  const addScreen = (screenId: string) => {
    handleChange('screens', [...screens, screenId]);
  };

  const removeScreen = (index: number) => {
    const newScreens = [...screens];
    newScreens.splice(index, 1);
    handleChange('screens', newScreens);
  };

  const moveScreen = (fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= screens.length) return;
    const newScreens = [...screens];
    const [moved] = newScreens.splice(fromIndex, 1);
    newScreens.splice(toIndex, 0, moved);
    handleChange('screens', newScreens);
  };

  // --- Drag and Drop ---

  const handleDragStart = (index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === index) return;
    moveScreen(draggedIndex, index);
    setDraggedIndex(index);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
  };

  // --- Extra sensors management ---

  const addExtraSensor = () => {
    const newSensor = { sensor_type: 'modbus', sensor_id: '' };
    handleChange('extra_screen_sensors', [...extraSensors, newSensor]);
  };

  const updateExtraSensor = (index: number, field: string, value: string) => {
    const newSensors = [...extraSensors];
    newSensors[index] = { ...newSensors[index], [field]: value };
    // Clear modbus_id when switching to dallas
    if (field === 'sensor_type' && value === 'dallas') {
      delete newSensors[index].modbus_id;
    }
    handleChange('extra_screen_sensors', newSensors);
  };

  const removeExtraSensor = (index: number) => {
    const newSensors = [...extraSensors];
    newSensors.splice(index, 1);
    handleChange('extra_screen_sensors', newSensors);
  };

  // --- Screensaver timeout parsing ---

  const parseTimeoutValue = (timeout: string | number | any): number => {
    if (typeof timeout === 'number') return timeout;
    if (typeof timeout === 'object' && timeout !== null) {
      // TimePeriod object from backend
      if (timeout._total_in_seconds !== undefined) return timeout._total_in_seconds;
      if (timeout.seconds !== undefined) return timeout.seconds;
      return 60;
    }
    if (typeof timeout !== 'string') return 60;
    const match = timeout.match(/^(\d+)(s|ms|min|m|h)?$/);
    if (!match) return 60;
    const val = parseInt(match[1], 10);
    const unit = match[2] || 's';
    switch (unit) {
      case 'ms': return val / 1000;
      case 's': return val;
      case 'min':
      case 'm': return val * 60;
      case 'h': return val * 3600;
      default: return val;
    }
  };

  const timeoutSeconds = parseTimeoutValue(screensaverTimeout);

  const getScreenInfo = (screenId: string) => {
    return AVAILABLE_SCREENS.find(s => s.id === screenId);
  };

  return (
    <div className="space-y-6">
      {/* Enable/Disable Toggle */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-3">
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={data?.enabled !== false}
            onChange={(e) => handleChange('enabled', e.target.checked)}
          />
          <div>
            <span className="label-text font-medium text-base">{t('oled.enabled')}</span>
            <p className="text-xs text-base-content/60 mt-0.5">{t('oled.enabled_hint')}</p>
          </div>
        </label>
      </div>

      {data?.enabled !== false && (
        <>
          {/* Screens Section */}
          <div className="card bg-base-200/50 shadow-sm">
            <div className="card-body p-4">
              <h3 className="card-title text-base gap-2">
                <Monitor size={18} />
                {t('oled.screens_title')}
              </h3>
              <p className="text-xs text-base-content/60 mb-3">
                {t('oled.screens_hint')}
              </p>

              {/* Active screens list */}
              <div className="space-y-1">
                {screens.map((screenId, index) => {
                  const info = getScreenInfo(screenId);
                  return (
                    <div
                      key={`${screenId}-${index}`}
                      draggable
                      onDragStart={() => handleDragStart(index)}
                      onDragOver={(e) => handleDragOver(e, index)}
                      onDragEnd={handleDragEnd}
                      className={`flex items-center gap-2 p-2 rounded-lg border transition-all ${
                        draggedIndex === index
                          ? 'border-primary bg-primary/10 opacity-70'
                          : 'border-base-300 bg-base-100 hover:border-base-content/20'
                      }`}
                    >
                      <GripVertical
                        size={16}
                        className="cursor-grab active:cursor-grabbing text-base-content/40 shrink-0"
                      />
                      <span className="text-lg shrink-0">{info?.icon || '📺'}</span>
                      <span className="font-medium flex-1">
                        {t(`oled.screen_${screenId}`)}
                      </span>
                      <span className="text-xs text-base-content/50 font-mono">{index + 1}</span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs btn-square text-error/70 hover:text-error"
                        onClick={() => removeScreen(index)}
                        title={t('common.remove')}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Add screen buttons */}
              {unusedScreens.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-base-content/60 mb-2">{t('oled.add_screen')}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {unusedScreens.map((screen) => (
                      <button
                        key={screen.id}
                        type="button"
                        className="btn btn-outline btn-sm gap-1"
                        onClick={() => addScreen(screen.id)}
                      >
                        <span>{screen.icon}</span>
                        {t(`oled.screen_${screen.id}`)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Extra Screen Sensors */}
          {screens.includes('extra_sensors') && (
            <div className="card bg-base-200/50 shadow-sm">
              <div className="card-body p-4">
                <h3 className="card-title text-base gap-2">
                  <Thermometer size={18} />
                  {t('oled.extra_sensors_title')}
                </h3>
                <p className="text-xs text-base-content/60 mb-3">
                  {t('oled.extra_sensors_hint')}
                </p>

                {/* Sensors list */}
                <div className="space-y-3">
                  {extraSensors.map((sensor, index) => (
                    <div
                      key={index}
                      className="flex flex-wrap items-end gap-2 p-3 rounded-lg border border-base-300 bg-base-100"
                    >
                      {/* Sensor Type */}
                      <div className="form-control flex-1 min-w-[120px]">
                        <label className="label py-0.5">
                          <span className="label-text text-xs">{t('oled.sensor_type')}</span>
                        </label>
                        <select
                          className="select select-bordered select-sm w-full"
                          value={sensor.sensor_type || 'modbus'}
                          onChange={(e) => updateExtraSensor(index, 'sensor_type', e.target.value)}
                        >
                          {SENSOR_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type === 'modbus' ? 'Modbus' : 'Dallas (1-Wire)'}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Modbus ID (only for modbus type) */}
                      {sensor.sensor_type === 'modbus' && (
                        <div className="form-control flex-1 min-w-[120px]">
                          <label className="label py-0.5">
                            <span className="label-text text-xs">{t('oled.modbus_id')}</span>
                          </label>
                          <input
                            type="text"
                            className="input input-bordered input-sm w-full"
                            placeholder={t('oled.modbus_id_placeholder')}
                            value={sensor.modbus_id || ''}
                            onChange={(e) => updateExtraSensor(index, 'modbus_id', e.target.value)}
                          />
                        </div>
                      )}

                      {/* Sensor ID */}
                      <div className="form-control flex-1 min-w-[120px]">
                        <label className="label py-0.5">
                          <span className="label-text text-xs">
                            {t('oled.sensor_id')} <span className="text-error">*</span>
                          </span>
                        </label>
                        <input
                          type="text"
                          className={`input input-bordered input-sm w-full ${!sensor.sensor_id ? 'input-error' : ''}`}
                          placeholder={t('oled.sensor_id_placeholder')}
                          value={sensor.sensor_id || ''}
                          onChange={(e) => updateExtraSensor(index, 'sensor_id', e.target.value)}
                        />
                      </div>

                      {/* Remove button */}
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm btn-square text-error shrink-0"
                        onClick={() => removeExtraSensor(index)}
                        title={t('common.remove')}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                </div>

                {/* Add sensor button */}
                <button
                  type="button"
                  className="btn btn-outline btn-sm gap-1 mt-2"
                  onClick={addExtraSensor}
                >
                  <Plus size={14} />
                  {t('oled.add_sensor')}
                </button>
              </div>
            </div>
          )}

          {/* Screensaver Timeout */}
          <div className="card bg-base-200/50 shadow-sm">
            <div className="card-body p-4">
              <h3 className="card-title text-base gap-2">
                <Moon size={18} />
                {t('oled.screensaver_title')}
              </h3>

              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('oled.screensaver_timeout')}</span>
                  <span className="label-text-alt badge badge-ghost">
                    {timeoutSeconds === 0
                      ? t('oled.screensaver_disabled')
                      : `${timeoutSeconds}s`
                    }
                  </span>
                </label>
                <input
                  type="range"
                  className="range range-primary range-sm"
                  min={0}
                  max={600}
                  step={10}
                  value={timeoutSeconds}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    handleChange('screensaver_timeout', val === 0 ? '0' : `${val}s`);
                  }}
                />
                <div className="flex justify-between text-xs text-base-content/50 mt-1 px-1">
                  <span>{t('oled.screensaver_off')}</span>
                  <span>1 min</span>
                  <span>5 min</span>
                  <span>10 min</span>
                </div>
                <p className="text-xs text-base-content/60 mt-2">
                  {t('oled.screensaver_timeout_hint')}
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default OledForm;
