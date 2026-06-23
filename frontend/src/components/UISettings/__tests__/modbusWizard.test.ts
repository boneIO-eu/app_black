/**
 * Tests for AddModbusDeviceWizard logic:
 * - Catalog integrity (all devices have required fields)
 * - Device config output format (matches what backend expects)
 * - Address conflict detection
 * - Search filtering
 * - i18n description lookup
 */
import { describe, it, expect } from 'vitest';
import {
  MODBUS_DEVICE_CATALOG,
  MODBUS_CATEGORIES,
  ModbusDeviceInfo,
} from '../../../generated/modbusDeviceCatalog';

// ---------------------------------------------------------------------------
// Catalog integrity
// ---------------------------------------------------------------------------

describe('MODBUS_DEVICE_CATALOG', () => {
  const allDevices = Object.values(MODBUS_DEVICE_CATALOG);

  it('has at least 20 devices', () => {
    expect(allDevices.length).toBeGreaterThanOrEqual(20);
  });

  it.each(allDevices.map(d => [d.modelKey, d]))(
    '%s has all required fields',
    (_key, device) => {
      expect(device.modelKey).toBeTruthy();
      expect(device.displayName).toBeTruthy();
      expect(device.manufacturer).toBeTruthy();
      expect(device.description).toBeTruthy();
      expect(device.category).toBeTruthy();
      expect(typeof device.defaultAddress).toBe('number');
      expect(device.defaultAddress).toBeGreaterThanOrEqual(1);
      expect(device.defaultAddress).toBeLessThanOrEqual(247);
      expect(device.defaultUpdateInterval).toBeTruthy();
      expect(typeof device.hasSetBase).toBe('boolean');
    }
  );

  it('does not have descriptionPl field (i18n migration)', () => {
    for (const device of allDevices) {
      expect(device).not.toHaveProperty('descriptionPl');
    }
  });

  it('contains known devices', () => {
    expect(MODBUS_DEVICE_CATALOG['wanas415']).toBeDefined();
    expect(MODBUS_DEVICE_CATALOG['sdm120']).toBeDefined();
    expect(MODBUS_DEVICE_CATALOG['thessla']).toBeDefined();
    expect(MODBUS_DEVICE_CATALOG['sht30']).toBeDefined();
  });
});

describe('MODBUS_CATEGORIES', () => {
  it('has at least 4 categories', () => {
    expect(MODBUS_CATEGORIES.length).toBeGreaterThanOrEqual(4);
  });

  it('contains expected categories', () => {
    expect(MODBUS_CATEGORIES).toContain('energy_meters');
    expect(MODBUS_CATEGORIES).toContain('hvac');
    expect(MODBUS_CATEGORIES).toContain('sensors');
    expect(MODBUS_CATEGORIES).toContain('inverters');
  });

  it('is sorted alphabetically', () => {
    const sorted = [...MODBUS_CATEGORIES].sort();
    expect(MODBUS_CATEGORIES).toEqual(sorted);
  });

  it('each category has at least one device', () => {
    const allDevices = Object.values(MODBUS_DEVICE_CATALOG);
    for (const category of MODBUS_CATEGORIES) {
      const devicesInCategory = allDevices.filter(d => d.category === category);
      expect(devicesInCategory.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// Wizard config output format
// ---------------------------------------------------------------------------

describe('Wizard config output', () => {
  /**
   * Simulates buildDeviceConfig — the object the wizard sends to onAdd().
   * This must match what the backend YAML schema expects.
   */
  function buildDeviceConfig(params: {
    model: ModbusDeviceInfo;
    address: number;
    name: string;
    updateInterval: string;
    area?: string;
    customId?: string;
  }) {
    const config: Record<string, any> = {
      model: params.model.modelKey,
      address: Number(params.address),
      name: params.name.trim(),
      update_interval: params.updateInterval,
    };
    if (params.area) config.area = params.area;
    if (params.customId) config.id = params.customId.trim();
    return config;
  }

  it('produces correct format for Wanas 415', () => {
    const device = MODBUS_DEVICE_CATALOG['wanas415'];
    const config = buildDeviceConfig({
      model: device,
      address: 1,
      name: 'Living Room Recuperator',
      updateInterval: '30s',
      area: 'salon',
      customId: '1_wanas415',
    });

    expect(config).toEqual({
      model: 'wanas415',
      address: 1,
      name: 'Living Room Recuperator',
      update_interval: '30s',
      area: 'salon',
      id: '1_wanas415',
    });
  });

  it('omits area when not provided', () => {
    const device = MODBUS_DEVICE_CATALOG['sdm120'];
    const config = buildDeviceConfig({
      model: device,
      address: 2,
      name: 'Energy Meter',
      updateInterval: '10s',
    });

    expect(config).not.toHaveProperty('area');
    expect(config.model).toBe('sdm120');
    expect(config.address).toBe(2);
  });

  it('uses model key (lowercase), not displayName', () => {
    const device = MODBUS_DEVICE_CATALOG['le-03mw'];
    const config = buildDeviceConfig({
      model: device,
      address: 3,
      name: 'Test',
      updateInterval: '10s',
    });

    // Backend expects lowercase model key matching the JSON filename
    expect(config.model).toBe('le-03mw');
    expect(config.model).not.toBe('LE-03MW'); // Not the displayName
  });

  it('address is always a number, not a string', () => {
    const device = MODBUS_DEVICE_CATALOG['sht20'];
    const config = buildDeviceConfig({
      model: device,
      address: 5,
      name: 'Temp Sensor',
      updateInterval: '10s',
    });

    expect(typeof config.address).toBe('number');
  });
});

// ---------------------------------------------------------------------------
// Address conflict detection
// ---------------------------------------------------------------------------

describe('Address conflict detection', () => {
  interface UsedAddress {
    address: number;
    model: string;
    id: string;
    name: string;
  }

  function findConflict(address: number, usedAddresses: UsedAddress[]) {
    return usedAddresses.find(u => u.address === address);
  }

  function findNextFreeAddress(usedAddresses: UsedAddress[]): number {
    const usedSet = new Set(usedAddresses.map(u => u.address));
    let nextFree = 1;
    while (usedSet.has(nextFree)) {
      nextFree++;
    }
    return nextFree;
  }

  const usedAddresses: UsedAddress[] = [
    { address: 1, model: 'sdm120', id: '1_sdm120', name: 'Energy Meter' },
    { address: 3, model: 'sht30', id: '3_sht30', name: 'Temp Sensor' },
  ];

  it('detects conflict at address 1', () => {
    const conflict = findConflict(1, usedAddresses);
    expect(conflict).toBeDefined();
    expect(conflict!.model).toBe('sdm120');
  });

  it('no conflict at address 2', () => {
    expect(findConflict(2, usedAddresses)).toBeUndefined();
  });

  it('suggests address 2 as next free (1 and 3 taken)', () => {
    expect(findNextFreeAddress(usedAddresses)).toBe(2);
  });

  it('suggests address 1 when nothing is used', () => {
    expect(findNextFreeAddress([])).toBe(1);
  });

  it('suggests address 4 when 1-3 are taken', () => {
    const all = [
      { address: 1, model: 'a', id: '', name: '' },
      { address: 2, model: 'b', id: '', name: '' },
      { address: 3, model: 'c', id: '', name: '' },
    ];
    expect(findNextFreeAddress(all)).toBe(4);
  });
});

// ---------------------------------------------------------------------------
// Search filtering
// ---------------------------------------------------------------------------

describe('Search filtering', () => {
  const allDevices = Object.values(MODBUS_DEVICE_CATALOG);

  function searchDevices(query: string): ModbusDeviceInfo[] {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return allDevices.filter(device =>
      device.displayName.toLowerCase().includes(q) ||
      device.modelKey.toLowerCase().includes(q) ||
      device.manufacturer.toLowerCase().includes(q) ||
      device.description.toLowerCase().includes(q)
    );
  }

  it('finds Wanas by manufacturer name', () => {
    const results = searchDevices('wanas');
    expect(results.length).toBeGreaterThanOrEqual(1);
    expect(results[0].modelKey).toBe('wanas415');
  });

  it('finds SDM by model key', () => {
    const results = searchDevices('sdm');
    expect(results.length).toBe(2); // sdm120 + sdm630
  });

  it('finds devices by description keyword', () => {
    const results = searchDevices('energy meter');
    expect(results.length).toBeGreaterThan(0);
    results.forEach(d => {
      expect(d.description.toLowerCase()).toContain('energy meter');
    });
  });

  it('search is case-insensitive', () => {
    const upper = searchDevices('EASTRON');
    const lower = searchDevices('eastron');
    expect(upper).toEqual(lower);
    expect(upper.length).toBeGreaterThan(0);
  });

  it('empty query returns no results', () => {
    expect(searchDevices('')).toHaveLength(0);
    expect(searchDevices('   ')).toHaveLength(0);
  });

  it('non-matching query returns empty', () => {
    expect(searchDevices('xyznonexistent123')).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Auto-generated ID
// ---------------------------------------------------------------------------

describe('Auto-generated device ID', () => {
  function generateId(address: number, modelKey: string): string {
    return `${address}_${modelKey}`.toLowerCase().replace(/[^a-z0-9]+/g, '_');
  }

  it('produces expected format', () => {
    expect(generateId(1, 'wanas415')).toBe('1_wanas415');
    expect(generateId(5, 'sdm120')).toBe('5_sdm120');
    expect(generateId(10, 'le-03mw')).toBe('10_le_03mw');
  });

  it('handles special characters in model key', () => {
    expect(generateId(1, 'dyp-a12-ultrasonic')).toBe('1_dyp_a12_ultrasonic');
    expect(generateId(2, 'esp32_relay_x4_modbus')).toBe('2_esp32_relay_x4_modbus');
  });
});
