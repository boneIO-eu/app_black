import React from 'react';
import { FaTrash } from 'react-icons/fa';
import { sanitizeId } from './helpers/idValidation';
import OutputSelectDropdown from './OutputSelectDropdown';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// Export validation function for use in parent components
export const validateAction = (action: any, t: (key: string) => string): string | null => {
  if (!action.action) return t('event_form.validation_action_type_required');
  
  const actionType = action.action.toLowerCase();
  
  if (actionType === 'output' || actionType === 'output_over_mqtt') {
    if (!action.pin) return t('event_form.validation_output_required');
  }
  
  if (actionType === 'cover' || actionType === 'cover_over_mqtt') {
    if (!action.pin) return t('event_form.validation_cover_required');
  }
  
  if (actionType === 'mqtt') {
    if (!action.topic) return t('event_form.validation_topic_required');
  }
  
  if (actionType === 'output_over_mqtt' || actionType === 'cover_over_mqtt') {
    if (!action.boneio_id) return t('event_form.validation_boneio_id_required');
  }
  
  return null;
};

interface Area {
  id: string;
  name: string;
}

interface ActionFieldsProps {
  action: any;
  index: number;
  onUpdate: (field: string, value: any) => void;
  onRemove: () => void;
  allOutputs: any[];
  allOutputGroups: any[];
  allCovers: any[];
  allAreas: Area[];
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
  showValidation?: boolean; // Kontrola czy pokazywać błędy walidacji
}

const ActionFields: React.FC<ActionFieldsProps> = ({
  action,
  index,
  onUpdate,
  onRemove,
  allOutputs,
  allOutputGroups,
  allCovers,
  allAreas,
  actionTypeOptions,
  actionOutputOptions,
  actionCoverOptions,
  showValidation = false,
}) => {
  const { t } = useTranslation();
  const actionType = action.action || 'output';

  const validationError = showValidation ? validateAction(action, t) : null;

  return (
    <div className="border border-base-300 rounded-lg p-4 mb-4">
      <div className="flex justify-between items-center mb-3">
        <h4 className="font-medium">{t('event_form.action')} {index + 1}</h4>
        <button
          onClick={onRemove}
          className="btn btn-ghost btn-xs text-error"
        >
          <FaTrash />
        </button>
      </div>

      {validationError && (
        <div className="alert alert-error mb-3">
          <span className="text-sm">{validationError}</span>
        </div>
      )}

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.action_type')}</span>
        </label>
        <Select
          value={actionType}
          onValueChange={(value) => onUpdate('action', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select action..." />
          </SelectTrigger>
          <SelectContent>
            {actionTypeOptions.map((opt: string) => (
              <SelectItem key={opt} value={opt}>
                {opt.split('_').map(word =>
                  word.charAt(0).toUpperCase() + word.slice(1)
                ).join(' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {(actionType === 'cover' || actionType === 'cover_over_mqtt') && (
        <>
          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.cover')}</span>
            </label>
            <Select
              value={action.pin || ''}
              onValueChange={(value) => onUpdate('pin', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('event_form.select_cover')} />
              </SelectTrigger>
              <SelectContent>
                {allCovers
                  .filter((cover: any) => cover && typeof cover === 'object' && cover.id)
                  .map((cover: any) => {
                    const id = cover.id;
                    const name = cover.name || id;
                    const label = name !== id ? `${name} - ${id}` : id;
                    return (
                      <SelectItem key={id} value={id}>
                        {label}
                      </SelectItem>
                    );
                  })}
              </SelectContent>
            </Select>
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.cover_action')}</span>
            </label>
            <Select
              value={action.action_cover || 'TOGGLE'}
              onValueChange={(value) => onUpdate('action_cover', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select action..." />
              </SelectTrigger>
              <SelectContent>
                {actionCoverOptions.map((option: string) => (
                  <SelectItem key={option} value={option}>
                    {option.split('_').map(word => 
                      word.charAt(0) + word.slice(1).toLowerCase()
                    ).join(' ')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </>
      )}

      {actionType === 'output' && (
        <>
          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.output')}</span>
            </label>
            <OutputSelectDropdown
              value={action.pin || ''}
              onChange={(value: string) => onUpdate('pin', value)}
              allOutputs={[
                ...allOutputs.filter((output: any) => output && typeof output === 'object' && (output.id || output.boneio_output)),
                ...allOutputGroups.filter((group: any) => group && typeof group === 'object' && group.id).map((group: any) => ({
                  ...group,
                  id: group.id,
                  name: group.name || group.id,
                  isGroup: true
                }))
              ]}
              allAreas={allAreas}
              placeholder={t('event_form.select_output')}
            />
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.action_output')}</span>
            </label>
            <Select
              value={action.action_output || 'TOGGLE'}
              onValueChange={(value) => onUpdate('action_output', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select action..." />
              </SelectTrigger>
              <SelectContent>
                {actionOutputOptions.map((option: string) => (
                  <SelectItem key={option} value={option}>
                    {option.charAt(0) + option.slice(1).toLowerCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </>
      )}

      {actionType === 'mqtt' && (
        <>
          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.mqtt_topic')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              placeholder={t('event_form.mqtt_topic_placeholder')}
              value={action.topic || ''}
              onChange={(e) => onUpdate('topic', e.target.value)}
            />
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.mqtt_message')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              placeholder={t('event_form.mqtt_message_placeholder')}
              value={action.action_mqtt_msg || ''}
              onChange={(e) => onUpdate('action_mqtt_msg', e.target.value)}
            />
          </div>
        </>
      )}

      {actionType === 'output_over_mqtt' && (
        <>
          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.boneio_id')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              placeholder={t('event_form.boneio_id_placeholder')}
              value={action.boneio_id || ''}
              onChange={(e) => onUpdate('boneio_id', sanitizeId(e.target.value))}
            />
            <label className="label">
              <span className="label-text-alt">{t('event_form.boneio_id_hint')}</span>
            </label>
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.output_id')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              placeholder={t('event_form.output_id_placeholder')}
              value={action.pin || ''}
              onChange={(e) => onUpdate('pin', e.target.value)}
            />
            <label className="label">
              <span className="label-text-alt">{t('event_form.output_id_hint')}</span>
            </label>
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.action_output')}</span>
            </label>
            <Select
              value={action.action_output || 'TOGGLE'}
              onValueChange={(value) => onUpdate('action_output', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select action..." />
              </SelectTrigger>
              <SelectContent>
                {actionOutputOptions.map((option: string) => (
                  <SelectItem key={option} value={option}>
                    {option.charAt(0) + option.slice(1).toLowerCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </>
      )}

      {actionType === 'cover_over_mqtt' && (
        <>
          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.boneio_id')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              placeholder={t('event_form.boneio_id_placeholder')}
              value={action.boneio_id || ''}
              onChange={(e) => onUpdate('boneio_id', sanitizeId(e.target.value))}
            />
            <label className="label">
              <span className="label-text-alt">{t('event_form.boneio_id_hint')}</span>
            </label>
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.cover_id')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              placeholder={t('event_form.cover_id_placeholder')}
              value={action.pin || ''}
              onChange={(e) => onUpdate('pin', e.target.value)}
            />
            <label className="label">
              <span className="label-text-alt">{t('event_form.cover_id_hint')}</span>
            </label>
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.cover_action')}</span>
            </label>
            <Select
              value={action.action_cover || 'TOGGLE'}
              onValueChange={(value) => onUpdate('action_cover', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select action..." />
              </SelectTrigger>
              <SelectContent>
                {actionCoverOptions.map((option: string) => (
                  <SelectItem key={option} value={option}>
                    {option.split('_').map(word => 
                      word.charAt(0) + word.slice(1).toLowerCase()
                    ).join(' ')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </>
      )}
    </div>
  );
};

export default ActionFields;
