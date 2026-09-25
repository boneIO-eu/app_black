import React, { useState } from 'react';
import {
  FaCheck,
  FaLock,
  FaPlay,
  FaSpinner,
  FaChevronDown,
  FaChevronRight,
  FaExternalLinkAlt,
} from 'react-icons/fa';
import axios from '@/api/axios';
import type { AxiosError } from 'axios';
import { useTranslation } from '@/hooks/useTranslation';
import { useMigrations, type AppliedMigration } from '@/hooks/useMigrations';
import {
  SettingsPage,
  SettingsCard,
  FormField,
  FormActions,
  CardSection,
  NoticeCallout,
  EmptyState,
} from './ui';

type ApiError = AxiosError<{ detail?: string }>;

const GITHUB_BASE = 'https://github.com/boneIO-eu/app_black/blob/dev-debian13';

/**
 * Convert a Python module name like 'boneio.migrations.versions.v1_3_0_baseline'
 * to a GitHub source URL.
 */
function moduleToGithubUrl(moduleName: string): string | null {
  if (!moduleName) return null;
  const filePath = moduleName.replace(/\./g, '/') + '.py';
  return `${GITHUB_BASE}/${filePath}`;
}

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
  const [showApplied, setShowApplied] = useState<boolean>(false);

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
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      const detail = apiErr?.response?.data?.detail || apiErr?.message || 'Unknown error';
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
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      const detail = apiErr?.response?.data?.detail || apiErr?.message || 'Unknown error';
      setFeedback(t('migrations.apply_failed', { error: detail }), true);
    } finally {
      setBusy(false);
    }
  };

  if (loading && !status) {
    return (
      <SettingsPage>
        <SettingsCard>
          <div className="flex items-center gap-2.5 text-sm text-base-content/60">
            <FaSpinner className="animate-spin" />
            <span>{t('migrations.title')}…</span>
          </div>
        </SettingsCard>
      </SettingsPage>
    );
  }

  const nothingToDo =
    status !== null &&
    status.pending_count === 0 &&
    !status.bootstrap_required &&
    status.status === 'ok';

  // This used to render nothing at all in these cases, which was right when it
  // was one card among ten on the System page: a device with nothing to
  // migrate simply did not show it. It has its own entry in the settings tree
  // now, and an entry that opens onto a blank page reads as a broken page.
  if (!status || (nothingToDo && status.applied.length === 0)) {
    return (
      <SettingsPage>
        <SettingsCard>
          <EmptyState
            icon={<FaCheck className="text-success" />}
            title={t('migrations.nothing_to_do')}
          />
        </SettingsCard>
      </SettingsPage>
    );
  }

  return (
    <SettingsPage width="wide">
      <SettingsCard
        variant={status.bootstrap_required || status.pending_count > 0 ? 'accent' : 'default'}
        className="scroll-mt-4"
        icon={
          status.bootstrap_required ? (
            <FaLock />
          ) : status.pending_count > 0 ? (
            <FaPlay />
          ) : (
            <FaCheck />
          )
        }
        title={t('migrations.title')}
        description={
          status.bootstrap_required
            ? t('migrations.explain_bootstrap')
            : status.pending_count > 0
              ? t('migrations.explain_pending', { count: status.pending_count })
              : status.applied.length > 0
                ? t('migrations.all_applied')
                : undefined
        }
        action={
          nothingToDo && status.applied.length > 0 ? (
            <button
              className="btn btn-ghost btn-sm gap-2"
              onClick={() => setShowApplied(!showApplied)}
            >
              {showApplied ? <FaChevronDown /> : <FaChevronRight />}
              {t('migrations.applied_count', { count: status.applied.length })}
            </button>
          ) : undefined
        }
        footer={
          !status.bootstrap_required && status.pending_count > 0 ? (
            <FormActions>
              <button className="btn btn-primary btn-sm gap-2" onClick={handleApply} disabled={busy}>
                {busy ? <FaSpinner className="animate-spin" /> : <FaPlay />}
                {t('migrations.apply_button')}
              </button>
            </FormActions>
          ) : undefined
        }
      >
      <div id="migrations" className="space-y-4">
        {/* Pending list */}
        {status.pending.length > 0 && (
          <CardSection title={t('migrations.pending_list')}>
            <div className="stg-inset overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>{t('software_update.version')}</th>
                    <th>{t('migrations.description') || 'Description'}</th>
                  </tr>
                </thead>
                <tbody>
                  {status.pending.map((m) => (
                    <tr key={m.version}>
                      <td className="font-mono">{m.version}</td>
                      <td className="opacity-70">{m.description || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardSection>
        )}

        {/* Applied list (collapsible) */}
        {showApplied && status.applied.length > 0 && (
          <CardSection title={t('migrations.applied_count', { count: status.applied.length })}>
            <div className="stg-inset overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>{t('software_update.version')}</th>
                    <th>{t('migrations.description') || 'Description'}</th>
                    <th>{t('migrations.source') || 'Source'}</th>
                  </tr>
                </thead>
                <tbody>
                  {status.applied.map((m: AppliedMigration) => {
                    const githubUrl = moduleToGithubUrl(m.module_name);
                    return (
                      <tr key={m.version}>
                        <td className="font-mono">{m.version}</td>
                        <td className="opacity-70">{m.description || '—'}</td>
                        <td>
                          {githubUrl && (
                            <a
                              href={githubUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn btn-ghost btn-xs gap-1"
                            >
                              <FaExternalLinkAlt className="h-3 w-3" />
                              {t('migrations.source') || 'Source'}
                            </a>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardSection>
        )}

        {/* Last error */}
        {status.last_error && (
          <NoticeCallout
            variant="error"
            message={<span className="font-mono text-xs break-all">{status.last_error}</span>}
          />
        )}

        {/* Bootstrap form */}
        {status.bootstrap_required && (
          <div className="space-y-3">
            <NoticeCallout
              variant="warning"
              title={t('migrations.bootstrap_title')}
              message={t('migrations.bootstrap_description')}
            />

            <form
              autoComplete="off"
              onSubmit={(e) => {
                e.preventDefault();
                if (!busy && password) handleBootstrap();
              }}
              className="space-y-4"
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

              <FormField
                label={t('migrations.sudo_password_label')}
                help={t('migrations.password_hint')}
                className="max-w-lg"
              >
                <div className="join w-full">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="input input-bordered join-item flex-1 min-w-0 font-mono"
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
                    className="btn btn-neutral join-item"
                    onClick={() => setShowPassword((v) => !v)}
                    disabled={busy}
                  >
                    {showPassword ? t('migrations.hide') : t('migrations.show')}
                  </button>
                </div>
              </FormField>

              <FormActions>
                <button
                  type="submit"
                  className="btn btn-warning btn-sm gap-2"
                  disabled={busy || !password}
                >
                  {busy ? <FaSpinner className="animate-spin" /> : <FaLock />}
                  {t('migrations.bootstrap_button')}
                </button>
              </FormActions>
            </form>
          </div>
        )}

        {/* Feedback */}
        {message && (
          <NoticeCallout variant={isError ? 'error' : 'success'} message={message} />
        )}
      </div>
      </SettingsCard>
    </SettingsPage>
  );
};

export default MigrationsSection;
