import React, { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { sanitizeId } from './helpers/idValidation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import OutputSelectDropdown from './OutputSelectDropdown';

interface VirtualEnergySensorData {
  id?: string;
  name?: string;
  output_id?: string;
  sensor_type?: 'power' | 'water';
  power_usage?: string | number;
  flow_rate?: string | number;
  area?: string;
}

interface Area {
  id: string;
  name: string;
}

interface VirtualEnergySensorFormProps {
  data: VirtualEnergySensorData;
  onChange: (data: VirtualEnergySensorData) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  allAreas?: Area[];
  allOutputs?: any[];
  existingSensors?: VirtualEnergySensorData[];
  editingIndex?: number | null;
  onValidationChange?: (hasErrors: boolean) => void;
}

const VirtualEnergySensorForm: React.FC<VirtualEnergySensorFormProps> = ({
  data,
  onChange,
  allAreas = [],
  allOutputs = [],
  existingSensors = [],
  editingIndex,
  onValidationChange
}) => {
  const { t } = useTranslation();
  
  // Use ref to store callback to avoid triggering useEffect on every render
  const onValidationChangeRef = useRef(onValidationChange);
  onValidationChangeRef.current = onValidationChange;

  // Calculate errors using useMemo
  const errors = useMemo(() => {
    const newErrors: Record<string, string> = {};
    
    // Name is required
    if (!data.name?.trim()) {
      newErrors.name = 'name_required';
    }
    
    // Output ID is required
    if (!data.output_id) {
      newErrors.output_id = 'output_id_required';
    }
    
    // Sensor type is required
    if (!data.sensor_type) {
      newErrors.sensor_type = 'sensor_type_required';
    }
    
    // Power usage required for power type
    if (data.sensor_type === 'power' && !data.power_usage) {
      newErrors.power_usage = 'power_usage_required';
    }
    
    // Flow rate required for water type
    if (data.sensor_type === 'water' && !data.flow_rate) {
      newErrors.flow_rate = 'flow_rate_required';
    }
    
    // Check for duplicate ID (same logic as backend - generate from name if not provided)
    if (data.name?.trim()) {
      const currentId = data.id || sanitizeId(data.name);
      const isDuplicate = existingSensors.some((sensor, index) => {
        // Skip the sensor being edited
        if (editingIndex !== null && editingIndex !== undefined && index === editingIndex) {
          return false;
        }
        const existingId = sensor.id || (sensor.name ? sanitizeId(sensor.name) : '');
        return existingId === currentId;
      });
      
      if (isDuplicate) {
        newErrors.id = 'duplicate_id_error';
      }
    }
    
    return newErrors;
  }, [data.name, data.id, data.output_id, data.sensor_type, data.power_usage, data.flow_rate, existingSensors, editingIndex]);

  // Notify parent about validation state changes
  useEffect(() => {
    onValidationChangeRef.current?.(Object.keys(errors).length > 0);
  }, [errors]);

  const handleChange = (field: keyof VirtualEnergySensorData, value: any) => {
    const newData = { ...data, [field]: value };
    
    // Clear power_usage when switching to water, and vice versa
    if (field === 'sensor_type') {
      if (value === 'power') {
        delete newData.flow_rate;
      } else if (value === 'water') {
        delete newData.power_usage;
      }
    }
    
    onChange(newData);
  };

  const handleIdChange = (value: string) => {
    handleChange('id', sanitizeId(value));
  };

  return (
    <div className="space-y-4">
      {/* Name (required) */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('virtual_energy_sensor.name')} *</span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full ${errors.name ? 'input-error' : ''}`}
          value={data.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder={t('virtual_energy_sensor.name_placeholder')}
        />
        {errors.name && (
          <label className="label">
            <span className="label-text-alt text-error">{t(`virtual_energy_sensor.${errors.name}`)}</span>
          </label>
        )}
        <label className="label">
          <span className="label-text-alt">{t('virtual_energy_sensor.name_hint')}</span>
        </label>
      </div>

      {/* Custom ID (optional) */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('virtual_energy_sensor.custom_id')}</span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full font-mono ${errors.id ? 'input-error' : ''}`}
          value={data.id || ''}
          onChange={(e) => handleIdChange(e.target.value)}
          placeholder={t('virtual_energy_sensor.id_placeholder')}
        />
        {errors.id && (
          <label className="label">
            <span className="label-text-alt text-error">{t(`virtual_energy_sensor.${errors.id}`)}</span>
          </label>
        )}
        <label className="label">
          <span className="label-text-alt">{t('virtual_energy_sensor.id_hint')}</span>
        </label>
        {/* Show generated ID preview when custom ID is empty and name is provided */}
        {!data.id && data.name?.trim() && (
          <label className="label pt-0">
            <span className="label-text-alt text-info">
              {t('virtual_energy_sensor.generated_id')}: <code className="font-mono bg-base-200 px-1 rounded">{sanitizeId(data.name)}</code>
            </span>
          </label>
        )}
      </div>

      {/* Output ID (required) */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('virtual_energy_sensor.output_id')} *</span>
        </label>
        {allOutputs.filter((o: any) => o && (o.id || o.boneio_output)).length > 0 ? (
          <OutputSelectDropdown
            value={data.output_id || ''}
            onChange={(value: string) => handleChange('output_id', value)}
            allOutputs={allOutputs.filter((output: any) => output && typeof output === 'object' && (output.id || output.boneio_output))}
            allAreas={allAreas}
            placeholder={t('virtual_energy_sensor.select_output')}
          />
        ) : (
          <div className="alert alert-warning text-sm">
            <span>{t('virtual_energy_sensor.no_outputs_available') || 'No outputs available. Please configure outputs first.'}</span>
          </div>
        )}
        {errors.output_id && (
          <label className="label">
            <span className="label-text-alt text-error">{t(`virtual_energy_sensor.${errors.output_id}`)}</span>
          </label>
        )}
        <label className="label">
          <span className="label-text-alt">{t('virtual_energy_sensor.output_id_hint')}</span>
        </label>
      </div>

      {/* Sensor Type (required) */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('virtual_energy_sensor.sensor_type')} *</span>
        </label>
        <Select
          value={data.sensor_type || undefined}
          onValueChange={(value) => handleChange('sensor_type', value as 'power' | 'water')}
        >
          <SelectTrigger className={`w-full ${errors.sensor_type ? 'border-error' : ''}`}>
            <SelectValue placeholder={t('virtual_energy_sensor.select_sensor_type')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem key="power" value="power">{t('virtual_energy_sensor.type_power')}</SelectItem>
            <SelectItem key="water" value="water">{t('virtual_energy_sensor.type_water')}</SelectItem>
          </SelectContent>
        </Select>
        {errors.sensor_type && (
          <label className="label">
            <span className="label-text-alt text-error">{t(`virtual_energy_sensor.${errors.sensor_type}`)}</span>
          </label>
        )}
      </div>

      {/* Power Usage (for power type) */}
      {data.sensor_type === 'power' && (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('virtual_energy_sensor.power_usage')} *</span>
          </label>
          <input
            type="text"
            className={`input input-bordered w-full ${errors.power_usage ? 'input-error' : ''}`}
            value={data.power_usage || ''}
            onChange={(e) => handleChange('power_usage', e.target.value)}
            placeholder="60W"
          />
          {errors.power_usage && (
            <label className="label">
              <span className="label-text-alt text-error">{t(`virtual_energy_sensor.${errors.power_usage}`)}</span>
            </label>
          )}
          <label className="label">
            <span className="label-text-alt">{t('virtual_energy_sensor.power_usage_hint')}</span>
          </label>
        </div>
      )}

      {/* Flow Rate (for water type) */}
      {data.sensor_type === 'water' && (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('virtual_energy_sensor.flow_rate')} *</span>
          </label>
          <input
            type="text"
            className={`input input-bordered w-full ${errors.flow_rate ? 'input-error' : ''}`}
            value={data.flow_rate || ''}
            onChange={(e) => handleChange('flow_rate', e.target.value)}
            placeholder="500 L/h"
          />
          {errors.flow_rate && (
            <label className="label">
              <span className="label-text-alt text-error">{t(`virtual_energy_sensor.${errors.flow_rate}`)}</span>
            </label>
          )}
          <label className="label">
            <span className="label-text-alt">{t('virtual_energy_sensor.flow_rate_hint')}</span>
          </label>
        </div>
      )}

      {/* Area (optional) */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('virtual_energy_sensor.area')}</span>
        </label>
        <Select
          value={data.area || '_none_'}
          onValueChange={(value) => handleChange('area', value === '_none_' ? undefined : value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('virtual_energy_sensor.no_area')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem key="_none_" value="_none_">{t('virtual_energy_sensor.no_area')}</SelectItem>
            {allAreas.map((area, index) => (
              <SelectItem key={`area-${index}-${area.id}`} value={area.id}>
                {area.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="label">
          <span className="label-text-alt">{t('virtual_energy_sensor.area_hint')}</span>
        </label>
      </div>
    </div>
  );
};

export default VirtualEnergySensorForm;
