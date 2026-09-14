import { useState, FormEvent, useRef } from 'react';
import type { AxiosError } from 'axios';
import axios from '@/api/axios';
import { useAuth } from '../hooks/useAuth';
import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '../hooks/useTranslation';
import ThemeChanger from './ThemeChanger';
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

/** Mirrors the backend minimum in boneio/core/auth/store.py. */
const MIN_PASSWORD_LENGTH = 8;

type Step = 'welcome' | 'account' | 'import' | 'cloud' | 'done';

const STEP_ORDER: Step[] = ['welcome', 'account', 'import', 'cloud', 'done'];

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
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [importFile, setImportFile] = useState<File | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importDone, setImportDone] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const [cloudError, setCloudError] = useState<string | null>(null);
  const [cloudDone, setCloudDone] = useState(false);
  const [isEnablingCloud, setIsEnablingCloud] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const legacy = initData?.legacy_migration ?? null;
  const stepIndex = STEP_ORDER.indexOf(step);

  const passwordProblem = (): string | null => {
    if (password.length < MIN_PASSWORD_LENGTH) {
      return t('onboarding.error_password_short', { min: MIN_PASSWORD_LENGTH });
    }
    if (password !== confirmPassword) {
      return t('onboarding.error_password_mismatch');
    }
    return null;
  };

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
      const response = await axios.post('/api/onboarding/admin', { username, password });
      // The device is now ours; adopt the token before anything else so the
      // remaining steps run authenticated rather than through the open window.
      loginWithToken(response.data.token);
      // Deliberately NOT refetching /api/init here. The gate in App.tsx keys
      // the wizard off needs_onboarding, so refreshing it the moment the
      // account exists unmounts this component mid-flow and the import and
      // summary steps become unreachable. finish() reloads the page, which
      // refetches everything anyway.
      // Only cleared on success: a recoverable error (a rejected username,
      // say) should not cost the user both passwords as well.
      setPassword('');
      setConfirmPassword('');
      setStep('import');
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

  const handleImport = async () => {
    if (!importFile) return;
    setImportError(null);
    setIsImporting(true);

    const form = new FormData();
    form.append('file', importFile);

    try {
      await axios.post('/api/config/restore', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setImportDone(true);
    } catch (err: unknown) {
      setImportError(errorMessage(err, t('onboarding.import_failed')));
    } finally {
      setIsImporting(false);
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
      await axios.put('/api/config/web', { ...web, cloud: { ...cloud, enabled: true } });
      setCloudDone(true);
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
    <div className="min-h-screen flex items-center justify-center bg-base-100 p-4">
      <div className="hidden">
        <ThemeChanger />
      </div>

      <div className="max-w-xl w-full space-y-6 p-8 bg-base-100 rounded-lg shadow-lg">
        <div className="flex flex-col items-center">
          <div className="w-28">
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

        <ul className="steps w-full text-xs">
          {STEP_ORDER.map((name, index) => (
            <li
              key={name}
              className={`step ${index <= stepIndex ? 'step-primary' : ''}`}
            >
              {t(`onboarding.step_${name}`)}
            </li>
          ))}
        </ul>

        {step === 'welcome' && (
          <div className="space-y-4">
            <p className="text-sm opacity-80">{t('onboarding.welcome_intro')}</p>

            <div className="alert alert-warning text-sm">
              <span>{t('onboarding.welcome_why')}</span>
            </div>

            {legacy && (
              <div className="alert alert-info text-sm">
                <span>
                  {t('onboarding.legacy_migrated', { username: legacy.username })}
                  {legacy.used_secret_file ? ` ${t('onboarding.legacy_secret_hint')}` : ''}
                </span>
              </div>
            )}

            {initData && (
              <div className="text-xs opacity-60 text-center">
                {initData.name} · v{initData.version}
              </div>
            )}

            <button className="btn btn-primary w-full" onClick={() => setStep('account')}>
              {t('onboarding.start')}
            </button>
          </div>
        )}

        {step === 'account' && (
          <form className="space-y-4" onSubmit={handleCreateAccount}>
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
              <input
                id="onboarding-password"
                type="password"
                className="input w-full"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="text-xs opacity-60 mt-1">
                {t('onboarding.password_hint', { min: MIN_PASSWORD_LENGTH })}
              </p>
            </div>

            <div className="w-full">
              <label htmlFor="onboarding-confirm" className="block text-sm mb-1">
                {t('onboarding.confirm_password')}
              </label>
              <input
                id="onboarding-confirm"
                type="password"
                className="input w-full"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>

            {error && <div className="text-error text-sm text-center">{error}</div>}

            <button
              type="submit"
              className="btn btn-primary w-full"
              disabled={isSubmitting || !username || !password}
            >
              {isSubmitting && <span className="loading loading-spinner loading-sm" />}
              {t('onboarding.create_account')}
            </button>
          </form>
        )}

        {step === 'import' && (
          <div className="space-y-4">
            <p className="text-sm opacity-80">{t('onboarding.import_intro')}</p>

            <input
              ref={fileInputRef}
              type="file"
              accept=".tar.gz,.tgz,application/gzip"
              className="file-input file-input-bordered w-full"
              onChange={(e) => {
                setImportFile(e.target.files?.[0] ?? null);
                setImportError(null);
                setImportDone(false);
              }}
            />

            {importError && <div className="text-error text-sm">{importError}</div>}

            {importDone && (
              <div className="alert alert-success text-sm">
                <span>{t('onboarding.import_done')}</span>
              </div>
            )}

            <div className="flex gap-2">
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
              <button className="btn btn-outline flex-1" onClick={() => setStep('cloud')}>
                {importDone ? t('onboarding.next') : t('onboarding.skip_import')}
              </button>
            </div>
          </div>
        )}

        {step === 'cloud' && (
          <div className="space-y-4">
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
              <div className="alert alert-success text-sm">
                <span>{t('onboarding.cloud_done')}</span>
              </div>
            )}

            <div className="flex gap-2">
              <button
                className="btn btn-primary flex-1"
                disabled={isEnablingCloud || cloudDone}
                onClick={handleEnableCloud}
              >
                {isEnablingCloud && <span className="loading loading-spinner loading-sm" />}
                {t('onboarding.cloud_enable')}
              </button>
              <button className="btn btn-outline flex-1" onClick={() => setStep('done')}>
                {cloudDone ? t('onboarding.next') : t('onboarding.cloud_skip')}
              </button>
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className="space-y-4">
            <div className="alert alert-success text-sm">
              <span>{t('onboarding.done_summary', { username })}</span>
            </div>

            {legacy && (
              <div className="alert alert-warning text-sm">
                <span>{t('onboarding.done_remove_web_auth')}</span>
              </div>
            )}

            <button className="btn btn-primary w-full" onClick={finish}>
              {t('onboarding.finish')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
