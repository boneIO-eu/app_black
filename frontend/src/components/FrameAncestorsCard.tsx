import { useState, useEffect } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import axios from '../api/axios';
import { FaObjectGroup } from 'react-icons/fa';
import { SettingsCard, FormField, FormActions, ToggleRow } from './UISettings/ui';

interface FramingState {
  restrict: boolean;
  extra_origins: string[];
  value: string;
}

interface FrameAncestorsCardProps {
  onSaved?: () => void;
}

/**
 * Accept only a payload that actually looks like a framing state.
 *
 * The endpoint used to be addressed by a name the backend does not serve, and
 * the dev server answers an unknown /api path with index.html at status 200 —
 * so `extra_origins` arrived as undefined, `origins.map` threw during render,
 * and the whole security page went blank. The URL is fixed above; this keeps a
 * surprising answer from taking the page down again.
 */
function normalize(raw: unknown): FramingState {
  const data = (raw ?? {}) as Partial<FramingState>;
  return {
    restrict: typeof data.restrict === 'boolean' ? data.restrict : true,
    extra_origins: Array.isArray(data.extra_origins) ? data.extra_origins : [],
    value: typeof data.value === 'string' ? data.value : '',
  };
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
        const res = await axios.get<FramingState>('/api/security/frame-ancestors');
        if (cancelled) return;
        const data = normalize(res.data);
        setState(data);
        setRestrict(data.restrict);
        setOrigins(data.extra_origins);
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
      const res = await axios.put<FramingState>('/api/security/frame-ancestors', {
        restrict,
        extra_origins: cleanOrigins,
      });
      const data = normalize(res.data);
      setState(data);
      setRestrict(data.restrict);
      setOrigins(data.extra_origins);
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
      icon={<FaObjectGroup />}
      title={t('security.framing.title')}
      description={t('security.framing.intro')}
      footer={
        <FormActions
          hint={
            <code className="font-mono text-xs bg-base-content/5 px-2 py-1 rounded">
              frame-ancestors {state.value}
            </code>
          }
        >
          {saved && (
            <span className="badge badge-warning badge-sm font-medium">
              {t('security.framing.restart_needed')}
            </span>
          )}
          <button
            className="btn btn-sm btn-primary"
            onClick={() => void save()}
            disabled={saving || !dirty}
          >
            {saving ? t('security.framing.saving') : t('security.framing.save')}
          </button>
        </FormActions>
      }
    >
      <div className="space-y-4">
        <ToggleRow
          checked={restrict}
          onChange={setRestrict}
          label={t('security.framing.restrict')}
          description={t('security.framing.restrict_help')}
        />

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
                    className="input input-bordered flex-1 font-mono text-sm"
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
      </div>
    </SettingsCard>
  );
}
