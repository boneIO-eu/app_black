import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { FaEye, FaEyeSlash, FaLock } from 'react-icons/fa';
import type { AxiosError } from 'axios';
import axios, { UNAUTHORIZED_EVENT } from '@/api/axios';
import { setReauthHandler, type ReauthOutcome } from '@/api/reauth';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

type ConfirmError = AxiosError<{ code?: string }>;

/**
 * The password prompt for requests that want it typed recently.
 *
 * Mounted once at the app root, above the first-run wizard's gate, so it
 * answers for every screen. It does not know which request asked: the axios
 * interceptor refuses, asks this through src/api/reauth.ts, and sends the
 * request again once the password is confirmed.
 */
export default function ReauthDialog() {
  const { t } = useTranslation();
  const { username } = useAuth();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const settleRef = useRef<((outcome: ReauthOutcome) => void) | null>(null);

  const settle = useCallback((outcome: ReauthOutcome) => {
    settleRef.current?.(outcome);
    settleRef.current = null;
    setOpen(false);
    setPassword('');
    setError(null);
  }, []);

  const cancel = useCallback(() => {
    settle({ ok: false, message: t('reauth.cancelled') });
  }, [settle, t]);

  useEffect(
    () =>
      setReauthHandler(
        () =>
          new Promise<ReauthOutcome>((resolve) => {
            settleRef.current = resolve;
            setPassword('');
            setShowPassword(false);
            setError(null);
            setOpen(true);
          }),
      ),
    [],
  );

  // Signed out while the prompt is up (the token expired, or the password
  // changed elsewhere): the login screen takes over, and the request that
  // asked is not coming back.
  useEffect(() => {
    window.addEventListener(UNAUTHORIZED_EVENT, cancel);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, cancel);
  }, [cancel]);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // The same scrypt check as a login, which on a BeagleBone busy with
      // something else runs past the default 5 s.
      const { data } = await axios.post('/api/auth/confirm', { password }, { timeout: 60_000 });
      localStorage.setItem('token', data.token);
      settle({ ok: true });
    } catch (err: unknown) {
      const response = (err as ConfirmError).response;
      if (response?.status === 403 && response.data?.code === 'reauth_failed') {
        setError(t('reauth.wrong'));
      } else if (response?.status === 429) {
        setError(t('reauth.throttled'));
      } else if (response?.status !== 401) {
        setError(t('reauth.failed'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && cancel()}>
      <DialogContent className="sm:max-w-sm">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <div className="flex items-center gap-3">
              <span className="stg-chip w-10 h-10 rounded-xl flex items-center justify-center shrink-0">
                <FaLock />
              </span>
              <DialogTitle>{t('reauth.title')}</DialogTitle>
            </div>
            <DialogDescription>{t('reauth.intro')}</DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="reauth-password" className="text-sm font-medium">
              {username ? t('reauth.password_for', { username }) : t('reauth.password')}
            </label>
            {/* The login screen's field, eye button and all. */}
            <div className={`input input-lg w-full pr-1 ${error ? 'input-error' : ''}`}>
              <input
                id="reauth-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                autoFocus
                required
                className="grow text-base"
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'reauth-error' : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="btn btn-ghost btn-square btn-sm h-10 w-10"
                aria-label={showPassword ? t('login.hide_password') : t('login.show_password')}
                aria-pressed={showPassword}
                title={showPassword ? t('login.hide_password') : t('login.show_password')}
              >
                {showPassword ? (
                  <FaEyeSlash className="h-5 w-5 opacity-70" />
                ) : (
                  <FaEye className="h-5 w-5 opacity-70" />
                )}
              </button>
            </div>
            {error && (
              <p id="reauth-error" role="alert" className="text-error text-xs">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <button type="button" className="btn btn-ghost max-sm:btn-lg" onClick={cancel}>
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-primary max-sm:btn-lg"
              disabled={submitting || !password}
            >
              {submitting && <span className="loading loading-spinner loading-sm" />}
              {t('reauth.confirm')}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
