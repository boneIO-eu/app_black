import * as yaml from 'js-yaml';

export type Pasted = { section: string; data: unknown } | { error: 'empty' | 'unparsable' | 'shape' };

/**
 * A config section pasted from an AI chat: YAML (JSON is YAML too), often in
 * a ``` fence, with the section's name as its one top-level key - `output:`
 * and the list under it. The name is how the paste says which section it
 * replaces, so no menu is needed and a wrong pick cannot happen.
 */
export function parsePastedSection(text: string): Pasted {
  const fenced = text.match(/```[a-z]*\n([\s\S]*?)```/i);
  const body = (fenced ? fenced[1] : text).trim();
  if (!body) return { error: 'empty' };
  let parsed: unknown;
  try {
    parsed = yaml.load(body);
  } catch {
    return { error: 'unparsable' };
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { error: 'shape' };
  const keys = Object.keys(parsed);
  if (keys.length !== 1 || !/^[a-z][a-z0-9_]*$/.test(keys[0])) return { error: 'shape' };
  const data = (parsed as Record<string, unknown>)[keys[0]];
  if (!data || typeof data !== 'object') return { error: 'shape' };
  return { section: keys[0], data };
}
