import { describe, it, expect } from 'vitest';
import {
  buildLocalInputsSchema,
  pickInputVariantSchema,
  withFilteredInputs,
  type LocalInputType,
} from '../helpers/inputSchema';
import type { JsonSchema } from '@/types/jsonSchema';

/** The per-type item schemas buildLocalInputsSchema stores under 'x-variants'. */
const variantsOf = (schema: JsonSchema | undefined) =>
  schema?.items?.['x-variants'] as Record<LocalInputType, JsonSchema> | undefined;

/** Minimal stand-in for config.schema.json — only what these helpers read. */
const mainSchema = {
  properties: {
    event: {
      type: 'array',
      items: {
        properties: {
          boneio_input: { type: 'string', enum: ['in_01', 'in_50'] },
          device_class: { type: 'string', enum: ['button', 'doorbell', 'motion'] },
          bounce_time: { default: '30ms' },
          actions: { properties: { single: {}, double: {}, long: {} } },
          mqtt_sequences: {},
        },
      },
    },
    binary_sensor: {
      type: 'array',
      items: {
        properties: {
          boneio_input: { type: 'string', enum: ['in_01', 'in_50'] },
          device_class: {
            type: 'string',
            enum: ['door', 'gas', 'moisture', 'motion', 'smoke', 'tamper', 'window'],
          },
          bounce_time: { default: '120ms' },
          actions: { properties: { pressed: {}, released: {} } },
          initial_send: { type: 'boolean' },
        },
      },
    },
  },
};

const allowed = ['in_01'];

describe('withFilteredInputs', () => {
  it('drops inputs the board version does not have', () => {
    const filtered = withFilteredInputs(mainSchema.properties.event, allowed);
    expect(filtered.items?.properties?.boneio_input?.enum).toEqual(['in_01']);
  });

  it('leaves a schema without boneio_input untouched', () => {
    const schema = { items: { properties: { id: {} } } };
    expect(withFilteredInputs(schema, allowed)).toBe(schema);
  });
});

describe('buildLocalInputsSchema', () => {
  const merged = buildLocalInputsSchema(mainSchema, allowed);

  it('keeps properties that only binary_sensor has', () => {
    expect(merged?.items?.properties?.initial_send).toBeDefined();
  });

  it('filters boneio_input in the merged schema and in both variants', () => {
    expect(merged?.items?.properties?.boneio_input?.enum).toEqual(['in_01']);
    expect(variantsOf(merged)?.event.properties?.boneio_input?.enum).toEqual(['in_01']);
    expect(variantsOf(merged)?.binary_sensor.properties?.boneio_input?.enum).toEqual(['in_01']);
  });

  it('carries both device_class lists, unmixed', () => {
    const variants = variantsOf(merged);
    expect(variants?.event.properties?.device_class?.enum).toEqual(['button', 'doorbell', 'motion']);
    expect(variants?.binary_sensor.properties?.device_class?.enum).toContain('window');
    expect(variants?.binary_sensor.properties?.device_class?.enum).not.toContain('doorbell');
  });

  it('falls back to whichever schema exists when the other is missing', () => {
    expect(buildLocalInputsSchema({ properties: { event: mainSchema.properties.event } }, allowed))
      .toMatchObject({ type: 'array' });
    expect(buildLocalInputsSchema({ properties: {} }, allowed)).toBeUndefined();
  });
});

describe('pickInputVariantSchema', () => {
  const merged = buildLocalInputsSchema(mainSchema, allowed);

  it('gives a binary sensor its own device classes, not the event ones', () => {
    const schema = pickInputVariantSchema(merged, 'binary_sensor');
    expect(schema?.items?.properties?.device_class?.enum).not.toContain('doorbell');
    expect(schema?.items?.properties?.device_class?.enum).toContain('smoke');
  });

  it('gives an event its own device classes and action types', () => {
    const schema = pickInputVariantSchema(merged, 'event');
    expect(schema?.items?.properties?.device_class?.enum).toEqual(['button', 'doorbell', 'motion']);
    expect(Object.keys(schema?.items?.properties?.actions?.properties ?? {})).toContain('single');
  });

  it('gives each form the action types it edits', () => {
    const bs = pickInputVariantSchema(merged, 'binary_sensor');
    expect(Object.keys(bs?.items?.properties?.actions?.properties ?? {})).toEqual(['pressed', 'released']);
  });

  it('keeps per-type bounce_time defaults apart', () => {
    expect(pickInputVariantSchema(merged, 'event')?.items?.properties?.bounce_time?.default).toBe('30ms');
    expect(pickInputVariantSchema(merged, 'binary_sensor')?.items?.properties?.bounce_time?.default).toBe('120ms');
  });

  it('passes a plain section schema through unchanged', () => {
    const plain = mainSchema.properties.binary_sensor;
    expect(pickInputVariantSchema(plain, 'binary_sensor')).toBe(plain);
  });
});
