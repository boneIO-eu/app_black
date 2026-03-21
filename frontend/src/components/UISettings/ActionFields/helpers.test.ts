import { describe, it, expect } from 'vitest';
import { cleanActionFields, validateAction } from './helpers';

// ---------------------------------------------------------------------------
// cleanActionFields
// ---------------------------------------------------------------------------

describe('cleanActionFields', () => {
  it('returns only action when switching to unknown type with no prior fields', () => {
    const result = cleanActionFields('output', {});
    expect(result).toEqual({ action: 'output' });
  });

  // --- output_over_mqtt → remote_output (the bug scenario) ---
  it('strips boneio_id when switching from output_over_mqtt to remote_output', () => {
    const prior = {
      action: 'output_over_mqtt',
      boneio_id: 'boneio_led',
      boneio_output: 'OUT_01',
      action_output: 'TOGGLE',
    };
    const result = cleanActionFields('remote_output', prior);
    expect(result.boneio_id).toBeUndefined();
    expect(result.action).toBe('remote_output');
  });

  it('strips boneio_id when switching from cover_over_mqtt to remote_cover', () => {
    const prior = {
      action: 'cover_over_mqtt',
      boneio_id: 'boneio_main',
      boneio_cover: 'blinds_01',
      action_cover: 'TOGGLE',
    };
    const result = cleanActionFields('remote_cover', prior);
    expect(result.boneio_id).toBeUndefined();
    expect(result.action).toBe('remote_cover');
  });

  it('strips remote_device and output_id when switching from remote_output to output', () => {
    const prior = {
      action: 'remote_output',
      remote_device: 'boneio_led',
      output_id: 'chr_02',
      action_output: 'TOGGLE',
      brightness: 200,
    };
    const result = cleanActionFields('output', prior);
    expect(result.remote_device).toBeUndefined();
    expect(result.output_id).toBeUndefined();
    expect(result.brightness).toBeUndefined();
    expect(result.action).toBe('output');
  });

  it('keeps boneio_output when switching from output to output_over_mqtt', () => {
    const prior = {
      action: 'output',
      boneio_output: 'OUT_05',
      action_output: 'ON',
    };
    const result = cleanActionFields('output_over_mqtt', prior);
    expect(result.boneio_output).toBe('OUT_05');
    expect(result.action_output).toBe('ON');
    expect(result.action).toBe('output_over_mqtt');
  });

  it('keeps boneio_id when switching from output_over_mqtt to cover_over_mqtt', () => {
    const prior = {
      action: 'output_over_mqtt',
      boneio_id: 'boneio_remote',
      boneio_output: 'OUT_01',
    };
    const result = cleanActionFields('cover_over_mqtt', prior);
    expect(result.boneio_id).toBe('boneio_remote');
    expect(result.boneio_output).toBeUndefined();
    expect(result.action).toBe('cover_over_mqtt');
  });

  it('preserves shared fields (min_duration, max_duration, repeat, repeat_interval) across all types', () => {
    const prior = {
      action: 'output',
      min_duration: 500,
      max_duration: 2000,
      repeat: true,
      repeat_interval: '800ms',
      boneio_output: 'OUT_01',
    };
    const result = cleanActionFields('mqtt', prior);
    expect(result.min_duration).toBe(500);
    expect(result.max_duration).toBe(2000);
    expect(result.repeat).toBe(true);
    expect(result.repeat_interval).toBe('800ms');
    expect(result.boneio_output).toBeUndefined();
  });

  it('strips light-specific fields (brightness, rgb, transition) when switching from remote_output to output', () => {
    const prior = {
      action: 'remote_output',
      remote_device: 'wled_strip',
      output_id: 'light_1',
      brightness: 128,
      rgb: [255, 0, 0],
      transition: '1s',
      colors: [[255, 0, 0], [0, 255, 0]],
    };
    const result = cleanActionFields('output', prior);
    expect(result.brightness).toBeUndefined();
    expect(result.rgb).toBeUndefined();
    expect(result.transition).toBeUndefined();
    expect(result.colors).toBeUndefined();
  });

  it('keeps remote_device when switching from remote_output to remote_cover', () => {
    const prior = {
      action: 'remote_output',
      remote_device: 'esphome_garage',
      output_id: 'relay_1',
      action_output: 'TOGGLE',
    };
    const result = cleanActionFields('remote_cover', prior);
    expect(result.remote_device).toBe('esphome_garage');
    expect(result.output_id).toBeUndefined();
    expect(result.action).toBe('remote_cover');
  });

  it('does not carry over undefined values', () => {
    const prior = { action: 'output', boneio_output: undefined };
    const result = cleanActionFields('output', prior);
    expect('boneio_output' in result).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// validateAction
// ---------------------------------------------------------------------------

const t = (key: string) => key;

describe('validateAction', () => {
  it('returns error when action type is missing', () => {
    expect(validateAction({}, t)).toBe('event_form.validation_action_type_required');
  });

  // output
  it('returns error for output without boneio_output', () => {
    expect(validateAction({ action: 'output' }, t)).toBe('event_form.validation_output_required');
  });

  it('returns null for valid output action', () => {
    expect(validateAction({ action: 'output', boneio_output: 'OUT_01' }, t)).toBeNull();
  });

  // cover
  it('returns error for cover without boneio_cover', () => {
    expect(validateAction({ action: 'cover' }, t)).toBe('event_form.validation_cover_required');
  });

  it('returns null for valid cover action', () => {
    expect(validateAction({ action: 'cover', boneio_cover: 'blind_01' }, t)).toBeNull();
  });

  // mqtt
  it('returns error for mqtt without topic', () => {
    expect(validateAction({ action: 'mqtt' }, t)).toBe('event_form.validation_topic_required');
  });

  it('returns null for valid mqtt action', () => {
    expect(validateAction({ action: 'mqtt', topic: 'home/light/set' }, t)).toBeNull();
  });

  // output_over_mqtt
  it('returns error for output_over_mqtt without boneio_id', () => {
    expect(validateAction({ action: 'output_over_mqtt', boneio_output: 'OUT_01' }, t))
      .toBe('event_form.validation_boneio_id_required');
  });

  it('returns error for output_over_mqtt without boneio_output', () => {
    expect(validateAction({ action: 'output_over_mqtt', boneio_id: 'boneio_led' }, t))
      .toBe('event_form.validation_output_required');
  });

  it('returns null for valid output_over_mqtt action', () => {
    expect(validateAction({
      action: 'output_over_mqtt',
      boneio_id: 'boneio_led',
      boneio_output: 'OUT_01',
    }, t)).toBeNull();
  });

  // remote_output
  it('returns error for remote_output without remote_device', () => {
    expect(validateAction({ action: 'remote_output', output_id: 'chr_02' }, t))
      .toBe('event_form.validation_remote_device_required');
  });

  it('returns error for remote_output without output_id', () => {
    expect(validateAction({ action: 'remote_output', remote_device: 'boneio_led' }, t))
      .toBe('event_form.validation_output_id_required');
  });

  it('returns null for valid remote_output action', () => {
    expect(validateAction({
      action: 'remote_output',
      remote_device: 'boneio_led',
      output_id: 'chr_02',
    }, t)).toBeNull();
  });

  it('returns error for remote_output CYCLE_COLOR without colors', () => {
    expect(validateAction({
      action: 'remote_output',
      remote_device: 'wled',
      output_id: 'strip_1',
      action_output: 'CYCLE_COLOR',
      colors: [],
    }, t)).toBe('event_form.validation_colors_required');
  });

  it('returns null for remote_output CYCLE_COLOR with colors', () => {
    expect(validateAction({
      action: 'remote_output',
      remote_device: 'wled',
      output_id: 'strip_1',
      action_output: 'CYCLE_COLOR',
      colors: [[255, 0, 0]],
    }, t)).toBeNull();
  });

  it('returns error for remote_output CYCLE_PRESET without presets', () => {
    expect(validateAction({
      action: 'remote_output',
      remote_device: 'wled',
      output_id: 'strip_1',
      action_output: 'CYCLE_PRESET',
      presets: [],
    }, t)).toBe('event_form.validation_presets_required');
  });

  // remote_cover
  it('returns error for remote_cover without remote_device', () => {
    expect(validateAction({ action: 'remote_cover', cover_id: 'blinds' }, t))
      .toBe('event_form.validation_remote_device_required');
  });

  it('returns error for remote_cover without cover_id', () => {
    expect(validateAction({ action: 'remote_cover', remote_device: 'esp_home' }, t))
      .toBe('event_form.validation_cover_id_required');
  });

  it('returns null for valid remote_cover action', () => {
    expect(validateAction({
      action: 'remote_cover',
      remote_device: 'esp_home',
      cover_id: 'blinds_01',
    }, t)).toBeNull();
  });

  // cover_over_mqtt
  it('returns error for cover_over_mqtt without boneio_id', () => {
    expect(validateAction({ action: 'cover_over_mqtt', boneio_cover: 'blind' }, t))
      .toBe('event_form.validation_boneio_id_required');
  });

  it('returns null for valid cover_over_mqtt action', () => {
    expect(validateAction({
      action: 'cover_over_mqtt',
      boneio_id: 'boneio_remote',
      boneio_cover: 'blind_01',
    }, t)).toBeNull();
  });
});
