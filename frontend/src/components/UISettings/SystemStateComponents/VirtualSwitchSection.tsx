import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { FaCheck, FaChevronDown, FaChevronRight, FaPlus, FaPowerOff, FaSpinner, FaTrash } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import type {
  AreaEntity,
  BinarySensorEntity,
  CoverEntity,
  OutputEntity,
  RemoteDeviceEntity,
} from '@/types/config';
import axios from '@/api/axios';
import ActionFields from '../ActionFields';
import { applyActionUpdate } from '../ActionFields/helpers';
import { EDGES, withEdgeActions, type ActionEntry, type Edge, type SwitchEntry } from './virtualSwitchEdges';
import {
  SettingsPage,
  SettingsCard,
  FormActions,
  NoticeCallout,
} from '../ui';

// Mirrors boneio/schema/actions.yaml. Hardcoded rather than derived from the
// JSON schema: this page is not schema-driven, and threading the schema in for
// three lists would cost more than it saves.
const ACTION_TYPE_OPTIONS = ['output', 'cover', 'virtual_switch', 'mqtt', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'];
const ACTION_OUTPUT_OPTIONS = ['TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET'];
const ACTION_COVER_OPTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE'];

/** What the running controller says about a switch the config only describes. */
interface SwitchStatus {
  id: string;
  name: string;
  state: string;
  last_changed: number | null;
  on_turn_on: number;
  on_turn_off: number;
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
  allVirtualSwitches: Record<string, unknown>[];
}

const NO_ENTITIES: EntityLists = {
  allOutputs: [],
  allOutputGroups: [],
  allCovers: [],
  allAreas: [],
  allRemoteDevices: [],
  allBinarySensors: [],
  allRemoteInputs: [],
  allVirtualSwitches: [],
};

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

/**
 * Virtual switches: flags with no hardware, read by conditions and set by actions.
 *
 * Its own page rather than a generated form, for the same reason Schedules has
 * one: the interesting half of a virtual switch is the two action lists it
 * carries, and a generated array table has nowhere to put a list of actions
 * nested under an edge. The live state and a toggle are here too — a flag that
 * runs actions is worth testing from the page you configured it on.
 */
export default function VirtualSwitchSection() {
  const { t } = useTranslation();
  const [switches, setSwitches] = useState<SwitchEntry[]>([]);
  const [status, setStatus] = useState<Record<string, SwitchStatus>>({});
  const [entities, setEntities] = useState<EntityLists>(NO_ENTITIES);
  const [dirty, setDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);
  // One editor open at a time, as on the Schedules page: two action lists per
  // switch stacked down the page is a lot of scrolling that shows nothing at
  // a glance.
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [result, setResult] = useState<{ status: string; message: string } | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [{ data: config }, { data: state }] = await Promise.all([
        axios.get('/api/config'),
        axios.get('/api/virtual_switch'),
      ]);
      const parsed = config.config || {};
      setSwitches(parsed.virtual_switch || []);
      setEntities({
        allOutputs: parsed.output || [],
        allOutputGroups: parsed.output_group || [],
        allCovers: parsed.cover || [],
        allAreas: parsed.areas || [],
        allRemoteDevices: parsed.remote_devices || [],
        allBinarySensors: parsed.binary_sensor || [],
        allRemoteInputs: parsed.remote_inputs || [],
        allVirtualSwitches: parsed.virtual_switch || [],
      });
      const byId: Record<string, SwitchStatus> = {};
      for (const entry of state.virtual_switches || []) byId[entry.id] = entry;
      setStatus(byId);
      setDirty(false);
    } catch (err) {
      console.error('Failed to load virtual switches:', err);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchAll();
  }, [fetchAll]);

  const update = (index: number, mutate: (entry: SwitchEntry) => SwitchEntry) => {
    setSwitches((current) => current.map((entry, i) => (i === index ? mutate({ ...entry }) : entry)));
    setDirty(true);
  };

  const updateEdge = (index: number, edge: Edge, next: ActionEntry[]) => {
    update(index, (entry) => withEdgeActions(entry, edge, next));
  };

  const addSwitch = () => {
    setSwitches((current) => [
      ...current,
      {
        id: `switch_${current.length + 1}`,
        name: '',
        restore_state: true,
        initial: false,
        show_in_ha: true,
      },
    ]);
    setOpenIndex(switches.length);
    setDirty(true);
  };

  const save = async () => {
    setIsSaving(true);
    setResult(null);
    try {
      await axios.put('/api/config/virtual_switch', switches);
      await axios.post('/api/config/reload', ['virtual_switch'], { timeout: 30000 });
      setResult({ status: 'success', message: t('virtual_switch.saved') });
      await fetchAll();
    } catch (err: unknown) {
      setResult({ status: 'error', message: errorDetail(err) || t('virtual_switch.save_failed') });
    } finally {
      setIsSaving(false);
    }
  };

  const toggle = async (id: string) => {
    setToggling(id);
    setResult(null);
    try {
      await axios.post(`/api/virtual_switch/${encodeURIComponent(id)}/toggle`);
      await fetchAll();
    } catch (err: unknown) {
      setResult({ status: 'error', message: errorDetail(err) || t('virtual_switch.toggle_failed') });
    } finally {
      setToggling(null);
    }
  };

  const hint = useMemo(
    () => `${switches.length} ${t('virtual_switch.count')}`,
    [switches.length, t],
  );

  /** The action editor for one edge of one switch. */
  const renderEdge = (entry: SwitchEntry, index: number, edge: Edge) => {
    const actions = entry.actions?.[edge] || [];
    return (
      <div className="space-y-2">
        <div className="divider text-xs opacity-70 my-1">{t(`virtual_switch.${edge}`)}</div>
        {actions.length === 0 && (
          <p className="text-xs opacity-50">{t(`virtual_switch.${edge}_empty`)}</p>
        )}
        {actions.map((action, actionIndex) => (
          <ActionFields
            key={actionIndex}
            action={action}
            index={actionIndex}
            onUpdate={(field, value) =>
              updateEdge(
                index,
                edge,
                actions.map((a, i) => (i === actionIndex ? applyActionUpdate(a, field, value) : a)),
              )
            }
            onRemove={() => updateEdge(index, edge, actions.filter((_, i) => i !== actionIndex))}
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
            updateEdge(index, edge, [...actions, { action: 'output', action_output: edge === 'on_turn_on' ? 'ON' : 'OFF' }])
          }
        >
          <FaPlus className="w-2.5 h-2.5" />
          {t('virtual_switch.add_action')}
        </button>
      </div>
    );
  };

  return (
    <SettingsPage>
      <SettingsCard
        footer={
          <FormActions hint={hint}>
            <button className="btn btn-ghost btn-sm gap-2" onClick={addSwitch}>
              <FaPlus className="w-3 h-3" />
              {t('virtual_switch.add')}
            </button>
            <button className="btn btn-primary btn-sm gap-2" onClick={save} disabled={isSaving || !dirty}>
              {isSaving ? <><FaSpinner className="animate-spin" />{t('virtual_switch.saving')}</>
                        : <><FaCheck />{t('virtual_switch.save')}</>}
            </button>
          </FormActions>
        }
      >
        <div className="space-y-4">
          <p className="text-xs opacity-60">{t('virtual_switch.description')}</p>

          {switches.length === 0 && (
            <NoticeCallout variant="info" message={t('virtual_switch.empty')} />
          )}

          {switches.length > 0 && (
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th className="w-10"></th>
                    <th>{t('virtual_switch.column_name')}</th>
                    <th>{t('virtual_switch.column_actions')}</th>
                    <th>{t('virtual_switch.column_restore')}</th>
                    <th className="w-16"></th>
                  </tr>
                </thead>
                <tbody>
                  {switches.map((entry, index) => {
                    const state = status[entry.id];
                    const open = openIndex === index;
                    const on = state?.state === 'ON';
                    const counts = EDGES.map((edge) => (entry.actions?.[edge] || []).length);
                    return (
                      <Fragment key={index}>
                        <tr
                          className={`hover cursor-pointer ${open ? 'bg-base-200' : ''}`}
                          onClick={() => setOpenIndex(open ? null : index)}
                        >
                          <td onClick={(e) => e.stopPropagation()}>
                            {/* Flips the live switch, it does not edit the
                                config — which is why it is disabled until
                                what is on screen has been saved. */}
                            <button
                              type="button"
                              className={`btn btn-xs btn-square ${on ? 'btn-success' : 'btn-ghost'}`}
                              onClick={() => toggle(entry.id)}
                              disabled={!state || dirty || toggling === entry.id}
                              title={dirty ? t('virtual_switch.toggle_needs_save') : t('virtual_switch.toggle')}
                            >
                              {toggling === entry.id
                                ? <FaSpinner className="animate-spin w-3 h-3" />
                                : <FaPowerOff className="w-3 h-3" />}
                            </button>
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
                          <td>
                            <div className="flex flex-wrap gap-1">
                              {counts[0] > 0 && (
                                <span className="badge badge-ghost badge-xs">{`${t('virtual_switch.on_turn_on')}: ${counts[0]}`}</span>
                              )}
                              {counts[1] > 0 && (
                                <span className="badge badge-ghost badge-xs">{`${t('virtual_switch.on_turn_off')}: ${counts[1]}`}</span>
                              )}
                              {counts[0] + counts[1] === 0 && (
                                <span className="text-xs opacity-40">{t('virtual_switch.flag_only')}</span>
                              )}
                            </div>
                          </td>
                          <td className="text-xs">
                            {entry.restore_state === false
                              ? `${t('virtual_switch.initial')}: ${entry.initial ? 'ON' : 'OFF'}`
                              : t('virtual_switch.restored')}
                          </td>
                          <td onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-end">
                              <button
                                type="button"
                                className="btn btn-ghost btn-xs btn-square text-error"
                                onClick={() => {
                                  setSwitches((current) => current.filter((_, i) => i !== index));
                                  setOpenIndex(null);
                                  setDirty(true);
                                }}
                                title={t('virtual_switch.remove')}
                              >
                                <FaTrash className="w-3 h-3" />
                              </button>
                            </div>
                          </td>
                        </tr>

                        {open && (
                          <tr>
                            <td colSpan={5} className="bg-base-200/40">
                              <div className="space-y-3 p-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <input
                                    type="text"
                                    className="input input-bordered input-sm"
                                    placeholder={t('virtual_switch.name')}
                                    value={entry.name || ''}
                                    onChange={(e) => update(index, (s) => ({ ...s, name: e.target.value }))}
                                  />
                                  <input
                                    type="text"
                                    className="input input-bordered input-sm w-40 font-mono"
                                    placeholder="id"
                                    value={entry.id || ''}
                                    onChange={(e) => update(index, (s) => ({ ...s, id: e.target.value }))}
                                  />
                                  <input
                                    type="text"
                                    className="input input-bordered input-sm w-44 font-mono"
                                    placeholder="mdi:weather-night"
                                    value={entry.icon || ''}
                                    onChange={(e) => update(index, (s) => ({ ...s, icon: e.target.value }))}
                                  />
                                </div>

                                <div className="flex flex-wrap items-center gap-4">
                                  <label className="label cursor-pointer gap-2 py-0">
                                    <input
                                      type="checkbox"
                                      className="toggle toggle-xs"
                                      checked={entry.restore_state !== false}
                                      onChange={(e) => update(index, (s) => ({ ...s, restore_state: e.target.checked }))}
                                    />
                                    <span className="label-text text-xs">{t('virtual_switch.restore_state')}</span>
                                  </label>
                                  <label className="label cursor-pointer gap-2 py-0">
                                    <input
                                      type="checkbox"
                                      className="toggle toggle-xs"
                                      checked={entry.initial === true}
                                      onChange={(e) => update(index, (s) => ({ ...s, initial: e.target.checked }))}
                                      disabled={entry.restore_state !== false}
                                    />
                                    <span className="label-text text-xs">{t('virtual_switch.initial_on')}</span>
                                  </label>
                                  <label className="label cursor-pointer gap-2 py-0">
                                    <input
                                      type="checkbox"
                                      className="toggle toggle-xs"
                                      checked={entry.show_in_ha !== false}
                                      onChange={(e) => update(index, (s) => ({ ...s, show_in_ha: e.target.checked }))}
                                    />
                                    <span className="label-text text-xs">{t('virtual_switch.show_in_ha')}</span>
                                  </label>
                                </div>

                                <NoticeCallout variant="info" message={t('virtual_switch.actions_hint')} />

                                {renderEdge(entry, index, 'on_turn_on')}
                                {renderEdge(entry, index, 'on_turn_off')}
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
