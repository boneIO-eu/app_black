/**
 * Turning a name somebody typed into an identifier a machine can carry.
 *
 * Mirrors `boneio/core/utils/naming.py`. The panel needs it to show what the
 * name will become and to spot a collision before saving; the backend is the
 * one that decides. If the two ever disagree, the backend is right — which is
 * why the panel shows the result rather than sending it.
 */

/** Letters that do not decompose under NFKD, so stripping combining marks
 *  leaves them intact. Polish `ł` is the one that matters here. */
const UNDECOMPOSABLE: Record<string, string> = {
  'ł': 'l',
  'đ': 'd',
  'ø': 'o',
  'ß': 'ss',
  'æ': 'ae',
  'œ': 'oe',
  'þ': 'th',
};

/**
 * Make an identifier out of a display name.
 *
 * @param name The display name, in any language.
 * @returns The identifier, or `""` when the name has nothing usable in it.
 */
export function slugifyId(name: string): string {
  let text = (name || '').trim().toLowerCase();
  for (const [char, replacement] of Object.entries(UNDECOMPOSABLE)) {
    text = text.split(char).join(replacement);
  }
  text = text.normalize('NFKD').replace(/\p{M}/gu, '');
  return text.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

/** The identifier for one entry: an explicit id, else the one from its name. */
export function resolveId(entry: { id?: string; name?: string }): string {
  const explicit = (entry.id || '').trim();
  return explicit || slugifyId(entry.name || '');
}
