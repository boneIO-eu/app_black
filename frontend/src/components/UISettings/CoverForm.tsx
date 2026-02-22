import React, { useState } from 'react';
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

  const platformOptions = schema?.items?.properties?.platform?.enum || ['time_based', 'venetian'];
  const deviceClassOptions = schema?.items?.properties?.device_class?.enum || [
    'awning', 'blind', 'curtain', 'damper', 'door', 'garage', 'gate', 'shade', 'shutter', 'window'
  ];

  const updateField = (field: string, value: any) => {
    const newData = { ...data, [field]: value };
    
    // Clean up platform-specific fields when platform changes
    if (field === 'platform') {
      if (value !== 'venetian') {
        // Remove tilt_duration when not venetian
        delete newData.tilt_duration;
      }
    }
    
    onChange(newData);
  };

  const selectedPlatform = data.platform || 'time_based';
  const showTiltDuration = selectedPlatform === 'venetian';

  return (
    <div className="space-y-4">
      <TabsBox
        name="cover_tabs"
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
                    placeholder={t('sensors.cover_name_placeholder')}
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
                    <span className="label-text-alt whitespace-normal wrap-break-words">
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
                    </span>
                  </label>
                </div>

                {/* Open Relay */}
                <div className="form-control">
                  <label className="label">
                    <span className="label-text font-medium">{t('covers.open_relay')} *</span>
                  </label>
                  <OutputSelectDropdown
                    value={data.open_relay || ''}
                    onChange={(value: string) => updateField('open_relay', value)}
                    allOutputs={allOutputs.filter((output: any) => 
                      output && typeof output === 'object' && 
                      (output.id || output.boneio_output) &&
                      output.output_type?.toLowerCase() === 'cover'
                    )}
                    allAreas={allAreas}
                    placeholder={t('covers.select_relay')}
                    excludeIds={data.close_relay ? [data.close_relay] : []}
                  />
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
                  <OutputSelectDropdown
                    value={data.close_relay || ''}
                    onChange={(value: string) => updateField('close_relay', value)}
                    allOutputs={allOutputs.filter((output: any) => 
                      output && typeof output === 'object' && 
                      (output.id || output.boneio_output) &&
                      output.output_type?.toLowerCase() === 'cover'
                    )}
                    allAreas={allAreas}
                    placeholder={t('covers.select_relay')}
                    excludeIds={data.open_relay ? [data.open_relay] : []}
                  />
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

              </div>
            ),
          },
          {
            id: 'advanced',
            label: t('settings.advanced_settings'),
            content: (
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
            ),
          },
        ]}
      />
    </div>
  );
};

export default CoverForm;
