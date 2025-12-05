import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import * as yaml from 'js-yaml';
import { FaSave, FaEye, FaEyeSlash, FaCheck, FaExclamationTriangle, FaUndo } from 'react-icons/fa';
import ArrayTableWidget from './ArrayTableWidget';
import { convertFormDataToOriginalTypes, stripHiddenAndDefaults, convertTimeperiodToMilliseconds } from '@/components/UISettings/helpers/configSchemaUtils';
// Custom forms for simple sections (replacing RJSF)
import BoneIOForm from './BoneIOForm';
import MqttForm from './MqttForm';
import WebServerForm from './WebServerForm';
import ModbusForm from './ModbusForm';
import LoggerForm from './LoggerForm';

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
  const navigate = useNavigate();
  const [sections, setSections] = useState<ConfigSection[]>([]);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [originalData, setOriginalData] = useState<Record<string, any>>({});
  const [showYamlPreview, setShowYamlPreview] = useState(false);
  const [saveStatus, setSaveStatus] = useState<{ [key: string]: 'idle' | 'saving' | 'success' | 'error' }>({});
  const [unsavedChanges, setUnsavedChanges] = useState<{ [key: string]: boolean }>({});
  const [isReloading, setIsReloading] = useState(false);
  const [restartRequired, setRestartRequired] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_schemaLoaded, setSchemaLoaded] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_schemaCache, setSchemaCache] = useState<any>(null);

  // Get active section from URL parameter or default to first section
  const activeSection = section || 'mqtt';
  
  // Function to navigate to a section
  const navigateToSection = (sectionName: string) => {
    navigate(`/settings/${sectionName}`);
  };

  // Sections that only require reload (hot reload supported)
  const reloadSections = [
    { name: 'areas', title: 'Areas/Rooms', icon: '🏠' },
    { name: 'binary_sensor', title: 'Binary Sensors', icon: '🔘' },
    { name: 'event', title: 'Events', icon: '⚡' },
    { name: 'output', title: 'Outputs', icon: '💡' },
    { name: 'output_group', title: 'Output Groups', icon: '🔗' },
    { name: 'cover', title: 'Covers', icon: '🚪' },
    { name: 'modbus_devices', title: 'Modbus Devices', icon: '📱' },
    { name: 'logger', title: 'Logger', icon: '📝' },
  ];

  // Sections that require full restart
  const restartSections = [
    { name: 'boneio', title: 'boneIO', icon: '🔧' },
    { name: 'mqtt', title: 'MQTT', icon: '📡' },
    { name: 'web', title: 'Web Server', icon: '🌐' },
    { name: 'modbus', title: 'Modbus', icon: '🔌' },
    // { name: 'oled', title: 'OLED Display', icon: '📺' },
    // { name: 'lm75', title: 'LM75 Sensors', icon: '🌡️' },
    // { name: 'ina219', title: 'INA219 Sensors', icon: '⚡' },
    // { name: 'mcp23017', title: 'MCP23017', icon: '🔗' },
    // { name: 'mcp9808', title: 'MCP9808', icon: '🌡️' },
    // { name: 'pcf8575', title: 'PCF8575', icon: '🔗' },
    // { name: 'pca9685', title: 'PCA9685', icon: '📡' },
    // { name: 'ds2482', title: 'DS2482', icon: '🔗' },
    // { name: 'dallas', title: 'Dallas Sensors', icon: '🌡️' },
    // { name: 'adc', title: 'ADC', icon: '📈' },
    // { name: 'sensor', title: 'Sensors', icon: '📊' },
  ];

  // Combined for lookup
  const configSections = [...reloadSections, ...restartSections];


 

  /**
   * Convert data to match schema types (for form display)
   */
  const convertDataToSchemaTypes = (data: Record<string, any>, schema: any): Record<string, any> => {
    console.log("convertDataToSchemaTypes called with:", { data, schema });
    
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
          
          console.log(`Processing key: ${key}, currentValue:`, currentValue, `propSchema:`, propSchema);
          
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
            console.log(`✓ Converted timeperiod ${key}:`, currentValue, '→', milliseconds, 'ms');
          }
          // Convert number to string if schema expects string with enum
          else if (propSchema?.type === 'string' && propSchema?.enum && typeof currentValue === 'number') {
            const stringValue = String(currentValue);
            console.log(`Converting ${key}: ${currentValue} (${typeof currentValue}) → ${stringValue} (${typeof stringValue})`);
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
    
    console.log("convertDataToSchemaTypes result:", converted);
    return converted;
  };

  /**
   * Load configuration and schemas (lazy loading - config first, schema in background)
   */
  const loadConfiguration = useCallback(async () => {
    try {
      // Check restart status from backend (non-blocking)
      fetch('/api/status/restart')
        .then(r => r.ok ? r.json() : null)
        .then(status => {
          if (status?.restart_required) setRestartRequired(true);
        })
        .catch(() => {});
      
      // Load parsed config from backend FIRST (fast, small)
      const configResponse = await fetch('/api/config');
      const configContent = await configResponse.json();
      const configData = configContent?.config || {};
      
      // Set form data immediately WITHOUT schema conversion (UI shows instantly)
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
      const isDevelopment = import.meta.env.DEV;
      fetch(isDevelopment ? '/schem/config.schema.json' : '/schema/config.schema.json')
        .then(r => r.json())
        .then(mainSchema => {
          setSchemaCache(mainSchema);
          setSchemaLoaded(true);
          
          // Update sections with proper schemas
          const loadedSections: ConfigSection[] = configSections.map(sectionConfig => {
            const sectionSchema = mainSchema.properties?.[sectionConfig.name] || { type: 'object' };
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
          
          console.log('✅ Schema loaded in background');
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
            const { kind, mcp_id, pca_id, pcf_id, pin,...rest } = item;
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
          if (cleanedValue !== null && 
              cleanedValue !== undefined && 
              cleanedValue !== '' &&
              !(Array.isArray(cleanedValue) && cleanedValue.length === 0) &&
              !(typeof cleanedValue === 'object' && Object.keys(cleanedValue).length === 0)) {
            cleaned[key] = cleanedValue;
          }
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
  const convertToYaml = useCallback((data: any, sectionName?: string): string => {
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
  }, [filterAutoGeneratedFields, sections]);

  /**
   * Handle form data change for a section
   */
  const handleSectionChange = (sectionName: string, newFormData: any) => {
    console.log("📝 handleSectionChange called for:", sectionName);
    
    setFormData((prevFormData: Record<string, any>) => ({ ...prevFormData, [sectionName]: newFormData }));
    
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
        return '{' + keys.map(k => JSON.stringify(k) + ':' + sortedStringify(obj[k])).join(',') + '}';
      }
      return JSON.stringify(obj);
    };
    
    const normalizedNew = normalizeForComparison(newFormData);
    const normalizedOriginal = normalizeForComparison(originalData[sectionName]);
    const newDataStr = sortedStringify(normalizedNew);
    const originalDataStr = sortedStringify(normalizedOriginal);
    const hasChanges = newDataStr !== originalDataStr;
    console.log("📝 hasChanges:", hasChanges, "new:", normalizedNew, "original:", normalizedOriginal);
    
    if (hasChanges) {
      console.log("✅ Setting unsavedChanges to true for:", sectionName);
      setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({ ...prevUnsavedChanges, [sectionName]: true }));
    } else {
      console.log("❌ Setting unsavedChanges to false for:", sectionName);
      setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({ ...prevUnsavedChanges, [sectionName]: false }));
    }
  };


  /**
   * Restore section to original state (before changes)
   */
  const restoreSection = (sectionName: string) => {
    if (originalData[sectionName]) {
      setFormData((prevFormData: Record<string, any>) => ({ 
        ...prevFormData, 
        [sectionName]: JSON.parse(JSON.stringify(originalData[sectionName])) // Deep copy
      }));
      setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({ 
        ...prevUnsavedChanges, 
        [sectionName]: false 
      }));
    }
  };

  /**
   * Save a specific section
   */
  const saveSection = async (sectionName: string) => {
    console.log('🔄 saveSection called for:', sectionName);
    console.log('📦 formData[sectionName]:', formData[sectionName]);
    console.log('📦 unsavedChanges[sectionName]:', unsavedChanges[sectionName]);
    
    // Allow saving empty arrays (e.g., when user deletes all items)
    if (formData[sectionName] === undefined || formData[sectionName] === null) {
      console.log('❌ formData is undefined/null, returning early');
      return;
    }

    setSaveStatus(prev => ({ ...prev, [sectionName]: 'saving' }));

    try {
      // Find the section schema
      const sectionInfo = sections.find(s => s.name === sectionName);
      const sectionSchema = sectionInfo?.schema;
      
      // Convert form data back to original types before sending
      const dataToSend = convertFormDataToOriginalTypes(
        formData[sectionName], 
        originalData[sectionName],
        sectionSchema
      );
      
      // Filter out auto-generated fields (kind, mcp_id, pin, etc.)
      const filteredData = filterAutoGeneratedFields(dataToSend);
      
      // Usuń pola ukryte i wartości domyślne
      const minimalConfig = stripHiddenAndDefaults(
        filteredData,
        sectionSchema,
        sectionInfo?.uiSchema || {}
      );
      
      // Send converted data to backend
      console.log("Sending config for section:", sectionName);
      console.log("Data:", minimalConfig);
      
      const bodyData = JSON.stringify(minimalConfig);
      console.log("📤 Sending to backend:", bodyData);
      
      const response = await fetch(`/api/config/${sectionName}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: bodyData,
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error("❌ Backend error response:", errorText);
        throw new Error(`Server returned ${response.status}: ${errorText}`);
      }
      
      if (response.status === 200) {
        const result = await response.json();
        
        setSaveStatus(prev => ({ ...prev, [sectionName]: 'success' }));
        setUnsavedChanges(prev => ({ ...prev, [sectionName]: false }));
        // Update original data to reflect the saved state (deep copy to avoid reference issues)
        setOriginalData(prev => ({ ...prev, [sectionName]: JSON.parse(JSON.stringify(formData[sectionName])) }));
        
        // Check if backend says restart is required
        if (result.restart_required) {
          setRestartRequired(true);
        }
        
        // Trigger reload for sections that support hot-reload
        const reloadableSections = ['output_group', 'output', 'cover', 'event', 'binary_sensor', 'modbus_devices', 'areas'];
        if (reloadableSections.includes(sectionName)) {
          try {
            setIsReloading(true);
            console.log(`🔄 Triggering reload for section: ${sectionName}`);
            const reloadResponse = await fetch('/api/config/reload', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify([sectionName]),
            });
            
            if (reloadResponse.ok) {
              console.log(`✅ Section ${sectionName} reloaded successfully`);
              
              // Reload entire configuration to get fresh data
              // This ensures all dependent sections are updated (e.g., output_group depends on output)
              await loadConfiguration();
              console.log(`📥 Reloaded full configuration from backend`);
            } else {
              console.warn(`⚠️ Failed to reload section ${sectionName}:`, await reloadResponse.text());
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
        const hasYamlBooleanString = normalized.oneOf.some((option: any) => 
          option.type === 'string' && option['x-yaml-boolean'] === true
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
    <div className="flex h-full bg-base-100 relative">
      {/* Global loading overlay - fixed to viewport */}
      {isReloading && (
        <div className="fixed inset-0 bg-base-100/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4 p-8 bg-base-200 rounded-2xl shadow-xl">
            <span className="loading loading-spinner loading-lg text-primary"></span>
            <div className="text-center">
              <p className="text-lg font-semibold text-base-content">Reloading configuration...</p>
              <p className="text-sm text-base-content/70">Please wait while changes are applied</p>
            </div>
          </div>
        </div>
      )}
      
      {/* Restart required toast - persistent, cannot be dismissed */}
      {restartRequired && (
        <div className="toast toast-top toast-center z-50">
          <div className="alert alert-error shadow-lg">
            <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <h3 className="font-bold">⚠️ App restart required</h3>
              <div className="text-xs">Configuration was changed. Restart the application to apply changes.</div>
            </div>
          </div>
        </div>
      )}

      {/* Sidebar with section tabs */}
      <div className="w-80 bg-base-200 border-r border-base-content/10 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-xl font-bold text-base-content mb-4">Configuration Sections</h2>
          
          {/* Reload sections - hot reload supported */}
          <div className="space-y-2 mb-4">
            {sections
              .filter(s => reloadSections.some(rs => rs.name === s.name))
              .map((section) => {
                const sectionConfig = configSections.find(s => s.name === section.name);
                const status = saveStatus[section.name];
                
                return (
                  <button
                    key={section.name}
                    onClick={() => navigateToSection(section.name)}
                    className={`w-full text-left p-3 rounded-lg transition-all duration-200 flex items-center justify-between group ${
                      activeSection === section.name
                        ? 'bg-primary text-primary-content shadow-md'
                        : 'bg-base-100 hover:bg-base-300 text-base-content'
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <span className="text-lg">{sectionConfig?.icon || '⚙️'}</span>
                      <div>
                        <div className="font-medium">{sectionConfig?.title}</div>
                        <div className="text-xs opacity-70">{section.name}</div>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      {unsavedChanges[section.name] && (
                        <div className="w-2 h-2 bg-warning rounded-full" title="Unsaved changes"></div>
                      )}
                      {status === 'success' && (
                        <FaCheck className="text-success" title="Saved successfully" />
                      )}
                      {status === 'error' && (
                        <FaExclamationTriangle className="text-error" title="Save failed" />
                      )}
                      {status === 'saving' && (
                        <div className="loading loading-spinner loading-xs"></div>
                      )}
                    </div>
                  </button>
                );
              })}
          </div>

          {/* Separator */}
          <div className="divider text-xs text-warning font-medium my-2">
            ⚠️ Restart required for sections below
          </div>

          {/* Restart sections */}
          <div className="space-y-2">
            {sections
              .filter(s => restartSections.some(rs => rs.name === s.name))
              .map((section) => {
                const sectionConfig = configSections.find(s => s.name === section.name);
                const status = saveStatus[section.name];
                
                return (
                  <button
                    key={section.name}
                    onClick={() => navigateToSection(section.name)}
                    className={`w-full text-left p-3 rounded-lg transition-all duration-200 flex items-center justify-between group ${
                      activeSection === section.name
                        ? 'bg-primary text-primary-content shadow-md'
                        : 'bg-base-100 hover:bg-base-300 text-base-content'
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <span className="text-lg">{sectionConfig?.icon || '⚙️'}</span>
                      <div>
                        <div className="font-medium">{sectionConfig?.title}</div>
                        <div className="text-xs opacity-70">{section.name}</div>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      {unsavedChanges[section.name] && (
                        <div className="w-2 h-2 bg-warning rounded-full" title="Unsaved changes"></div>
                      )}
                      {status === 'success' && (
                        <FaCheck className="text-success" title="Saved successfully" />
                      )}
                      {status === 'error' && (
                        <FaExclamationTriangle className="text-error" title="Save failed" />
                      )}
                      {status === 'saving' && (
                        <div className="loading loading-spinner loading-xs"></div>
                      )}
                    </div>
                  </button>
                );
              })}
          </div>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {activeSection_data && (
          <>
            {/* Header */}
            <div className="bg-base-200 border-b border-base-content/10 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-2xl font-bold text-base-content">
                    {activeSection_data.name}
                  </h1>
                  <p className="text-sm text-base-content/70 mt-1">
                    Configure {activeSection_data.name} settings
                  </p>
                </div>
                <div className="flex items-center space-x-3">
                  <button
                    onClick={() => setShowYamlPreview(!showYamlPreview)}
                    className="btn btn-ghost btn-sm"
                    title={showYamlPreview ? "Hide YAML preview" : "Show YAML preview"}
                  >
                    {showYamlPreview ? <FaEyeSlash /> : <FaEye />}
                    YAML
                  </button>
                  {unsavedChanges[activeSection] && (
                    <button
                      onClick={() => restoreSection(activeSection)}
                      className="btn btn-warning btn-sm"
                      title="Restore to last saved state"
                    >
                      <FaUndo />
                      Restore
                    </button>
                  )}
                  <button
                    onClick={() => saveSection(activeSection)}
                    disabled={!unsavedChanges[activeSection]}
                    className="btn btn-primary btn-sm"
                  >
                    {saveStatus[activeSection] === 'saving' ? (
                      <div className="loading loading-spinner loading-xs"></div>
                    ) : (
                      <FaSave />
                    )}
                    Save {activeSection_data.name}
                  </button>
                </div>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-hidden">
              {showYamlPreview ? (
                <div className="h-full flex">
                  {/* Form */}
                  <div className="flex-1 overflow-y-auto p-6">
                    {(activeSection === 'event' || activeSection === 'binary_sensor' || activeSection === 'output' || activeSection === 'output_group' || activeSection === 'cover' || activeSection === 'modbus_devices' || activeSection === 'areas') ? (
                      <ArrayTableWidget
                        value={formData[activeSection] || []}
                        uiSchema={activeSection_data.uiSchema.items}
                        onChange={(newData) => handleSectionChange(activeSection, newData)}
                        schema={activeSection_data.normalizedSchema}
                        sectionType={activeSection as 'binary_sensor' | 'event' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'other'}
                        deviceType={formData.boneio?.device_type}
                        allBinarySensors={formData.binary_sensor || []}
                        allEvents={formData.event || []}
                        allOutputs={formData.output || []}
                        allOutputGroups={formData.output_group || []}
                        allAreas={formData.areas || []}
                        title={
                          activeSection === 'binary_sensor' ? 'Binary Sensors' : 
                          activeSection === 'event' ? 'Events' : 
                          activeSection === 'output' ? 'Outputs' :
                          activeSection === 'output_group' ? 'Output Groups' :
                          activeSection === 'cover' ? 'Covers' :
                          activeSection === 'areas' ? 'Areas/Rooms' :
                          'Modbus Devices'
                        }
                      />
                    ) : (
                      // Custom forms for simple dict sections
                      activeSection === 'boneio' ? (
                        <BoneIOForm
                          data={formData[activeSection]}
                          onChange={(data) => handleSectionChange(activeSection, data)}
                        />
                      ) : activeSection === 'mqtt' ? (
                        <MqttForm
                          data={formData[activeSection]}
                          onChange={(data) => handleSectionChange(activeSection, data)}
                        />
                      ) : activeSection === 'web' ? (
                        <WebServerForm
                          data={formData[activeSection]}
                          onChange={(data) => handleSectionChange(activeSection, data)}
                        />
                      ) : activeSection === 'modbus' ? (
                        <ModbusForm
                          data={formData[activeSection]}
                          onChange={(data) => handleSectionChange(activeSection, data)}
                        />
                      ) : activeSection === 'logger' ? (
                        <LoggerForm
                          data={formData[activeSection]}
                          onChange={(data) => handleSectionChange(activeSection, data)}
                        />
                      ) : (
                        <div className="alert alert-warning">
                          <span>No form available for section: {activeSection}</span>
                        </div>
                      )
                    )}
                  </div>
                  
                  {/* YAML Preview */}
                  <div className="w-1/2 border-l border-base-content/10 bg-base-300">
                    <div className="p-4 border-b border-base-content/10">
                      <h3 className="font-semibold text-base-content">YAML Preview</h3>
                    </div>
                    <div className="p-4 h-full overflow-y-auto">
                      <pre className="text-sm font-mono text-base-content bg-base-100 p-4 rounded-lg overflow-x-auto">
                        {convertToYaml(formData[activeSection], activeSection)}
                      </pre>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-full overflow-y-auto p-6">
                  {(activeSection === 'event' || activeSection === 'binary_sensor' || activeSection === 'output' || activeSection === 'output_group' || activeSection === 'cover' || activeSection === 'modbus_devices' || activeSection === 'areas') ? (
                    <ArrayTableWidget
                      value={formData[activeSection] || []}
                      uiSchema={activeSection_data.uiSchema.items}
                      onChange={(newData) => handleSectionChange(activeSection, newData)}
                      schema={activeSection_data.normalizedSchema}
                      sectionType={activeSection as 'binary_sensor' | 'event' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'other'}
                      deviceType={formData.boneio?.device_type}
                      allBinarySensors={formData.binary_sensor || []}
                      allEvents={formData.event || []}
                      allOutputs={formData.output || []}
                      allOutputGroups={formData.output_group || []}
                      allAreas={formData.areas || []}
                      title={
                        activeSection === 'binary_sensor' ? 'Binary Sensors' : 
                        activeSection === 'event' ? 'Events' : 
                        activeSection === 'output' ? 'Outputs' :
                        activeSection === 'output_group' ? 'Output Groups' :
                        activeSection === 'cover' ? 'Covers' :
                        activeSection === 'areas' ? 'Areas/Rooms' :
                        'Modbus Devices'
                      }
                    />
                  ) : (
                    // Custom forms for simple dict sections
                    activeSection === 'boneio' ? (
                      <BoneIOForm
                        data={formData[activeSection]}
                        onChange={(data) => handleSectionChange(activeSection, data)}
                      />
                    ) : activeSection === 'mqtt' ? (
                      <MqttForm
                        data={formData[activeSection]}
                        onChange={(data) => handleSectionChange(activeSection, data)}
                      />
                    ) : activeSection === 'web' ? (
                      <WebServerForm
                        data={formData[activeSection]}
                        onChange={(data) => handleSectionChange(activeSection, data)}
                      />
                    ) : activeSection === 'modbus' ? (
                      <ModbusForm
                        data={formData[activeSection]}
                        onChange={(data) => handleSectionChange(activeSection, data)}
                      />
                    ) : activeSection === 'logger' ? (
                      <LoggerForm
                        data={formData[activeSection]}
                        onChange={(data) => handleSectionChange(activeSection, data)}
                      />
                    ) : (
                      <div className="alert alert-warning">
                        <span>No form available for section: {activeSection}</span>
                      </div>
                    )
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}