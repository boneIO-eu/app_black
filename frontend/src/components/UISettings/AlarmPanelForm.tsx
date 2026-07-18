import React, { useState, useMemo, useRef } from 'react';
import { FaPlus, FaTrash, FaWifi } from 'react-icons/fa';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import AreaSelect from './widgets/AreaSelect';
import SearchableMultiEntityPicker from './SearchableMultiEntityPicker';
import { buildOutputItems } from './helpers/thermostatHelpers';
import type { OutputConfigEntry } from './helpers/thermostatHelpers';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
import { TabsBox } from '@/components/ui/tabs-box';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import SettingsToggleGroup from './widgets/SettingsToggleGroup';
import type { TemplateSubFormProps, AlarmZone, AlarmOutput, AlarmPin, ZoneInput } from './types/template';
import { ARM_MODE_OPTIONS, OUTPUT_TYPE_OPTIONS } from './types/template';

/**
 * AlarmPanelForm — configuration form for the alarm_control_panel template platform.
 *
 * Zone-based alarm system with independent zone arming, entry delay,
 * multiple outputs (siren, notification, etc.), and configurable timing.
 */
const AlarmPanelForm: React.FC<TemplateSubFormProps> = ({
  data,
  onChange,
  allOutputs,
  allAreas,
  allInputs,
  allRemoteInputs,
  onValidationChange,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  // --- Zone helpers ---
  const zones: AlarmZone[] = data.zones || [];

  React.useEffect(() => {
    if (onValidationChange) {
      const hasErrors = zones.some((z) => !z.arm_modes || z.arm_modes.length === 0 || !z.name || z.name.trim() === '');
      onValidationChange(hasErrors);
    }
  }, [zones, onValidationChange]);

  // --- PIN codes helpers ---
  const pinCodes: AlarmPin[] = data.codes || [];
  const updatePinCodes = (newCodes: AlarmPin[]) => updateField('codes', newCodes);

  const isSha256 = (value: string) =>
    value.length === 64 && /^[0-9a-f]{64}$/i.test(value);

  // Track original hashes in local ref (not in form data)
  const originalHashesRef = useRef<Record<number, string>>({});

  const addPinCode = () => {
    updatePinCodes([...pinCodes, { name: '', code: '' }]);
  };

  const removePinCode = (index: number) => {
    // Clean up hash tracking
    const newHashes: Record<number, string> = {};
    for (const [k, v] of Object.entries(originalHashesRef.current)) {
      const ki = Number(k);
      if (ki < index) newHashes[ki] = v;
      else if (ki > index) newHashes[ki - 1] = v;
    }
    originalHashesRef.current = newHashes;
    updatePinCodes(pinCodes.filter((_, i) => i !== index));
  };

  const updatePinCode = (index: number, field: string, value: string) => {
    const newCodes = [...pinCodes];
    if (field === 'code') {
      const current = newCodes[index].code || '';
      // When user starts editing a hashed code, remember the hash
      if (isSha256(current) && !originalHashesRef.current[index]) {
        originalHashesRef.current[index] = current;
      }
      if (value === '' && originalHashesRef.current[index]) {
        // User cleared the field — restore original hash (PIN unchanged)
        newCodes[index] = { ...newCodes[index], code: originalHashesRef.current[index] };
      } else {
        newCodes[index] = { ...newCodes[index], code: value };
      }
    } else {
      newCodes[index] = { ...newCodes[index], [field]: value };
    }
    updatePinCodes(newCodes);
  };

  const updateZones = (newZones: AlarmZone[]) => updateField('zones', newZones);

  const addZone = () => {
    updateZones([...zones, { name: '', inputs: [], arm_modes: ['armed_away'], entry_delay: false }]);
  };

  const removeZone = (index: number) => {
    updateZones(zones.filter((_, i) => i !== index));
  };

  const updateZone = (index: number, field: string, value: any) => {
    const newZones = [...zones];
    newZones[index] = { ...newZones[index], [field]: value };
    updateZones(newZones);
  };

  const toggleZoneArmMode = (zoneIndex: number, mode: string) => {
    const zone = zones[zoneIndex];
    const modes = zone.arm_modes || [];
    const newModes = modes.includes(mode)
      ? modes.filter((m) => m !== mode)
      : [...modes, mode];
    updateZone(zoneIndex, 'arm_modes', newModes);
  };

  /** Normalize a zone input entry to ZoneInput object. */
  const normalizeZoneInput = (inp: string | ZoneInput): ZoneInput => {
    if (typeof inp === 'string') return { id: inp, type: 'normally_closed' };
    return inp;
  };

  /** Get all ZoneInput objects for a zone (normalized). */
  const getZoneInputs = (zone: AlarmZone): ZoneInput[] =>
    (zone.inputs || []).map(normalizeZoneInput);

  /** Get list of input IDs already used in a zone. */
  const getZoneInputIds = (zone: AlarmZone): string[] =>
    getZoneInputs(zone).map((zi) => zi.id);

  const toggleInputType = (zoneIndex: number, inputId: string) => {
    const zone = zones[zoneIndex];
    const normalized = getZoneInputs(zone);
    updateZone(zoneIndex, 'inputs', normalized.map((zi) =>
      zi.id === inputId
        ? { ...zi, type: zi.type === 'normally_closed' ? 'normally_open' : 'normally_closed' }
        : zi
    ));
  };

  const toggleOnDisconnect = (zoneIndex: number, inputId: string) => {
    const zone = zones[zoneIndex];
    const normalized = getZoneInputs(zone);
    updateZone(zoneIndex, 'inputs', normalized.map((zi) =>
      zi.id === inputId
        ? { ...zi, on_disconnect: zi.on_disconnect === 'trigger' ? 'ignore' : 'trigger' }
        : zi
    ));
  };

  // --- Alarm outputs helpers ---
  const alarmOutputs: AlarmOutput[] = data.outputs || [];
  const updateAlarmOutputs = (newOutputs: AlarmOutput[]) => updateField('outputs', newOutputs);


  const updateAlarmOutput = (index: number, field: string, value: string) => {
    const newOutputs = [...alarmOutputs];
    newOutputs[index] = { ...newOutputs[index], [field]: value };
    updateAlarmOutputs(newOutputs);
  };

  /** Build enriched input list from local binary sensors. */
  const enrichedInputs = allInputs
    .filter((inp: any) => {
      const id = inp.id || inp.boneio_input || '';
      return Boolean(id);
    })
    .map((inp: any) => {
      const id = inp.id || inp.boneio_input || '';
      const name = inp.name || '';
      const area = inp.area || '';
      const areaName = allAreas.find((a) => a.id === area)?.name || '';
      return { id, name, area, areaName, boneioInput: inp.boneio_input || '', source: 'local' as const };
    });

  /** Build enriched input list from remote inputs (binary sensors from remote devices). */
  const enrichedRemoteInputs = (allRemoteInputs || [])
    .filter((inp: any) => {
      const id = inp.name || inp.id || '';
      return Boolean(id);
    })
    .map((inp: any) => {
      const id = inp.name || inp.id || '';
      const name = inp.name || '';
      const deviceId = inp.device_id || '';
      const inputId = inp.input_id || '';
      return {
        id,
        name,
        deviceId,
        inputId,
        remoteSource: inp.remote_source || 'esphome_api',
        source: 'remote' as const,
      };
    });

  /** Convert allOutputs to EntityItem[] for SearchableMultiEntityPicker. */
  const outputItems = useMemo(
    () => buildOutputItems(allOutputs as OutputConfigEntry[]),
    [allOutputs]
  );

  /** Combine local + remote inputs into EntityItem[] for SearchableMultiEntityPicker. */
  const inputItems = useMemo(() => {
    const localItems = enrichedInputs.map((inp) => ({
      id: inp.id,
      name: inp.name || inp.id,
      area: inp.area,
      badge: inp.boneioInput && inp.boneioInput !== inp.id ? inp.boneioInput : undefined,
      badgeClass: 'badge-ghost' as const,
    }));
    const remoteItems = enrichedRemoteInputs.map((inp) => ({
      id: inp.id,
      name: inp.name || inp.id,
      badge: '📡 Remote',
      badgeClass: 'badge-primary' as const,
    }));
    return [...localItems, ...remoteItems];
  }, [enrichedInputs, enrichedRemoteInputs]);

  return (
    <TabsBox
      name="alarm_tabs"
      activeTab={activeTab}
      onTabChange={(tabId) => setActiveTab(tabId as 'basic' | 'advanced')}
      tabs={[
        {
          id: 'basic',
          label: t('settings.basic_settings'),
          content: (
            <div className="space-y-4">
              {/* Display Name */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('outputs.display_name')}</span>
                </label>
                <input
                  type="text"
                  className="input w-full"
                  value={data.name || ''}
                  onChange={(e) => updateField('name', e.target.value)}
                  placeholder={t('template.alarm_name_placeholder')}
                />
                <label className="label">
                  <span className="label-text-alt text-info">{t('common.optional')}</span>
                </label>
              </div>

              {/* ID */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('outputs.id')}</span>
                </label>
                <input
                  type="text"
                  className="input w-full font-mono"
                  value={data.id || ''}
                  onChange={(e) => updateField('id', sanitizeId(e.target.value))}
                  placeholder={t('template.id_placeholder')}
                />
                <label className="label">
                  <span className="label-text-alt text-info">{t('template.id_hint')}</span>
                </label>
              </div>

              {/* Area */}
              <AreaSelect
                value={data.area}
                onChange={(v) => updateField('area', v)}
                areas={allAreas}
                hideHint
              />

              {/* Outputs */}
              <div className="form-control">
                <SearchableMultiEntityPicker
                  value={alarmOutputs.map((o) => o.id)}
                  onChange={(selectedIds: string[]) => {
                    // Sync AlarmOutput[] with selected IDs, preserving existing types
                    const existingMap = new Map(alarmOutputs.map((o) => [o.id, o.type || 'siren']));
                    const newOutputs: AlarmOutput[] = selectedIds.map((id) => ({
                      id,
                      type: existingMap.get(id) || 'siren',
                    }));
                    updateAlarmOutputs(newOutputs);
                  }}
                  items={outputItems}
                  allAreas={allAreas}
                  label={t('template.alarm_outputs')}
                  placeholder={t('template.select_output')}
                  preferredArea={data.area}
                />
                {/* Per-output type selectors */}
                {alarmOutputs.length > 0 && (
                  <div className="mt-3 space-y-2">
                    <label className="label py-0">
                      <span className="label-text-alt font-medium">{t('template.output_types')}</span>
                    </label>
                    {alarmOutputs.map((out, idx) => {
                      const outputInfo = outputItems.find((o) => o.id === out.id);
                      return (
                        <div key={out.id} className="flex items-center gap-2 px-3 py-2 bg-base-200 rounded-lg">
                          <span className="flex-1 text-sm font-medium truncate">
                            {outputInfo?.name || out.id}
                          </span>
                          <Select
                            value={out.type || 'siren'}
                            onValueChange={(value) => updateAlarmOutput(idx, 'type', value)}
                          >
                            <SelectTrigger className="w-32 h-8">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {OUTPUT_TYPE_OPTIONS.map((opt) => (
                                <SelectItem key={opt} value={opt}>
                                  {t(`template.output_type_${opt}`)}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* PIN Codes */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.alarm_codes')}</span>
                </label>
                <div className="space-y-3">
                  {pinCodes.map((pin, idx) => {
                    const codeIsHash = isSha256(pin.code || '');
                    const hasOriginalHash = !!originalHashesRef.current[idx] || codeIsHash;
                    const displayValue = codeIsHash ? '' : (pin.code || '');
                    return (
                      <div key={idx} className="p-3 bg-base-200 rounded-lg space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-base-content/60">
                            {t('template.pin_code')} #{idx + 1}
                          </span>
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs btn-square text-error"
                            onClick={() => removePinCode(idx)}
                          >
                            <FaTrash />
                          </button>
                        </div>
                        <div className="form-control">
                          <label className="label py-0">
                            <span className="label-text text-sm">{t('template.pin_user_name')}</span>
                          </label>
                          <input
                            type="text"
                            className="input input-sm w-full"
                            value={pin.name || ''}
                            onChange={(e) => updatePinCode(idx, 'name', e.target.value)}
                            placeholder={t('template.pin_name_placeholder')}
                          />
                        </div>
                        <div className="form-control">
                          <label className="label py-0">
                            <span className="label-text text-sm">{t('template.pin_code_label')}</span>
                          </label>
                          <input
                            type="password"
                            className="input input-sm w-full font-mono"
                            value={displayValue}
                            onChange={(e) => updatePinCode(idx, 'code', e.target.value.replace(/[^0-9]/g, ''))}
                            placeholder={hasOriginalHash ? '••••••' : t('template.alarm_code_placeholder')}
                            inputMode="numeric"
                            maxLength={8}
                          />
                        </div>
                      </div>
                    );
                  })}
                  <button
                    type="button"
                    className="btn btn-outline btn-sm gap-2"
                    onClick={addPinCode}
                  >
                    <FaPlus /> {t('template.add_pin_code')}
                  </button>
                </div>
                <label className="label">
                  <span className="label-text-alt text-info">{t('template.alarm_codes_hint')}</span>
                </label>
              </div>

              {/* Zones */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.alarm_zones')}</span>
                </label>
                <div className="space-y-3">
                  {zones.map((zone, zIdx) => (
                    <div key={zIdx} className="p-4 bg-base-200 rounded-lg space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm">{t('template.zone')} #{zIdx + 1}</span>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-square text-error"
                          onClick={() => removeZone(zIdx)}
                        >
                          <FaTrash />
                        </button>
                      </div>

                      {/* Zone name */}
                      <div className="form-control">
                        <label className="label py-1">
                          <span className="label-text text-sm">
                            {t('template.zone_name')}
                            {(!zone.name || zone.name.trim() === '') ? (
                              <span className="text-error font-medium ml-2">* {t('common.required')}</span>
                            ) : (
                              ' *'
                            )}
                          </span>
                        </label>
                        <input
                          type="text"
                          className={`input input-sm w-full ${(!zone.name || zone.name.trim() === '') ? 'input-error bg-error/5' : ''}`}
                          value={zone.name || ''}
                          onChange={(e) => updateZone(zIdx, 'name', e.target.value)}
                          placeholder={t('template.zone_name_placeholder')}
                        />
                      </div>

                      {/* Arm modes */}
                      <div className={`form-control p-3 rounded-lg ${(zone.arm_modes?.length === 0 || !zone.arm_modes) ? 'border border-error bg-error/10' : ''}`}>
                        <label className="label py-1">
                          <span className="label-text text-sm font-medium">
                            {t('template.arm_modes')}
                            {(zone.arm_modes?.length === 0 || !zone.arm_modes) && (
                              <span className="text-error ml-2">* {t('common.required')}</span>
                            )}
                          </span>
                        </label>
                        <div className="flex flex-col gap-2 mt-1">
                          {ARM_MODE_OPTIONS.map((mode) => (
                            <label key={mode} className="flex items-center cursor-pointer gap-3">
                              <input
                                type="checkbox"
                                className="toggle toggle-sm toggle-primary"
                                checked={(zone.arm_modes || []).includes(mode)}
                                onChange={() => toggleZoneArmMode(zIdx, mode)}
                              />
                              <span className="label-text text-sm">{t(`template.arm_mode_${mode}`)}</span>
                            </label>
                          ))}
                        </div>
                      </div>

                      {/* Entry delay */}
                      <div className="px-3">
                        <label className="flex items-center cursor-pointer gap-3">
                          <input
                            type="checkbox"
                            className="toggle toggle-sm toggle-primary"
                            checked={zone.entry_delay || false}
                            onChange={(e) => updateZone(zIdx, 'entry_delay', e.target.checked)}
                          />
                          <span className="label-text text-sm">{t('template.entry_delay')}</span>
                        </label>
                        <p className="text-xs text-base-content/50 mt-1 ml-12">
                          {t('template.entry_delay_hint')}
                        </p>
                      </div>

                      {/* Inputs */}
                      <div className="form-control">
                        <SearchableMultiEntityPicker
                          value={getZoneInputIds(zone)}
                          onChange={(selectedIds: string[]) => {
                            // Sync zone inputs with selected IDs, preserving existing config
                            const existingMap = new Map(
                              getZoneInputs(zone).map((zi) => [zi.id, zi])
                            );
                            const newInputs: ZoneInput[] = selectedIds.map((id) => {
                              const existing = existingMap.get(id);
                              if (existing) return existing;
                              // Determine if remote
                              const isRemote = enrichedRemoteInputs.some((r) => r.id === id);
                              return {
                                id,
                                type: 'normally_closed' as const,
                                ...(isRemote ? { source: 'remote' as const, on_disconnect: 'ignore' as const } : {}),
                              };
                            });
                            updateZone(zIdx, 'inputs', newInputs);
                          }}
                          items={inputItems}
                          allAreas={allAreas}
                          label={t('template.zone_inputs')}
                          placeholder={t('template.add_input')}
                          preferredArea={data.area}
                        />
                        {/* Per-input configuration */}
                        {getZoneInputs(zone).length > 0 && (
                          <div className="mt-2 space-y-1">
                            {getZoneInputs(zone).map((zi) => {
                              const isRemote = zi.source === 'remote';
                              const info = inputItems.find((item) => item.id === zi.id);

                              return (
                                <div
                                  key={zi.id}
                                  className={`flex items-center gap-2 px-3 py-2 rounded-lg ${
                                    isRemote ? 'bg-primary/10 border border-primary/20' : 'bg-base-200'
                                  }`}
                                >
                                  {isRemote && (
                                    <FaWifi className="text-primary shrink-0 w-3 h-3" title={t('template.remote_input')} />
                                  )}
                                  <span className="flex-1 text-sm font-medium truncate" title={info?.name || zi.id}>
                                    {info?.name || zi.id}
                                    {info?.badge && (
                                      <span className="text-xs opacity-60 ml-1">({info.badge})</span>
                                    )}
                                  </span>
                                  {/* NC/NO toggle — only for local inputs */}
                                  {!isRemote && (
                                    <button
                                      type="button"
                                      className={`btn btn-xs ${
                                        zi.type === 'normally_closed' ? 'btn-info' : 'btn-warning'
                                      }`}
                                      onClick={() => toggleInputType(zIdx, zi.id)}
                                      title={
                                        zi.type === 'normally_closed'
                                          ? t('template.wiring_nc_hint')
                                          : t('template.wiring_no_hint')
                                      }
                                    >
                                      {zi.type === 'normally_closed' ? 'NC' : 'NO'}
                                    </button>
                                  )}
                                  {/* On disconnect toggle — only for remote inputs */}
                                  {isRemote && (
                                    <button
                                      type="button"
                                      className={`btn btn-xs ${
                                        zi.on_disconnect === 'trigger'
                                          ? 'btn-error'
                                          : 'btn-ghost border-base-content/20'
                                      }`}
                                      onClick={() => toggleOnDisconnect(zIdx, zi.id)}
                                      title={
                                        zi.on_disconnect === 'trigger'
                                          ? t('template.on_disconnect_trigger_hint')
                                          : t('template.on_disconnect_ignore_hint')
                                      }
                                    >
                                      {zi.on_disconnect === 'trigger'
                                        ? t('template.on_disconnect_trigger')
                                        : t('template.on_disconnect_ignore')}
                                    </button>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="btn btn-outline btn-sm gap-2"
                    onClick={addZone}
                  >
                    <FaPlus /> {t('template.add_zone')}
                  </button>
                </div>
              </div>
            </div>
          ),
        },
        {
          id: 'advanced',
          label: t('settings.advanced_settings'),
          content: (
            <div className="space-y-4">
              {/* Arming Time */}
              <SimpleTimePeriodInput
                value={data.arming_time || '30s'}
                onChange={(value: string) => updateField('arming_time', value)}
                label={t('template.arming_time')}
                allowedUnits={['s', 'min']}
              />

              {/* Delay Time */}
              <SimpleTimePeriodInput
                value={data.delay_time || '30s'}
                onChange={(value: string) => updateField('delay_time', value)}
                label={t('template.delay_time')}
                allowedUnits={['s', 'min']}
              />

              {/* Trigger Time */}
              <SimpleTimePeriodInput
                value={data.trigger_time || '5min'}
                onChange={(value: string) => updateField('trigger_time', value)}
                label={t('template.trigger_time')}
                allowedUnits={['s', 'min', 'h']}
              />

              {/* Code Arm Required & Allow Frontend Control */}
              <SettingsToggleGroup
                items={[
                  {
                    key: 'code_arm_required',
                    label: t('template.code_arm_required'),
                    description: t('template.code_arm_required_hint'),
                    checked: data.code_arm_required || false,
                    onChange: (checked) => updateField('code_arm_required', checked),
                  },
                  {
                    key: 'allow_frontend_control',
                    label: t('template.allow_frontend_control'),
                    description: t('template.allow_frontend_control_hint'),
                    checked: data.allow_frontend_control || false,
                    onChange: (checked) => updateField('allow_frontend_control', checked),
                  },
                ]}
              />
            </div>
          ),
        },
      ]}
    />
  );
};

export default AlarmPanelForm;
