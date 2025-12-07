import React, { useEffect, useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import { useTranslation } from '../../hooks/useTranslation';
import { sanitizeId } from './helpers/idValidation';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';

// Filter types available in schema
const FILTER_TYPES = ['offset', 'round', 'multiply', 'filter_out', 'filter_out_greater', 'filter_out_lower'] as const;
type FilterType = typeof FILTER_TYPES[number];

interface Filter {
  [key: string]: number | undefined;
}

interface SensorData {
  id?: string;
  name?: string;
  address?: string;
  platform?: string;
  bus_id?: string;
  area?: string;
  show_in_ha?: boolean;
  update_interval?: string | number;
  unit_of_measurement?: string;
  filters?: Filter[];
}

interface Area {
  id: string;
  name: string;
}

interface AvailableSensor {
  address: string;
  type: string;
}

interface SensorFormProps {
  data: SensorData;
  onChange: (data: SensorData) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  allAreas?: Area[];
  availableSensors?: AvailableSensor[];
  existingSensors?: SensorData[];
  editingIndex?: number | null;
  onValidationChange?: (hasErrors: boolean) => void;
}

const SensorForm: React.FC<SensorFormProps> = ({
  data,
  onChange,
  allAreas = [],
  availableSensors = [],
  existingSensors = [],
  editingIndex,
  onValidationChange
}) => {
  const { t } = useTranslation();
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Validate form
  useEffect(() => {
    const newErrors: Record<string, string> = {};
    
    // Address is required
    if (!data.address) {
      newErrors.address = t('sensors.address_required');
    }
    
    // Check for duplicate address
    const isDuplicate = existingSensors.some((sensor, index) => 
      sensor.address === data.address && index !== editingIndex
    );
    if (isDuplicate) {
      newErrors.address = t('sensors.address_duplicate');
    }
    
    setErrors(newErrors);
    onValidationChange?.(Object.keys(newErrors).length > 0);
  }, [data, existingSensors, editingIndex, onValidationChange, t]);

  const handleChange = (field: keyof SensorData, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleIdChange = (value: string) => {
    handleChange('id', sanitizeId(value));
  };

  // Get unused sensors (not already configured)
  const getUnusedSensors = () => {
    const usedAddresses = existingSensors
      .filter((_, index) => index !== editingIndex)
      .map(s => s.address);
    return availableSensors.filter(s => !usedAddresses.includes(s.address));
  };

  const unusedSensors = getUnusedSensors();

  return (
    <div className="space-y-4">
      {/* Available Sensors Dropdown */}
      {availableSensors.length > 0 && (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('sensors.detected_sensors')}</span>
          </label>
          <select
            className={`select select-bordered w-full ${errors.address ? 'select-error' : ''}`}
            value={data.address || ''}
            onChange={(e) => handleChange('address', e.target.value)}
          >
            <option value="">{t('sensors.select_sensor')}</option>
            {unusedSensors.map((sensor) => (
              <option key={sensor.address} value={sensor.address}>
                {sensor.address} ({sensor.type})
              </option>
            ))}
            {/* Show current value if it's not in the list */}
            {data.address && !availableSensors.find(s => s.address === data.address) && (
              <option value={data.address}>{data.address} (manual)</option>
            )}
          </select>
          {errors.address && (
            <label className="label">
              <span className="label-text-alt text-error">{errors.address}</span>
            </label>
          )}
        </div>
      )}

      {/* Manual Address Input (if no sensors detected) */}
      {availableSensors.length === 0 && (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('sensors.address')} *</span>
          </label>
          <input
            type="text"
            className={`input input-bordered w-full font-mono ${errors.address ? 'input-error' : ''}`}
            value={data.address || ''}
            onChange={(e) => handleChange('address', e.target.value)}
            placeholder="28-0000098c7df0"
          />
          {errors.address && (
            <label className="label">
              <span className="label-text-alt text-error">{errors.address}</span>
            </label>
          )}
        </div>
      )}

      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('sensors.name')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder={t('sensors.name_placeholder')}
        />
      </div>

      {/* Custom ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('sensors.custom_id')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full font-mono"
          value={data.id || ''}
          onChange={(e) => handleIdChange(e.target.value)}
          placeholder={data.address || 'sensor_id'}
        />
        <label className="label">
          <span className="label-text-alt">{t('sensors.id_hint')}</span>
        </label>
      </div>

      {/* Area */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('sensors.area')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data.area || ''}
          onChange={(e) => handleChange('area', e.target.value || undefined)}
        >
          <option value="">{t('sensors.no_area')}</option>
          {allAreas.map((area) => (
            <option key={area.id} value={area.id}>
              {area.name}
            </option>
          ))}
        </select>
      </div>

      {/* Platform */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('sensors.platform')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data.platform || 'gpio_onewire'}
          onChange={(e) => handleChange('platform', e.target.value)}
        >
          <option value="gpio_onewire">GPIO 1-Wire (DS18B20)</option>
          {/* <option value="ds2482">DS2482 I2C Bridge</option> */}
        </select>
      </div>

      {/* Bus ID (only for ds2482) */}
      {data.platform === 'ds2482' && (
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">{t('sensors.bus_id')}</span>
          </label>
          <input
            type="text"
            className="input input-bordered w-full font-mono"
            value={data.bus_id || ''}
            onChange={(e) => handleChange('bus_id', e.target.value)}
            placeholder="ds2482_bus"
          />
          <label className="label">
            <span className="label-text-alt">{t('sensors.bus_id_hint')}</span>
          </label>
        </div>
      )}

      {/* Show in HA */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data.show_in_ha !== false}
            onChange={(e) => handleChange('show_in_ha', e.target.checked)}
          />
          <span className="label-text">{t('sensors.show_in_ha')}</span>
        </label>
      </div>

      {/* Update Interval */}
      <SimpleTimePeriodInput
        value={data.update_interval || '60s'}
        onChange={(value: string) => handleChange('update_interval', value)}
        label={t('sensors.update_interval')}
        required={false}
        minimum={1000}
      />

      {/* Filters Section */}
      <div className="form-control">
        <div className="collapse collapse-arrow bg-base-200 rounded-lg">
          <input type="checkbox" />
          <div className="collapse-title font-medium">
            {t('sensors.filters')}
            <span className="badge badge-sm ml-2">{(data.filters || []).length}</span>
          </div>
          <div className="collapse-content">
            <div className="space-y-2 pt-2">
              {(data.filters || []).map((filter, index) => {
                const getFilterType = (): FilterType => {
                  for (const type of FILTER_TYPES) {
                    if (filter[type] !== undefined) {
                      return type;
                    }
                  }
                  return 'round';
                };
                const filterType = getFilterType();
                const filterValue = filter[filterType];

                return (
                  <div key={index} className="flex items-center gap-2">
                    <select
                      className="select select-bordered select-sm flex-1"
                      value={filterType}
                      onChange={(e) => {
                        const newFilters = [...(data.filters || [])];
                        const newFilter: Filter = {};
                        newFilter[e.target.value as FilterType] = filterValue;
                        newFilters[index] = newFilter;
                        handleChange('filters', newFilters);
                      }}
                    >
                      {FILTER_TYPES.map(type => (
                        <option key={type} value={type}>{type}</option>
                      ))}
                    </select>
                    <input
                      type="number"
                      step="0.1"
                      className="input input-bordered input-sm w-24"
                      value={filterValue ?? ''}
                      onChange={(e) => {
                        const newFilters = [...(data.filters || [])];
                        const newFilter: Filter = {};
                        newFilter[filterType] = parseFloat(e.target.value) || undefined;
                        newFilters[index] = newFilter;
                        handleChange('filters', newFilters);
                      }}
                      placeholder={t('sensors.filter_value')}
                    />
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm text-error"
                      onClick={() => {
                        const newFilters = (data.filters || []).filter((_, i) => i !== index);
                        handleChange('filters', newFilters);
                      }}
                    >
                      <FaTrash />
                    </button>
                  </div>
                );
              })}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  const newFilters = [...(data.filters || []), { round: 2 }];
                  handleChange('filters', newFilters);
                }}
              >
                <FaPlus className="mr-1" /> {t('sensors.add_filter')}
              </button>
              <p className="text-xs text-base-content/60 mt-2">
                {t('sensors.filters_hint')}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SensorForm;
