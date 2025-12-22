import React, { useState } from 'react';
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
  allAreas?: Area[];
  interlockGroups?: string[];
  onInterlockGroupCreated?: (groupName: string) => void;
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
  onInterlockGroupCreated
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');
  const [newInterlockGroup, setNewInterlockGroup] = useState('');

  // Extract enums from schema for dropdowns
  const getOutputCount = (deviceType: string) => {
    const type = deviceType?.toLowerCase() || '';
    if (type.includes('32') || type.includes('cm')) {
      return 32; // 32x10A, Cover, Cover Mix
    } else if (type.includes('24')) {
      return 24; // 24x16A
    }
    return 49; // default fallback
  };

  const outputCount = getOutputCount(deviceType || '');
  const allBoneioOutputs = Array.from({ length: outputCount }, (_, i) => i + 1).map(num => `OUT_${num.toString().padStart(2, '0')}`);
  
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
  
  // If current output is used by this item, include it in options
  const currentOutput = data.boneio_output;
  const boneioOutputOptions = currentOutput && usedOutputs.includes(currentOutput)
    ? [...new Set([currentOutput, ...availableOutputs])].sort()
    : availableOutputs;
  
  const outputTypeOptions = schema?.items?.properties?.output_type?.enum || [];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const toggleRestoreState = () => {
    updateField('restore_state', !data.restore_state);
  };


  const getFieldDescription = (fieldName: string) => {
    return uiSchema?.[fieldName]?.['ui:description'] || '';
  };

  return (
    <div className="space-y-4">
      {/* DaisyUI Tabs */}
      <div className="tabs tabs-bordered tabs-lifted">
        <a 
          className={`tab ${activeTab === 'basic' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          {t('settings.basic_settings') || 'Basic Settings'}
        </a>
        <a 
          className={`tab ${activeTab === 'advanced' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('advanced')}
        >
          {t('settings.advanced_settings') || 'Advanced Settings'}
        </a>
      </div>

      {/* Basic Settings Tab */}
      {activeTab === 'basic' && (
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
              >
                <SelectTrigger className={`w-full uppercase ${usedOutputs.length > 0 && boneioOutputOptions.length === 0 ? 'border-warning' : ''}`}>
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
              >
                <SelectTrigger className="w-full">
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
                placeholder={t('sensors.name_placeholder')}
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
                className="input input-bordered w-full"
                placeholder={data.boneio_output || t('sensors.id_hint')}
                value={data.id || ''}
                onChange={(e) => updateField('id', sanitizeId(e.target.value))}
              />
              <label className="label">
                <span className="label-text-alt whitespace-normal wrap-break-word">{t('outputs.auto_sanitized')}</span>
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
                <span className="label-text-alt whitespace-normal wrap-break-word">
                  {allAreas.length === 0 
                    ? t('outputs.area_empty_hint')
                    : t('outputs.area_hint')
                  }
                </span>
              </label>
            </div>
          </div>

          <div className="divider">{t('outputs.divider_options')}</div>

          <div className="grid grid-cols-1 gap-4">
            <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
              <legend className="fieldset-legend">{t('outputs.restore_state')}</legend>
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={data.restore_state === true}
                  onChange={toggleRestoreState}
                />
                <span className="label-text">{getFieldDescription('restore_state')}</span>
              </label>
            </fieldset>
          </div>
        </div>
      )}

      {/* Advanced Settings Tab */}
      {activeTab === 'advanced' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Momentary Turn On */}
            <SimpleTimePeriodInput
              value={data.momentary_turn_on || ''}
              onChange={(value: string) => updateField('momentary_turn_on', value || undefined)}
              label={t('outputs.momentary_turn_on')}
              required={false}
              minimum={0}
            />

            {/* Momentary Turn Off */}
            <SimpleTimePeriodInput
              value={data.momentary_turn_off || ''}
              onChange={(value: string) => updateField('momentary_turn_off', value || undefined)}
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
      )}
    </div>
  );
};

export default OutputForm;
