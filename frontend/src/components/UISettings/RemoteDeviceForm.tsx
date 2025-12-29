import React, { useState } from 'react';
import { FaPlus, FaTrash, FaSync } from 'react-icons/fa';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { 
  ESPHomeSwitchEntity, 
  ESPHomeLightEntity, 
  ESPHomeCoverEntity 
} from '@/types/config';

// Supported protocols
const PROTOCOLS = ['mqtt', 'esphome_api'] as const;

const DEVICE_TYPES = ['boneio_black', 'esphome', 'generic'] as const;

interface OutputItem {
  id: string;
  name?: string;
}

interface CoverItem {
  id: string;
  name?: string;
}

interface RemoteDeviceFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Remote Device item editing.
 * Fields: id, name, protocol, device_type, mqtt settings (outputs, covers)
 */
const RemoteDeviceForm: React.FC<RemoteDeviceFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);
  
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleMqttChange = (field: string, value: any) => {
    const mqtt = data?.mqtt || {};
    onChange({ ...data, mqtt: { ...mqtt, [field]: value } });
  };

  const handleEsphomeApiChange = (field: string, value: any) => {
    const esphome_api = data?.esphome_api || {};
    onChange({ ...data, esphome_api: { ...esphome_api, [field]: value } });
  };

  /**
   * Discover ESPHome entities via API
   */
  const discoverEsphomeEntities = async () => {
    const esphomeConfig = data?.esphome_api || {};
    if (!esphomeConfig.host) {
      setDiscoveryError(t('remote_devices.esphome_host_required') || 'Host is required');
      return;
    }

    setIsDiscovering(true);
    setDiscoveryError(null);

    try {
      const response = await fetch('/api/remote-devices/discover-esphome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host: esphomeConfig.host,
          port: esphomeConfig.port || 6053,
          password: esphomeConfig.password || '',
          encryption_key: esphomeConfig.encryption_key || '',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Discovery failed');
      }

      const result = await response.json();
      
      // Update esphome_api config with discovered entities
      onChange({
        ...data,
        esphome_api: {
          ...esphomeConfig,
          switches: result.switches || [],
          lights: result.lights || [],
          covers: result.covers || [],
        },
      });
    } catch (error) {
      setDiscoveryError(error instanceof Error ? error.message : 'Discovery failed');
    } finally {
      setIsDiscovering(false);
    }
  };

  // Output management
  const outputs: OutputItem[] = data?.mqtt?.outputs || [];
  
  const addOutput = () => {
    const newOutputs = [...outputs, { id: '', name: '' }];
    handleMqttChange('outputs', newOutputs);
  };

  const removeOutput = (index: number) => {
    const newOutputs = outputs.filter((_, i) => i !== index);
    handleMqttChange('outputs', newOutputs);
  };

  const updateOutput = (index: number, field: string, value: string) => {
    const newOutputs = [...outputs];
    newOutputs[index] = { ...newOutputs[index], [field]: value };
    handleMqttChange('outputs', newOutputs);
  };

  // Cover management
  const covers: CoverItem[] = data?.mqtt?.covers || [];
  
  const addCover = () => {
    const newCovers = [...covers, { id: '', name: '' }];
    handleMqttChange('covers', newCovers);
  };

  const removeCover = (index: number) => {
    const newCovers = covers.filter((_, i) => i !== index);
    handleMqttChange('covers', newCovers);
  };

  const updateCover = (index: number, field: string, value: string) => {
    const newCovers = [...covers];
    newCovers[index] = { ...newCovers[index], [field]: value };
    handleMqttChange('covers', newCovers);
  };

  return (
    <div className="space-y-4">
      {/* ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('remote_devices.device_id')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.id || ''}
          onChange={(e) => handleChange('id', sanitizeId(e.target.value))}
          placeholder="salon_boneio"
          required
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('remote_devices.id_hint')}</span>
        </label>
      </div>

      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('remote_devices.device_name')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder="Salon boneIO"
          required
        />
      </div>

      {/* Protocol */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('remote_devices.protocol')} <span className="text-error">*</span></span>
        </label>
        <Select
          value={data?.protocol || 'mqtt'}
          onValueChange={(value) => handleChange('protocol', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('remote_devices.select_protocol')} />
          </SelectTrigger>
          <SelectContent>
            {PROTOCOLS.map(protocol => (
              <SelectItem key={protocol} value={protocol}>
                {protocol.toUpperCase()}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('remote_devices.protocol_hint')}</span>
        </label>
      </div>

      {/* Device Type - hidden for ESPHome API protocol */}
      {data?.protocol !== 'esphome_api' && (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('remote_devices.device_type')}</span>
          </label>
          <Select
            value={data?.device_type || 'boneio_black'}
            onValueChange={(value) => handleChange('device_type', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('remote_devices.select_device_type')} />
            </SelectTrigger>
            <SelectContent>
              {DEVICE_TYPES.map(type => (
                <SelectItem key={type} value={type}>
                  {type === 'boneio_black' ? 'boneIO Black' : type === 'esphome' ? 'ESPHome' : 'Generic'}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="label">
            <span className="label-text-alt text-base-content/60">{t('remote_devices.device_type_hint')}</span>
          </label>
        </div>
      )}

      {/* ESPHome API Settings - shown when protocol is esphome_api */}
      {data?.protocol === 'esphome_api' && (
        <div className="card bg-base-200 p-4 space-y-4">
          <h3 className="font-medium text-lg">{t('remote_devices.esphome_settings') || 'ESPHome API Settings'}</h3>
          
          {/* Host */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('remote_devices.esphome_host') || 'Host'} <span className="text-error">*</span></span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={data?.esphome_api?.host || ''}
              onChange={(e) => handleEsphomeApiChange('host', e.target.value)}
              placeholder="192.168.1.50"
              required
            />
          </div>

          {/* Port */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('remote_devices.esphome_port') || 'Port'}</span>
            </label>
            <input
              type="number"
              className="input input-bordered w-full"
              value={data?.esphome_api?.port || 6053}
              onChange={(e) => handleEsphomeApiChange('port', parseInt(e.target.value) || 6053)}
              placeholder="6053"
            />
          </div>

          {/* Password */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('remote_devices.esphome_password') || 'API Password'}</span>
            </label>
            <input
              type="password"
              className="input input-bordered w-full"
              value={data?.esphome_api?.password || ''}
              onChange={(e) => handleEsphomeApiChange('password', e.target.value)}
              placeholder={t('remote_devices.esphome_password_placeholder') || 'Optional'}
            />
          </div>

          {/* Encryption Key */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">{t('remote_devices.esphome_encryption_key') || 'Encryption Key'}</span>
            </label>
            <input
              type="password"
              className="input input-bordered w-full"
              value={data?.esphome_api?.encryption_key || ''}
              onChange={(e) => handleEsphomeApiChange('encryption_key', e.target.value)}
              placeholder={t('remote_devices.esphome_encryption_key_placeholder') || 'Base64 encoded (optional)'}
            />
          </div>

          {/* Discover Entities Button */}
          <div className="form-control">
            <button
              type="button"
              className={`btn btn-primary ${isDiscovering ? 'loading' : ''}`}
              onClick={discoverEsphomeEntities}
              disabled={isDiscovering || !data?.esphome_api?.host}
            >
              <FaSync className={`mr-2 ${isDiscovering ? 'animate-spin' : ''}`} />
              {isDiscovering 
                ? (t('remote_devices.discovering') || 'Discovering...') 
                : (t('remote_devices.discover_entities') || 'Discover Entities')}
            </button>
          </div>

          {/* Discovery error display */}
          {discoveryError && (
            <div className="alert alert-error">
              <span>{discoveryError}</span>
            </div>
          )}

          {/* Discovered Switches */}
          {(data?.esphome_api?.switches?.length > 0) && (
            <div className="collapse collapse-arrow bg-base-300">
              <input type="checkbox" defaultChecked />
              <div className="collapse-title font-medium">
                {t('remote_devices.esphome_switches') || 'Switches'}
                <span className="badge badge-sm ml-2">{data.esphome_api.switches.length}</span>
              </div>
              <div className="collapse-content">
                <div className="overflow-x-auto">
                  <table className="table table-xs">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>{t('common.name') || 'Name'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.esphome_api.switches.map((sw: ESPHomeSwitchEntity, idx: number) => (
                        <tr key={idx}>
                          <td className="font-mono text-xs">{sw.id}</td>
                          <td>{sw.name || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Discovered Lights */}
          {(data?.esphome_api?.lights?.length > 0) && (
            <div className="collapse collapse-arrow bg-base-300">
              <input type="checkbox" defaultChecked />
              <div className="collapse-title font-medium">
                {t('remote_devices.esphome_lights') || 'Lights'}
                <span className="badge badge-sm ml-2">{data.esphome_api.lights.length}</span>
              </div>
              <div className="collapse-content">
                <div className="overflow-x-auto">
                  <table className="table table-xs">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>{t('common.name') || 'Name'}</th>
                        <th>{t('remote_devices.capabilities') || 'Capabilities'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.esphome_api.lights.map((light: ESPHomeLightEntity, idx: number) => (
                        <tr key={idx}>
                          <td className="font-mono text-xs">{light.id}</td>
                          <td>{light.name || '-'}</td>
                          <td>
                            {light.supports_brightness && <span className="badge badge-xs badge-info mr-1">Brightness</span>}
                            {light.supports_color_temp && <span className="badge badge-xs badge-warning mr-1">Color Temp</span>}
                            {light.supports_rgb && <span className="badge badge-xs badge-success mr-1">RGB</span>}
                            {light.supports_rgbw && <span className="badge badge-xs badge-accent mr-1">RGBW</span>}
                            {!light.supports_brightness && !light.supports_color_temp && !light.supports_rgb && <span className="badge badge-xs badge-ghost">ON/OFF</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Discovered Covers */}
          {(data?.esphome_api?.covers?.length > 0) && (
            <div className="collapse collapse-arrow bg-base-300">
              <input type="checkbox" defaultChecked />
              <div className="collapse-title font-medium">
                {t('remote_devices.esphome_covers') || 'Covers'}
                <span className="badge badge-sm ml-2">{data.esphome_api.covers.length}</span>
              </div>
              <div className="collapse-content">
                <div className="overflow-x-auto">
                  <table className="table table-xs">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>{t('common.name') || 'Name'}</th>
                        <th>{t('remote_devices.capabilities') || 'Capabilities'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.esphome_api.covers.map((cover: ESPHomeCoverEntity, idx: number) => (
                        <tr key={idx}>
                          <td className="font-mono text-xs">{cover.id}</td>
                          <td>{cover.name || '-'}</td>
                          <td>
                            {cover.supports_position && <span className="badge badge-xs badge-info mr-1">Position</span>}
                            {cover.supports_tilt && <span className="badge badge-xs badge-warning mr-1">Tilt</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* MQTT Settings - shown when protocol is mqtt */}
      {(data?.protocol === 'mqtt' || !data?.protocol) && (
        <div className="card bg-base-200 p-4 space-y-4">
          <h3 className="font-medium text-lg">{t('remote_devices.mqtt_settings')}</h3>
          
          <div className="alert alert-info">
            <div className="flex-1">
              <p className="text-sm">
                {t('remote_devices.autodiscovery_info')}
              </p>
            </div>
          </div>

          {/* Outputs Section */}
          <div className="collapse collapse-arrow bg-base-300">
            <input type="checkbox" defaultChecked />
            <div className="collapse-title font-medium">
              {t('remote_devices.outputs')}
              <span className="badge badge-sm ml-2">{outputs.length}</span>
            </div>
            <div className="collapse-content">
              <p className="text-sm text-base-content/60 mb-2">{t('remote_devices.outputs_hint')}</p>
              <div className="space-y-2">
                {outputs.map((output, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <input
                      type="text"
                      className="input input-bordered input-sm flex-1"
                      value={output.id}
                      onChange={(e) => updateOutput(index, 'id', e.target.value)}
                      placeholder="relay_1"
                    />
                    <input
                      type="text"
                      className="input input-bordered input-sm flex-1"
                      value={output.name || ''}
                      onChange={(e) => updateOutput(index, 'name', e.target.value)}
                      placeholder={t('remote_devices.output_name_placeholder')}
                    />
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-error"
                      onClick={() => removeOutput(index)}
                    >
                      <FaTrash />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={addOutput}
                >
                  <FaPlus className="mr-1" /> {t('remote_devices.add_output')}
                </button>
              </div>
            </div>
          </div>

          {/* Covers Section */}
          <div className="collapse collapse-arrow bg-base-300">
            <input type="checkbox" defaultChecked />
            <div className="collapse-title font-medium">
              {t('remote_devices.covers')}
              <span className="badge badge-sm ml-2">{covers.length}</span>
            </div>
            <div className="collapse-content">
              <p className="text-sm text-base-content/60 mb-2">{t('remote_devices.covers_hint')}</p>
              <div className="space-y-2">
                {covers.map((cover, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <input
                      type="text"
                      className="input input-bordered input-sm flex-1"
                      value={cover.id}
                      onChange={(e) => updateCover(index, 'id', e.target.value)}
                      placeholder="cover_living_room"
                    />
                    <input
                      type="text"
                      className="input input-bordered input-sm flex-1"
                      value={cover.name || ''}
                      onChange={(e) => updateCover(index, 'name', e.target.value)}
                      placeholder={t('remote_devices.cover_name_placeholder')}
                    />
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-error"
                      onClick={() => removeCover(index)}
                    >
                      <FaTrash />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={addCover}
                >
                  <FaPlus className="mr-1" /> {t('remote_devices.add_cover')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RemoteDeviceForm;
