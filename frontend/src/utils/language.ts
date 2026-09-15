/**
 * Language selection, kept free of `localStorage` and `navigator` so the rules
 * can be tested directly — the wizard is the one screen a user cannot read
 * their way out of if this picks wrong.
 */

/** Used when neither storage nor the browser names a language we ship. */
export const FALLBACK_LANGUAGE = 'en';

/**
 * Choose the language to start in.
 *
 * @param stored - Previously chosen code, or null. Honoured only if supported,
 *   so a hand-edited localStorage entry cannot strand the UI on bare keys.
 * @param preferred - The browser's language tags, most-wanted first. Matched on
 *   the primary subtag, so `de-AT` resolves to `de` once we ship German.
 * @param supported - Codes we actually have translations for.
 */
export function pickLanguage(
  stored: string | null | undefined,
  preferred: readonly (string | undefined)[],
  supported: readonly string[],
): string {
  if (stored && supported.includes(stored)) {
    return stored;
  }

  for (const tag of preferred) {
    const code = tag?.toLowerCase().split('-')[0];
    if (code && supported.includes(code)) {
      return code;
    }
  }

  return supported.includes(FALLBACK_LANGUAGE) ? FALLBACK_LANGUAGE : supported[0];
}
