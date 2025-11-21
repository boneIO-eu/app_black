import { RJSFSchema } from '@rjsf/utils';

/**
 * Filter schema properties based on x-dependencies
 * 
 * @param schema - The JSON Schema to filter
 * @param formData - Current form data to check dependencies against
 * @returns Filtered schema with only properties that meet their dependencies
 */
export const filterSchemaByDependencies = (
  schema: RJSFSchema,
  formData: any
): RJSFSchema => {
  if (!schema || typeof schema !== 'object') {
    return schema;
  }

  // Clone schema to avoid mutations
  const filteredSchema = { ...schema };

  // If schema has properties, filter them based on x-dependencies
  if (filteredSchema.properties && typeof filteredSchema.properties === 'object') {
    const filteredProperties: Record<string, any> = {};

    Object.keys(filteredSchema.properties).forEach((key) => {
      const propSchema = filteredSchema.properties![key];
      
      // Check if property has x-dependencies
      if (propSchema && typeof propSchema === 'object' && 'x-dependencies' in propSchema) {
        const dependencies = (propSchema as any)['x-dependencies'];
        
        // Check if all dependencies are met
        let dependenciesMet = true;
        
        if (dependencies && typeof dependencies === 'object') {
          Object.keys(dependencies).forEach((depKey) => {
            const allowedValues = dependencies[depKey];
            const currentValue = formData?.[depKey];
            
            // Check if current value is in allowed values
            if (Array.isArray(allowedValues)) {
              // Normalize values for comparison (lowercase)
              const normalizedAllowed = allowedValues.map((v: any) => 
                typeof v === 'string' ? v.toLowerCase() : v
              );
              const normalizedCurrent = typeof currentValue === 'string' 
                ? currentValue.toLowerCase() 
                : currentValue;
              
              if (!normalizedAllowed.includes(normalizedCurrent)) {
                dependenciesMet = false;
              }
            }
          });
        }
        
        // Only include property if dependencies are met
        if (dependenciesMet) {
          filteredProperties[key] = propSchema;
        }
      } else {
        // No dependencies, include property
        filteredProperties[key] = propSchema;
      }
    });

    filteredSchema.properties = filteredProperties;

    // Update required array to only include fields that are still in properties
    if (filteredSchema.required && Array.isArray(filteredSchema.required)) {
      filteredSchema.required = filteredSchema.required.filter((field: string) =>
        field in filteredProperties
      );
    }
  }

  return filteredSchema;
};
