import { useState, useEffect } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import axios from '../api/axios';
import { SettingsCard, FormField } from './UISettings/ui';

interface FramingState {
  restrict: boolean;
  extra_origins: string[];
  value: string;
}

interface FrameAncestorsCardProps {
  onSaved?: () => void;
}

/**
 * Control who may embed this panel in an iframe.
 */
export default function FrameAncestorsCard({ onSaved }: FrameAncestorsCardProps) {
  const { t } = useTranslation();
  const [state, setState] = useState<FramingState | null>(null);
  const [restrict, setRestrict] = useState(false);
  const [origins, setOrigins] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get<FramingState>('/api/security/framing');
        if (cancelled) return;
        setState(res.data);
        setRestrict(res.data.restrict);
        setOrigins(res.data.extra_origins);
      } catch (err: any) {
        if (cancelled) return;
        setError(err.message || 'Failed to load framing settings');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setOriginAt = (idx: number, value: string) => {
    setOrigins(prev => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  };

  const removeOriginAt = (idx: number) => {
    setOrigins(prev => prev.filter((_, i) => i !== idx));
  };

  const cleanOrigins = origins.map(s => s.trim()).filter(Boolean);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await axios.post<FramingState>('/api/security/framing', {
        restrict,
        extra_origins: cleanOrigins,
      });
      setState(res.data);
      setRestrict(res.data.restrict);
      setOrigins(res.data.extra_origins);
      setSaved(true);
      onSaved?.();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (!state) {
    return (
      <SettingsCard title={t('security.framing.title')}>
        <div className="flex justify-center p-4">
          <span className="loading loading-spinner loading-md text-primary" />
        </div>
      </SettingsCard>
    );
  }

  const dirty =
    restrict !== state.restrict ||
    cleanOrigins.join('\u0000') !== state.extra_origins.join('\u0000');

  return (
    <SettingsCard
      title={t('security.framing.title')}
      description={t('security.framing.intro')}
    >
      <div className="space-y-4">
        <label className="flex items-start gap-3 cursor-pointer select-none">
          <input
            type="checkbox"
            className="toggle toggle-primary toggle-sm mt-0.5"
            checked={restrict}
            onChange={e => setRestrict(e.target.checked)}
          />
          <span className="text-sm">
            <span className="font-medium text-base-content block">
              {t('security.framing.restrict')}
            </span>
            <span className="block text-xs text-base-content/60 mt-0.5">
              {t('security.framing.restrict_help')}
            </span>
          </span>
        </label>

        {restrict && (
          <FormField
            label={t('security.framing.extra_origin')}
            help={t('security.framing.extra_origin_help')}
          >
            <div className="space-y-2 mt-1">
              {origins.map((value, index) => (
                <div key={index} className="flex items-center gap-2 max-w-xl">
                  <input
                    id={`frame-extra-origin-${index}`}
                    type="url"
                    className="input input-bordered input-sm flex-1 font-mono text-sm"
                    placeholder="https://homeassistant.local:8123"
                    value={value}
                    onChange={e => setOriginAt(index, e.target.value)}
                  />
                  {origins.length > 1 && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm btn-square text-base-content/60"
                      aria-label={t('security.framing.remove_origin')}
                      onClick={() => removeOriginAt(index)}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                className="btn btn-ghost btn-xs text-primary gap-1"
                onClick={() => setOrigins(prev => [...prev, ''])}
              >
                + {t('security.framing.add_origin')}
              </button>
            </div>
          </FormField>
        )}

        {error && <p className="text-sm text-error font-medium">{error}</p>}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-base-200/80">
          <div className="flex items-center gap-3 flex-wrap">
            <button
              className="btn btn-sm btn-primary"
              onClick={() => void save()}
              disabled={saving || !dirty}
            >
              {saving ? t('security.framing.saving') : t('security.framing.save')}
            </button>
            {saved && (
              <span className="badge badge-warning badge-sm font-medium">
                {t('security.framing.restart_needed')}
              </span>
            )}
          </div>
          <code className="text-xs font-mono text-base-content/50 bg-base-200/50 px-2 py-1 rounded">
            frame-ancestors {state.value}
          </code>
        </div>
      </div>
    </SettingsCard>
  );
}
