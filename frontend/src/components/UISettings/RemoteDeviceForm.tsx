import React from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// Currently only mqtt is supported, future protocols are planned
const PROTOCOLS = ['mqtt'] as const;

const DEVICE_TYPES = ['boneio_black'] as const;

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
 * Fields: id, name, protocol, device_type, mqtt settings (topic_prefix, outputs, covers)
 */
const RemoteDeviceForm: React.FC<RemoteDeviceFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleMqttChange = (field: string, value: any) => {
    const mqtt = data?.mqtt || {};
    onChange({ ...data, mqtt: { ...mqtt, [field]: value } });
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

      {/* Device Type */}
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
