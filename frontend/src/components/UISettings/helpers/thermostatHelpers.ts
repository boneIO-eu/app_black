/**
 * Typed interfaces and helper functions for the thermostat template form.
 *
 * Extracted from ThermostatForm to enable unit testing of data transformation
 * and validation logic independently of React rendering.
 */

import type { EntityItem } from '../EntitySelectDropdown';

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

/** Raw sensor data from the YAML config (1-Wire, I2C). */
export interface SensorConfigEntry {
  id?: string;
  address?: string;
  name?: string;
  area?: string;
  /** Source marker injected by SectionContent (e.g. 'lm75', 'mcp9808'). */
  _source?: string;
}

/** Raw Modbus device entry from YAML config. */
export interface ModbusDeviceEntry {
  id?: string;
  address?: number;
  model?: string;
  name?: string;
  area?: string;
}

/** Modbus model capability info returned by /api/modbus/models. */
export interface ModbusModelInfo {
  has_temperature: boolean;
  temperature_sensors?: { name: string; suffix: string }[];
}

/** Intermediate representation of a discovered temperature sensor. */
export interface TemperatureSensor {
  id: string;
  label: string;
  source: string;
  area?: string;
}

/** Raw output data from YAML config. */
export interface OutputConfigEntry {
  id?: string;
  boneio_output?: string;
  name?: string;
  area?: string;
  output_type?: string;
}

/** Thermostat form data shape. */
export interface ThermostatData {
  id?: string;
  name?: string;
  area?: string;
  sensor_id?: string;
  sensor_ids?: string[];
  output_id?: string;
  target_temperature?: number | string;
  hysteresis?: number | string;
  min_temperature?: number | string;
  max_temperature?: number | string;
  mode?: 'heat' | 'off';
  platform?: string;
}

/** Translation function signature used throughout helpers. */
export type TFunction = (key: string, params?: Record<string, string | number>) => string;

/** Validation result returned by validateThermostat. */
export interface ValidationResult {
  isValid: boolean;
  errors: string[];
}

// ---------------------------------------------------------------------------
// Build sensor items
// ---------------------------------------------------------------------------

/**
 * Build a unified list of temperature sensors from all config sources.
 *
 * @param allSensors - Raw sensor entries (1-Wire, LM75, MCP9808)
 * @param allModbusDevices - Raw modbus device entries
 * @param modbusModels - Modbus model capability map
 * @returns Array of TemperatureSensor
 */
export function buildTemperatureSensors(
  allSensors: SensorConfigEntry[],
  allModbusDevices: ModbusDeviceEntry[],
  modbusModels: Record<string, ModbusModelInfo>,
): TemperatureSensor[] {
  const sensors: TemperatureSensor[] = [];

  for (const s of allSensors) {
    const src = s._source || '';
    if (src === 'lm75' || src === 'mcp9808') {
      const id = (s.id || '').replace(/\s/g, '');
      if (id) {
        sensors.push({
          id,
          label: s.id || `${src.toUpperCase()} @ 0x${(s.address ? parseInt(String(s.address), 10) : 0).toString(16)}`,
          source: src.toUpperCase(),
          area: s.area || '',
        });
      }
    } else {
      const id = s.id || s.address || '';
      if (id) {
        sensors.push({
          id,
          label: s.name || s.id || s.address || '',
          source: '1-Wire',
          area: s.area || '',
        });
      }
    }
  }

  for (const dev of allModbusDevices) {
    const model = (dev.model || '').toLowerCase();
    const devId = dev.id
      ? String(dev.id).replace(/\s/g, '').toLowerCase()
      : `${dev.address}_${model}`.toLowerCase().replace(/\s/g, '_');
    const modelInfo = modbusModels[model];
    if (modelInfo?.has_temperature) {
      const tempSensors = modelInfo.temperature_sensors || [];
      if (tempSensors.length > 1) {
        for (const ts of tempSensors) {
          sensors.push({
            id: `${devId}_${ts.suffix}`,
            label: `${dev.name || devId} → ${ts.name}`,
            source: 'Modbus',
            area: dev.area || '',
          });
        }
      } else {
        const suffix = tempSensors.length === 1 ? tempSensors[0].suffix : 'temperature';
        const name = tempSensors.length === 1 ? tempSensors[0].name : 'Temperature';
        sensors.push({
          id: `${devId}_${suffix}`,
          label: `${dev.name || devId} (${name})`,
          source: 'Modbus',
          area: dev.area || '',
        });
      }
    }
  }

  return sensors;
}

/**
 * Convert temperature sensors to EntityItem[] for SearchableMultiEntityPicker.
 * Appends orphan IDs (saved in YAML but not discovered) with a warning badge.
 *
 * @param sensors - Known temperature sensors
 * @param selectedIds - Currently selected sensor IDs (may include orphans)
 * @param unavailableLabel - Translated label for unavailable items (e.g. "Niedostępny")
 * @returns EntityItem[] ready for the picker
 */
export function buildSensorItems(
  sensors: TemperatureSensor[],
  selectedIds: string[],
  unavailableLabel: string,
): EntityItem[] {
  const knownItems: EntityItem[] = sensors.map((sensor) => ({
    id: sensor.id,
    name: sensor.label,
    area: sensor.area || '',
    badge: sensor.source,
    badgeClass:
      sensor.source === '1-Wire' ? 'badge-info'
      : sensor.source === 'Modbus' ? 'badge-warning'
      : 'badge-ghost',
  }));

  const knownIds = new Set(sensors.map((s) => s.id));
  const orphans: EntityItem[] = selectedIds
    .filter((id) => !knownIds.has(id))
    .map((id) => ({
      id,
      name: id,
      badge: `⚠ ${unavailableLabel}`,
      badgeClass: 'badge-error',
      disabledLabel: unavailableLabel,
    }));

  return [...knownItems, ...orphans];
}

// ---------------------------------------------------------------------------
// Build output items
// ---------------------------------------------------------------------------

/**
 * Convert raw output config entries to EntityItem[] for SearchableEntityPicker.
 *
 * @param outputs - Raw output entries from the YAML config
 * @returns EntityItem[] ready for the picker
 */
export function buildOutputItems(outputs: OutputConfigEntry[]): EntityItem[] {
  return (outputs || [])
    .filter((o) => o && (o.id || o.boneio_output))
    .map((output) => {
      const effectiveId = output.id || output.boneio_output || '';
      const outputType = output.output_type;
      return {
        id: effectiveId,
        name: output.name || effectiveId,
        area: output.area || '',
        badge: outputType && outputType !== 'none' ? outputType : undefined,
        badgeClass:
          outputType === 'light' ? 'badge-warning'
          : outputType === 'switch' ? 'badge-info'
          : outputType === 'valve' ? 'badge-accent'
          : 'badge-ghost',
      };
    });
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/**
 * Validate thermostat form data.
 *
 * @param data - Current thermostat form state
 * @param t - Translation function
 * @returns ValidationResult with errors array
 */
export function validateThermostat(
  data: ThermostatData,
  t: TFunction,
): ValidationResult {
  const errors: string[] = [];

  // At least one sensor required
  const sensorIds = data.sensor_ids || (data.sensor_id ? [data.sensor_id] : []);
  if (sensorIds.length === 0) {
    errors.push(t('template.sensor_required'));
  }

  // Output is required
  if (!data.output_id) {
    errors.push(t('template.output_required'));
  }

  // Target temperature must be a valid number
  const target = parseFloat(String(data.target_temperature ?? ''));
  if (isNaN(target)) {
    errors.push(t('template.invalid_target_temperature'));
  }

  // Hysteresis must be a positive number
  const hysteresis = parseFloat(String(data.hysteresis ?? ''));
  if (!isNaN(hysteresis) && hysteresis <= 0) {
    errors.push(t('template.hysteresis_positive'));
  }

  // Min < Max temperature check
  const minTemp = parseFloat(String(data.min_temperature ?? ''));
  const maxTemp = parseFloat(String(data.max_temperature ?? ''));
  if (!isNaN(minTemp) && !isNaN(maxTemp) && minTemp >= maxTemp) {
    errors.push(t('template.min_max_invalid'));
  }

  // Target within min/max range
  if (!isNaN(target) && !isNaN(minTemp) && !isNaN(maxTemp)) {
    if (target < minTemp || target > maxTemp) {
      errors.push(t('template.target_out_of_range'));
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
}
