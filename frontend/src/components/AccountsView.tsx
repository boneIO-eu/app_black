import { useCallback, useEffect, useState, FormEvent } from 'react';
import type { AxiosError } from 'axios';
import axios from '@/api/axios';
import { useAuth, type Role } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import {
  MIN_PASSWORD_LENGTH,
  PASSWORD_PROBLEM_KEYS,
  checkPassword,
} from '@/utils/passwordPolicy';
import { FaUsers, FaUserPlus } from 'react-icons/fa';
import AccountPasswordDialog from './AccountPasswordDialog';
import AccountDeleteDialog from './AccountDeleteDialog';
import SshPasswordCard from './SshPasswordCard';
import {
  SettingsPage,
  SettingsCard,
  FormField,
  FormActions,
  NoticeCallout,
} from './UISettings/ui';

interface Account {
  username: string;
  role: Role;
  created_at: string;
  updated_at: string;
}

type ApiError = AxiosError<{ detail?: string }>;

function errorMessage(err: unknown, fallback: string): string {
  return (err as ApiError)?.response?.data?.detail || fallback;
}

/**
 * Account management, for administrators.
 *
 * A section of the Settings editor, listed alongside the other tools. It is
 * not schema-driven — accounts live in users.json, not config.yaml — so
 * UISettings renders it on its own branch, without the save, restore and
 * YAML-preview header the config sections carry. Same arrangement as the
 * binding matrix. The Web server section links here, from where the old
 * web.auth password fields used to be.
 *
 * Everything here is also enforced server-side — the middleware refuses a
 * viewer's request whatever this component renders — so the UI's job is to not
 * offer actions that would fail, not to be the boundary.
 */
export default function AccountsView() {
  const { t } = useTranslation();
  const { username: me, isAdmin } = useAuth();

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<Role>('viewer');
  const [isCreating, setIsCreating] = useState(false);

  // Which account a dialog is open for; null when none is.
  const [passwordFor, setPasswordFor] = useState<string | null>(null);
  const [deleteFor, setDeleteFor] = useState<string | null>(null);

  // The backend applies the same rules, so this only means the admin hears
  // about a doomed password before submitting rather than after.
  const newPasswordIssue = newPassword ? checkPassword(newPassword, newUsername) : null;
  const newPasswordProblem = newPasswordIssue
    ? t(PASSWORD_PROBLEM_KEYS[newPasswordIssue], { min: MIN_PASSWORD_LENGTH })
    : null;

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/accounts');
      setAccounts(data.accounts ?? []);
      setError(null);
    } catch (err: unknown) {
      setError(errorMessage(err, t('accounts.load_failed')));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // Non-admins never reach the spinner — the component returns the
    // "admin only" notice above it — so there is nothing to settle here.
    if (isAdmin) void load();
  }, [isAdmin, load]);

  const handleCreate = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setIsCreating(true);
    try {
      await axios.post('/api/accounts', {
        username: newUsername,
        password: newPassword,
        role: newRole,
      });
      setNewUsername('');
      setNewPassword('');
      setNewRole('viewer');
      setNotice(t('accounts.created'));
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err, t('accounts.create_failed')));
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async (username: string) => {
    setError(null);
    setNotice(null);
    try {
      await axios.delete(`/api/accounts/${encodeURIComponent(username)}`);
      setNotice(t('accounts.deleted', { username }));
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err, t('accounts.delete_failed')));
    } finally {
      setDeleteFor(null);
    }
  };

  const handleRoleChange = async (account: Account, role: Role) => {
    setError(null);
    setNotice(null);
    try {
      await axios.put(`/api/accounts/${encodeURIComponent(account.username)}/role`, { role });
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err, t('accounts.role_failed')));
      await load();
    }
  };

  const handlePasswordChanged = (username: string) => {
    setPasswordFor(null);
    setError(null);
    setNotice(t('accounts.password_reset', { username }));
  };

  const isSelf = (username: string) => username.toLowerCase() === (me ?? '').toLowerCase();

  if (!isAdmin) {
    return (
      <SettingsPage width="wide">
        <NoticeCallout variant="warning" message={t('accounts.admin_only')} />
      </SettingsPage>
    );
  }

  return (
    <SettingsPage width="wide">
      {error && <NoticeCallout variant="error" message={error} />}
      {notice && <NoticeCallout variant="success" message={notice} />}

      {/* Accounts list */}
      <SettingsCard icon={<FaUsers />} title={t('accounts.title')}>
        {isLoading ? (
          <div className="flex justify-center py-6">
            <span className="loading loading-spinner loading-md text-primary" />
          </div>
        ) : (
          // A list, not a table: three columns of controls do not fit a phone,
          // and a table that scrolls sideways hides the delete button off-screen.
          <ul className="stg-inset divide-y divide-base-content/10">
            {accounts.map((account) => {
              const isMe = isSelf(account.username);
              return (
                <li
                  key={account.username}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5"
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className="font-medium font-mono truncate">{account.username}</span>
                    {isMe && (
                      <span className="badge badge-ghost badge-xs shrink-0">
                        {t('accounts.you')}
                      </span>
                    )}
                  </div>
                  <select
                    className="select select-xs select-bordered w-auto"
                    aria-label={t('accounts.role')}
                    value={account.role}
                    disabled={isMe}
                    onChange={(e) => handleRoleChange(account, e.target.value as Role)}
                  >
                    <option value="admin">{t('accounts.role_admin')}</option>
                    <option value="viewer">{t('accounts.role_viewer')}</option>
                  </select>
                  <div className="flex justify-end gap-1 w-full sm:w-auto">
                    <button
                      className="btn btn-ghost btn-xs"
                      onClick={() => {
                        setNotice(null);
                        setPasswordFor(account.username);
                      }}
                    >
                      {t('accounts.reset_password')}
                    </button>
                    <button
                      className="btn btn-ghost btn-xs text-error"
                      disabled={isMe}
                      onClick={() => setDeleteFor(account.username)}
                    >
                      {t('accounts.delete')}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </SettingsCard>

      {/* Add account */}
      <form onSubmit={handleCreate}>
        <SettingsCard
          icon={<FaUserPlus />}
          title={t('accounts.add_title')}
          description={t('accounts.add_intro')}
          footer={
            <FormActions>
              <button
                type="submit"
                className="btn btn-primary btn-sm gap-2"
                disabled={isCreating || !newUsername || !newPassword || !!newPasswordProblem}
              >
                {isCreating && <span className="loading loading-spinner loading-xs" />}
                {t('accounts.add_button')}
              </button>
            </FormActions>
          }
        >
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-3">
            <FormField label={t('accounts.username')}>
              <input
                type="text"
                className="input input-bordered w-full font-mono"
                placeholder={t('accounts.username')}
                autoComplete="off"
                required
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
              />
            </FormField>

            <FormField
              label={t('accounts.password')}
              error={newPasswordProblem || undefined}
            >
              <input
                type="password"
                className={`input input-bordered w-full font-mono ${newPasswordProblem ? 'input-error' : ''}`}
                placeholder={t('accounts.password')}
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                aria-invalid={newPasswordProblem ? true : undefined}
                aria-describedby={newPasswordProblem ? 'accounts-password-error' : undefined}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </FormField>

            <FormField label={t('accounts.role')} className="sm:w-40">
              <select
                className="select select-bordered w-full"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as Role)}
              >
                <option value="viewer">{t('accounts.role_viewer')}</option>
                <option value="admin">{t('accounts.role_admin')}</option>
              </select>
            </FormField>
          </div>
        </SettingsCard>
      </form>

      {/* Not a panel account: the Linux login behind SSH and sudo. */}
      <SshPasswordCard />

      {/* Keyed by account: a fresh form, nothing typed for the last one. */}
      <AccountPasswordDialog
        key={passwordFor ?? ''}
        username={passwordFor}
        isSelf={passwordFor !== null && isSelf(passwordFor)}
        onClose={() => setPasswordFor(null)}
        onChanged={handlePasswordChanged}
      />
      <AccountDeleteDialog
        username={deleteFor}
        onClose={() => setDeleteFor(null)}
        onConfirm={handleDelete}
      />
    </SettingsPage>
  );
}
