import React, { useEffect, useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import ActionConditions from './ActionFields/ActionConditions';
import ActionRowList from './ActionFields/ActionRowList';
import { applyActionUpdate } from './ActionFields/helpers';
import { CardSection, FormField, MoreOptions } from './ui';
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
}

/**
 * Editor for one schedule.
 *
 * One scrolling page, not tabs. A schedule is a single sentence — *when* this
 * happens, *only if* that holds, *do* these things — and the three parts are
 * read together: you pick an action while looking at the trigger it hangs off.
 * Tabs are right for an input, where single/double/long are alternatives you
 * never need side by side; they were wrong here.
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
}) => {
  const { t } = useTranslation();
  const { hasLocation } = useConfig();
  const trigger = data.trigger || {};
  const kind = trigger.type || 'sun';
  const actions = data.actions || [];

  const entities = {
    allOutputs,
    allOutputGroups,
    allCovers,
    allAreas,
    allRemoteDevices,
    allBinarySensors,
    allRemoteInputs,
    allVirtualSwitches,
    savedOutputs,
    savedOutputGroups,
    savedCovers,
  };

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

      {/* The id first, and called what it is: this is the word you type once
          and then use everywhere — in the MQTT topic, in a condition, in
          another switch's action. The friendly `name` is the longer label
          Home Assistant shows, which is a description of the same thing. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <FormField label={t('common.name')} help={t('schedule.id_hint')}>
          <input
            type="text"
            className="input input-bordered w-full font-mono"
            value={data.id || ''}
            onChange={(e) => updateField('id', sanitizeId(e.target.value))}
          />
        </FormField>
        <FormField label={t('common.description')} help={t('common.description_hint')}>
          <input
            type="text"
            className="input input-bordered w-full"
            value={data.name || ''}
            onChange={(e) => updateField('name', e.target.value)}
          />
        </FormField>
      </div>

      <label className="cursor-pointer flex items-center gap-2">
        <input
          type="checkbox"
          className="toggle toggle-sm"
          checked={data.enabled !== false}
          onChange={(e) => updateField('enabled', e.target.checked)}
        />
        <span className="text-sm">{t('schedule.enabled')}</span>
      </label>

      <CardSection title={t('schedule.section_when')} divided>
        {/* Four fields for a sun trigger, three for a clock one — the offset
            is not offered there. A fixed four columns left the clock trigger
            with an empty quarter. */}
        <div className={`grid grid-cols-1 sm:grid-cols-2 gap-3 ${kind === 'sun' ? 'lg:grid-cols-4' : 'lg:grid-cols-3'}`}>
          <FormField label={t('schedule.trigger_type')}>
            <Select value={kind} onValueChange={(value) => updateTrigger('type', value)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {/* Greyed out rather than hidden without coordinates: seeing
                    that the option exists, and being told why it is
                    unavailable, beats wondering where it went. A schedule that
                    already uses one stays selectable, or removing the location
                    would blank the field. */}
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
                <SelectTrigger className="w-full">
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
                className="input input-bordered w-full"
                value={trigger.at || ''}
                onChange={(e) => updateTrigger('at', e.target.value)}
              />
            </FormField>
          )}

          <FormField label={t('schedule.days')}>
            <Select value={trigger.days || 'daily'} onValueChange={(value) => updateTrigger('days', value)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {DAY_OPTIONS.map((day) => (
                  <SelectItem key={day} value={day}>{t(`schedule.days_${day}`)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>

          {kind === 'sun' && (
            <FormField label={t('schedule.offset')} help={t('schedule.offset_hint')}>
              <label className="input input-bordered flex items-center gap-1 w-full">
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
          )}


        </div>
      </CardSection>

      <CardSection
        title={t('schedule.section_only_if')}
        description={t('schedule.section_only_if_hint')}
        divided
      >
        {/* The schedule's own conditions gate the whole firing. Each action may
            still carry its own, below. */}
        <ActionConditions
          hideHeading
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
      </CardSection>

      <CardSection title={t('schedule.section_do')} divided>
        <ActionRowList
          actions={actions}
          onChange={setActions}
          newAction={() => ({ action: 'output', action_output: 'TOGGLE' })}
          emptyText={t('schedule.no_actions_hint')}
          entities={entities}
          actionTypeOptions={ACTION_TYPE_OPTIONS}
          actionOutputOptions={ACTION_OUTPUT_OPTIONS}
          actionCoverOptions={ACTION_COVER_OPTIONS}
          attemptedSubmit={attemptedSubmit}
        />
      </CardSection>

      <MoreOptions
        label={t('common.more_options')}
        summary={`${t('schedule.jitter')} · ${t('schedule.on_missed')}`}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FormField label={t('schedule.jitter')} help={t('schedule.jitter_hint')}>
            <label className="input input-bordered flex items-center gap-1 w-full">
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
            <Select value={data.on_missed || 'skip'} onValueChange={(value) => updateField('on_missed', value)}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="skip">{t('schedule.on_missed_skip')}</SelectItem>
                <SelectItem value="run">{t('schedule.on_missed_run')}</SelectItem>
              </SelectContent>
            </Select>
          </FormField>
        </div>
      </MoreOptions>

    </div>
  );
};

export default ScheduleForm;
