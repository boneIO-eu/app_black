import { describe, it, expect } from 'vitest';
import {
  STEP_ORDER,
  stepsFor,
  previousStepFor,
  stepAfterImport,
} from '../onboardingSteps';

describe('stepsFor', () => {
  it('shows every step on a device being set up for the first time', () => {
    expect(stepsFor(false)).toEqual(STEP_ORDER);
  });

  it('drops import and devices on a device that already has a configuration', () => {
    // The devices step replaces the whole `event` section, so on an upgraded
    // controller it would delete input actions the owner configured. Import
    // is dropped for a gentler reason: offering it reads as "yours is gone".
    expect(stepsFor(true)).toEqual(['welcome', 'account', 'cloud', 'done']);
  });

  it('never drops the account step — it is the only reason the wizard ran', () => {
    for (const configured of [true, false]) {
      expect(stepsFor(configured)).toContain('account');
      expect(stepsFor(configured)[0]).toBe('welcome');
    }
  });
});

describe('previousStepFor', () => {
  it('walks back through the steps a first-run device saw', () => {
    expect(previousStepFor('account', false)).toBe('welcome');
    expect(previousStepFor('devices', false)).toBe('import');
    expect(previousStepFor('cloud', false)).toBe('cloud' === 'cloud' ? 'devices' : undefined);
    expect(previousStepFor('done', false)).toBe('cloud');
  });

  it('returns to import from done when import skipped the steps between', () => {
    expect(previousStepFor('done', true)).toBe('import');
  });

  it('never returns to a step an upgraded device was not shown', () => {
    const shown = stepsFor(true);
    for (const step of shown) {
      const back = previousStepFor(step, false, true);
      if (back !== undefined) {
        expect(shown).toContain(back);
      }
    }
    expect(previousStepFor('account', false, true)).toBe('welcome');
    expect(previousStepFor('done', false, true)).toBe('account');
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
