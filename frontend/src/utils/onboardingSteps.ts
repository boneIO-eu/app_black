/**
 * Which first-run steps a given device should see, and how to walk back.
 *
 * Kept out of the component so the decision can be tested: it is the
 * difference between a wizard that sets a controller up and one that undoes
 * the configuration it already had.
 */

export type Step = 'welcome' | 'account' | 'import' | 'devices' | 'cloud' | 'done';

export const STEP_ORDER: Step[] = [
  'welcome', 'account', 'import', 'devices', 'cloud', 'done',
];

/**
 * The steps to show on this device.
 *
 * An upgraded controller already has a configuration and input actions of its
 * own. Offering to import a configuration there reads as "yours is gone", and
 * the devices step does not merely read oddly — POST /api/config/input-bindings
 * replaces the whole `event` section, so a controller with fifty configured
 * inputs would lose them to a wizard its owner only opened to create an
 * account.
 *
 * @param configuredBefore - Whether this device was set up under an earlier
 *   release, reported by /api/onboarding/status.
 */
export function stepsFor(configuredBefore: boolean): Step[] {
  if (!configuredBefore) return STEP_ORDER;
  return STEP_ORDER.filter((s) => s !== 'import' && s !== 'devices');
}

/**
 * Which step the back button returns to.
 *
 * @param step - The step being shown.
 * @param importRestored - Whether the import step actually restored a config.
 *   When it did, `devices` and `cloud` are skipped on the way forward, so
 *   going back from `done` has to return to `import` rather than to a step the
 *   user never saw.
 * @param configuredBefore - Whether the device was already configured.
 */
export function previousStepFor(
  step: Step,
  importRestored: boolean,
  configuredBefore = false,
): Step | undefined {
  if (configuredBefore) {
    // welcome → account → cloud → done. Nothing leads back to the account
    // step: the account exists once it is left, and going back there offered
    // to create it a second time, which the server refuses.
    if (step === 'account') return 'welcome';
    if (step === 'done') return 'cloud';
    return undefined;
  }
  const map: Partial<Record<Step, Step>> = {
    account: 'welcome',
    devices: 'import',
    cloud: 'devices',
    done: importRestored ? 'import' : 'cloud',
  };
  return map[step];
}

/**
 * Where the import step goes next.
 *
 * A restored configuration already decides both of the things the next two
 * steps would set: the devices step replaces every input action, and the cloud
 * step writes back a `web` section that came from the other device (restore
 * unpacks config.yaml too, so `web.cloud` is the old device's). Neither is ours
 * to overwrite, so both are skipped.
 *
 * @param importRestored - Whether a configuration was actually restored.
 */
export function stepAfterImport(importRestored: boolean): Step {
  return importRestored ? 'done' : 'devices';
}

/**
 * Where the account step goes once the account exists.
 *
 * An upgraded device skips import and devices (see {@link stepsFor}) but
 * still has the cloud step: it only turns web.cloud on in the device's own
 * web section, which is as much the owner's choice on an upgraded controller
 * as on a new one. It used to jump straight to done, past a step the progress
 * bar was showing.
 *
 * @param configuredBefore - Whether the device was already configured.
 */
export function stepAfterAccount(configuredBefore: boolean): Step {
  return configuredBefore ? 'cloud' : 'import';
}
