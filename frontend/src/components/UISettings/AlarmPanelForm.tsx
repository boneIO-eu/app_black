import React, { useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import OutputSelectDropdown from './OutputSelectDropdown';
import { useTranslation } from '@/hooks/useTranslation';
import { TabsBox } from '@/components/ui/tabs-box';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { TemplateSubFormProps, AlarmZone, AlarmOutput } from './types/template';
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
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  // --- Zone helpers ---
  const zones: AlarmZone[] = data.zones || [];
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

  const addInputToZone = (zoneIndex: number, inputId: string) => {
    const zone = zones[zoneIndex];
    if (!zone.inputs.includes(inputId)) {
      updateZone(zoneIndex, 'inputs', [...zone.inputs, inputId]);
    }
  };

  const removeInputFromZone = (zoneIndex: number, inputId: string) => {
    const zone = zones[zoneIndex];
    updateZone(zoneIndex, 'inputs', zone.inputs.filter((id) => id !== inputId));
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

  const availableInputIds = allInputs
    .map((inp: any) => inp.id || inp.boneio_input || '')
    .filter(Boolean);

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
                          <span className="label-text text-sm">{t('template.zone_name')} *</span>
                        </label>
                        <input
                          type="text"
                          className="input input-sm w-full"
                          value={zone.name || ''}
                          onChange={(e) => updateZone(zIdx, 'name', e.target.value)}
                          placeholder={t('template.zone_name_placeholder')}
                        />
                      </div>

                      {/* Arm modes */}
                      <div className="form-control">
                        <label className="label py-1">
                          <span className="label-text text-sm">{t('template.arm_modes')}</span>
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
                        <div className="flex flex-wrap gap-1 mb-2">
                          {(zone.inputs || []).map((inputId: string) => (
                            <span key={inputId} className="badge badge-primary gap-1">
                              {inputId}
                              <button
                                type="button"
                                className="btn btn-ghost btn-xs p-0"
                                onClick={() => removeInputFromZone(zIdx, inputId)}
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                        {availableInputIds.length > 0 ? (
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
                              {availableInputIds
                                .filter((id: string) => !(zone.inputs || []).includes(id))
                                .map((id: string) => (
                                  <SelectItem key={id} value={id}>
                                    {id}
                                  </SelectItem>
                                ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <input
                            type="text"
                            className="input input-sm w-full"
                            placeholder={t('template.input_id_manual')}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                const val = (e.target as HTMLInputElement).value.trim();
                                if (val) {
                                  addInputToZone(zIdx, val);
                                  (e.target as HTMLInputElement).value = '';
                                }
                                e.preventDefault();
                              }
                            }}
                          />
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

              {/* Code / PIN */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.alarm_code')}</span>
                </label>
                <input
                  type="text"
                  className="input w-full font-mono"
                  value={data.code || ''}
                  onChange={(e) => updateField('code', e.target.value.replace(/[^0-9]/g, ''))}
                  placeholder={t('template.alarm_code_placeholder')}
                  inputMode="numeric"
                  maxLength={8}
                />
                <label className="label">
                  <span className="label-text-alt text-info">{t('template.alarm_code_hint')}</span>
                </label>
              </div>

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
                    <p className="text-sm text-base-content/70 mt-1">
                      {t('template.code_arm_required_hint')}
                    </p>
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
