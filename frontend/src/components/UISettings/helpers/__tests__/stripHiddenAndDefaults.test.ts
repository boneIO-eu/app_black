/**
 * What the panel strips from a section before saving it.
 *
 * `actions` comes in two shapes. Inputs keep them per click type
 * (`{single: [...], double: [...]}`); a schedule keeps a plain list. The list
 * went through the dict branch, lost every action, and the backend then refused
 * the schedule for having none — which is how "I added an action, it shows in
 * the list, and saving says there are no actions" came about.
 */
import { describe, expect, it } from 'vitest';
import { stripHiddenAndDefaults } from '../configSchemaUtils';
// The schemas the panel really uses, as generated from schema.yaml.
import scheduleSchema from '../../../../../../boneio/webui/schema/schedule.schema.json';
import eventSchema from '../../../../../../boneio/webui/schema/event.schema.json';

const schemas = {
  schedule: scheduleSchema.properties.schedule,
  event: eventSchema.properties.event,
};

const sectionSchema = (section: keyof typeof schemas) => schemas[section];

const schedule = <A,>(actions: A) => [
  {
    name: 'uruchomienie swiatel',
    enabled: true,
    trigger: { type: 'sun', event: 'sunrise', days: 'daily' },
    actions,
  },
];

describe('a schedule keeps its actions', () => {
  it('saves the action that was added in the form', () => {
    const saved = stripHiddenAndDefaults(
      schedule([{ action: 'output', boneio_output: 'OUT_31', action_output: 'ON' }]),
      sectionSchema('schedule'),
    );

    expect(saved[0].actions).toEqual([
      { action: 'output', boneio_output: 'OUT_31', action_output: 'ON' },
    ]);
  });

  it('still drops what only repeats a default inside each action', () => {
    const saved = stripHiddenAndDefaults(
      schedule([
        { action: 'output', boneio_output: 'OUT_31', action_output: 'TOGGLE', data: {}, repeat: false },
      ]),
      sectionSchema('schedule'),
    );

    expect(saved[0].actions).toEqual([{ action: 'output', boneio_output: 'OUT_31' }]);
  });

  it('keeps the actions in the order they run', () => {
    const saved = stripHiddenAndDefaults(
      schedule([
        { action: 'output', boneio_output: 'OUT_01', action_output: 'ON' },
        { action: 'cover', boneio_cover: 'salon', action_cover: 'CLOSE' },
        { action: 'output', boneio_output: 'OUT_02', action_output: 'OFF' },
      ]),
      sectionSchema('schedule'),
    );

    expect(saved[0].actions.map((a: { boneio_output?: string; boneio_cover?: string }) =>
      a.boneio_output ?? a.boneio_cover,
    )).toEqual(['OUT_01', 'salon', 'OUT_02']);
  });

  it('leaves the rest of the entry to the ordinary default stripping', () => {
    const saved = stripHiddenAndDefaults(
      schedule([{ action: 'output', boneio_output: 'OUT_31', action_output: 'ON' }]),
      sectionSchema('schedule'),
    );

    // enabled, trigger.type and trigger.days are all schema defaults.
    expect(saved[0]).toEqual({
      name: 'uruchomienie swiatel',
      trigger: { event: 'sunrise' },
      actions: [{ action: 'output', boneio_output: 'OUT_31', action_output: 'ON' }],
    });
  });
});

describe('an input keeps its per-click-type actions', () => {
  it('is unchanged by the list handling', () => {
    const saved = stripHiddenAndDefaults(
      [
        {
          id: 'in_01',
          actions: {
            single: [{ action: 'output', boneio_output: 'OUT_01', action_output: 'TOGGLE' }],
            double: [{ action: 'cover', boneio_cover: 'salon', action_cover: 'OPEN' }],
            long: [],
          },
        },
      ],
      sectionSchema('event'),
    );

    expect(saved[0].actions).toEqual({
      single: [{ action: 'output', boneio_output: 'OUT_01' }],
      double: [{ action: 'cover', boneio_cover: 'salon', action_cover: 'OPEN' }],
    });
  });
});
