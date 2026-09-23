import React, { useMemo, useState } from 'react';
import { FaCheck, FaChevronLeft, FaChevronRight, FaSpinner } from 'react-icons/fa';
import { FaMagnifyingGlass, FaWandMagicSparkles, FaWifi, FaXmark } from 'react-icons/fa6';
import { cn } from '@/lib/utils';
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
  type RemoteTarget,
} from './helpers/presenceSimulation';

interface OutputOption {
  id: string;
  label: string;
  area?: string;
  isLight: boolean;
  remote?: boolean;
}

interface PresenceSimulationWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after the entries are written, so the page can refresh. */
  onDone?: () => void;
  /** The config the settings page has loaded — outputs, remote outputs, areas. */
  formData: Record<string, unknown>;
}

type Entry = Record<string, unknown>;

const typeOf = (entry: Entry) => String(entry.output_type || '').toLowerCase();

/** Everything that could be a light, local relays and remote outputs alike. */
function buildOutputOptions(formData: Record<string, unknown>): {
  outputs: OutputOption[];
  remotes: Record<string, RemoteTarget>;
} {
  const list = (key: string) => (Array.isArray(formData[key]) ? formData[key] as Entry[] : []);
  const areaNames: Record<string, string> = Object.fromEntries(
    list('areas').map((area) => [String(area.id), String(area.name || area.id)]),
  );
  const areaOf = (entry: Entry) =>
    entry.area ? areaNames[String(entry.area)] || String(entry.area) : undefined;
  // A cover or valve relay switched on at dusk is not a lamp coming on — it
  // is a blind driving or water running. Only what could be a light is offered.
  const couldBeLight = (entry: Entry) => !NOT_A_LIGHT.has(typeOf(entry));

  const local: OutputOption[] = list('output')
    .filter(couldBeLight)
    .map((output) => ({
      id: String(output.boneio_output || output.id || ''),
      label: String(output.name || output.boneio_output || output.id || ''),
      area: areaOf(output),
      isLight: typeOf(output) === 'light',
    }))
    .filter((output) => output.id);

  const remotes: Record<string, RemoteTarget> = {};
  const remote: OutputOption[] = list('remote_outputs')
    .filter((output) => couldBeLight(output) && output.device_id && output.output_id)
    .map((output) => {
      // Keyed apart from local ids: a remote `relay_1` must not collide with
      // anything on this board.
      const id = `remote:${output.device_id}/${output.output_id}`;
      remotes[id] = { remote_device: String(output.device_id), output_id: String(output.output_id) };
      return {
        id,
        label: String(output.name || output.id || `${output.device_id} · ${output.output_id}`),
        area: areaOf(output),
        isLight: typeOf(output) === 'light',
        remote: true,
      };
    });

  return { outputs: [...local, ...remote], remotes };
}

const STEPS = ['lights', 'timing', 'randomness', 'summary'] as const;
type Step = typeof STEPS[number];

const NOT_A_LIGHT = new Set(['cover', 'valve', 'none']);

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
  formData,
}) => {
  const { t } = useTranslation();
  const { hasLocation } = useConfig();
  const [step, setStep] = useState<Step>('lights');
  const [lights, setLights] = useState<string[]>([]);
  const [endsAt, setEndsAt] = useState('23:10');
  const [randomness, setRandomness] = useState<PresenceOptions['randomness']>('normal');
  const [filter, setFilter] = useState<'lights' | 'all' | null>(null);
  const [query, setQuery] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Built from the config the settings page already holds, so the list is
  // there the moment the dialog opens rather than a round trip later.
  const { outputs, remotes } = useMemo(() => buildOutputOptions(formData), [formData]);

  const labels = useMemo(
    () => Object.fromEntries(outputs.map((output) => [output.id, output.label])),
    [outputs],
  );

  const result = useMemo(
    () => buildPresenceSimulation({
      lights,
      endsAt,
      randomness,
      labels,
      remotes,
      // The generated entries are named, not id-ed, and the name is what the
      // table shows — so it is localised like everything else on the page.
      flagName: t('presence.flag_name'),
      namePrefix: t('presence.name_prefix'),
      endName: t('presence.end_name'),
    }),
    [lights, endsAt, randomness, labels, remotes, t],
  );

  const labelOf = (id: string) => labels[id] || id;

  const lightCount = outputs.filter((output) => output.isLight).length;
  // Lights first when there are any; on a board where every relay is still a
  // plain switch there is nothing to narrow to, so everything is shown.
  const activeFilter = filter ?? (lightCount > 0 ? 'lights' : 'all');

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const visible = outputs.filter((output) =>
      (activeFilter === 'all' || output.isLight) &&
      (!needle || output.label.toLowerCase().includes(needle) || output.id.toLowerCase().includes(needle)),
    );
    const byArea = new Map<string, OutputOption[]>();
    for (const output of visible) {
      const key = output.area || '';
      byArea.set(key, [...(byArea.get(key) || []), output]);
    }
    // Named areas alphabetically, the unassigned ones last.
    return [...byArea.entries()].sort(([a], [b]) =>
      a === '' ? 1 : b === '' ? -1 : a.localeCompare(b));
  }, [outputs, activeFilter, query]);

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
      // The sections being replaced are read fresh from the device, not from
      // the page: what gets merged must be what is saved, not unsaved edits.
      const { data } = await axios.get('/api/config');
      const config = (data.config || {}) as Record<string, unknown[]>;
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
      {/* A column that holds the height: header and footer stay put, only the
          body scrolls. As a grid the body grew with 32 outputs and pushed the
          footer off a 1080p screen. One fixed height for every step, so Back
          and Next stay under the cursor instead of jumping as it resizes. */}
      <DialogContent
        maxWidthClass="sm:max-w-2xl"
        className="flex flex-col gap-0 overflow-hidden p-0 pt-3 sm:p-0 sm:h-[min(85vh,46rem)]"
      >
        <DialogHeader className="px-6 pt-2 sm:pt-5 pb-4 border-b border-base-content/8">
          <DialogTitle className="flex items-center gap-2.5">
            <span className="stg-chip w-8 h-8 rounded-lg inline-flex items-center justify-center text-sm">
              <FaWandMagicSparkles />
            </span>
            {t('presence.title')}
          </DialogTitle>

          {/* Numbered steps with names — where you are and what is left. */}
          <ol className="flex items-center gap-2 pt-4">
            {STEPS.map((name, i) => {
              const done = i < index;
              const current = i === index;
              return (
                <li key={name} className="flex flex-1 items-center gap-2 min-w-0">
                  <span
                    className={cn(
                      'w-6 h-6 shrink-0 rounded-full inline-flex items-center justify-center text-[11px] font-semibold',
                      done && 'bg-primary text-primary-content',
                      current && 'bg-primary/15 text-primary ring-1 ring-primary/40',
                      !done && !current && 'bg-base-content/8 text-base-content/45',
                    )}
                  >
                    {done ? <FaCheck className="w-2.5 h-2.5" /> : i + 1}
                  </span>
                  <span
                    className={cn(
                      'hidden sm:inline text-xs truncate',
                      current ? 'font-semibold text-base-content' : 'text-base-content/50',
                    )}
                  >
                    {t(`presence.step_label_${name}`)}
                  </span>
                  {i < STEPS.length - 1 && (
                    <span className={cn('h-px flex-1 min-w-3', done ? 'bg-primary/50' : 'bg-base-content/10')} />
                  )}
                </li>
              );
            })}
          </ol>
          <DialogDescription className="pt-3">{t(`presence.step_${step}_hint`)}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5 space-y-4">
          {!hasLocation && (
            <NoticeCallout variant="warning" message={t('presence.needs_location')} />
          )}

          {step === 'lights' && (
            <>
              {/* The order, as it will play out — removable from here. */}
              <div className="stg-inset p-3">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-base-content/50 mb-2">
                  {t('presence.order_title')}
                </div>
                {lights.length === 0 ? (
                  <p className="text-[13px] text-base-content/55">{t('presence.order_empty')}</p>
                ) : (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {lights.map((id, i) => (
                      <React.Fragment key={id}>
                        {i > 0 && <FaChevronRight className="w-2.5 h-2.5 text-base-content/30" />}
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 text-primary pl-1 pr-1 py-0.5 text-[13px] font-medium">
                          <span className="w-5 h-5 rounded-full bg-primary text-primary-content inline-flex items-center justify-center text-[10px] font-semibold">
                            {i + 1}
                          </span>
                          <span className="max-w-40 truncate">{labelOf(id)}</span>
                          <button
                            type="button"
                            className="w-5 h-5 rounded-full inline-flex items-center justify-center hover:bg-primary/15"
                            onClick={() => toggleLight(id)}
                            aria-label={t('presence.remove')}
                          >
                            <FaXmark className="w-3 h-3" />
                          </button>
                        </span>
                      </React.Fragment>
                    ))}
                  </div>
                )}
                <p className="text-xs text-base-content/50 mt-2 leading-relaxed">{t('presence.order_hint')}</p>
              </div>

              {outputs.length === 0 ? (
                <NoticeCallout variant="info" message={t('presence.no_outputs')} />
              ) : (
                <>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <label className="input input-bordered input-sm flex items-center gap-2 flex-1">
                      <FaMagnifyingGlass className="w-3 h-3 opacity-50" />
                      <input
                        type="search"
                        className="grow"
                        placeholder={t('presence.search')}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    {lightCount > 0 && lightCount < outputs.length && (
                      <div className="flex gap-1 rounded-lg bg-base-content/5 p-1 shrink-0">
                        {(['lights', 'all'] as const).map((choice) => (
                          <button
                            key={choice}
                            type="button"
                            onClick={() => setFilter(choice)}
                            className={cn(
                              'rounded-md px-2.5 py-0.5 text-xs font-medium transition-colors',
                              activeFilter === choice
                                ? 'bg-base-100 text-base-content shadow-sm'
                                : 'text-base-content/55 hover:text-base-content/85',
                            )}
                          >
                            {t(`presence.filter_${choice}`)}{' '}
                            <span className="opacity-50">
                              {choice === 'lights' ? lightCount : outputs.length}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {groups.length === 0 && (
                    <p className="text-[13px] text-base-content/55 text-center py-6">{t('presence.no_match')}</p>
                  )}

                  {groups.map(([area, items]) => (
                    <div key={area || '_none'}>
                      {(groups.length > 1 || area) && (
                        <div className="text-[11px] font-semibold uppercase tracking-wider text-base-content/45 mb-1.5 px-0.5">
                          {area || t('presence.no_area')}
                        </div>
                      )}
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                        {items.map((output) => {
                          const order = lights.indexOf(output.id);
                          const picked = order >= 0;
                          return (
                            <button
                              key={output.id}
                              type="button"
                              onClick={() => toggleLight(output.id)}
                              className={cn(
                                'flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-[13px] transition-colors',
                                picked
                                  ? 'border-primary/50 bg-primary/8 text-base-content'
                                  : 'border-base-content/10 hover:border-base-content/25 hover:bg-base-content/3 text-base-content/80',
                              )}
                            >
                              {/* The number is the order they come on in,
                                  which is the whole point of picking them one
                                  at a time. */}
                              <span
                                className={cn(
                                  'w-5 h-5 shrink-0 rounded-full inline-flex items-center justify-center text-[10px] font-semibold',
                                  picked
                                    ? 'bg-primary text-primary-content'
                                    : 'border border-base-content/20',
                                )}
                              >
                                {picked ? order + 1 : ''}
                              </span>
                              <span className="truncate">{output.label}</span>
                              {output.remote && (
                                <FaWifi
                                  className="ml-auto w-3 h-3 shrink-0 text-base-content/35"
                                  title={t('presence.remote')}
                                />
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </>
          )}

          {step === 'timing' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="stg-inset p-4">
                <div className="text-xs font-medium text-base-content/55">{t('presence.starts_at')}</div>
                <div className="text-lg font-semibold mt-0.5">{t('presence.starts_at_value')}</div>
                <p className="text-xs text-base-content/50 mt-1 leading-relaxed">{t('presence.starts_at_hint')}</p>
              </div>
              <div className="stg-inset p-4">
                <FormField label={t('presence.ends_at')}>
                  <input
                    type="time"
                    className="input input-bordered w-full"
                    value={endsAt}
                    onChange={(e) => setEndsAt(e.target.value || '23:10')}
                  />
                </FormField>
              </div>
              <p className="sm:col-span-2 text-xs text-base-content/55 leading-relaxed">
                {t('presence.ends_at_hint')}
              </p>
            </div>
          )}

          {step === 'randomness' && (
            <div className="space-y-2">
              {RANDOMNESS_CHOICES.map((choice) => {
                const selected = randomness === choice;
                return (
                  <button
                    key={choice}
                    type="button"
                    onClick={() => setRandomness(choice)}
                    className={cn(
                      'w-full flex items-start gap-3 rounded-xl border p-3.5 text-left transition-colors',
                      selected
                        ? 'border-primary/50 bg-primary/5 ring-1 ring-primary/20'
                        : 'border-base-content/10 hover:border-base-content/20 hover:bg-base-content/3',
                    )}
                  >
                    <input
                      type="radio"
                      className="radio radio-primary radio-sm mt-0.5 pointer-events-none"
                      checked={selected}
                      readOnly
                    />
                    <span className="min-w-0">
                      <span className="block font-medium text-sm">{t(`presence.random_${choice}`)}</span>
                      <span className="block text-xs text-base-content/60 mt-0.5 leading-relaxed">
                        {t(`presence.random_${choice}_hint`)}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {step === 'summary' && (
            <div className="space-y-4">
              {/* The evening as a timeline, before anything is written. */}
              <ol className="relative ml-2 border-l border-base-content/12 space-y-3">
                {result.preview.map((line) => (
                  <li key={line.at + line.label} className="relative pl-5">
                    <span
                      className={cn(
                        'absolute -left-[5px] top-1.5 w-2.5 h-2.5 rounded-full ring-4 ring-base-100',
                        line.label === 'off' ? 'bg-base-content/40' : 'bg-primary',
                      )}
                    />
                    <div className="flex items-baseline gap-3 text-sm">
                      <span className="font-mono text-base-content/55 w-14 shrink-0">{line.at}</span>
                      <span>
                        {line.label === 'off'
                          ? t('presence.everything_off')
                          : t('presence.turns_on').replace('{name}', labelOf(line.label))}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>

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

        <DialogFooter className="px-6 py-3.5 border-t border-base-content/8 bg-base-content/[0.02] sm:justify-between">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => (index === 0 ? onOpenChange(false) : setStep(STEPS[index - 1]))}
            disabled={saving}
          >
            {index === 0 ? t('common.cancel') : <><FaChevronLeft className="w-3 h-3" />{t('presence.back')}</>}
          </button>
          {step === 'summary' ? (
            <button type="button" className="btn btn-primary btn-sm gap-2" onClick={write} disabled={saving}>
              {saving ? <><FaSpinner className="animate-spin" />{t('presence.writing')}</>
                      : <><FaCheck />{t('presence.create')}</>}
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary btn-sm gap-2"
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
