import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { ACTION_COVER_OPTIONS, ACTION_OUTPUT_OPTIONS, ACTION_TYPE_OPTIONS } from './options';

interface ActionDef {
  properties: Record<string, { enum?: string[] }>;
}

const schema = JSON.parse(
  readFileSync(new URL('../../../../public/schema/event.schema.json', import.meta.url), 'utf-8'),
) as { $defs: Record<string, ActionDef> };
const actions = Object.values(schema.$defs).filter((def) => def.properties?.action);

describe('action options', () => {
  it('lists every action type the schema has', () => {
    // Each type is listed in every case the controller reads it in.
    const types = new Set(actions.flatMap((def) => def.properties.action.enum ?? []).map((t) => t.toLowerCase()));
    expect([...ACTION_TYPE_OPTIONS].sort()).toEqual([...types].sort());
  });

  it('lists the output and cover commands the schema has', () => {
    const enumOf = (field: string) => [
      ...new Set(actions.find((def) => def.properties[field])?.properties[field].enum?.map((c) => c.toUpperCase())),
    ];
    expect([...ACTION_OUTPUT_OPTIONS].sort()).toEqual(enumOf('action_output').sort());
    expect([...ACTION_COVER_OPTIONS].sort()).toEqual(enumOf('action_cover').sort());
  });
});
