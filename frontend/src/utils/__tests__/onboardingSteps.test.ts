import { describe, it, expect } from 'vitest';
import {
  STEP_ORDER,
  stepsFor,
  previousStepFor,
  stepAfterImport,
  stepAfterDevices,
  stepAfterAccount,
  stepAfterBoard,
} from '../onboardingSteps';

/** Every device the wizard can open on: configured before × cloud already on. */
const DEVICES = [false, true].flatMap((configured) =>
  [false, true].map((cloud) => ({ configured, cloud })),
);

describe('stepsFor', () => {
  it('shows every step on a device being set up for the first time', () => {
    // The board step only when the card did not name the controller; see below.
    expect(stepsFor(false)).toEqual(STEP_ORDER.filter((s) => s !== 'board'));
  });

  it('drops import and devices on a device that already has a configuration', () => {
    // The devices step replaces the whole `event` section, so on an upgraded
    // controller it would delete input actions the owner configured. Import
    // is dropped for a gentler reason: offering it reads as "yours is gone".
    expect(stepsFor(true)).toEqual(['welcome', 'account', 'cloud', 'done']);
  });

  it('drops the cloud step when cloud registration is already on', () => {
    // A 1.5.x controller upgraded with cloud on is reached through its
    // boneio.app subdomain; asking to turn it on reads as if it were lost.
    expect(stepsFor(true, true)).toEqual(['welcome', 'account', 'done']);
    expect(stepsFor(false, true)).toEqual(['welcome', 'account', 'import', 'devices', 'done']);
  });

  it('never drops the account step — it is the only reason the wizard ran', () => {
    for (const { configured, cloud } of DEVICES) {
      expect(stepsFor(configured, cloud)).toContain('account');
      expect(stepsFor(configured, cloud)[0]).toBe('welcome');
      const shown = stepsFor(configured, cloud);
      expect(shown[shown.length - 1]).toBe('done');
    }
  });
});

describe('previousStepFor', () => {
  it('walks back through the steps a first-run device saw', () => {
    expect(previousStepFor('account', false)).toBe('welcome');
    expect(previousStepFor('devices', false)).toBe('import');
    expect(previousStepFor('cloud', false)).toBe('devices');
    expect(previousStepFor('done', false)).toBe('cloud');
  });

  it('returns to import from done when import skipped the steps between', () => {
    expect(previousStepFor('done', true)).toBe('import');
  });

  it('never returns to a step the device was not shown', () => {
    for (const { configured, cloud } of DEVICES) {
      const shown = stepsFor(configured, cloud);
      for (const step of shown) {
        const back = previousStepFor(step, false, configured, cloud);
        if (back !== undefined) {
          expect(shown).toContain(back);
        }
      }
    }
    expect(previousStepFor('account', false, true)).toBe('welcome');
    expect(previousStepFor('done', false, true)).toBe('cloud');
  });

  it('skips the cloud step on the way back when cloud was already on', () => {
    expect(previousStepFor('done', false, false, true)).toBe('devices');
    expect(previousStepFor('done', true, false, true)).toBe('import');
    // Upgraded with cloud on: done comes straight after account, and nothing
    // leads back there.
    expect(previousStepFor('done', false, true, true)).toBeUndefined();
  });

  it('never leads back to the account step once it has been left', () => {
    // The account exists by then; going back offered to create it again.
    for (const { configured, cloud } of DEVICES) {
      for (const importRestored of [true, false]) {
        for (const step of stepsFor(configured, cloud)) {
          if (step === 'account' || step === 'welcome') continue;
          expect(previousStepFor(step, importRestored, configured, cloud)).not.toBe('account');
        }
      }
    }
  });

  it('has no predecessor for the first screen', () => {
    expect(previousStepFor('welcome', false)).toBeUndefined();
    expect(previousStepFor('welcome', false, true)).toBeUndefined();
  });
});

describe('stepAfterImport', () => {
  it('goes to devices when nothing was restored', () => {
    expect(stepAfterImport(false)).toBe('devices');
  });

  it('skips to done when a configuration was restored', () => {
    expect(stepAfterImport(true)).toBe('done');
  });
});

describe('stepAfterDevices', () => {
  it('goes to cloud while cloud is off', () => {
    expect(stepAfterDevices(false)).toBe('cloud');
  });

  it('goes to done when cloud is already on', () => {
    expect(stepAfterDevices(true)).toBe('done');
  });
});

describe('stepAfterAccount', () => {
  it('goes to import on a first-run device', () => {
    expect(stepAfterAccount(false)).toBe('import');
  });

  it('goes to cloud, not past it, on an upgraded device', () => {
    expect(stepAfterAccount(true)).toBe('cloud');
    expect(stepsFor(true)).toContain(stepAfterAccount(true));
  });

  it('goes to done on an upgraded device whose cloud is already on', () => {
    expect(stepAfterAccount(true, true)).toBe('done');
  });

  it('always lands on a step the device is shown', () => {
    for (const { configured, cloud } of DEVICES) {
      expect(stepsFor(configured, cloud)).toContain(stepAfterAccount(configured, cloud));
    }
  });
});

describe('the board step', () => {
  it('is shown only when the card did not say which controller this is', () => {
    expect(stepsFor(false)).not.toContain('board');
    expect(stepsFor(false, false, true)).toEqual(
      ['welcome', 'account', 'board', 'import', 'devices', 'cloud', 'done'],
    );
  });

  it('comes straight after the account and leads on to import', () => {
    expect(stepAfterAccount(false, false, true)).toBe('board');
    expect(stepAfterBoard(false)).toBe('import');
    expect(stepAfterBoard(true, true)).toBe('done');
  });

  it('is never walked back to: the type is set once it is left', () => {
    expect(previousStepFor('import', false, false, false, true)).toBeUndefined();
    expect(previousStepFor('board', false, false, false, true)).toBeUndefined();
  });
});
