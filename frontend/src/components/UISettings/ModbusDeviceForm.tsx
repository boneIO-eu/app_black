import React, { useState, useMemo, useEffect } from 'react';
import axios from '@/api/axios';
import { FaPlus, FaTrash } from 'react-icons/fa';
import { NumericInput } from '@/components/ui/NumericInput';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';
import HelpLabel from './components/HelpLabel';
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

interface FilterSectionProps {
  title: string;
  filters: Filter[];
  onChange: (filters: Filter[]) => void;
  t: (key: string) => string;
}

/**
 * FilterSection - component for managing a list of sensor filters.
 */
const FilterSection: React.FC<FilterSectionProps> = ({ title, filters, onChange, t }) => {
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
              <Select
                value={getFilterType(filter)}
                onValueChange={(value) => updateFilter(index, value as FilterType, getFilterValue(filter))}
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
                value={getFilterValue(filter) ?? ''}
                onChange={(v) => updateFilter(index, getFilterType(filter), v === '' ? undefined : v)}
                placeholder={t('modbus.filters.value_placeholder')}
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
            <FaPlus className="mr-1" /> {t('modbus.filters.add')}
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
  const [activeTab, setActiveTab] = useState<'basic' | 'filters' | 'data' | 'labels'>('basic');

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

  // Entity labels: fetch entity list from model JSON (not from running coordinator)
  const [entities, setEntities] = useState<Array<{ decoded_name: string; name: string; entity_type: string }>>([]);
  const [labelsLoading, setLabelsLoading] = useState(false);
  const [labelsError, setLabelsError] = useState<string | null>(null);
  const fetchedModelRef = React.useRef<string>('');

  useEffect(() => {
    if (activeTab !== 'labels' || !selectedModel) return;
    if (fetchedModelRef.current === selectedModel) return;

    let cancelled = false;
    setLabelsLoading(true);
    setLabelsError(null);

    axios.get(`/api/modbus/models/${selectedModel}/entities`)
      .then((res) => {
        if (!cancelled) {
          setEntities(res.data.entities || []);
          fetchedModelRef.current = selectedModel;
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLabelsError(t('modbus.labels.fetch_error'));
          setEntities([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLabelsLoading(false);
      });

    return () => { cancelled = true; };
  }, [activeTab, selectedModel]); // eslint-disable-line react-hooks/exhaustive-deps

  // Determine which tabs to show
  const availableTabs = useMemo(() => {
    const tabs: Array<{ id: 'basic' | 'filters' | 'data' | 'labels'; label: string }> = [
      { id: 'basic', label: t('modbus.tabs.basic') }
    ];
    if (showSensorsFilters) {
      tabs.push({ id: 'filters', label: t('modbus.tabs.filters') });
    }
    if (showDataFields) {
      tabs.push({ id: 'data', label: t('modbus.tabs.data') });
    }
    if (selectedModel) {
      tabs.push({ id: 'labels', label: t('modbus.tabs.labels') });
    }
    return tabs;
  }, [showSensorsFilters, showDataFields, selectedModel, t]);

  // Reset to basic tab if current tab is not available
  React.useEffect(() => {
    if (activeTab === 'filters' && !showSensorsFilters) {
      setActiveTab('basic');
    }
    if (activeTab === 'data' && !showDataFields) {
      setActiveTab('basic');
    }
    if (activeTab === 'labels' && !selectedModel) {
      setActiveTab('basic');
    }
  }, [activeTab, showSensorsFilters, showDataFields, selectedModel]);

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
                <span className="label-text font-medium">{t('modbus.display_name')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={data.name || ''}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder={t('modbus.display_name_placeholder')}
              />
              <HelpLabel className="py-0.5">{t('modbus.display_name_hint')}</HelpLabel>
            </div>

            {/* Area */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">{t('modbus.area')}</span>
              </label>
              <Select
                value={data.area || '_none_'}
                onValueChange={(value) => updateField('area', value === '_none_' ? undefined : value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('modbus.no_area')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none_">{t('modbus.no_area')}</SelectItem>
                  {areas.map((area) => (
                    <SelectItem key={area.id} value={area.id}>
                      {area.name || area.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <HelpLabel className="py-0.5">{t('modbus.area_hint')}</HelpLabel>
            </div>
          </div>

          {/* Row 2: Address and Model */}
          <div className="grid grid-cols-2 gap-4">
            {/* Address */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">{t('modbus.address_required')}</span>
              </label>
              <NumericInput
                value={data.address || ''}
                onChange={(v) => updateField('address', v)}
                placeholder={t('modbus.address_placeholder')}
                min={1}
                max={247}
              />
              <HelpLabel className="py-0.5">{t('modbus.address_hint')}</HelpLabel>
            </div>

            {/* Model */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">{t('modbus.model_required')}</span>
              </label>
              <Select
                value={data.model || ''}
                onValueChange={(value) => updateField('model', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('modbus.select_model')} />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((model: string) => (
                    <SelectItem key={model} value={model}>
                      {model.toUpperCase()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <HelpLabel className="py-0.5">{t('modbus.model_hint')}</HelpLabel>
            </div>
          </div>

          {/* Model description / notes from i18n — full width below the grid */}
          {selectedModel && (() => {
            const descKey = `modbus_devices.${selectedModel}.description`;
            const desc = t(descKey);
            return desc !== descKey ? (
              <div className="flex items-start gap-2 rounded-lg bg-warning/10 border border-warning/30 px-3 py-2 text-xs text-warning-content">
                <svg xmlns="http://www.w3.org/2000/svg" className="stroke-warning shrink-0 h-4 w-4 mt-0.5" fill="none" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{desc}</span>
              </div>
            ) : null;
          })()}

          {/* ID - optional */}
          <div className="form-control">
            <label className="label py-1">
              <span className="label-text font-medium">{t('modbus.id')}</span>
            </label>
            <input
              type="text"
              className="input input-bordered w-full"
              value={data.id || ''}
              onChange={(e) => updateField('id', sanitizeId(e.target.value))}
              placeholder={t('modbus.id_placeholder')}
            />
            <HelpLabel className="py-0.5">
              {t('modbus.technical_id')}
              {!data.id && data.address && data.model && (
                <span className="block mt-1">
                  {t('modbus.will_be')}: <code className="bg-base-300 px-1 rounded">{data.address}_{data.model}</code>
                </span>
              )}
            </HelpLabel>
          </div>

          {/* Update Interval */}
          <SimpleTimePeriodInput
            value={data.update_interval || '30s'}
            onChange={(value: string) => updateField('update_interval', value)}
            label={t('modbus.update_interval')}
            required={true}
            minimum={1000}
          />
        </div>
      )}

      {/* Sensor Filters Tab - only for CWT model */}
      {activeTab === 'filters' && showSensorsFilters && (
        <div className="space-y-4">
          <div className="alert alert-info text-sm">
            <span>{t('modbus.filters.info')}</span>
          </div>

          {/* Temperature Filters */}
          <FilterSection
            title={t('modbus.filters.temperature')}
            filters={data.sensors_filters?.temperature || []}
            onChange={(filters) => updateNestedField('sensors_filters', 'temperature', filters)}
            t={t}
          />

          {/* Humidity Filters */}
          <FilterSection
            title={t('modbus.filters.humidity')}
            filters={data.sensors_filters?.humidity || []}
            onChange={(filters) => updateNestedField('sensors_filters', 'humidity', filters)}
            t={t}
          />
        </div>
      )}

      {/* Data Tab - only for liquid-sensor model */}
      {activeTab === 'data' && showDataFields && (
        <div className="space-y-4">
          <div className="alert alert-info">
            <span>{t('modbus.data.info')}</span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Width */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">{t('modbus.data.width')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={data.data?.width || ''}
                onChange={(e) => updateNestedField('data', 'width', e.target.value.replace(',', '.') || undefined)}
                placeholder={t('modbus.data.width_placeholder')}
              />
              <HelpLabel className="py-0.5">{t('modbus.data.width_hint')}</HelpLabel>
            </div>

            {/* Length */}
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text font-medium">{t('modbus.data.length')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                value={data.data?.length || ''}
                onChange={(e) => updateNestedField('data', 'length', e.target.value.replace(',', '.') || undefined)}
                placeholder={t('modbus.data.length_placeholder')}
              />
              <HelpLabel className="py-0.5">{t('modbus.data.length_hint')}</HelpLabel>
            </div>
          </div>
        </div>
      )}

      {/* Entity Labels Tab */}
      {activeTab === 'labels' && (
        <div className="space-y-4">
          <div className="alert alert-info text-sm">
            <span>{t('modbus.labels.info')}</span>
          </div>

          {labelsLoading && (
            <div className="flex justify-center py-4">
              <span className="loading loading-spinner loading-md" />
            </div>
          )}

          {labelsError && (
            <div className="alert alert-warning text-sm">
              <span>{labelsError}</span>
            </div>
          )}

          {!labelsLoading && entities.filter(e => !e.entity_type?.includes('discrete')).length > 0 && (
            <div className="space-y-2">
              {entities.filter(e => !e.entity_type?.includes('discrete')).map((entity) => (
                <div key={entity.decoded_name} className="flex items-center gap-3">
                  <div className="w-44 shrink-0">
                    <span className="text-sm text-base-content/70 truncate block" title={entity.name}>
                      {entity.name}
                    </span>
                    <span className="badge badge-xs badge-ghost">{entity.entity_type}</span>
                  </div>
                  <input
                    type="text"
                    className="input input-bordered input-sm flex-1"
                    value={data.entity_labels?.[entity.decoded_name] ?? ''}
                    onChange={(e) => {
                      const newLabels = { ...(data.entity_labels || {}) };
                      if (e.target.value.trim()) {
                        newLabels[entity.decoded_name] = e.target.value;
                      } else {
                        delete newLabels[entity.decoded_name];
                      }
                      updateField('entity_labels', Object.keys(newLabels).length > 0 ? newLabels : undefined);
                    }}
                    placeholder={entity.name}
                  />
                </div>
              ))}
            </div>
          )}

          {!labelsLoading && entities.filter(e => !e.entity_type?.includes('discrete')).length === 0 && !labelsError && (
            <div className="text-center py-4 text-base-content/60 text-sm">
              {t('modbus.labels.no_entities')}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ModbusDeviceForm;
