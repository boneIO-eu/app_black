import { useState, useEffect, FormEvent, useRef } from 'react';
import { FaEye, FaEyeSlash } from 'react-icons/fa';
import type { AxiosError } from 'axios';
import axios from '@/api/axios';
import { useAuth } from '../hooks/useAuth';
import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '../hooks/useTranslation';
import { type Step, stepsFor, previousStepFor, stepAfterImport } from '@/utils/onboardingSteps';
import { checkImportFile, interpretRestoreResponse } from '@/utils/onboardingImport';
import {
  MIN_PASSWORD_LENGTH,
  PASSWORD_PROBLEM_KEYS,
  checkPassword,
} from '@/utils/passwordPolicy';
import ThemeChanger from './ThemeChanger';
import LanguageSelector from './LanguageSelector';
import Logo from './Logo';

/** Shape of the error bodies the onboarding and restore routes return. */
type ApiError = AxiosError<{ detail?: string }>;

/**
 * Pull the backend's message out of a failed request.
 *
 * @param err - Whatever the request rejected with.
 * @param fallback - Message to use when the response carries none.
 */
function errorMessage(err: unknown, fallback: string): string {
  return (err as ApiError)?.response?.data?.detail || fallback;
}

/** Mirrors INPUT_MODES in boneio/core/config/input_bindings.py. */
type InputMode = 'covers_and_outputs' | 'covers' | 'outputs' | 'none';

/** What GET /api/config/input-bindings/targets reports about this board. */
interface BindingTargets {
  device_type: string | null;
  free_inputs: number;
  outputs: number;
  covers: number;
  available_modes: InputMode[];
}

/**
 * First-run wizard.
 *
 * Shown instead of the normal UI while the device has no administrator, which
 * the backend reports as `needs_onboarding` in /api/init. The account step is
 * the only one that cannot be skipped: until it completes, the device has no
 * owner and POST /api/onboarding/admin is open to whoever reaches it first.
 */
export default function OnboardingWizard() {
  const { t } = useTranslation();
  const { loginWithToken } = useAuth();
  const { data: initData } = useAppInit();

  const [step, setStep] = useState<Step>('welcome');
  // Which way the last move went, so a step slides in from the side it came
  // from. Purely cosmetic, but going back and having the panel arrive from the
  // right feels wrong in a way people notice without being able to name it.
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  // Set once the confirmation field has been edited, so the mismatch hint does
  // not accuse the user of a typo before they have finished typing.
  const [confirmTouched, setConfirmTouched] = useState(false);

  const [importFile, setImportFile] = useState<File | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importDone, setImportDone] = useState(false);
  const [importWarning, setImportWarning] = useState<string | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  const [targets, setTargets] = useState<BindingTargets | null>(null);
  const [targetsError, setTargetsError] = useState<string | null>(null);
  const [restoreState, setRestoreState] = useState(true);
  const [inputMode, setInputMode] = useState<InputMode | null>(null);
  const [devicesError, setDevicesError] = useState<string | null>(null);
  const [devicesDone, setDevicesDone] = useState(false);
  const [isApplyingDevices, setIsApplyingDevices] = useState(false);

  /**
   * What happened to the SSH login when the account was created.
   *
   * The image ships that login locked, and the owner's first password becomes
   * it — once, and only while nobody has chosen one. The done step says which
   * of those it was, because "your SSH password is now X" is not something to
   * leave anybody guessing about.
   */
  const [sshOutcome, setSshOutcome] = useState<string | null>(null);
  const [cloudError, setCloudError] = useState<string | null>(null);
  const [cloudDone, setCloudDone] = useState<'live' | 'deferred' | false>(false);
  const [isEnablingCloud, setIsEnablingCloud] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeStepRef = useRef<HTMLLIElement>(null);

  const configuredBefore = initData?.configured_before ?? false;
  const steps = stepsFor(configuredBefore);
  const stepIndex = steps.indexOf(step);

  // Shown under the password field once there is something to judge. The
  // backend enforces the same rules, so this only saves a round trip — and
  // saves the user from learning about the username rule after submitting.
  const passwordIssue = password ? checkPassword(password, username) : null;

  const passwordProblem = (): string | null => {
    if (passwordIssue) {
      return t(PASSWORD_PROBLEM_KEYS[passwordIssue], { min: MIN_PASSWORD_LENGTH });
    }
    if (password !== confirmPassword) {
      return t('onboarding.error_password_mismatch');
    }
    return null;
  };

  // The length rule already has its own permanent hint under the field, so
  // only the username rule needs announcing while typing.
  const usernameInPassword =
    passwordIssue === 'contains_username'
      ? t(PASSWORD_PROBLEM_KEYS.contains_username)
      : null;

  // Shown under the confirmation field while typing.
  const confirmProblem =
    confirmTouched && confirmPassword && password !== confirmPassword
      ? t('onboarding.error_password_mismatch')
      : null;

  const accountIncomplete = !username || !password || !confirmPassword;

  // Keep the current step on screen when the row is too wide to fit.
  // `nearest` so a step that is already visible does not jump.
  useEffect(() => {
    activeStepRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [step]);

  const previousStep = previousStepFor(step, importDone, configuredBefore);

  // On a phone the step's primary buttons already fill the row, so the back
  // button drops onto its own line underneath rather than squeezing them into
  // two-line labels. `order-last` keeps it below, where it reads as secondary.
  const backButtonClass = 'btn btn-outline basis-full order-last sm:basis-auto sm:order-first';

  const goTo = (next: Step) => {
    setDirection(steps.indexOf(next) < stepIndex ? 'back' : 'forward');
    setStep(next);
  };

  const goBack = () => {
    if (previousStep) {
      goTo(previousStep);
    }
  };

  // Each step is a separate conditional block, so switching steps is a real
  // unmount and mount and the enter animation replays without needing a key.
  const stepEnter = [
    'animate-in fade-in duration-300 ease-out',
    direction === 'forward' ? 'slide-in-from-right-6' : 'slide-in-from-left-6',
  ].join(' ');

  const handleCreateAccount = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    const problem = passwordProblem();
    if (problem) {
      setError(problem);
      return;
    }

    setIsSubmitting(true);
    try {
      // Not the default 5 s. On a BeagleBone this is a scrypt hash plus two
      // runs of the Python system helper (the SSH password's state, then
      // chpasswd) — past 5 s easily on a first boot that is also pulling
      // containers. The panel then said "could not create the account" while
      // the server went on and created it, and the retry met "already set up".
      const response = await axios.post(
        '/api/onboarding/admin',
        { username, password },
        { timeout: 60_000 },
      );
      // The device is now ours; adopt the token before anything else so the
      // remaining steps run authenticated rather than through the open window.
      loginWithToken(response.data.token);
      setSshOutcome(typeof response.data.ssh === 'string' ? response.data.ssh : null);
      // Deliberately NOT refetching /api/init here. The gate in App.tsx keys
      // the wizard off needs_onboarding, so refreshing it the moment the
      // account exists unmounts this component mid-flow and the import and
      // summary steps become unreachable. finish() reloads the page, which
      // refetches everything anyway.
      // Only cleared on success: a recoverable error (a rejected username,
      // say) should not cost the user both passwords as well.
      setPassword('');
      setConfirmPassword('');
      // On an upgraded device there is nothing to import and nothing to wire:
      // the account was the only thing missing.
      goTo(configuredBefore ? 'done' : 'import');
    } catch (err: unknown) {
      if ((err as ApiError)?.response?.status === 409) {
        // Somebody else finished the wizard between page load and submit.
        setError(t('onboarding.error_already_provisioned'));
      } else {
        setError(errorMessage(err, t('onboarding.error_create_failed')));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSelectImportFile = (file: File | null) => {
    setImportError(null);
    setImportWarning(null);
    setImportDone(false);

    if (!file) {
      setImportFile(null);
      return;
    }

    const rejection = checkImportFile(file);
    if (rejection) {
      setImportError(
        rejection.reason === 'invalid_type'
          ? t('onboarding.import_invalid_type')
          : t('onboarding.import_too_large', { max: rejection.maxMegabytes }),
      );
      setImportFile(null);
      // Clear the input too: picking the very same file again fires no change
      // event, so without this the user is stuck staring at their rejection.
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    setImportFile(file);
  };

  const handleImport = async () => {
    if (!importFile) return;
    setImportError(null);
    setImportWarning(null);
    setIsImporting(true);

    const form = new FormData();
    form.append('file', importFile);

    try {
      const { data } = await axios.post('/api/config/restore', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      // Failure arrives as HTTP 200 with a status field, so axios never
      // rejects on a bad archive — the body is the only signal there is.
      const outcome = interpretRestoreResponse(data);

      if (outcome.status === 'error') {
        setImportError(outcome.message || t('onboarding.import_failed'));
        return;
      }
      if (outcome.status === 'empty') {
        setImportError(t('onboarding.import_empty'));
        return;
      }
      if (outcome.status === 'warning') {
        setImportWarning(outcome.message || t('onboarding.import_invalid_config'));
      }

      setImportDone(true);
    } catch (err: unknown) {
      setImportError(errorMessage(err, t('onboarding.import_failed')));
    } finally {
      setIsImporting(false);
    }
  };

  // Read on entering the step rather than up front: the import step may have
  // just replaced the whole configuration, so asking earlier would describe a
  // board layout that no longer applies.
  useEffect(() => {
    if (step !== 'devices' || targets) return;

    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get('/api/config/input-bindings/targets');
        if (cancelled) return;
        setTargets(data);
        // Preselect the most complete option the board can actually do.
        setInputMode(data.available_modes?.[0] ?? 'none');
      } catch (err: unknown) {
        if (!cancelled) {
          setTargetsError(errorMessage(err, t('onboarding.devices_targets_failed')));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [step, targets, t]);

  const handleApplyDevices = async () => {
    if (!inputMode) return;
    setDevicesError(null);
    setIsApplyingDevices(true);
    try {
      await axios.post('/api/config/input-bindings', {
        mode: inputMode,
        restore_state: restoreState,
      });
      setDevicesDone(true);
    } catch (err: unknown) {
      setDevicesError(errorMessage(err, t('onboarding.devices_failed')));
    } finally {
      setIsApplyingDevices(false);
    }
  };

  const handleEnableCloud = async () => {
    setCloudError(null);
    setIsEnablingCloud(true);
    try {
      // PUT replaces the whole section, so merge rather than overwrite — the
      // port and proxy port set moments ago live in here too.
      const { data: config } = await axios.get('/api/config');
      const web = (config?.web ?? {}) as Record<string, unknown>;
      const cloud = (web.cloud ?? {}) as Record<string, unknown>;
      const { data: saved } = await axios.put('/api/config/web', {
        ...web,
        cloud: { ...cloud, enabled: true },
      });
      // The backend starts registration where the change is made. It reports
      // "unavailable" when it could not — no address yet, most likely — and
      // then the next boot is what picks it up, which is worth saying rather
      // than leaving somebody waiting for a certificate.
      setCloudDone(saved?.cloud === 'unavailable' ? 'deferred' : 'live');
    } catch (err: unknown) {
      setCloudError(errorMessage(err, t('onboarding.cloud_failed')));
    } finally {
      setIsEnablingCloud(false);
    }
  };

  const finish = () => {
    // A restored config is only live after a restart, and the rest of the app
    // caches config aggressively, so start from a clean load either way.
    window.location.reload();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-100 p-3 sm:p-4">
      <div className="max-w-xl w-full space-y-6 p-6 sm:p-8 bg-base-100 rounded-lg shadow-lg animate-in fade-in zoom-in-95 duration-500 ease-out">
        {/* The wizard is the first screen a new owner sees, so the language and
            theme pickers have to live here — the header that normally carries
            them only exists once onboarding is done. */}
        <div className="flex justify-end items-center gap-1 -mb-4">
          <ThemeChanger />
          <LanguageSelector />
        </div>

        <div className="flex flex-col items-center">
          {/* Slightly behind the card, so the mark settles into a frame that is
              already there rather than racing it. */}
          <div className="w-28 animate-in fade-in slide-in-from-top-2 duration-700 delay-150 fill-mode-backwards">
            <Logo />
          </div>
          {/* Brand name, not copy — deliberately not translated. */}
          <span className="mt-1 text-xs font-semibold tracking-[0.35em] uppercase opacity-60">
            Black
          </span>
          <h1 className="mt-4 text-center text-2xl font-extrabold">
            {t('onboarding.title')}
          </h1>
        </div>

        {/* Six labelled steps want ~360px and a 375px phone leaves 295px
            inside the card, so the labels are dropped there and the current
            one is spelled out underneath instead. Numbers alone still show
            how far along the wizard is, and nothing gets clipped. */}
        <div className="overflow-x-auto no-scrollbar -mx-1 px-1">
          <ul className="steps wizard-steps text-xs w-full">
            {steps.map((name, index) => (
              <li
                key={name}
                ref={index === stepIndex ? activeStepRef : undefined}
                className={`step ${index <= stepIndex ? 'step-primary' : ''}`}
              >
                <span className="hidden sm:inline">{t(`onboarding.step_${name}`)}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="sm:hidden text-center text-xs opacity-70 -mt-3">
          {t('onboarding.step_counter', {
            current: stepIndex + 1,
            total: steps.length,
          })}{' '}
          · {t(`onboarding.step_${step}`)}
        </div>

        {/* Reserve the tallest step's height so the card does not resize from
            step to step. Measured across both languages at 375px and at the
            576px the card maxes out at; the worst case is the devices step on
            a cover_mix board in Polish, where every mode is on offer at once
            (481px on a phone, 375px on a desktop). Both values leave a little
            room for an inline error growing a step by a line.
            A floor, not a cap: a step that somehow runs taller still grows.
            Re-measure when a step gains content — the reserved area's own
            height is what keeps the card still. */}
        <div className="min-h-[32rem] sm:min-h-[24rem] flex">
        {step === 'welcome' && (
          <div className={`space-y-4 flex-1 flex flex-col ${stepEnter}`}>
            <p className="text-sm opacity-80">
              {/* An upgraded device keeps its configuration; saying otherwise
                  reads as though the update threw it away. */}
              {t(configuredBefore ? 'onboarding.welcome_intro_upgraded' : 'onboarding.welcome_intro')}
            </p>

            <div className="alert alert-warning text-sm">
              <span>{t('onboarding.welcome_why')}</span>
            </div>

            {/* Pinned as a pair, and pinned on the wrapper rather than on the
                caption: /api/init can be slow or absent, and the button must
                not drift up the card just because the version line is late. */}
            <div className="mt-auto space-y-4">
              {initData && (
                <div className="text-xs opacity-60 text-center">
                  {initData.name} · v{initData.version}
                </div>
              )}

              <button className="btn btn-primary w-full" onClick={() => goTo('account')}>
                {t('onboarding.start')}
              </button>
            </div>
          </div>
        )}

        {step === 'account' && (
          <form className={`space-y-4 flex-1 flex flex-col ${stepEnter}`} onSubmit={handleCreateAccount}>
            <p className="text-sm opacity-80">{t('onboarding.account_intro')}</p>

            <div className="w-full">
              <label htmlFor="onboarding-username" className="block text-sm mb-1">
                {t('onboarding.username')}
              </label>
              <input
                id="onboarding-username"
                type="text"
                className="input w-full"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="w-full">
              <label htmlFor="onboarding-password" className="block text-sm mb-1">
                {t('onboarding.password')}
              </label>
              <div className="relative">
                <input
                  id="onboarding-password"
                  type={showPassword ? 'text' : 'password'}
                  className={`input w-full pr-12 ${usernameInPassword ? 'input-error' : ''}`}
                  autoComplete="new-password"
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  aria-invalid={usernameInPassword ? true : undefined}
                  aria-describedby={usernameInPassword ? 'onboarding-password-error' : undefined}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                {/* One toggle for both fields: they must end up identical, so
                    revealing them separately would only hide the mismatch. */}
                <button
                  type="button"
                  className="btn btn-ghost btn-sm absolute right-1 top-1/2 -translate-y-1/2"
                  aria-label={
                    showPassword ? t('onboarding.hide_password') : t('onboarding.show_password')
                  }
                  aria-pressed={showPassword}
                  // Out of the tab order on purpose: Tab goes from the password
                  // straight to its confirmation, which is what somebody typing
                  // a password they just invented is about to do. The button is
                  // still clickable and still announced, since aria-label and
                  // aria-pressed do not depend on tab order.
                  tabIndex={-1}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <FaEyeSlash className="w-4 h-4" /> : <FaEye className="w-4 h-4" />}
                </button>
              </div>
              {usernameInPassword ? (
                <p id="onboarding-password-error" className="text-error text-xs mt-1">
                  {usernameInPassword}
                </p>
              ) : (
                <p className="text-xs opacity-60 mt-1">
                  {t('onboarding.password_hint', { min: MIN_PASSWORD_LENGTH })}
                </p>
              )}
            </div>

            <div className="w-full">
              <label htmlFor="onboarding-confirm" className="block text-sm mb-1">
                {t('onboarding.confirm_password')}
              </label>
              <input
                id="onboarding-confirm"
                type={showPassword ? 'text' : 'password'}
                className={`input w-full ${confirmProblem ? 'input-error' : ''}`}
                autoComplete="new-password"
                required
                aria-invalid={confirmProblem ? true : undefined}
                aria-describedby={confirmProblem ? 'onboarding-confirm-error' : undefined}
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  setConfirmTouched(true);
                }}
              />
              {confirmProblem && (
                <p id="onboarding-confirm-error" className="text-error text-xs mt-1">
                  {confirmProblem}
                </p>
              )}
            </div>

            {/* Said before the password is sent, not after. It becomes the
                root-capable SSH login as well, and somebody choosing a
                password deserves to know what it will open. */}
            <div className="alert alert-info text-xs">
              <span>{t('onboarding.ssh_password_notice')}</span>
            </div>

            {error && <div className="text-error text-sm text-center">{error}</div>}

            <div className="flex flex-wrap gap-2 mt-auto">
              {previousStep && (
                <button type="button" className={backButtonClass} onClick={goBack}>
                  {t('onboarding.back')}
                </button>
              )}
              <button
                type="submit"
                className="btn btn-primary flex-1"
                disabled={
                  isSubmitting || accountIncomplete || !!confirmProblem || !!usernameInPassword
                }
              >
                {isSubmitting && <span className="loading loading-spinner loading-sm" />}
                {t('onboarding.create_account')}
              </button>
            </div>
          </form>
        )}

        {step === 'import' && (
          <div className={`space-y-4 flex-1 flex flex-col ${stepEnter}`}>
            <p className="text-sm opacity-80">{t('onboarding.import_intro')}</p>

            <input
              ref={fileInputRef}
              type="file"
              accept=".tar.gz,.tgz,application/gzip"
              className="file-input file-input-bordered w-full"
              onChange={(e) => handleSelectImportFile(e.target.files?.[0] ?? null)}
            />

            {importError && <div className="text-error text-sm">{importError}</div>}

            {importDone && (
              <div className="alert alert-success text-sm animate-in fade-in zoom-in-95 duration-200">
                <span>{t('onboarding.import_done')}</span>
              </div>
            )}

            {importWarning && (
              <div className="alert alert-warning text-sm animate-in fade-in zoom-in-95 duration-200">
                <span>{importWarning}</span>
              </div>
            )}

            {/* Say it here rather than letting "Next" quietly jump two steps. */}
            {importDone && (
              <p className="text-xs opacity-70">{t('onboarding.import_skips_rest')}</p>
            )}

            <div className="flex gap-2 mt-auto">
              <button
                className="btn btn-primary flex-1"
                disabled={!importFile || isImporting || importDone}
                onClick={handleImport}
              >
                {isImporting && <span className="loading loading-spinner loading-sm" />}
                {t('onboarding.import_button')}
              </button>
              {/* Outline, not ghost: ghost renders borderless on the light card,
                  so this read as plain text rather than a button. */}
              <button
                className="btn btn-outline flex-1"
                onClick={() => goTo(stepAfterImport(importDone))}
              >
                {importDone ? t('onboarding.next') : t('onboarding.skip_import')}
              </button>
            </div>
          </div>
        )}

        {step === 'devices' && (
          <div className={`space-y-4 flex-1 flex flex-col ${stepEnter}`}>
            <p className="text-sm opacity-80">{t('onboarding.devices_intro')}</p>

            {targetsError && <div className="text-error text-sm">{targetsError}</div>}

            {!targets && !targetsError && (
              <div className="flex justify-center py-6">
                <span className="loading loading-spinner loading-md text-primary" />
              </div>
            )}

            {targets && (
              <>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary mt-0.5"
                    checked={restoreState}
                    onChange={(e) => {
                      setRestoreState(e.target.checked);
                      setDevicesDone(false);
                    }}
                  />
                  <span className="text-sm">{t('onboarding.devices_restore_state')}</span>
                </label>

                <div className="space-y-2">
                  {/* Only the modes this board can honour: a cover board has no
                      plain relays, a relay board no covers until two are
                      paired, so the backend decides what is on offer. */}
                  {targets.available_modes.map((mode) => (
                    <label key={mode} className="flex items-start gap-3 cursor-pointer">
                      <input
                        type="radio"
                        name="onboarding-input-mode"
                        className="radio radio-primary mt-0.5"
                        checked={inputMode === mode}
                        onChange={() => {
                          setInputMode(mode);
                          setDevicesDone(false);
                        }}
                      />
                      <span className="text-sm">
                        {t(`onboarding.devices_mode_${mode}`, {
                          outputs: targets.outputs,
                          covers: targets.covers,
                        })}
                      </span>
                    </label>
                  ))}
                </div>

                <div className="text-xs opacity-60">
                  {t('onboarding.devices_summary', {
                    device: targets.device_type ?? '—',
                    inputs: targets.free_inputs,
                    outputs: targets.outputs,
                    covers: targets.covers,
                  })}
                </div>

                {/* Dropped once applied: warning about a replacement that has
                    already happened is noise, and it makes room for the
                    confirmation without the card growing much. */}
                {inputMode !== 'none' && !devicesDone && (
                  <div className="alert alert-warning text-sm">
                    <span>{t('onboarding.devices_replace_warning')}</span>
                  </div>
                )}
              </>
            )}

            {devicesError && <div className="text-error text-sm">{devicesError}</div>}

            {devicesDone && (
              <div className="alert alert-success text-sm animate-in fade-in zoom-in-95 duration-200">
                <span>{t('onboarding.devices_done')}</span>
              </div>
            )}

            <div className="flex flex-wrap gap-2 mt-auto">
              {previousStep && (
                <button className={backButtonClass} onClick={goBack}>
                  {t('onboarding.back')}
                </button>
              )}
              <button
                className="btn btn-primary flex-1"
                disabled={!targets || !inputMode || isApplyingDevices || devicesDone}
                onClick={handleApplyDevices}
              >
                {isApplyingDevices && <span className="loading loading-spinner loading-sm" />}
                {t('onboarding.devices_apply')}
              </button>
              <button className="btn btn-outline flex-1" onClick={() => goTo('cloud')}>
                {devicesDone ? t('onboarding.next') : t('onboarding.devices_skip')}
              </button>
            </div>
          </div>
        )}

        {step === 'cloud' && (
          <div className={`space-y-4 flex-1 flex flex-col ${stepEnter}`}>
            <p className="text-sm opacity-80">{t('onboarding.cloud_intro')}</p>

            <ul className="text-sm opacity-80 list-disc list-inside space-y-1">
              <li>{t('onboarding.cloud_benefit_ssl')}</li>
              <li>{t('onboarding.cloud_benefit_pwa')}</li>
            </ul>

            <div className="alert alert-warning text-sm">
              <span>{t('onboarding.cloud_caveat')}</span>
            </div>

            {cloudError && <div className="text-error text-sm">{cloudError}</div>}

            {cloudDone && (
              <div className="alert alert-success text-sm animate-in fade-in zoom-in-95 duration-200">
                <span>
                  {t(cloudDone === 'deferred'
                    ? 'onboarding.cloud_done_deferred'
                    : 'onboarding.cloud_done')}
                </span>
              </div>
            )}

            <div className="flex flex-wrap gap-2 mt-auto">
              {previousStep && (
                <button className={backButtonClass} onClick={goBack}>
                  {t('onboarding.back')}
                </button>
              )}
              <button
                className="btn btn-primary flex-1"
                disabled={isEnablingCloud || cloudDone !== false}
                onClick={handleEnableCloud}
              >
                {isEnablingCloud && <span className="loading loading-spinner loading-sm" />}
                {t('onboarding.cloud_enable')}
              </button>
              <button className="btn btn-outline flex-1" onClick={() => goTo('done')}>
                {cloudDone ? t('onboarding.next') : t('onboarding.cloud_skip')}
              </button>
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className={`space-y-4 flex-1 flex flex-col ${stepEnter}`}>
            {/* The one flourish in the wizard, and the only place it is
                earned: the device now has an owner. Drawn with stroke offsets
                rather than a spinner so it reads as a finished gesture. */}
            <div className="flex justify-center py-2">
              <svg
                viewBox="0 0 52 52"
                className="w-16 h-16 text-success"
                aria-hidden="true"
                focusable="false"
              >
                <circle
                  className="wizard-check-ring"
                  cx="26"
                  cy="26"
                  r="24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path
                  className="wizard-check-tick"
                  d="M14 27 l8 8 l16 -16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <div className="alert alert-success text-sm animate-in fade-in zoom-in-95 duration-200 delay-300 fill-mode-backwards">
              <span>{t('onboarding.done_summary', { username })}</span>
            </div>

            {importDone && (
              <div className="alert alert-info text-sm">
                <span>{t('onboarding.done_import_skipped')}</span>
              </div>
            )}

            {sshOutcome === 'set' && (
              <div className="alert alert-info text-sm">
                <span>{t('onboarding.ssh_set', { username: 'boneio' })}</span>
              </div>
            )}
            {sshOutcome === 'kept' && (
              <div className="alert alert-info text-sm">
                <span>{t('onboarding.ssh_kept')}</span>
              </div>
            )}
            {sshOutcome === 'failed' && (
              <div className="alert alert-warning text-sm">
                <span>{t('onboarding.ssh_failed')}</span>
              </div>
            )}

            <div className="flex flex-wrap gap-2 mt-auto">
              {previousStep && (
                <button className={backButtonClass} onClick={goBack}>
                  {t('onboarding.back')}
                </button>
              )}
              <button className="btn btn-primary flex-1" onClick={finish}>
                {t('onboarding.finish')}
              </button>
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
