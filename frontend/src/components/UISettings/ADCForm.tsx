import React, { useEffect, useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import { NumericInput } from '@/components/ui/NumericInput';
import { useTranslation } from '../../hooks/useTranslation';
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
import type { AreaEntity } from '@/types/config';

// ADC pins available on BeagleBone Black (from schema)
const ADC_PINS = ['P9_33', 'P9_35', 'P9_36', 'P9_37', 'P9_38', 'P9_39', 'P9_40'] as const;

// Pin to AIN mapping for display
const PIN_AIN_MAP: Record<string, string> = {
  'P9_39': 'AIN0',
  'P9_40': 'AIN1',
  'P9_37': 'AIN2',
  'P9_38': 'AIN3',
  'P9_33': 'AIN4',
  'P9_36': 'AIN5',
  'P9_35': 'AIN6',
};

// Filter types available for ADC
const FILTER_TYPES = ['offset', 'round', 'multiply', 'filter_out', 'filter_out_greater', 'filter_out_lower'] as const;
type FilterType = typeof FILTER_TYPES[number];

interface Filter {
  [key: string]: number | undefined;
}

interface ADCData {
  name?: string;
  id?: string;
  pin?: string;
  area?: string;
  show_in_ha?: boolean;
  update_interval?: string | number;
  filters?: Filter[];
}

interface ADCFormProps {
  data: ADCData;
  onChange: (data: ADCData) => void;
  existingItems?: ADCData[];
  editingIndex?: number | null;
  allAreas?: AreaEntity[];
  onValidationChange?: (hasErrors: boolean) => void;
}

const ADCForm: React.FC<ADCFormProps> = ({
  data,
  onChange,
  existingItems = [],
  editingIndex,
  allAreas = [],
  onValidationChange
}) => {
  const { t } = useTranslation();
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Validate form
  useEffect(() => {
    const newErrors: Record<string, string> = {};

    // Pin is required
    if (!data.pin) {
      newErrors.pin = 'pin_required';
    }

    // Check for duplicate pin
    const isDuplicate = existingItems.some((item, index) =>
      item.pin === data.pin && index !== editingIndex
    );
    if (isDuplicate && data.pin) {
      newErrors.pin = 'pin_duplicate';
    }

    setErrors(newErrors);
    onValidationChange?.(Object.keys(newErrors).length > 0);
  }, [data.pin, existingItems, editingIndex, onValidationChange]);

  const handleChange = (field: keyof ADCData, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleIdChange = (value: string) => {
    handleChange('id', sanitizeId(value));
  };

  // Get pins already used by other ADC entries
  const getUsedPins = (): Set<string> => {
    const used = new Set<string>();
    existingItems.forEach((item, index) => {
      if (index !== editingIndex && item.pin) {
        used.add(item.pin);
      }
    });
    return used;
  };

  const usedPins = getUsedPins();

  return (
    <div className="space-y-4">
      {/* Pin Selection */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('adc.pin')} *</span>
        </label>
        <Select
          value={data.pin || ''}
          onValueChange={(value) => handleChange('pin', value)}
        >
          <SelectTrigger className={`w-full ${errors.pin ? 'border-error' : ''}`}>
            <SelectValue placeholder={t('adc.select_pin')} />
          </SelectTrigger>
          <SelectContent>
            {ADC_PINS.map((pin) => {
              const ain = PIN_AIN_MAP[pin] || '';
              const isUsed = usedPins.has(pin);
              return (
                <SelectItem key={pin} value={pin} disabled={isUsed}>
                  {pin} ({ain}){isUsed ? ` - ${t('adc.pin_in_use')}` : ''}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
        {errors.pin && (
          <label className="label">
            <span className="label-text-alt text-error">{t(`adc.${errors.pin}`)}</span>
          </label>
        )}
        <label className="label">
          <span className="label-text-alt">{t('adc.pin_hint')}</span>
        </label>
      </div>

      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('adc.name')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data.name || ''}
          onChange={(e) => handleChange('name', e.target.value || undefined)}
          placeholder={data.pin ? PIN_AIN_MAP[data.pin] || data.pin : ''}
        />
        <label className="label">
          <span className="label-text-alt">{t('adc.name_hint')}</span>
        </label>
      </div>

      {/* Custom ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('adc.id')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full font-mono"
          value={data.id || ''}
          onChange={(e) => handleIdChange(e.target.value)}
          placeholder={data.name || (data.pin ? PIN_AIN_MAP[data.pin] || data.pin : 'adc_sensor_id')}
        />
        <label className="label">
          <span className="label-text-alt">{t('adc.id_hint')}</span>
        </label>
      </div>

      {/* Show in HA */}
      <SettingsToggleGroup
        items={[
          {
            key: 'show_in_ha',
            label: t('adc.show_in_ha'),
            description: t('adc.show_in_ha_hint'),
            checked: data.show_in_ha !== false,
            onChange: (checked) => handleChange('show_in_ha', checked),
          },
        ]}
      />

      {/* Area */}
      <AreaSelect
        value={data.area}
        onChange={(areaId) => handleChange('area', areaId)}
        areas={allAreas}
      />

      {/* Update Interval */}
      <SimpleTimePeriodInput
        value={data.update_interval || '60s'}
        onChange={(value: string) => handleChange('update_interval', value)}
        label={t('adc.update_interval')}
        required={false}
        minimum={1000}
      />

      {/* Filters Section */}
      <div className="form-control">
        <div className="collapse collapse-arrow bg-base-200 rounded-lg">
          <input type="checkbox" defaultChecked />
          <div className="collapse-title font-medium">
            {t('adc.filters')}
            <span className="badge badge-sm ml-2">{(data.filters || []).length}</span>
          </div>
          <div className="collapse-content">
            <p className="text-xs text-base-content/60 mb-3">
              {t('adc.filters_hint')}
            </p>
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
                      <SelectTrigger className="w-36 h-8">
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
                      placeholder={t('adc.filter_value')}
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
                <FaPlus className="mr-1" /> {t('adc.add_filter')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ADCForm;
