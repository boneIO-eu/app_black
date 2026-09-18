import { useCallback, useEffect, useState } from 'react';
import { FaCheck, FaPlus, FaSpinner, FaTrash } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import { FormField, NoticeCallout } from '../ui';

interface NtpInfo {
  enabled: boolean;
  synchronized: boolean;
  servers: string[];
  /** 'boneio' when we wrote a drop-in, 'system' for distribution defaults. */
  source: 'boneio' | 'system' | 'unknown';
  max_servers: number;
  /** What the clock is actually following right now, per timedatectl. */
  server_name?: string;
  server_address?: string;
}

/**
 * An IPv4 address, an IPv6 address, or a DNS name.
 *
 * This mirrors the check inside boneio-system and exists only to fail fast with
 * a clear message. The helper's copy is the one that matters: the value ends up
 * in a file systemd parses as root, so it is validated on the root side of the
 * boundary, not here.
 */
function isUsableServer(value: string): boolean {
  const entry = value.trim();
  if (!entry || entry.length > 253) return false;
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(entry)) {
    return entry.split('.').every((part) => Number(part) <= 255);
  }
  if (entry.includes(':')) {
    // Leave IPv6 to the backend; only reject what could break out of the line.
    return /^[0-9a-fA-F:.]+$/.test(entry);
  }
  return /^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$/.test(entry);
}

/** Pull the backend's `detail` out of an axios error, falling back to its message. */
function errorDetail(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const response = (err as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    const message = (err as { message?: unknown }).message;
    if (typeof message === 'string') return message;
  }
  return '';
}

interface NtpServersFieldProps {
  /** Called after a successful save so the parent can refresh its own status. */
  onChanged?: () => void;
}

/**
 * Choose where the clock gets its time from.
 *
 * The device has no battery-backed RTC, so after a power cut it boots with a
 * meaningless date until something corrects it. On an installation with no
 * route to the internet the public pool never answers and nothing ever does —
 * which is why pointing this at a server on the local network is a setting and
 * not a nicety.
 */
export default function NtpServersField({ onChanged }: NtpServersFieldProps) {
  const { t } = useTranslation();
  const [info, setInfo] = useState<NtpInfo | null>(null);
  const [useCustom, setUseCustom] = useState(false);
  const [servers, setServers] = useState<string[]>(['']);
  const [isSaving, setIsSaving] = useState(false);
  const [result, setResult] = useState<{ status: string; message: string } | null>(null);

  const fetchNtp = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/ntp');
      setInfo(data);
      const configured: string[] = data.servers || [];
      setUseCustom(configured.length > 0);
      setServers(configured.length > 0 ? configured : ['']);
    } catch (err) {
      console.error('Failed to fetch NTP info:', err);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchNtp();
  }, [fetchNtp]);

  const maxServers = info?.max_servers ?? 5;
  const filled = servers.map((s) => s.trim()).filter(Boolean);
  const invalid = filled.filter((s) => !isUsableServer(s));
  const duplicated = filled.length !== new Set(filled).size;
  const canSave =
    !isSaving && invalid.length === 0 && !duplicated && (!useCustom || filled.length > 0);

  const updateServer = (index: number, value: string) => {
    setServers((current) => current.map((entry, i) => (i === index ? value : entry)));
  };

  const removeServer = (index: number) => {
    setServers((current) => {
      const next = current.filter((_, i) => i !== index);
      return next.length > 0 ? next : [''];
    });
  };

  const save = async () => {
    setIsSaving(true);
    setResult(null);
    try {
      // An empty list is the wire format for "go back to the distribution
      // defaults" — the backend removes the drop-in rather than writing one.
      await axios.post('/api/ntp', { servers: useCustom ? filled : [] });
      setResult({
        status: 'success',
        message: useCustom
          ? t('timezone.ntp_servers_saved')
          : t('timezone.ntp_servers_defaults_restored'),
      });
      // timesyncd needs a moment to pick a server before the status is worth
      // reading back.
      setTimeout(() => {
        void fetchNtp();
        onChanged?.();
      }, 2000);
    } catch (err: unknown) {
      setResult({
        status: 'error',
        message: errorDetail(err) || t('timezone.ntp_servers_failed'),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const activeServer = info?.server_name || info?.server_address;

  return (
    <FormField
      label={t('timezone.ntp_servers')}
      help={t('timezone.ntp_servers_hint')}
      className="max-w-xl"
    >
      <div className="space-y-3">
        <div className="flex flex-wrap gap-4">
          <label className="label cursor-pointer gap-2 py-0">
            <input
              type="radio"
              className="radio radio-sm"
              checked={!useCustom}
              onChange={() => setUseCustom(false)}
            />
            <span className="label-text text-sm">{t('timezone.ntp_servers_default')}</span>
          </label>
          <label className="label cursor-pointer gap-2 py-0">
            <input
              type="radio"
              className="radio radio-sm"
              checked={useCustom}
              onChange={() => setUseCustom(true)}
            />
            <span className="label-text text-sm">{t('timezone.ntp_servers_custom')}</span>
          </label>
        </div>

        {useCustom && (
          <div className="space-y-2">
            {servers.map((server, index) => {
              const trimmed = server.trim();
              const bad = trimmed.length > 0 && !isUsableServer(trimmed);
              return (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    className={`input input-bordered input-sm w-full font-mono ${bad ? 'input-error' : ''}`}
                    placeholder={t('timezone.ntp_servers_placeholder')}
                    value={server}
                    onChange={(e) => updateServer(index, e.target.value)}
                    spellCheck={false}
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square text-error"
                    onClick={() => removeServer(index)}
                    title={t('timezone.ntp_servers_remove')}
                    disabled={servers.length === 1 && !trimmed}
                  >
                    <FaTrash className="w-3 h-3" />
                  </button>
                </div>
              );
            })}

            {servers.length < maxServers && (
              <button
                type="button"
                className="btn btn-ghost btn-xs gap-1"
                onClick={() => setServers((current) => [...current, ''])}
              >
                <FaPlus className="w-2.5 h-2.5" />
                {t('timezone.ntp_servers_add')}
              </button>
            )}

            {invalid.length > 0 && (
              <p className="text-xs text-error">
                {t('timezone.ntp_servers_invalid')}: {invalid.join(', ')}
              </p>
            )}
            {duplicated && (
              <p className="text-xs text-error">{t('timezone.ntp_servers_duplicate')}</p>
            )}
          </div>
        )}

        {activeServer && (
          <p className="text-xs opacity-60">
            {t('timezone.ntp_servers_active')}:{' '}
            <span className="font-mono">{activeServer}</span>
          </p>
        )}

        <button className="btn btn-primary btn-sm gap-2" onClick={save} disabled={!canSave}>
          {isSaving ? (
            <>
              <FaSpinner className="animate-spin" />
              {t('timezone.saving')}
            </>
          ) : (
            <>
              <FaCheck />
              {t('timezone.ntp_servers_save')}
            </>
          )}
        </button>

        {result && (
          <NoticeCallout
            variant={result.status === 'success' ? 'success' : 'error'}
            message={result.message}
          />
        )}
      </div>
    </FormField>
  );
}
