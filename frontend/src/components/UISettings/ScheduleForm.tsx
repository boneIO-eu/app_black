import React, { useEffect, useMemo, useState } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '../../hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import { TabsBox } from '@/components/ui/tabs-box';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import ActionFields, { cleanActionFields } from './ActionFields';
import ActionConditions from './ActionFields/ActionConditions';
import { applyActionUpdate } from './ActionFields/helpers';
import { FormField } from './ui';
import { sanitizeId } from './helpers/idValidation';
import type { CoverEntity, OutputEntity, BinarySensorEntity } from '@/types/config';
import type { RemoteDevice } from './ActionFields/types';
import {
  DAY_OPTIONS,
  SUN_EVENT_GROUPS,
  minutesToOffset,
  offsetToMinutes,
  withTriggerField,
  type ActionEntry,
  type ScheduleEntry,
  type ScheduleTrigger,
} from './helpers/scheduleTrigger';

// Mirrors boneio/schema/actions.yaml.
const ACTION_TYPE_OPTIONS = ['output', 'cover', 'virtual_switch', 'mqtt', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'];
const ACTION_OUTPUT_OPTIONS = ['TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET'];
const ACTION_COVER_OPTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE'];

interface Area {
  id: string;
  name: string;
}

interface ScheduleFormProps {
  data: ScheduleEntry;
  onChange: (data: ScheduleEntry) => void;
  allOutputs?: OutputEntity[];
  allOutputGroups?: Record<string, unknown>[];
  allCovers?: CoverEntity[];
  allAreas?: Area[];
  allRemoteDevices?: RemoteDevice[];
  allBinarySensors?: BinarySensorEntity[];
  allRemoteInputs?: Record<string, unknown>[];
  allVirtualSwitches?: Record<string, unknown>[];
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: Record<string, unknown>[];
  savedCovers?: CoverEntity[];
  existingItems?: ScheduleEntry[];
  editingIndex?: number | null;
  onValidationChange?: (hasErrors: boolean) => void;
  attemptedSubmit?: boolean;
  /** Opens straight on one of the tabs, e.g. from a deep link. */
  initialTab?: string;
}

/**
 * Editor for one schedule.
 *
 * Four tabs, because the four things are independent: what it is called, when
 * it fires, whether it is allowed to, and what it does. The old page stacked
 * all four down a table row, which meant the actions were a screen and a half
 * below the trigger they belong to.
 */
const ScheduleForm: React.FC<ScheduleFormProps> = ({
  data,
  onChange,
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allRemoteDevices = [],
  allBinarySensors = [],
  allRemoteInputs = [],
  allVirtualSwitches = [],
  savedOutputs,
  savedOutputGroups,
  savedCovers,
  existingItems = [],
  editingIndex = null,
  onValidationChange,
  attemptedSubmit = false,
  initialTab,
}) => {
  const { t } = useTranslation();
  const { hasLocation } = useConfig();
  const validTabs = new Set(['basic', 'trigger', 'conditions', 'actions']);
  const [activeTab, setActiveTab] = useState<string>(
    initialTab && validTabs.has(initialTab) ? initialTab : 'basic',
  );

  const trigger = data.trigger || {};
  const kind = trigger.type || 'sun';
  const actions = data.actions || [];

  const errors = useMemo(() => {
    const found: string[] = [];
    const id = (data.id || '').trim();
    if (!id) {
      found.push(t('schedule.error_id_required'));
    } else if (existingItems.some((other, index) => index !== editingIndex && other.id === id)) {
      found.push(t('schedule.error_id_duplicate'));
    }
    if (kind === 'sun' && !trigger.event) found.push(t('schedule.error_event_required'));
    if (kind === 'time' && !trigger.at) found.push(t('schedule.error_at_required'));
    // A sun trigger without coordinates can never resolve, so the schedule
    // would sit there looking configured and never fire.
    if (kind === 'sun' && !hasLocation) found.push(t('schedule.needs_location'));
    return found;
  }, [data.id, existingItems, editingIndex, kind, trigger.event, trigger.at, hasLocation, t]);

  useEffect(() => {
    onValidationChange?.(errors.length > 0);
  }, [errors.length, onValidationChange]);

  const updateField = (field: keyof ScheduleEntry, value: unknown) => onChange({ ...data, [field]: value });

  const updateTrigger = (field: keyof ScheduleTrigger, value: string | undefined) =>
    onChange({ ...data, trigger: withTriggerField(data.trigger, field, value) });

  const setActions = (next: ActionEntry[]) => onChange({ ...data, actions: next });

  return (
    <div className="space-y-4 py-2">
      {attemptedSubmit && errors.length > 0 && (
        <div className="alert alert-error">
          <ul className="list-disc list-inside text-sm">
            {errors.map((error) => <li key={error}>{error}</li>)}
          </ul>
        </div>
      )}

      <TabsBox
        name="schedule_tabs"
        activeTab={activeTab}
        onTabChange={setActiveTab}
        tabs={[
          {
            id: 'basic',
            label: t('settings.basic_settings'),
            content: (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('outputs.display_name')}</span>
                    </label>
                    <input
                      type="text"
                      className="input w-full"
                      value={data.name || ''}
                      onChange={(e) => updateField('name', e.target.value)}
                    />
                    <label className="label">
                      <span className="label-text-alt">{t('common.optional')}</span>
                    </label>
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">ID</span>
                    </label>
                    <input
                      type="text"
                      className="input w-full font-mono"
                      value={data.id || ''}
                      onChange={(e) => updateField('id', sanitizeId(e.target.value))}
                    />
                  </div>
                </div>

                <label className="label cursor-pointer gap-2 justify-start">
                  <input
                    type="checkbox"
                    className="toggle toggle-sm"
                    checked={data.enabled !== false}
                    onChange={(e) => updateField('enabled', e.target.checked)}
                  />
                  <span className="label-text">{t('schedule.enabled')}</span>
                </label>

                <div className="alert alert-info">
                  <span className="text-sm">{t('schedule.description')}</span>
                </div>
              </div>
            ),
          },
          {
            id: 'trigger',
            label: t('schedule.column_trigger'),
            content: (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <FormField label={t('schedule.trigger_type')}>
                  <Select value={kind} onValueChange={(value) => updateTrigger('type', value)}>
                    <SelectTrigger className="w-full h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {/* Greyed out rather than hidden without coordinates: seeing
                          that the option exists, and being told why it is
                          unavailable, beats wondering where it went. A schedule
                          that already uses one stays selectable, or removing the
                          location would blank the field. */}
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
                    <Select value={trigger.event || ''} onValueChange={(value) => updateTrigger('event', value)}>
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
                      onChange={(e) => updateTrigger('at', e.target.value)}
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
                      onChange={(e) => updateTrigger('offset', minutesToOffset(e.target.value))}
                    />
                    <span className="text-xs opacity-60 shrink-0">{t('event_form.condition_sun_minutes')}</span>
                  </label>
                </FormField>

                <FormField label={t('schedule.days')}>
                  <Select value={trigger.days || 'daily'} onValueChange={(value) => updateTrigger('days', value)}>
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
                      onChange={(e) => updateTrigger('jitter', minutesToOffset(e.target.value))}
                    />
                    <span className="text-xs opacity-60 shrink-0">{t('event_form.condition_sun_minutes')}</span>
                  </label>
                </FormField>

                <FormField label={t('schedule.on_missed')} help={t('schedule.on_missed_hint')}>
                  <Select
                    value={data.on_missed || 'skip'}
                    onValueChange={(value) => updateField('on_missed', value)}
                  >
                    <SelectTrigger className="w-full h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="skip">{t('schedule.on_missed_skip')}</SelectItem>
                      <SelectItem value="run">{t('schedule.on_missed_run')}</SelectItem>
                    </SelectContent>
                  </Select>
                </FormField>
              </div>
            ),
          },
          {
            id: 'conditions',
            label: t('event_form.conditions'),
            content: (
              <div className="space-y-2">
                {/* The schedule's own conditions gate the whole firing. Each
                    action may still carry its own, edited on the next tab. */}
                <ActionConditions
                  action={data}
                  onUpdate={(field, value) => onChange(applyActionUpdate(data, field, value) as ScheduleEntry)}
                  t={t}
                  allOutputs={allOutputs}
                  allCovers={allCovers}
                  allBinarySensors={allBinarySensors}
                  allRemoteInputs={allRemoteInputs}
                  allVirtualSwitches={allVirtualSwitches}
                  allAreas={allAreas}
                />
              </div>
            ),
          },
          {
            id: 'actions',
            label: t('schedule.actions'),
            badge: actions.length || undefined,
            content: (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold">{t('schedule.actions')}</h3>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => setActions([...actions, { action: 'output', action_output: 'TOGGLE' }])}
                  >
                    <FaPlus className="mr-2" />
                    {t('inputs.add_action')}
                  </button>
                </div>

                {actions.length > 0 ? (
                  actions.map((action, index) => (
                    <ActionFields
                      key={index}
                      action={action}
                      index={index}
                      onUpdate={(field, value) =>
                        setActions(
                          actions.map((current, i) => {
                            if (i !== index) return current;
                            return field === 'action'
                              ? (cleanActionFields(value, current) as ActionEntry)
                              : applyActionUpdate(current, field, value);
                          }),
                        )
                      }
                      onRemove={() => setActions(actions.filter((_, i) => i !== index))}
                      allOutputs={allOutputs}
                      allOutputGroups={allOutputGroups}
                      allCovers={allCovers}
                      allAreas={allAreas}
                      allRemoteDevices={allRemoteDevices}
                      allBinarySensors={allBinarySensors}
                      allRemoteInputs={allRemoteInputs}
                      allVirtualSwitches={allVirtualSwitches}
                      actionTypeOptions={ACTION_TYPE_OPTIONS}
                      actionOutputOptions={ACTION_OUTPUT_OPTIONS}
                      actionCoverOptions={ACTION_COVER_OPTIONS}
                      showValidation={attemptedSubmit}
                      savedOutputs={savedOutputs}
                      savedOutputGroups={savedOutputGroups}
                      savedCovers={savedCovers}
                    />
                  ))
                ) : (
                  <div className="text-center py-8 text-base-content/60">
                    <p>{t('schedule.no_actions')}</p>
                    <p className="text-sm">{t('event_form.click_add_action')}</p>
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default ScheduleForm;
