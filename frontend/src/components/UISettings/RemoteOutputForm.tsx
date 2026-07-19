/**
 * RemoteOutputForm — dedicated form for editing remote output entries.
 *
 * Lets the user:
 *   1. Pick a remote device (only devices with switches or lights)
 *   2. Pick an output (switch/light) from that device
 *   3. Set output_type (switch, light, valve)
 *   4. Set on_disconnect policy (ignore, turn_off)
 *   5. Optionally set name, id, area, show_in_ha
 *   6. Momentary turn on/off, adjustable duration (Advanced)
 *   7. Shared interlock groups with local outputs (Advanced)
 */
import React, { useState } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import AreaSelect from './widgets/AreaSelect';
import SettingsToggleGroup from './widgets/SettingsToggleGroup';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import { sanitizeId } from './helpers/idValidation';
import { TabsBox } from '@/components/ui/tabs-box';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type {
  AreaEntity,
  RemoteDeviceEntity,
} from '@/types/config';

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */
interface RemoteOutputFormProps {
  data: any;
  onChange: (data: any) => void;
  isNew: boolean;
  schema?: any;
  allAreas?: AreaEntity[];
  allRemoteDevices?: RemoteDeviceEntity[];
  existingItems?: any[];
  editingIndex?: number | null;
  onValidationChange?: (hasErrors: boolean) => void;
  attemptedSubmit?: boolean;
  interlockGroups?: string[];
  onInterlockGroupCreated?: (groupName: string) => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
const RemoteOutputForm: React.FC<RemoteOutputFormProps> = ({
  data,
  onChange,
  allAreas = [],
  allRemoteDevices = [],
  onValidationChange,
  attemptedSubmit = false,
  interlockGroups = [],
  onInterlockGroupCreated,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');
  const [newInterlockGroup, setNewInterlockGroup] = useState('');

  /* ---------- field helpers ---------- */
  const updateField = (field: string, value: any) => {
    const newData = { ...data, [field]: value };

    // When enabling adjustable_duration, clear static momentary (mutual exclusion)
    if (field === 'adjustable_duration' && value) {
      delete newData.momentary_turn_on;
      delete newData.momentary_turn_off;
    }

    // When disabling adjustable_duration, clean up related fields
    if (field === 'adjustable_duration' && !value) {
      delete newData.duration_default;
      delete newData.duration_min;
      delete newData.duration_max;
      delete newData.duration_unit;
    }

    // When setting momentary_turn_on, disable adjustable_duration (mutual exclusion)
    if (field === 'momentary_turn_on' && value) {
      delete newData.adjustable_duration;
      delete newData.duration_default;
      delete newData.duration_min;
      delete newData.duration_max;
      delete newData.duration_unit;
    }

    onChange(newData);
  };

  /* ---------- validation ---------- */
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    if (!data.device_id) errors.push(t('validation.required') + ': ' + t('remote_devices.device'));
    if (!data.output_id) errors.push(t('validation.required') + ': ' + t('remote_outputs.output_entity'));
    return errors;
  };

  const validationErrors = getValidationErrors();
  React.useEffect(() => {
    onValidationChange?.(validationErrors.length > 0);
  }, [validationErrors.length, onValidationChange]);

  /* ---------- device output lists ---------- */
  const selectedDevice = allRemoteDevices.find(d => d.id === data.device_id);
  const isWledDevice = (selectedDevice as any)?.protocol === 'wled';
  const esphomeApi = (selectedDevice as any)?.esphome_api || selectedDevice;

  // ESPHome / MQTT switches & lights
  const availableSwitches: Array<{ id: string; name?: string }> =
    isWledDevice ? [] : (esphomeApi?.switches || []);
  const availableLights: Array<{ id: string; name?: string; supports_brightness?: boolean }> =
    isWledDevice ? [] : (esphomeApi?.lights || []);

  // WLED segments + "main" (whole device)
  const wledConfig = (selectedDevice as any)?.wled;
  const wledSegments: Array<{ id: string; name: string; supports_brightness: boolean }> =
    isWledDevice && wledConfig?.segments
      ? [
          { id: 'main', name: t('remote_outputs.wled_main'), supports_brightness: true },
          ...wledConfig.segments.map((seg: { id: number; name?: string; len?: number }) => ({
            id: String(seg.id),
            name: seg.name || `${t('remote_outputs.wled_segment')} ${seg.id}${seg.len ? ` (${seg.len} LEDs)` : ''}`,
            supports_brightness: true,
          })),
        ]
      : [];

  const allAvailableOutputs = [
    ...availableSwitches.map(s => ({ ...s, _type: 'switch' as const })),
    ...availableLights.map(l => ({ ...l, _type: 'light' as const })),
    ...wledSegments.map(w => ({ ...w, _type: 'light' as const })),
  ];

  /* ---------- selected output capabilities ---------- */
  const selectedOutput = allAvailableOutputs.find(o => o.id === data.output_id);
  const isLightEntity = selectedOutput?._type === 'light';
  const selectedLight = isLightEntity
    ? [...availableLights, ...wledSegments].find(l => l.id === data.output_id)
    : null;
  const supportsBrightness = !!(selectedLight as any)?.supports_brightness;
  // Lights with brightness cannot be degraded to plain switch
  const outputTypeLocked = (isLightEntity && supportsBrightness) || isWledDevice;

  /* ---------- devices with outputs ---------- */
  const devicesWithOutputs = allRemoteDevices.filter((device) => {
    const proto = (device as any)?.protocol;
    // WLED devices always have at least "main" output
    if (proto === 'wled') return true;
    const api = (device as any)?.esphome_api || device;
    const sw = api?.switches || [];
    const li = api?.lights || [];
    return sw.length > 0 || li.length > 0;
  });

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

      <TabsBox
        name="remote_output_tabs"
        activeTab={activeTab}
        onTabChange={(tabId) => setActiveTab(tabId as 'basic' | 'advanced')}
        tabs={[
          {
            id: 'basic',
            label: t('settings.basic_settings'),
            content: (
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
                      placeholder={t('remote_outputs.name_placeholder')}
                      value={data.name || ''}
                      onChange={(e) => updateField('name', e.target.value)}
                    />
                    <label className="label">
                      <span className="label-text-alt">{t('common.optional')}</span>
                    </label>
                  </div>

                  {/* Custom Output ID */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('remote_outputs.custom_output_id')}</span>
                    </label>
                    <input
                      type="text"
                      className="input w-full"
                      placeholder={t('remote_outputs.custom_output_id_placeholder')}
                      value={data.id || ''}
                      onChange={(e) => updateField('id', sanitizeId(e.target.value))}
                    />
                    <label className="label">
                      <span className="label-text-alt">{t('remote_outputs.custom_output_id_hint')}</span>
                    </label>
                  </div>

                  {/* Remote Device (device_id) — only devices with switches/lights */}
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
                        const protocol = (device as any)?.protocol || 'esphome_api';
                        onChange({ ...data, device_id: deviceId, output_id: '', remote_source: protocol });
                      }}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t('remote_devices.select_device')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none_">{t('remote_devices.select_device')}</SelectItem>
                        {devicesWithOutputs.map((device) => {
                          const protocolLabel =
                            (device as any).protocol === 'esphome_api' ? 'ESPHome API' :
                            (device as any).protocol === 'wled' ? 'WLED' :
                            (device as any).protocol === 'mqtt' ? 'MQTT' :
                            (device as any).protocol || '';
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

                  {/* Output Entity (output_id) — dropdown from selected device's switches/lights */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('remote_outputs.output_entity')}</span>
                    </label>
                    <Select
                      value={data.output_id || '_none_'}
                      onValueChange={(v) => {
                        const outputId = v === '_none_' ? '' : v;
                        // Auto-detect output type from source
                        const found = allAvailableOutputs.find(o => o.id === outputId);
                        const autoType = found?._type === 'light' ? 'light' : data.output_type || 'switch';
                        onChange({ ...data, output_id: outputId, output_type: autoType });
                      }}
                      disabled={!data.device_id}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={
                          data.device_id
                            ? t('remote_outputs.select_output')
                            : t('remote_devices.select_device')
                        } />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none_">{t('remote_outputs.select_output')}</SelectItem>
                        {availableSwitches.length > 0 && (
                          <>
                            <SelectItem value="_header_switches" disabled>
                              ⚡ {t('remote_outputs.switches_header')}
                            </SelectItem>
                            {availableSwitches.map((sw) => (
                              <SelectItem key={`sw_${sw.id}`} value={sw.id}>
                                🔌 {sw.name ? `${sw.name} (${sw.id})` : sw.id}
                              </SelectItem>
                            ))}
                          </>
                        )}
                        {availableLights.length > 0 && (
                          <>
                            <SelectItem value="_header_lights" disabled>
                              💡 {t('remote_outputs.lights_header')}
                            </SelectItem>
                            {availableLights.map((li) => (
                              <SelectItem key={`li_${li.id}`} value={li.id}>
                                💡 {li.name ? `${li.name} (${li.id})` : li.id}
                              </SelectItem>
                            ))}
                          </>
                        )}
                        {wledSegments.length > 0 && (
                          <>
                            <SelectItem value="_header_wled" disabled>
                              🌈 {t('remote_outputs.wled_segments_header')}
                            </SelectItem>
                            {wledSegments.map((seg) => (
                              <SelectItem key={`wled_${seg.id}`} value={seg.id}>
                                {seg.id === 'main' ? '🎨' : '🌈'} {seg.name}
                              </SelectItem>
                            ))}
                          </>
                        )}
                      </SelectContent>
                    </Select>
                    {attemptedSubmit && !data.output_id && (
                      <label className="label">
                        <span className="label-text-alt text-error">{t('validation.required')}</span>
                      </label>
                    )}
                  </div>

                  {/* Output Type */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('remote_outputs.output_type')}</span>
                    </label>
                    <Select
                      value={data.output_type || 'switch'}
                      onValueChange={(v) => updateField('output_type', v)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="switch" disabled={outputTypeLocked}>{t('outputs.categories.switches')}</SelectItem>
                        <SelectItem value="light">{t('outputs.categories.lights')}</SelectItem>
                        <SelectItem value="valve" disabled={outputTypeLocked}>{t('outputs.categories.valves')}</SelectItem>
                      </SelectContent>
                    </Select>
                    <label className="label">
                      <span className="label-text-alt">
                        {outputTypeLocked
                          ? t('remote_outputs.output_type_locked_hint')
                          : t('remote_outputs.output_type_hint')}
                      </span>
                    </label>
                  </div>

                  {/* On Disconnect */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('remote_outputs.on_disconnect')}</span>
                    </label>
                    <Select
                      value={data.on_disconnect || 'ignore'}
                      onValueChange={(v) => updateField('on_disconnect', v)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="ignore">{t('remote_outputs.on_disconnect_ignore')}</SelectItem>
                        <SelectItem value="turn_off">{t('remote_outputs.on_disconnect_turn_off')}</SelectItem>
                      </SelectContent>
                    </Select>
                    <label className="label">
                      <span className="label-text-alt">{t('remote_outputs.on_disconnect_hint')}</span>
                    </label>
                  </div>

                  {/* Area */}
                  <AreaSelect
                    value={data.area}
                    onChange={(v) => updateField('area', v)}
                    areas={allAreas}
                  />
                </div>

                {/* ---- Options ---- */}
                <div className="divider">{t('settings.options')}</div>

                <SettingsToggleGroup
                  items={[
                    {
                      key: 'show_in_ha',
                      label: t('inputs.forward_to_ha'),
                      description: t('remote_outputs.forward_to_ha_hint'),
                      checked: data.show_in_ha === true,
                      onChange: (checked) => updateField('show_in_ha', checked),
                    },
                  ]}
                />
              </div>
            ),
          },
          {
            id: 'advanced',
            label: t('settings.advanced_settings'),
            content: (
              <div className="space-y-4">
                {/* --- Momentary Turn On/Off --- */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Momentary Turn On */}
                  <SimpleTimePeriodInput
                    value={data.momentary_turn_on || ''}
                    onChange={(value: string) => {
                      const isZero = /^0+(ms|s|sec|min|h|hours?)?$/i.test(value.trim());
                      updateField('momentary_turn_on', isZero ? undefined : (value || undefined));
                    }}
                    label={t('outputs.momentary_turn_on')}
                    required={false}
                    minimum={0}
                  />

                  {/* Momentary Turn Off */}
                  <SimpleTimePeriodInput
                    value={data.momentary_turn_off || ''}
                    onChange={(value: string) => {
                      const isZero = /^0+(ms|s|sec|min|h|hours?)?$/i.test(value.trim());
                      updateField('momentary_turn_off', isZero ? undefined : (value || undefined));
                    }}
                    label={t('outputs.momentary_turn_off')}
                    required={false}
                    minimum={0}
                  />
                </div>

                <div className="alert alert-info">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                  <div>
                    <h3 className="font-bold">{t('outputs.momentary_actions_title')}</h3>
                    <div className="text-sm">
                      <p>{t('outputs.momentary_actions_desc1')}</p>
                      <p>{t('outputs.momentary_actions_desc2')}</p>
                      <p>{t('outputs.momentary_actions_desc3')}</p>
                    </div>
                  </div>
                </div>

                {/* --- Adjustable Duration --- */}
                <div className="divider">{t('outputs.divider_adjustable_duration')}</div>

                  <div className="space-y-2">
                    <SettingsToggleGroup
                      items={[
                        {
                          key: 'adjustable_duration',
                          label: t('outputs.adjustable_duration_label'),
                          description: t('outputs.adjustable_duration_desc'),
                          checked: data.adjustable_duration === true,
                          onChange: () => updateField('adjustable_duration', !data.adjustable_duration),
                          disabled: !!data.momentary_turn_on,
                        },
                      ]}
                    />
                    {data.momentary_turn_on && (
                      <p className="text-xs text-warning px-1">
                        {t('outputs.adjustable_duration_conflict')}
                      </p>
                    )}
                  </div>


                  {data.adjustable_duration && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pl-2 border-l-2 border-primary/30">
                      {/* Duration Default */}
                      <SimpleTimePeriodInput
                        value={data.duration_default || '60s'}
                        onChange={(value: string) => updateField('duration_default', value || undefined)}
                        label={t('outputs.duration_default')}
                        required={false}
                        minimum={1000}
                        allowedUnits={['s', 'min', 'h']}
                        unitlessNumberUnit="s"
                      />

                      {/* Duration Min */}
                      <SimpleTimePeriodInput
                        value={data.duration_min || '1s'}
                        onChange={(value: string) => updateField('duration_min', value || undefined)}
                        label={t('outputs.duration_min')}
                        required={false}
                        minimum={1000}
                        allowedUnits={['s', 'min', 'h']}
                        unitlessNumberUnit="s"
                      />

                      {/* Duration Max */}
                      <SimpleTimePeriodInput
                        value={data.duration_max || '1h'}
                        onChange={(value: string) => updateField('duration_max', value || undefined)}
                        label={t('outputs.duration_max')}
                        required={false}
                        minimum={1000}
                        allowedUnits={['s', 'min', 'h']}
                        unitlessNumberUnit="s"
                      />

                      {/* Duration Unit for HA */}
                      <div className="form-control">
                        <label className="label">
                          <span className="label-text font-medium">{t('outputs.duration_unit')}</span>
                        </label>
                        <select
                          className="select select-bordered w-full min-h-12"
                          value={data.duration_unit || 's'}
                          onChange={(e) => updateField('duration_unit', e.target.value)}
                        >
                          <option value="s">{t('outputs.duration_unit_seconds')}</option>
                          <option value="min">{t('outputs.duration_unit_minutes')}</option>
                        </select>
                        <label className="label">
                          <span className="label-text-alt text-base-content/70">{t('outputs.duration_unit_hint')}</span>
                        </label>
                      </div>
                    </div>
                  )}

                <div className="alert alert-info">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                  <div>
                    <h3 className="font-bold">{t('outputs.adjustable_duration_info_title')}</h3>
                    <div className="text-sm">
                      <p>{t('outputs.adjustable_duration_info_desc1')}</p>
                      <p>{t('outputs.adjustable_duration_info_desc2')}</p>
                    </div>
                  </div>
                </div>

                {/* --- Interlock --- */}
                <div className="divider">{t('outputs.divider_interlock')}</div>

                {/* Normalize interlock_group: schema default is [], could be string or array */}
                {(() => {
                  const rawGroup = data.interlock_group;
                  const interlockValue: string | undefined =
                    Array.isArray(rawGroup)
                      ? (rawGroup.length > 0 ? rawGroup[0] : undefined)
                      : (rawGroup || undefined);

                  return (
                    <>
                <div className="grid grid-cols-1 gap-4">
                  {/* Current Interlock Group */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('outputs.interlock_group_label')}</span>
                    </label>
                    <Select
                      value={interlockValue || '_none_'}
                      onValueChange={(value) => updateField('interlock_group', value === '_none_' ? undefined : value)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t('outputs.interlock_group_placeholder')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none_">{t('outputs.interlock_group_none')}</SelectItem>
                        {interlockGroups.map((group) => (
                          <SelectItem key={group} value={group}>
                            {group}
                          </SelectItem>
                        ))}
                        {/* Show current value if it's not in the list (new group) */}
                        {interlockValue && !interlockGroups.includes(interlockValue) && (
                          <SelectItem value={interlockValue}>
                            {interlockValue} ({t('outputs.interlock_group_new')})
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                    <label className="label">
                      <span className="label-text-alt whitespace-normal wrap-break-word">
                        {t('remote_outputs.interlock_hint')}
                      </span>
                    </label>
                  </div>

                  {/* Add New Interlock Group */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('outputs.create_new_group')}</span>
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        className="input flex-1"
                        placeholder={t('outputs.enter_group_name')}
                        value={newInterlockGroup}
                        onChange={(e) => setNewInterlockGroup(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && newInterlockGroup.trim()) {
                            const groupName = newInterlockGroup.trim();
                            updateField('interlock_group', groupName);
                            onInterlockGroupCreated?.(groupName);
                            setNewInterlockGroup('');
                          }
                        }}
                      />
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={!newInterlockGroup.trim()}
                        onClick={() => {
                          if (newInterlockGroup.trim()) {
                            const groupName = newInterlockGroup.trim();
                            updateField('interlock_group', groupName);
                            onInterlockGroupCreated?.(groupName);
                            setNewInterlockGroup('');
                          }
                        }}
                      >
                        {t('outputs.add_button')}
                      </button>
                    </div>
                    <label className="label">
                      <span className="label-text-alt whitespace-normal wrap-break-word">
                        {t('outputs.create_group_hint')}
                      </span>
                    </label>
                  </div>
                </div>

                {/* Enforce Interlock — visible when interlock_group is set */}
                {interlockValue && (
                  <SettingsToggleGroup
                    items={[
                      {
                        key: 'enforce_interlock',
                        label: t('remote_outputs.enforce_interlock'),
                        description: t('remote_outputs.enforce_interlock_hint'),
                        checked: data.enforce_interlock === true,
                        onChange: (checked) => updateField('enforce_interlock', checked),
                      },
                    ]}
                  />
                )}

                <div className="alert alert-info">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                  <div>
                    <h3 className="font-bold">{t('outputs.software_interlock_title')}</h3>
                    <div className="text-sm">
                      <p>{t('remote_outputs.interlock_shared_desc')}</p>
                    </div>
                  </div>
                </div>
                    </>
                  );
                })()}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default RemoteOutputForm;
