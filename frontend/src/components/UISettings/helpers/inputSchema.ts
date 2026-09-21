/**
 * Schema helpers for the virtual 'local_inputs' section.
 *
 * 'local_inputs' shows event and binary_sensor items in one list, but the two
 * schemas overlap without either being a superset: device_class, actions and
 * bounce_time differ, and initial_send exists only on binary_sensor. Feeding one
 * schema to both forms offered binary sensors the event device classes
 * (button/doorbell/motion) instead of their own (door, window, smoke, …).
 *
 * So the merged schema keeps the union of the properties and carries both item
 * schemas under 'x-variants'; FormRenderer then hands each form its own.
 */

/** Item type held by the merged section. */
export type LocalInputType = 'event' | 'binary_sensor';

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Narrow a schema's boneio_input enum to the inputs this board actually has. */
export function withFilteredInputs(schema: any, allowedInputs: string[]): any {
  const current = schema?.items?.properties?.boneio_input?.enum;
  if (!current) return schema;
  return {
    ...schema,
    items: {
      ...schema.items,
      properties: {
        ...schema.items.properties,
        boneio_input: {
          ...schema.items.properties.boneio_input,
          enum: current.filter((v: string) => allowedInputs.includes(v)),
        },
      },
    },
  };
}

/**
 * Build the merged schema for 'local_inputs' from the full config schema.
 *
 * @param mainSchema Parsed config.schema.json.
 * @param allowedInputs boneio_input values this board version exposes.
 */
export function buildLocalInputsSchema(mainSchema: any, allowedInputs: string[]): any {
  const eventSchema = withFilteredInputs(mainSchema?.properties?.event, allowedInputs);
  const bsSchema = withFilteredInputs(mainSchema?.properties?.binary_sensor, allowedInputs);
  if (!eventSchema?.items || !bsSchema?.items) return eventSchema || bsSchema;

  return {
    ...eventSchema,
    items: {
      ...eventSchema.items,
      properties: {
        ...bsSchema.items.properties,
        ...eventSchema.items.properties,
      },
      'x-variants': {
        event: eventSchema.items,
        binary_sensor: bsSchema.items,
      },
    },
  };
}

/**
 * Pick the schema for the input type being edited.
 * Falls back to the given schema when there are no variants (plain
 * 'event' / 'binary_sensor' sections, or an older cached schema).
 */
export function pickInputVariantSchema(schema: any, type: LocalInputType): any {
  const variant = schema?.items?.['x-variants']?.[type];
  return variant ? { ...schema, items: variant } : schema;
}
