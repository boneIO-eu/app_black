import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Form } from '@rjsf/shadcn';
import { RJSFSchema, UiSchema } from '@rjsf/utils';
import validator from '@rjsf/validator-ajv8';
import { FaSave, FaEye, FaEyeSlash, FaCheck, FaExclamationTriangle } from 'react-icons/fa';
import ArrayTableWidget from './ArrayTableWidget';
import { getUiSchema } from './helpers/uiSchema';
import { convertFormDataToOriginalTypes, stripHiddenAndDefaults, convertTimeperiodToMilliseconds } from '@/components/UISettings/helpers/configSchemaUtils';

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
  schema: RJSFSchema;
  normalizedSchema: RJSFSchema;
  uiSchema: UiSchema;
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

  // Get active section from URL parameter or default to first section
  const activeSection = section || 'mqtt';
  
  // Function to navigate to a section
  const navigateToSection = (sectionName: string) => {
    navigate(`/settings/${sectionName}`);
  };

  // Main configuration sections
  const configSections = [
    { name: 'mqtt', title: 'MQTT', icon: '📡' },
    { name: 'web', title: 'Web Server', icon: '🌐' },
    { name: 'logger', title: 'Logger', icon: '📝' },
    { name: 'boneio', title: 'BoneIO', icon: '🔧' },
    // { name: 'oled', title: 'OLED Display', icon: '📺' },
    { name: 'modbus', title: 'Modbus', icon: '🔌' },
    { name: 'modbus_devices', title: 'Modbus Devices', icon: '📱' },
    { name: 'modbus_sensors', title: 'Modbus Sensors', icon: '📊' },
    // { name: 'lm75', title: 'LM75 Sensors', icon: '🌡️' },
    // { name: 'ina219', title: 'INA219 Sensors', icon: '⚡' },
    // { name: 'mcp23017', title: 'MCP23017', icon: '🔗' },
    // { name: 'mcp9808', title: 'MCP9808', icon: '🌡️' },
    // { name: 'pcf8575', title: 'PCF8575', icon: '🔗' },
    // { name: 'pca9685', title: 'PCA9685', icon: '📡' },
    // { name: 'ds2482', title: 'DS2482', icon: '🔗' },
    // { name: 'dallas', title: 'Dallas Sensors', icon: '🌡️' },
    // { name: 'adc', title: 'ADC', icon: '📈' },
    { name: 'binary_sensor', title: 'Binary Sensors', icon: '🔘' },
    { name: 'sensor', title: 'Sensors', icon: '📊' },
    { name: 'output', title: 'Outputs', icon: '💡' },
    { name: 'output_group', title: 'Output Groups', icon: '🔗' },
    { name: 'cover', title: 'Covers', icon: '🚪' },
    { name: 'event', title: 'Events', icon: '⚡' },
  ];


 

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
   * Load configuration and schemas
   */
  const loadConfiguration = useCallback(async () => {
    try {
      // Load parsed config from backend (handles !include automatically)
      const configResponse = await fetch('/api/config');
      const configContent = await configResponse.json();
      
      // Load main schema
      const isDevelopment = import.meta.env.DEV;
      const mainSchemaResponse = await fetch(isDevelopment ? '/schem/config.schema.json' : '/schema/config.schema.json');
      const mainSchema = await mainSchemaResponse.json();
      
      // Convert data to match schema types for form display
      const configData = configContent?.config || {};
      const convertedFormData = convertDataToSchemaTypes(configData, mainSchema);
      setOriginalData(convertedFormData);
      setFormData(convertedFormData);

      // Create sections based on available schemas and data
      const loadedSections: ConfigSection[] = [];
      
      for (const sectionConfig of configSections) {
        try {
          // Try to load section-specific schema
          let sectionSchema: RJSFSchema;
          try {
            // Extract the section schema from the nested structure
            sectionSchema = mainSchema.properties?.[sectionConfig.name] || mainSchema;
            
            if (isDevelopment) {
              console.log(`✅ Loaded schema for ${sectionConfig.name} from Vite static files`);
            }
          } catch {
            // Fallback to main schema property
            sectionSchema = mainSchema.properties?.[sectionConfig.name] || { type: 'object' };
            console.warn(`⚠️ Using fallback schema for ${sectionConfig.name}`);
          }

          const normalizedSchema = normalizeSchema(sectionSchema);
          
          console.log("AHA", configData)
          loadedSections.push({
            name: sectionConfig.name,
            schema: sectionSchema,
            normalizedSchema: normalizedSchema,
            uiSchema: getUiSchema(sectionConfig.name),
            data: configData[sectionConfig.name] || {},
          });
        } catch (error) {
          console.warn(`Could not load schema for section ${sectionConfig.name}:`, error);
        }
      }

      setSections(loadedSections);
    } catch (error) {
      console.error('Error loading configuration:', error);
    }
  }, []);

  /**
   * Handle form data change for a section
   */
  const handleSectionChange = (sectionName: string, newFormData: any) => {
    setFormData((prevFormData: Record<string, any>) => ({ ...prevFormData, [sectionName]: newFormData }));
    console.log("handleSectionChange", sectionName, newFormData)
    
    // Compare with original data to determine if there are unsaved changes
    if (JSON.stringify(newFormData) !== JSON.stringify(originalData[sectionName])) {
      console.log("unsaved changed")
      setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({ ...prevUnsavedChanges, [sectionName]: true }));
    } else {
      console.log("saved")
      setUnsavedChanges((prevUnsavedChanges: Record<string, boolean>) => ({ ...prevUnsavedChanges, [sectionName]: false }));
    }
  };


  /**
   * Save a specific section
   */
  const saveSection = async (sectionName: string) => {
    if (!formData[sectionName]) return;

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
      
      // Usuń pola ukryte i wartości domyślne
      const minimalConfig = stripHiddenAndDefaults(
        dataToSend,
        sectionSchema,
        sectionInfo?.uiSchema || {}
      );
      
      // Send converted data to backend
      console.log("I'd like to send")
      console.log(minimalConfig)
      // const response = await fetch(`/api/config/${sectionName}`, {
      //   method: 'PUT',
      //   headers: {
      //     'Content-Type': 'application/json',
      //   },
      //   body: JSON.stringify(minimalConfig),
      // });
      
      // if (response.status === 200) {
      //   setSaveStatus(prev => ({ ...prev, [sectionName]: 'success' }));
      //   setUnsavedChanges(prev => ({ ...prev, [sectionName]: false }));
      //   // Update original data to reflect the saved state
      //   setOriginalData(prev => ({ ...prev, [sectionName]: formData[sectionName] }));
        
      //   // Clear success status after 3 seconds
      //   setTimeout(() => {
      //     setSaveStatus(prev => ({ ...prev, [sectionName]: 'idle' }));
      //   }, 3000);
      // }
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
  const normalizeSchema = (schema: RJSFSchema): RJSFSchema => {
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
    <div className="flex h-full bg-base-100">
      {/* Sidebar with section tabs */}
      <div className="w-80 bg-base-200 border-r border-base-content/10 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-xl font-bold text-base-content mb-4">Configuration Sections</h2>
          <div className="space-y-2">
            {sections.map((section) => {
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
                    {(activeSection === 'event' || activeSection === 'binary_sensor') ? (
                      <ArrayTableWidget
                        value={formData[activeSection] || []}
                        uiSchema={activeSection_data.uiSchema.items}
                        onChange={(newData) => handleSectionChange(activeSection, newData)}
                        schema={activeSection_data.normalizedSchema}
                        title={activeSection === 'binary_sensor' ? 'Binary Sensors' : 'Events'}
                      />
                    ) : (
                      <Form
                        schema={activeSection_data.normalizedSchema}
                        uiSchema={activeSection_data.uiSchema}
                        formData={formData[activeSection]}
                        validator={validator}
                        onChange={({ formData }) => handleSectionChange(activeSection, formData)}
                        onSubmit={() => saveSection(activeSection)}
                        className="space-y-4"
                      >
                        <div></div> {/* Hide default submit button */}
                      </Form>
                    )}
                  </div>
                  
                  {/* YAML Preview */}
                  <div className="w-1/2 border-l border-base-content/10 bg-base-300">
                    <div className="p-4 border-b border-base-content/10">
                      <h3 className="font-semibold text-base-content">YAML Preview</h3>
                    </div>
                    <div className="p-4 h-full overflow-y-auto">
                      <pre className="text-sm font-mono text-base-content bg-base-100 p-4 rounded-lg overflow-x-auto">
                        {JSON.stringify(formData[activeSection], null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-full overflow-y-auto p-6">
                  {(activeSection === 'event' || activeSection === 'binary_sensor') ? (
                    <ArrayTableWidget
                      value={formData[activeSection] || []}
                      uiSchema={activeSection_data.uiSchema.items}
                      onChange={(newData) => handleSectionChange(activeSection, newData)}
                      schema={activeSection_data.normalizedSchema}
                      title={activeSection === 'binary_sensor' ? 'Binary Sensors' : 'Events'}
                    />
                  ) : (
                    <Form
                      schema={activeSection_data.normalizedSchema}
                      uiSchema={activeSection_data.uiSchema}
                      formData={formData[activeSection]}
                      validator={validator}
                      onChange={({ formData }) => handleSectionChange(activeSection, formData)}
                      onSubmit={() => saveSection(activeSection)}
                      className="space-y-4"
                    >
                      <div></div> {/* Hide default submit button */}
                    </Form>
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