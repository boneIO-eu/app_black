import React, { useState, useMemo } from 'react';
import AreaSelect from './widgets/AreaSelect';
import SettingsToggleGroup from './widgets/SettingsToggleGroup';
import SearchableMultiEntityPicker from './SearchableMultiEntityPicker';
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

interface OutputGroupFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  allOutputs?: any[];
  allAreas?: any[];
}

const OutputGroupForm: React.FC<OutputGroupFormProps> = ({ 
  data, 
  onChange, 
  schema,
  allOutputs = [],
  allAreas = []
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  // Get available outputs from allOutputs with their effective IDs.
  // Local outputs have `boneio_output`; remote outputs have `remote_source` + `device_id`.
  // Both are keyed in backend's _outputs by their effective ID.
  const availableOutputs = useMemo(() => allOutputs
    .filter(output => {
      // Exclude covers — they can't be group members
      if (output.output_type === 'cover') return false;
      // Local output: must have boneio_output
      if (output.boneio_output) return true;
      // Remote output: has remote_source + device_id (or at least an id)
      if (output.remote_source && output.device_id) return true;
      // Remote output with explicit id
      if (output.id && output.remote_source) return true;
      return false;
    })
    .map(output => {
      const isRemote = !!output.remote_source;
      const effectiveId = isRemote
        ? (output.id || `${output.device_id}_${output.output_id}`)
        : (output.id || output.boneio_output);
      return {
        id: effectiveId,
        name: output.name || effectiveId,
        area: output.area || '',
        badge: isRemote
          ? `📡 ${output.device_id || output.remote_source}`
          : (output.boneio_output !== effectiveId ? output.boneio_output : undefined),
        badgeClass: isRemote ? 'badge-info' : 'badge-ghost',
      };
    })
    .sort((a, b) => a.id.localeCompare(b.id)), [allOutputs]);

  // Extract enums from schema
  const outputTypeOptions = schema?.items?.properties?.output_type?.enum || ['switch', 'light'];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleOutputsChange = (selectedOutputs: string[]) => {
    updateField('outputs', selectedOutputs);
  };


  const selectedOutputs = Array.isArray(data.outputs) ? data.outputs : [];

  return (
    <div className="space-y-4">
      <TabsBox
        name="output_group_tabs"
        activeTab={activeTab}
        onTabChange={(tabId) => setActiveTab(tabId as 'basic' | 'advanced')}
        tabs={[
          {
            id: 'basic',
            label: t('settings.basic_settings'),
            content: (
              <div className="space-y-4">
                {/* ID */}
                <div className="form-control">
                  <label className="label">
                    <span className="label-text font-medium">{t('groups.id')} *</span>
                  </label>
                  <input
                    type="text"
                    className="input w-full"
                    value={data.id || ''}
                    onChange={(e) => updateField('id', sanitizeId(e.target.value))}
                    placeholder="e.g., lights_living_room"
                  />
                  <p className="text-xs text-base-content/60 mt-1">
                    {t('groups.id_hint')}
                  </p>
                </div>

                {/* Name */}
                <div className="form-control">
                  <label className="label">
                    <span className="label-text font-medium">{t('groups.name')}</span>
                  </label>
                  <input
                    type="text"
                    className="input w-full"
                    value={data.name || ''}
                    onChange={(e) => updateField('name', e.target.value)}
                    placeholder="e.g., Living Room Lights"
                  />
                  <p className="text-xs text-base-content/60 mt-1">
                    {t('groups.name_hint')}
                  </p>
                </div>

                {/* Outputs Selection */}
                <div className="form-control">
                  <SearchableMultiEntityPicker
                    value={selectedOutputs}
                    onChange={handleOutputsChange}
                    items={availableOutputs}
                    allAreas={allAreas}
                    label={t('groups.member_outputs')}
                    placeholder={t('groups.select_outputs')}
                    required
                    errorMessage={t('groups.at_least_one_required')}
                  />
                </div>

                {/* Output Type */}
                <div className="form-control">
                  <label className="label">
                    <span className="label-text font-medium">{t('groups.output_type')}</span>
                  </label>
                  <Select
                    value={data.output_type || 'switch'}
                    onValueChange={(value) => updateField('output_type', value)}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t('outputs.select_type')} />
                    </SelectTrigger>
                    <SelectContent>
                      {outputTypeOptions.map((type: string) => (
                        <SelectItem key={type} value={type}>
                          {type.toUpperCase()}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-base-content/60 mt-1">
                    {t('groups.output_type_hint')}
                  </p>
                </div>

                {/* Area */}
                <AreaSelect
                  value={data.area}
                  onChange={(v) => updateField('area', v)}
                  areas={allAreas}
                  hint={t('groups.area_hint')}
                />
              </div>
            ),
          },
          {
            id: 'advanced',
            label: t('settings.advanced_settings'),
            content: (
              <div className="space-y-4">
                <SettingsToggleGroup
                  items={[
                    {
                      key: 'all_on_behaviour',
                      label: t('groups.all_on_behaviour'),
                      description: t('groups.all_on_behaviour_hint'),
                      checked: data.all_on_behaviour || false,
                      onChange: (checked) => updateField('all_on_behaviour', checked),
                    },
                  ]}
                />
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default OutputGroupForm;
