// Utility functions for config schema processing

// Rozszerzamy interfejs JSONSchema7 o właściwości specyficzne dla naszej aplikacji
interface ExtendedJSONSchema {
  'x-timeperiod'?: boolean;
  properties?: { [key: string]: ExtendedJSONSchema };
  items?: ExtendedJSONSchema | ExtendedJSONSchema[];
}

/**
 * Bezpieczne sprawdzenie czy schemat jest obiektem ExtendedJSONSchema i ma właściwość properties
 */
function hasProperties(schema: any): schema is ExtendedJSONSchema {
  return schema && typeof schema === 'object' && 'properties' in schema;
}

/**
 * Bezpieczna konwersja schematu do ExtendedJSONSchema
 */
function asExtendedSchema(schema: any): ExtendedJSONSchema | undefined {
  if (!schema || typeof schema !== 'object') return undefined;
  return schema as ExtendedJSONSchema;
}

 /**
   * Convert milliseconds back to string format for backend
   */
 export const convertMillisecondsToTimeperiod = (milliseconds: number): string => {
    // Check if it's a whole number of hours
    if (milliseconds >= 3600000 && milliseconds % 3600000 === 0) {
      return `${milliseconds / 3600000}h`;
    }
    // Check if it's a whole number of minutes
    else if (milliseconds >= 60000 && milliseconds % 60000 === 0) {
      return `${milliseconds / 60000}min`;
    }
    // Check if it's a whole number of seconds
    else if (milliseconds >= 1000 && milliseconds % 1000 === 0) {
      return `${milliseconds / 1000}s`;
    }
    // Otherwise use milliseconds
    else {
      return `${milliseconds}ms`;
    }
  };



  /**
   * Convert timeperiod object to milliseconds for form display
   */
  export const convertTimeperiodToMilliseconds = (timeperiodObj: any): number => {
    if (typeof timeperiodObj === 'number') return timeperiodObj;
    if (typeof timeperiodObj === 'string') {
      // Parse string like "120ms" or "30s"
      const match = timeperiodObj.match(/^(\d+(?:\.\d+)?)(ms|s|m|h)?$/);
      if (match) {
        const value = parseFloat(match[1]);
        const unit = match[2] || 'ms';
        switch (unit) {
          case 'ms': return value;
          case 's': return value * 1000;
          case 'm': return value * 60 * 1000;
          case 'h': return value * 60 * 60 * 1000;
          default: return value;
        }
      }
      return 0;
    }
    if (timeperiodObj && typeof timeperiodObj === 'object') {
      // Use milliseconds from timeperiod object
      return timeperiodObj.milliseconds || timeperiodObj._total_in_seconds * 1000 || 0;
    }
    return 0;
  };

  /**
   * Convert form data back to original types based on original data and schema
   */
  export const convertFormDataToOriginalTypes = (formData: any, originalData: any, schema?: any): any => {
    // Konwertujemy schema do ExtendedJSONSchema
    const extendedSchema = asExtendedSchema(schema);
    console.log("convertFormDataToOriginalTypes", formData, originalData, schema)
    
    // Handle arrays at top level - don't convert to object!
    if (Array.isArray(formData)) {
      const itemsSchema = extendedSchema?.items as ExtendedJSONSchema | undefined;
      return formData.map((item: any, index: number) => {
        if (typeof item === 'object' && item !== null) {
          const originalItem = Array.isArray(originalData) && index < originalData.length ? originalData[index] : {};
          
          // Convert timeperiod fields
          const convertedItem = { ...item };
          if (hasProperties(itemsSchema) && itemsSchema.properties) {
            Object.keys(convertedItem).forEach(itemKey => {
              const itemPropSchema = itemsSchema.properties?.[itemKey];
              
              if (itemPropSchema && 
                  typeof itemPropSchema === 'object' && 
                  itemPropSchema['x-timeperiod'] === true && 
                  typeof convertedItem[itemKey] === 'number') {
                convertedItem[itemKey] = convertMillisecondsToTimeperiod(convertedItem[itemKey]);
              }
            });
          }
          
          // Recursively convert nested objects
          if (originalItem && typeof originalItem === 'object') {
            return convertFormDataToOriginalTypes(convertedItem, originalItem, itemsSchema);
          }
          
          return convertedItem;
        }
        return item;
      });
    }
    
    if (!originalData || typeof originalData !== 'object') return formData;
    if (!formData || typeof formData !== 'object') return formData;

    const converted = { ...formData };
    
    // Przetwarzamy wszystkie klucze z formData, nie tylko z originalData
    // aby uwzględnić nowe pola dodane w formularzu
    Object.keys(converted).forEach(key => {
      const currentValue = converted[key];
      const originalValue = originalData[key];
      const propSchema = extendedSchema?.properties?.[key];
      
      // Jeśli klucz nie istnieje w originalData, zachowujemy wartość z formularza
      if (originalValue === undefined || originalValue === null) {
        return;
      }
      
      const originalType = typeof originalValue;
      
      // Handle array with items schema
      if (Array.isArray(currentValue)) {
        // Sprawdzamy czy schema ma definicję items
        if (propSchema && typeof propSchema === 'object' && propSchema.items) {
          converted[key] = currentValue.map((item: any, index: number) => {
            // Sprawdzamy czy element jest obiektem i czy mamy odpowiedni schemat
            if (typeof item === 'object' && item !== null && typeof propSchema.items === 'object') {
              const itemsSchema = propSchema.items as ExtendedJSONSchema;
              const originalItem = Array.isArray(originalValue) && index < originalValue.length ? originalValue[index] : {};
              
              // Konwertujemy pola timeperiod ZAWSZE (dla nowych i istniejących elementów)
              const convertedItem = { ...item };
              // Process all keys, not just those in schema (to catch TimePeriod objects)
              Object.keys(convertedItem).forEach(itemKey => {
                const itemPropSchema = hasProperties(itemsSchema) ? itemsSchema.properties?.[itemKey] : undefined;
                const val = convertedItem[itemKey];
                
                // Check if this is a timeperiod field (by schema or by detecting TimePeriod object)
                const isTimePeriodSchema = itemPropSchema && 
                    typeof itemPropSchema === 'object' && 
                    itemPropSchema['x-timeperiod'] === true;
                const isTimePeriodObject = typeof val === 'object' && val !== null &&
                    ('milliseconds' in val || 'seconds' in val || 
                     'minutes' in val || 'hours' in val || 
                     '_total_in_seconds' in val);
                
                if (isTimePeriodSchema || isTimePeriodObject) {
                  // If already string with unit (from SimpleTimePeriodInput), keep it
                  if (typeof val === 'string' && /^\d+(\.\d+)?\s*(ms|s|sec|min|h|hours?)$/i.test(val)) {
                    // Already has unit, keep as-is
                  }
                  // If number (milliseconds), convert to string with unit
                  else if (typeof val === 'number') {
                    convertedItem[itemKey] = convertMillisecondsToTimeperiod(val);
                  }
                  // If TimePeriod object from backend, convert to string
                  else if (isTimePeriodObject) {
                    if (val.hours !== undefined && val.hours > 0) {
                      convertedItem[itemKey] = `${val.hours}h`;
                    } else if (val.minutes !== undefined && val.minutes > 0) {
                      convertedItem[itemKey] = `${val.minutes}min`;
                    } else if (val.seconds !== undefined && val.seconds > 0) {
                      convertedItem[itemKey] = `${val.seconds}s`;
                    } else if (val.milliseconds !== undefined && val.milliseconds > 0) {
                      convertedItem[itemKey] = `${val.milliseconds}ms`;
                    } else if (val._total_in_seconds !== undefined) {
                      convertedItem[itemKey] = convertMillisecondsToTimeperiod(val._total_in_seconds * 1000);
                    } else {
                      convertedItem[itemKey] = '0s';
                    }
                  }
                }
              });
              
              // Jeśli mamy oryginalny element, używamy rekurencji dla pozostałych pól
              if (originalItem && typeof originalItem === 'object') {
                return convertFormDataToOriginalTypes(convertedItem, originalItem, itemsSchema);
              }
              
              return convertedItem;
            }
            return item;
          });
        }
      }
      // Handle timeperiod fields - keep string values with units as-is
      // Also detect TimePeriod objects from backend even without schema
      else if ((propSchema && 
               typeof propSchema === 'object' && 
               propSchema['x-timeperiod'] === true) ||
               // Detect TimePeriod object by its structure
               (typeof currentValue === 'object' && currentValue !== null &&
                ('milliseconds' in currentValue || 'seconds' in currentValue || 
                 'minutes' in currentValue || 'hours' in currentValue || 
                 '_total_in_seconds' in currentValue))) {
        // If value is already a string with unit (e.g., "30s"), keep it
        if (typeof currentValue === 'string' && /^\d+(\.\d+)?\s*(ms|s|sec|min|h|hours?)$/i.test(currentValue)) {
          converted[key] = currentValue;
          console.log(`✓ Timeperiod ${key} already has unit: ${currentValue}`);
        }
        // If value is a number (milliseconds), convert to string with unit
        else if (typeof currentValue === 'number') {
          console.log(`Converting timeperiod ${key}: ${currentValue}ms`, propSchema);
          const timeperiodString = convertMillisecondsToTimeperiod(currentValue);
          converted[key] = timeperiodString;
        }
        // If value is a TimePeriod object from backend, convert to string
        else if (typeof currentValue === 'object' && currentValue !== null) {
          console.log(`Converting TimePeriod object ${key}:`, currentValue);
          if (currentValue.hours !== undefined && currentValue.hours > 0) {
            converted[key] = `${currentValue.hours}h`;
          } else if (currentValue.minutes !== undefined && currentValue.minutes > 0) {
            converted[key] = `${currentValue.minutes}min`;
          } else if (currentValue.seconds !== undefined && currentValue.seconds > 0) {
            converted[key] = `${currentValue.seconds}s`;
          } else if (currentValue.milliseconds !== undefined && currentValue.milliseconds > 0) {
            converted[key] = `${currentValue.milliseconds}ms`;
          } else if (currentValue._total_in_seconds !== undefined) {
            converted[key] = convertMillisecondsToTimeperiod(currentValue._total_in_seconds * 1000);
          } else {
            converted[key] = '0s';
          }
        }
        // Otherwise keep as-is (shouldn't happen)
        else {
          converted[key] = currentValue;
        }
      }
      // Convert string back to number if original was number (but NOT for timeperiod fields)
      else if (originalType === 'number' && typeof currentValue === 'string') {
        const numValue = parseFloat(currentValue);
        if (!isNaN(numValue)) {
          converted[key] = numValue;
        }
      }
      // Handle nested objects recursively
      else if (typeof currentValue === 'object' && currentValue !== null && 
               typeof originalValue === 'object' && originalValue !== null) {
        converted[key] = convertFormDataToOriginalTypes(currentValue, originalValue, 
          propSchema && typeof propSchema === 'object' ? propSchema as ExtendedJSONSchema : undefined);
      }
    });
    
    return converted;
  };


  /**
 * Usuwa z formData:
 * 1. Pola ukryte (ui:widget: "hidden" w uiSchema)
 * 2. Pola o wartości domyślnej (zdefiniowanej w schema)
 *
 * @param formData - Dane formularza przekazywane przez RJSF
 * @param schema - JSON Schema sekcji
 * @param uiSchema - uiSchema sekcji
 * @returns Nowy obiekt bez ukrytych pól i pól z wartością domyślną
 */
export const stripHiddenAndDefaults = (
    formData: any,
    schema: any,
    uiSchema: any = {}
  ): any => {
    
    // Handle arrays
    if (Array.isArray(formData)) {
      const filteredArray = formData
        .map((item) => {
          // For arrays, uiSchema might be structured differently
          const itemUiSchema = uiSchema?.items || uiSchema || {};
          return stripHiddenAndDefaults(item, schema?.items, itemUiSchema);
        })
        .filter((item) => {
          // Keep item if it's not undefined and not an empty object
          if (item === undefined || item === null) return false;
          if (typeof item !== "object") return true;
          if (Array.isArray(item)) return item.length > 0;
          return Object.keys(item).length > 0;
        });
      
      return filteredArray;
    }
    
    // Handle primitives
    if (typeof formData !== "object" || formData === null) {
      return formData;
    }
    
    const result: any = {};
    
    for (const key of Object.keys(formData)) {
      const fieldValue = formData[key];
      const fieldSchema = schema?.properties?.[key];
      const fieldUiSchema = uiSchema?.[key] || {};
      
      // Skip hidden fields
      if (fieldUiSchema["ui:widget"] === "hidden") {
        console.log(`Skipping hidden field: ${key}`);
        continue;
      }
      
      // Special handling for actions
      if (key === 'actions' && typeof fieldValue === 'object' && fieldValue !== null) {
        const cleanedActions: any = {};
        
        for (const [actionType, actionList] of Object.entries(fieldValue)) {
          if (Array.isArray(actionList)) {
            const cleanedList = actionList.map((actionItem: any) => {
              if (typeof actionItem !== 'object' || actionItem === null) return actionItem;
              
              const cleanedAction: any = {};
              
              for (const [actionKey, actionValue] of Object.entries(actionItem)) {
                // Skip default values for action fields
                if (actionKey === 'action_cover' && actionValue === 'TOGGLE') continue;
                if (actionKey === 'action_output' && actionValue === 'TOGGLE') continue;
                if (actionKey === 'transition' && (actionValue === 0 || actionValue === 0.0)) continue;
                if (actionKey === 'data' && typeof actionValue === 'object' && Object.keys(actionValue as object).length === 0) continue;
                
                cleanedAction[actionKey] = actionValue;
              }
              
              return Object.keys(cleanedAction).length > 0 ? cleanedAction : null;
            }).filter((item: any) => item !== null);
            
            if (cleanedList.length > 0) {
              cleanedActions[actionType] = cleanedList;
            }
          }
        }
        
        if (Object.keys(cleanedActions).length > 0) {
          result[key] = cleanedActions;
        }
        continue;
      }
      
      // Skip empty data objects
      if (key === 'data' && typeof fieldValue === 'object' && fieldValue !== null && Object.keys(fieldValue).length === 0) {
        continue;
      }
      
      // Skip fields with default values
      const defaultValue = fieldSchema?.default;
      if (defaultValue !== undefined) {
        // Special handling for timeperiod fields (x-timeperiod: true)
        if (fieldSchema?.['x-timeperiod'] === true) {
          // Convert both to milliseconds for comparison
          const defaultMs = convertTimeperiodToMilliseconds(defaultValue);
          const fieldMs = convertTimeperiodToMilliseconds(fieldValue);
          if (defaultMs === fieldMs) {
            console.log(`Skipping default timeperiod field: ${key} = ${fieldValue} (default: ${defaultValue})`);
            continue;
          }
        } else if (JSON.stringify(fieldValue) === JSON.stringify(defaultValue)) {
          console.log(`Skipping default value field: ${key} = ${JSON.stringify(defaultValue)}`);
          continue;
        }
      }
      
      // Recursively process nested objects and arrays
      const processedChild = stripHiddenAndDefaults(fieldValue, fieldSchema, fieldUiSchema);
      
      // Include field if it has meaningful content
      if (processedChild !== undefined && processedChild !== null && processedChild !== '') {
        if (typeof processedChild === "object") {
          if (Array.isArray(processedChild)) {
            if (processedChild.length > 0) {
              result[key] = processedChild;
            }
          } else {
            if (Object.keys(processedChild).length > 0) {
              result[key] = processedChild;
            }
          }
        } else {
          result[key] = processedChild;
        }
      }
    }
    
    return result;
  }