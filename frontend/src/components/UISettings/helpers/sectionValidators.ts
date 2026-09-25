/**
 * Validation functions for configuration sections.
 * Each validator returns null if valid, or an error message if invalid.
 */

/** The fields of the `boneio` section this validator reads. */
interface BoneioSectionData {
  name?: string;
  version?: unknown;
  device_type?: unknown;
}

/** The fields of one `virtual_energy_sensor` entry this validator reads. */
interface VirtualEnergySensorData {
  id?: string;
  name?: string;
}

export interface ValidationResult {
  valid: boolean;
  errorMessage?: string;
}

/**
 * Validate boneio section - name is required if any other field is set.
 */
export function validateBoneioSection(input: unknown): ValidationResult {
  const data = input as BoneioSectionData | null | undefined;
  const hasOtherFields = data?.version || data?.device_type;
  const hasName = data?.name && data.name.trim() !== '';
  
  if (hasOtherFields && !hasName) {
    return {
      valid: false,
      errorMessage: 'boneio_config.name_required_error'
    };
  }
  
  return { valid: true };
}

/**
 * Validate virtual_energy_sensor section - IDs must be unique.
 */
export function validateVirtualEnergySensorSection(data: unknown): ValidationResult {
  if (!Array.isArray(data)) {
    return { valid: true };
  }
  
  const ids = new Set<string>();
  const duplicates: string[] = [];
  
  for (const sensor of data as VirtualEnergySensorData[]) {
    // Generate ID from name if not provided (same logic as backend)
    const sensorId = sensor.id || (sensor.name 
      ? sensor.name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') 
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
    return {
      valid: false,
      errorMessage: `virtual_energy_sensor.duplicate_id_error:${duplicates.join(', ')}`
    };
  }
  
  return { valid: true };
}

/**
 * Validate a section before saving.
 * Returns validation result with error message key if invalid.
 */
export function validateSection(sectionName: string, data: unknown): ValidationResult {
  switch (sectionName) {
    case 'boneio':
      return validateBoneioSection(data);
    case 'virtual_energy_sensor':
      return validateVirtualEnergySensorSection(data);
    default:
      return { valid: true };
  }
}
