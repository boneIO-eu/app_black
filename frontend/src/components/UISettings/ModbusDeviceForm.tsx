import React, { useState, useMemo } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';

// Filter types available in schema
const FILTER_TYPES = ['offset', 'round', 'multiply', 'filter_out', 'filter_out_greater', 'filter_out_lower'] as const;
type FilterType = typeof FILTER_TYPES[number];

interface Filter {
  [key: string]: number | undefined;
}

interface FilterSectionProps {
  title: string;
  filters: Filter[];
  onChange: (filters: Filter[]) => void;
}

/**
 * FilterSection - component for managing a list of sensor filters.
 */
const FilterSection: React.FC<FilterSectionProps> = ({ title, filters, onChange }) => {
  const addFilter = () => {
    onChange([...filters, { round: 2 }]);
  };

  const removeFilter = (index: number) => {
    onChange(filters.filter((_, i) => i !== index));
  };

  const updateFilter = (index: number, filterType: FilterType, value: number | undefined) => {
    const newFilters = [...filters];
    // Clear old filter type and set new one
    const newFilter: Filter = {};
    newFilter[filterType] = value;
    newFilters[index] = newFilter;
    onChange(newFilters);
  };

  const getFilterType = (filter: Filter): FilterType => {
    for (const type of FILTER_TYPES) {
      if (filter[type] !== undefined) {
        return type;
      }
    }
    return 'round';
  };

  const getFilterValue = (filter: Filter): number | undefined => {
    const type = getFilterType(filter);
    return filter[type];
  };

  return (
    <div className="collapse collapse-arrow bg-base-200">
      <input type="checkbox" defaultChecked />
      <div className="collapse-title font-medium">
        {title}
        <span className="badge badge-sm ml-2">{filters.length}</span>
      </div>
      <div className="collapse-content">
        <div className="space-y-2">
          {filters.map((filter, index) => (
            <div key={index} className="flex items-center gap-2">
              <select
                className="select select-bordered select-sm flex-1"
                value={getFilterType(filter)}
                onChange={(e) => updateFilter(index, e.target.value as FilterType, getFilterValue(filter))}
              >
                {FILTER_TYPES.map(type => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
              <input
                type="number"
                step="0.1"
                className="input input-bordered input-sm w-24"
                value={getFilterValue(filter) ?? ''}
                onChange={(e) => updateFilter(index, getFilterType(filter), parseFloat(e.target.value) || undefined)}
                placeholder="Value"
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm text-error"
                onClick={() => removeFilter(index)}
              >
                <FaTrash />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={addFilter}
          >
            <FaPlus className="mr-1" /> Add Filter
          </button>
        </div>
      </div>
    </div>
  );
};

interface ModbusDeviceFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  areas?: Array<{ id: string; name: string }>;
}

/**
 * ModbusDeviceForm - dedicated form for Modbus device configuration.
 * 
 * Features:
 * - Consistent field widths
 * - Conditional fields based on model (sensors_filters for CWT, data for liquid-sensor)
 * - Compact layout
 */
const ModbusDeviceForm: React.FC<ModbusDeviceFormProps> = ({ 
  data, 
  onChange, 
  schema,
  areas = []
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'filters' | 'data'>('basic');

  // Extract model options from schema
  const modelOptions = useMemo(() => {
    const modelSchema = schema?.items?.properties?.model;
    if (modelSchema?.enum) {
      return modelSchema.enum;
    }
    // Default models if not in schema
    return ['sdm120', 'sdm630', 'cwt', 'liquid-sensor'];
  }, [schema]);

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const updateNestedField = (parent: string, field: string, value: any) => {
    onChange({
      ...data,
      [parent]: {
        ...(data[parent] || {}),
        [field]: value
      }
    });
  };

  const selectedModel = data.model?.toLowerCase() || '';
  const showSensorsFilters = selectedModel === 'cwt';
  const showDataFields = selectedModel === 'liquid-sensor';

  // Determine which tabs to show
  const availableTabs = useMemo(() => {
    const tabs: Array<{ id: 'basic' | 'filters' | 'data'; label: string }> = [
      { id: 'basic', label: 'Basic' }
    ];
    if (showSensorsFilters) {
      tabs.push({ id: 'filters', label: 'Sensor Filters' });
    }
    if (showDataFields) {
      tabs.push({ id: 'data', label: 'Data' });
    }
    return tabs;
  }, [showSensorsFilters, showDataFields]);

  // Reset to basic tab if current tab is not available
  React.useEffect(() => {
    if (activeTab === 'filters' && !showSensorsFilters) {
      setActiveTab('basic');
    }
    if (activeTab === 'data' && !showDataFields) {
      setActiveTab('basic');
    }
  }, [activeTab, showSensorsFilters, showDataFields]);

  return (
    <div className="space-y-4">
      {/* Tabs - only show if more than basic tab */}
      {availableTabs.length > 1 && (
        <div className="tabs tabs-boxed">
          {availableTabs.map(tab => (
            <button
              key={tab.id}
              className={`tab ${activeTab === tab.id ? 'tab-active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* Basic Tab */}
      {activeTab === 'basic' && (
        <div className="space-y-4">
          {/* Row 1: Display Name and Area */}
          <div className="grid grid-cols-2 gap-4">
            {/* Display Name */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">Display Name</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={data.name || ''}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder="e.g., Energy Meter Living Room"
              />
              <label className="label py-0.5">
                <span className="label-text-alt text-base-content/60">
                  Friendly name for Home Assistant
                </span>
              </label>
            </div>

            {/* Area */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">Area</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={data.area || ''}
                onChange={(e) => updateField('area', e.target.value || undefined)}
              >
                <option value="">No area</option>
                {areas.map((area) => (
                  <option key={area.id} value={area.id}>
                    {area.name || area.id}
                  </option>
                ))}
              </select>
              <label className="label py-0.5">
                <span className="label-text-alt text-base-content/60">
                  Room/area for grouping in HA
                </span>
              </label>
            </div>
          </div>

          {/* Row 2: Address and Model */}
          <div className="grid grid-cols-2 gap-4">
            {/* Address */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">Address *</span>
              </label>
              <input
                type="number"
                className="input input-bordered w-full"
                value={data.address || ''}
                onChange={(e) => updateField('address', parseInt(e.target.value) || '')}
                placeholder="1-247"
                min={1}
                max={247}
              />
              <label className="label py-0.5">
                <span className="label-text-alt text-base-content/60">
                  Modbus address (1-247)
                </span>
              </label>
            </div>

            {/* Model */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">Model *</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={data.model || ''}
                onChange={(e) => updateField('model', e.target.value)}
              >
                <option value="">Select model...</option>
                {modelOptions.map((model: string) => (
                  <option key={model} value={model}>
                    {model.toUpperCase()}
                  </option>
                ))}
              </select>
              <label className="label py-0.5">
                <span className="label-text-alt text-base-content/60">
                  Device model
                </span>
              </label>
            </div>
          </div>

          {/* ID - optional */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text font-medium">ID</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={data.id || ''}
              onChange={(e) => updateField('id', sanitizeId(e.target.value))}
              placeholder="Auto-generated if empty"
            />
            <label className="label py-0.5">
              <span className="label-text-alt text-base-content/60">
                {t('modbus.technical_id')}
                {!data.id && data.address && data.model && (
                  <span className="block mt-1">
                    {t('modbus.will_be')}: <code className="bg-base-300 px-1 rounded">{data.address}_{data.model}</code>
                  </span>
                )}
              </span>
            </label>
          </div>

          {/* Update Interval */}
          <SimpleTimePeriodInput
            value={data.update_interval || '30s'}
            onChange={(value: string) => updateField('update_interval', value)}
            label="Update Interval"
            required={true}
            minimum={1000}
          />
        </div>
      )}

      {/* Sensor Filters Tab - only for CWT model */}
      {activeTab === 'filters' && showSensorsFilters && (
        <div className="space-y-4">
          <div className="alert alert-info text-sm">
            <span>Configure sensor filters for CWT temperature/humidity sensor. Filters are applied in order.</span>
          </div>

          {/* Temperature Filters */}
          <FilterSection
            title="Temperature Filters"
            filters={data.sensors_filters?.temperature || []}
            onChange={(filters) => updateNestedField('sensors_filters', 'temperature', filters)}
          />

          {/* Humidity Filters */}
          <FilterSection
            title="Humidity Filters"
            filters={data.sensors_filters?.humidity || []}
            onChange={(filters) => updateNestedField('sensors_filters', 'humidity', filters)}
          />
        </div>
      )}

      {/* Data Tab - only for liquid-sensor model */}
      {activeTab === 'data' && showDataFields && (
        <div className="space-y-4">
          <div className="alert alert-info">
            <span>Configure dimensions for liquid level sensor calculation.</span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Width */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">Width</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={data.data?.width || ''}
                onChange={(e) => updateNestedField('data', 'width', e.target.value || undefined)}
                placeholder="e.g., 50cm or 0.5"
              />
              <label className="label py-0.5">
                <span className="label-text-alt text-base-content/60">
                  Width in meters, cm, etc.
                </span>
              </label>
            </div>

            {/* Length */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">Length</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={data.data?.length || ''}
                onChange={(e) => updateNestedField('data', 'length', e.target.value || undefined)}
                placeholder="e.g., 100cm or 1.0"
              />
              <label className="label py-0.5">
                <span className="label-text-alt text-base-content/60">
                  Length in meters, cm, etc.
                </span>
              </label>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ModbusDeviceForm;
