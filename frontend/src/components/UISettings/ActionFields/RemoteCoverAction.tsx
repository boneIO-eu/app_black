import React, { useMemo } from 'react';
import { NumericInput } from '@/components/ui/NumericInput';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import RemoteDeviceSelect from '../widgets/RemoteDeviceSelect';
import type { RemoteCoverActionProps } from './types';
import { TILT_ACTIONS, coverSupportsTilt, filterCoverActionsByTilt, formatActionLabel } from './helpers';

/**
 * Remote Cover Action component - handles ESPHome and MQTT remote covers.
 * Filters tilt-related actions based on whether the selected cover supports tilt.
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


  /** Filter action options: show tilt actions only when cover supports tilt. */
  const filteredCoverOptions = useMemo(
    () => filterCoverActionsByTilt(actionCoverOptions, selectedCover),
    [actionCoverOptions, selectedCover],
  );

  return (
    <>
      {/* Remote Device Selection */}
      <RemoteDeviceSelect
        value={action.remote_device || ''}
        onChange={(value) => onUpdate('remote_device', value)}
        allRemoteDevices={allRemoteDevices}
        label={t('event_form.remote_device')}
        placeholder={t('event_form.select_remote_device')}
      />

      {/* Cover Selection */}
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.cover_id')}</span>
        </label>
        <Select
          value={action.cover_id || ''}
          onValueChange={(value) => {
            onUpdate('cover_id', value);
            // When changing cover, reset tilt action if new cover doesn't support it
            const newCover = covers.find((c: any) => c.id === value);
            if (!coverSupportsTilt(newCover) && TILT_ACTIONS.includes(action.action_cover)) {
              onUpdate('action_cover', 'TOGGLE');
              onUpdate('data', undefined);
            }
          }}
          disabled={!action.remote_device}
        >
          <SelectTrigger className="w-full input input-bordered h-auto min-h-12 py-2">
            <SelectValue placeholder={t('event_form.select_cover_id')}>
              {selectedCover ? (
                <div className="flex flex-col items-start">
                  <span className="font-medium">
                    {'supports_tilt' in selectedCover && (
                      <span className={`badge badge-xs ${(selectedCover as any).supports_tilt ? 'badge-accent' : 'badge-info'} mr-1`}>
                        {(selectedCover as any).supports_tilt ? t('covers.type_venetian') : t('covers.type_time_based')}
                      </span>
                    )}
                    {selectedCover.name || selectedCover.id}
                  </span>
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
                  <span className="font-medium">
                    {'supports_tilt' in cover && (
                      <span className={`badge badge-xs ${cover.supports_tilt ? 'badge-accent' : 'badge-info'} mr-1`}>
                        {cover.supports_tilt ? t('covers.type_venetian') : t('covers.type_time_based')}
                      </span>
                    )}
                    {cover.name || cover.id}
                  </span>
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
          onValueChange={(value) => {
            onUpdate('action_cover', value);
            // Clear tilt_position data when switching away from TILT
            if (value !== 'TILT') {
              const currentData = action.data || {};
              if (currentData.tilt_position !== undefined) {
                const { tilt_position, ...rest } = currentData;
                onUpdate('data', Object.keys(rest).length > 0 ? rest : undefined);
              }
            }
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select action..." />
          </SelectTrigger>
          <SelectContent>
            {filteredCoverOptions.map((option: string) => (
              <SelectItem key={option} value={option}>
                {formatActionLabel(option, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Tilt position input — required for TILT action */}
      {action.action_cover === 'TILT' && (
        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('event_form.tilt_position')} <span className="text-error">*</span></span>
          </label>
          <NumericInput
            className={(action.data?.tilt_position === undefined || action.data?.tilt_position === null || action.data?.tilt_position === '') ? 'input-error' : ''}
            min={0}
            max={100}
            placeholder="50"
            value={action.data?.tilt_position ?? ''}
            onChange={(v) => {
              const data = { ...(action.data || {}), tilt_position: v === '' ? undefined : v };
              onUpdate('data', data);
            }}
          />
          <label className="label">
            <span className="label-text-alt">{t('event_form.tilt_position_hint')}</span>
          </label>
        </div>
      )}

      {action.action_cover === 'SMART_TOGGLE' && (
        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('event_form.always_open_till')}</span>
          </label>
          <NumericInput
            min={0}
            max={100}
            placeholder="50"
            value={action.data?.always_open_till ?? 50}
            onChange={(v) => {
              const data = { ...(action.data || {}), always_open_till: v === '' ? 50 : v };
              onUpdate('data', data);
            }}
          />
          <label className="label">
            <span className="label-text-alt">{t('event_form.always_open_till_hint')}</span>
          </label>
        </div>
      )}

      {/* Restore Tilt — only for covers with tilt support */}
      {selectedCover && coverSupportsTilt(selectedCover) && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="checkbox checkbox-sm"
              checked={action.restore_tilt || false}
              onChange={(e) => onUpdate('restore_tilt', e.target.checked || undefined)}
            />
            <div>
              <span className="label-text font-medium">{t('event_form.restore_tilt')}</span>
              <p className="text-sm text-base-content/70 mt-1">
                {t('event_form.restore_tilt_hint')}
              </p>
            </div>
          </label>
        </div>
      )}
    </>
  );
};

export default RemoteCoverAction;
