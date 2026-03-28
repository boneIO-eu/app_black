/**
 * BoardSensorsForm — form for adding/editing LM75, INA219, and MCP9808 board sensors.
 *
 * Renders different fields based on sensor type selection.
 * Common fields: type, address, id, update_interval
 * LM75/MCP9808 extra: filters, unit_of_measurement
 * INA219 extra: sensors sub-list (current, power, voltage)
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { formatTimeperiod } from '@/utils/formatters';

/** I2C address options per sensor type */
const ADDRESS_OPTIONS: Record<string, { value: number; label: string }[]> = {
  lm75: [
    { value: 0x48, label: '0x48 (default)' },
    { value: 0x49, label: '0x49' },
    { value: 0x4A, label: '0x4A' },
    { value: 0x4B, label: '0x4B' },
    { value: 0x4C, label: '0x4C' },
    { value: 0x4D, label: '0x4D' },
    { value: 0x4E, label: '0x4E' },
    { value: 0x4F, label: '0x4F' },
  ],
  ina219: [
    { value: 0x40, label: '0x40 (default)' },
    { value: 0x41, label: '0x41' },
    { value: 0x44, label: '0x44' },
    { value: 0x45, label: '0x45' },
  ],
  mcp9808: [
    { value: 0x18, label: '0x18 (default)' },
    { value: 0x19, label: '0x19' },
    { value: 0x1A, label: '0x1A' },
    { value: 0x1B, label: '0x1B' },
    { value: 0x1C, label: '0x1C' },
    { value: 0x1D, label: '0x1D' },
    { value: 0x1E, label: '0x1E' },
    { value: 0x1F, label: '0x1F' },
  ],
};

/** Default sensor sub-entries for INA219 */
const DEFAULT_INA219_SENSORS = [
  { id: 'Board Current', device_class: 'current' },
  { id: 'Board Power', device_class: 'power' },
  { id: 'Board Voltage', device_class: 'voltage' },
];

const SENSOR_TYPES = [
  { value: 'lm75', label: 'LM75 / PCT2075' },
  { value: 'ina219', label: 'INA219' },
  { value: 'mcp9808', label: 'MCP9808' },
];

interface BoardSensorsFormProps {
  data: any;
  onChange: (data: any) => void;
  existingItems: any[];
  editingIndex: number | null;
  onValidationChange?: (isValid: boolean) => void;
}

const BoardSensorsForm: React.FC<BoardSensorsFormProps> = ({
  data,
  onChange,
  existingItems,
  editingIndex,
  onValidationChange,
}) => {
  const { t } = useTranslation();
  const [errors, setErrors] = useState<Record<string, string>>({});

  const sensorType = data?._type || 'lm75';

  const updateField = useCallback(
    (field: string, value: any) => {
      const updated = { ...data, [field]: value };

      // When type changes, reset to defaults for new type
      if (field === '_type') {
        const defaultAddr = ADDRESS_OPTIONS[value]?.[0]?.value || 0;
        updated.address = defaultAddr;
        // Reset type-specific fields
        if (value === 'ina219') {
          updated.sensors = DEFAULT_INA219_SENSORS;
          delete updated.filters;
          delete updated.unit_of_measurement;
        } else {
          delete updated.sensors;
        }
      }

      onChange(updated);
    },
    [data, onChange],
  );

  // Validate
  useEffect(() => {
    const newErrors: Record<string, string> = {};

    // id is required for lm75/mcp9808 (it's the sensor name), optional for ina219 (prefix for sub-sensor IDs)
    if (sensorType !== 'ina219' && (!data?.id || String(data.id).trim() === '')) {
      newErrors.id = t('board_sensors.id_required');
    }

    if (data?.address === undefined || data?.address === null) {
      newErrors.address = t('board_sensors.address_required');
    }

    // Check for duplicate address within same type
    const isDuplicate = existingItems.some((item, idx) => {
      if (editingIndex !== null && idx === editingIndex) return false;
      return item._type === sensorType && item.address === data?.address;
    });
    if (isDuplicate) {
      newErrors.address = t('board_sensors.address_duplicate');
    }

    setErrors(newErrors);
    onValidationChange?.(Object.keys(newErrors).length === 0);
  }, [data, existingItems, editingIndex, sensorType, t, onValidationChange]);

  const addresses = ADDRESS_OPTIONS[sensorType] || [];

  return (
    <div className="space-y-4">
      {/* Sensor Type */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('board_sensors.type')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={sensorType}
          onChange={(e) => updateField('_type', e.target.value)}
          disabled={editingIndex !== null}
        >
          {SENSOR_TYPES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('board_sensors.type_hint')}</span>
        </label>
      </div>

      {/* Name / ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('board_sensors.id')}</span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full ${errors.id ? 'input-error' : ''}`}
          value={data?.id ?? ''}
          onChange={(e) => updateField('id', e.target.value || undefined)}
          placeholder={sensorType === 'lm75' ? 'Board temperature' : sensorType === 'ina219' ? '' : 'Temperature'}
        />
        {errors.id && (
          <label className="label">
            <span className="label-text-alt text-error">{errors.id}</span>
          </label>
        )}
        <label className="label">
          <span className="label-text-alt text-base-content/60">
            {sensorType === 'ina219'
              ? t('board_sensors.id_hint_ina')
              : t('board_sensors.id_hint')}
          </span>
        </label>
      </div>

      {/* I2C Address */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('board_sensors.address')}</span>
        </label>
        <select
          className={`select select-bordered w-full ${errors.address ? 'select-error' : ''}`}
          value={data?.address ?? ''}
          onChange={(e) => updateField('address', parseInt(e.target.value, 10))}
        >
          <option value="">{t('board_sensors.select_address')}</option>
          {addresses.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {errors.address && (
          <label className="label">
            <span className="label-text-alt text-error">{errors.address}</span>
          </label>
        )}
      </div>

      {/* Update Interval */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('board_sensors.update_interval')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={typeof data?.update_interval === 'object' ? formatTimeperiod(data.update_interval) : (data?.update_interval || '')}
          onChange={(e) => updateField('update_interval', e.target.value || undefined)}
          placeholder="60s"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('board_sensors.update_interval_hint')}</span>
        </label>
      </div>

      {/* INA219-specific: Sensors sub-list */}
      {sensorType === 'ina219' && (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('board_sensors.ina_sensors')}</span>
          </label>
          <div className="space-y-2">
            {(data?.sensors || DEFAULT_INA219_SENSORS).map((sensor: any, idx: number) => (
              <div key={idx} className="flex items-center gap-2 bg-base-100 rounded p-2">
                <input
                  type="text"
                  className="input input-bordered input-sm flex-1"
                  value={sensor.id || ''}
                  onChange={(e) => {
                    const updated = [...(data?.sensors || DEFAULT_INA219_SENSORS)];
                    updated[idx] = { ...updated[idx], id: e.target.value };
                    updateField('sensors', updated);
                  }}
                />
                <span className="badge badge-sm badge-ghost">{sensor.device_class}</span>
              </div>
            ))}
          </div>
          <label className="label">
            <span className="label-text-alt text-base-content/60">{t('board_sensors.ina_sensors_hint')}</span>
          </label>
        </div>
      )}
    </div>
  );
};

export default BoardSensorsForm;
