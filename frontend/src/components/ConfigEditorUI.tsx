import { useState, useEffect } from 'react';
import axios from '@/api/axios';
import * as yaml from 'js-yaml';
import { FaCheck, FaTimes, FaSave, FaPlus, FaChevronDown, FaChevronRight } from 'react-icons/fa';

interface ConfigSection {
  title: string;
  key: string;
  description?: string;
  fields: ConfigField[];
  expanded?: boolean;
  isArray?: boolean;
  items?: ConfigSection[];
}

interface ConfigField {
  key: string;
  title: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'object' | 'array';
  description?: string;
  default?: any;
  required?: boolean;
  options?: { value: string; label: string }[];
  value?: any;
  fields?: ConfigField[];
  arrayItemType?: ConfigField;
  validation?: {
    min?: number;
    max?: number;
    pattern?: string;
    message?: string;
  };
}

export default function ConfigEditorUI() {
  const [config, setConfig] = useState<any>(null);
  const [configSections, setConfigSections] = useState<ConfigSection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [activeTab, setActiveTab] = useState<'form' | 'yaml'>('form');
  const [yamlView, setYamlView] = useState<string>('');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      // Load the flattened config
      const configResponse = await axios.get('/api/config/flattened');
      const config = configResponse.data.config;
      setConfig(config);
      
      // Get the schema structure to build the UI
      const schemaResponse = await axios.get('/schema/config.schema.json');
      const schema = schemaResponse.data;
      console.log("Schema and config loaded:", { schema: schema, config });
      
      // Build config sections from schema and config data
      const sections = buildConfigSections(schema.properties, config);
      console.log("Built config sections:", sections);
      setConfigSections(sections);
      
      // Generate YAML view
      updateYamlView(config);
    } catch (err: any) {
      console.error('Error loading config:', err);
      setError(`Failed to load configuration: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const buildConfigSections = (schemaProperties: any, configData: any): ConfigSection[] => {
    const sections: ConfigSection[] = [];
    
    // Process each property in the schema
    if (schemaProperties) {
      Object.entries(schemaProperties).forEach(([key, propSchema]: [string, any]) => {
        const section: ConfigSection = {
          title: propSchema.title || key,
          key,
          description: propSchema.description,
          fields: [],
          expanded: false
        };
        
        console.log("PROP", propSchema)
        
        // If this is an object with properties
        if (propSchema.type && propSchema.type.includes && propSchema.type.includes('object') && propSchema.properties) {
          section.fields = buildConfigFields(propSchema, configData?.[key] || {}, key);
        }
        // If this is an array of objects
        else if (propSchema.type && propSchema.type.includes && propSchema.type.includes('array') && propSchema.items) {
          section.isArray = true;
          const items = configData?.[key] || [];
          section.items = items.map((item: any, itemIndex: number) => ({
            title: `${key} ${itemIndex + 1}`,
            key: `${key}[${itemIndex}]`,
            fields: buildConfigFields(propSchema.items, item, `${key}[${itemIndex}]`),
            expanded: false
          }));
        }
        
        sections.push(section);
      });
    }
    
    return sections;
  };

  const buildConfigFields = (schema: any, data: any, parentKey: string): ConfigField[] => {
    const fields: ConfigField[] = [];
    
    if (schema.properties) {
      Object.entries(schema.properties).forEach(([key, propSchema]: [string, any]) => {
        const fullKey = `${parentKey}.${key}`;
        const field: ConfigField = {
          key: fullKey,
          title: propSchema.title || key,
          type: mapSchemaTypeToFieldType(propSchema),
          description: propSchema.description,
          default: propSchema.default,
          required: schema.required?.includes(key),
          value: data[key] !== undefined ? data[key] : propSchema.default
        };
        
        // Handle select options
        if (propSchema.enum) {
          field.type = 'select';
          field.options = propSchema.enum.map((value: string) => ({
            value,
            label: value
          }));
        }
        
        // Handle nested objects
        if (propSchema.type && propSchema.type.includes && propSchema.type.includes('object') && propSchema.properties) {
          field.type = 'object';
          field.fields = buildConfigFields(propSchema, data[key] || {}, fullKey);
        }
        
        // Handle arrays
        if (propSchema.type && propSchema.type.includes && propSchema.type.includes('array')) {
          field.type = 'array';
          if (propSchema.items) {
            field.arrayItemType = {
              type: mapSchemaTypeToFieldType(propSchema.items),
              key: `${fullKey}[]`,
              title: 'Item'
            };
            
            // If array items are objects with properties
            if (propSchema.items.type && propSchema.items.type.includes && propSchema.items.type.includes('object') && propSchema.items.properties) {
              field.arrayItemType.type = 'object';
              field.arrayItemType.fields = [];
            }
          }
        }
        
        // Add validation
        if (propSchema.minimum !== undefined || propSchema.maximum !== undefined || propSchema.pattern) {
          field.validation = {
            min: propSchema.minimum,
            max: propSchema.maximum,
            pattern: propSchema.pattern,
            message: propSchema.errorMessage
          };
        }
        
        fields.push(field);
      });
    }
    
    return fields;
  };

  const mapSchemaTypeToFieldType = (schema: any): ConfigField['type'] => {
    if (!schema.type) return 'string';
    
    // Handle array of types (e.g. ["string", "integer"])
    const type = Array.isArray(schema.type) ? schema.type[1] : schema.type;
    
    switch (type) {
      case 'integer':
      case 'number':
        return 'number';
      case 'boolean':
        return 'boolean';
      case 'array':
        return 'array';
      case 'object':
        return 'object';
      default:
        return 'string';
    }
  };

  const filterAutoGeneratedFields = (configData: any): any => {
    // Create a deep copy to avoid mutating original
    const filtered = JSON.parse(JSON.stringify(configData));
    
    // Filter outputs - remove auto-generated fields if boneio_output exists
    if (filtered.output && Array.isArray(filtered.output)) {
      filtered.output = filtered.output.map((output: any) => {
        // If boneio_output exists, remove auto-generated fields that come from predefined config
        if (output.boneio_output) {
          const { kind, mcp_id, pca_id, pcf_id, pin, ...rest } = output;
          return rest;
        }
        // Otherwise keep all fields (user manually configured them)
        return output;
      });
    }
    
    // Filter inputs - similar logic if needed
    if (filtered.input && Array.isArray(filtered.input)) {
      filtered.input = filtered.input.map((input: any) => {
        if (input.boneio_input) {
          // Remove auto-generated fields for inputs too
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
  };

  const updateYamlView = (configData: any) => {
    // Filter out auto-generated fields
    const filteredConfig = filterAutoGeneratedFields(configData);
    
    // Convert to YAML format
    try {
      const yamlString = yaml.dump(filteredConfig, {
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
      setYamlView(yamlString);
      console.log("YAML", yamlString);
    } catch (error) {
      console.error('Error converting to YAML:', error);
      // Fallback to JSON if YAML conversion fails
      setYamlView(JSON.stringify(filteredConfig, null, 2));
    }
  };
  console.log("dupa dupa dupa")

  const renderConfigForm = () => {
    if (loading) {
      return <div className="flex justify-center p-8"><div className="loading loading-spinner loading-lg"></div></div>;
    }
    
    if (error) {
      return (
        <div className="alert alert-error">
          <FaTimes className="w-6 h-6" />
          <span>{error}</span>
        </div>
      );
    }
    
    return (
      <div className="p-4">
        {configSections.map(section => (
          <div key={section.key} className="card bg-base-200 shadow-xl mb-6">
            <div className="card-body">
              <h2 className="card-title flex justify-between">
                {section.title}
                <button 
                  className="btn btn-sm btn-ghost"
                  onClick={() => toggleSectionExpand(section.key)}
                >
                  {section.expanded ? <FaChevronDown /> : <FaChevronRight />}
                </button>
              </h2>
              {section.description && <p className="text-sm opacity-70">{section.description}</p>}
              
              {section.expanded && (
                <div className="mt-4">
                  {section.isArray ? (
                    <div>
                      {section.items?.map(item => (
                        <div key={item.key} className="card bg-base-300 mb-4">
                          <div className="card-body">
                            <h3 className="font-bold">{item.title}</h3>
                            {renderFields(item.fields)}
                          </div>
                        </div>
                      ))}
                      <button className="btn btn-sm btn-primary mt-2">
                        <FaPlus className="mr-2" /> Add {section.title}
                      </button>
                    </div>
                  ) : (
                    renderFields(section.fields)
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        
        <div className="flex justify-end mt-6">
          <button 
            className={`btn btn-primary ${saveStatus === 'saving' ? 'loading' : ''}`}
            onClick={saveConfig}
            disabled={saveStatus === 'saving'}
          >
            {saveStatus !== 'saving' && <FaSave className="mr-2" />}
            Save Configuration
          </button>
        </div>
        
        {saveStatus === 'success' && (
          <div className="alert alert-success mt-4">
            <FaCheck className="w-6 h-6" />
            <span>Configuration saved successfully!</span>
          </div>
        )}
        
        {saveStatus === 'error' && (
          <div className="alert alert-error mt-4">
            <FaTimes className="w-6 h-6" />
            <span>Failed to save configuration. Please try again.</span>
          </div>
        )}
      </div>
    );
  };

  const renderFields = (fields: ConfigField[]) => {
    return (
      <div className="grid grid-cols-1 gap-4">
        {fields.map(field => (
          <div key={field.key} className="form-control">
            <label className="label">
              <span className="label-text font-medium">
                {field.title}
                {field.required && <span className="text-error">*</span>}
              </span>
            </label>
            
            {renderFieldInput(field)}
            
            {field.description && (
              <label className="label">
                <span className="label-text-alt text-xs opacity-70">{field.description}</span>
              </label>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderFieldInput = (field: ConfigField) => {
    switch (field.type) {
      case 'string':
        return (
          <input
            type="text"
            className="input  w-full"
            value={field.value || ''}
            onChange={(e) => handleFieldChange(field, e.target.value)}
            autoComplete="new-password"
          />
        );
      case 'number':
        return (
          <input
            type="number"
            className="input  w-full"
            value={field.value || ''}
            onChange={(e) => handleFieldChange(field, Number(e.target.value))}
            min={field.validation?.min}
            max={field.validation?.max}
            autoComplete="off"
          />
        );
      case 'boolean':
        return (
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={field.value || false}
            onChange={(e) => handleFieldChange(field, e.target.checked)}
            autoComplete="off"
          />
        );
      case 'select':
        return (
          <select
            className="select ed w-full"
            value={field.value || ''}
            onChange={(e) => handleFieldChange(field, e.target.value)}
            autoComplete="off"
          >
            <option value="">Select...</option>
            {field.options?.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        );
      case 'object':
        return field.fields ? (
          <div className="card bg-base-300 p-4">
            {renderFields(field.fields)}
          </div>
        ) : null;
      case 'array':
        return (
          <div className="card bg-base-300 p-4">
            {/* Array rendering would go here */}
            <p className="text-sm italic">Array editing not yet implemented</p>
          </div>
        );
      default:
        return <p>Unsupported field type: {field.type}</p>;
    }
  };

  const handleFieldChange = (field: ConfigField, value: any) => {
    // Update the field value in the config state
    const newConfig = { ...config };
    const keyPath = field.key.split('.');
    
    // Remove the first segment (parent key)
    const parentKey = keyPath.shift();
    
    // Navigate to the correct nested object
    let current = newConfig[parentKey as string];
    
    // Handle array indices in the path
    const lastKey = keyPath.pop() as string;
    
    keyPath.forEach(segment => {
      const match = segment.match(/(.+)\[(\d+)\]/);
      if (match) {
        // This is an array index notation
        const [, arrayName, indexStr] = match;
        const index = parseInt(indexStr, 10);
        current = current[arrayName][index];
      } else {
        // Regular object property
        if (!current[segment]) {
          current[segment] = {};
        }
        current = current[segment];
      }
    });
    
    // Set the value
    current[lastKey] = value;
    
    // Update state
    setConfig(newConfig);
    
    // Update YAML view
    updateYamlView(newConfig);
  };

  const toggleSectionExpand = (sectionKey: string) => {
    setConfigSections(prev => 
      prev.map(section => 
        section.key === sectionKey 
          ? { ...section, expanded: !section.expanded }
          : section
      )
    );
  };

  const saveConfig = async () => {
    setSaveStatus('saving');
    try {
      // This would need to be implemented on the backend
      await axios.post('/api/config/update', { config });
      setSaveStatus('success');
      
      // Reset status after a delay
      setTimeout(() => setSaveStatus('idle'), 3000);
    } catch (err) {
      console.error('Error saving config:', err);
      setSaveStatus('error');
      
      // Reset status after a delay
      setTimeout(() => setSaveStatus('idle'), 3000);
    }
  };

  return (
    <div className="container mx-auto">
      <div className="tabs tabs-boxed mb-6">
        <a 
          className={`tab ${activeTab === 'form' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('form')}
        >
          Form Editor
        </a>
        <a 
          className={`tab ${activeTab === 'yaml' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('yaml')}
        >
          YAML View
        </a>
      </div>
      
      {activeTab === 'form' ? (
        renderConfigForm()
      ) : (
        <div className="bg-base-300 p-4 rounded-lg">
          <pre className="whitespace-pre-wrap wrap-break-word">{yamlView}</pre>
        </div>
      )}
    </div>
  );
}
