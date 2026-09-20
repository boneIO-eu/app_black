import { describe, it, expect } from 'vitest';
import {
  actionTypes,
  formatFire,
  minutesToOffset,
  offsetToMinutes,
  triggerSummary,
  withTriggerField,
  type ScheduleEntry,
} from './scheduleTrigger';

/** The table and the editor only ever show these keys back, so echoing the key
 * is enough to assert which one was asked for. */
const t = (key: string) => key;

describe('offsetToMinutes', () => {
  it('reads the seconds the backend sends', () => {
    expect(offsetToMinutes(-900)).toBe('-15');
  });

  it('reads the string the editor last sent', () => {
    expect(offsetToMinutes('-15min')).toBe('-15');
    expect(offsetToMinutes('2h')).toBe('120');
    expect(offsetToMinutes('90')).toBe('2'); // bare number is seconds
  });

  it('is empty for nothing at all', () => {
    expect(offsetToMinutes(undefined)).toBe('');
    expect(offsetToMinutes('')).toBe('');
    expect(offsetToMinutes('nonsense')).toBe('');
  });
});

describe('minutesToOffset', () => {
  it('round-trips through offsetToMinutes', () => {
    expect(offsetToMinutes(minutesToOffset('-15'))).toBe('-15');
  });

  it('drops zero and empty rather than writing offset: 0min', () => {
    expect(minutesToOffset('0')).toBeUndefined();
    expect(minutesToOffset('')).toBeUndefined();
    expect(minutesToOffset('-')).toBeUndefined();
  });
});

describe('withTriggerField', () => {
  it('drops `at` when switching to a sun trigger', () => {
    const result = withTriggerField({ type: 'time', at: '20:00', days: 'daily' }, 'type', 'sun');
    expect(result).toEqual({ type: 'sun', days: 'daily' });
  });

  it('drops `event` when switching to a clock trigger', () => {
    const result = withTriggerField({ type: 'sun', event: 'sunset' }, 'type', 'time');
    expect(result).toEqual({ type: 'time' });
  });

  it('removes a field set to undefined', () => {
    expect(withTriggerField({ type: 'sun', offset: '-15min' }, 'offset', undefined)).toEqual({ type: 'sun' });
  });

  it('does not mutate the trigger it was given', () => {
    const trigger = { type: 'time', at: '20:00' };
    withTriggerField(trigger, 'type', 'sun');
    expect(trigger).toEqual({ type: 'time', at: '20:00' });
  });
});

describe('formatFire', () => {
  const now = new Date(2026, 8, 20, 12, 0);

  it('shows just the clock for today', () => {
    expect(formatFire(new Date(2026, 8, 20, 19, 5).toISOString(), now)).toBe('19:05');
  });

  it('adds the date for another day', () => {
    expect(formatFire(new Date(2026, 8, 21, 19, 5).toISOString(), now)).toBe('21.09 19:05');
  });

  it('is a dash for a schedule that is not armed', () => {
    expect(formatFire(null, now)).toBe('—');
    expect(formatFire('not a date', now)).toBe('—');
  });
});

describe('triggerSummary', () => {
  it('describes a clock trigger', () => {
    const entry: ScheduleEntry = { id: 's', trigger: { type: 'time', at: '20:00', days: 'weekdays' } };
    expect(triggerSummary(entry, t)).toBe('20:00 · schedule.days_weekdays');
  });

  it('describes a sun trigger with a negative offset', () => {
    const entry: ScheduleEntry = { id: 's', trigger: { type: 'sun', event: 'sunset', offset: -900 } };
    expect(triggerSummary(entry, t)).toBe('sun.anchor_sunset −15 min · schedule.days_daily');
  });

  it('defaults to a sun trigger, as the loader does', () => {
    expect(triggerSummary({ id: 's' }, t)).toBe('— · schedule.days_daily');
  });
});

describe('actionTypes', () => {
  it('lists each type once', () => {
    const entry: ScheduleEntry = {
      id: 's',
      actions: [{ action: 'output' }, { action: 'output' }, { action: 'cover' }],
    };
    expect(actionTypes(entry)).toEqual(['output', 'cover']);
  });

  it('is empty for a schedule that runs nothing', () => {
    expect(actionTypes({ id: 's' })).toEqual([]);
  });
});

describe('withTriggerField, switching to a clock trigger', () => {
  it('drops the offset too', () => {
    // The editor stops offering it, because "20:00 minus 15 minutes" is just
    // 19:45. Leaving it in the config would shift the schedule by an amount
    // nothing on screen explains — the backend applies it either way.
    const result = withTriggerField(
      { type: 'sun', event: 'sunset', offset: '-15min', days: 'daily' },
      'type',
      'time',
    );
    expect(result).toEqual({ type: 'time', days: 'daily' });
  });

  it('keeps the offset when staying on a sun trigger', () => {
    const result = withTriggerField({ type: 'sun', event: 'sunset', offset: '-15min' }, 'event', 'sunrise');
    expect(result).toEqual({ type: 'sun', event: 'sunrise', offset: '-15min' });
  });
});
