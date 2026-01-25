import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { RemoteCoverActionProps } from './types';

/**
 * Remote Cover Action component - handles ESPHome and MQTT remote covers.
 */
const RemoteCoverAction: React.FC<RemoteCoverActionProps> = ({
  action,
  onUpdate,
  t,
  allRemoteDevices,
  actionCoverOptions,
}) => {
  const selectedDevice = allRemoteDevices.find(d => d.id === action.remote_device);
  const isEspHome = selectedDevice?.protocol === 'esphome_api';
  const covers = isEspHome 
    ? (selectedDevice?.esphome_api?.covers || [])
    : (selectedDevice?.mqtt?.covers || []);
  const selectedCover = covers.find((c: any) => c.id === action.cover_id);

  return (
    <>
      {/* Remote Device Selection */}
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.remote_device')}</span>
        </label>
        <Select
          value={action.remote_device || ''}
          onValueChange={(value) => {
            onUpdate('remote_device', value);
            onUpdate('cover_id', '');
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('event_form.select_remote_device')} />
          </SelectTrigger>
          <SelectContent>
            {allRemoteDevices.filter(device => device.id).map((device) => (
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

      {/* Cover Selection */}
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
              {selectedCover ? (
                <div className="flex flex-col items-start">
                  <span className="font-medium">{selectedCover.name || selectedCover.id}</span>
                  <span className="text-xs opacity-60">ID: {selectedCover.id}</span>
                </div>
              ) : (
                <span className="opacity-50">{t('event_form.select_cover_id')}</span>
              )}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {covers.map((cover: any) => (
              <SelectItem key={cover.id} value={cover.id}>
                <div className="flex flex-col">
                  <span className="font-medium">{cover.name || cover.id}</span>
                  <span className="text-xs opacity-60">ID: {cover.id}</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!action.remote_device && (
          <label className="label">
            <span className="label-text-alt text-warning">{t('event_form.select_device_first')}</span>
          </label>
        )}
      </div>

      {/* Cover Action Selection */}
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
  );
};

export default RemoteCoverAction;
