/**
 * Shapes for `config.schema.json` and for the config data it describes.
 *
 * The schema is generated from `schema.yaml` (see `boneio/webui/schema/`), so
 * only the keywords that generator emits are spelled out. Anything else —
 * the `x-*` extensions most of all — is reachable through the index signature
 * as `unknown` and has to be narrowed where it is read.
 */

/** Any value that survives a JSON (or YAML) round trip. */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

/** A config object whose shape is not known here: read fields as `unknown`. */
export type ConfigRecord = Record<string, unknown>;

/** One node of the JSON Schema. */
export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  examples?: unknown[];
  enum?: unknown[];
  const?: unknown;
  properties?: Record<string, JsonSchema>;
  /** The generator never emits tuple schemas, so `items` is always one schema. */
  items?: JsonSchema;
  required?: string[];
  oneOf?: JsonSchema[];
  anyOf?: JsonSchema[];
  allOf?: JsonSchema[];
  additionalProperties?: boolean | JsonSchema;
  $ref?: string;
  definitions?: Record<string, JsonSchema>;
  $defs?: Record<string, JsonSchema>;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  format?: string;
  'x-timeperiod'?: boolean;
  'x-yaml-boolean'?: boolean;
  [key: string]: unknown;
}

/** True for a plain object (not an array, not null). */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
