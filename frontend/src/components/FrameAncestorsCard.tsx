import { useCallback, useEffect, useState } from 'react';
import type { AxiosError } from 'axios';
import api from '@/api/axios';
import { useTranslation } from '../hooks/useTranslation';

/**
 * Who may embed this panel in a frame.
 *
 * The CSP directive behind this is a trap to type by hand: `self` without its
 * quotes is a host name, a trailing slash makes an origin invalid, and either
 * mistake fails silently in a way only a browser console reveals. So the card
 * asks the two questions that matter and lets the backend assemble the value.
 *
 * The default, `'self'`, is what the boneIO Black Home Assistant add-on needs:
 * it proxies each device, so the framed page is served on Home Assistant's own
 * origin and is same-origin with the dashboard framing it. The setup that
 * needs more is a dashboard pointing an iframe card straight at the device —
 * that one names its Home Assistant address here.
 */

interface FrameAncestorsState {
  restrict: boolean;
  extra_origins: string[];
  value: string;
  configured: boolean;
  default: string;
}

function errorMessage(err: unknown, fallback: string): string {
  return (err as AxiosError<{ detail?: string }>)?.response?.data?.detail || fallback;
}

export default function FrameAncestorsCard({ onSaved }: { onSaved?: () => void }) {
  const { t } = useTranslation();

  const [state, setState] = useState<FrameAncestorsState | null>(null);
  const [restrict, setRestrict] = useState(true);
  const [origin, setOrigin] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<FrameAncestorsState>('/api/security/frame-ancestors');
      setState(data);
      setRestrict(data.restrict);
      setOrigin(data.extra_origins[0] ?? '');
    } catch (err) {
      setError(errorMessage(err, t('security.framing.load_failed')));
    }
  }, [t]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const { data } = await api.put<FrameAncestorsState>('/api/security/frame-ancestors', {
        restrict,
        extra_origins: restrict && origin.trim() ? [origin.trim()] : [],
      });
      setState(data);
      setSaved(true);
      onSaved?.();
    } catch (err) {
      setError(errorMessage(err, t('security.framing.save_failed')));
    } finally {
      setSaving(false);
    }
  };

  if (!state) {
    return (
      <div className="border border-base-300 rounded-xl p-4">
        {error ? (
          <p className="text-sm text-error">{error}</p>
        ) : (
          <span className="loading loading-spinner loading-sm" />
        )}
      </div>
    );
  }

  const dirty =
    restrict !== state.restrict || origin.trim() !== (state.extra_origins[0] ?? '');

  return (
    <div className="border border-base-300 rounded-xl p-4 space-y-3">
      <div>
        <h3 className="font-semibold">{t('security.framing.title')}</h3>
        <p className="text-sm opacity-70 mt-1 max-w-3xl">{t('security.framing.intro')}</p>
      </div>

      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          className="toggle toggle-primary mt-0.5"
          checked={restrict}
          onChange={e => setRestrict(e.target.checked)}
        />
        <span className="text-sm">
          <span className="font-medium">{t('security.framing.restrict')}</span>
          <span className="block opacity-70">{t('security.framing.restrict_help')}</span>
        </span>
      </label>

      {restrict && (
        <div>
          <label htmlFor="frame-extra-origin" className="block text-sm font-medium">
            {t('security.framing.extra_origin')}
          </label>
          <p className="text-xs opacity-70 mt-1 max-w-3xl">
            {t('security.framing.extra_origin_help')}
          </p>
          <input
            id="frame-extra-origin"
            type="url"
            className="input input-bordered w-full max-w-md mt-2"
            placeholder="https://homeassistant.local:8123"
            value={origin}
            onChange={e => setOrigin(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      )}

      {error && <p className="text-sm text-error">{error}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="btn btn-sm btn-primary"
          onClick={() => void save()}
          disabled={saving || !dirty}
        >
          {saving ? t('security.framing.saving') : t('security.framing.save')}
        </button>
        {saved && (
          <span className="text-sm text-warning">{t('security.framing.restart_needed')}</span>
        )}
        <code className="text-xs opacity-60 break-all">frame-ancestors {state.value}</code>
      </div>
    </div>
  );
}
