import React, { useState } from 'react';
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
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const availableSensorIds = allSensors
    .map((s: any) => s.id || s.address || '')
    .filter(Boolean);

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
          ),
        },
      ]}
    />
  );
};

export default ThermostatForm;
