import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { FaBolt, FaCheck, FaChevronDown, FaChevronRight, FaPlus, FaSpinner, FaTrash } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import type {
  AreaEntity,
  BinarySensorEntity,
  CoverEntity,
  OutputEntity,
  RemoteDeviceEntity,
} from '@/types/config';
import axios from '@/api/axios';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import ActionFields from '../ActionFields';
import ActionConditions from '../ActionFields/ActionConditions';
import { applyActionUpdate } from '../ActionFields/helpers';
import {
  SettingsPage,
  SettingsCard,
  FormField,
  FormActions,
  NoticeCallout,
} from '../ui';

/** Sun anchors, grouped the way someone shopping for one thinks about them. */
const SUN_EVENT_GROUPS: { label: string; events: string[] }[] = [
  { label: 'event_form.condition_sun_group_basic', events: ['sunrise', 'sunset', 'solar_noon', 'solar_midnight'] },
  {
    label: 'event_form.condition_sun_group_twilight',
    events: ['civil_dawn', 'civil_dusk', 'nautical_dawn', 'nautical_dusk', 'astronomical_dawn', 'astronomical_dusk'],
  },
  {
    label: 'event_form.condition_sun_group_photographic',
    events: [
      'golden_hour_morning_start', 'golden_hour_morning_end',
      'golden_hour_evening_start', 'golden_hour_evening_end',
      'blue_hour_morning_start', 'blue_hour_morning_end',
      'blue_hour_evening_start', 'blue_hour_evening_end',
    ],
  },
];

const DAY_OPTIONS = ['daily', 'weekdays', 'weekend', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

// Mirrors boneio/schema/actions.yaml. Hardcoded rather than derived from the
// JSON schema: this page is not schema-driven, and threading the schema in for
// three lists would cost more than it saves.
const ACTION_TYPE_OPTIONS = ['output', 'cover', 'mqtt', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'];
const ACTION_OUTPUT_OPTIONS = ['TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET'];
const ACTION_COVER_OPTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE'];

/** One action, as the config carries it. Its fields depend on `action`. */
type ActionEntry = Record<string, unknown>;

/** A schedule's trigger, as `boneio/schema/schema.yaml` defines it.
 *
 * Offsets are numbers (seconds) coming from the backend and strings ("-15min")
 * going back, which is why both are allowed here. */
interface ScheduleTrigger {
  type?: string;
  event?: string;
  at?: string;
  offset?: string | number;
  jitter?: string | number;
  days?: string;
}

/** One schedule. The index signature covers `condition`/`conditions`, which
 * are passed straight through to the shared condition editor. */
interface ScheduleEntry {
  id: string;
  name?: string;
  enabled?: boolean;
  trigger?: ScheduleTrigger;
  on_missed?: string;
  actions?: ActionEntry[];
  [key: string]: unknown;
}

/** Entity lists the action editor needs, read once from the config.
 *
 * Never undefined: ActionFields takes them as required arrays, and an empty
 * list renders an empty picker, which is the honest state before the config
 * has loaded. */
interface EntityLists {
  allOutputs: OutputEntity[];
  allOutputGroups: Record<string, unknown>[];
  allCovers: CoverEntity[];
  allAreas: AreaEntity[];
  allRemoteDevices: RemoteDeviceEntity[];
  allBinarySensors: BinarySensorEntity[];
  allRemoteInputs: Record<string, unknown>[];
}

const NO_ENTITIES: EntityLists = {
  allOutputs: [],
  allOutputGroups: [],
  allCovers: [],
  allAreas: [],
  allRemoteDevices: [],
  allBinarySensors: [],
  allRemoteInputs: [],
};

interface ScheduleStatus {
  id: string;
  name: string;
  enabled: boolean;
  actions: number;
  next_fire: string | null;
  last_fire: string | null;
  last_error: string | null;
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

/** Offsets come back from the backend in seconds; minutes is what people type. */
function offsetToMinutes(value: string | number | undefined): string {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'number') return String(Math.round(value / 60));
  const match = String(value).trim().match(/^([-+]?\d*\.?\d+)\s*(\w*)$/);
  if (!match) return '';
  const amount = parseFloat(match[1]);
  const unit = (match[2] || 's').toLowerCase();
  const seconds = unit.startsWith('h') ? amount * 3600 : unit.startsWith('m') ? amount * 60 : amount;
  return String(Math.round(seconds / 60));
}

function minutesToOffset(minutes: string): string | undefined {
  const trimmed = minutes.trim();
  if (trimmed === '' || trimmed === '-') return undefined;
  const value = parseInt(trimmed, 10);
  if (isNaN(value) || value === 0) return undefined;
  return `${value}min`;
}

/** Local HH:MM from an ISO timestamp, with the date when it is not today. */
function formatFire(iso: string | null): string {
  if (!iso) return '—';
  const when = new Date(iso);
  if (isNaN(when.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  const clock = `${pad(when.getHours())}:${pad(when.getMinutes())}`;
  const today = new Date();
  const sameDay =
    when.getFullYear() === today.getFullYear() &&
    when.getMonth() === today.getMonth() &&
    when.getDate() === today.getDate();
  return sameDay ? clock : `${pad(when.getDate())}.${pad(when.getMonth() + 1)} ${clock}`;
}

/**
 * Schedules: actions that fire on their own.
 *
 * Its own page rather than a generated form, for one reason: a schedule is the
 * only thing here nobody can test by pressing a button. Without "next firing"
 * and "run now" next to the fields, the only way to find out whether it works
 * is to wait until evening.
 */
export default function ScheduleSection() {
  const { t } = useTranslation();
  const { hasLocation } = useConfig();
  const [schedules, setSchedules] = useState<ScheduleEntry[]>([]);
  const [status, setStatus] = useState<Record<string, ScheduleStatus>>({});
  const [entities, setEntities] = useState<EntityLists>(NO_ENTITIES);
  const [dirty, setDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  // One editor open at a time. With several schedules, stacking every
  // trigger, condition and action editor on the page is a kilometre of
  // scrolling that shows nothing at a glance.
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [result, setResult] = useState<{ status: string; message: string } | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [{ data: config }, { data: state }] = await Promise.all([
        axios.get('/api/config'),
        axios.get('/api/schedule'),
      ]);
      const parsed = config.config || {};
      setSchedules(parsed.schedule || []);
      setEntities({
        allOutputs: parsed.output || [],
        allOutputGroups: parsed.output_group || [],
        allCovers: parsed.cover || [],
        allAreas: parsed.areas || [],
        allRemoteDevices: parsed.remote_devices || [],
        allBinarySensors: parsed.binary_sensor || [],
        allRemoteInputs: parsed.remote_inputs || [],
      });
      const byId: Record<string, ScheduleStatus> = {};
      for (const entry of state.schedules || []) byId[entry.id] = entry;
      setStatus(byId);
      setDirty(false);
    } catch (err) {
      console.error('Failed to load schedules:', err);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchAll();
  }, [fetchAll]);

  const update = (index: number, mutate: (entry: ScheduleEntry) => ScheduleEntry) => {
    setSchedules((current) => current.map((entry, i) => (i === index ? mutate({ ...entry }) : entry)));
    setDirty(true);
  };


  const updateTrigger = (index: number, field: keyof ScheduleTrigger, value: string | undefined) => {
    update(index, (entry) => {
      const trigger: ScheduleTrigger = { ...(entry.trigger || {}), [field]: value };
      if (field === 'type') {
        // `at` and `event` belong to different trigger types; carrying one over
        // produces a config the loader rejects.
        if (value === 'sun') delete trigger.at;
        else delete trigger.event;
      }
      if (value === undefined) delete trigger[field];
      entry.trigger = trigger;
      return entry;
    });
  };

  const addSchedule = () => {
    setSchedules((current) => [
      ...current,
      {
        id: `schedule_${current.length + 1}`,
        name: '',
        enabled: true,
        // Sunset is the schedule people usually want, but only where the
        // device knows when sunset is. Without coordinates a sun trigger can
        // never resolve, so a new schedule starts as a clock time instead of
        // opening on an option that is greyed out.
        trigger: hasLocation
          ? { type: 'sun', event: 'sunset', days: 'daily' }
          : { type: 'time', at: '20:00', days: 'daily' },
        actions: [],
      },
    ]);
    setOpenIndex(schedules.length);
    setDirty(true);
  };

  const save = async () => {
    setIsSaving(true);
    setResult(null);
    try {
      await axios.put('/api/config/schedule', schedules);
      await axios.post('/api/config/reload', ['schedule'], { timeout: 30000 });
      setResult({ status: 'success', message: t('schedule.saved') });
      await fetchAll();
    } catch (err: unknown) {
      setResult({ status: 'error', message: errorDetail(err) || t('schedule.save_failed') });
    } finally {
      setIsSaving(false);
    }
  };

  const runNow = async (id: string) => {
    setRunning(id);
    setResult(null);
    try {
      await axios.post(`/api/schedule/${encodeURIComponent(id)}/run`);
      setResult({ status: 'success', message: t('schedule.ran') });
      await fetchAll();
    } catch (err: unknown) {
      setResult({ status: 'error', message: errorDetail(err) || t('schedule.run_failed') });
    } finally {
      setRunning(null);
    }
  };

  const hint = useMemo(
    () => `${schedules.length} ${t('schedule.count')}`,
    [schedules.length, t],
  );

  /** One line describing when this schedule fires, for the table row. */
  const triggerSummary = (entry: ScheduleEntry): string => {
    const trigger = entry.trigger || {};
    const days = t(`schedule.days_${trigger.days || 'daily'}`);
    const offset = offsetToMinutes(trigger.offset);
    const shift = offset && offset !== '0'
      ? ` ${Number(offset) > 0 ? '+' : '\u2212'}${Math.abs(Number(offset))} min`
      : '';

    if ((trigger.type || 'sun') === 'time') {
      return `${trigger.at || '--:--'}${shift} · ${days}`;
    }
    const event = trigger.event ? t(`sun.anchor_${trigger.event}`) : '—';
    return `${event}${shift} · ${days}`;
  };

  /** The distinct action types this schedule runs, for the table row. */
  const actionTypes = (entry: ScheduleEntry): string[] => [
    ...new Set((entry.actions || []).map((a) => String(a.action || '')).filter(Boolean)),
  ];

  const renderTrigger = (entry: ScheduleEntry, index: number) => {
    const trigger = entry.trigger || {};
    const kind = trigger.type || 'sun';
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <FormField label={t('schedule.trigger_type')}>
          <Select value={kind} onValueChange={(value) => updateTrigger(index, 'type', value)}>
            <SelectTrigger className="w-full h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {/* Greyed out rather than hidden without coordinates: seeing that
                  the option exists, and being told why it is unavailable, beats
                  wondering where it went. A schedule that already uses one stays
                  selectable, or removing the location would blank the field. */}
              <SelectItem value="sun" disabled={!hasLocation && kind !== 'sun'}>
                {t('schedule.trigger_sun')}
                {!hasLocation && kind !== 'sun' && (
                  <span className="text-xs opacity-60"> — {t('schedule.needs_location_short')}</span>
                )}
              </SelectItem>
              <SelectItem value="time">{t('schedule.trigger_time')}</SelectItem>
            </SelectContent>
          </Select>
        </FormField>

        {kind === 'sun' ? (
          <FormField label={t('schedule.event')}>
            <Select
              value={trigger.event || ''}
              onValueChange={(value) => updateTrigger(index, 'event', value)}
            >
              <SelectTrigger className="w-full h-9">
                <SelectValue placeholder={t('event_form.condition_sun_anchor')} />
              </SelectTrigger>
              <SelectContent>
                {SUN_EVENT_GROUPS.map((group) => (
                  <SelectGroup key={group.label}>
                    <SelectLabel>{t(group.label)}</SelectLabel>
                    {group.events.map((event) => (
                      <SelectItem key={event} value={event}>{t(`sun.anchor_${event}`)}</SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </FormField>
        ) : (
          <FormField label={t('schedule.at')}>
            <input
              type="time"
              className="input input-bordered input-sm w-full"
              value={trigger.at || ''}
              onChange={(e) => updateTrigger(index, 'at', e.target.value)}
            />
          </FormField>
        )}

        <FormField label={t('schedule.offset')} help={t('schedule.offset_hint')}>
          <label className="input input-bordered input-sm flex items-center gap-1 w-full">
            <input
              type="number"
              className="grow min-w-0 bg-transparent outline-hidden"
              placeholder="0"
              step={5}
              value={offsetToMinutes(trigger.offset)}
              onChange={(e) => updateTrigger(index, 'offset', minutesToOffset(e.target.value))}
            />
            <span className="text-xs opacity-60 shrink-0">{t('event_form.condition_sun_minutes')}</span>
          </label>
        </FormField>

        <FormField label={t('schedule.days')}>
          <Select
            value={trigger.days || 'daily'}
            onValueChange={(value) => updateTrigger(index, 'days', value)}
          >
            <SelectTrigger className="w-full h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DAY_OPTIONS.map((day) => (
                <SelectItem key={day} value={day}>{t(`schedule.days_${day}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FormField>

        <FormField label={t('schedule.jitter')} help={t('schedule.jitter_hint')}>
          <label className="input input-bordered input-sm flex items-center gap-1 w-full">
            <input
              type="number"
              className="grow min-w-0 bg-transparent outline-hidden"
              placeholder="0"
              min={0}
              step={5}
              value={offsetToMinutes(trigger.jitter)}
              onChange={(e) => updateTrigger(index, 'jitter', minutesToOffset(e.target.value))}
            />
            <span className="text-xs opacity-60 shrink-0">{t('event_form.condition_sun_minutes')}</span>
          </label>
        </FormField>

        <FormField label={t('schedule.on_missed')} help={t('schedule.on_missed_hint')}>
          <Select
            value={entry.on_missed || 'skip'}
            onValueChange={(value) => update(index, (e) => ({ ...e, on_missed: value }))}
          >
            <SelectTrigger className="w-full h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="skip">{t('schedule.on_missed_skip')}</SelectItem>
              <SelectItem value="run">{t('schedule.on_missed_run')}</SelectItem>
            </SelectContent>
          </Select>
        </FormField>
      </div>
    );
  };

  return (
    <SettingsPage>
      <SettingsCard
        footer={
          <FormActions hint={hint}>
            <button className="btn btn-ghost btn-sm gap-2" onClick={addSchedule}>
              <FaPlus className="w-3 h-3" />
              {t('schedule.add')}
            </button>
            <button className="btn btn-primary btn-sm gap-2" onClick={save} disabled={isSaving || !dirty}>
              {isSaving ? <><FaSpinner className="animate-spin" />{t('schedule.saving')}</>
                        : <><FaCheck />{t('schedule.save')}</>}
            </button>
          </FormActions>
        }
      >
        <div className="space-y-4">
          <p className="text-xs opacity-60">{t('schedule.description')}</p>

          {!hasLocation && (
            <NoticeCallout variant="info" message={t('schedule.needs_location')} />
          )}

          {schedules.length === 0 && (
            <NoticeCallout variant="info" message={t('schedule.empty')} />
          )}

          {schedules.length > 0 && (
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th className="w-10"></th>
                    <th>{t('schedule.column_name')}</th>
                    <th>{t('schedule.column_trigger')}</th>
                    <th>{t('schedule.column_actions')}</th>
                    <th className="text-right">{t('schedule.column_next')}</th>
                    <th className="w-32"></th>
                  </tr>
                </thead>
                <tbody>
                  {schedules.map((entry, index) => {
                    const state = status[entry.id];
                    const open = openIndex === index;
                    const disabled = entry.enabled === false;
                    return (
                      <Fragment key={index}>
                        <tr
                          className={`hover cursor-pointer ${open ? 'bg-base-200' : ''} ${disabled ? 'opacity-50' : ''}`}
                          onClick={() => setOpenIndex(open ? null : index)}
                        >
                          <td onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              className="toggle toggle-xs"
                              checked={!disabled}
                              onChange={(e) => update(index, (sc) => ({ ...sc, enabled: e.target.checked }))}
                              title={t('schedule.enabled')}
                            />
                          </td>
                          <td>
                            <div className="flex items-center gap-1.5">
                              {open ? <FaChevronDown className="w-2.5 h-2.5 opacity-50" />
                                    : <FaChevronRight className="w-2.5 h-2.5 opacity-50" />}
                              <div className="min-w-0">
                                <div className="truncate">{entry.name || entry.id}</div>
                                {entry.name && (
                                  <div className="text-xs opacity-50 font-mono truncate">{entry.id}</div>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="whitespace-nowrap text-xs">{triggerSummary(entry)}</td>
                          <td>
                            <div className="flex flex-wrap gap-1">
                              {actionTypes(entry).map((type) => (
                                <span key={type} className="badge badge-ghost badge-xs">{type}</span>
                              ))}
                              {(entry.actions || []).length === 0 && (
                                <span className="badge badge-warning badge-xs">{t('schedule.no_actions')}</span>
                              )}
                            </div>
                          </td>
                          <td className="text-right font-mono text-xs whitespace-nowrap">
                            {formatFire(state?.next_fire ?? null)}
                          </td>
                          <td onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-end gap-1">
                              <button
                                type="button"
                                className="btn btn-ghost btn-xs btn-square"
                                onClick={() => runNow(entry.id)}
                                disabled={!state || running === entry.id || dirty}
                                title={dirty ? t('schedule.run_needs_save') : t('schedule.run_now')}
                              >
                                {running === entry.id
                                  ? <FaSpinner className="animate-spin w-3 h-3" />
                                  : <FaBolt className="w-3 h-3" />}
                              </button>
                              <button
                                type="button"
                                className="btn btn-ghost btn-xs btn-square text-error"
                                onClick={() => {
                                  setSchedules((current) => current.filter((_, i) => i !== index));
                                  setOpenIndex(null);
                                  setDirty(true);
                                }}
                                title={t('schedule.remove')}
                              >
                                <FaTrash className="w-3 h-3" />
                              </button>
                            </div>
                          </td>
                        </tr>

                        {open && (
                          <tr>
                            <td colSpan={6} className="bg-base-200/40">
                              <div className="space-y-3 p-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <input
                                    type="text"
                                    className="input input-bordered input-sm"
                                    placeholder={t('schedule.name')}
                                    value={entry.name || ''}
                                    onChange={(e) => update(index, (sc) => ({ ...sc, name: e.target.value }))}
                                  />
                                  <input
                                    type="text"
                                    className="input input-bordered input-sm w-40 font-mono"
                                    placeholder="id"
                                    value={entry.id || ''}
                                    onChange={(e) => update(index, (sc) => ({ ...sc, id: e.target.value }))}
                                  />
                                </div>
                    {state?.last_error && (
                      <NoticeCallout variant="error" message={`${t('schedule.last_error')}: ${state.last_error}`} />
                    )}

                    {renderTrigger(entry, index)}

                    {/* The schedule's own conditions gate the whole firing. Each
                        action may still carry its own, edited below. */}
                    <ActionConditions
                      action={entry}
                      onUpdate={(field, value) =>
                        update(index, (s) => applyActionUpdate(s, field, value))
                      }
                      t={t}
                      allOutputs={entities.allOutputs}
                      allCovers={entities.allCovers}
                      allBinarySensors={entities.allBinarySensors}
                      allRemoteInputs={entities.allRemoteInputs}
                      allAreas={entities.allAreas}
                    />

                    <div className="divider text-xs opacity-70 my-1">{t('schedule.actions')}</div>
                    {(entry.actions || []).map((action: ActionEntry, actionIndex: number) => (
                      <ActionFields
                        key={actionIndex}
                        action={action}
                        index={actionIndex}
                        onUpdate={(field, value) =>
                          update(index, (s) => ({
                            ...s,
                            actions: (s.actions || []).map((a: ActionEntry, i: number) =>
                              i === actionIndex ? applyActionUpdate(a, field, value) : a,
                            ),
                          }))
                        }
                        onRemove={() =>
                          update(index, (s) => ({
                            ...s,
                            actions: (s.actions || []).filter((_: ActionEntry, i: number) => i !== actionIndex),
                          }))
                        }
                        actionTypeOptions={ACTION_TYPE_OPTIONS}
                        actionOutputOptions={ACTION_OUTPUT_OPTIONS}
                        actionCoverOptions={ACTION_COVER_OPTIONS}
                        {...entities}
                      />
                    ))}
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs gap-1"
                      onClick={() =>
                        update(index, (s) => ({
                          ...s,
                          actions: [...(s.actions || []), { action: 'output', action_output: 'TOGGLE' }],
                        }))
                      }
                    >
                      <FaPlus className="w-2.5 h-2.5" />
                      {t('schedule.add_action')}
                    </button>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {result && (
            <NoticeCallout
              variant={result.status === 'success' ? 'success' : 'error'}
              message={result.message}
            />
          )}
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
