/**
 * Tests for itemValidation helper — validateItem and areAllItemsUsed.
 */
import { describe, it, expect } from 'vitest';
import { validateItem, areAllItemsUsed } from '../helpers/itemValidation';

const t = (key: string) => key;

describe('validateItem', () => {
  it('binary_sensor requires boneio_input', () => {
    expect(validateItem('binary_sensor', {}, t).isValid).toBe(false);
    expect(validateItem('binary_sensor', { boneio_input: 'in_01' }, t).isValid).toBe(true);
  });

  it('event requires boneio_input', () => {
    expect(validateItem('event', {}, t).isValid).toBe(false);
    expect(validateItem('event', { boneio_input: 'in_02' }, t).isValid).toBe(true);
  });

  it('local_inputs validates based on _type', () => {
    expect(validateItem('local_inputs', { _type: 'event', boneio_input: 'in_03' }, t).isValid).toBe(true);
    expect(validateItem('local_inputs', { _type: 'binary_sensor' }, t).isValid).toBe(false);
  });

  it('remote_inputs requires id or name', () => {
    expect(validateItem('remote_inputs', {}, t).isValid).toBe(false);
    expect(validateItem('remote_inputs', { id: 'motion' }, t).isValid).toBe(true);
    expect(validateItem('remote_inputs', { name: 'PIR Sensor' }, t).isValid).toBe(true);
  });

  it('output requires boneio_output', () => {
    expect(validateItem('output', {}, t).isValid).toBe(false);
    expect(validateItem('output', { boneio_output: 'rel_01' }, t).isValid).toBe(true);
  });

  it('cover requires all relay/time fields', () => {
    expect(validateItem('cover', { open_relay: 'rel_01' }, t).isValid).toBe(false);
    expect(validateItem('cover', {
      open_relay: 'rel_01', close_relay: 'rel_02', open_time: '30s', close_time: '30s',
    }, t).isValid).toBe(true);
  });

  it('modbus_devices rejects update_interval < 1s', () => {
    const result = validateItem('modbus_devices', {
      address: 1, model: 'sdm120', update_interval: '500ms',
    }, t);
    expect(result.isValid).toBe(false);
  });

  it('remote_devices requires id, name, protocol + host for esphome', () => {
    expect(validateItem('remote_devices', { id: 'x', name: 'X', protocol: 'mqtt' }, t).isValid).toBe(true);
    expect(validateItem('remote_devices', { id: 'x', name: 'X', protocol: 'esphome_api' }, t).isValid).toBe(false);
    expect(validateItem('remote_devices', {
      id: 'x', name: 'X', protocol: 'esphome_api', esphome_api: { host: '192.168.1.5' },
    }, t).isValid).toBe(true);
  });

  it('template requires platform', () => {
    expect(validateItem('template', {}, t).isValid).toBe(false);
    expect(validateItem('template', { platform: 'thermostat', sensor_id: 's', output_id: 'o' }, t).isValid).toBe(true);
  });

  it('unknown section type always valid', () => {
    expect(validateItem('unknown_thing', {}, t).isValid).toBe(true);
  });
});

describe('areAllItemsUsed', () => {
  const schema = { items: { properties: { boneio_input: { enum: ['in_01', 'in_02', 'in_03'] } } } };

  it('returns false when inputs remain', () => {
    const result = areAllItemsUsed(
      'binary_sensor', [{ boneio_input: 'in_01' }], schema, undefined,
      [{ boneio_input: 'in_01' }], [],
    );
    expect(result).toBe(false);
  });

  it('returns true when all inputs used', () => {
    const result = areAllItemsUsed(
      'local_inputs', [], schema, undefined,
      [{ boneio_input: 'in_01' }],
      [{ boneio_input: 'in_02' }, { boneio_input: 'in_03' }],
    );
    expect(result).toBe(true);
  });

  it('handles case-insensitive input matching', () => {
    const result = areAllItemsUsed(
      'event', [], schema, undefined,
      [{ boneio_input: 'IN_01' }, { boneio_input: 'IN_02' }, { boneio_input: 'IN_03' }], [],
    );
    expect(result).toBe(true);
  });

  it('returns false for non-input sections', () => {
    expect(areAllItemsUsed('sensor', [], schema, undefined, [], [])).toBe(false);
  });
});
