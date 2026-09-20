/**
 * One readable line describing what an action does.
 *
 * So a list of actions can be read without opening any of them. An action card
 * is ~250px tall whether it says one thing or ten, which turned "this switch
 * turns on two lights" into a page of scrolling.
 */
import { formatActionLabel } from '../ActionFields/helpers';

/** One action, as the config carries it. Its fields depend on `action`. */
export type ActionEntry = Record<string, unknown>;

/** Anything with an id and possibly a friendlier name, for naming a target. */
export interface NamedEntity {
  id?: string;
  name?: string;
  boneio_output?: string;
}

/** The lists a summary needs to turn an id into the name someone gave it.
 *
 * Deliberately the narrowest shape that works, so every caller's own entity
 * types are assignable without a cast. */
export interface SummaryEntities {
  allOutputs?: readonly NamedEntity[];
  allCovers?: readonly NamedEntity[];
  allVirtualSwitches?: readonly NamedEntity[];
  allRemoteDevices?: readonly NamedEntity[];
}

const str = (value: unknown): string => (typeof value === 'string' ? value : '');

/** "Verb: target", or just the verb while there is no target yet.
 *
 * A colon rather than a space because the target is a proper noun in a
 * sentence the verb governs: Polish would have to decline it ("Włącz kuchnię",
 * not "Włącz Kuchnia"), and no UI string should have to. */
const join = (verb: string, target: string): string =>
  target ? `${verb}: ${target}` : verb;

/** "thing @ device", or just whichever half exists. */
const at = (thing: string, device: string): string =>
  thing && device ? `${thing} @ ${device}` : thing || device;

/** The friendliest name for a target, falling back to the id it was given. */
function nameOf(id: string, entities: readonly NamedEntity[] | undefined): string {
  if (!id) return '';
  const match = (entities || []).find(
    (entity) => entity.id === id || entity.boneio_output === id,
  );
  const name = str(match?.name).trim();
  return name || id;
}

/** How many conditions an action carries, in either of the two shapes. */
export function conditionCount(action: ActionEntry): number {
  if (action.condition && typeof action.condition === 'object') return 1;
  const conditions = action.conditions as { list?: unknown[] } | undefined;
  if (conditions && Array.isArray(conditions.list)) return conditions.list.length;
  return 0;
}

/**
 * Describe one action in a single line, e.g. "Turn on Living room · 2 conditions".
 *
 * @param action The action.
 * @param t Translator.
 * @param entities Lists used to turn an id into the name someone gave it.
 * @returns A line for the collapsed row. Never empty: an action that has been
 *   added but not filled in reads as its type, which is what it is.
 */
export function actionSummary(
  action: ActionEntry,
  t: (key: string) => string,
  entities: SummaryEntities = {},
): string {
  const kind = str(action.action) || 'output';
  const verb = (field: string, fallback: string) =>
    formatActionLabel(str(action[field]) || fallback, t);

  let line: string;
  switch (kind) {
    case 'output':
      line = join(verb('action_output', 'TOGGLE'), nameOf(str(action.boneio_output), entities.allOutputs));
      break;
    case 'cover':
      line = join(verb('action_cover', 'TOGGLE'), nameOf(str(action.boneio_cover), entities.allCovers));
      break;
    case 'virtual_switch':
      line = join(verb('action_output', 'TOGGLE'), nameOf(str(action.boneio_virtual_switch), entities.allVirtualSwitches));
      break;
    case 'mqtt':
      line = join('MQTT', str(action.topic));
      break;
    case 'output_over_mqtt':
      line = join(verb('action_output', 'TOGGLE'), at(str(action.boneio_output), str(action.boneio_id)));
      break;
    case 'cover_over_mqtt':
      line = join(verb('action_cover', 'TOGGLE'), at(str(action.boneio_cover), str(action.boneio_id)));
      break;
    case 'remote_output':
      line = join(verb('action_output', 'TOGGLE'), at(str(action.output_id), nameOf(str(action.remote_device), entities.allRemoteDevices)));
      break;
    case 'remote_cover':
      line = join(verb('action_cover', 'TOGGLE'), at(str(action.cover_id), nameOf(str(action.remote_device), entities.allRemoteDevices)));
      break;
    default:
      line = kind;
  }

  if (!line) line = kind;

  const conditions = conditionCount(action);
  const parts = [line];
  // "conditions: 2" rather than "2 conditions": Polish needs three plural
  // forms for that number and this string does not get to pick one.
  if (conditions > 0) parts.push(`${t('event_form.conditions')}: ${conditions}`);
  if (action.delay) parts.push(`${t('actions.delay_execution')} ${String(action.delay)}`);
  return parts.join(' · ');
}

/** True when the action has not been pointed at anything yet. */
export function actionIsIncomplete(action: ActionEntry): boolean {
  const kind = str(action.action) || 'output';
  switch (kind) {
    case 'output':
      return !action.boneio_output;
    case 'cover':
      return !action.boneio_cover;
    case 'virtual_switch':
      return !action.boneio_virtual_switch;
    case 'mqtt':
      return !action.topic;
    case 'output_over_mqtt':
      return !action.boneio_output || !action.boneio_id;
    case 'cover_over_mqtt':
      return !action.boneio_cover || !action.boneio_id;
    case 'remote_output':
      return !action.output_id || !action.remote_device;
    case 'remote_cover':
      return !action.cover_id || !action.remote_device;
    default:
      return false;
  }
}
