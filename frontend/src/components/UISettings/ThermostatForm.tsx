import React, { useState, useMemo, useEffect, useCallback } from 'react';
import AreaSelect from './widgets/AreaSelect';
import SearchableEntityPicker from './SearchableEntityPicker';
import SearchableMultiEntityPicker from './SearchableMultiEntityPicker';
import { sanitizeId } from './helpers/idValidation';
import {
  buildTemperatureSensors,
  buildSensorItems,
  buildOutputItems,
} from './helpers/thermostatHelpers';
import type {
  ThermostatData,
  ModbusModelInfo,
  SensorConfigEntry,
  ModbusDeviceEntry,
  OutputConfigEntry,
} from './helpers/thermostatHelpers';
import { useTranslation } from '@/hooks/useTranslation';
import { TabsBox } from '@/components/ui/tabs-box';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { TemplateSubFormProps } from './types/template';
import axios from '@/api/axios';

/**
 * ThermostatForm — configuration form for the thermostat template platform.
 *
 * Bang-bang climate controller: reads a temperature sensor, controls a relay
 * output with configurable hysteresis, target temperature, and min/max range.
 */
const ThermostatForm: React.FC<TemplateSubFormProps> = ({
  data,
  onChange,
  allOutputs,
  allAreas,
  allSensors,
  allModbusDevices,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');
  const [modbusModels, setModbusModels] = useState<Record<string, ModbusModelInfo>>({});

  /** Typed accessor for thermostat form data. */
  const formData = data as ThermostatData;

  const updateField = <K extends keyof ThermostatData>(field: K, value: ThermostatData[K]) => {
    onChange({ ...data, [field]: value });
  };

  // Fetch Modbus model capabilities once
  useEffect(() => {
    axios.get('/api/modbus/models')
      .then((res) => setModbusModels((res.data as { models?: Record<string, ModbusModelInfo> }).models || {}))
      .catch(() => {});
  }, []);

  /** Build temperature sensors from all config sources using extracted helper. */
  const temperatureSensors = useMemo(
    () => buildTemperatureSensors(
      allSensors as SensorConfigEntry[],
      allModbusDevices as ModbusDeviceEntry[],
      modbusModels,
    ),
    [allSensors, allModbusDevices, modbusModels]
  );

  /** Currently selected sensor IDs (handles legacy single sensor_id). */
  const selectedSensorIds: string[] = useMemo(
    () => formData.sensor_ids || (formData.sensor_id ? [formData.sensor_id] : []),
    [formData.sensor_ids, formData.sensor_id]
  );

  /** Sensor items for the multi-select picker (includes orphan/unavailable items). */
  const sensorItems = useMemo(
    () => buildSensorItems(temperatureSensors, selectedSensorIds, t('common.unavailable')),
    [temperatureSensors, selectedSensorIds, t]
  );

  /** Handle sensor selection changes, keeping both sensor_ids and legacy sensor_id in sync. */
  const handleSensorChange = useCallback(
    (newIds: string[]) => {
      onChange({ ...data, sensor_ids: newIds, sensor_id: newIds[0] || '' });
    },
    [data, onChange]
  );

  /** Output items for the single-select picker. */
  const outputItems = useMemo(
    () => buildOutputItems(allOutputs as OutputConfigEntry[]),
    [allOutputs]
  );

  return (
    <TabsBox
      name="thermostat_tabs"
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
                  placeholder={t('template.thermostat_name_placeholder')}
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

              {/* Temperature Sensors — multi-select picker */}
              <div className="form-control">
                <SearchableMultiEntityPicker
                  value={selectedSensorIds}
                  onChange={handleSensorChange}
                  items={sensorItems}
                  allAreas={allAreas}
                  label={`${t('template.sensor_id')} *`}
                  placeholder={t('template.select_sensors')}
                  required
                  errorMessage={t('template.sensor_required')}
                  preferredArea={data.area}
                />
                <label className="label">
                  <span className="label-text-alt text-info">{t('template.sensor_ids_hint')}</span>
                </label>
              </div>

              {/* Output ID */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.output_id')} *</span>
                </label>
                <SearchableEntityPicker
                  value={data.output_id || ''}
                  onChange={(value: string) => updateField('output_id', value)}
                  items={outputItems}
                  allAreas={allAreas}
                  placeholder={t('template.select_output')}
                  recentKey="thermostat-outputs"
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
                    type="text"
                    inputMode="decimal"
                    className="input w-full"
                    value={data.target_temperature ?? '21'}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === '' || v === '-' || /^-?\d*\.?\d*$/.test(v)) {
                        updateField('target_temperature', v === '' ? '' : v);
                      }
                    }}
                    onBlur={() => {
                      const num = parseFloat(data.target_temperature);
                      if (!isNaN(num)) updateField('target_temperature', num);
                      else updateField('target_temperature', 21);
                    }}
                  />
                  <span className="text-base-content/70">°C</span>
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
              {/* Initial Mode */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.initial_mode')}</span>
                </label>
                <Select
                  value={data.mode || 'heat'}
                  onValueChange={(value) => updateField('mode', value as ThermostatData['mode'])}
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
                    type="text"
                    inputMode="decimal"
                    className="input w-full"
                    value={data.hysteresis ?? '0.5'}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === '' || /^\d*\.?\d*$/.test(v)) {
                        updateField('hysteresis', v === '' ? '' : v);
                      }
                    }}
                    onBlur={() => {
                      const num = parseFloat(data.hysteresis);
                      if (!isNaN(num) && num > 0) updateField('hysteresis', num);
                      else updateField('hysteresis', 0.5);
                    }}
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
                    type="text"
                    inputMode="decimal"
                    className="input w-full"
                    value={data.min_temperature ?? '5'}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === '' || v === '-' || /^-?\d*\.?\d*$/.test(v)) {
                        updateField('min_temperature', v === '' ? '' : v);
                      }
                    }}
                    onBlur={() => {
                      const num = parseFloat(data.min_temperature);
                      if (!isNaN(num)) updateField('min_temperature', num);
                      else updateField('min_temperature', 5);
                    }}
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
                    type="text"
                    inputMode="decimal"
                    className="input w-full"
                    value={data.max_temperature ?? '35'}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === '' || v === '-' || /^-?\d*\.?\d*$/.test(v)) {
                        updateField('max_temperature', v === '' ? '' : v);
                      }
                    }}
                    onBlur={() => {
                      const num = parseFloat(data.max_temperature);
                      if (!isNaN(num)) updateField('max_temperature', num);
                      else updateField('max_temperature', 35);
                    }}
                  />
                  <span className="text-base-content/70">°C</span>
                </div>
              </div>
            </div>
          ),
        },
      ]}
    />
  );
};

export default ThermostatForm;
