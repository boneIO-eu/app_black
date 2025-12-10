import React, { useState, useMemo } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
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

interface CoverFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  allOutputs?: any[];
  allAreas?: Area[];
}

const CoverForm: React.FC<CoverFormProps> = ({ 
  data, 
  onChange, 
  schema,
  allOutputs = [],
  allAreas = []
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  // Get available outputs that have output_type === 'cover' (or deprecated 'none')
  const availableCoverOutputs = useMemo(() => {
    return allOutputs
      .filter(output => {
        const outputType = output.output_type?.toLowerCase();
        return outputType === 'cover'; // 'none' is deprecated
      })
      .map(output => output.boneio_output || output.id)
      .filter(Boolean);
  }, [allOutputs]);

  // Extract enums from schema
  const platformOptions = schema?.items?.properties?.platform?.enum || ['time_based', 'venetian', 'previous'];
  const deviceClassOptions = schema?.items?.properties?.device_class?.enum || [
    'awning', 'blind', 'curtain', 'damper', 'door', 'garage', 'gate', 'shade', 'shutter', 'window'
  ];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const selectedPlatform = data.platform || 'previous';
  const showTiltDuration = selectedPlatform === 'venetian';
  const showActuatorDuration = selectedPlatform === 'previous';

  return (
    <div className="space-y-4">
      {/* Tabs */}
      <div className="tabs tabs-boxed">
        <button 
          className={`tab ${activeTab === 'basic' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          {t('settings.basic_settings')}
        </button>
        <button 
          className={`tab ${activeTab === 'advanced' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('advanced')}
        >
          {t('settings.advanced_settings')}
        </button>
      </div>

      {/* Basic Tab */}
      {activeTab === 'basic' && (
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
              placeholder={t('sensors.name_placeholder')}
            />
            <label className="label">
              <span className="label-text-alt text-info">
                {t('common.optional')}
              </span>
            </label>
          </div>

          {/* ID */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('outputs.id')}</span>
            </label>
            <input
              type="text"
              className="input w-full"
              value={data.id || ''}
              onChange={(e) => updateField('id', sanitizeId(e.target.value))}
              placeholder={t('sensors.id_hint')}
            />
            <label className="label">
              <span className="label-text-alt text-info">
                {t('modbus.technical_id')}
                {!data.id && data.open_relay && data.close_relay && (
                  <span className="block mt-1">
                    {t('modbus.will_be')}: <code className="bg-base-300 px-1 rounded">cover_{data.open_relay}_{data.close_relay}</code>
                  </span>
                )}
              </span>
            </label>
          </div>

          {/* Area / Room */}
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
            <label className="label">
              <span className="label-text-alt whitespace-normal break-words">
                {allAreas.length === 0 
                  ? t('outputs.area_empty_hint')
                  : t('outputs.area_hint')
                }
              </span>
            </label>
          </div>

          {/* Platform */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('covers.platform')} *</span>
            </label>
            <Select
              value={selectedPlatform}
              onValueChange={(value) => updateField('platform', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('covers.select_platform')} />
              </SelectTrigger>
              <SelectContent>
                {platformOptions.map((platform: string) => (
                  <SelectItem key={platform} value={platform}>
                    {platform.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label className="label">
              <span className="label-text-alt text-info">
                {selectedPlatform === 'time_based' && t('covers.platform_time_based')}
                {selectedPlatform === 'venetian' && t('covers.platform_venetian')}
                {selectedPlatform === 'previous' && t('covers.platform_previous')}
              </span>
            </label>
          </div>

          {/* Open Relay */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('covers.open_relay')} *</span>
            </label>
            {availableCoverOutputs.length === 0 ? (
              <div className="alert alert-warning">
                <span>{t('covers.no_cover_outputs')}</span>
              </div>
            ) : (
              <Select
                value={data.open_relay || ''}
                onValueChange={(value) => updateField('open_relay', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('covers.select_relay')} />
                </SelectTrigger>
                <SelectContent>
                  {availableCoverOutputs
                    .filter((output: string) => output !== data.close_relay)
                    .map((output: string) => (
                      <SelectItem key={output} value={output}>
                        {output}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            )}
            <label className="label">
              <span className="label-text-alt text-info">
                {t('covers.open_relay_hint')}
              </span>
            </label>
          </div>

          {/* Close Relay */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('covers.close_relay')} *</span>
            </label>
            {availableCoverOutputs.length === 0 ? (
              <div className="alert alert-warning">
                <span>{t('covers.no_cover_outputs')}</span>
              </div>
            ) : (
              <Select
                value={data.close_relay || ''}
                onValueChange={(value) => updateField('close_relay', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('covers.select_relay')} />
                </SelectTrigger>
                <SelectContent>
                  {availableCoverOutputs
                    .filter((output: string) => output !== data.open_relay)
                    .map((output: string) => (
                      <SelectItem key={output} value={output}>
                        {output}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            )}
            <label className="label">
              <span className="label-text-alt text-info">
                {t('covers.close_relay_hint')}
              </span>
            </label>
          </div>

          {/* Open Time */}
          <SimpleTimePeriodInput
            value={data.open_time || ''}
            onChange={(value: string) => updateField('open_time', value)}
            label={t('covers.open_time')}
            required={true}
            minimum={1000}
          />

          {/* Close Time */}
          <SimpleTimePeriodInput
            value={data.close_time || ''}
            onChange={(value: string) => updateField('close_time', value)}
            label={t('covers.close_time')}
            required={true}
            minimum={1000}
          />

          {/* Tilt Duration - only for venetian */}
          {showTiltDuration && (
            <SimpleTimePeriodInput
              value={data.tilt_duration || ''}
              onChange={(value: string) => updateField('tilt_duration', value)}
              label={t('covers.tilt_duration')}
              required={false}
              minimum={10}
            />
          )}

          {/* Actuator Activation Duration - only for previous */}
          {showActuatorDuration && (
            <SimpleTimePeriodInput
              value={data.actuator_activation_duration || ''}
              onChange={(value: string) => updateField('actuator_activation_duration', value)}
              label={t('covers.actuator_duration')}
              required={false}
              minimum={0}
            />
          )}
        </div>
      )}

      {/* Advanced Tab */}
      {activeTab === 'advanced' && (
        <div className="space-y-4">
          {/* Device Class */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('covers.device_class')}</span>
            </label>
            <Select
              value={data.device_class || '_none_'}
              onValueChange={(value) => updateField('device_class', value === '_none_' ? undefined : value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('inputs.none')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_none_">{t('inputs.none')}</SelectItem>
                {deviceClassOptions.map((deviceClass: string) => (
                  <SelectItem key={deviceClass} value={deviceClass}>
                    {deviceClass.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label className="label">
              <span className="label-text-alt text-info">
                {t('covers.device_class_hint')}
              </span>
            </label>
          </div>

          {/* Restore State */}
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="checkbox"
                checked={data.restore_state || false}
                onChange={(e) => updateField('restore_state', e.target.checked)}
              />
              <div>
                <span className="label-text font-medium">{t('covers.restore_state')}</span>
                <p className="text-sm text-base-content/70 mt-1">
                  {t('covers.restore_state_hint')}
                </p>
              </div>
            </label>
          </div>

          {/* Show in HA */}
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="checkbox"
                checked={data.show_in_ha !== false}
                onChange={(e) => updateField('show_in_ha', e.target.checked)}
              />
              <div>
                <span className="label-text font-medium">{t('inputs.show_in_ha')}</span>
                <p className="text-sm text-base-content/70 mt-1">
                  {t('covers.show_in_ha_hint')}
                </p>
              </div>
            </label>
          </div>
        </div>
      )}

    </div>
  );
};

export default CoverForm;
