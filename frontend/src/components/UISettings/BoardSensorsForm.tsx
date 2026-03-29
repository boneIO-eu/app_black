/**
 * BoardSensorsForm — form for adding/editing LM75, INA219, and MCP9808 board sensors.
 *
 * Renders different fields based on sensor type selection.
 * Common fields: type, address, id, update_interval
 * LM75/MCP9808 extra: filters, unit_of_measurement
 * INA219 extra: sensors sub-list (current, power, voltage)
 *
 * Supports I2C bus scanning to auto-detect available addresses.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { formatTimeperiod } from '@/utils/formatters';
import { FaSearch } from 'react-icons/fa';
import axios from '@/api/axios';

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

/** All known board sensor addresses for matching scan results */
const ALL_SENSOR_ADDRESSES = new Set(
  Object.values(ADDRESS_OPTIONS).flatMap(opts => opts.map(o => o.value))
);

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
  const [scanning, setScanning] = useState(false);
  const [detectedAddresses, setDetectedAddresses] = useState<Set<number> | null>(null);

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

  /**
   * Scan I2C bus 2 and store detected addresses.
   * If a matching address for the current sensor type is found,
   * auto-select it.
   */
  const handleI2CScan = useCallback(async () => {
    setScanning(true);
    try {
      const { data: scanResult } = await axios.get('/api/i2c/scan?bus=2', { timeout: 15000 });
      const foundAddresses = new Set<number>(
        (scanResult.devices || []).map((dev: any) => dev.address)
      );
      setDetectedAddresses(foundAddresses);

      // Auto-select first matching address for current sensor type
      const typeAddresses = ADDRESS_OPTIONS[sensorType] || [];
      const matchingAddr = typeAddresses.find(opt => foundAddresses.has(opt.value));
      if (matchingAddr) {
        updateField('address', matchingAddr.value);
      }
    } catch (err) {
      console.error('I2C scan failed:', err);
    } finally {
      setScanning(false);
    }
  }, [sensorType, updateField]);

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

  /**
   * Build the label for an address option, appending
   * "✓ detected" or "✓ detected ⚠ in use" based on scan and existing items.
   */
  const getAddressLabel = (opt: { value: number; label: string }) => {
    const isDetected = detectedAddresses?.has(opt.value);
    const isUsed = existingItems.some((item, idx) => {
      if (editingIndex !== null && idx === editingIndex) return false;
      return item._type === sensorType && item.address === opt.value;
    });
    if (isDetected && isUsed) {
      return `${opt.label}  ✓ ${t('board_sensors.detected')}  ⚠ ${t('board_sensors.in_use')}`;
    }
    if (isDetected) {
      return `${opt.label}  ✓ ${t('board_sensors.detected')}`;
    }
    if (isUsed) {
      return `${opt.label}  ⚠ ${t('board_sensors.in_use')}`;
    }
    return opt.label;
  };

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

      {/* I2C Address with Scan button */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('board_sensors.address')}</span>
        </label>
        <div className="flex gap-2">
          <select
            className={`select select-bordered flex-1 ${errors.address ? 'select-error' : ''}`}
            value={data?.address ?? ''}
            onChange={(e) => updateField('address', parseInt(e.target.value, 10))}
          >
            <option value="">{t('board_sensors.select_address')}</option>
            {addresses.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {getAddressLabel(opt)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={`btn btn-square btn-outline ${scanning ? 'loading' : ''}`}
            onClick={handleI2CScan}
            disabled={scanning}
            title={t('board_sensors.scan_i2c')}
          >
            {!scanning && <FaSearch />}
          </button>
        </div>
        {errors.address && (
          <label className="label">
            <span className="label-text-alt text-error">{errors.address}</span>
          </label>
        )}
        {/* Scan results summary */}
        {detectedAddresses !== null && (
          <label className="label">
            <span className={`label-text-alt ${(() => {
              const typeAddrs = addresses.filter(a => detectedAddresses.has(a.value));
              const freeAddrs = typeAddrs.filter(a => !existingItems.some((item, idx) => {
                if (editingIndex !== null && idx === editingIndex) return false;
                return item._type === sensorType && item.address === a.value;
              }));
              if (freeAddrs.length > 0) return 'text-success';
              if (typeAddrs.length > 0) return 'text-warning';
              return 'text-base-content/60';
            })()}`}>
              {(() => {
                const typeAddrs = addresses.filter(a => detectedAddresses.has(a.value));
                const freeAddrs = typeAddrs.filter(a => !existingItems.some((item, idx) => {
                  if (editingIndex !== null && idx === editingIndex) return false;
                  return item._type === sensorType && item.address === a.value;
                }));
                const usedAddrs = typeAddrs.filter(a => existingItems.some((item, idx) => {
                  if (editingIndex !== null && idx === editingIndex) return false;
                  return item._type === sensorType && item.address === a.value;
                }));

                if (typeAddrs.length > 0) {
                  const parts: string[] = [];
                  if (freeAddrs.length > 0) {
                    parts.push(t('board_sensors.scan_found_matching', {
                      count: String(freeAddrs.length),
                      addresses: freeAddrs.map(a => a.label.split(' ')[0]).join(', '),
                    }));
                  }
                  if (usedAddrs.length > 0) {
                    parts.push(t('board_sensors.scan_found_in_use', {
                      count: String(usedAddrs.length),
                      addresses: usedAddrs.map(a => a.label.split(' ')[0]).join(', '),
                    }));
                  }
                  return parts.join('. ');
                }
                // Check for any sensor addresses at all
                const anySensor = [...detectedAddresses].filter(a => ALL_SENSOR_ADDRESSES.has(a));
                if (anySensor.length > 0) {
                  return t('board_sensors.scan_found_other', {
                    addresses: anySensor.map(a => `0x${a.toString(16).toUpperCase()}`).join(', '),
                  });
                }
                return t('board_sensors.scan_none_found');
              })()}
            </span>
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
