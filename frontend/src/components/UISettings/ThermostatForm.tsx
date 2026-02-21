import React, { useState, useMemo, useEffect } from 'react';
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
import type { TemplateSubFormProps } from './types/template';
import axios from '@/api/axios';

interface TemperatureSensor {
  id: string;
  label: string;
  source: string;
}

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
  const [modbusModels, setModbusModels] = useState<Record<string, { has_temperature: boolean }>>({});

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  // Fetch Modbus model capabilities once
  useEffect(() => {
    axios.get('/api/modbus/models')
      .then((res) => setModbusModels(res.data.models || {}))
      .catch(() => {});
  }, []);

  /**
   * Build a unified list of temperature sensors from all sources:
   * - 1-Wire sensors (sensor section)
   * - I2C sensors (LM75, MCP9808)
   * - Modbus devices whose model has_temperature capability
   */
  const temperatureSensors: TemperatureSensor[] = useMemo(() => {
    const sensors: TemperatureSensor[] = [];

    for (const s of allSensors) {
      const src = s._source || '';
      if (src === 'lm75' || src === 'mcp9808') {
        // I2C temperature sensors (LM75/PCT2075, MCP9808)
        const id = (s.id || '').replace(/\s/g, '');
        if (id) {
          sensors.push({
            id,
            label: s.id || `${src.toUpperCase()} @ 0x${(s.address ?? 0).toString(16)}`,
            source: src.toUpperCase(),
          });
        }
      } else {
        // 1-Wire / Dallas sensors
        const id = s.id || s.address || '';
        if (id) {
          sensors.push({
            id,
            label: s.name || s.id || s.address,
            source: '1-Wire',
          });
        }
      }
    }

    // Modbus devices — use capabilities from /api/modbus/models
    // devId must match backend coordinator ID generation:
    //   custom id: str(id).replace(' ','').lower()
    //   auto id:   `${address}_${model}`.lower().replace(' ', '_')
    for (const dev of allModbusDevices) {
      const model = (dev.model || '').toLowerCase();
      const devId = dev.id
        ? String(dev.id).replace(/\s/g, '').toLowerCase()
        : `${dev.address}_${model}`.toLowerCase().replace(/\s/g, '_');
      if (modbusModels[model]?.has_temperature) {
        sensors.push({
          id: `${devId}_temperature`,
          label: `${dev.name || devId} (${t('template.modbus_temp')})`,
          source: 'Modbus',
        });
      }
    }

    return sensors;
  }, [allSensors, allModbusDevices, modbusModels, t]);

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

              {/* Temperature Sensors — multi-select checkboxes */}
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('template.sensor_id')} *</span>
                </label>
                {(() => {
                  const selectedIds: string[] = data.sensor_ids || (data.sensor_id ? [data.sensor_id] : []);
                  const toggleSensor = (sensorId: string) => {
                    const newIds = selectedIds.includes(sensorId)
                      ? selectedIds.filter((id: string) => id !== sensorId)
                      : [...selectedIds, sensorId];
                    onChange({ ...data, sensor_ids: newIds, sensor_id: newIds[0] || '' });
                  };
                  // IDs selected manually that are not in the known sensor list
                  const knownIds = new Set(temperatureSensors.map((s) => s.id));
                  const manualIds = selectedIds.filter((id) => !knownIds.has(id));

                  return (
                    <div className="space-y-2">
                      {temperatureSensors.length > 0 && (
                        <div className="space-y-1 p-3 bg-base-200 rounded-lg max-h-48 overflow-y-auto">
                          {temperatureSensors.map((sensor) => (
                            <label key={sensor.id} className="flex items-center gap-2 cursor-pointer py-1">
                              <input
                                type="checkbox"
                                className="checkbox checkbox-sm checkbox-primary"
                                checked={selectedIds.includes(sensor.id)}
                                onChange={() => toggleSensor(sensor.id)}
                              />
                              <span className="badge badge-xs badge-outline">{sensor.source}</span>
                              <span className="text-sm">{sensor.label}</span>
                            </label>
                          ))}
                        </div>
                      )}
                      {temperatureSensors.length === 0 && selectedIds.length === 0 && (
                        <div className="text-sm text-base-content/50 italic p-3 bg-base-200 rounded-lg">
                          {t('template.no_sensors_available')}
                        </div>
                      )}
                      {/* Manually added IDs (not in known sensor list) — shown as removable chips */}
                      {manualIds.map((id) => (
                        <div key={id} className="flex items-center gap-2 px-3 py-1 bg-base-200 rounded-lg">
                          <input
                            type="checkbox"
                            className="checkbox checkbox-sm checkbox-primary"
                            checked
                            onChange={() => toggleSensor(id)}
                          />
                          <span className="badge badge-xs badge-ghost">manual</span>
                          <span className="text-sm font-mono">{id}</span>
                        </div>
                      ))}
                    </div>
                  );
                })()}
                <label className="label">
                  <span className="label-text-alt text-info">{t('template.sensor_ids_hint')}</span>
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
