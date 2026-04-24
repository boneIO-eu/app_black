import React, { useState } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaLock,
  FaPlay,
  FaSpinner,
} from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { useMigrations } from '@/hooks/useMigrations';

/**
 * SystemState sub-section that displays pending system migrations and
 * allows the user to bootstrap the ``boneio-migrate`` helper (one-time
 * sudo password) and trigger migration apply.
 */
const MigrationsSection: React.FC = () => {
  const { t } = useTranslation();
  const { status, loading, refresh } = useMigrations(10000);
  const [password, setPassword] = useState<string>('');
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [message, setMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState<boolean>(false);

  const setFeedback = (msg: string, error: boolean) => {
    setMessage(msg);
    setIsError(error);
  };

  const handleBootstrap = async () => {
    if (!password) {
      setFeedback(t('migrations.password_required'), true);
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const { data } = await axios.post('/api/migrations/bootstrap', { password });
      setFeedback(
        data.message || t('migrations.bootstrap_success'),
        false,
      );
      setPassword('');
      await refresh();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
      setFeedback(t('migrations.bootstrap_failed', { error: detail }), true);
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const { data } = await axios.post('/api/migrations/apply');
      setFeedback(data.message || t('migrations.apply_started'), false);
      setTimeout(refresh, 2000);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
      setFeedback(t('migrations.apply_failed', { error: detail }), true);
    } finally {
      setBusy(false);
    }
  };

  if (loading && !status) {
    return (
      <div className="card bg-base-200">
        <div className="card-body">
          <FaSpinner className="animate-spin" />
        </div>
      </div>
    );
  }

  if (!status) return null;

  // Hide entirely when nothing to do
  const nothingToDo =
    status.pending_count === 0 && !status.bootstrap_required && status.status === 'ok';

  if (nothingToDo && status.applied.length === 0) return null;

  return (
    <div
      id="migrations"
      className={`card ${
        status.bootstrap_required
          ? 'bg-warning/10 border border-warning'
          : status.pending_count > 0
            ? 'bg-info/10 border border-info'
            : 'bg-base-200'
      }`}
    >
      <div className="card-body">
        <h3 className="card-title">
          {status.bootstrap_required ? (
            <FaLock className="text-warning" />
          ) : status.pending_count > 0 ? (
            <FaPlay className="text-info" />
          ) : (
            <FaCheck className="text-success" />
          )}
          {t('migrations.title')}
        </h3>

        {/* Status summary */}
        <div className="text-sm opacity-80">
          {status.bootstrap_required && (
            <p className="mb-2">{t('migrations.explain_bootstrap')}</p>
          )}
          {!status.bootstrap_required && status.pending_count > 0 && (
            <p className="mb-2">
              {t('migrations.explain_pending', { count: status.pending_count })}
            </p>
          )}
          {nothingToDo && status.applied.length > 0 && (
            <p className="mb-2">{t('migrations.all_applied')}</p>
          )}
        </div>

        {/* Pending list */}
        {status.pending.length > 0 && (
          <div className="mt-2">
            <p className="text-sm font-medium">{t('migrations.pending_list')}:</p>
            <ul className="list-disc list-inside text-sm">
              {status.pending.map((m) => (
                <li key={m.version}>
                  <span className="font-mono">{m.version}</span>
                  {m.description && <span className="opacity-70"> — {m.description}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Applied list */}
        {status.applied.length > 0 && (
          <details className="mt-2">
            <summary className="text-sm cursor-pointer opacity-70">
              {t('migrations.applied_count', { count: status.applied.length })}
            </summary>
            <ul className="list-disc list-inside text-sm mt-1 opacity-70">
              {status.applied.map((v) => (
                <li key={v} className="font-mono">
                  {v}
                </li>
              ))}
            </ul>
          </details>
        )}

        {/* Last error */}
        {status.last_error && (
          <div className="alert alert-error mt-2">
            <FaExclamationTriangle />
            <span className="font-mono text-xs">{status.last_error}</span>
          </div>
        )}

        {/* Bootstrap form */}
        {status.bootstrap_required && (
          <div className="mt-5 space-y-3 pl-1">
            <div className="flex items-start gap-2 text-sm text-warning-content/80 bg-warning/10 border border-warning/30 rounded-lg p-3">
              <FaExclamationTriangle className="mt-0.5 shrink-0" />
              <div>
                <p className="font-medium">{t('migrations.bootstrap_title')}</p>
                <p className="opacity-80">{t('migrations.bootstrap_description')}</p>
              </div>
            </div>

            <form
              autoComplete="off"
              onSubmit={(e) => {
                e.preventDefault();
                if (!busy && password) handleBootstrap();
              }}
              className="flex flex-col gap-4 mt-2"
            >
              {/* Honeypot fields to discourage password manager autofill */}
              <input
                type="text"
                name="username"
                autoComplete="username"
                className="hidden"
                tabIndex={-1}
                aria-hidden="true"
              />
              <input
                type="password"
                name="password"
                autoComplete="new-password"
                className="hidden"
                tabIndex={-1}
                aria-hidden="true"
              />

              <div className="form-control min-w-0 max-w-lg">
                <label className="label pt-0 mr-2">
                  <span className="label-text font-medium">
                    {t('migrations.sudo_password_label')}
                  </span>
                </label>
                <div className="join">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="input input-bordered join-item flex-1 min-w-0"
                    placeholder={t('migrations.sudo_password_placeholder')}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="off"
                    spellCheck={false}
                    name="boneio-migrate-sudo"
                    data-lpignore="true"
                    data-1p-ignore="true"
                    data-form-type="other"
                    disabled={busy}
                  />
                  <button
                    type="button"
                    className="btn join-item"
                    onClick={() => setShowPassword((v) => !v)}
                    disabled={busy}
                  >
                    {showPassword ? t('migrations.hide') : t('migrations.show')}
                  </button>
                </div>
                <label className="label pt-2">
                  <span className="label-text-alt opacity-70">
                    {t('migrations.password_hint')}
                  </span>
                </label>
              </div>

              <div className="card-actions justify-end mt-2">
                <button
                  type="submit"
                  className="btn btn-warning"
                  disabled={busy || !password}
                >
                  {busy ? <FaSpinner className="animate-spin" /> : <FaLock />}
                  {t('migrations.bootstrap_button')}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Apply button when helper installed and pending */}
        {!status.bootstrap_required && status.pending_count > 0 && (
          <div className="card-actions justify-end mt-4">
            <button
              className="btn btn-info"
              onClick={handleApply}
              disabled={busy}
            >
              {busy ? <FaSpinner className="animate-spin" /> : <FaPlay />}
              {t('migrations.apply_button')}
            </button>
          </div>
        )}

        {/* Feedback */}
        {message && (
          <div
            className={`alert ${isError ? 'alert-error' : 'alert-success'} mt-3`}
          >
            {isError ? <FaExclamationTriangle /> : <FaCheck />}
            <span>{message}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default MigrationsSection;
