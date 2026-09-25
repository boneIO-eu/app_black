import { describe, it, expect } from 'vitest';
import { checkText, fixRoute, promptDecision } from '../securityPosture';
import type { SecurityPosture } from '../../hooks/useSecurityPosture';
import plCommon from '../../locales/pl/common.json';
import enCommon from '../../locales/en/common.json';

/** A posture with `failed` actionable critical findings and no advice. */
function posture(failed: number): SecurityPosture {
  return {
    checks: [],
    summary: {
      failed,
      actionable: failed,
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
      const checks = (bundle as { security: { checks: Record<string, Record<string, string>> } }).security.checks;
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

  describe('a snooze', () => {
    const NOW = 1_700_000_000_000;

    it('hides the prompt while it has not run out', () => {
      const decision = promptDecision({ ...base, snoozedUntil: NOW + 1000, now: NOW });
      expect(decision.show).toBe(false);
    });

    it('lets it back once it has', () => {
      // The gap is still there tomorrow, and so is the notice — this is what
      // separates "remind me tomorrow" from the button that means never.
      expect(promptDecision({ ...base, snoozedUntil: NOW - 1000, now: NOW }).show).toBe(true);
    });

    it('is ignored when the stored value is not a number', () => {
      // Storage can come back with anything. Hiding the prompt forever on
      // unreadable input is the one failure worth avoiding here; showing it
      // once more than asked is not.
      for (const broken of [NaN, Infinity, null, undefined]) {
        const decision = promptDecision({
          ...base,
          snoozedUntil: broken as unknown as number | null,
          now: NOW,
        });
        expect(decision.show).toBe(true);
      }
    });

    it('does not override an outstanding count of zero', () => {
      // A device with nothing to fix stays quiet whether or not it was snoozed.
      const decision = promptDecision({
        ...base,
        posture: posture(0),
        snoozedUntil: NOW - 1000,
        now: NOW,
      });
      expect(decision.show).toBe(false);
    });
  });

  it('ignores advice that applies to every device', () => {
    // Self-signed certificate and unset frame_ancestors are INFO: reported in
    // the panel, never a reason to interrupt.
    const adviceOnly: SecurityPosture = {
      checks: [],
      summary: { failed: 2, actionable: 0, critical: 0, warning: 0, info: 2, worst: 'info' },
    };
    expect(promptDecision({ ...base, posture: adviceOnly }).show).toBe(false);
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

describe('fixRoute and the page it is on', () => {
  it('offers no button when the fix is on this very page', () => {
    // frame_ancestors is fixed by the card in the Security section itself; a
    // button that navigates nowhere teaches people the buttons do nothing.
    expect(fixRoute({ settings_section: 'security' }, '/settings/security')).toBeNull();
  });

  it('still offers a button for anywhere else', () => {
    expect(fixRoute({ settings_section: 'accounts' }, '/settings/security')).toBe(
      '/settings/accounts',
    );
    expect(fixRoute({ settings_section: 'system:mqtt-passwords' }, '/settings/security')).toBe(
      '/system#mqtt-passwords',
    );
  });
});

describe('the framing card is translated', () => {
  const keys = [
    'title',
    'intro',
    'restrict',
    'restrict_help',
    'extra_origin',
    'extra_origin_help',
    'save',
    'saving',
    'restart_needed',
    'load_failed',
    'save_failed',
    'add_origin',
    'remove_origin',
  ];

  for (const [lang, bundle] of [['pl', plCommon], ['en', enCommon]] as const) {
    it(`${lang} has every framing string`, () => {
      const framing = (bundle as { security: { framing?: Record<string, string> } }).security.framing;
      for (const key of keys) {
        expect(framing?.[key], `${lang}: framing.${key}`).toBeTruthy();
      }
    });
  }
});

describe('the prompt and the section agree on wording', () => {
  it('both translate a check by id rather than showing the backend English', () => {
    // The prompt used to render check.title directly, so it read half in one
    // language and half in the other on a Polish panel.
    const t = fakeT({ 'security.checks.mqtt_password.title': 'Hasło brokera MQTT' });
    expect(checkText(t, 'mqtt_password', 'title', 'MQTT broker password')).toBe(
      'Hasło brokera MQTT',
    );
  });
});

describe('promptDecision during the first-run wizard', () => {
  const base = {
    isAdmin: true,
    version: '1.6.0',
    seenVersion: '1.5.2',
    posture: {
      checks: [],
      summary: { failed: 1, actionable: 1, critical: 0, warning: 1, info: 0, worst: 'warning' },
    },
    dismissed: false,
  } as Parameters<typeof promptDecision>[0];

  it('stays out of the way while the wizard is on screen', () => {
    // The wizard adopts a token as soon as it creates the account, so from its
    // second step an administrator is signed in and this used to open over a
    // wizard the user was halfway through.
    expect(promptDecision({ ...base, onboarding: true }).show).toBe(false);
  });

  it('appears once the wizard is done', () => {
    expect(promptDecision({ ...base, onboarding: false }).show).toBe(true);
  });

  it('treats an absent flag as "no wizard"', () => {
    expect(promptDecision(base).show).toBe(true);
  });
});
