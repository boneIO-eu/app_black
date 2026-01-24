import React from 'react';
import { FaTrash } from 'react-icons/fa';
import { sanitizeId } from './helpers/idValidation';
import { normalizeCovers } from './helpers/coverUtils';
import OutputSelectDropdown from './OutputSelectDropdown';
import { useTranslation } from '@/hooks/useTranslation';
import type { CoverEntity, OutputEntity } from '@/types/config';
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
  protocol?: string;
  mqtt?: {
    outputs?: { id: string; name?: string }[];
    covers?: { id: string; name?: string }[];
  };
  esphome_api?: {
    host?: string;
    switches?: { id: string; name?: string; key?: number }[];
    lights?: { id: string; name?: string; key?: number; supports_brightness?: boolean; supports_color_temp?: boolean; supports_rgb?: boolean; min_mireds?: number; max_mireds?: number }[];
    covers?: { id: string; name?: string; key?: number; supports_position?: boolean; supports_tilt?: boolean }[];
  };
}

interface ActionFieldsProps {
  action: any;
  index: number;
  onUpdate: (field: string, value: any) => void;
  onRemove: () => void;
  allOutputs: OutputEntity[];
  allOutputGroups: any[];
  allCovers: CoverEntity[];
  allAreas: Area[];
  allRemoteDevices?: RemoteDevice[];
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
  showValidation?: boolean; // Kontrola czy pokazywać błędy walidacji
  /** Saved (committed) outputs for comparison - items not in saved are disabled */
  savedOutputs?: OutputEntity[];
  /** Saved (committed) output groups for comparison */
  savedOutputGroups?: any[];
  /** Saved (committed) covers for comparison */
  savedCovers?: CoverEntity[];
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
    if (!savedCovers) return true;
    const normalized = normalizeCovers(savedCovers);
    return normalized.some(c => c.id === coverId);
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
                {normalizeCovers(allCovers).map((cover) => {
                    const name = cover.name || cover.id;
                    const label = name !== cover.id ? `${name} (${cover.id})` : cover.id;
                    const isSaved = isCoverSaved(cover.id);
                    return (
                      <SelectItem 
                        key={cover.id} 
                        value={cover.id}
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
                // Clear output_id and brightness/transition when device changes
                onUpdate('output_id', '');
                onUpdate('brightness', undefined);
                onUpdate('transition', undefined);
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('event_form.select_remote_device')} />
              </SelectTrigger>
              <SelectContent>
                {allRemoteDevices.map((device) => (
                  <SelectItem key={device.id} value={device.id}>
                    <div className="flex flex-col">
                      <span>{device.name || device.id}</span>
                      <span className="text-xs opacity-60">
                        {device.protocol === 'esphome_api' ? 'ESPHome' : 'MQTT'}
                      </span>
                    </div>
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
              <SelectTrigger className="w-full input input-bordered h-auto min-h-12 py-2">
                <SelectValue placeholder={t('event_form.select_output_id')}>
                  {(() => {
                    const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
                    // For ESPHome: combine switches and lights
                    // For MQTT: use outputs
                    const isEspHome = selectedDevice?.protocol === 'esphome_api';
                    let allEntities: any[] = [];
                    if (isEspHome) {
                      const switches = (selectedDevice?.esphome_api?.switches || []).map((s: any) => ({ ...s, _type: 'switch' }));
                      const lights = (selectedDevice?.esphome_api?.lights || []).map((l: any) => ({ ...l, _type: 'light' }));
                      allEntities = [...switches, ...lights];
                    } else {
                      allEntities = selectedDevice?.mqtt?.outputs || [];
                    }
                    const selectedEntity = allEntities.find((o: any) => o.id === action.output_id);
                    if (selectedEntity) {
                      return (
                        <div className="flex flex-col items-start">
                          <span className="font-medium">{selectedEntity.name || selectedEntity.id}</span>
                          <span className="text-xs opacity-60">
                            {selectedEntity._type === 'light' ? '💡 Light' : selectedEntity._type === 'switch' ? '🔌 Switch' : `ID: ${selectedEntity.id}`}
                          </span>
                        </div>
                      );
                    }
                    return <span className="opacity-50">{t('event_form.select_output_id')}</span>;
                  })()}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {(() => {
                  const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
                  const isEspHome = selectedDevice?.protocol === 'esphome_api';
                  let allEntities: any[] = [];
                  if (isEspHome) {
                    const switches = (selectedDevice?.esphome_api?.switches || []).map((s: any) => ({ ...s, _type: 'switch' }));
                    const lights = (selectedDevice?.esphome_api?.lights || []).map((l: any) => ({ ...l, _type: 'light' }));
                    allEntities = [...switches, ...lights];
                  } else {
                    allEntities = selectedDevice?.mqtt?.outputs || [];
                  }
                  return allEntities.map((entity: any) => (
                    <SelectItem key={entity.id} value={entity.id}>
                      <div className="flex flex-col">
                        <span className="font-medium">{entity.name || entity.id}</span>
                        <span className="text-xs opacity-60">
                          {entity._type === 'light' ? (
                            <>💡 Light {entity.supports_brightness && '• Dimmable'}</>
                          ) : entity._type === 'switch' ? (
                            <>🔌 Switch</>
                          ) : (
                            <>ID: {entity.id}</>
                          )}
                        </span>
                      </div>
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
                    {option.split('_').map(word => word.charAt(0) + word.slice(1).toLowerCase()).join(' ')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Light controls - shown for ESPHome lights */}
          {(() => {
            const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
            const isEspHome = selectedDevice?.protocol === 'esphome_api';
            const lights = selectedDevice?.esphome_api?.lights || [];
            const selectedLight = lights.find((l: any) => l.id === action.output_id);
            const isLight = isEspHome && selectedLight;
            
            if (!isLight) return null;
            
            // Show brightness for ON, TOGGLE, SET_BRIGHTNESS if light supports it
            const showBrightness = selectedLight?.supports_brightness && 
              ['ON', 'TOGGLE', 'SET_BRIGHTNESS'].includes(action.action_output || '');
            
            // Show color temp for ON, TOGGLE if light supports it
            const showColorTemp = selectedLight?.supports_color_temp && 
              ['ON', 'TOGGLE'].includes(action.action_output || '');
            
            return (
              <>
                {showBrightness && (
                  <div className="form-control mb-3">
                    <label className="label cursor-pointer justify-start gap-2 pb-1">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm checkbox-primary"
                        checked={action.brightness !== undefined}
                        onChange={(e) => onUpdate('brightness', e.target.checked ? 255 : undefined)}
                      />
                      <span className="label-text font-medium">{t('event_form.brightness') || 'Brightness'}</span>
                      {action.brightness !== undefined && (
                        <span className="label-text-alt ml-auto">{Math.round((action.brightness / 255) * 100)}%</span>
                      )}
                    </label>
                    {action.brightness !== undefined && (
                      <div className="pl-7">
                        <input
                          type="range"
                          min="1"
                          max="255"
                          value={action.brightness}
                          onChange={(e) => onUpdate('brightness', parseInt(e.target.value))}
                          className="range range-primary range-sm w-full"
                        />
                        <div className="w-full flex justify-between text-xs opacity-50">
                          <span>1%</span>
                          <span>50%</span>
                          <span>100%</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                
                {showColorTemp && (
                  <div className="form-control mb-3">
                    <label className="label cursor-pointer justify-start gap-2 pb-1">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm checkbox-warning"
                        checked={action.color_temp !== undefined}
                        onChange={(e) => onUpdate('color_temp', e.target.checked ? (selectedLight?.min_mireds || 153) : undefined)}
                      />
                      <span className="label-text font-medium">{t('event_form.color_temp') || 'Color Temperature'}</span>
                      {action.color_temp !== undefined && (
                        <span className="label-text-alt ml-auto">{action.color_temp} mireds</span>
                      )}
                    </label>
                    {action.color_temp !== undefined && (
                      <div className="pl-7">
                        <input
                          type="range"
                          min={selectedLight?.min_mireds || 153}
                          max={selectedLight?.max_mireds || 500}
                          value={action.color_temp}
                          onChange={(e) => onUpdate('color_temp', parseInt(e.target.value))}
                          className="range range-warning range-sm w-full"
                        />
                        <div className="w-full flex justify-between text-xs opacity-50">
                          <span>{t('event_form.color_temp_cool') || 'Cool'}</span>
                          <span>{t('event_form.color_temp_warm') || 'Warm'}</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                
                <div className="form-control mb-3">
                  <label className="label">
                    <span className="label-text font-medium">{t('event_form.transition') || 'Transition (seconds)'}</span>
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="60"
                    step="0.1"
                    className="input input-bordered w-full"
                    value={action.transition ?? ''}
                    onChange={(e) => {
                      const val = e.target.value;
                      // Set to undefined if empty or 0 (default value)
                      onUpdate('transition', val === '' || parseFloat(val) === 0 ? undefined : parseFloat(val));
                    }}
                    placeholder="0"
                  />
                </div>
              </>
            );
          })()}
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
                    <div className="flex flex-col">
                      <span>{device.name || device.id}</span>
                      <span className="text-xs opacity-60">
                        {device.protocol === 'esphome_api' ? 'ESPHome' : 'MQTT'}
                      </span>
                    </div>
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
              <SelectTrigger className="w-full input input-bordered h-auto min-h-12 py-2">
                <SelectValue placeholder={t('event_form.select_cover_id')}>
                  {(() => {
                    const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
                    // For ESPHome: use esphome_api.covers, for MQTT: use mqtt.covers
                    const isEspHome = selectedDevice?.protocol === 'esphome_api';
                    const covers = isEspHome 
                      ? (selectedDevice?.esphome_api?.covers || [])
                      : (selectedDevice?.mqtt?.covers || []);
                    const selectedCover = covers.find((c: any) => c.id === action.cover_id);
                    if (selectedCover) {
                      return (
                        <div className="flex flex-col items-start">
                          <span className="font-medium">{selectedCover.name || selectedCover.id}</span>
                          <span className="text-xs opacity-60">ID: {selectedCover.id}</span>
                        </div>
                      );
                    }
                    return <span className="opacity-50">{t('event_form.select_cover_id')}</span>;
                  })()}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {(() => {
                  const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
                  const isEspHome = selectedDevice?.protocol === 'esphome_api';
                  const covers = isEspHome 
                    ? (selectedDevice?.esphome_api?.covers || [])
                    : (selectedDevice?.mqtt?.covers || []);
                  return covers.map((cover: any) => (
                    <SelectItem key={cover.id} value={cover.id}>
                      <div className="flex flex-col">
                        <span className="font-medium">{cover.name || cover.id}</span>
                        <span className="text-xs opacity-60">ID: {cover.id}</span>
                      </div>
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

      {/* Duration thresholds - only for long press actions */}
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.duration_thresholds')}</span>
          <span className="label-text-alt">{t('event_form.duration_thresholds_hint')}</span>
        </label>
        <div className="flex gap-2">
          <div className="flex-1">
            <input
              type="number"
              placeholder={t('event_form.min_duration_ms')}
              className="input input-bordered w-full"
              value={action.min_duration || ''}
              onChange={(e) => onUpdate('min_duration', e.target.value ? parseInt(e.target.value) : undefined)}
              min="0"
            />
          </div>
          <div className="flex-1">
            <input
              type="number"
              placeholder={t('event_form.max_duration_ms')}
              className="input input-bordered w-full"
              value={action.max_duration || ''}
              onChange={(e) => onUpdate('max_duration', e.target.value ? parseInt(e.target.value) : undefined)}
              min="0"
            />
          </div>
        </div>
      </div>

    </div>
  );
};

export default ActionFields;
