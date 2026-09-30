/**
 * What the SSH password card on the accounts page shows, from what
 * `GET /api/accounts/ssh-password` reports.
 *
 * The change is `passwd` done by the privileged helper: it wants the current
 * password, so the form is offered only where the boneio login has one. A
 * locked or empty login is the first-run wizard's to set, once, and after that
 * the flasher card's — never the panel's.
 */

/** How the boneio login stands, as boneio-system reports it. */
export type SshPasswordState = 'locked' | 'empty' | 'shipped' | 'set' | 'unknown' | null;

/** What the card renders. */
export type SshCardMode = 'form' | 'outdated' | 'locked' | 'empty' | 'unknown';

/**
 * Decide what the card shows.
 *
 * @param state - The login's state, or null when the helper could not be asked.
 * @param supported - Whether the installed helper can change it (migration 1.6.29).
 * @returns The mode.
 */
export function sshCardMode(state: SshPasswordState, supported: boolean): SshCardMode {
  if (state === 'locked' || state === 'empty') {
    return state;
  }
  if (state === 'set' || state === 'shipped') {
    return supported ? 'form' : 'outdated';
  }
  return 'unknown';
}

/** The Linux account the card is about; the password policy's similarity rule uses it. */
export const SSH_ACCOUNT = 'boneio';
