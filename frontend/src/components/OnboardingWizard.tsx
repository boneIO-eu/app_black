import { useState, useEffect, FormEvent, useRef, type DragEvent, type ReactNode } from 'react';
import {
  FaCheck,
  FaCloud,
  FaEye,
  FaEyeSlash,
  FaFileArchive,
  FaFileImport,
  FaMicrochip,
  FaRocket,
  FaSlidersH,
  FaUserShield,
} from 'react-icons/fa';
import type { AxiosError } from 'axios';
import axios from '@/api/axios';
import { updateWebSection } from '@/api/webSection';
import { useAuth } from '../hooks/useAuth';
import { type CloudSwitch, isCurrentOrigin, useCloudSwitch } from '../hooks/useCloudSwitch';
import { useAppInit } from '@/contexts/AppInitContext';
import { useTranslation } from '../hooks/useTranslation';
import {
  type Step,
  stepsFor,
  previousStepFor,
  stepAfterImport,
  stepAfterDevices,
  stepAfterAccount,
  stepAfterBoard,
} from '@/utils/onboardingSteps';
import { checkImportFile, interpretRestoreResponse } from '@/utils/onboardingImport';
import {
  MIN_PASSWORD_LENGTH,
  PASSWORD_PROBLEM_KEYS,
  checkPassword,
} from '@/utils/passwordPolicy';
import ThemeChanger from './ThemeChanger';
import LanguageSelector from './LanguageSelector';
import Logo from './Logo';
// Straight from the files, not the UISettings/ui barrel: the wizard is in the
// entry chunk, and the barrel would drag the whole settings kit in with it.
import { NoticeCallout } from './UISettings/ui/NoticeCallout';
import { ToggleRow } from './UISettings/ui/ToggleRow';

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

/** The host of a URL, for a button label; the URL itself if it does not parse. */
function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/**
 * A translated sentence with *url* in it, the address made a link. Split on
 * the address rather than marked up in every locale: the translation is
 * already interpolated, and the address is the one thing to click.
 */
function withLink(text: string, url: string): ReactNode {
  const at = text.indexOf(url);
  if (at < 0) return text;
  return (
    <>
      {text.slice(0, at)}
      <a href={url} target="_blank" rel="noopener noreferrer" className="link link-primary wrap-break-word">
        {url}
      </a>
      {text.slice(at + url.length)}
    </>
  );
}

/**
 * Where the PWA switch is, in words. Shown on the cloud step once it is on
 * and again on the last one, since that is where the owner waits for it.
 */
function CloudSwitchNotice({ cloud }: { cloud: CloudSwitch }) {
  const { t } = useTranslation();
  switch (cloud.phase) {
    case 'switching':
    case 'probing':
      return (
        <NoticeCallout
          variant="info"
          title={
            <span className="inline-flex items-center gap-2">
              <span className="loading loading-spinner loading-xs" />
              {t('onboarding.cloud_switching_title')}
            </span>
          }
          message={t('onboarding.cloud_switching')}
        />
      );
    case 'ready':
      return (
        <NoticeCallout
          variant="success"
          message={cloud.url && !isCurrentOrigin(cloud.url)
            ? withLink(t('onboarding.cloud_ready', { url: cloud.url }), cloud.url)
            : t('onboarding.cloud_ready_here')}
        />
      );
    case 'unreachable':
      return (
        <NoticeCallout
          variant="warning"
          message={withLink(t('onboarding.cloud_unreachable', { url: cloud.url ?? '' }), cloud.url ?? '')}
        />
      );
    case 'timeout': {
      const text = cloud.url ? t('onboarding.cloud_timeout_at', { url: cloud.url }) : t('onboarding.cloud_timeout');
      const message = cloud.url ? withLink(text, cloud.url) : text;
      return (
        <NoticeCallout
          variant="warning"
          message={cloud.error ? <>{message} {cloud.error}</> : message}
        />
      );
    }
    default:
      return null;
  }
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

/** The controllers the board step offers, as boneio.txt DEVICE_TYPE names them. */
const BOARD_TYPES = ['32x10', '24x16', 'cover', 'cover_mix'] as const;
type BoardType = (typeof BOARD_TYPES)[number];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** The chip each step's header carries. `done` draws its own checkmark. */
const STEP_ICONS: Record<Exclude<Step, 'done'>, ReactNode> = {
  welcome: <FaRocket />,
  account: <FaUserShield />,
  board: <FaMicrochip />,
  import: <FaFileImport />,
  devices: <FaSlidersH />,
  cloud: <FaCloud />,
};

/** "12.4 kB" — enough to tell a config archive from the wrong file at a glance. */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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
  const cloudSwitch = useCloudSwitch(cloudDone === 'live');
  const cloudSwitchPending = cloudSwitch.phase === 'switching' || cloudSwitch.phase === 'probing';
  // Only a name this browser reached: one it cannot resolve would trade a
  // working panel for an error page.
  const newAddress =
    cloudSwitch.phase === 'ready' && cloudSwitch.url && !isCurrentOrigin(cloudSwitch.url)
      ? cloudSwitch.url
      : null;
  // Set while a file is dragged over the drop zone, so it can light up.
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const configuredBefore = initData?.configured_before ?? false;
  // Latched as the wizard opens. /api/init is polled, and enabling cloud on
  // the cloud step would otherwise make that step vanish from under the user.
  const [cloudEnabled] = useState(() => initData?.cloud?.enabled ?? false);
  // Latched too: choosing the type clears the flag, and the step must not
  // vanish from the progress bar the moment it is done.
  const [boardTypeRequired] = useState(() => initData?.board_type_required ?? false);
  const [boardType, setBoardType] = useState<BoardType | null>(null);
  const [isSettingBoard, setIsSettingBoard] = useState(false);
  const [boardError, setBoardError] = useState<string | null>(null);
  const steps = stepsFor(configuredBefore, cloudEnabled, boardTypeRequired);
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

  const previousStep = previousStepFor(step, importDone, configuredBefore, cloudEnabled, boardTypeRequired);

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
      // On an upgraded device there is nothing to import and nothing to wire.
      goTo(stepAfterAccount(configuredBefore, cloudEnabled, boardTypeRequired));
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

  const handleSetBoard = async () => {
    if (!boardType) return;
    setBoardError(null);
    setIsSettingBoard(true);
    try {
      const { data } = await axios.post('/api/onboarding/board-type', { type: boardType }, { timeout: 30_000 });
      if (data?.restarting) {
        // boneIO restarts on the new configuration. Give the old process time
        // to go, then wait for the API itself: while it starts, port 8090
        // answers with an HTML loading page, which is not the panel back.
        await sleep(3_000);
        const deadline = Date.now() + 180_000;
        for (;;) {
          try {
            const res = await axios.get('/api/init', { timeout: 5_000 });
            if (res.data && typeof res.data === 'object') break;
          } catch {
            // Still restarting.
          }
          if (Date.now() > deadline) throw new Error(t('onboarding.board_restart_slow'));
          await sleep(2_000);
        }
      }
      goTo(stepAfterBoard(configuredBefore, cloudEnabled));
    } catch (err: unknown) {
      setBoardError(errorMessage(err, t('onboarding.board_failed')));
    } finally {
      setIsSettingBoard(false);
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

  // A dropped file goes through the same checks as a picked one.
  const handleDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (isImporting) return;
    handleSelectImportFile(e.dataTransfer.files?.[0] ?? null);
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
      // Merged into the stored section: the port and proxy port set moments
      // ago live in here too, and so does `expose`.
      // Not the default 5 s: the backend starts registration inside this
      // request, and on a fresh controller that first loads aiohttp — 8 s on a
      // BeagleBone — so the save succeeded while the wizard reported failure.
      const saved = await updateWebSection<{ cloud?: string }>((web) => ({
        ...web,
        cloud: { ...((web.cloud ?? {}) as Record<string, unknown>), enabled: true },
      }), { timeout: 30_000 });
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
    if (newAddress) {
      // Another origin, so another localStorage: the token stays behind and
      // the panel there asks for the password once. The notice says so. A new
      // tab, so a browser that offers to install the PWA does it on a fresh
      // load of the address it will keep.
      window.open(newAddress, '_blank', 'noopener');
      return;
    }
    // A restored config is only live after a restart, and the rest of the app
    // caches config aggressively, so start from a clean load either way.
    window.location.reload();
  };

  // Every step opens the same way as a settings card: its chip, what it is
  // called, and one line on what it is for.
  const stepHeader = (name: Exclude<Step, 'done'>, intro: string) => (
    <div className="flex items-start gap-3.5">
      <div className="stg-chip w-11 h-11 rounded-xl flex items-center justify-center text-lg shrink-0">
        {STEP_ICONS[name]}
      </div>
      <div className="min-w-0">
        <h2 className="text-lg font-semibold leading-tight">{t(`onboarding.heading_${name}`)}</h2>
        <p className="mt-1 text-sm text-base-content/70 leading-relaxed">{intro}</p>
      </div>
    </div>
  );

  const stepCounter = t('onboarding.step_counter', {
    current: stepIndex + 1,
    total: steps.length,
  });

  return (
    // Same shell as the login screen, which is what the owner sees next: on a
    // phone the wizard is the page, edge to edge, with its buttons pinned to
    // the bottom; from sm up it is a card on the app's tinted field.
    <div className="min-h-dvh flex flex-col sm:items-center sm:justify-center stg-backdrop sm:p-6">
      {/* The wizard is the first screen a new owner sees, so the language and
          theme pickers have to live here — the header that normally carries
          them only exists once onboarding is done. Absolute, not fixed as
          on the login: several steps run taller than a phone screen, and
          fixed icons would sit over the text scrolling under them. */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
        <ThemeChanger />
        <LanguageSelector />
      </div>

      <main className="flex-1 sm:flex-none flex flex-col w-full sm:max-w-xl bg-base-100 px-5 pt-16 pb-6 sm:p-8 sm:rounded-2xl sm:border sm:border-base-content/10 sm:shadow-xl animate-in fade-in sm:zoom-in-95 duration-500 ease-out">
        <div className="flex flex-col items-center text-center">
          {/* Slightly behind the card, so the mark settles into a frame that is
              already there rather than racing it. */}
          <div className="w-24 sm:w-28 animate-in fade-in slide-in-from-top-2 duration-700 delay-150 fill-mode-backwards">
            <Logo />
          </div>
          {/* Brand name, not copy — deliberately not translated. */}
          <span className="mt-1 text-xs font-semibold tracking-[0.35em] uppercase opacity-60">
            Black
          </span>
          <h1 className="mt-5 text-xl sm:text-2xl font-bold">{t('onboarding.title')}</h1>
          {/* With several fresh controllers on one network, this says which
              one is about to get an owner. */}
          {initData?.name && (
            <p className="mt-1 text-sm text-base-content/60 break-words">{initData.name}</p>
          )}
        </div>

        {/* One segment per step: it fits a 320px phone at any step count,
            which the numbered daisyUI row did not. The names come in from sm
            up; on a phone the current one is spelled out beside the counter. */}
        <div className="mt-6">
          <div className="flex items-baseline justify-between gap-3 mb-2 text-xs">
            <span className="font-semibold uppercase tracking-[0.08em] text-base-content/50">
              {stepCounter}
            </span>
            <span className="sm:hidden font-medium text-base-content/70 truncate">
              {t(`onboarding.step_${step}`)}
            </span>
          </div>
          <ol className="flex gap-1.5" aria-label={stepCounter}>
            {steps.map((name, index) => (
              <li
                key={name}
                className="flex-1 min-w-0"
                aria-current={index === stepIndex ? 'step' : undefined}
              >
                <div
                  className={`h-1.5 rounded-full transition-colors duration-500 ${
                    index <= stepIndex ? 'bg-primary' : 'bg-base-content/10'
                  }`}
                />
                <span
                  className={`hidden sm:block mt-1.5 text-[11px] truncate transition-colors ${
                    index === stepIndex
                      ? 'font-semibold text-base-content'
                      : index < stepIndex
                        ? 'text-base-content/60'
                        : 'text-base-content/40'
                  }`}
                >
                  {t(`onboarding.step_${name}`)}
                </span>
              </li>
            ))}
          </ol>
        </div>

        {/* Reserve the tallest step's height so the card does not resize from
            step to step. Only from sm up: on a phone the page itself is the
            card, the step fills whatever is left of the screen and the
            buttons sit at the bottom of it either way.
            Measured in Polish at the 576px the card maxes out at. Tallest is
            the account step once the server has refused it (574px with a
            one-line error), then its inline hints (545px), the devices step
            on a cover_mix board where every mode is on offer at once (532px)
            and the welcome step (525px). An error running to a second line
            still grows the card a little.
            On a short screen the floor gives way: header, progress bar and
            paddings take about 19rem, and a 768px laptop would otherwise
            push even the shortest step's buttons below the fold.
            A floor, not a cap: a step that somehow runs taller still grows.
            Re-measure when a step gains content. */}
        <div className="mt-6 flex-1 flex sm:min-h-[min(36rem,calc(100dvh_-_19rem))]">
        {step === 'welcome' && (
          <div className={`flex-1 flex flex-col gap-4 ${stepEnter}`}>
            {/* An upgraded device keeps its configuration; saying otherwise
                reads as though the update threw it away. */}
            {stepHeader(
              'welcome',
              t(configuredBefore ? 'onboarding.welcome_intro_upgraded' : 'onboarding.welcome_intro'),
            )}

            <NoticeCallout variant="warning" message={t('onboarding.welcome_why')} />

            {/* What the rest of the wizard holds, so "Start" does not lead
                into the unknown. The closing step is not a task, so it is
                left off. */}
            <div className="stg-inset p-3.5 sm:p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-base-content/50 mb-3">
                {t('onboarding.welcome_plan')}
              </div>
              <ol className="space-y-2.5">
                {steps
                  .filter((name): name is Exclude<Step, 'welcome' | 'done'> =>
                    name !== 'welcome' && name !== 'done',
                  )
                  .map((name) => (
                    <li key={name} className="flex items-center gap-3 text-sm">
                      <span className="stg-chip-neutral w-8 h-8 rounded-lg flex items-center justify-center text-[13px] shrink-0">
                        {STEP_ICONS[name]}
                      </span>
                      <span>{t(`onboarding.heading_${name}`)}</span>
                    </li>
                  ))}
              </ol>
            </div>

            {/* Pinned as a pair, and pinned on the wrapper rather than on the
                caption: /api/init can be slow or absent, and the button must
                not drift up the card just because the version line is late. */}
            <div className="mt-auto space-y-3">
              {initData && (
                <div className="text-xs text-base-content/50 text-center">v{initData.version}</div>
              )}

              <button className="btn btn-primary w-full" onClick={() => goTo('account')}>
                {t('onboarding.start')}
              </button>
            </div>
          </div>
        )}

        {step === 'account' && (
          <form className={`flex-1 flex flex-col gap-4 ${stepEnter}`} onSubmit={handleCreateAccount}>
            {stepHeader('account', t('onboarding.account_intro'))}

            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="onboarding-username" className="text-sm font-medium">
                  {t('onboarding.username')}
                </label>
                <input
                  id="onboarding-username"
                  type="text"
                  className="input input-lg w-full text-base"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="onboarding-password" className="text-sm font-medium">
                  {t('onboarding.password')}
                </label>
                {/* daisyUI styles a wrapper holding an input as the input
                    itself, focus ring included, which leaves room for the eye
                    button — the same field as on the login screen. The error
                    colour goes on the wrapper, since that is what draws the
                    border; the ARIA state stays on the input it describes. */}
                <div className={`input input-lg w-full pr-1 ${usernameInPassword ? 'input-error' : ''}`}>
                  <input
                    id="onboarding-password"
                    type={showPassword ? 'text' : 'password'}
                    className="grow text-base"
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
                    className="btn btn-ghost btn-square btn-sm h-10 w-10"
                    aria-label={
                      showPassword ? t('onboarding.hide_password') : t('onboarding.show_password')
                    }
                    aria-pressed={showPassword}
                    title={showPassword ? t('onboarding.hide_password') : t('onboarding.show_password')}
                    // Out of the tab order on purpose: Tab goes from the password
                    // straight to its confirmation, which is what somebody typing
                    // a password they just invented is about to do. The button is
                    // still clickable and still announced, since aria-label and
                    // aria-pressed do not depend on tab order.
                    tabIndex={-1}
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? (
                      <FaEyeSlash className="h-5 w-5 opacity-70" />
                    ) : (
                      <FaEye className="h-5 w-5 opacity-70" />
                    )}
                  </button>
                </div>
                {usernameInPassword ? (
                  <p id="onboarding-password-error" className="text-error text-xs">
                    {usernameInPassword}
                  </p>
                ) : (
                  <p className="text-xs text-base-content/55">
                    {t('onboarding.password_hint', { min: MIN_PASSWORD_LENGTH })}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="onboarding-confirm" className="text-sm font-medium">
                  {t('onboarding.confirm_password')}
                </label>
                <input
                  id="onboarding-confirm"
                  type={showPassword ? 'text' : 'password'}
                  className={`input input-lg w-full text-base ${confirmProblem ? 'input-error' : ''}`}
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
                  <p id="onboarding-confirm-error" className="text-error text-xs">
                    {confirmProblem}
                  </p>
                )}
              </div>
            </div>

            {/* Said before the password is sent, not after. It becomes the
                root-capable SSH login as well, and somebody choosing a
                password deserves to know what it will open. */}
            <NoticeCallout variant="info" message={t('onboarding.ssh_password_notice')} />
            {/* Node-RED keeps no accounts of its own: its login asks boneIO
                (settings.js, adminAuth), administrators only. */}
            <NoticeCallout variant="info" message={t('onboarding.nodered_login_notice')} />

            {error && (
              <div role="alert">
                <NoticeCallout variant="error" message={error} />
              </div>
            )}

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

        {step === 'board' && (
          <div className={`flex-1 flex flex-col gap-4 ${stepEnter}`}>
            {stepHeader('board', t('onboarding.board_intro'))}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5" role="radiogroup" aria-label={t('onboarding.heading_board')}>
              {BOARD_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  role="radio"
                  aria-checked={boardType === type}
                  disabled={isSettingBoard}
                  onClick={() => setBoardType(type)}
                  className={`stg-inset text-left p-3.5 rounded-xl border-2 transition-colors ${
                    boardType === type ? 'border-primary' : 'border-transparent hover:border-base-content/20'
                  }`}
                >
                  <span className="block font-semibold">{t(`onboarding.board_${type}`)}</span>
                  <span className="block mt-0.5 text-xs text-base-content/70">{t(`onboarding.board_${type}_desc`)}</span>
                </button>
              ))}
            </div>

            {isSettingBoard && (
              <NoticeCallout variant="info" message={t('onboarding.board_restarting')} />
            )}
            {boardError && <NoticeCallout variant="error" message={boardError} />}

            <div className="flex flex-wrap gap-2 mt-auto">
              <button
                className="btn btn-primary flex-1"
                disabled={!boardType || isSettingBoard}
                onClick={handleSetBoard}
              >
                {isSettingBoard && <span className="loading loading-spinner loading-sm" />}
                {t('onboarding.board_apply')}
              </button>
            </div>
          </div>
        )}

        {step === 'import' && (
          <div className={`flex-1 flex flex-col gap-4 ${stepEnter}`}>
            {stepHeader('import', t('onboarding.import_intro'))}

            {/* A drop zone around the native input rather than daisyUI's
                file-input, whose "Choose file / No file chosen" comes from the
                browser in the browser's language, not the panel's. The input
                is visually hidden but not removed, so Tab still reaches it and
                Enter still opens the picker; the ring follows it. Children
                ignore the pointer so dragging across them does not fire
                dragleave on the zone and make it flicker. */}
            <label
              htmlFor="onboarding-import-file"
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              className={`flex flex-col items-center justify-center gap-2 text-center rounded-xl border-2 border-dashed px-4 py-7 cursor-pointer transition-colors *:pointer-events-none has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary/40 ${
                isDragging
                  ? 'border-primary bg-primary/5'
                  : importFile
                    ? 'border-primary/40 bg-primary/[0.03]'
                    : 'border-base-content/15 hover:border-primary/40 hover:bg-primary/[0.03]'
              }`}
            >
              <input
                ref={fileInputRef}
                id="onboarding-import-file"
                type="file"
                accept=".tar.gz,.tgz,application/gzip"
                className="sr-only"
                disabled={isImporting}
                onChange={(e) => handleSelectImportFile(e.target.files?.[0] ?? null)}
              />
              <span
                className={`${importFile ? 'stg-chip' : 'stg-chip-neutral'} w-12 h-12 rounded-xl flex items-center justify-center text-xl mb-1`}
              >
                <FaFileArchive />
              </span>
              {importFile ? (
                <>
                  <span className="text-sm font-medium break-all">{importFile.name}</span>
                  <span className="text-xs text-base-content/55">
                    {formatSize(importFile.size)} · {t('onboarding.import_change')}
                  </span>
                </>
              ) : (
                <>
                  <span className="text-sm font-medium">{t('onboarding.import_choose')}</span>
                  <span className="text-xs text-base-content/55">{t('onboarding.import_formats')}</span>
                </>
              )}
            </label>

            {importError && <NoticeCallout variant="error" message={importError} />}

            {importDone && (
              <NoticeCallout
                variant="success"
                message={t('onboarding.import_done')}
                className="animate-in fade-in zoom-in-95 duration-200"
              />
            )}

            {importWarning && (
              <NoticeCallout
                variant="warning"
                message={importWarning}
                className="animate-in fade-in zoom-in-95 duration-200"
              />
            )}

            {/* Say it here rather than letting "Next" quietly jump two steps. */}
            {importDone && (
              <p className="text-xs text-base-content/60">{t('onboarding.import_skips_rest')}</p>
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
          <div className={`flex-1 flex flex-col gap-4 ${stepEnter}`}>
            {stepHeader('devices', t('onboarding.devices_intro'))}

            {targetsError && <NoticeCallout variant="error" message={targetsError} />}

            {!targets && !targetsError && (
              <div className="flex justify-center py-6">
                <span className="loading loading-spinner loading-md text-primary" />
              </div>
            )}

            {targets && (
              <>
                <ToggleRow
                  checked={restoreState}
                  onChange={(checked) => {
                    setRestoreState(checked);
                    setDevicesDone(false);
                  }}
                  label={t('onboarding.devices_restore_state')}
                  className="p-3 sm:p-3.5"
                />

                <div className="space-y-1.5">
                  {/* Only the modes this board can honour: a cover board has no
                      plain relays, a relay board no covers until two are
                      paired, so the backend decides what is on offer.
                      Native radios inside the cards, so arrow keys move
                      between them and the card lights up from the input's own
                      state rather than from a click handler. */}
                  {targets.available_modes.map((mode) => (
                    <label
                      key={mode}
                      className="flex items-center gap-3 px-3.5 py-3 rounded-xl border border-base-content/10 bg-base-100 cursor-pointer select-none transition-colors hover:border-base-content/20 has-[:checked]:border-primary/50 has-[:checked]:bg-primary/5 has-[:checked]:ring-1 has-[:checked]:ring-primary/20 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary/40"
                    >
                      <input
                        type="radio"
                        name="onboarding-input-mode"
                        className="radio radio-primary radio-sm shrink-0"
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

                <div className="text-xs text-base-content/55">
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
                  <NoticeCallout variant="warning" message={t('onboarding.devices_replace_warning')} />
                )}
              </>
            )}

            {devicesError && <NoticeCallout variant="error" message={devicesError} />}

            {devicesDone && (
              <NoticeCallout
                variant="success"
                message={t('onboarding.devices_done')}
                className="animate-in fade-in zoom-in-95 duration-200"
              />
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
              <button className="btn btn-outline flex-1" onClick={() => goTo(stepAfterDevices(cloudEnabled))}>
                {devicesDone ? t('onboarding.next') : t('onboarding.devices_skip')}
              </button>
            </div>
          </div>
        )}

        {step === 'cloud' && (
          <div className={`flex-1 flex flex-col gap-4 ${stepEnter}`}>
            {stepHeader('cloud', t('onboarding.cloud_intro'))}

            <ul className="stg-inset p-3.5 sm:p-4 space-y-2.5">
              {[t('onboarding.cloud_benefit_ssl'), t('onboarding.cloud_benefit_pwa')].map((benefit) => (
                <li key={benefit} className="flex items-start gap-2.5 text-sm">
                  <FaCheck className="text-success text-xs mt-1 shrink-0" aria-hidden="true" />
                  <span>{benefit}</span>
                </li>
              ))}
            </ul>

            <NoticeCallout variant="warning" message={t('onboarding.cloud_caveat')} />

            {cloudError && <NoticeCallout variant="error" message={cloudError} />}

            {cloudDone === 'deferred' && (
              <NoticeCallout
                variant="success"
                message={t('onboarding.cloud_done_deferred')}
                className="animate-in fade-in zoom-in-95 duration-200"
              />
            )}
            {cloudDone === 'live' && <CloudSwitchNotice cloud={cloudSwitch} />}

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
              <button
                className="btn btn-outline flex-1"
                onClick={() => goTo('done')}
                disabled={cloudSwitchPending}
              >
                {cloudDone ? t('onboarding.next') : t('onboarding.cloud_skip')}
              </button>
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className={`flex-1 flex flex-col gap-4 ${stepEnter}`}>
            <div className="flex flex-col items-center text-center pt-2 pb-1">
              {/* The one flourish in the wizard, and the only place it is
                  earned: the device now has an owner. Drawn with stroke offsets
                  rather than a spinner so it reads as a finished gesture. */}
              <svg
                viewBox="0 0 52 52"
                className="w-20 h-20 text-success"
                aria-hidden="true"
                focusable="false"
              >
                <circle
                  cx="26"
                  cy="26"
                  r="24"
                  className="fill-success/10"
                  stroke="none"
                />
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
              <h2 className="mt-4 text-xl font-semibold">{t('onboarding.heading_done')}</h2>
              <p className="mt-1.5 max-w-md text-sm text-base-content/70 leading-relaxed animate-in fade-in duration-300 delay-300 fill-mode-backwards">
                {t('onboarding.done_summary', { username })}
              </p>
            </div>

            {importDone && (
              <NoticeCallout variant="info" message={t('onboarding.done_import_skipped')} />
            )}

            {sshOutcome === 'set' && (
              <NoticeCallout variant="info" message={t('onboarding.ssh_set', { username: 'boneio' })} />
            )}
            {sshOutcome === 'kept' && (
              <NoticeCallout variant="info" message={t('onboarding.ssh_kept')} />
            )}
            {sshOutcome === 'failed' && (
              <NoticeCallout variant="warning" message={t('onboarding.ssh_failed')} />
            )}
            <NoticeCallout variant="info" message={t('onboarding.nodered_login_done', { username })} />

            {cloudDone === 'live' && <CloudSwitchNotice cloud={cloudSwitch} />}

            {newAddress ? (
              // Three buttons in a row left "Go to blk….black.boneio.app:8443"
              // and "Stay at this address" wrapped inside fixed-height buttons.
              // The way forward gets its own row; the two ways back share one.
              <div className="flex flex-col gap-2 mt-auto">
                <button className="btn btn-primary h-auto min-h-11 py-2 whitespace-normal wrap-break-word" onClick={finish}>
                  {t('onboarding.finish_at', { host: hostOf(newAddress) })}
                </button>
                <div className="flex gap-2">
                  {previousStep && (
                    <button className="btn btn-outline" onClick={goBack}>
                      {t('onboarding.back')}
                    </button>
                  )}
                  <button className="btn btn-outline flex-1 h-auto min-h-10 whitespace-normal" onClick={() => window.location.reload()}>
                    {t('onboarding.cloud_stay_here')}
                  </button>
                </div>
              </div>
            ) : (
            <div className="flex flex-wrap gap-2 mt-auto">
              {previousStep && (
                <button className={backButtonClass} onClick={goBack}>
                  {t('onboarding.back')}
                </button>
              )}
              {(cloudSwitch.phase === 'unreachable' || cloudSwitch.phase === 'timeout') && cloudSwitch.url && (
                <a className="btn btn-outline basis-full order-first h-auto min-h-10 py-2 whitespace-normal wrap-break-word" href={cloudSwitch.url} target="_blank" rel="noopener noreferrer">
                  {t('onboarding.cloud_open_anyway', { host: hostOf(cloudSwitch.url) })}
                </a>
              )}
              <button
                className="btn btn-primary flex-1"
                onClick={finish}
                disabled={cloudSwitchPending}
              >
                {cloudSwitchPending && <span className="loading loading-spinner loading-sm" />}
                {cloudSwitchPending ? t('onboarding.cloud_switch_wait') : t('onboarding.finish')}
              </button>
            </div>
            )}
          </div>
        )}
        </div>
      </main>
    </div>
  );
}
