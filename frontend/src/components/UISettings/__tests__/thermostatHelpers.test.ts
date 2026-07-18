/**
 * Tests for thermostatHelpers — buildTemperatureSensors, buildSensorItems,
 * buildOutputItems, and validateThermostat.
 */
import { describe, it, expect } from 'vitest';
import {
  buildTemperatureSensors,
  buildSensorItems,
  buildOutputItems,
  validateThermostat,
} from '../helpers/thermostatHelpers';
import type {
  SensorConfigEntry,
  ModbusDeviceEntry,
  ModbusModelInfo,
  ThermostatData,
} from '../helpers/thermostatHelpers';

const t = (key: string) => key;

// ---------------------------------------------------------------------------
// buildTemperatureSensors
// ---------------------------------------------------------------------------

describe('buildTemperatureSensors', () => {
  it('returns empty array when no sources', () => {
    expect(buildTemperatureSensors([], [], {})).toEqual([]);
  });

  it('detects 1-Wire sensors', () => {
    const sensors: SensorConfigEntry[] = [
      { id: 'dallas_28abc', name: 'Kitchen Temp', area: 'kitchen' },
    ];
    const result = buildTemperatureSensors(sensors, [], {});
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      id: 'dallas_28abc',
      label: 'Kitchen Temp',
      source: '1-Wire',
      area: 'kitchen',
    });
  });

  it('detects LM75 sensors', () => {
    const sensors: SensorConfigEntry[] = [
      { id: 'Boardtemperature', _source: 'lm75', area: '' },
    ];
    const result = buildTemperatureSensors(sensors, [], {});
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      id: 'Boardtemperature',
      source: 'LM75',
    });
  });

  it('detects MCP9808 sensors', () => {
    const sensors: SensorConfigEntry[] = [
      { id: 'RoomTemp', _source: 'mcp9808' },
    ];
    const result = buildTemperatureSensors(sensors, [], {});
    expect(result).toHaveLength(1);
    expect(result[0].source).toBe('MCP9808');
  });

  it('skips sensors without id or address', () => {
    const sensors: SensorConfigEntry[] = [
      { name: 'NoId' },
      { id: '', _source: 'lm75' },
    ];
    expect(buildTemperatureSensors(sensors, [], {})).toEqual([]);
  });

  it('uses address as fallback id for 1-Wire', () => {
    const sensors: SensorConfigEntry[] = [
      { address: '28-000abc123' },
    ];
    const result = buildTemperatureSensors(sensors, [], {});
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('28-000abc123');
  });

  it('builds Modbus single-temperature sensors', () => {
    const devices: ModbusDeviceEntry[] = [
      { id: 'edge-temp', model: 'boneio-edge-temp', name: 'Salon', area: 'living_room' },
    ];
    const models: Record<string, ModbusModelInfo> = {
      'boneio-edge-temp': {
        has_temperature: true,
        temperature_sensors: [{ name: 'Temperature', suffix: 'temperature' }],
      },
    };
    const result = buildTemperatureSensors([], devices, models);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      id: 'edge-temp_temperature',
      source: 'Modbus',
      area: 'living_room',
    });
    expect(result[0].label).toContain('Salon');
  });

  it('builds Modbus multi-temperature sensors', () => {
    const devices: ModbusDeviceEntry[] = [
      { address: 10, model: 'R4DCB08', name: 'Collector' },
    ];
    const models: Record<string, ModbusModelInfo> = {
      r4dcb08: {
        has_temperature: true,
        temperature_sensors: [
          { name: 'Temp 1', suffix: 'temp1' },
          { name: 'Temp 2', suffix: 'temp2' },
        ],
      },
    };
    const result = buildTemperatureSensors([], devices, models);
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe('10_r4dcb08_temp1');
    expect(result[1].id).toBe('10_r4dcb08_temp2');
  });

  it('skips Modbus devices without has_temperature', () => {
    const devices: ModbusDeviceEntry[] = [
      { id: 'relay1', model: 'some_relay' },
    ];
    const models: Record<string, ModbusModelInfo> = {
      some_relay: { has_temperature: false },
    };
    expect(buildTemperatureSensors([], devices, models)).toEqual([]);
  });

  it('generates auto-id for Modbus devices without custom id', () => {
    const devices: ModbusDeviceEntry[] = [
      { address: 5, model: 'Boneio Edge Temp' },
    ];
    const models: Record<string, ModbusModelInfo> = {
      'boneio edge temp': {
        has_temperature: true,
        temperature_sensors: [{ name: 'Temperature', suffix: 'temperature' }],
      },
    };
    const result = buildTemperatureSensors([], devices, models);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('5_boneio_edge_temp_temperature');
  });

  it('mixes all source types', () => {
    const sensors: SensorConfigEntry[] = [
      { id: 'dallas_28abc', name: 'Floor' },
      { id: 'Board', _source: 'lm75' },
    ];
    const devices: ModbusDeviceEntry[] = [
      { id: 'edge1', model: 'boneio-edge-temp' },
    ];
    const models: Record<string, ModbusModelInfo> = {
      'boneio-edge-temp': {
        has_temperature: true,
        temperature_sensors: [{ name: 'Temperature', suffix: 'temperature' }],
      },
    };
    const result = buildTemperatureSensors(sensors, devices, models);
    expect(result).toHaveLength(3);
    expect(result.map((s) => s.source)).toEqual(['1-Wire', 'LM75', 'Modbus']);
  });
});

// ---------------------------------------------------------------------------
// buildSensorItems
// ---------------------------------------------------------------------------

describe('buildSensorItems', () => {
  const sensors = [
    { id: 'dallas_28abc', label: 'Kitchen', source: '1-Wire', area: 'kitchen' },
    { id: 'edge1_temperature', label: 'Salon (Temperature)', source: 'Modbus', area: 'salon' },
  ];

  it('converts sensors to EntityItems with proper badges', () => {
    const result = buildSensorItems(sensors, ['dallas_28abc'], 'Unavailable');
    expect(result).toHaveLength(2);
    expect(result[0]).toMatchObject({
      id: 'dallas_28abc',
      name: 'Kitchen',
      area: 'kitchen',
      badgeClass: 'badge-info',
    });
    expect(result[1].badgeClass).toBe('badge-warning');
  });

  it('appends orphan IDs with error badge', () => {
    const result = buildSensorItems(sensors, ['dallas_28abc', 'ghost_sensor'], 'Niedostępny');
    expect(result).toHaveLength(3);
    const orphan = result[2];
    expect(orphan).toMatchObject({
      id: 'ghost_sensor',
      name: 'ghost_sensor',
      badge: '⚠ Niedostępny',
      badgeClass: 'badge-error',
      disabledLabel: 'Niedostępny',
    });
  });

  it('does not duplicate known items as orphans', () => {
    const result = buildSensorItems(sensors, ['dallas_28abc', 'edge1_temperature'], 'Unavailable');
    expect(result).toHaveLength(2);
  });

  it('handles empty sensors with orphans', () => {
    const result = buildSensorItems([], ['orphan1', 'orphan2'], 'Unavailable');
    expect(result).toHaveLength(2);
    expect(result.every((r) => r.badgeClass === 'badge-error')).toBe(true);
  });

  it('handles empty selection', () => {
    const result = buildSensorItems(sensors, [], 'Unavailable');
    expect(result).toHaveLength(2);
    expect(result.every((r) => !r.disabledLabel)).toBe(true);
  });

  it('handles LM75 source badge class', () => {
    const lm75 = [{ id: 'board', label: 'Board', source: 'LM75' }];
    const result = buildSensorItems(lm75, [], 'Unavailable');
    expect(result[0].badgeClass).toBe('badge-ghost');
  });
});

// ---------------------------------------------------------------------------
// buildOutputItems
// ---------------------------------------------------------------------------

describe('buildOutputItems', () => {
  it('converts outputs with proper badges', () => {
    const outputs = [
      { id: 'OUT_01', name: 'Living Room Light', area: 'living_room', output_type: 'light' },
      { id: 'OUT_02', name: 'Heater Relay', output_type: 'switch' },
    ];
    const result = buildOutputItems(outputs);
    expect(result).toHaveLength(2);
    expect(result[0]).toMatchObject({
      id: 'OUT_01',
      name: 'Living Room Light',
      area: 'living_room',
      badge: 'light',
      badgeClass: 'badge-warning',
    });
    expect(result[1].badgeClass).toBe('badge-info');
  });

  it('uses boneio_output as fallback id', () => {
    const outputs = [
      { boneio_output: 'rel_01', name: 'Relay 1' },
    ];
    const result = buildOutputItems(outputs);
    expect(result[0].id).toBe('rel_01');
  });

  it('skips outputs without id or boneio_output', () => {
    const outputs = [
      { name: 'Orphan Output' },
      { id: 'valid', name: 'Valid' },
    ];
    const result = buildOutputItems(outputs);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('valid');
  });

  it('sets badge to undefined for output_type "none"', () => {
    const outputs = [{ id: 'OUT_01', output_type: 'none' }];
    const result = buildOutputItems(outputs);
    expect(result[0].badge).toBeUndefined();
  });

  it('handles valve output type', () => {
    const outputs = [{ id: 'valve_01', output_type: 'valve' }];
    const result = buildOutputItems(outputs);
    expect(result[0].badgeClass).toBe('badge-accent');
  });

  it('uses id as fallback name', () => {
    const outputs = [{ id: 'OUT_03' }];
    const result = buildOutputItems(outputs);
    expect(result[0].name).toBe('OUT_03');
  });

  it('handles empty array', () => {
    expect(buildOutputItems([])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// validateThermostat
// ---------------------------------------------------------------------------

describe('validateThermostat', () => {
  const validData: ThermostatData = {
    sensor_ids: ['dallas_28abc'],
    output_id: 'OUT_01',
    target_temperature: 21,
    hysteresis: 0.5,
    min_temperature: 5,
    max_temperature: 35,
    mode: 'heat',
  };

  it('validates correct data', () => {
    const result = validateThermostat(validData, t);
    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it('requires at least one sensor', () => {
    const data: ThermostatData = { ...validData, sensor_ids: [], sensor_id: '' };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.sensor_required');
  });

  it('accepts legacy sensor_id when sensor_ids is missing', () => {
    const data: ThermostatData = { ...validData, sensor_ids: undefined, sensor_id: 'legacy_sensor' };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(true);
  });

  it('requires output_id', () => {
    const data: ThermostatData = { ...validData, output_id: '' };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.output_required');
  });

  it('rejects invalid target temperature', () => {
    const data: ThermostatData = { ...validData, target_temperature: 'abc' };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.invalid_target_temperature');
  });

  it('rejects zero hysteresis', () => {
    const data: ThermostatData = { ...validData, hysteresis: 0 };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.hysteresis_positive');
  });

  it('rejects negative hysteresis', () => {
    const data: ThermostatData = { ...validData, hysteresis: -1 };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.hysteresis_positive');
  });

  it('rejects min >= max temperature', () => {
    const data: ThermostatData = { ...validData, min_temperature: 35, max_temperature: 35 };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.min_max_invalid');
  });

  it('rejects min > max temperature', () => {
    const data: ThermostatData = { ...validData, min_temperature: 40, max_temperature: 35 };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.min_max_invalid');
  });

  it('rejects target out of min/max range', () => {
    const data: ThermostatData = { ...validData, target_temperature: 50 };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.target_out_of_range');
  });

  it('rejects target below min', () => {
    const data: ThermostatData = { ...validData, target_temperature: 2 };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors).toContain('template.target_out_of_range');
  });

  it('collects multiple errors at once', () => {
    const data: ThermostatData = {
      sensor_ids: [],
      output_id: '',
      target_temperature: 'bad',
      hysteresis: -1,
      min_temperature: 40,
      max_temperature: 5,
    };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThanOrEqual(4);
  });

  it('handles string numeric values (form input)', () => {
    const data: ThermostatData = {
      ...validData,
      target_temperature: '21',
      hysteresis: '0.5',
      min_temperature: '5',
      max_temperature: '35',
    };
    const result = validateThermostat(data, t);
    expect(result.isValid).toBe(true);
  });

  it('accepts undefined optional fields with defaults', () => {
    const data: ThermostatData = {
      sensor_ids: ['s1'],
      output_id: 'out1',
    };
    const result = validateThermostat(data, t);
    // target_temperature is undefined → NaN → error
    expect(result.errors).toContain('template.invalid_target_temperature');
  });
});
