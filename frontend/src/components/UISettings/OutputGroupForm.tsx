import React, { useState } from 'react';
import AreaSelect from './widgets/AreaSelect';
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

  // Get available outputs from allOutputs with their effective IDs
  // The backend keys outputs by custom `id` if set, otherwise by `boneio_output`.
  // Groups must reference the effective ID so the backend can look them up in _outputs.
  const availableOutputs = allOutputs
    .filter(output => output.boneio_output && output.output_type !== 'cover')
    .map(output => {
      const effectiveId = output.id || output.boneio_output;
      return {
        id: effectiveId,
        name: output.name || effectiveId,
        displayName: `${output.name || effectiveId} : ${output.boneio_output}`,
        outputType: output.output_type,
        boneioOutput: output.boneio_output,
      };
    })
    .sort((a, b) => a.id.localeCompare(b.id));

  // Extract enums from schema
  const outputTypeOptions = schema?.items?.properties?.output_type?.enum || ['switch', 'light'];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleOutputsChange = (selectedOutputs: string[]) => {
    updateField('outputs', selectedOutputs);
  };

  const toggleOutput = (outputId: string) => {
    const currentOutputs = Array.isArray(data.outputs) ? data.outputs : [];
    const newOutputs = currentOutputs.includes(outputId)
      ? currentOutputs.filter((o: string) => o !== outputId)
      : [...currentOutputs, outputId];
    handleOutputsChange(newOutputs);
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
                  <label className="label">
                    <span className="label-text font-medium">{t('groups.member_outputs')} *</span>
                  </label>
                  <div className="border border-base-300 rounded-lg p-3">
                    {availableOutputs.length === 0 ? (
                      <p className="text-warning">{t('groups.no_outputs_available')}</p>
                    ) : (
                      <div className="flex flex-col gap-1">
                        {availableOutputs.map((output) => (
                          <label 
                            key={output.id} 
                            className={`label cursor-pointer justify-start gap-3 px-3 py-2 rounded-lg hover:bg-base-200 transition-colors ${
                              selectedOutputs.includes(output.id) ? 'bg-primary/10' : ''
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="checkbox checkbox-sm checkbox-primary"
                              checked={selectedOutputs.includes(output.id)}
                              onChange={() => toggleOutput(output.id)}
                            />
                            <span className="label-text flex-1">
                              <span className="font-medium">{output.name}</span>
                              <span className="text-base-content/60 ml-2 uppercase text-xs">
                                ({output.id}{output.boneioOutput !== output.id ? ` → ${output.boneioOutput}` : ''})
                              </span>
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap justify-between gap-2 mt-2">
                    <p className="text-xs text-base-content/60">
                      {t('groups.selected')}: {selectedOutputs.length > 0 
                        ? selectedOutputs.map((id: string) => {
                            const output = availableOutputs.find(o => o.id === id);
                            return output ? output.name : id;
                          }).join(', ') 
                        : t('common.no')}
                    </p>
                    {selectedOutputs.length === 0 && (
                      <p className="text-xs text-error">
                        {t('groups.at_least_one_required')}
                      </p>
                    )}
                  </div>
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
                {/* All On Behaviour */}
                <div className="form-control">
                  <label className="label cursor-pointer justify-start gap-4">
                    <input
                      type="checkbox"
                      className="checkbox"
                      checked={data.all_on_behaviour || false}
                      onChange={(e) => updateField('all_on_behaviour', e.target.checked)}
                    />
                    <span className="label-text font-medium">{t('groups.all_on_behaviour')}</span>
                  </label>
                  <p className="text-xs text-base-content/60 ml-10">
                    {t('groups.all_on_behaviour_hint')}
                  </p>
                </div>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default OutputGroupForm;
