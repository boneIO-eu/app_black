import React, { useState, useRef } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import OutputSelectDropdown from './OutputSelectDropdown';
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
import HelpLabel from './components/HelpLabel';
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

  const addInputToZone = (zoneIndex: number, inputId: string) => {
    const zone = zones[zoneIndex];
    if (!getZoneInputIds(zone).includes(inputId)) {
      const normalized = getZoneInputs(zone);
      updateZone(zoneIndex, 'inputs', [...normalized, { id: inputId, type: 'normally_closed' }]);
    }
  };

  const removeInputFromZone = (zoneIndex: number, inputId: string) => {
    const zone = zones[zoneIndex];
    const normalized = getZoneInputs(zone);
    updateZone(zoneIndex, 'inputs', normalized.filter((zi) => zi.id !== inputId));
  };

  const toggleInputType = (zoneIndex: number, inputId: string) => {
    const zone = zones[zoneIndex];
    const normalized = getZoneInputs(zone);
    updateZone(zoneIndex, 'inputs', normalized.map((zi) =>
      zi.id === inputId
        ? { ...zi, type: zi.type === 'normally_closed' ? 'normally_open' : 'normally_closed' }
        : zi
    ));
  };

  // --- Alarm outputs helpers ---
  const alarmOutputs: AlarmOutput[] = data.outputs || [];
  const updateAlarmOutputs = (newOutputs: AlarmOutput[]) => updateField('outputs', newOutputs);

  const addAlarmOutput = () => {
    updateAlarmOutputs([...alarmOutputs, { id: '', type: 'siren' }]);
  };

  const removeAlarmOutput = (index: number) => {
    updateAlarmOutputs(alarmOutputs.filter((_, i) => i !== index));
  };

  const updateAlarmOutput = (index: number, field: string, value: string) => {
    const newOutputs = [...alarmOutputs];
    newOutputs[index] = { ...newOutputs[index], [field]: value };
    updateAlarmOutputs(newOutputs);
  };

  /** Build enriched input list from binary sensors only. */
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
      return { id, name, area, areaName, boneioInput: inp.boneio_input || '' };
    });

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
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('outputs.area')}</span>
                </label>
                <Select
                  value={data.area || '_none_'}
                  onValueChange={(value) => updateField('area', value === '_none_' ? undefined : value)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t('outputs.no_area')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none_">{t('outputs.no_area')}</SelectItem>
                    {allAreas.map((area) => (
                      <SelectItem key={area.id} value={area.id}>
                        {area.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Outputs */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.alarm_outputs')}</span>
                </label>
                <div className="space-y-2">
                  {alarmOutputs.map((out, idx) => (
                    <div key={idx} className="flex gap-2 items-start p-3 bg-base-200 rounded-lg">
                      <div className="flex-1 space-y-2">
                        <OutputSelectDropdown
                          value={out.id || ''}
                          onChange={(value: string) => updateAlarmOutput(idx, 'id', value)}
                          allOutputs={allOutputs}
                          allAreas={allAreas}
                          placeholder={t('template.select_output')}
                        />
                        <Select
                          value={out.type || 'siren'}
                          onValueChange={(value) => updateAlarmOutput(idx, 'type', value)}
                        >
                          <SelectTrigger className="w-full">
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
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm btn-square text-error"
                        onClick={() => removeAlarmOutput(idx)}
                      >
                        <FaTrash />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="btn btn-outline btn-sm gap-2"
                    onClick={addAlarmOutput}
                  >
                    <FaPlus /> {t('template.add_output')}
                  </button>
                </div>
              </div>

              {/* PIN Codes */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.alarm_codes')}</span>
                </label>
                <div className="space-y-2">
                  {pinCodes.map((pin, idx) => {
                    const codeIsHash = isSha256(pin.code || '');
                    const hasOriginalHash = !!originalHashesRef.current[idx] || codeIsHash;
                    const displayValue = codeIsHash ? '' : (pin.code || '');
                    return (
                      <div key={idx} className="flex gap-2 items-center p-3 bg-base-200 rounded-lg">
                        <input
                          type="text"
                          className="input input-sm flex-1"
                          value={pin.name || ''}
                          onChange={(e) => updatePinCode(idx, 'name', e.target.value)}
                          placeholder={t('template.pin_name_placeholder')}
                        />
                        <input
                          type="password"
                          className="input input-sm w-28 font-mono"
                          value={displayValue}
                          onChange={(e) => updatePinCode(idx, 'code', e.target.value.replace(/[^0-9]/g, ''))}
                          placeholder={hasOriginalHash ? '••••••' : t('template.alarm_code_placeholder')}
                          inputMode="numeric"
                          maxLength={8}
                        />
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-square text-error"
                          onClick={() => removePinCode(idx)}
                        >
                          <FaTrash />
                        </button>
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
                      <div className={`form-control p-2 rounded-lg ${(zone.arm_modes?.length === 0 || !zone.arm_modes) ? 'border border-error bg-error/10' : ''}`}>
                        <label className="label py-1">
                          <span className="label-text text-sm font-medium">
                            {t('template.arm_modes')}
                            {(zone.arm_modes?.length === 0 || !zone.arm_modes) && (
                              <span className="text-error ml-2">* {t('common.required')}</span>
                            )}
                          </span>
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {ARM_MODE_OPTIONS.map((mode) => (
                            <label key={mode} className="label cursor-pointer gap-2 p-0">
                              <input
                                type="checkbox"
                                className="checkbox checkbox-sm"
                                checked={(zone.arm_modes || []).includes(mode)}
                                onChange={() => toggleZoneArmMode(zIdx, mode)}
                              />
                              <span className="label-text text-sm">{t(`template.arm_mode_${mode}`)}</span>
                            </label>
                          ))}
                        </div>
                      </div>

                      {/* Entry delay */}
                      <label className="label cursor-pointer justify-start gap-3 p-0">
                        <input
                          type="checkbox"
                          className="checkbox checkbox-sm"
                          checked={zone.entry_delay || false}
                          onChange={(e) => updateZone(zIdx, 'entry_delay', e.target.checked)}
                        />
                        <span className="label-text text-sm">{t('template.entry_delay')}</span>
                      </label>

                      {/* Inputs */}
                      <div className="form-control">
                        <label className="label py-1">
                          <span className="label-text text-sm">{t('template.zone_inputs')}</span>
                        </label>
                        <div className="space-y-1 mb-2">
                          {getZoneInputs(zone).map((zi) => {
                            const info = enrichedInputs.find((e) => e.id === zi.id);
                            const label = info
                              ? `${info.name || zi.id}${info.boneioInput ? ` (${info.boneioInput})` : ''}${info.areaName ? ` · ${info.areaName}` : ''}`
                              : zi.id;
                            return (
                              <div key={zi.id} className="flex items-center gap-2 p-2 bg-base-300 rounded-lg">
                                <span className="flex-1 text-sm font-medium truncate" title={label}>
                                  {label}
                                </span>
                                <button
                                  type="button"
                                  className={`btn btn-xs ${zi.type === 'normally_closed'
                                    ? 'btn-info'
                                    : 'btn-warning'
                                    }`}
                                  onClick={() => toggleInputType(zIdx, zi.id)}
                                  title={zi.type === 'normally_closed'
                                    ? t('template.wiring_nc_hint')
                                    : t('template.wiring_no_hint')}
                                >
                                  {zi.type === 'normally_closed' ? 'NC' : 'NO'}
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-xs btn-square text-error"
                                  onClick={() => removeInputFromZone(zIdx, zi.id)}
                                >
                                  ×
                                </button>
                              </div>
                            );
                          })}
                        </div>
                        {enrichedInputs.length > 0 ? (
                          <Select
                            value=""
                            onValueChange={(value) => {
                              if (value) addInputToZone(zIdx, value);
                            }}
                          >
                            <SelectTrigger className="w-full">
                              <SelectValue placeholder={t('template.add_input')} />
                            </SelectTrigger>
                            <SelectContent>
                              {enrichedInputs
                                .filter((inp) => !getZoneInputIds(zone).includes(inp.id))
                                .map((inp) => (
                                  <SelectItem key={inp.id} value={inp.id}>
                                    <div className="flex items-center gap-2">
                                      <span className="font-medium">{inp.name || inp.id}</span>
                                      {inp.boneioInput && (
                                        <span className="text-xs opacity-60">{inp.boneioInput}</span>
                                      )}
                                      {inp.areaName && (
                                        <span className="text-xs opacity-50">· {inp.areaName}</span>
                                      )}
                                    </div>
                                  </SelectItem>
                                ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <p className="text-sm text-base-content/50 italic">
                            {t('template.no_binary_sensors')}
                          </p>
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

              {/* Code Arm Required */}
              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox"
                    checked={data.code_arm_required || false}
                    onChange={(e) => updateField('code_arm_required', e.target.checked)}
                  />
                  <div>
                    <span className="label-text font-medium">{t('template.code_arm_required')}</span>
                    <HelpLabel>{t('template.code_arm_required_hint')}</HelpLabel>
                  </div>
                </label>
              </div>

              {/* Allow Frontend Control */}
              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-4">
                  <input
                    type="checkbox"
                    className="checkbox"
                    checked={data.allow_frontend_control || false}
                    onChange={(e) => updateField('allow_frontend_control', e.target.checked)}
                  />
                  <div>
                    <span className="label-text font-medium">{t('template.allow_frontend_control')}</span>
                    <HelpLabel>{t('template.allow_frontend_control_hint')}</HelpLabel>
                  </div>
                </label>
              </div>
            </div>
          ),
        },
      ]}
    />
  );
};

export default AlarmPanelForm;
