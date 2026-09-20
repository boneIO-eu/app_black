import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FaCheck, FaChevronLeft, FaChevronRight, FaSpinner } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FormField, NoticeCallout } from './ui';
import {
  PRESENCE_FLAG,
  buildPresenceSimulation,
  mergeGenerated,
  type PresenceOptions,
} from './helpers/presenceSimulation';

interface OutputOption {
  id: string;
  label: string;
  area?: string;
}

interface PresenceSimulationWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after the entries are written, so the page can refresh. */
  onDone?: () => void;
}

const STEPS = ['lights', 'timing', 'randomness', 'summary'] as const;
type Step = typeof STEPS[number];

const RANDOMNESS_CHOICES: PresenceOptions['randomness'][] = ['calm', 'normal', 'lively'];

/**
 * Four questions, then a handful of ordinary schedules.
 *
 * What it writes is not special: one virtual switch and one schedule per
 * light, all editable afterwards on their own pages, nothing extra running at
 * runtime. A second run replaces what the first one wrote and leaves anything
 * hand-made alone.
 */
const PresenceSimulationWizard: React.FC<PresenceSimulationWizardProps> = ({
  open,
  onOpenChange,
  onDone,
}) => {
  const { t } = useTranslation();
  const { hasLocation } = useConfig();
  const [step, setStep] = useState<Step>('lights');
  const [outputs, setOutputs] = useState<OutputOption[]>([]);
  const [config, setConfig] = useState<Record<string, unknown[]>>({});
  const [lights, setLights] = useState<string[]>([]);
  const [endsAt, setEndsAt] = useState('23:10');
  const [randomness, setRandomness] = useState<PresenceOptions['randomness']>('normal');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/config');
      const parsed = data.config || {};
      setOutputs(
        (parsed.output || []).map((output: Record<string, unknown>) => ({
          id: String(output.boneio_output || output.id || ''),
          label: String(output.name || output.boneio_output || output.id || ''),
          area: output.area ? String(output.area) : undefined,
        })).filter((output: OutputOption) => output.id),
      );
      setConfig({
        schedule: parsed.schedule || [],
        virtual_switch: parsed.virtual_switch || [],
      });
    } catch (err) {
      console.error('Failed to load config for the wizard:', err);
    }
  }, []);

  // Mounted only while open (see SectionContent), so the initial state above
  // is already the reset — there is nothing to clear on the way in.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const result = useMemo(
    () => buildPresenceSimulation({ lights, endsAt, randomness }),
    [lights, endsAt, randomness],
  );

  const labelOf = (id: string) => outputs.find((output) => output.id === id)?.label || id;

  const toggleLight = (id: string) =>
    setLights((current) =>
      current.includes(id) ? current.filter((light) => light !== id) : [...current, id],
    );

  const canContinue = step !== 'lights' || lights.length > 0;
  const index = STEPS.indexOf(step);

  const write = async () => {
    setSaving(true);
    setError(null);
    try {
      const switches = mergeGenerated(
        (config.virtual_switch || []) as { id?: string }[],
        [result.virtualSwitch as { id?: string }],
      );
      const schedules = mergeGenerated(
        (config.schedule || []) as { id?: string }[],
        result.schedules as { id?: string }[],
      );
      // The flag first: a schedule whose condition names a switch that does
      // not exist yet is a schedule that never fires.
      await axios.put('/api/config/virtual_switch', switches);
      await axios.put('/api/config/schedule', schedules);
      await axios.post('/api/config/reload', ['virtual_switch', 'schedule'], { timeout: 30000 });
      onOpenChange(false);
      onDone?.();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('presence.write_failed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl bg-base-100">
        <DialogHeader>
          <DialogTitle>{t('presence.title')}</DialogTitle>
          <DialogDescription>{t(`presence.step_${step}_hint`)}</DialogDescription>
        </DialogHeader>

        {/* Which step, without a progress bar that would be taller than the
            three dots it replaces. */}
        <div className="flex items-center gap-1.5 pb-2">
          {STEPS.map((name, i) => (
            <span
              key={name}
              className={`h-1 flex-1 rounded-full ${i <= index ? 'bg-primary' : 'bg-base-300'}`}
            />
          ))}
        </div>

        <div className="min-h-64 space-y-4">
          {!hasLocation && (
            <NoticeCallout variant="warning" message={t('presence.needs_location')} />
          )}

          {step === 'lights' && (
            <div className="space-y-2">
              {outputs.length === 0 && (
                <NoticeCallout variant="info" message={t('presence.no_outputs')} />
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {outputs.map((output) => {
                  const order = lights.indexOf(output.id);
                  return (
                    <button
                      key={output.id}
                      type="button"
                      onClick={() => toggleLight(output.id)}
                      className={`btn justify-start gap-2 ${order >= 0 ? 'btn-primary' : 'btn-outline'}`}
                    >
                      {/* The number is the order they come on in, which is the
                          whole point of picking them one at a time. */}
                      <span className="badge badge-sm shrink-0">{order >= 0 ? order + 1 : '·'}</span>
                      <span className="truncate">{output.label}</span>
                    </button>
                  );
                })}
              </div>
              <p className="text-xs opacity-60">{t('presence.order_hint')}</p>
            </div>
          )}

          {step === 'timing' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <FormField label={t('presence.ends_at')} help={t('presence.ends_at_hint')}>
                <input
                  type="time"
                  className="input input-bordered w-full"
                  value={endsAt}
                  onChange={(e) => setEndsAt(e.target.value || '23:10')}
                />
              </FormField>
            </div>
          )}

          {step === 'randomness' && (
            <div className="space-y-2">
              {RANDOMNESS_CHOICES.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => setRandomness(choice)}
                  className={`btn w-full justify-start h-auto py-3 flex-col items-start gap-0.5 ${
                    randomness === choice ? 'btn-primary' : 'btn-outline'
                  }`}
                >
                  <span className="font-medium">{t(`presence.random_${choice}`)}</span>
                  <span className="text-xs font-normal opacity-70 whitespace-normal text-left">
                    {t(`presence.random_${choice}_hint`)}
                  </span>
                </button>
              ))}
            </div>
          )}

          {step === 'summary' && (
            <div className="space-y-3">
              {/* The evening in words, before anything is written. */}
              <ul className="space-y-1">
                {result.preview.map((line) => (
                  <li key={line.at + line.label} className="flex items-baseline gap-3 text-sm">
                    <span className="font-mono opacity-70 w-16 shrink-0">{line.at}</span>
                    <span>
                      {line.label === 'off'
                        ? t('presence.everything_off')
                        : t('presence.turns_on').replace('{name}', labelOf(line.label))}
                    </span>
                  </li>
                ))}
              </ul>

              <NoticeCallout
                variant="info"
                message={t('presence.writes')
                  .replace('{schedules}', String(result.schedules.length))
                  .replace('{flag}', PRESENCE_FLAG)}
              />

              {error && <NoticeCallout variant="error" message={error} />}
            </div>
          )}
        </div>

        <DialogFooter>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => (index === 0 ? onOpenChange(false) : setStep(STEPS[index - 1]))}
            disabled={saving}
          >
            {index === 0 ? t('common.cancel') : <><FaChevronLeft className="w-3 h-3" />{t('presence.back')}</>}
          </button>
          {step === 'summary' ? (
            <button type="button" className="btn btn-primary gap-2" onClick={write} disabled={saving}>
              {saving ? <><FaSpinner className="animate-spin" />{t('presence.writing')}</>
                      : <><FaCheck />{t('presence.create')}</>}
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary gap-2"
              onClick={() => setStep(STEPS[index + 1])}
              disabled={!canContinue}
            >
              {t('presence.next')}
              <FaChevronRight className="w-3 h-3" />
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PresenceSimulationWizard;
