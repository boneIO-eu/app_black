import { useState, type FormEvent } from 'react';
import { FaEye, FaEyeSlash, FaKey } from 'react-icons/fa';
import type { AxiosError } from 'axios';
import axios from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';
import {
  MIN_PASSWORD_LENGTH,
  PASSWORD_PROBLEM_KEYS,
  checkNewPassword,
} from '@/utils/passwordPolicy';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

type ChangeError = AxiosError<{ code?: string; attempts_left?: number; detail?: string }>;

/** From how many tries left the form starts counting them down, as ReauthDialog does. */
const WARN_FROM = 3;

interface PasswordFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: 'current-password' | 'new-password';
  error?: string | null;
  autoFocus?: boolean;
}

/** The login screen's field, eye button and all. */
function PasswordField({ id, label, value, onChange, autoComplete, error, autoFocus }: PasswordFieldProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className={`input w-full pr-1 ${error ? 'input-error' : ''}`}>
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          required
          className="grow font-mono"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="btn btn-ghost btn-square btn-sm"
          aria-label={visible ? t('login.hide_password') : t('login.show_password')}
          aria-pressed={visible}
          title={visible ? t('login.hide_password') : t('login.show_password')}
        >
          {visible ? <FaEyeSlash className="h-4 w-4 opacity-70" /> : <FaEye className="h-4 w-4 opacity-70" />}
        </button>
      </div>
      {error && (
        <p id={`${id}-error`} role="alert" className="text-error text-xs">
          {error}
        </p>
      )}
    </div>
  );
}

interface AccountPasswordDialogProps {
  /** The account whose password changes, or null when the dialog is closed. */
  username: string | null;
  /** Whether that account is the signed-in one. */
  isSelf: boolean;
  onClose: () => void;
  /** Called after the password has been changed. */
  onChanged: (username: string) => void;
}

/**
 * Change an account's password.
 *
 * Your own account goes through the self-service route, which wants the
 * current password: a session left open on somebody's laptop must not be
 * able to lock its owner out. Someone else's goes through the administrator
 * reset, which does not know the old one; the step-up prompt (ReauthDialog)
 * asks for yours on the way when the login is older than ten minutes.
 *
 * Either way it is the panel password only. The first-run wizard copies the
 * first one onto the boneio SSH login, once; after that the two are separate,
 * which the dialog says, because the table offers no other hint of it.
 *
 * Render it with `key` set to the account, so nothing typed for one account
 * survives into the next one's dialog.
 */
export default function AccountPasswordDialog({
  username,
  isSelf,
  onClose,
  onChanged,
}: AccountPasswordDialogProps) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [currentError, setCurrentError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const problem = checkNewPassword(password, repeat, username ?? '');
  // The mismatch waits until the second field has something in it, and the
  // policy until the first does: a form that scolds an empty field is noise.
  const passwordError =
    password && problem && problem !== 'mismatch'
      ? t(PASSWORD_PROBLEM_KEYS[problem], { min: MIN_PASSWORD_LENGTH })
      : null;
  const repeatError = repeat && problem === 'mismatch' ? t('accounts.password_mismatch') : null;

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!username || problem || (isSelf && !current)) return;
    setCurrentError(null);
    setFormError(null);
    setSubmitting(true);
    try {
      // The same scrypt work as a login, twice for your own (check, then
      // hash), which on a busy BeagleBone runs past the default 5 s.
      const { data } = isSelf
        ? await axios.put(
            '/api/account/password',
            { current_password: current, new_password: password },
            { timeout: 60_000 },
          )
        : await axios.put(
            `/api/accounts/${encodeURIComponent(username)}/password`,
            { password },
            { timeout: 60_000 },
          );
      // A new password signs the account out everywhere. When it is your own,
      // that includes this session, unless it adopts the token sent back.
      if (typeof data?.token === 'string') {
        localStorage.setItem('token', data.token);
      }
      onChanged(username);
    } catch (err: unknown) {
      const response = (err as ChangeError).response;
      if (response?.status === 403 && response.data?.code === 'current_password_wrong') {
        const left = response.data.attempts_left;
        setCurrentError(
          typeof left === 'number' && left <= WARN_FROM
            ? `${t('accounts.current_password_wrong')} ${t('reauth.attempts_left', { count: left })}`
            : t('accounts.current_password_wrong'),
        );
      } else if (response?.status === 429) {
        setFormError(t('reauth.throttled'));
      } else if (response?.status !== 401) {
        // 401 is a sign-out (the last wrong try, or the session ended), and
        // the login screen is already on its way.
        setFormError(response?.data?.detail || t('accounts.password_failed'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const title = isSelf
    ? t('accounts.change_own_password_title')
    : t('accounts.change_password_title', { username: username ?? '' });

  return (
    <Dialog open={username !== null} onOpenChange={(next) => !next && !submitting && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <div className="flex items-center gap-3">
              <span className="stg-chip w-10 h-10 rounded-xl flex items-center justify-center shrink-0">
                <FaKey />
              </span>
              <DialogTitle>{title}</DialogTitle>
            </div>
            <DialogDescription>
              {isSelf ? t('accounts.change_own_password_intro') : t('accounts.change_password_intro')}
            </DialogDescription>
          </DialogHeader>

          {isSelf && (
            <PasswordField
              id="account-current-password"
              label={t('accounts.current_password')}
              value={current}
              onChange={(v) => {
                setCurrent(v);
                setCurrentError(null);
              }}
              autoComplete="current-password"
              error={currentError}
              autoFocus
            />
          )}
          <PasswordField
            id="account-new-password"
            label={t('accounts.new_password')}
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            error={passwordError}
            autoFocus={!isSelf}
          />
          <PasswordField
            id="account-repeat-password"
            label={t('accounts.repeat_password')}
            value={repeat}
            onChange={setRepeat}
            autoComplete="new-password"
            error={repeatError}
          />

          <p className="text-xs opacity-70">{t('accounts.ssh_password_separate')}</p>

          {formError && (
            <p role="alert" className="text-error text-sm">
              {formError}
            </p>
          )}

          <DialogFooter>
            <button
              type="button"
              className="btn btn-ghost max-sm:btn-lg"
              onClick={onClose}
              disabled={submitting}
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-primary max-sm:btn-lg"
              disabled={submitting || !!problem || (isSelf && !current)}
            >
              {submitting && <span className="loading loading-spinner loading-sm" />}
              {t('accounts.change_password_button')}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
