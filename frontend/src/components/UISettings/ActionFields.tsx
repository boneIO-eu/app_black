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
    if (!action.boneio_output) return t('event_form.validation_output_required');
  }
  
  if (actionType === 'cover' || actionType === 'cover_over_mqtt') {
    if (!action.boneio_cover) return t('event_form.validation_cover_required');
  }
  
  if (actionType === 'mqtt') {
    if (!action.topic) return t('event_form.validation_topic_required');
  }
  
  if (actionType === 'output_over_mqtt' || actionType === 'cover_over_mqtt') {
    if (!action.boneio_id) return t('event_form.validation_boneio_id_required');
  }
  
  if (actionType === 'remote_output') {
    if (!action.remote_device) return t('event_form.validation_remote_device_required');
    if (!action.output_id) return t('event_form.validation_output_id_required');
  }
  
  if (actionType === 'remote_cover') {
    if (!action.remote_device) return t('event_form.validation_remote_device_required');
    if (!action.cover_id) return t('event_form.validation_cover_id_required');
  }
  
  return null;
};

interface Area {
  id: string;
  name: string;
}

interface RemoteDevice {
  id: string;
  name?: string;
  mqtt?: {
    outputs?: { id: string; name?: string }[];
    covers?: { id: string; name?: string }[];
  };
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
  allRemoteDevices?: RemoteDevice[];
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
  showValidation?: boolean; // Kontrola czy pokazywać błędy walidacji
  /** Saved (committed) outputs for comparison - items not in saved are disabled */
  savedOutputs?: any[];
  /** Saved (committed) output groups for comparison */
  savedOutputGroups?: any[];
  /** Saved (committed) covers for comparison */
  savedCovers?: any[];
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
  allRemoteDevices = [],
  actionTypeOptions,
  actionOutputOptions,
  actionCoverOptions,
  showValidation = false,
  savedOutputs,
  savedOutputGroups,
  savedCovers,
}) => {
  const { t } = useTranslation();
  const actionType = action.action || 'output';

  const validationError = showValidation ? validateAction(action, t) : null;

  /**
   * Wrapper for onUpdate that removes deprecated 'pin' field when setting new fields
   */
  const handleUpdate = (field: string, value: any) => {
    if (field === 'boneio_output' || field === 'boneio_cover') {
      // When setting new field, also remove old 'pin' field if it exists
      if (action.pin) {
        onUpdate('pin', undefined);
      }
    }
    onUpdate(field, value);
  };

  /**
   * Check if a cover is saved (committed) by comparing with saved data.
   * Returns true if cover exists in saved data.
   */
  const isCoverSaved = (coverId: string): boolean => {
    if (!savedCovers) return true; // If no saved data provided, assume all are saved
    return savedCovers.some((c: any) => {
      const id = c.id || (c.open_relay && c.close_relay 
        ? `cover_${c.open_relay}_${c.close_relay}`.toLowerCase()
        : null);
      return id === coverId;
    });
  };

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
              value={action.boneio_cover || action.pin || ''}
              onValueChange={(value) => handleUpdate('boneio_cover', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('event_form.select_cover')} />
              </SelectTrigger>
              <SelectContent>
                {allCovers
                  .filter((cover: any) => cover && typeof cover === 'object')
                  .map((cover: any, index: number) => {
                    // Cover ID can be explicit or generated from open_relay + close_relay
                    const id = cover.id || (cover.open_relay && cover.close_relay 
                      ? `cover_${cover.open_relay}_${cover.close_relay}`.toLowerCase()
                      : `cover_${index}`);
                    const name = cover.name || id;
                    const label = name !== id ? `${name} (${id})` : id;
                    const isSaved = isCoverSaved(id);
                    return (
                      <SelectItem 
                        key={id} 
                        value={id}
                        disabled={!isSaved}
                        className={!isSaved ? 'opacity-50 cursor-not-allowed' : ''}
                      >
                        {!isSaved && <span className="badge badge-xs badge-warning mr-1">Niezapisane</span>}
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
              value={action.boneio_output || action.pin || ''}
              onChange={(value: string) => handleUpdate('boneio_output', value)}
              allOutputs={[
                ...allOutputs.filter((output: any) => output && typeof output === 'object' && output.output_type?.toLowerCase() !== 'cover' && (output.id || output.boneio_output)),
                ...allOutputGroups.filter((group: any) => group && typeof group === 'object' && group.id).map((group: any) => ({
                  ...group,
                  id: group.id,
                  name: group.name || group.id,
                  isGroup: true
                }))
              ]}
              allAreas={allAreas}
              placeholder={t('event_form.select_output')}
              savedOutputs={savedOutputs}
              savedOutputGroups={savedOutputGroups}
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
              value={action.boneio_output || action.pin || ''}
              onChange={(e) => handleUpdate('boneio_output', e.target.value)}
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
              value={action.boneio_cover || action.pin || ''}
              onChange={(e) => handleUpdate('boneio_cover', e.target.value)}
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

      {actionType === 'remote_output' && (
        <>
          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.remote_device')}</span>
            </label>
            <Select
              value={action.remote_device || ''}
              onValueChange={(value) => {
                onUpdate('remote_device', value);
                // Clear output_id when device changes
                onUpdate('output_id', '');
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('event_form.select_remote_device')} />
              </SelectTrigger>
              <SelectContent>
                {allRemoteDevices.map((device) => (
                  <SelectItem key={device.id} value={device.id}>
                    {device.name || device.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.output_id')}</span>
            </label>
            <Select
              value={action.output_id || ''}
              onValueChange={(value) => onUpdate('output_id', value)}
              disabled={!action.remote_device}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('event_form.select_output_id')} />
              </SelectTrigger>
              <SelectContent>
                {(() => {
                  const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
                  const outputs = selectedDevice?.mqtt?.outputs || [];
                  return outputs.map((output) => (
                    <SelectItem key={output.id} value={output.id}>
                      {output.name || output.id}
                    </SelectItem>
                  ));
                })()}
              </SelectContent>
            </Select>
            {!action.remote_device && (
              <label className="label">
                <span className="label-text-alt text-warning">{t('event_form.select_device_first')}</span>
              </label>
            )}
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.output_action')}</span>
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

      {actionType === 'remote_cover' && (
        <>
          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.remote_device')}</span>
            </label>
            <Select
              value={action.remote_device || ''}
              onValueChange={(value) => {
                onUpdate('remote_device', value);
                // Clear cover_id when device changes
                onUpdate('cover_id', '');
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('event_form.select_remote_device')} />
              </SelectTrigger>
              <SelectContent>
                {allRemoteDevices.map((device) => (
                  <SelectItem key={device.id} value={device.id}>
                    {device.name || device.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="form-control mb-3">
            <label className="label">
              <span className="label-text font-medium">{t('event_form.cover_id')}</span>
            </label>
            <Select
              value={action.cover_id || ''}
              onValueChange={(value) => onUpdate('cover_id', value)}
              disabled={!action.remote_device}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('event_form.select_cover_id')} />
              </SelectTrigger>
              <SelectContent>
                {(() => {
                  const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
                  const covers = selectedDevice?.mqtt?.covers || [];
                  return covers.map((cover) => (
                    <SelectItem key={cover.id} value={cover.id}>
                      {cover.name || cover.id}
                    </SelectItem>
                  ));
                })()}
              </SelectContent>
            </Select>
            {!action.remote_device && (
              <label className="label">
                <span className="label-text-alt text-warning">{t('event_form.select_device_first')}</span>
              </label>
            )}
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
