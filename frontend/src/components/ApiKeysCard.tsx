import { useCallback, useEffect, useState, FormEvent } from 'react';
import type { AxiosError } from 'axios';
import { FaKey } from 'react-icons/fa';
import axios from '@/api/axios';
import { copyToClipboard } from '@/utils/clipboard';
import { useTranslation } from '../hooks/useTranslation';
import { SettingsCard, FormField, FormActions, NoticeCallout } from './UISettings/ui';
import { LoadingState } from '@/components/ui/LoadingState';

type Scope = 'read' | 'propose' | 'write';

interface ApiKey {
  id: string;
  name: string;
  owner: string;
  scope: Scope;
  created_at: string;
  expires_at: string;
  last_used: string;
}

const SCOPES: Scope[] = ['read', 'propose', 'write'];
// What the server accepts (boneio/core/auth/api_keys.py LIFETIMES_DAYS).
const LIFETIMES = [7, 30, 90, 365];

function errorMessage(err: unknown, fallback: string): string {
  return (err as AxiosError<{ detail?: string }>)?.response?.data?.detail || fallback;
}

function day(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

/**
 * API keys: the credentials an AI agent or a script uses instead of a login.
 *
 * The secret is in the response that makes a key and nowhere else, so it is
 * shown here once, until the card is left. Making a key asks for the password
 * again (the axios interceptor handles that); revoking one does not — taking
 * access away is never the risky direction.
 */
export default function ApiKeysCard() {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [scope, setScope] = useState<Scope>('read');
  const [days, setDays] = useState(30);
  const [isCreating, setIsCreating] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/api-keys');
      setKeys(data.keys ?? []);
      setError(null);
    } catch (err: unknown) {
      setError(errorMessage(err, t('api_keys.load_failed')));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setIsCreating(true);
    try {
      const { data } = await axios.post('/api/api-keys', { name, scope, days });
      setSecret(data.secret);
      setCopied(false);
      setName('');
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err, t('api_keys.create_failed')));
    } finally {
      setIsCreating(false);
    }
  };

  const handleRevoke = async (key: ApiKey) => {
    setError(null);
    setNotice(null);
    try {
      await axios.delete(`/api/api-keys/${encodeURIComponent(key.id)}`);
      setNotice(t('api_keys.revoked', { name: key.name }));
      await load();
    } catch (err: unknown) {
      setError(errorMessage(err, t('api_keys.revoke_failed')));
    } finally {
      setRevoking(null);
    }
  };

  return (
    <>
      <SettingsCard icon={<FaKey />} title={t('api_keys.title')} description={t('api_keys.intro')}>
        {error && <NoticeCallout variant="error" message={error} />}
        {notice && <NoticeCallout variant="success" message={notice} />}
        {secret && (
          <div className="alert alert-warning flex-col items-stretch gap-2">
            <span className="font-medium">{t('api_keys.created_title')}</span>
            <div className="flex gap-2">
              <code className="flex-1 break-all rounded bg-base-100 px-2 py-1 text-xs">{secret}</code>
              <button
                type="button"
                className="btn btn-sm"
                onClick={async () => setCopied(await copyToClipboard(secret))}
              >
                {copied ? t('api_keys.copied') : t('api_keys.copy')}
              </button>
            </div>
            <span className="text-xs">{t('api_keys.mcp_title')}</span>
            <code className="break-all rounded bg-base-100 px-2 py-1 text-xs">
              {`claude mcp add --transport http boneio ${window.location.origin}/api/mcp --header "Authorization: Bearer ${secret}"`}
            </code>
            <span className="text-xs">{t('api_keys.mcp_hint')}</span>
          </div>
        )}
        {isLoading ? (
          <LoadingState className="py-6" />
        ) : keys.length === 0 ? (
          <p className="text-sm text-base-content/60">{t('api_keys.empty')}</p>
        ) : (
          <ul className="stg-inset divide-y divide-base-content/10">
            {keys.map((key) => (
              <li key={key.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">{key.name}</span>
                    <span className="badge badge-ghost badge-sm shrink-0">
                      {t(`api_keys.scope_${key.scope}`)}
                    </span>
                  </div>
                  <div className="text-xs text-base-content/60">
                    {t('api_keys.owner', { owner: key.owner })}
                    {' · '}
                    {t('api_keys.expires', { date: day(key.expires_at) })}
                    {' · '}
                    {key.last_used ? t('api_keys.last_used', { date: day(key.last_used) }) : t('api_keys.never_used')}
                  </div>
                </div>
                {revoking === key.id ? (
                  <div className="flex items-center gap-1">
                    <span className="text-xs">{t('api_keys.revoke_confirm')}</span>
                    <button className="btn btn-error btn-xs" onClick={() => handleRevoke(key)}>
                      {t('api_keys.revoke')}
                    </button>
                    <button className="btn btn-ghost btn-xs" onClick={() => setRevoking(null)}>
                      {t('common.cancel')}
                    </button>
                  </div>
                ) : (
                  <button className="btn btn-ghost btn-xs text-error" onClick={() => setRevoking(key.id)}>
                    {t('api_keys.revoke')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </SettingsCard>

      <form onSubmit={handleCreate}>
        <SettingsCard
          icon={<FaKey />}
          title={t('api_keys.add_title')}
          footer={
            <FormActions>
              <button type="submit" className="btn btn-primary btn-sm gap-2" disabled={isCreating || !name.trim()}>
                {isCreating && <span className="loading loading-spinner loading-xs" />}
                {t('api_keys.create_button')}
              </button>
            </FormActions>
          }
        >
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-3">
            <FormField label={t('api_keys.name')}>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder={t('api_keys.name_placeholder')}
                maxLength={64}
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </FormField>
            <FormField label={t('api_keys.scope')} className="sm:w-40">
              <select
                className="select select-bordered w-full"
                value={scope}
                onChange={(e) => setScope(e.target.value as Scope)}
              >
                {SCOPES.map((s) => (
                  <option key={s} value={s}>{t(`api_keys.scope_${s}`)}</option>
                ))}
              </select>
            </FormField>
            <FormField label={t('api_keys.days')} className="sm:w-32">
              <select
                className="select select-bordered w-full"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              >
                {LIFETIMES.map((d) => (
                  <option key={d} value={d}>{t('api_keys.days_option', { days: d })}</option>
                ))}
              </select>
            </FormField>
          </div>
          <p className="text-xs text-base-content/70">{t(`api_keys.scope_${scope}_hint`)}</p>
        </SettingsCard>
      </form>
    </>
  );
}
