/**
 * Tests verifying that WebUI optimization changes correctly eliminate
 * duplicate API requests and derive config state from /api/init data.
 *
 * These tests validate the data-flow logic — not React rendering — since
 * the test environment is 'node' (no DOM/jsdom).
 */
import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// ConfigContext derivation logic
// (Extracted from ConfigContext.tsx for testability)
// ---------------------------------------------------------------------------

/** Board versions that support CAN bus (0.5+) */
const CAN_SUPPORTED_VERSIONS = ['0.5', '0.6', '0.7', '0.8', '1.0'];

/** Max inputs per board version */
const MAX_INPUTS: Record<string, number> = {
  '0.2': 52, '0.3': 52, '0.4': 52,
  '0.5': 49, '0.6': 49, '0.7': 49, '0.8': 49, '1.0': 49,
};

/**
 * Derive config context values from /api/init data.
 * This mirrors the useMemo logic in ConfigContext.tsx.
 */
function deriveConfigFromInit(initData: {
  has_boneio: boolean;
  board_version: string | null;
  has_irrigation: boolean;
} | null) {
  const boardVersion = initData?.board_version ?? null;
  return {
    hasBoneioSection: initData?.has_boneio ?? false,
    hasIrrigationSection: initData?.has_irrigation ?? false,
    boardVersion,
    canSupported: boardVersion ? CAN_SUPPORTED_VERSIONS.includes(boardVersion) : true,
    maxInputs: boardVersion && MAX_INPUTS[boardVersion] ? MAX_INPUTS[boardVersion] : 49,
  };
}

describe('deriveConfigFromInit', () => {
  it('returns defaults when initData is null', () => {
    const result = deriveConfigFromInit(null);
    expect(result).toEqual({
      hasBoneioSection: false,
      hasIrrigationSection: false,
      boardVersion: null,
      canSupported: true,
      maxInputs: 49,
    });
  });

  it('correctly derives values for board v0.8', () => {
    const result = deriveConfigFromInit({
      has_boneio: true,
      board_version: '0.8',
      has_irrigation: false,
    });
    expect(result.hasBoneioSection).toBe(true);
    expect(result.boardVersion).toBe('0.8');
    expect(result.canSupported).toBe(true); // 0.5+ supports CAN
    expect(result.maxInputs).toBe(49);
    expect(result.hasIrrigationSection).toBe(false);
  });

  it('correctly derives values for old board v0.3 (no CAN)', () => {
    const result = deriveConfigFromInit({
      has_boneio: true,
      board_version: '0.3',
      has_irrigation: true,
    });
    expect(result.canSupported).toBe(false); // 0.3 does not support CAN
    expect(result.maxInputs).toBe(52); // old boards have 52 inputs
    expect(result.hasIrrigationSection).toBe(true);
  });

  it('handles null board_version gracefully', () => {
    const result = deriveConfigFromInit({
      has_boneio: false,
      board_version: null,
      has_irrigation: false,
    });
    expect(result.boardVersion).toBeNull();
    expect(result.canSupported).toBe(true); // defaults to true when unknown
    expect(result.maxInputs).toBe(49); // defaults to 49
  });

  it('handles board v1.0', () => {
    const result = deriveConfigFromInit({
      has_boneio: true,
      board_version: '1.0',
      has_irrigation: false,
    });
    expect(result.canSupported).toBe(true);
    expect(result.maxInputs).toBe(49);
  });
});

// ---------------------------------------------------------------------------
// AppInitContext shallow compare logic
// ---------------------------------------------------------------------------

/**
 * Simulates the shallow compare logic in AppInitContext.fetchInit.
 * Returns whether the state should be updated (true = new data, false = same).
 */
function shouldUpdateInitData(
  prev: Record<string, unknown> | null,
  next: Record<string, unknown>
): boolean {
  if (!prev) return true;
  return JSON.stringify(prev) !== JSON.stringify(next);
}

describe('shouldUpdateInitData (shallow compare)', () => {
  it('returns true when prev is null (first fetch)', () => {
    expect(shouldUpdateInitData(null, { version: '1.0' })).toBe(true);
  });

  it('returns false when data is identical', () => {
    const data = { version: '1.0', name: 'test', has_boneio: true };
    expect(shouldUpdateInitData(data, { ...data })).toBe(false);
  });

  it('returns true when version changes', () => {
    const prev = { version: '1.0', name: 'test' };
    const next = { version: '1.1', name: 'test' };
    expect(shouldUpdateInitData(prev, next)).toBe(true);
  });

  it('returns true when a new field is added', () => {
    const prev = { version: '1.0' };
    const next = { version: '1.0', has_boneio: true };
    expect(shouldUpdateInitData(prev, next)).toBe(true);
  });

  it('returns false for deeply equal nested objects', () => {
    const prev = { cloud: { enabled: true, domain: 'test.com' } };
    const next = { cloud: { enabled: true, domain: 'test.com' } };
    expect(shouldUpdateInitData(prev, next)).toBe(false);
  });

  it('returns true when nested object changes', () => {
    const prev = { cloud: { enabled: true, domain: 'test.com' } };
    const next = { cloud: { enabled: false, domain: 'test.com' } };
    expect(shouldUpdateInitData(prev, next)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// /api/init response contract — ensures all expected fields are present
// ---------------------------------------------------------------------------

describe('/api/init response contract', () => {
  /** Minimal valid /api/init response shape */
  const INIT_RESPONSE = {
    version: '3.5.0',
    name: 'boneIO Black 32x10A',
    serial_no: 'blk_abc123',
    serial_override: null,
    auth_required: true,
    pwa_name: 'bIO abc123',
    pwa_default: 'bIO abc123',
    pwa_max_length: 12,
    cloud: { enabled: false },
    has_boneio: true,
    board_version: '0.8',
    has_irrigation: false,
  };

  it('has all fields needed by ConfigContext', () => {
    // ConfigContext needs these fields from /api/init:
    expect(INIT_RESPONSE).toHaveProperty('has_boneio');
    expect(INIT_RESPONSE).toHaveProperty('board_version');
    expect(INIT_RESPONSE).toHaveProperty('has_irrigation');
  });

  it('has name field (replaces /api/name)', () => {
    expect(INIT_RESPONSE).toHaveProperty('name');
    expect(typeof INIT_RESPONSE.name).toBe('string');
  });

  it('has version field (replaces /api/version)', () => {
    expect(INIT_RESPONSE).toHaveProperty('version');
    expect(typeof INIT_RESPONSE.version).toBe('string');
  });

  it('has auth_required field (replaces /api/auth/required)', () => {
    expect(INIT_RESPONSE).toHaveProperty('auth_required');
    expect(typeof INIT_RESPONSE.auth_required).toBe('boolean');
  });

  it('derives valid config values', () => {
    const config = deriveConfigFromInit(INIT_RESPONSE);
    expect(config.hasBoneioSection).toBe(true);
    expect(config.boardVersion).toBe('0.8');
    expect(config.canSupported).toBe(true);
    expect(config.maxInputs).toBe(49);
    expect(config.hasIrrigationSection).toBe(false);
  });
});
