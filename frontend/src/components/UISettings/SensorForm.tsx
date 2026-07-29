import React, { useEffect, useState } from 'react';
import { FaCheckCircle, FaExclamationCircle, FaExclamationTriangle, FaPlus, FaSearch, FaTrash } from 'react-icons/fa';
import { NumericInput } from '@/components/ui/NumericInput';
import { useTranslation } from '../../hooks/useTranslation';
import axios from 'axios';
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
  const [errors, setErrors] = useState<Record<string, string>>({});

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

  // Local scan state
  const [isScanning, setIsScanning] = useState(false);
  const [localSensors, setLocalSensors] = useState<AvailableSensor[]>(availableSensors);
  const [scanStatus, setScanStatus] = useState<'idle' | 'success' | 'warning' | 'error'>('idle');
  const [scanMessage, setScanMessage] = useState<string | null>(null);

  // Sync parent sensors into local state
  useEffect(() => {
    if (availableSensors.length > 0) {
      setLocalSensors(prev => {
        const merged = [...prev];
        for (const s of availableSensors) {
          if (!merged.find(m => m.address === s.address)) {
            merged.push(s);
          }
        }
        return merged;
      });
    }
  }, [availableSensors]);

  const handleScan = async () => {
    setIsScanning(true);
    setScanMessage(null);
    setScanStatus('idle');
    try {
      const res = await axios.get('/api/onewire/scan');
      const devices = (res.data.devices || []) as { address: string; family_name: string; error?: string }[];
      const found = devices
        .filter((d: { address: string; error?: string }) => d.address && !d.error)
        .map((d: { address: string; family_name: string }) => ({ address: d.address, type: d.family_name || 'DS18B20' }));

      if (found.length > 0) {
        setLocalSensors(prev => {
          const merged = [...prev];
          for (const s of found) {
            if (!merged.find(m => m.address === s.address)) {
              merged.push(s);
            }
          }
          return merged;
        });
        setScanStatus('success');
        if (found.length === 1) {
          setScanMessage(t('sensors.scan_found_one', { count: '1', defaultValue: 'Wykryto 1 urządzenie' }));
        } else if (found.length >= 2 && found.length <= 4) {
          setScanMessage(t('sensors.scan_found_few', { count: String(found.length), defaultValue: `Wykryto ${found.length} urządzenia` }));
        } else {
          setScanMessage(t('sensors.scan_found', { count: String(found.length) }));
        }
      } else {
        setScanStatus('warning');
        setScanMessage(t('sensors.scan_no_devices'));
      }
    } catch {
      setScanStatus('error');
      setScanMessage(t('sensors.scan_error'));
    } finally {
      setIsScanning(false);
    }
  };

  // Use local sensors for the dropdown
  const allSensors = localSensors;
  const getUnusedSensorsLocal = () => {
    const usedAddresses = existingSensors
      .filter((_, index) => index !== editingIndex)
      .map(s => s.address);
    return allSensors.filter(s => !usedAddresses.includes(s.address));
  };
  const unusedSensorsLocal = getUnusedSensorsLocal();

  return (
    <div className="space-y-4">
      {/* Scan 1-Wire Button & Status */}
      <div className="flex flex-wrap items-center gap-3 my-1">
        <button
          type="button"
          className={`btn btn-outline btn-sm gap-2 shrink-0 ${isScanning ? 'loading' : ''}`}
          onClick={handleScan}
          disabled={isScanning}
        >
          {!isScanning && <FaSearch />}
          {isScanning ? t('sensors.scanning') : t('sensors.scan_onewire')}
        </button>

        {scanMessage && (
          <div className={`text-xs px-3 py-1.5 rounded-lg flex items-center gap-2 font-medium transition-all ${
            scanStatus === 'success'
              ? 'bg-success/10 text-success border border-success/20'
              : scanStatus === 'warning'
              ? 'bg-warning/10 text-warning-content border border-warning/20'
              : 'bg-error/10 text-error border border-error/20'
          }`}>
            {scanStatus === 'success' && <FaCheckCircle className="shrink-0 text-sm" />}
            {scanStatus === 'warning' && <FaExclamationTriangle className="shrink-0 text-sm" />}
            {scanStatus === 'error' && <FaExclamationCircle className="shrink-0 text-sm" />}
            <span>{scanMessage}</span>
          </div>
        )}
      </div>

      {/* Available Sensors Dropdown */}
      {allSensors.length > 0 && (
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
              {unusedSensorsLocal.map((sensor) => (
                <SelectItem key={sensor.address} value={sensor.address}>
                  {sensor.address} ({sensor.type})
                </SelectItem>
              ))}
              {/* Show current value if it's not in the list */}
              {data.address && !allSensors.find(s => s.address === data.address) && (
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
      {allSensors.length === 0 && (
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
