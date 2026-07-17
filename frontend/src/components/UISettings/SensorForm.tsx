import React, { useEffect, useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import { NumericInput } from '@/components/ui/NumericInput';
import { useTranslation } from '../../hooks/useTranslation';
import { useConfig } from '../../contexts/ConfigContext';
import { sanitizeId } from './helpers/idValidation';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import AreaSelect from './widgets/AreaSelect';
import SettingsToggleGroup from './widgets/SettingsToggleGroup';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

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
  const { ds2482Supported } = useConfig();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const defaultPlatform = ds2482Supported ? 'ds2482' : 'gpio_onewire';

  // Validate form
  useEffect(() => {
    const newErrors: Record<string, string> = {};
    
    // Address is required
    if (!data.address) {
      newErrors.address = 'address_required';
    }
    
    // Check for duplicate address
    const isDuplicate = existingSensors.some((sensor, index) => 
      sensor.address === data.address && index !== editingIndex
    );
    if (isDuplicate) {
      newErrors.address = 'address_duplicate';
    }
    
    setErrors(newErrors);
    onValidationChange?.(Object.keys(newErrors).length > 0);
  }, [data.address, existingSensors, editingIndex, onValidationChange]);
  
  // Helper to get translated error message
  const getErrorMessage = (errorKey: string) => {
    return t(`sensors.${errorKey}`);
  };

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
          <Select
            value={data.address || ''}
            onValueChange={(value) => handleChange('address', value)}
          >
            <SelectTrigger className={`w-full ${errors.address ? 'border-error' : ''}`}>
              <SelectValue placeholder={t('sensors.select_sensor')} />
            </SelectTrigger>
            <SelectContent>
              {unusedSensors.map((sensor) => (
                <SelectItem key={sensor.address} value={sensor.address}>
                  {sensor.address} ({sensor.type})
                </SelectItem>
              ))}
              {/* Show current value if it's not in the list */}
              {data.address && !availableSensors.find(s => s.address === data.address) && (
                <SelectItem value={data.address}>{data.address} (manual)</SelectItem>
              )}
            </SelectContent>
          </Select>
          {errors.address && (
            <label className="label">
              <span className="label-text-alt text-error">{getErrorMessage(errors.address)}</span>
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
              <span className="label-text-alt text-error">{getErrorMessage(errors.address)}</span>
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
      <AreaSelect
        value={data.area}
        onChange={(v) => handleChange('area', v)}
        areas={allAreas}
      />

      {/* Platform */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('sensors.platform')}</span>
        </label>
        <Select
          value={data.platform || defaultPlatform}
          onValueChange={(value) => {
            if (value === 'ds2482') {
              handleChange('platform', value);
              if (!data.bus_id) handleChange('bus_id', 'ds2482_bus');
            } else {
              handleChange('platform', value);
            }
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select platform..." />
          </SelectTrigger>
          <SelectContent>
            {ds2482Supported ? (
              <SelectItem value="ds2482">DS2482 I2C Bridge</SelectItem>
            ) : (
              <>
                <SelectItem value="gpio_onewire">GPIO 1-Wire (DS18B20)</SelectItem>
                <SelectItem value="ds2482">DS2482 I2C Bridge</SelectItem>
              </>
            )}
          </SelectContent>
        </Select>
      </div>

      {/* Bus ID (only for ds2482) */}
      {(data.platform === 'ds2482' || (!data.platform && defaultPlatform === 'ds2482')) && (
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
      <SettingsToggleGroup
        items={[
          {
            key: 'show_in_ha',
            label: t('sensors.show_in_ha'),
            description: t('sensors.show_in_ha_hint'),
            checked: data.show_in_ha !== false,
            onChange: (checked) => handleChange('show_in_ha', checked),
          },
        ]}
      />

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
                    <Select
                      value={filterType}
                      onValueChange={(value) => {
                        const newFilters = [...(data.filters || [])];
                        const newFilter: Filter = {};
                        newFilter[value as FilterType] = filterValue;
                        newFilters[index] = newFilter;
                        handleChange('filters', newFilters);
                      }}
                    >
                      <SelectTrigger className="flex-1 h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {FILTER_TYPES.map(type => (
                          <SelectItem key={type} value={type}>{type}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <NumericInput
                      className="input-sm w-24"
                      decimal
                      value={filterValue ?? ''}
                      onChange={(v) => {
                        const newFilters = [...(data.filters || [])];
                        const newFilter: Filter = {};
                        newFilter[filterType] = v === '' ? undefined : v;
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
