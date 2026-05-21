/**
 * RemoteInputForm — dedicated form for editing remote (ESPHome) binary sensor inputs.
 *
 * Reuses the same layout, ActionFields, AreaSelect, TabsBox and InputTypeSwitcher
 * as BinarySensorForm / EventForm but omits GPIO-specific fields:
 *   - boneio_input (replaced by read-only sensor ID)
 *   - bounce_time  (not applicable to remote inputs)
 *   - initial_send (not applicable)
 *   - clear_message (not applicable)
 *
 * The show_in_ha toggle defaults to OFF and uses remote-specific labels.
 */
import React, { useState } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import ActionFields, { validateAction, cleanActionFields } from './ActionFields';
import AiConfigAssistant from './AiConfigAssistant';
import AreaSelect from './widgets/AreaSelect';
import { TabsBox } from '@/components/ui/tabs-box';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type {
  AreaEntity,
  OutputEntity,
  CoverEntity,
  BinarySensorEntity,
  RemoteDeviceEntity,
  Action,
} from '@/types/config';

/* ------------------------------------------------------------------ */
/*  Device class options — same as BinarySensorForm                    */
/* ------------------------------------------------------------------ */
const DEFAULT_DEVICE_CLASSES = [
  'battery', 'battery_charging', 'carbon_monoxide', 'cold', 'connectivity',
  'door', 'garage_door', 'gas', 'heat', 'light', 'lock', 'moisture',
  'motion', 'moving', 'occupancy', 'opening', 'plug', 'power', 'presence',
  'problem', 'running', 'safety', 'smoke', 'sound', 'tamper', 'vibration', 'window',
];

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */
interface RemoteInputFormProps {
  data: any;
  onChange: (data: any) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  allOutputs?: OutputEntity[];
  allOutputGroups?: any[];
  allCovers?: CoverEntity[];
  allAreas?: AreaEntity[];
  allRemoteDevices?: RemoteDeviceEntity[];
  allBinarySensors?: BinarySensorEntity[];
  onValidationChange?: (hasErrors: boolean) => void;
  attemptedSubmit?: boolean;
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: any[];
  savedCovers?: CoverEntity[];
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
const RemoteInputForm: React.FC<RemoteInputFormProps> = ({
  data,
  onChange,
  schema,
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allRemoteDevices = [],
  allBinarySensors = [],
  onValidationChange,
  attemptedSubmit = false,
  savedOutputs,
  savedOutputGroups,
  savedCovers,
}) => {
  const { t } = useTranslation();

  // Determine mode from data (binary_sensor vs event)
  const mode: 'binary_sensor' | 'event' =
    data.mode === 'event' || data._type === 'event' ? 'event' : 'binary_sensor';

  // State for active tab — differs per mode
  const [bsTab, setBsTab] = useState<'basic' | 'pressed' | 'released'>('basic');
  const [evTab, setEvTab] = useState<
    'basic' | 'single' | 'double' | 'triple' | 'long' | 'sequences' | 'advanced'
  >('basic');

  /* ---------- schema-derived enums ---------- */
  const deviceClassOptions =
    schema?.items?.properties?.device_class?.enum || DEFAULT_DEVICE_CLASSES;
  const actionTypeOptions =
    schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action?.enum ||
    schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action?.enum || [
      'mqtt', 'output', 'cover', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover',
    ];
  const actionOutputOptions =
    schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action_output?.enum ||
    schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action_output?.enum || [
      'TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET',
    ];
  const actionCoverOptions =
    schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action_cover?.enum ||
    schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action_cover?.enum || [
      'TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE',
    ];

  /* ---------- field helpers ---------- */
  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  /* ---------- action CRUD (shared for both modes) ---------- */
  const updateAction = (type: string, index: number, field: string, value: any) => {
    const actions = { ...data.actions };
    if (!actions[type]) actions[type] = [];
    const updated = [...actions[type]];

    if (field === 'action') {
      updated[index] = cleanActionFields(value, updated[index]) as any;
    } else if (field === '__batch') {
      const cur = { ...updated[index] };
      for (const [k, v] of Object.entries(value as Record<string, any>)) {
        if (v === undefined) delete cur[k];
        else cur[k] = v;
      }
      updated[index] = cur;
    } else if (field === 'remote_device') {
      updated[index] = { ...updated[index], [field]: value, output_id: undefined, cover_id: undefined, presets: undefined, colors: undefined };
    } else if (field === 'output_id') {
      updated[index] = { ...updated[index], [field]: value, presets: undefined, colors: undefined };
    } else if (field === 'boneio_output' || field === 'boneio_cover') {
      const { pin, ...rest } = updated[index] || {};
      updated[index] = { ...rest, [field]: value };
    } else {
      updated[index] = { ...updated[index], [field]: value };
    }

    actions[type] = updated;
    onChange({ ...data, actions });
  };

  const addAction = (type: string) => {
    const actions = { ...data.actions };
    if (!actions[type]) actions[type] = [];
    actions[type] = [...actions[type], { action: 'output' }];
    onChange({ ...data, actions });
  };

  const removeAction = (type: string, index: number) => {
    const actions = { ...data.actions };
    if (!actions[type]) return;
    actions[type] = actions[type].filter((_: any, i: number) => i !== index);
    onChange({ ...data, actions });
  };

  const updateMqttSequence = (seqType: string, enabled: boolean) => {
    onChange({ ...data, mqtt_sequences: { ...data.mqtt_sequences, [seqType]: enabled } });
  };

  /* ---------- validation ---------- */
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    const actionTypes =
      mode === 'event'
        ? ['single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single']
        : ['pressed', 'released'];

    actionTypes.forEach((type) => {
      const acts = data.actions?.[type] || [];
      acts.forEach((action: any, idx: number) => {
        const err = validateAction(action, t);
        if (err) errors.push(`${type} action ${idx + 1}: ${err}`);
      });
    });
    return errors;
  };

  const validationErrors = getValidationErrors();
  React.useEffect(() => {
    onValidationChange?.(validationErrors.length > 0);
  }, [validationErrors.length, onValidationChange]);

  /* ---------- render a single ActionFields row ---------- */
  const renderActionRow = (action: Action, type: string, index: number) => (
    <ActionFields
      key={index}
      action={action}
      index={index}
      onUpdate={(field, value) => updateAction(type, index, field, value)}
      onRemove={() => removeAction(type, index)}
      allOutputs={allOutputs}
      allOutputGroups={allOutputGroups}
      allCovers={allCovers}
      allAreas={allAreas}
      allRemoteDevices={allRemoteDevices}
      actionTypeOptions={actionTypeOptions}
      actionOutputOptions={actionOutputOptions}
      actionCoverOptions={actionCoverOptions}
      showValidation={attemptedSubmit}
      savedOutputs={savedOutputs}
      savedOutputGroups={savedOutputGroups}
      savedCovers={savedCovers}
      clickType={type as 'pressed' | 'released' | 'single' | 'double' | 'triple' | 'long' | 'double_then_long' | 'single_then_long' | 'double_then_single'}
      allBinarySensors={allBinarySensors}
      excludeEntityId={data.id}
    />
  );

  /* ---------- helper: action tab panel ---------- */
  const actionTabContent = (type: string, labelKey: string, emptyKey: string) => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">{t(labelKey)}</h3>
        <button type="button" onClick={() => addAction(type)} className="btn btn-primary btn-sm">
          <FaPlus className="mr-2" />
          {t('inputs.add_action')}
        </button>
      </div>
      {data.actions?.[type]?.length > 0
        ? data.actions[type].map((a: Action, i: number) => renderActionRow(a, type, i))
        : (
          <div className="text-center py-8 text-base-content/60">
            <p>{t(emptyKey)}</p>
            <p className="text-sm">{t('inputs.click_add_action')}</p>
          </div>
        )}
    </div>
  );

  /* ================================================================ */
  /*  BASIC SETTINGS panel — shared across both modes                  */
  /* ================================================================ */
  const basicSettings = (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Display Name */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('outputs.display_name')}</span>
          </label>
          <input
            type="text"
            className="input w-full"
            placeholder={t('sensors.binary_sensor_name_placeholder')}
            value={data.name || ''}
            onChange={(e) => updateField('name', e.target.value)}
          />
          <label className="label">
            <span className="label-text-alt">{t('common.optional')}</span>
          </label>
        </div>

        {/* Custom Input ID */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('inputs.custom_input_id')}</span>
          </label>
          <input
            type="text"
            className="input w-full"
            placeholder={t('inputs.custom_input_id_placeholder')}
            value={data.id || ''}
            onChange={(e) => updateField('id', e.target.value)}
          />
          <label className="label">
            <span className="label-text-alt">{t('inputs.custom_input_id_hint')}</span>
          </label>
        </div>

        {/* Remote Device (device_id) — only devices with binary sensors */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('remote_devices.device')}</span>
          </label>
          <Select
            value={data.device_id || '_none_'}
            onValueChange={(v) => {
              const deviceId = v === '_none_' ? '' : v;
              const device = allRemoteDevices.find(d => d.id === deviceId);
              // Auto-set remote_source from device protocol
              const protocol = device?.protocol || 'esphome_api';
              onChange({ ...data, device_id: deviceId, input_id: '', remote_source: protocol });
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('remote_devices.select_device')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_none_">{t('remote_devices.select_device')}</SelectItem>
              {allRemoteDevices
                .filter((device) => {
                  // Only show devices that have discoverable binary sensors
                  const bs = device.esphome_api?.binary_sensors || device.esphome_api?._discovered_binary_sensors;
                  return bs && bs.length > 0;
                })
                .map((device) => {
                  const protocolLabel =
                    device.protocol === 'esphome_api' ? 'ESPHome API' :
                    device.protocol === 'wled' ? 'WLED' :
                    device.protocol === 'mqtt' ? 'MQTT' :
                    device.protocol || '';
                  return (
                    <SelectItem key={device.id} value={device.id}>
                      {device.name || device.id}{protocolLabel ? ` (${protocolLabel})` : ''}
                    </SelectItem>
                  );
                })}
            </SelectContent>
          </Select>
          {attemptedSubmit && !data.device_id && (
            <label className="label">
              <span className="label-text-alt text-error">{t('validation.required')}</span>
            </label>
          )}
        </div>

        {/* Input/Sensor ID (input_id) — dropdown from selected device's binary sensors */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('inputs.device_input')}</span>
          </label>
          {(() => {
            const selectedDevice = allRemoteDevices.find(d => d.id === data.device_id);
            const availableInputs: Array<{ id: string; name?: string }> =
              selectedDevice?.esphome_api?.binary_sensors ||
              selectedDevice?.esphome_api?._discovered_binary_sensors ||
              [];
            return (
              <Select
                value={data.input_id || '_none_'}
                onValueChange={(v) => updateField('input_id', v === '_none_' ? '' : v)}
                disabled={!data.device_id}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={
                    data.device_id
                      ? t('remote_devices.select_device_first')
                      : t('remote_devices.select_device')
                  } />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none_">{t('inputs.select_input')}</SelectItem>
                  {availableInputs.map((input) => (
                    <SelectItem key={input.id} value={input.id}>
                      {input.name ? `${input.name} (${input.id})` : input.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            );
          })()}
          {attemptedSubmit && !data.input_id && (
            <label className="label">
              <span className="label-text-alt text-error">{t('validation.required')}</span>
            </label>
          )}
        </div>

        {/* Area */}
        <AreaSelect
          value={data.area}
          onChange={(v) => updateField('area', v)}
          areas={allAreas}
        />

        {/* Device class */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('inputs.device_class')}</span>
          </label>
          <Select
            value={data.device_class || '_none_'}
            onValueChange={(v) => updateField('device_class', v === '_none_' ? '' : v)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('inputs.none')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_none_">{t('inputs.none')}</SelectItem>
              {deviceClassOptions.map((dc: string) => (
                <SelectItem key={dc} value={dc}>
                  {dc.split('_').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* ---- Options ---- */}
      <div className="divider">{t('settings.options')}</div>

      <div className="grid grid-cols-1 gap-4">
        {/* Forward state to HA — default OFF */}
        <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
          <legend className="fieldset-legend">{t('inputs.forward_to_ha')}</legend>
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle toggle-primary"
              checked={data.show_in_ha === true}
              onChange={(e) => updateField('show_in_ha', e.target.checked)}
            />
            <span className="label-text wrap-break-word">{t('inputs.forward_to_ha_hint')}</span>
          </label>
        </fieldset>

        {/* Inverted */}
        <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
          <legend className="fieldset-legend">{t('inputs.inverted')}</legend>
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle toggle-primary"
              checked={data.inverted === true}
              onChange={(e) => updateField('inverted', e.target.checked)}
            />
            <span className="label-text">{t('inputs.inverted_hint')}</span>
          </label>
        </fieldset>
      </div>
    </div>
  );

  /* ================================================================ */
  /*  MODE: binary_sensor — tabs: Basic | Pressed | Released           */
  /* ================================================================ */
  if (mode === 'binary_sensor') {
    return (
      <div className="space-y-4">
        {/* Validation errors */}
        {attemptedSubmit && validationErrors.length > 0 && (
          <div className="alert alert-error sticky top-0 z-10">
            <ul className="list-disc list-inside">
              {validationErrors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}

        <AiConfigAssistant
          entityType="binary_sensor"
          data={data}
          schema={schema}
          allOutputs={allOutputs}
          allOutputGroups={allOutputGroups}
          allCovers={allCovers}
          allAreas={allAreas}
          allRemoteDevices={allRemoteDevices}
          actionTypeOptions={actionTypeOptions}
          actionOutputOptions={actionOutputOptions}
          actionCoverOptions={actionCoverOptions}
          onApply={onChange}
        />

        <TabsBox
          name="remote_bs_tabs"
          activeTab={bsTab}
          onTabChange={(id) => setBsTab(id as typeof bsTab)}
          tabs={[
            { id: 'basic', label: t('settings.basic_settings'), content: basicSettings },
            {
              id: 'pressed',
              label: t('inputs.pressed_actions'),
              badge: data.actions?.pressed?.length || undefined,
              content: actionTabContent('pressed', 'inputs.pressed_actions', 'inputs.no_pressed_actions'),
            },
            {
              id: 'released',
              label: t('inputs.released_actions'),
              badge: data.actions?.released?.length || undefined,
              content: actionTabContent('released', 'inputs.released_actions', 'inputs.no_released_actions'),
            },
          ]}
        />
      </div>
    );
  }

  /* ================================================================ */
  /*  MODE: event — tabs: Basic | Single | Double | Triple | Long |    */
  /*                       Sequences | Advanced                        */
  /* ================================================================ */
  return (
    <div className="space-y-4">
      {attemptedSubmit && validationErrors.length > 0 && (
        <div className="alert alert-error sticky top-0 z-10">
          <ul className="list-disc list-inside">
            {validationErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      <AiConfigAssistant
        entityType="event"
        data={data}
        schema={schema}
        allOutputs={allOutputs}
        allOutputGroups={allOutputGroups}
        allCovers={allCovers}
        allAreas={allAreas}
        allRemoteDevices={allRemoteDevices}
        actionTypeOptions={actionTypeOptions}
        actionOutputOptions={actionOutputOptions}
        actionCoverOptions={actionCoverOptions}
        onApply={onChange}
      />

      {/* DaisyUI Tabs */}
      <div role="tablist" className="tabs tabs-box">
        {(['basic', 'single', 'double', 'triple', 'long', 'sequences', 'advanced'] as const).map(
          (tabId) => {
            let label = '';
            if (tabId === 'basic') label = t('settings.basic_settings');
            else if (tabId === 'advanced') label = t('settings.advanced_settings');
            else if (tabId === 'sequences') {
              const seqCount =
                (data.actions?.double_then_long?.length || 0) +
                (data.actions?.single_then_long?.length || 0) +
                (data.actions?.double_then_single?.length || 0);
              label = `${t('event_form.sequences')}${seqCount ? ` (${seqCount})` : ''}`;
            } else {
              const count = data.actions?.[tabId]?.length || 0;
              const translationKey =
                tabId === 'single' ? 'event_form.single_click'
                : tabId === 'double' ? 'event_form.double_click'
                : tabId === 'triple' ? 'event_form.triple_click'
                : 'event_form.long_click';
              label = `${t(translationKey)}${count ? ` (${count})` : ''}`;
            }
            return (
              <input
                key={tabId}
                type="radio"
                name="remote_event_tabs"
                role="tab"
                className="tab"
                aria-label={label}
                checked={evTab === tabId}
                onChange={() => setEvTab(tabId)}
              />
            );
          },
        )}
      </div>

      <div className="border border-base-300 rounded-b-box rounded-tr-box bg-base-100 p-4">
        {evTab === 'basic' && basicSettings}

        {evTab === 'single' && actionTabContent('single', 'event_form.single_click', 'inputs.no_pressed_actions')}
        {evTab === 'double' && actionTabContent('double', 'event_form.double_click', 'inputs.no_pressed_actions')}
        {evTab === 'triple' && actionTabContent('triple', 'event_form.triple_click', 'inputs.no_pressed_actions')}
        {evTab === 'long' && actionTabContent('long', 'event_form.long_click', 'inputs.no_pressed_actions')}

        {/* Sequences tab */}
        {evTab === 'sequences' && (
          <div className="space-y-6">
            {(['double_then_long', 'single_then_long', 'double_then_single'] as const).map((seqType) => {
              const seqEnabled = data.mqtt_sequences?.[seqType] !== false;
              const labelKey =
                seqType === 'double_then_long' ? 'event_form.double_then_long'
                : seqType === 'single_then_long' ? 'event_form.single_then_long'
                : 'event_form.double_then_single';
              return (
                <div key={seqType} className="space-y-3">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="toggle toggle-sm toggle-primary"
                      checked={seqEnabled}
                      onChange={(e) => updateMqttSequence(seqType, e.target.checked)}
                    />
                    <h4 className="text-base font-semibold">{t(labelKey)}</h4>
                    {data.actions?.[seqType]?.length > 0 && (
                      <span className="badge badge-sm">{data.actions[seqType].length}</span>
                    )}
                  </div>
                  {seqEnabled && actionTabContent(seqType, labelKey, 'inputs.no_pressed_actions')}
                </div>
              );
            })}
          </div>
        )}

        {/* Advanced tab */}
        {evTab === 'advanced' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">{t('settings.advanced_settings')}</h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Double click window */}
              <div className="form-control">
              <SimpleTimePeriodInput
                  label={t('event_form.double_click_duration')}
                  value={data.double_click_duration || '220ms'}
                  onChange={(v) => updateField('double_click_duration', v)}
                  maximum={2000}
                  minimum={50}
                  allowedUnits={['ms', 's']}
                />
                <label className="label">
                  <span className="label-text-alt">{t('event_form.double_click_duration_hint')} ({t('common.default')}: 220ms)</span>
                </label>
              </div>

              {/* Long press threshold */}
              <div className="form-control">
                <SimpleTimePeriodInput
                  label={t('event_form.long_press_duration')}
                  value={data.long_press_duration || '400ms'}
                  onChange={(v) => updateField('long_press_duration', v)}
                  maximum={5000}
                  minimum={100}
                  allowedUnits={['ms', 's']}
                />
                <label className="label">
                  <span className="label-text-alt">{t('event_form.long_press_duration_hint')} ({t('common.default')}: 400ms)</span>
                </label>
              </div>

              {/* Sequence window */}
              <div className="form-control">
                <SimpleTimePeriodInput
                  label={t('event_form.sequence_window_duration')}
                  value={data.sequence_window_duration || '500ms'}
                  onChange={(v) => updateField('sequence_window_duration', v)}
                  maximum={5000}
                  minimum={100}
                  allowedUnits={['ms', 's']}
                />
                <label className="label">
                  <span className="label-text-alt">{t('event_form.sequence_window_duration_hint')} ({t('common.default')}: 500ms)</span>
                </label>
              </div>

              {/* Sequence mode */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('event_form.sequence_mode')}</span>
                </label>
                <Select
                  value={data.sequence_mode || 'exclusive'}
                  onValueChange={(v) => updateField('sequence_mode', v)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="exclusive">{t('event_form.sequence_mode_exclusive')}</SelectItem>
                    <SelectItem value="immediate">{t('event_form.sequence_mode_immediate')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Enable triple click */}
            <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
              <legend className="fieldset-legend">{t('event_form.enable_triple_click')}</legend>
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={data.enable_triple_click === true}
                  onChange={(e) => updateField('enable_triple_click', e.target.checked)}
                />
                <span className="label-text">{t('event_form.enable_triple_click_hint')}</span>
              </label>
            </fieldset>

            {/* Long press MQTT mode */}
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('event_form.long_press_mqtt_mode')}</span>
              </label>
              <Select
                value={data.long_press_mqtt_mode || 'single'}
                onValueChange={(v) => updateField('long_press_mqtt_mode', v)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">{t('event_form.long_press_mqtt_single')}</SelectItem>
                  <SelectItem value="periodic">{t('event_form.long_press_mqtt_periodic')}</SelectItem>
                </SelectContent>
              </Select>
              <label className="label">
                <span className="label-text-alt">
                  {data.long_press_mqtt_mode === 'periodic'
                    ? t('event_form.long_press_mqtt_periodic_hint')
                    : t('event_form.long_press_mqtt_single_hint')}
                </span>
              </label>
            </div>

            {/* Max long press duration */}
            <div className="form-control">
              <SimpleTimePeriodInput
                label={t('event_form.max_long_press_duration')}
                value={data.max_long_press_duration || '120s'}
                onChange={(v) => updateField('max_long_press_duration', v)}
                maximum={600000}
                minimum={1000}
                allowedUnits={['s']}
              />
              <label className="label">
                <span className="label-text-alt">{t('event_form.max_long_press_duration_hint')} ({t('common.default')}: 120s)</span>
              </label>
            </div>

            {/* Restore defaults */}
            <div className="mt-4">
              <button
                type="button"
                className="btn btn-sm btn-outline"
                onClick={() => {
                  updateField('double_click_duration', '220ms');
                  updateField('long_press_duration', '400ms');
                  updateField('sequence_window_duration', '500ms');
                  updateField('max_long_press_duration', '120s');
                }}
              >
                {t('event_form.restore_defaults')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RemoteInputForm;
