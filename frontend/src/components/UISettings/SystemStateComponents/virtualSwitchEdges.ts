/**
 * The action lists a virtual switch carries, and the one rule about editing them.
 *
 * Split out of `VirtualSwitchSection.tsx` so it can be tested: the component
 * itself renders, and this project's vitest runs in node with no DOM.
 */

/** The two edges a virtual switch can act on. Mirrors `boneio/schema/schema.yaml`.
 *
 * Not `on`/`off`: YAML reads those two as booleans, so the keys would silently
 * become `true` and `false` and nothing would ever match them. */
export const EDGES = ['on_turn_on', 'on_turn_off'] as const;
export type Edge = typeof EDGES[number];

/** One action, as the config carries it. Its fields depend on `action`. */
export type ActionEntry = Record<string, unknown>;

/** One virtual switch, as `boneio/schema/schema.yaml` defines it. */
export interface SwitchEntry {
  id: string;
  name?: string;
  area?: string;
  icon?: string;
  restore_state?: boolean;
  initial?: boolean;
  show_in_ha?: boolean;
  actions?: Partial<Record<Edge, ActionEntry[]>>;
  [key: string]: unknown;
}

/**
 * Replace one edge's action list on a switch.
 *
 * An emptied edge is removed rather than left as `on_turn_off: []`, and a
 * switch with no edges left loses `actions:` entirely. Both are valid config,
 * but both read as "this switch does something" in the YAML, which is the
 * opposite of true — and the empty keys accumulate, because every switch you
 * open and close again would otherwise gain a pair of them.
 *
 * @param entry The switch to change. Not mutated.
 * @param edge Which edge's list to replace.
 * @param next The new list.
 * @returns A new switch.
 */
export function withEdgeActions(
  entry: SwitchEntry,
  edge: Edge,
  next: ActionEntry[],
): SwitchEntry {
  const actions = { ...(entry.actions || {}), [edge]: next };
  if (next.length === 0) delete actions[edge];
  if (Object.keys(actions).length === 0) {
    const rest = { ...entry };
    delete rest.actions;
    return rest;
  }
  return { ...entry, actions };
}
