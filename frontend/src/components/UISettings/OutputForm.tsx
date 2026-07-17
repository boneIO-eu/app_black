import React, { useState } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import AreaSelect from './widgets/AreaSelect';
import SettingsToggleGroup from './widgets/SettingsToggleGroup';
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

import type { AreaOption } from './widgets/AreaSelect';

interface CoverEntity {
  id?: string;
  name?: string;
  pin?: string;
  open_relay?: string;
  close_relay?: string;
}

interface OutputFormProps {
  data: any;
  onChange: (data: any) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  uiSchema?: any;
  deviceType?: string;
  allOutputs?: any[];
  editingIndex?: number | null;
  allAreas?: AreaOption[];
  interlockGroups?: string[];
  onInterlockGroupCreated?: (groupName: string) => void;
  allCovers?: CoverEntity[];
}

const OutputForm: React.FC<OutputFormProps> = ({ 
  data, 
  onChange, 
  schema,
  uiSchema,
  deviceType,
  allOutputs = [],
  allAreas = [],
  editingIndex,
  interlockGroups = [],
  onInterlockGroupCreated,
  allCovers = []
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');
  const [newInterlockGroup, setNewInterlockGroup] = useState('');

  // Check if this output is used in any cover
  const getUsedInCover = (): CoverEntity | null => {
    const outputId = data.boneio_output || data.id;
    if (!outputId) return null;
    
    for (const cover of allCovers) {
      if (cover.open_relay === outputId || cover.close_relay === outputId) {
        return cover;
      }
    }
    return null;
  };
  
  const usedInCover = getUsedInCover();
  const isUsedInCover = usedInCover !== null;

  // Generate output names based on device type
  const generateBoneioOutputs = (deviceType: string) => {
    const type = deviceType?.toLowerCase() || '';
    
    // Cover type: 01_up, 01_down, 02_up, 02_down ... 16_up, 16_down
    if (type === 'cover') {
      const outputs: string[] = [];
      for (let i = 1; i <= 16; i++) {
        const num = i.toString().padStart(2, '0');
        outputs.push(`${num}_up`);
        outputs.push(`${num}_down`);
      }
      return outputs;
    }
    
    // Cover Mix type: 01_up, 01_down, 02_up, 02_down ... 08_up, 08_down
    if (type === 'cover mix') {
      const outputs: string[] = [];
      for (let i = 1; i <= 8; i++) {
        const num = i.toString().padStart(2, '0');
        outputs.push(`${num}_up`);
        outputs.push(`${num}_down`);
      }
      return outputs;
    }
    
    // 24x16A: OUT_01 - OUT_24
    if (type.includes('24')) {
      return Array.from({ length: 24 }, (_, i) => i + 1).map(num => `OUT_${num.toString().padStart(2, '0')}`);
    }
    
    // 32x10A: OUT_01 - OUT_32
    if (type.includes('32')) {
      return Array.from({ length: 32 }, (_, i) => i + 1).map(num => `OUT_${num.toString().padStart(2, '0')}`);
    }
    
    // 48x4A: OUT_01 - OUT_48 (DISCONTINUED)
    if (type.includes('48')) {
      return Array.from({ length: 48 }, (_, i) => i + 1).map(num => `OUT_${num.toString().padStart(2, '0')}`);
    }
    
    // Default fallback: OUT_01 - OUT_49
    return Array.from({ length: 49 }, (_, i) => i + 1).map(num => `OUT_${num.toString().padStart(2, '0')}`);
  };

  const allBoneioOutputs = generateBoneioOutputs(deviceType || '');
  
  // Filter out already used outputs (except current one)
  const usedOutputs = allOutputs
    .filter((output, index) => {
      // Skip current item being edited
      if (editingIndex !== null && index === editingIndex) {
        return false;
      }
      // For new items, just filter out any used outputs
      return output.boneio_output && output !== data;
    })
    .map(output => output.boneio_output);
  
  const availableOutputs = allBoneioOutputs.filter(output => !usedOutputs.includes(output));
  
  // If editing existing item, always include current output in options (even if it would be filtered)
  const currentOutput = data.boneio_output;
  const boneioOutputOptions = currentOutput
    ? [...new Set([currentOutput, ...availableOutputs])].sort()
    : availableOutputs;

  console.log("boneio output options", boneioOutputOptions);
  
  const outputTypeOptions = schema?.items?.properties?.output_type?.enum || [];

  const updateField = (field: string, value: any) => {
    const newData = { ...data, [field]: value };
    
    // When changing to cover type, clear incompatible fields
    if (field === 'output_type' && value === 'cover') {
      delete newData.momentary_turn_on;
      delete newData.momentary_turn_off;
      delete newData.interlock_group;
      delete newData.area;
      delete newData.restore_state;
      delete newData.adjustable_duration;
      delete newData.duration_default;
      delete newData.duration_min;
      delete newData.duration_max;
      delete newData.duration_unit;
    }
    
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

  const toggleRestoreState = () => {
    updateField('restore_state', !data.restore_state);
  };


  const getFieldDescription = (fieldName: string) => {
    return uiSchema?.[fieldName]?.['ui:description'] || '';
  };

  return (
    <div className="space-y-4">
      {/* Warning alert when output is used in a cover */}
      {isUsedInCover && (
        <div className="alert alert-warning">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h3 className="font-bold">{t('outputs.used_in_cover_title')}</h3>
            <div className="text-sm">
              {t('outputs.used_in_cover_message')} <strong>{usedInCover?.name || usedInCover?.id || usedInCover?.pin || usedInCover?.open_relay || 'unknown'}</strong>
            </div>
          </div>
        </div>
      )}

      {/* Tabs - show only basic for cover type, both for others */}
      {data.output_type === 'cover' ? (
        // Cover type - only basic settings, no tabs needed
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* BoneIO Output - Primary field */}
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('outputs.boneio_output')}</span>
              </label>
              <Select
                value={data.boneio_output || ''}
                onValueChange={(value) => updateField('boneio_output', value)}
                disabled={isUsedInCover}
              >
                <SelectTrigger className={`w-full uppercase ${usedOutputs.length > 0 && boneioOutputOptions.length === 0 ? 'border-warning' : ''} ${isUsedInCover ? 'opacity-50 cursor-not-allowed' : ''}`}>
                  <SelectValue placeholder={t('outputs.select_output')} />
                </SelectTrigger>
                <SelectContent>
                  {boneioOutputOptions.map((output: string) => (
                    <SelectItem key={output} value={output}>
                      {output}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <label className="label">
                <span className="label-text-alt whitespace-normal wrap-break-word">{getFieldDescription('boneio_output')}</span>
              </label>
            </div>

            {/* Output Type */}
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('outputs.output_type')}</span>
              </label>
              <Select
                value={data.output_type || 'none'}
                onValueChange={(value) => updateField('output_type', value)}
                disabled={isUsedInCover}
              >
                <SelectTrigger className={`w-full ${isUsedInCover ? 'opacity-50 cursor-not-allowed' : ''}`}>
                  <SelectValue placeholder={t('outputs.select_type')} />
                </SelectTrigger>
                <SelectContent>
                  {outputTypeOptions.map((type: string) => (
                    <SelectItem key={type} value={type}>
                      {type.charAt(0).toUpperCase() + type.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <label className="label">
                <span className="label-text-alt whitespace-normal wrap-break-word">{getFieldDescription('output_type')}</span>
              </label>
            </div>

            {/* Display Name */}
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('outputs.display_name')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder={t('sensors.output_name_placeholder')}
                value={data.name || ''}
                onChange={(e) => updateField('name', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt whitespace-normal wrap-break-word">{t('common.optional')}</span>
              </label>
            </div>

            {/* Custom ID (optional override) */}
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('outputs.custom_id')}</span>
              </label>
              <input
                type="text"
                className={`input input-bordered w-full ${isUsedInCover ? 'opacity-50 cursor-not-allowed' : ''}`}
                placeholder={data.boneio_output || t('sensors.id_hint')}
                value={data.id || ''}
                onChange={(e) => updateField('id', sanitizeId(e.target.value))}
                disabled={isUsedInCover}
              />
              <label className="label">
                <span className="label-text-alt whitespace-normal wrap-break-word">{t('outputs.auto_sanitized')}</span>
              </label>
            </div>
          </div>
        </div>
      ) : (
        // Non-cover type - show tabs
        <TabsBox
          name="output_tabs"
          activeTab={activeTab}
          onTabChange={(tabId) => setActiveTab(tabId as 'basic' | 'advanced')}
          tabs={[
            {
              id: 'basic',
              label: t('settings.basic_settings'),
              content: (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* BoneIO Output - Primary field */}
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">{t('outputs.boneio_output')}</span>
                      </label>
                      <Select
                        value={data.boneio_output || ''}
                        onValueChange={(value) => updateField('boneio_output', value)}
                        disabled={isUsedInCover}
                      >
                        <SelectTrigger className={`w-full uppercase ${usedOutputs.length > 0 && boneioOutputOptions.length === 0 ? 'border-warning' : ''} ${isUsedInCover ? 'opacity-50 cursor-not-allowed' : ''}`}>
                          <SelectValue placeholder={t('outputs.select_output')} />
                        </SelectTrigger>
                        <SelectContent>
                          {boneioOutputOptions.map((output: string) => (
                            <SelectItem key={output} value={output}>
                              {output}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <label className="label">
                        <span className="label-text-alt whitespace-normal wrap-break-word">{getFieldDescription('boneio_output')}</span>
                      </label>
                      {usedOutputs.length > 0 && boneioOutputOptions.length === 1 && (
                        <label className="label max-w-full">
                          <span 
                            className="label-text-alt text-warning" 
                            style={{ 
                              wordWrap: 'break-word', 
                              wordBreak: 'break-all', 
                              whiteSpace: 'normal',
                              maxWidth: '100%'
                            }}
                          >
                            {t('outputs.all_outputs_used')}
                          </span>
                        </label>
                      )}
                      {usedOutputs.length > 0 && (
                        <label className="label max-w-full">
                          <span className="label-text-alt text-info whitespace-normal break-all">
                            {t('outputs.used_outputs')}: {usedOutputs.length > 5 
                              ? `${usedOutputs.slice(0, 3).join(', ')}, ... (+${usedOutputs.length - 3} more)`
                              : usedOutputs.join(', ')
                            }
                          </span>
                        </label>
                      )}
                    </div>

                    {/* Output Type */}
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">{t('outputs.output_type')}</span>
                      </label>
                      <Select
                        value={data.output_type || 'none'}
                        onValueChange={(value) => updateField('output_type', value)}
                        disabled={isUsedInCover}
                      >
                        <SelectTrigger className={`w-full ${isUsedInCover ? 'opacity-50 cursor-not-allowed' : ''}`}>
                          <SelectValue placeholder={t('outputs.select_type')} />
                        </SelectTrigger>
                        <SelectContent>
                          {outputTypeOptions.map((type: string) => (
                            <SelectItem key={type} value={type}>
                              {type.charAt(0).toUpperCase() + type.slice(1)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <label className="label">
                        <span className="label-text-alt whitespace-normal wrap-break-word">{getFieldDescription('output_type')}</span>
                      </label>
                    </div>

                    {/* Display Name */}
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">{t('outputs.display_name')}</span>
                      </label>
                      <input
                        type="text"
                        className="input input-bordered w-full"
                        placeholder={t('sensors.output_name_placeholder')}
                        value={data.name || ''}
                        onChange={(e) => updateField('name', e.target.value)}
                      />
                      <label className="label">
                        <span className="label-text-alt whitespace-normal wrap-break-word">{t('common.optional')}</span>
                      </label>
                    </div>

                    {/* Custom ID (optional override) */}
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">{t('outputs.custom_id')}</span>
                      </label>
                      <input
                        type="text"
                        className={`input input-bordered w-full ${isUsedInCover ? 'opacity-50 cursor-not-allowed' : ''}`}
                        placeholder={data.boneio_output || t('sensors.id_hint')}
                        value={data.id || ''}
                        onChange={(e) => updateField('id', sanitizeId(e.target.value))}
                        disabled={isUsedInCover}
                      />
                      <label className="label">
                        <span className="label-text-alt whitespace-normal wrap-break-word">{t('outputs.auto_sanitized')}</span>
                      </label>
                    </div>

                    {/* Area / Room */}
                    <AreaSelect
                      value={data.area}
                      onChange={(v) => updateField('area', v)}
                      areas={allAreas}
                    />
                  </div>

                  {/* Restore State */}
                  <div className="divider">{t('outputs.divider_options')}</div>

                  <SettingsToggleGroup
                    items={[
                      {
                        key: 'restore_state',
                        label: t('outputs.restore_state'),
                        description: getFieldDescription('restore_state'),
                        checked: data.restore_state === true,
                        onChange: () => toggleRestoreState(),
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
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Momentary Turn On */}
                    <SimpleTimePeriodInput
                      value={data.momentary_turn_on || ''}
                      onChange={(value: string) => {
                        // Treat zero values ("0s", "0ms", etc.) as clearing the field
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

                  {/* Adjustable Duration */}
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

                  <div className="divider">{t('outputs.divider_interlock')}</div>

                  <div className="grid grid-cols-1 gap-4">
                    {/* Current Interlock Group */}
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">{t('outputs.interlock_group_label')}</span>
                      </label>
                      <Select
                        value={data.interlock_group || '_none_'}
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
                          {data.interlock_group && !interlockGroups.includes(data.interlock_group) && (
                            <SelectItem value={data.interlock_group}>
                              {data.interlock_group} ({t('outputs.interlock_group_new')})
                            </SelectItem>
                          )}
                        </SelectContent>
                      </Select>
                      <label className="label">
                        <span className="label-text-alt whitespace-normal wrap-break-word">
                          {t('outputs.interlock_description')}
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
                          className="input input-bordered flex-1"
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

                  <div className="alert alert-info">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <div>
                      <h3 className="font-bold">{t('outputs.software_interlock_title')}</h3>
                      <div className="text-sm">
                        <p>{t('outputs.software_interlock_desc1')}</p>
                        <p>{t('outputs.software_interlock_desc2')}</p>
                      </div>
                    </div>
                  </div>
                </div>
              ),
            },
          ]}
        />
      )}
    </div>
  );
};

export default OutputForm;
