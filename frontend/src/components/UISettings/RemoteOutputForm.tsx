/**
 * RemoteOutputForm — dedicated form for editing remote output entries.
 *
 * Lets the user:
 *   1. Pick a remote device (only devices with switches or lights)
 *   2. Pick an output (switch/light) from that device
 *   3. Set output_type (switch, light, valve)
 *   4. Set on_disconnect policy (ignore, turn_off)
 *   5. Optionally set name, id, area, show_in_ha
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import AreaSelect from './widgets/AreaSelect';
import { MqttRemoteOutputFields } from './modules/remote_mqtt';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type {
  AreaEntity,
  RemoteDeviceEntity,
} from '@/types/config';

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */
interface RemoteOutputFormProps {
  data: any;
  onChange: (data: any) => void;
  isNew: boolean;
  schema?: any;
  allAreas?: AreaEntity[];
  allRemoteDevices?: RemoteDeviceEntity[];
  existingItems?: any[];
  editingIndex?: number | null;
  onValidationChange?: (hasErrors: boolean) => void;
  attemptedSubmit?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
const RemoteOutputForm: React.FC<RemoteOutputFormProps> = ({
  data,
  onChange,
  allAreas = [],
  allRemoteDevices = [],
  onValidationChange,
  attemptedSubmit = false,
}) => {
  const { t } = useTranslation();

  /* ---------- field helpers ---------- */
  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  /* ---------- validation ---------- */
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    if (!data.device_id) errors.push(t('validation.required') + ': ' + t('remote_devices.device'));
    if (!data.output_id) errors.push(t('validation.required') + ': ' + t('remote_outputs.output_entity'));
    return errors;
  };

  const validationErrors = getValidationErrors();
  React.useEffect(() => {
    onValidationChange?.(validationErrors.length > 0);
  }, [validationErrors.length, onValidationChange]);

  /* ---------- device output lists ---------- */
  const selectedDevice = allRemoteDevices.find(d => d.id === data.device_id);
  const esphomeApi = (selectedDevice as any)?.esphome_api || selectedDevice;
  const availableSwitches: Array<{ id: string; name?: string }> =
    esphomeApi?.switches || [];
  const availableLights: Array<{ id: string; name?: string; supports_brightness?: boolean }> =
    esphomeApi?.lights || [];
  const allAvailableOutputs = [
    ...availableSwitches.map(s => ({ ...s, _type: 'switch' as const })),
    ...availableLights.map(l => ({ ...l, _type: 'light' as const })),
  ];

  /* ---------- selected output capabilities ---------- */
  const selectedOutput = allAvailableOutputs.find(o => o.id === data.output_id);
  const isLightEntity = selectedOutput?._type === 'light';
  const selectedLight = isLightEntity
    ? availableLights.find(l => l.id === data.output_id)
    : null;
  const supportsBrightness = !!(selectedLight as any)?.supports_brightness;
  // Lights with brightness cannot be degraded to plain switch
  const outputTypeLocked = isLightEntity && supportsBrightness;

  /* ---------- devices with outputs ---------- */
  const devicesWithOutputs = allRemoteDevices.filter((device) => {
    const api = (device as any)?.esphome_api || device;
    const sw = api?.switches || [];
    const li = api?.lights || [];
    return sw.length > 0 || li.length > 0;
  });

  return (
    <div className="space-y-4">
      {/* Validation errors */}
      {attemptedSubmit && validationErrors.length > 0 && (
        <div className="alert alert-error sticky top-0 z-10">
          <ul className="list-disc list-inside">
            {validationErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Display Name */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('outputs.display_name')}</span>
          </label>
          <input
            type="text"
            className="input w-full"
            placeholder={t('remote_outputs.name_placeholder')}
            value={data.name || ''}
            onChange={(e) => updateField('name', e.target.value)}
          />
          <label className="label">
            <span className="label-text-alt">{t('common.optional')}</span>
          </label>
        </div>

        {/* Custom Output ID */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('remote_outputs.custom_output_id')}</span>
          </label>
          <input
            type="text"
            className="input w-full"
            placeholder={t('remote_outputs.custom_output_id_placeholder')}
            value={data.id || ''}
            onChange={(e) => updateField('id', e.target.value)}
          />
          <label className="label">
            <span className="label-text-alt">{t('remote_outputs.custom_output_id_hint')}</span>
          </label>
        </div>

        {/* Remote Device (device_id) — only devices with switches/lights */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('remote_devices.device')}</span>
          </label>
          <Select
            value={data.device_id || '_none_'}
            onValueChange={(v) => {
              const deviceId = v === '_none_' ? '' : v;
              const device = allRemoteDevices.find(d => d.id === deviceId);
              // Auto-set remote_source from device protocol
              const protocol = (device as any)?.protocol || 'esphome_api';
              onChange({ ...data, device_id: deviceId, output_id: '', remote_source: protocol });
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('remote_devices.select_device')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_none_">{t('remote_devices.select_device')}</SelectItem>
              {devicesWithOutputs.map((device) => {
                const protocolLabel =
                  (device as any).protocol === 'esphome_api' ? 'ESPHome API' :
                  (device as any).protocol === 'wled' ? 'WLED' :
                  (device as any).protocol === 'mqtt' ? 'MQTT' :
                  (device as any).protocol || '';
                return (
                  <SelectItem key={device.id} value={device.id}>
                    {device.name || device.id}{protocolLabel ? ` (${protocolLabel})` : ''}
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
          {attemptedSubmit && !data.device_id && (
            <label className="label">
              <span className="label-text-alt text-error">{t('validation.required')}</span>
            </label>
          )}
        </div>

        {/* Output Entity — generic-MQTT branch shows command topic + template
            from the remote_mqtt module; everything else keeps the standard
            output_id dropdown for ESPHome / WLED devices. */}
        {data.remote_source === 'mqtt' ? (
          <MqttRemoteOutputFields
            data={data}
            onUpdate={(patch) => onChange({ ...data, ...patch, output_id: patch.topic ?? data.output_id ?? data.topic })}
            attemptedSubmit={attemptedSubmit}
          />
        ) : (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('remote_outputs.output_entity')}</span>
          </label>
          <Select
            value={data.output_id || '_none_'}
            onValueChange={(v) => {
              const outputId = v === '_none_' ? '' : v;
              // Auto-detect output type from source
              const found = allAvailableOutputs.find(o => o.id === outputId);
              const autoType = found?._type === 'light' ? 'light' : data.output_type || 'switch';
              onChange({ ...data, output_id: outputId, output_type: autoType });
            }}
            disabled={!data.device_id}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={
                data.device_id
                  ? t('remote_outputs.select_output')
                  : t('remote_devices.select_device')
              } />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_none_">{t('remote_outputs.select_output')}</SelectItem>
              {availableSwitches.length > 0 && (
                <>
                  <SelectItem value="_header_switches" disabled>
                    ⚡ {t('remote_outputs.switches_header')}
                  </SelectItem>
                  {availableSwitches.map((sw) => (
                    <SelectItem key={`sw_${sw.id}`} value={sw.id}>
                      🔌 {sw.name ? `${sw.name} (${sw.id})` : sw.id}
                    </SelectItem>
                  ))}
                </>
              )}
              {availableLights.length > 0 && (
                <>
                  <SelectItem value="_header_lights" disabled>
                    💡 {t('remote_outputs.lights_header')}
                  </SelectItem>
                  {availableLights.map((li) => (
                    <SelectItem key={`li_${li.id}`} value={li.id}>
                      💡 {li.name ? `${li.name} (${li.id})` : li.id}
                    </SelectItem>
                  ))}
                </>
              )}
            </SelectContent>
          </Select>
          {attemptedSubmit && !data.output_id && (
            <label className="label">
              <span className="label-text-alt text-error">{t('validation.required')}</span>
            </label>
          )}
        </div>
        )}

        {/* Output Type */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('remote_outputs.output_type')}</span>
          </label>
          <Select
            value={data.output_type || 'switch'}
            onValueChange={(v) => updateField('output_type', v)}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="switch" disabled={outputTypeLocked}>{t('outputs.categories.switches')}</SelectItem>
              <SelectItem value="light">{t('outputs.categories.lights')}</SelectItem>
              <SelectItem value="valve" disabled={outputTypeLocked}>{t('outputs.categories.valves')}</SelectItem>
            </SelectContent>
          </Select>
          <label className="label">
            <span className="label-text-alt">
              {outputTypeLocked
                ? t('remote_outputs.output_type_locked_hint')
                : t('remote_outputs.output_type_hint')}
            </span>
          </label>
        </div>

        {/* On Disconnect */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('remote_outputs.on_disconnect')}</span>
          </label>
          <Select
            value={data.on_disconnect || 'ignore'}
            onValueChange={(v) => updateField('on_disconnect', v)}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ignore">{t('remote_outputs.on_disconnect_ignore')}</SelectItem>
              <SelectItem value="turn_off">{t('remote_outputs.on_disconnect_turn_off')}</SelectItem>
            </SelectContent>
          </Select>
          <label className="label">
            <span className="label-text-alt">{t('remote_outputs.on_disconnect_hint')}</span>
          </label>
        </div>

        {/* Area */}
        <AreaSelect
          value={data.area}
          onChange={(v) => updateField('area', v)}
          areas={allAreas}
        />
      </div>

      {/* ---- Options ---- */}
      <div className="divider">{t('settings.options')}</div>

      <div className="grid grid-cols-1 gap-4">
        {/* Forward to HA — default OFF */}
        <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
          <legend className="fieldset-legend">{t('inputs.forward_to_ha')}</legend>
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle toggle-primary"
              checked={data.show_in_ha === true}
              onChange={(e) => updateField('show_in_ha', e.target.checked)}
            />
            <span className="label-text wrap-break-word">{t('remote_outputs.forward_to_ha_hint')}</span>
          </label>
        </fieldset>
      </div>
    </div>
  );
};

export default RemoteOutputForm;
