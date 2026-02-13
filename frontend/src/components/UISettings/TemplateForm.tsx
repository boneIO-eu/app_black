import React, { useState } from 'react';
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

interface Area {
  id: string;
  name: string;
}

interface AlarmZone {
  name: string;
  inputs: string[];
  arm_modes: string[];
  entry_delay: boolean;
}

interface AlarmOutput {
  id: string;
  type: string;
}

interface TemplateFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  allOutputs?: any[];
  allAreas?: Area[];
  allSensors?: any[];
  allInputs?: any[];
}

const PLATFORM_OPTIONS = ['thermostat', 'alarm_control_panel'];
const ARM_MODE_OPTIONS = ['armed_away', 'armed_home', 'armed_night'];
const OUTPUT_TYPE_OPTIONS = ['siren', 'notification', 'light', 'custom'];

const TemplateForm: React.FC<TemplateFormProps> = ({
  data,
  onChange,
  schema: _schema,
  allOutputs = [],
  allAreas = [],
  allSensors = [],
  allInputs = [],
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  const platform = data.platform || 'thermostat';

  const updateField = (field: string, value: any) => {
    const newData = { ...data, [field]: value };

    // Clean up platform-specific fields when platform changes
    if (field === 'platform') {
      if (value === 'thermostat') {
        delete newData.zones;
        delete newData.outputs;
        delete newData.arming_time;
        delete newData.delay_time;
        delete newData.trigger_time;
        delete newData.code;
        delete newData.code_arm_required;
      } else if (value === 'alarm_control_panel') {
        delete newData.sensor_id;
        delete newData.output_id;
        delete newData.mode;
        delete newData.target_temperature;
        delete newData.hysteresis;
        delete newData.min_temperature;
        delete newData.max_temperature;
      }
    }

    onChange(newData);
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

  // Collect all input IDs from binary_sensor + event sections
  const availableInputIds = allInputs
    .map((inp: any) => inp.id || inp.boneio_input || '')
    .filter(Boolean);

  // Collect all sensor IDs
  const availableSensorIds = allSensors
    .map((s: any) => s.id || s.address || '')
    .filter(Boolean);

  // --- Thermostat form ---
  const renderThermostatBasic = () => (
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
          placeholder={t('template.thermostat_name_placeholder')}
        />
        <label className="label">
          <span className="label-text-alt text-info">{t('common.optional')}</span>
        </label>
      </div>

      {/* ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('outputs.id')} *</span>
        </label>
        <input
          type="text"
          className="input w-full"
          value={data.id || ''}
          onChange={(e) => updateField('id', sanitizeId(e.target.value))}
          placeholder={t('sensors.id_hint')}
        />
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

      {/* Sensor ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.sensor_id')} *</span>
        </label>
        {availableSensorIds.length > 0 ? (
          <Select
            value={data.sensor_id || ''}
            onValueChange={(value) => updateField('sensor_id', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('template.select_sensor')} />
            </SelectTrigger>
            <SelectContent>
              {availableSensorIds.map((sid: string) => (
                <SelectItem key={sid} value={sid}>
                  {sid}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <input
            type="text"
            className="input w-full"
            value={data.sensor_id || ''}
            onChange={(e) => updateField('sensor_id', e.target.value)}
            placeholder={t('template.sensor_id_placeholder')}
          />
        )}
        <label className="label">
          <span className="label-text-alt text-info">{t('template.sensor_id_hint')}</span>
        </label>
      </div>

      {/* Output ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.output_id')} *</span>
        </label>
        <OutputSelectDropdown
          value={data.output_id || ''}
          onChange={(value: string) => updateField('output_id', value)}
          allOutputs={allOutputs}
          allAreas={allAreas}
          placeholder={t('template.select_output')}
        />
        <label className="label">
          <span className="label-text-alt text-info">{t('template.output_id_hint')}</span>
        </label>
      </div>

      {/* Target Temperature */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.target_temperature')}</span>
        </label>
        <div className="flex items-center gap-2">
          <input
            type="number"
            className="input w-full"
            value={data.target_temperature ?? 21}
            onChange={(e) => updateField('target_temperature', parseFloat(e.target.value) || 21)}
            min={data.min_temperature ?? 5}
            max={data.max_temperature ?? 35}
            step={0.5}
          />
          <span className="text-base-content/70">°C</span>
        </div>
      </div>
    </div>
  );

  const renderThermostatAdvanced = () => (
    <div className="space-y-4">
      {/* Initial Mode */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.initial_mode')}</span>
        </label>
        <Select
          value={data.mode || 'heat'}
          onValueChange={(value) => updateField('mode', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="heat">HEAT</SelectItem>
            <SelectItem value="off">OFF</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Hysteresis */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.hysteresis')}</span>
        </label>
        <div className="flex items-center gap-2">
          <input
            type="number"
            className="input w-full"
            value={data.hysteresis ?? 0.5}
            onChange={(e) => updateField('hysteresis', parseFloat(e.target.value) || 0.5)}
            min={0.1}
            max={5}
            step={0.1}
          />
          <span className="text-base-content/70">°C</span>
        </div>
        <label className="label">
          <span className="label-text-alt text-info">{t('template.hysteresis_hint')}</span>
        </label>
      </div>

      {/* Min Temperature */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.min_temperature')}</span>
        </label>
        <div className="flex items-center gap-2">
          <input
            type="number"
            className="input w-full"
            value={data.min_temperature ?? 5}
            onChange={(e) => updateField('min_temperature', parseFloat(e.target.value) || 5)}
            min={0}
            max={data.max_temperature ?? 35}
            step={0.5}
          />
          <span className="text-base-content/70">°C</span>
        </div>
      </div>

      {/* Max Temperature */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.max_temperature')}</span>
        </label>
        <div className="flex items-center gap-2">
          <input
            type="number"
            className="input w-full"
            value={data.max_temperature ?? 35}
            onChange={(e) => updateField('max_temperature', parseFloat(e.target.value) || 35)}
            min={data.min_temperature ?? 5}
            max={50}
            step={0.5}
          />
          <span className="text-base-content/70">°C</span>
        </div>
      </div>
    </div>
  );

  // --- Alarm panel form ---
  const renderAlarmBasic = () => (
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
          <span className="label-text font-medium">{t('outputs.id')} *</span>
        </label>
        <input
          type="text"
          className="input w-full"
          value={data.id || ''}
          onChange={(e) => updateField('id', sanitizeId(e.target.value))}
          placeholder={t('sensors.id_hint')}
        />
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
  );

  const renderAlarmAdvanced = () => (
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
            <p className="text-sm text-base-content/70 mt-1">
              {t('template.code_arm_required_hint')}
            </p>
          </div>
        </label>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Platform selector */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.platform')} *</span>
        </label>
        <Select
          value={platform}
          onValueChange={(value) => updateField('platform', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('template.select_platform')} />
          </SelectTrigger>
          <SelectContent>
            {PLATFORM_OPTIONS.map((p) => (
              <SelectItem key={p} value={p}>
                {t(`template.platform_${p}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="label">
          <span className="label-text-alt text-info">
            {platform === 'thermostat' && t('template.platform_thermostat_hint')}
            {platform === 'alarm_control_panel' && t('template.platform_alarm_hint')}
          </span>
        </label>
      </div>

      {/* Platform-specific form */}
      <TabsBox
        name="template_tabs"
        activeTab={activeTab}
        onTabChange={(tabId) => setActiveTab(tabId as 'basic' | 'advanced')}
        tabs={[
          {
            id: 'basic',
            label: t('settings.basic_settings'),
            content: platform === 'thermostat' ? renderThermostatBasic() : renderAlarmBasic(),
          },
          {
            id: 'advanced',
            label: t('settings.advanced_settings'),
            content: platform === 'thermostat' ? renderThermostatAdvanced() : renderAlarmAdvanced(),
          },
        ]}
      />
    </div>
  );
};

export default TemplateForm;
