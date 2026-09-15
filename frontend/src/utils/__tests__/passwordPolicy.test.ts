import { describe, it, expect } from 'vitest';
import { MIN_PASSWORD_LENGTH, checkPassword } from '../passwordPolicy';

describe('checkPassword', () => {
  it('rejects a password below the shared minimum', () => {
    expect(checkPassword('short', 'boneio')).toBe('too_short');
    expect(checkPassword('a'.repeat(MIN_PASSWORD_LENGTH - 1), 'boneio')).toBe('too_short');
    expect(checkPassword('', 'boneio')).toBe('too_short');
  });

  it('rejects a password that is the username', () => {
    expect(checkPassword('boneioAAA', 'boneioAAA')).toBe('contains_username');
    expect(checkPassword('BONEIOaaa', 'boneioAAA')).toBe('contains_username');
  });

  it('rejects a password the username is buried in', () => {
    expect(checkPassword('boneio1234', 'boneio')).toBe('contains_username');
    expect(checkPassword('xx-boneio-xx', 'boneio')).toBe('contains_username');
  });

  it('matches the backend on a padded username', () => {
    // normalize_username trims, so the policy has to compare the same form.
    expect(checkPassword('boneio-panel', '  boneio  ')).toBe('contains_username');
  });

  it('leaves the similarity rule out when no username is known yet', () => {
    // The wizard calls this on every keystroke, including before the name is
    // typed; complaining then would be noise.
    expect(checkPassword('boneioAAA', '')).toBeNull();
    expect(checkPassword('boneioAAA', '   ')).toBeNull();
  });

  it('does not ban a username too short to matter', () => {
    expect(checkPassword('abstract-cat', 'ab')).toBeNull();
  });

  it('accepts a password that merely shares a prefix', () => {
    expect(checkPassword('bone-shaker-42', 'boneio')).toBeNull();
    expect(checkPassword('correct horse battery', 'pawel')).toBeNull();
  });

  it('reports length before similarity, like the backend', () => {
    expect(checkPassword('bone', 'boneio')).toBe('too_short');
  });
});
