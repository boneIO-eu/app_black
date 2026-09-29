/**
 * Why the panel dropped back to the login screen.
 *
 * The backend says it in the 401's `code`, but the request that carried it
 * belongs to whatever screen was open, and the login screen that appears next
 * has nothing to read it from. So the interceptor notes the reason here and
 * the login screen reads it once.
 */

const KEY = 'boneio:signout-reason';

/** The codes worth telling the user about; anything else is a plain sign-out. */
export const SIGNOUT_REASONS = ['session_locked', 'session_revoked', 'account_gone'] as const;
export type SignoutReason = (typeof SIGNOUT_REASONS)[number];

const isReason = (code: unknown): code is SignoutReason =>
  typeof code === 'string' && (SIGNOUT_REASONS as readonly string[]).includes(code);

/**
 * Note why a 401 signed the panel out.
 *
 * Only a known reason is written, and nothing is ever cleared here: the
 * requests still in flight when the token is dropped come back as 401s with no
 * code ("No authorization header"), and letting them in would overwrite the
 * one reason that mattered.
 *
 * @param code - The `code` field of the 401 body.
 */
export function rememberSignoutReason(code: unknown): void {
  if (!isReason(code)) return;
  try {
    sessionStorage.setItem(KEY, code);
  } catch {
    // Storage off (private mode, say): the login screen just shows no reason.
  }
}

/**
 * Read the noted reason, if any.
 *
 * Separate from clearing it: React calls a state initialiser twice in
 * StrictMode, and a read that also cleared would leave the second call —
 * the one kept — with nothing.
 */
export function readSignoutReason(): SignoutReason | null {
  try {
    const code = sessionStorage.getItem(KEY);
    return isReason(code) ? code : null;
  } catch {
    return null;
  }
}

/** Forget the reason once it has been shown, so a later sign-out starts clean. */
export function clearSignoutReason(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Nothing stored, then.
  }
}
