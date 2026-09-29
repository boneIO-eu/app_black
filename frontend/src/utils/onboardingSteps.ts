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
 * The cloud step goes when cloud registration is already on. A controller
 * upgraded from 1.5.x with it enabled is usually being reached through its
 * boneio.app subdomain at that very moment, and a wizard asking whether to
 * turn on what is serving the page it is shown on reads as if the setting had
 * been lost in the upgrade.
 *
 * @param configuredBefore - Whether this device was set up under an earlier
 *   release, reported by /api/init.
 * @param cloudEnabled - Whether web.cloud is already enabled, the `cloud`
 *   section of /api/init.
 */
export function stepsFor(configuredBefore: boolean, cloudEnabled = false): Step[] {
  return STEP_ORDER.filter((s) => {
    if (configuredBefore && (s === 'import' || s === 'devices')) return false;
    if (cloudEnabled && s === 'cloud') return false;
    return true;
  });
}

/**
 * Which step the back button returns to.
 *
 * The step before this one on the way the user actually came, with one rule
 * on top: nothing leads back to the account step. The account exists once it
 * is left, and going back there offered to create it a second time, which the
 * server refuses — so the step right after it has no back button at all.
 *
 * @param step - The step being shown.
 * @param importRestored - Whether the import step actually restored a config.
 *   When it did, `devices` and `cloud` are skipped on the way forward, so
 *   going back from `done` has to return to `import` rather than to a step the
 *   user never saw.
 * @param configuredBefore - Whether the device was already configured.
 * @param cloudEnabled - Whether cloud registration was already on.
 */
export function previousStepFor(
  step: Step,
  importRestored: boolean,
  configuredBefore = false,
  cloudEnabled = false,
): Step | undefined {
  const walked = stepsFor(configuredBefore, cloudEnabled).filter(
    (s) => !(importRestored && (s === 'devices' || s === 'cloud')),
  );
  const index = walked.indexOf(step);
  if (index <= 0) return undefined;
  const previous = walked[index - 1];
  return previous === 'account' ? undefined : previous;
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
 * Where the devices step goes next: cloud, unless it is already on.
 *
 * @param cloudEnabled - Whether cloud registration was already on.
 */
export function stepAfterDevices(cloudEnabled = false): Step {
  return cloudEnabled ? 'done' : 'cloud';
}

/**
 * Where the account step goes once the account exists.
 *
 * An upgraded device skips import and devices (see {@link stepsFor}) but
 * still has the cloud step when cloud is off: it only turns web.cloud on in
 * the device's own web section, which is as much the owner's choice on an
 * upgraded controller as on a new one. It used to jump straight to done, past
 * a step the progress bar was showing.
 *
 * @param configuredBefore - Whether the device was already configured.
 * @param cloudEnabled - Whether cloud registration was already on.
 */
export function stepAfterAccount(configuredBefore: boolean, cloudEnabled = false): Step {
  const steps = stepsFor(configuredBefore, cloudEnabled);
  return steps[steps.indexOf('account') + 1] ?? 'done';
}
