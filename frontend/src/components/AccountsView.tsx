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

  const handleDelete = async (account: Account) => {
    if (!window.confirm(t('accounts.confirm_delete', { username: account.username }))) return;
    setError(null);
    setNotice(null);
    try {
      await axios.delete(`/api/accounts/${encodeURIComponent(account.username)}`);
      setNotice(t('accounts.deleted', { username: account.username }));
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err, t('accounts.delete_failed')));
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

  const handleReset = async (account: Account) => {
    const password = window.prompt(
      t('accounts.prompt_new_password', { username: account.username }),
    );
    if (!password) return;
    setError(null);
    setNotice(null);

    // A prompt has nowhere to put inline feedback, so the policy is checked
    // here; otherwise the only answer is the backend's untranslated detail.
    const problem = checkPassword(password, account.username);
    if (problem) {
      setError(t(PASSWORD_PROBLEM_KEYS[problem], { min: MIN_PASSWORD_LENGTH }));
      return;
    }
    try {
      await axios.put(`/api/accounts/${encodeURIComponent(account.username)}/password`, {
        password,
      });
      setNotice(t('accounts.password_reset', { username: account.username }));
    } catch (err: unknown) {
      setError(errorMessage(err, t('accounts.password_failed')));
    }
  };

  if (!isAdmin) {
    return (
      <div className="alert alert-warning text-sm">
        <span>{t('accounts.admin_only')}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && <div className="alert alert-error text-sm"><span>{error}</span></div>}
      {notice && <div className="alert alert-success text-sm"><span>{notice}</span></div>}

      {/* Accounts List Card */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6 space-y-4">
          <h3 className="text-base font-semibold">{t('accounts.title')}</h3>

          {isLoading ? (
            <div className="flex justify-center py-6">
              <span className="loading loading-spinner loading-md text-primary" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>{t('accounts.username')}</th>
                    <th>{t('accounts.role')}</th>
                    <th className="text-right">{t('accounts.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((account) => {
                    const isMe = account.username.toLowerCase() === (me ?? '').toLowerCase();
                    return (
                      <tr key={account.username}>
                        <td>
                          <span className="font-medium font-mono">{account.username}</span>
                          {isMe && (
                            <span className="ml-2 badge badge-ghost badge-xs">
                              {t('accounts.you')}
                            </span>
                          )}
                        </td>
                        <td>
                          <select
                            className="select select-xs select-bordered"
                            value={account.role}
                            disabled={isMe}
                            onChange={(e) => handleRoleChange(account, e.target.value as Role)}
                          >
                            <option value="admin">{t('accounts.role_admin')}</option>
                            <option value="viewer">{t('accounts.role_viewer')}</option>
                          </select>
                        </td>
                        <td className="text-right whitespace-nowrap">
                          <button
                            className="btn btn-outline btn-xs"
                            onClick={() => handleReset(account)}
                          >
                            {t('accounts.reset_password')}
                          </button>
                          <button
                            className="btn btn-outline btn-error btn-xs ml-2"
                            disabled={isMe}
                            onClick={() => handleDelete(account)}
                          >
                            {t('accounts.delete')}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Add Account Card */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6 space-y-4">
          <form className="space-y-4" onSubmit={handleCreate}>
            <div>
              <h3 className="text-base font-semibold">{t('accounts.add_title')}</h3>
              <p className="text-sm opacity-70 mt-1">{t('accounts.add_intro')}</p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                className="input input-bordered input-sm flex-1 font-mono"
                placeholder={t('accounts.username')}
                autoComplete="off"
                required
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
              />
              <input
                type="password"
                className={`input input-bordered input-sm flex-1 font-mono ${newPasswordProblem ? 'input-error' : ''}`}
                placeholder={t('accounts.password')}
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                aria-invalid={newPasswordProblem ? true : undefined}
                aria-describedby={newPasswordProblem ? 'accounts-password-error' : undefined}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <select
                className="select select-bordered select-sm"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as Role)}
              >
                <option value="viewer">{t('accounts.role_viewer')}</option>
                <option value="admin">{t('accounts.role_admin')}</option>
              </select>
            </div>

            {newPasswordProblem && (
              <p id="accounts-password-error" className="text-error text-xs">
                {newPasswordProblem}
              </p>
            )}

            <div>
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={isCreating || !newUsername || !newPassword || !!newPasswordProblem}
              >
                {isCreating && <span className="loading loading-spinner loading-xs" />}
                {t('accounts.add_button')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
