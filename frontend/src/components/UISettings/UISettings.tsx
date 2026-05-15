import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from '@/api/axios';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import * as yaml from 'js-yaml';
import {
  convertFormDataToOriginalTypes,
  convertTimeperiodToMilliseconds,
  stripHiddenAndDefaults,
  convertMillisecondsToTimeperiod,
} from '@/components/UISettings/helpers/configSchemaUtils';
import {
  RELOAD_SECTIONS,
  RESTART_SECTIONS,
  ALL_SECTIONS,
  COMPOSITE_SECTIONS,
} from '@/components/UISettings/constants/sectionDefinitions';
import { useTranslation } from '@/hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import { SectionContent, SettingsSidebar, SectionHeader } from './components';

/**
 * UISettings - Form-based configuration editor with tabs for each config section
 *
 * This component provides a modern form-based interface for editing YAML configuration files.
 * Each configuration section (mqtt, web, logger, etc.) is presented as a separate tab with
 * a JSON Schema-driven form. Users can edit one section at a time and save changes individually.
 *
 * CURRENTLY DISABLED: This component is temporarily disabled due to JSON Schema validation
 * issues and RJSFSchema compatibility problems. The routes still exist but the navigation
 * menu item is commented out. Can be re-enabled when schema issues are resolved.
 */

interface ConfigSection {
  name: string;
  schema: any;
  normalizedSchema: any;
  uiSchema: any;
  data: Record<string, any>;
}

export default function UISettings() {
  const { section } = useParams<{ section?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { refreshConfig } = useConfig();

  // Get edit item name from query param (for deep linking from InputsView/OutputsView)
  const editItemName = searchParams.get('edit');

  // Clear edit param after it's been used
  const clearEditParam = useCallback(() => {
    if (editItemName) {
      setSearchParams({});
    }
  }, [editItemName, setSearchParams]);
  const [sections, setSections] = useState<ConfigSection[]>([]);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [originalData, setOriginalData] = useState<Record<string, any>>({});
  const [showYamlPreview, setShowYamlPreview] = useState(false);
  const [saveStatus, setSaveStatus] = useState<{
    [key: string]: 'idle' | 'saving' | 'success' | 'error';
  }>({});
  const [unsavedChanges, setUnsavedChanges] = useState<{ [key: string]: boolean }>({});
  const [isReloading, setIsReloading] = useState(false);
  const [restartRequired, setRestartRequired] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [schemaLoaded, setSchemaLoaded] = useState(false);
  const [loxFormValid, setLoxFormValid] = useState(true);
  const contentRef = useRef<HTMLDivElement>(null);

  // Get active section from URL parameter or default to first section
  const activeSection = section || 'mqtt';

  /**
   * Handle application restart
   */
  const handleRestart = async () => {
    if (
      !confirm(
        'Are you sure you want to restart the application? This will briefly interrupt all connections.'
      )
    ) {
      return;
    }

    setIsRestarting(true);
    try {
      await axios.post('/api/restart');
      // The server will restart, so we won't get a response
      // Show a message and wait for reconnection
    } catch (error) {
      // Expected - server is restarting
      console.log('Server is restarting...');
    }
  };

  // Function to navigate to a section
  const navigateToSection = (sectionName: string) => {
    navigate(`/settings/${sectionName}`);
    // On mobile: close sidebar accordion so content is immediately visible
    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  };

  // Check if any remote inputs are configured or remote devices exist
  const hasRemoteInputs = useMemo(() => {
    const remoteInputs = formData.remote_inputs || [];
    const remoteDevices = formData.remote_devices || [];
    return remoteInputs.length > 0 || remoteDevices.length > 0;
  }, [formData.remote_inputs, formData.remote_devices]);

  // Use imported section definitions with translated titles
  // Hide remote_inputs when no remote devices exist and no inputs configured
  const reloadSections = useMemo(
    () => RELOAD_SECTIONS
      .filter(s => s.name !== 'remote_inputs' || hasRemoteInputs)
      .map(s => ({ ...s, title: t(s.translationKey) })),
    [t, hasRemoteInputs]
  );

  // Hardware version determines which sections are available
  // CAN bus support was added in hardware version 0.5
  const hwVersion = parseFloat(formData.boneio?.version || '0');
  const canSupported = hwVersion >= 0.5;

  if (!canSupported && hwVersion > 0) {
    console.log('CAN not supported: hardware version', hwVersion, '< 0.5');
  }

  const restartSections = useMemo(
    () => RESTART_SECTIONS
      .filter(s => s.name !== 'can' || canSupported)
      .map(s => ({ ...s, title: t(s.translationKey) })),
    [t, canSupported]
  );

  const configSections = useMemo(
    () => ALL_SECTIONS.map(s => ({ ...s, title: t(s.translationKey) })),
    [t]
  );

  /**
   * Convert data to match schema types (for form display)
   */
  const convertDataToSchemaTypes = (
    data: Record<string, any>,
    schema: any
  ): Record<string, any> => {
    if (!data || !schema || typeof data !== 'object' || typeof schema !== 'object') {
      return data;
    }

    const converted = { ...data };

    // Handle properties in schema
    if (schema.properties) {
      Object.keys(schema.properties).forEach(key => {
        if (key in converted && converted[key] !== null && converted[key] !== undefined) {
          const propSchema = schema.properties[key] as any;
          const currentValue = converted[key];

          // Handle array with items schema
          if (propSchema?.items && Array.isArray(currentValue)) {
            converted[key] = currentValue.map((item: any) => {
              if (typeof item === 'object' && propSchema.items?.properties) {
                return convertDataToSchemaTypes(item, propSchema.items);
              }
              return item;
            });
          }
          // Convert timeperiod object to milliseconds for form display
          else if (propSchema?.['x-timeperiod'] === true) {
            const milliseconds = convertTimeperiodToMilliseconds(currentValue);
            converted[key] = milliseconds;
          }
          // Convert number to string if schema expects string with enum
          else if (
            propSchema?.type === 'string' &&
            propSchema?.enum &&
            typeof currentValue === 'number'
          ) {
            const stringValue = String(currentValue);
            // Check if the string version exists in enum
            if (propSchema.enum.includes(stringValue)) {
              converted[key] = stringValue;
              console.log(`✓ Converted ${key} to string: ${stringValue}`);
            } else {
              console.log(`✗ String value ${stringValue} not found in enum:`, propSchema.enum);
            }
          }
          // Handle nested objects recursively
          else if (propSchema?.type === 'object' && typeof currentValue === 'object') {
            converted[key] = convertDataToSchemaTypes(currentValue, propSchema);
          }
        }
      });
    }

    return converted;
  };

  /**
   * Load configuration and schemas (lazy loading - config first, schema in background)
   */
  const loadConfiguration = useCallback(async () => {
    try {
      // Check restart status from backend (non-blocking)
      axios.get('/api/status/restart')
        .then(res => {
          if (res.data?.restart_required) setRestartRequired(true);
        })
        .catch(() => { });

      // Load parsed config from backend FIRST (fast, small)
      const { data: configContent } = await axios.get('/api/config');
      const configData = configContent?.config || {};

      // Merge composite sections (e.g. lm75 + ina219 + mcp9808 → board_sensors,
      // binary_sensor + event → local_inputs)
      for (const [virtualName, yamlKeys] of Object.entries(COMPOSITE_SECTIONS)) {
        const merged: any[] = [];
        for (const key of yamlKeys) {
          const items = configData[key];
          if (Array.isArray(items)) {
            for (const item of items) {
              merged.push({ ...item, _type: key });
            }
          }
        }
        configData[virtualName] = merged;
      }

      // remote_inputs is now a top-level config section (no aggregation needed)

      // Set form data immediately WITHOUT schema conversion (UI shows instantly)
      // Schema-converted data will overwrite this once schema loads in background.
      setFormData(configData);
      setOriginalData(JSON.parse(JSON.stringify(configData)));

      // Create initial sections without schema (for custom forms that don't need it)
      const initialSections: ConfigSection[] = configSections.map(sectionConfig => ({
        name: sectionConfig.name,
        schema: { type: 'object' },
        normalizedSchema: { type: 'object', properties: {} },
        uiSchema: {},
        data: configData[sectionConfig.name] || {},
      }));
      setSections(initialSections);

      // Load schema in background (lazy) - only needed for ArrayTableWidget sections
      const schemaUrl = '/schema/config.schema.json';

      axios.get(schemaUrl, { headers: { 'Cache-Control': 'no-store' } })
        .then(res => res.data)
        .then(mainSchema => {
          // Debug: log all schema keys
          console.log(
            '📦 Schema loaded. All property keys:',
            Object.keys(mainSchema.properties || {})
          );
          console.log('📦 Cover schema exists?', !!mainSchema.properties?.cover);
          if (mainSchema.properties?.cover) {
            console.log('📦 Cover schema type:', mainSchema.properties.cover.type);
          }

          // Update sections with proper schemas
          // Filter boneio_input enum based on board version:
          // Boards 0.5+ have 49 inputs (CAN uses 3 pins)
          // Boards 0.2-0.4 have 52 inputs (CAN pins repurposed as GPIO)
          const version = configData?.boneio?.version ? String(configData.boneio.version) : null;
          const maxInputs = version ? ({ '0.2': 52, '0.3': 52, '0.4': 52 }[version] ?? 49) : 49;
          const allowedInputs = Array.from({ length: maxInputs }, (_, i) =>
            `in_${String(i + 1).padStart(2, '0')}`
          );

          const loadedSections: ConfigSection[] = configSections.map(sectionConfig => {
            // Virtual sections use the event schema as base (superset of binary_sensor)
            const schemaKey = sectionConfig.name === 'local_inputs'
              ? 'event'
              : sectionConfig.name;
            let sectionSchema = mainSchema.properties?.[schemaKey];

            // Debug for cover section
            if (sectionConfig.name === 'cover') {
              console.log('🔍 Cover section lookup:', {
                name: sectionConfig.name,
                found: !!sectionSchema,
                schema: sectionSchema,
              });
            }

            // Safe fallback if schema is missing
            if (!sectionSchema) {
              console.warn(`⚠️ Missing schema for section: ${sectionConfig.name}`);
              if (
                [
                  'cover',
                  'output',
                  'input',
                  'event',
                  'binary_sensor',
                  'modbus_devices',
                  'areas',
                  'sensor',
                  'output_group',
                ].includes(sectionConfig.name)
              ) {
                sectionSchema = { type: 'array', items: { type: 'object', properties: {} } };
              } else {
                sectionSchema = { type: 'object', properties: {} };
              }
            }

            // Filter boneio_input enum for event/binary_sensor/local_inputs based on board version
            if (
              (sectionConfig.name === 'event' || sectionConfig.name === 'binary_sensor' || sectionConfig.name === 'local_inputs') &&
              sectionSchema?.items?.properties?.boneio_input?.enum
            ) {
              sectionSchema = {
                ...sectionSchema,
                items: {
                  ...sectionSchema.items,
                  properties: {
                    ...sectionSchema.items.properties,
                    boneio_input: {
                      ...sectionSchema.items.properties.boneio_input,
                      enum: sectionSchema.items.properties.boneio_input.enum.filter(
                        (v: string) => allowedInputs.includes(v)
                      ),
                    },
                  },
                },
              };
            }

            return {
              name: sectionConfig.name,
              schema: sectionSchema,
              normalizedSchema: normalizeSchema(sectionSchema),
              uiSchema: {},
              data: configData[sectionConfig.name] || {},
            };
          });
          setSections(loadedSections);

          // Now convert form data with schema types
          const convertedFormData = convertDataToSchemaTypes(configData, mainSchema);
          setFormData(convertedFormData);
          setOriginalData(JSON.parse(JSON.stringify(convertedFormData)));

          // Mark schema as loaded AFTER data conversion is complete
          setSchemaLoaded(true);
          console.log('✅ Schema loaded and data converted', convertedFormData);
        })
        .catch(err => console.warn('Schema loading failed (non-critical):', err));
    } catch (error) {
      console.error('Error loading configuration:', error);
    }
  }, []);

  /**
   * Filter out auto-generated fields from configuration
   */
  const filterAutoGeneratedFields = useCallback((data: any): any => {
    if (!data || typeof data !== 'object') return data;

    // Create a deep copy to avoid mutating original
    const filtered = JSON.parse(JSON.stringify(data));

    // Filter outputs - remove auto-generated fields if boneio_output exists
    if (Array.isArray(filtered)) {
      return filtered.map((item: any) => {
        if (item && typeof item === 'object') {
          // If boneio_output exists, remove auto-generated fields
          if (item.boneio_output) {
            const { kind, mcp_id, pca_id, pcf_id, pin, ...rest } = item;
            return rest;
          }
          // If boneio_input exists, remove auto-generated fields
          if (item.boneio_input) {
            const { kind, pin, gpiochip, line, ...rest } = item;
            return rest;
          }
        }
        return item;
      });
    }

    // Handle object with output/input arrays
    if (filtered.output && Array.isArray(filtered.output)) {
      filtered.output = filtered.output.map((output: any) => {
        if (output.boneio_output) {
          const { kind, mcp_id, pca_id, pcf_id, pin, ...rest } = output;
          return rest;
        }
        return output;
      });
    }

    if (filtered.input && Array.isArray(filtered.input)) {
      filtered.input = filtered.input.map((input: any) => {
        if (input.boneio_input) {
          const { kind, mcp_id, pca_id, pcf_id, pin, ...rest } = input;
          return rest;
        }
        return input;
      });
    }

    // Remove empty/null values to clean up the YAML
    const removeEmptyValues = (obj: any): any => {
      if (Array.isArray(obj)) {
        return obj.map(removeEmptyValues).filter(item => item !== null && item !== undefined);
      } else if (obj !== null && typeof obj === 'object') {
        const cleaned: any = {};
        for (const [key, value] of Object.entries(obj)) {
          const cleanedValue = removeEmptyValues(value);
          // Keep the key if value is not null/undefined/empty string/empty array/empty object
          // Also strip internal metadata keys starting with '_'
          if (
            key.startsWith('_') ||
            cleanedValue === null ||
            cleanedValue === undefined ||
            cleanedValue === '' ||
            (Array.isArray(cleanedValue) && cleanedValue.length === 0) ||
            (typeof cleanedValue === 'object' && Object.keys(cleanedValue).length === 0)
          ) {
            continue;
          }
          cleaned[key] = cleanedValue;
        }
        return cleaned;
      }
      return obj;
    };

    return removeEmptyValues(filtered);
  }, []);

  /**
   * Convert data to YAML format (with defaults stripped)
   */
  const convertToYaml = useCallback(
    (data: any, sectionName?: string): string => {
      try {
        // Filter out auto-generated fields
        let filteredData = filterAutoGeneratedFields(data);

        // Strip default values if we have schema for this section
        if (sectionName) {
          const sectionInfo = sections.find(s => s.name === sectionName);
          if (sectionInfo) {
            filteredData = stripHiddenAndDefaults(
              filteredData,
              sectionInfo.normalizedSchema,
              sectionInfo.uiSchema || {}
            );
          }
        }

        // Special handling for mcp23017 - convert addresses to hex format
        if (sectionName === 'mcp23017' && Array.isArray(filteredData)) {
          filteredData = filteredData.map((entry: any) => {
            if (entry && entry.address !== undefined) {
              let addr = entry.address;
              // Convert number to hex string
              if (typeof addr === 'number') {
                addr = `0x${addr.toString(16)}`;
              } else if (typeof addr === 'string' && !addr.startsWith('0x')) {
                const num = parseInt(addr, 10);
                if (!isNaN(num)) {
                  addr = `0x${num.toString(16)}`;
                }
              }
              return { ...entry, address: addr };
            }
            return entry;
          });
        }

        // Convert timeperiod fields from milliseconds (number) or TimePeriod object back to string with unit
        // This is needed because formData stores timeperiods as numbers for form inputs
        // and backend may return TimePeriod objects
        const convertTimeperiodsForYaml = (obj: any, schema: any): any => {
          if (!obj || typeof obj !== 'object') return obj;

          if (Array.isArray(obj)) {
            const itemsSchema = schema?.items;
            return obj.map((item: any) => convertTimeperiodsForYaml(item, itemsSchema));
          }

          const result = { ...obj };
          const properties = schema?.properties || {};

          Object.keys(result).forEach(key => {
            const propSchema = properties[key];
            const value = result[key];

            // Check if this is a timeperiod field (by schema or by detecting TimePeriod object)
            const isTimePeriodSchema = propSchema && propSchema['x-timeperiod'] === true;
            const isTimePeriodObject = typeof value === 'object' && value !== null &&
              ('milliseconds' in value || 'seconds' in value || 'minutes' in value || 'hours' in value || '_total_in_seconds' in value);

            if (isTimePeriodSchema || isTimePeriodObject) {
              // Convert number (milliseconds) to string with unit
              if (typeof value === 'number') {
                result[key] = convertMillisecondsToTimeperiod(value);
              }
              // Convert TimePeriod object to string with unit
              else if (isTimePeriodObject) {
                // Use the most appropriate unit based on what's defined
                if (value.hours !== undefined && value.hours > 0) {
                  result[key] = `${value.hours}h`;
                } else if (value.minutes !== undefined && value.minutes > 0) {
                  result[key] = `${value.minutes}min`;
                } else if (value.seconds !== undefined && value.seconds > 0) {
                  result[key] = `${value.seconds}s`;
                } else if (value.milliseconds !== undefined && value.milliseconds > 0) {
                  result[key] = `${value.milliseconds}ms`;
                } else if (value._total_in_seconds !== undefined) {
                  result[key] = convertMillisecondsToTimeperiod(value._total_in_seconds * 1000);
                } else {
                  result[key] = '0s';
                }
              }
              // String already - keep as-is
            }
            // Recursively handle nested objects/arrays (but not TimePeriod objects)
            else if (typeof value === 'object' && value !== null) {
              result[key] = convertTimeperiodsForYaml(value, propSchema);
            }
          });

          return result;
        };

        // Apply timeperiod conversion if we have schema
        if (sectionName) {
          const sectionInfo = sections.find(s => s.name === sectionName);
          if (sectionInfo?.schema) {
            filteredData = convertTimeperiodsForYaml(filteredData, sectionInfo.schema);
          }
        }

        // Convert to YAML format
        const yamlString = yaml.dump(filteredData, {
          indent: 2,
          lineWidth: -1, // No line wrapping
          noRefs: true,
          quotingType: '"',
          forceQuotes: false,
          sortKeys: false,
          flowLevel: -1, // Use block style (lists with -) instead of flow style
          styles: {
            '!!null': 'empty', // Represent null as empty
          },
        });

        return yamlString;
      } catch (error) {
        console.error('Error converting to YAML:', error);
        // Fallback to JSON if YAML conversion fails
        return JSON.stringify(data, null, 2);
      }
    },
    [filterAutoGeneratedFields, sections]
  );

  /**
   * Handle form data change for a section
   */
  const handleSectionChange = (sectionName: string, newFormData: any) => {
    console.log('📝 handleSectionChange called for:', sectionName);

    setFormData((prevFormData: Record<string, any>) => ({
      ...prevFormData,
      [sectionName]: newFormData,
    }));

    // Normalize data before comparison - remove empty objects/arrays/nulls
    const normalizeForComparison = (obj: any): any => {
      if (obj === null || obj === undefined) return undefined;
      if (Array.isArray(obj)) {
        const filtered = obj.map(normalizeForComparison).filter(v => v !== undefined);
        return filtered.length > 0 ? filtered : undefined;
      }
      if (typeof obj === 'object') {
        const result: any = {};
        for (const [key, value] of Object.entries(obj)) {
          const normalized = normalizeForComparison(value);
          if (normalized !== undefined) {
            result[key] = normalized;
          }
        }
        return Object.keys(result).length > 0 ? result : undefined;
      }
      if (obj === '') return undefined;
      return obj;
    };

    // Deep comparison using sorted JSON stringify
    const sortedStringify = (obj: any): string => {
      if (obj === null || obj === undefined) return 'null';
      if (Array.isArray(obj)) {
        return '[' + obj.map(sortedStringify).join(',') + ']';
      }
      if (typeof obj === 'object') {
        const keys = Object.keys(obj).sort();
        return (
          '{' + keys.map(k => JSON.stringify(k) + ':' + sortedStringify(obj[k])).join(',') + '}'
        );
      }
      return JSON.stringify(obj);
    };

    // Check if a value is "effectively empty" (only false/null/undefined/empty values)
    // e.g. { enabled: false } is semantically the same as no section at all
    const isEffectivelyEmpty = (obj: any): boolean => {
      if (obj === null || obj === undefined || obj === '') return true;
      if (Array.isArray(obj)) return obj.length === 0;
      if (typeof obj === 'object') {
        return Object.values(obj).every(v => isEffectivelyEmpty(v));
      }
      return false;
    };

    const normalizedNew = normalizeForComparison(newFormData);
    const normalizedOriginal = normalizeForComparison(originalData[sectionName]);

    let hasChanges: boolean;
    if (isEffectivelyEmpty(normalizedNew) && isEffectivelyEmpty(normalizedOriginal)) {
      hasChanges = false;
    } else {
      const newDataStr = sortedStringify(normalizedNew);
      const originalDataStr = sortedStringify(normalizedOriginal);
      hasChanges = newDataStr !== originalDataStr;
    }
    console.log(
      '📝 hasChanges:',
      hasChanges,
      'new:',
      normalizedNew,
      'original:',
      normalizedOriginal
    );

    if (hasChanges) {
      console.log('✅ Setting unsavedChanges to true for:', sectionName);
      setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({
        ...prevUnsavedChanges,
        [sectionName]: true,
      }));
    } else {
      console.log('❌ Setting unsavedChanges to false for:', sectionName);
      setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({
        ...prevUnsavedChanges,
        [sectionName]: false,
      }));
    }
  };

  /**
   * Restore section to original state (before changes)
   */
  const restoreSection = (sectionName: string) => {
    // Get original value, defaulting to empty array for array sections
    const arraySections = [
      'event',
      'binary_sensor',
      'local_inputs',
      'remote_inputs',
      'output',
      'output_group',
      'cover',
      'modbus_devices',
      'areas',
      'sensor',
      'virtual_energy_sensor',
      'remote_devices',
      'remote_outputs',
      'board_sensors',
    ];
    const defaultValue = arraySections.includes(sectionName) ? [] : {};
    const originalValue =
      originalData[sectionName] !== undefined ? originalData[sectionName] : defaultValue;

    setFormData((prevFormData: Record<string, any>) => ({
      ...prevFormData,
      [sectionName]: JSON.parse(JSON.stringify(originalValue)), // Deep copy
    }));
    setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({
      ...prevUnsavedChanges,
      [sectionName]: false,
    }));
  };

  /**
   * Save a specific section
   */
  const saveSection = async (sectionName: string, dataOverride?: any) => {
    console.log('🔄 saveSection called for:', sectionName);
    console.log('📦 formData[sectionName]:', formData[sectionName]);
    console.log('📦 dataOverride:', dataOverride);
    console.log('📦 unsavedChanges[sectionName]:', unsavedChanges[sectionName]);

    // Use dataOverride if provided, otherwise use formData
    const dataToUse = dataOverride !== undefined ? dataOverride : formData[sectionName];

    // Allow saving empty arrays (e.g., when user deletes all items)
    if (dataToUse === undefined || dataToUse === null) {
      console.log('❌ data is undefined/null, returning early');
      return;
    }

    // Validate boneio section - name is required if any other field is set
    if (sectionName === 'boneio') {
      const boneioData = formData[sectionName];
      const hasOtherFields = boneioData?.version || boneioData?.device_type;
      const hasName = boneioData?.name && boneioData.name.trim() !== '';

      if (hasOtherFields && !hasName) {
        console.log('❌ boneio section has version/device_type but no name');
        setSaveStatus(prev => ({ ...prev, [sectionName]: 'error' }));
        alert(
          t('boneio_config.name_required_error') ||
          'Name is required when version or device type is selected'
        );
        setTimeout(() => {
          setSaveStatus(prev => ({ ...prev, [sectionName]: 'idle' }));
        }, 3000);
        return;
      }
    }

    // Validate virtual_energy_sensor - IDs must be unique
    if (sectionName === 'virtual_energy_sensor' && Array.isArray(dataToUse)) {
      const ids = new Set<string>();
      const duplicates: string[] = [];

      for (const sensor of dataToUse) {
        // Generate ID from name if not provided (same logic as backend)
        const sensorId =
          sensor.id ||
          (sensor.name
            ? sensor.name
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, '_')
              .replace(/^_|_$/g, '')
            : '');
        if (sensorId) {
          if (ids.has(sensorId)) {
            duplicates.push(sensorId);
          } else {
            ids.add(sensorId);
          }
        }
      }

      if (duplicates.length > 0) {
        console.log('❌ Duplicate virtual_energy_sensor IDs:', duplicates);
        setSaveStatus(prev => ({ ...prev, [sectionName]: 'error' }));
        alert(
          `${t('virtual_energy_sensor.duplicate_id_error') || 'Duplicate sensor IDs detected'}: ${duplicates.join(', ')}. ${t('virtual_energy_sensor.unique_id_required') || 'Each sensor must have a unique ID or name.'}`
        );
        setTimeout(() => {
          setSaveStatus(prev => ({ ...prev, [sectionName]: 'idle' }));
        }, 3000);
        return;
      }
    }

    setSaveStatus(prev => ({ ...prev, [sectionName]: 'saving' }));

    try {
      // Find the section schema
      const sectionInfo = sections.find(s => s.name === sectionName);
      const sectionSchema = sectionInfo?.schema;

      // Special handling for mcp23017 - use data directly from form without transformations
      let minimalConfig;
      if (sectionName === 'mcp23017') {
        // For mcp23017, use data directly - form already provides clean data
        // Convert addresses to integers for backend
        minimalConfig = Array.isArray(dataToUse)
          ? dataToUse.map((entry: any) => {
            if (entry && entry.address !== undefined) {
              let addr = entry.address;
              // Convert to integer
              if (typeof addr === 'string') {
                if (addr.startsWith('0x') || addr.startsWith('0X')) {
                  addr = parseInt(addr, 16);
                } else {
                  addr = parseInt(addr, 10);
                }
              }
              // Ensure valid number
              if (isNaN(addr)) {
                addr = entry.id === 'mcp_left' ? 0x20 : 0x21;
              }
              return { id: entry.id, address: addr };
            }
            return entry;
          })
          : dataToUse;
      } else {
        // Convert form data back to original types before sending
        const dataToSend = convertFormDataToOriginalTypes(
          dataToUse,
          originalData[sectionName],
          sectionSchema
        );

        // Filter out auto-generated fields (kind, mcp_id, pin, etc.)
        const filteredData = filterAutoGeneratedFields(dataToSend);

        // Usuń pola ukryte i wartości domyślne
        minimalConfig = stripHiddenAndDefaults(
          filteredData,
          sectionSchema,
          sectionInfo?.uiSchema || {}
        );
      }

      // Send converted data to backend
      console.log('Sending config for section:', sectionName);
      console.log('Data:', minimalConfig);

      // remote_inputs is now a standard section — saved directly via PUT /api/config/remote_inputs

      // Handle composite sections — split and save each YAML key separately
      if (COMPOSITE_SECTIONS[sectionName]) {
        const yamlKeys = COMPOSITE_SECTIONS[sectionName];
        const allItems = Array.isArray(minimalConfig) ? minimalConfig : [];

        // Split items by _type back into separate arrays
        const buckets: Record<string, any[]> = {};
        for (const key of yamlKeys) {
          buckets[key] = [];
        }
        for (const item of allItems) {
          const type = item._type;
          if (type && buckets[type]) {
            const { _type, ...rest } = item;
            buckets[type].push(rest);
          }
        }

        // Save each YAML key separately
        for (const key of yamlKeys) {
          console.log(`📤 Saving composite key ${key}:`, buckets[key]);
          await axios.put(`/api/config/${key}`, buckets[key]);
        }

        // Determine reload strategy based on section type
        // local_inputs (binary_sensor + event) supports hot-reload with granular change detection
        if (sectionName === 'local_inputs') {
          // Granular reload: only reload sub-sections that actually changed
          const sectionsToReload: string[] = [];
          for (const key of yamlKeys) {
            const originalItems = (originalData[key] || []);
            const newItems = buckets[key];
            if (JSON.stringify(newItems) !== JSON.stringify(originalItems)) {
              sectionsToReload.push(key);
            }
          }

          if (sectionsToReload.length > 0) {
            try {
              setIsReloading(true);
              console.log(`🔄 Granular reload for local_inputs: ${sectionsToReload.join(', ')}`);
              await axios.post('/api/config/reload', sectionsToReload, { timeout: 30000 });
              await loadConfiguration();
              console.log(`✅ Reloaded: ${sectionsToReload.join(', ')}`);
            } catch (reloadError) {
              console.warn('⚠️ Error reloading local_inputs:', reloadError);
            } finally {
              setIsReloading(false);
            }
          }
        } else {
          // Other composite sections (e.g. board_sensors) require restart
          setRestartRequired(true);
        }

        setSaveStatus(prev => ({ ...prev, [sectionName]: 'success' }));
        setUnsavedChanges(prev => ({ ...prev, [sectionName]: false }));
        setOriginalData(prev => ({
          ...prev,
          [sectionName]: JSON.parse(JSON.stringify(dataToUse)),
        }));
        if (dataOverride !== undefined) {
          setFormData(prev => ({ ...prev, [sectionName]: JSON.parse(JSON.stringify(dataToUse)) }));
        }

        setTimeout(() => {
          setSaveStatus(prev => ({ ...prev, [sectionName]: 'idle' }));
        }, 3000);
        return;
      }

      const bodyData = JSON.stringify(minimalConfig);
      console.log('📤 Sending to backend:', bodyData);

      const response = await axios.put(`/api/config/${sectionName}`, minimalConfig);
      const result = response.data;

      if (response.status === 200) {

        setSaveStatus(prev => ({ ...prev, [sectionName]: 'success' }));
        setUnsavedChanges(prev => ({ ...prev, [sectionName]: false }));
        // Update original data to reflect the saved state (deep copy to avoid reference issues)
        setOriginalData(prev => ({
          ...prev,
          [sectionName]: JSON.parse(JSON.stringify(dataToUse)),
        }));
        // Also update formData if we used dataOverride
        if (dataOverride !== undefined) {
          setFormData(prev => ({ ...prev, [sectionName]: JSON.parse(JSON.stringify(dataToUse)) }));
        }

        // Check if backend says restart is required
        if (result.restart_required) {
          setRestartRequired(true);
        }

        // Trigger reload for sections that support hot-reload
        const reloadableSections = [
          'output_group',
          'output',
          'cover',
          'event',
          'binary_sensor',
          'modbus_devices',
          'areas',
          'sensor',
          'virtual_energy_sensor',
          'logger',
          'remote_devices',
          'remote_inputs',
          'remote_outputs',
          'template',
          'oled',
        ];
        if (reloadableSections.includes(sectionName)) {
          try {
            setIsReloading(true);
            console.log(`🔄 Triggering reload for section: ${sectionName}`);
            const reloadResponse = await axios.post('/api/config/reload', [sectionName], { timeout: 30000 });

            if (reloadResponse.status === 200) {
              console.log(`✅ Section ${sectionName} reloaded successfully`);

              // Reload entire configuration to get fresh data
              // This ensures all dependent sections are updated (e.g., output_group depends on output)
              await loadConfiguration();
              console.log(`📥 Reloaded full configuration from backend`);

              // Refresh config context so navigation updates (e.g., irrigation menu visibility)
              if (sectionName === 'template' || sectionName === 'irrigation') {
                await refreshConfig();
              }
            } else {
              console.warn(
                `⚠️ Failed to reload section ${sectionName}:`,
                reloadResponse.data
              );
            }
          } catch (reloadError) {
            console.warn(`⚠️ Error reloading section ${sectionName}:`, reloadError);
            // Don't throw - save was successful, reload is optional
          } finally {
            setIsReloading(false);
          }
        }

        // Clear success status after 3 seconds
        setTimeout(() => {
          setSaveStatus(prev => ({ ...prev, [sectionName]: 'idle' }));
        }, 3000);
      } else {
        throw new Error(`Server returned ${response.status}`);
      }
    } catch (error) {
      console.error('Error saving section:', error);
      setSaveStatus(prev => ({ ...prev, [sectionName]: 'error' }));

      // Clear error status after 5 seconds
      setTimeout(() => {
        setSaveStatus(prev => ({ ...prev, [sectionName]: 'idle' }));
      }, 5000);
    }
  };

  /**
   * Filter enum options to show only lowercase variants
   * while keeping all variants in the schema for validation
   */
  const filterEnumOptions = (enumValues: string[]): string[] => {
    if (!enumValues || enumValues.length === 0) return enumValues;

    // Group values by their lowercase version
    const groups: { [key: string]: string[] } = {};
    enumValues.forEach(value => {
      const lowerValue = value.toLowerCase();
      if (!groups[lowerValue]) {
        groups[lowerValue] = [];
      }
      groups[lowerValue].push(value);
    });

    // For each group, prefer lowercase variant
    const filtered: string[] = [];
    Object.values(groups).forEach(group => {
      if (group.length === 1) {
        // Only one variant, keep it
        filtered.push(group[0]);
      } else {
        // Multiple variants, prefer lowercase
        const lowerCase = group.find(v => v === v.toLowerCase());

        if (lowerCase) {
          filtered.push(lowerCase);
        } else {
          // Fallback to first variant
          filtered.push(group[0]);
        }
      }
    });

    return filtered;
  };

  /**
   * Normalize schema to fix common issues
   */
  const normalizeSchema = (schema: any): any => {
    const normalizeProperty = (prop: any): any => {
      if (!prop || typeof prop !== 'object') return prop;

      const normalized = { ...prop };

      // Handle oneOf with x-yaml-boolean - normalize to simple boolean
      if (normalized.oneOf && Array.isArray(normalized.oneOf)) {
        // Check if this is a boolean field with string alternatives
        const hasBooleanType = normalized.oneOf.some((option: any) => option.type === 'boolean');
        const hasYamlBooleanString = normalized.oneOf.some(
          (option: any) => option.type === 'string' && option['x-yaml-boolean'] === true
        );

        if (hasBooleanType && hasYamlBooleanString) {
          // Convert to simple boolean type
          const booleanOption = normalized.oneOf.find((option: any) => option.type === 'boolean');
          normalized.type = 'boolean';
          if (booleanOption.default !== undefined) {
            normalized.default = booleanOption.default;
          }
          // Keep title and description from the original
          delete normalized.oneOf;
        }
      }

      // Handle enum with mixed string/number types - normalize to consistent type
      if (normalized.enum && Array.isArray(normalized.enum) && normalized.type === 'string') {
        // Check if enum contains numbers that should be strings
        const hasNumbers = normalized.enum.some((val: any) => typeof val === 'number');
        const hasStrings = normalized.enum.some((val: any) => typeof val === 'string');

        if (hasNumbers && hasStrings) {
          // Convert all enum values to strings to match the string type
          normalized.enum = normalized.enum.map((val: any) => String(val));
        } else if (hasNumbers && !hasStrings) {
          // If all enum values are numbers but type is string, convert to strings
          normalized.enum = normalized.enum.map((val: any) => String(val));
        }
      }

      // Handle type arrays - convert to single type if possible
      if (Array.isArray(normalized.type)) {
        if (normalized.type.length === 1) {
          normalized.type = normalized.type[0];
        } else {
          // Take the first non-null type, but prefer structural types
          const validTypes = normalized.type.filter((t: any) => t && t !== 'null');
          if (validTypes.length > 0) {
            // Prefer object types for complex structures
            if (validTypes.includes('object')) {
              normalized.type = 'object';
            } else if (validTypes.includes('integer')) {
              normalized.type = 'integer';
            } else if (validTypes.includes('array')) {
              normalized.type = 'array';
            } else if (validTypes.includes('string') && validTypes.includes('number')) {
              // For mixed string/number, prefer string for form inputs
              normalized.type = 'string';
            } else {
              normalized.type = validTypes[0];
            }
          } else {
            normalized.type = 'string';
          }
        }
      }

      // Handle x-timeperiod fields - convert to number type for form display
      if (normalized['x-timeperiod'] === true) {
        normalized.type = 'number';
        normalized.minimum = 0;
        // Remove string-specific properties that don't apply to numbers
        delete normalized.enum;
        delete normalized.pattern;
      }

      // Filter enum options to show only user-friendly variants
      if (normalized.enum && Array.isArray(normalized.enum) && normalized.enum.length > 5) {
        // Only filter if there are many options (likely case variants)
        const allStrings = normalized.enum.every((v: string) => typeof v === 'string');
        if (allStrings) {
          normalized.enum = filterEnumOptions(normalized.enum);
        }
      }

      // Handle nested properties
      if (normalized.properties) {
        const newProperties: any = {};
        Object.keys(normalized.properties).forEach(key => {
          newProperties[key] = normalizeProperty(normalized.properties[key]);
        });
        normalized.properties = newProperties;
      }

      // Handle array items
      if (normalized.items) {
        normalized.items = normalizeProperty(normalized.items);
      }

      // Handle additionalProperties (for dynamic dicts)
      if (normalized.additionalProperties && typeof normalized.additionalProperties === 'object') {
        normalized.additionalProperties = normalizeProperty(normalized.additionalProperties);
      }

      return normalized;
    };

    return normalizeProperty(schema);
  };

  useEffect(() => {
    let isMounted = true;

    const loadConfigurationSafe = async () => {
      if (!isMounted) return;
      await loadConfiguration();
    };

    loadConfigurationSafe();

    return () => {
      isMounted = false;
    };
  }, []);

  // Effect to handle URL parameter changes
  useEffect(() => {
    // If no section in URL and we have sections loaded, navigate to first section
    if (!section && sections.length > 0) {
      navigateToSection(sections[0].name);
    }
    // If section in URL doesn't exist in loaded sections, navigate to first section
    else if (section && sections.length > 0 && !sections.find(s => s.name === section)) {
      navigateToSection(sections[0].name);
    }
  }, [section, sections, navigateToSection]);

  // Auto-hide YAML preview when switching to a composite section
  useEffect(() => {
    if (activeSection && COMPOSITE_SECTIONS[activeSection] && showYamlPreview) {
      setShowYamlPreview(false);
    }
  }, [activeSection, showYamlPreview]);

  // Debug console.log for active section
  useEffect(() => {
    const activeSection_data = sections.find(s => s.name === activeSection);
    if (activeSection_data) {
      console.log(`=== ACTIVE SECTION: ${activeSection} ===`);
      console.log('Config data:', formData[activeSection]);
      console.log('Original schema:', activeSection_data.schema);
      console.log('Normalized schema:', activeSection_data.normalizedSchema);
      console.log('UI schema:', activeSection_data.uiSchema);
      console.log('===============================');
    }
  }, [activeSection, sections, formData]);

  const activeSection_data = sections.find(s => s.name === activeSection);
  return (
    <div className="flex flex-col lg:flex-row h-full bg-base-100 relative">
      {/* Global loading overlay - fixed to viewport */}
      {isReloading && (
        <div className="fixed inset-0 bg-base-100/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4 p-8 bg-base-200 rounded-2xl shadow-xl">
            <span className="loading loading-spinner loading-lg text-primary"></span>
            <div className="text-center">
              <p className="text-lg font-semibold text-base-content">
                {t('settings.reloading_config')}
              </p>
              <p className="text-sm text-base-content/70">{t('settings.wait_changes')}</p>
            </div>
          </div>
        </div>
      )}

      {/* Unsaved changes toast - show when there are unsaved changes and no restart required */}
      {Object.values(unsavedChanges).some(Boolean) && !restartRequired && (
        <div className="toast toast-top toast-center z-50">
          <div className="alert alert-warning shadow-lg">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="stroke-current shrink-0 h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div>
              <h3 className="font-bold">📝 {t('settings.unsaved_changes')}</h3>
              <div className="text-xs">{t('settings.click_save')}</div>
            </div>
          </div>
        </div>
      )}

      {/* Restart required toast - persistent, with restart button */}
      {restartRequired && (
        <div className="toast toast-top toast-center z-50">
          <div className="alert alert-error shadow-lg">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="stroke-current shrink-0 h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div>
              <h3 className="font-bold">⚠️ {t('settings.app_restart_required')}</h3>
              <div className="text-xs">{t('settings.config_changed')}</div>
            </div>
            <button
              className="btn btn-sm btn-warning"
              onClick={handleRestart}
              disabled={isRestarting}
            >
              {isRestarting ? (
                <>
                  <span className="loading loading-spinner loading-xs"></span>
                  {t('settings.restarting')}
                </>
              ) : (
                `🔄 ${t('settings.restart_now')}`
              )}
            </button>
          </div>
        </div>
      )}

      {/* Restarting overlay */}
      {isRestarting && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-100">
          <div className="flex flex-col items-center gap-4 p-8 bg-base-200 rounded-2xl shadow-xl">
            <span className="loading loading-spinner loading-lg text-warning"></span>
            <div className="text-center">
              <p className="text-lg font-semibold text-base-content">
                {t('settings.restarting_app')}
              </p>
              <p className="text-sm text-base-content/70">{t('settings.page_reload')}</p>
            </div>
          </div>
        </div>
      )}

      {/* Sidebar with section tabs */}
      <SettingsSidebar
        sections={sections}
        reloadSections={reloadSections}
        restartSections={restartSections}
        configSections={configSections}
        activeSection={activeSection}
        saveStatus={saveStatus}
        unsavedChanges={unsavedChanges}
        isSidebarOpen={isSidebarOpen}
        onSidebarToggle={setIsSidebarOpen}
        onNavigate={navigateToSection}
      />

      {/* Main content area */}
      <div ref={contentRef} className="flex-1 flex flex-col overflow-hidden lg:min-h-0">
        {activeSection_data && (
          <>
            {/* Header */}
            <SectionHeader
              sectionName={activeSection}
              sectionTitle={t(`sections.${activeSection}`) || activeSection_data.name}
              showYamlPreview={showYamlPreview}
              hasUnsavedChanges={
                activeSection === 'mqtt'
                  ? (unsavedChanges['mqtt'] || unsavedChanges['lox_udp'] || false)
                  : (unsavedChanges[activeSection] || false)
              }
              saveDisabled={
                activeSection === 'mqtt' && unsavedChanges['lox_udp'] && !loxFormValid
              }
              saveStatus={saveStatus[activeSection] || 'idle'}
              onToggleYamlPreview={() => setShowYamlPreview(!showYamlPreview)}
              onRestore={() => {
                restoreSection(activeSection);
                if (activeSection === 'mqtt') restoreSection('lox_udp');
              }}
              onSave={async () => {
                if (activeSection === 'mqtt') {
                  // Save both mqtt and lox_udp when in messaging protocols view
                  if (unsavedChanges['mqtt']) await saveSection('mqtt');
                  if (unsavedChanges['lox_udp']) await saveSection('lox_udp');
                } else {
                  await saveSection(activeSection);
                }
              }}
              hideYamlPreview={!!COMPOSITE_SECTIONS[activeSection]}
            />

            {/* Content */}
            <div className="flex-1 overflow-hidden">
              {showYamlPreview ? (
                <div className="h-full flex">
                  {/* Form */}
                  <div className="flex-1 overflow-y-auto p-6">
                    <SectionContent
                      activeSection={activeSection}
                      activeSectionData={activeSection_data}
                      formData={formData}
                      originalData={originalData}
                      schemaLoaded={schemaLoaded}
                      editItemName={editItemName || undefined}
                      onEditItemOpened={clearEditParam}
                      onSectionChange={handleSectionChange}
                      onSaveSection={saveSection}
                      onLoxValidationChange={setLoxFormValid}
                    />
                  </div>

                  {/* YAML Preview */}
                  <div className="w-1/2 border-l border-base-content/10 bg-base-300">
                    <div className="p-4 border-b border-base-content/10">
                      <h3 className="font-semibold text-base-content">YAML Preview</h3>
                    </div>
                    <div className="p-4 h-full overflow-y-auto">
                      <pre className="text-sm font-mono text-base-content bg-base-100 p-4 rounded-lg overflow-x-auto">
                        {activeSection === 'mqtt'
                          ? [
                            `mqtt:\n${convertToYaml(formData['mqtt'], 'mqtt').split('\n').map(l => l ? `  ${l}` : '').join('\n')}`,
                            formData['lox_udp'] && Object.keys(formData['lox_udp']).length > 0
                              ? `lox_udp:\n${convertToYaml(formData['lox_udp'], 'lox_udp').split('\n').map(l => l ? `  ${l}` : '').join('\n')}`
                              : null,
                          ].filter(Boolean).join('\n')
                          : convertToYaml(formData[activeSection], activeSection)
                        }
                      </pre>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-full overflow-y-auto p-6">
                  <SectionContent
                    activeSection={activeSection}
                    activeSectionData={activeSection_data}
                    formData={formData}
                    originalData={originalData}
                    schemaLoaded={schemaLoaded}
                    editItemName={editItemName || undefined}
                    onEditItemOpened={clearEditParam}
                    onSectionChange={handleSectionChange}
                    onSaveSection={saveSection}
                    onLoxValidationChange={setLoxFormValid}
                  />
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
