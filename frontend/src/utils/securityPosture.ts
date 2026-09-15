/**
 * The decisions the security UI makes, kept out of the components.
 *
 * Three of them are worth pinning down: where a check's Fix button goes,
 * which text wins when the panel has no translation for a check, and whether
 * the prompt after an update appears at all. Each is a rule that can be wrong
 * in a way nobody notices — a Fix button leading nowhere, a dotted key shown
 * as a sentence, a notice that either never appears or appears every time.
 *
 * The frontend has no DOM in its test environment, so a rule that lives inside
 * a component is a rule that is not tested.
 */
import type { SecurityCheck, SecurityPosture } from '../hooks/useSecurityPosture';

/**
 * The route that fixes a check, or null when there is no control for it.
 *
 * The backend names a destination rather than a URL: a bare name is a
 * Settings section, `system:<anchor>` is a spot on the System page. Keeping
 * the mapping here means a new check needs no frontend release to be
 * actionable, as long as it points at somewhere that already exists.
 */
export function fixRoute(check: Pick<SecurityCheck, 'settings_section'>): string | null {
  const target = check.settings_section;
  if (!target) return null;
  if (target.startsWith('system:')) {
    return `/system#${target.slice('system:'.length)}`;
  }
  return `/settings/${target}`;
}

/**
 * Translated text for a check, falling back to what the backend said.
 *
 * The backend is the source of truth and writes in English; the panel
 * translates by check id. A check this bundle has never heard of — newer
 * backend, older frontend — then still reads as a sentence rather than a
 * dotted key, because `t` returns the key itself when there is no translation.
 */
export function checkText(
  t: (key: string) => string,
  id: string,
  field: string,
  fallback: string,
): string {
  const key = `security.checks.${id}.${field}`;
  const value = t(key);
  return value === key || !value ? fallback : value;
}

export interface PromptDecision {
  show: boolean;
  /** True when a previous version was recorded, so "updated to X" is truthful. */
  knownUpgrade: boolean;
}

/**
 * Whether the post-update security prompt should be on screen.
 *
 * It appears for an administrator, once per version, and only when something
 * actionable is outstanding — interrupting someone to say everything is fine
 * is how the next notice gets dismissed unread, and the INFO advice applies
 * to nearly every device, so it would fire for everyone forever.
 *
 * With no recorded version there is no evidence an update happened; this
 * browser may simply never have been here. The prompt still appears, because
 * a device that has been running since 1.5 is exactly the one that needs it,
 * but `knownUpgrade` tells the caller not to claim a version change it cannot
 * demonstrate.
 */
export function promptDecision(input: {
  isAdmin: boolean;
  version: string | null;
  seenVersion: string | null;
  posture: SecurityPosture | null;
  dismissed: boolean;
}): PromptDecision {
  const { isAdmin, version, seenVersion, posture, dismissed } = input;
  const knownUpgrade = Boolean(seenVersion) && seenVersion !== version;

  if (!isAdmin || !version || !posture || dismissed) return { show: false, knownUpgrade };
  if (posture.summary.actionable === 0) return { show: false, knownUpgrade };
  if (seenVersion === version) return { show: false, knownUpgrade };

  return { show: true, knownUpgrade };
}
