import { describe, it, expect } from 'vitest';
import { checkText, fixRoute, promptDecision } from '../securityPosture';
import type { SecurityPosture } from '../../hooks/useSecurityPosture';
import plCommon from '../../locales/pl/common.json';
import enCommon from '../../locales/en/common.json';

function posture(failed: number): SecurityPosture {
  return {
    checks: [],
    summary: {
      failed,
      critical: failed,
      warning: 0,
      info: 0,
      worst: failed ? 'critical' : null,
    },
  };
}

/** Stands in for the real `t`, which returns the key when there is no entry. */
function fakeT(entries: Record<string, string>) {
  return (key: string) => entries[key] ?? key;
}

describe('fixRoute', () => {
  it('sends a Settings section to the settings editor', () => {
    expect(fixRoute({ settings_section: 'accounts' })).toBe('/settings/accounts');
  });

  it('sends a system: target to the System page anchor', () => {
    expect(fixRoute({ settings_section: 'system:mqtt-passwords' })).toBe(
      '/system#mqtt-passwords',
    );
  });

  it('returns null when there is no control, so no dead button is offered', () => {
    expect(fixRoute({ settings_section: null })).toBeNull();
  });
});

describe('checkText', () => {
  it('prefers the panel translation', () => {
    const t = fakeT({ 'security.checks.mqtt_password.title': 'Hasło brokera MQTT' });
    expect(checkText(t, 'mqtt_password', 'title', 'MQTT broker password')).toBe(
      'Hasło brokera MQTT',
    );
  });

  it('falls back to the backend text for a check it has never heard of', () => {
    // A newer backend with an older bundle: the user must still read a
    // sentence, not `security.checks.new_thing.title`.
    const t = fakeT({});
    expect(checkText(t, 'new_thing', 'title', 'Something new')).toBe('Something new');
  });

  it('falls back when the translation is an empty string', () => {
    const t = fakeT({ 'security.checks.x.detail': '' });
    expect(checkText(t, 'x', 'detail', 'backend detail')).toBe('backend detail');
  });
});

describe('every shipped check is translated', () => {
  // The fallback exists for a backend that has moved ahead of the bundle, not
  // as licence to ship English strings into the Polish panel.
  const ids = [
    'admin_account',
    'anonymous_access',
    'mqtt_password',
    'legacy_web_auth',
    'certificate',
    'frame_ancestors',
    'dev_mode',
  ];

  for (const [lang, bundle] of [['pl', plCommon], ['en', enCommon]] as const) {
    it(`${lang} has title, detail, ok and remedy for each check`, () => {
      const checks = (bundle as any).security.checks;
      for (const id of ids) {
        expect(checks[id], `${lang}: ${id}`).toBeDefined();
        for (const field of ['title', 'detail', 'ok', 'remedy']) {
          expect(checks[id][field], `${lang}: ${id}.${field}`).toBeTruthy();
        }
      }
    });
  }
});

describe('promptDecision', () => {
  const base = {
    isAdmin: true,
    version: '1.6.0',
    seenVersion: '1.5.4',
    posture: posture(2),
    dismissed: false,
  };

  it('shows after an update when something is outstanding', () => {
    expect(promptDecision(base)).toEqual({ show: true, knownUpgrade: true });
  });

  it('stays away when nothing is outstanding', () => {
    // Interrupting to say everything is fine is how the next notice gets
    // dismissed unread.
    expect(promptDecision({ ...base, posture: posture(0) }).show).toBe(false);
  });

  it('does not come back for a version already prompted', () => {
    expect(promptDecision({ ...base, seenVersion: '1.6.0' }).show).toBe(false);
  });

  it('never shows to a read-only account', () => {
    expect(promptDecision({ ...base, isAdmin: false }).show).toBe(false);
  });

  it('stays away while the posture is still unknown', () => {
    expect(promptDecision({ ...base, posture: null }).show).toBe(false);
  });

  it('stays away once dismissed in this session', () => {
    expect(promptDecision({ ...base, dismissed: true }).show).toBe(false);
  });

  it('still shows on a browser that has never been here', () => {
    // The 1.5 device that has never opened this panel is the whole audience.
    const decision = promptDecision({ ...base, seenVersion: null });
    expect(decision.show).toBe(true);
    expect(decision.knownUpgrade).toBe(false);
  });

  it('does not claim an upgrade it cannot demonstrate', () => {
    expect(promptDecision({ ...base, seenVersion: null }).knownUpgrade).toBe(false);
    expect(promptDecision({ ...base, seenVersion: '1.5.4' }).knownUpgrade).toBe(true);
  });
});
