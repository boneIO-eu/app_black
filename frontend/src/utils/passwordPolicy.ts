/**
 * The account password rules, mirrored from the backend so the wizard can say
 * no before a round trip.
 *
 * Authority lives in `boneio/core/auth/store.py`: every path that sets a
 * password goes through `validate_password` there, and this file only exists to
 * make the same answer arrive sooner. Keep the two in step — a rule that is
 * checked only here is not a rule.
 */

/** Mirrors `_MIN_PASSWORD_LEN`. */
export const MIN_PASSWORD_LENGTH = 8;

/** Mirrors `_MIN_USERNAME_IN_PASSWORD_LEN`. */
const MIN_USERNAME_IN_PASSWORD_LENGTH = 4;

/** Why a password cannot be used. */
export type PasswordProblem = 'too_short' | 'contains_username';

/**
 * Check a password against the account policy.
 *
 * @param password - The proposed password, untrimmed: spaces are part of it.
 * @param username - Account it is for. An empty name skips the similarity rule,
 *   the same way the backend does, so a half-typed form is not scolded.
 * @returns The problem, or null when the password is acceptable.
 */
export function checkPassword(password: string, username: string): PasswordProblem | null {
  if (!password || password.length < MIN_PASSWORD_LENGTH) {
    return 'too_short';
  }

  const name = username.trim().toLowerCase();
  if (!name) {
    return null;
  }

  const secret = password.toLowerCase();
  if (
    name === secret ||
    (name.length >= MIN_USERNAME_IN_PASSWORD_LENGTH && secret.includes(name))
  ) {
    return 'contains_username';
  }

  return null;
}

/**
 * Translation key for each problem, so every form that sets a password says
 * the same thing. Both messages are written to take a `min` parameter, which
 * only the length one uses.
 */
export const PASSWORD_PROBLEM_KEYS: Record<PasswordProblem, string> = {
  too_short: 'password_policy.too_short',
  contains_username: 'password_policy.contains_username',
};
