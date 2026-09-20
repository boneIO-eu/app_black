/**
 * Turn a few answers into the entries a presence simulation is made of.
 *
 * Deliberately a generator of ordinary config, not a subsystem. What comes out
 * is one virtual switch and a handful of schedules — the same ones you would
 * write by hand, editable afterwards on their own pages, with nothing extra
 * running at runtime. The wizard is a shortcut, not a layer.
 */

/** Everything generated carries this prefix, so a second run can recognise its
 *  own output and replace it instead of adding a second copy. */
export const PRESENCE_PREFIX = 'presence_';

/** The id of the flag that arms the simulation. */
export const PRESENCE_FLAG = `${PRESENCE_PREFIX}away`;

/** How long the arranged part of the evening lasts, in minutes.
 *
 * Everything after the first light is spread across this window, and the first
 * light's sun anchor is capped to its start. Two hours is long enough to look
 * like an evening and short enough that midsummer dusk (21:50 here) still
 * leaves one. */
const EVENING_MINUTES = 120;

export interface PresenceOptions {
  /** Output ids to use, in the order they should come on. */
  lights: string[];
  /** When the evening ends and everything goes off, "HH:MM". */
  endsAt: string;
  /** How random: spreads the firing times and, above `calm`, skips steps. */
  randomness: 'calm' | 'normal' | 'lively';
  /** Name for the flag, shown in Home Assistant. */
  flagName?: string;
}

export interface PresenceResult {
  virtualSwitch: Record<string, unknown>;
  schedules: Record<string, unknown>[];
  /** One line per step, for the summary the wizard shows before writing. */
  preview: { at: string; label: string }[];
}

/** jitter spreads *when* a step happens; probability decides *whether*.
 *
 * Only the second one breaks the pattern an observer reads over three
 * evenings — the same four steps every night is a timer, not a household. */
const RANDOMNESS = {
  calm: { jitter: '15min', probability: 1 },
  normal: { jitter: '25min', probability: 0.85 },
  lively: { jitter: '40min', probability: 0.7 },
} as const;

/** Minutes since midnight, from "HH:MM". */
function toMinutes(clock: string): number {
  const [hour, minute] = clock.split(':').map((part) => parseInt(part, 10));
  return hour * 60 + minute;
}

/** "HH:MM" from minutes since midnight, wrapping across midnight. */
function toClock(minutes: number): string {
  const wrapped = ((minutes % 1440) + 1440) % 1440;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(Math.floor(wrapped / 60))}:${pad(wrapped % 60)}`;
}

/** The gate every generated schedule carries: only while the flag is on. */
function armedOnly() {
  return { type: 'state', entity: 'virtual_switch', entity_id: PRESENCE_FLAG, state: 'is_on' };
}

/**
 * Build the flag and the schedules.
 *
 * The shape of an evening: the first light follows dusk, so it tracks the
 * season. The rest divide the two hours before bedtime evenly — dusk is 15:30
 * in December here and 21:50 in June, so a step placed relative to it would be
 * on at four in the afternoon in winter, and dividing a fixed window keeps the
 * steps in order and apart whatever the count.
 *
 * Dusk itself is capped to the start of that window, because in midsummer it
 * arrives after the evening would otherwise be over.
 *
 * @param options What the wizard asked.
 * @returns The entries to write, and a preview of the evening they describe.
 */
export function buildPresenceSimulation(options: PresenceOptions): PresenceResult {
  const lights = options.lights.filter(Boolean);
  const { jitter, probability } = RANDOMNESS[options.randomness];
  const end = toMinutes(options.endsAt);
  // The structured part of the evening: the last two hours before bedtime.
  // Dusk is not allowed past its start, or midsummer leaves no evening at all.
  const windowStart = end - EVENING_MINUTES;
  const cap = toClock(windowStart);
  // The window is divided evenly, so the steps stay in order and apart
  // whatever the count. Fixed hourly gaps counted back from bedtime collided
  // with the cap at three lights and inverted the order at four.
  const slot = EVENING_MINUTES / Math.max(lights.length, 1);

  const schedules: Record<string, unknown>[] = [];
  const preview: { at: string; label: string }[] = [];

  lights.forEach((light, index) => {
    const first = index === 0;
    const at = toClock(windowStart + index * slot);
    schedules.push({
      id: `${PRESENCE_PREFIX}step_${index + 1}`,
      name: `Presence — ${light}`,
      enabled: true,
      trigger: first
        ? { type: 'sun', event: 'civil_dusk', offset: '-10min', latest: cap, jitter, days: 'daily' }
        : { type: 'time', at, jitter, days: 'daily' },
      condition: armedOnly(),
      actions: [
        // Turning the previous one off as the next comes on is what makes it
        // look like someone walking through the house rather than the whole
        // ground floor lighting up.
        ...(first ? [] : [{ action: 'output', boneio_output: lights[index - 1], action_output: 'OFF', probability }]),
        { action: 'output', boneio_output: light, action_output: 'ON', probability },
      ],
    });
    preview.push({ at: first ? `~${cap}` : `~${at}`, label: light });
  });

  if (lights.length > 0) {
    schedules.push({
      id: `${PRESENCE_PREFIX}off`,
      name: 'Presence — end of evening',
      enabled: true,
      trigger: { type: 'time', at: options.endsAt, jitter, days: 'daily' },
      condition: armedOnly(),
      // No probability here, ever. A step that might not happen is realistic;
      // a light that might not go off burns until morning and announces that
      // nobody is home, which is the opposite of the point.
      actions: lights.map((light) => ({ action: 'output', boneio_output: light, action_output: 'OFF' })),
    });
    preview.push({ at: options.endsAt, label: 'off' });
  }

  const virtualSwitch = {
    id: PRESENCE_FLAG,
    name: options.flagName || 'Away',
    restore_state: true,
    show_in_ha: true,
    icon: 'mdi:home-export-outline',
    actions: {
      // Catching up: armed at 22:00, after the dusk schedule has already
      // passed with the flag off. The schedule cannot help — its moment is
      // gone — but this can, because it carries its own conditions.
      on_turn_on: lights.length === 0 ? [] : [
        {
          action: 'output',
          boneio_output: lights[0],
          action_output: 'ON',
          conditions: {
            mode: 'and',
            list: [
              { type: 'sun', after: 'civil_dusk' },
              { type: 'time', before: options.endsAt },
            ],
          },
        },
      ],
      // Cleaning up: coming home must put back whatever the simulation left on.
      on_turn_off: lights.map((light) => ({
        action: 'output',
        boneio_output: light,
        action_output: 'OFF',
      })),
    },
  };

  return { virtualSwitch, schedules, preview };
}

/** True for an entry this wizard generated, by id. */
export function isGenerated(entry: { id?: string }): boolean {
  return typeof entry.id === 'string' && entry.id.startsWith(PRESENCE_PREFIX);
}

/**
 * Put the generated entries into a section, replacing an earlier run.
 *
 * Anything the wizard did not generate is left exactly where it was, in its
 * original order: someone who ran this once and then wrote three schedules of
 * their own must not lose them by running it again.
 */
export function mergeGenerated<T extends { id?: string }>(existing: T[], generated: T[]): T[] {
  return [...existing.filter((entry) => !isGenerated(entry)), ...generated];
}
