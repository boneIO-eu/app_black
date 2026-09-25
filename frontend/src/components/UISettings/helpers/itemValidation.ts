import { resolveId } from './slugifyId';
import type { JsonSchema } from '../../../types/jsonSchema';
/**
 * Section-specific validation for ArrayTableWidget save operations.
 * Determines required fields and validates items before saving.
 */

interface ValidationResult {
  isValid: boolean;
  errorMessage: string;
}

/**
 * The fields of an item (of any section) that validateItem reads. No index
 * signature on purpose, so entity interfaces and ConfigRecord both fit.
 */
interface ItemToValidate {
  _type?: unknown;
  boneio_input?: unknown;
  boneio_output?: unknown;
  id?: string;
  name?: string;
  outputs?: unknown;
  open_relay?: unknown;
  close_relay?: unknown;
  open_time?: unknown;
  close_time?: unknown;
  address?: unknown;
  model?: unknown;
  update_interval?: string | number;
  protocol?: unknown;
  esphome_api?: { host?: unknown } | null;
  platform?: unknown;
  sensor_id?: unknown;
  output_id?: unknown;
  control_mode?: unknown;
  open_output?: unknown;
  close_output?: unknown;
  pulse_output?: unknown;
  pin?: unknown;
}

/** An input entry as areAllItemsUsed counts it. */
interface InputEntry {
  boneio_input?: string;
}

/** Same truthiness test as before, spelled as a type guard. */
const hasBoneioInput = (entry: InputEntry): entry is InputEntry & { boneio_input: string } =>
  !!entry.boneio_input;

/** An output entry as areAllItemsUsed counts it. */
interface OutputEntry {
  boneio_output?: unknown;
}

/**
 * Validate an item before saving based on section type.
 * Returns validation result with error message if invalid.
 */
export function validateItem(
  sectionType: string,
  dataToSave: ItemToValidate,
  t: (key: string, params?: Record<string, string | number>) => string,
): ValidationResult {
  switch (sectionType) {
    case 'binary_sensor':
      return { isValid: !!dataToSave.boneio_input, errorMessage: t('array_table_widget.boneio_input_required') };

    case 'event':
      return { isValid: !!dataToSave.boneio_input, errorMessage: t('array_table_widget.boneio_input_required') };

    case 'local_inputs':
      // Validate based on _type within merged section
      if (dataToSave._type === 'binary_sensor' || dataToSave._type === 'event') {
        return { isValid: !!dataToSave.boneio_input, errorMessage: t('array_table_widget.boneio_input_required') };
      }
      return { isValid: !!dataToSave.boneio_input, errorMessage: t('array_table_widget.boneio_input_required') };

    case 'remote_inputs':
      // Remote inputs only require an ID (entity name)
      return { isValid: !!(dataToSave.id || dataToSave.name), errorMessage: t('array_table_widget.id_required') };

    case 'output':
      return { isValid: !!dataToSave.boneio_output, errorMessage: t('array_table_widget.boneio_output_required') };

    case 'output_group': {
      const hasId = !!dataToSave.id;
      const hasOutputs = !!dataToSave.outputs && (Array.isArray(dataToSave.outputs) ? dataToSave.outputs.length > 0 : true);
      return {
        isValid: hasId && hasOutputs,
        errorMessage: !hasId ? t('array_table_widget.id_required') : t('array_table_widget.at_least_one_output_required'),
      };
    }

    case 'cover':
      return {
        isValid: !!dataToSave.open_relay && !!dataToSave.close_relay && !!dataToSave.open_time && !!dataToSave.close_time,
        errorMessage: t('array_table_widget.cover_fields_required'),
      };

    case 'modbus_devices': {
      let isValid = !!dataToSave.address && !!dataToSave.model;
      let errorMessage = t('array_table_widget.address_and_model_required');

      if (isValid && dataToSave.update_interval) {
        const raw = dataToSave.update_interval;
        let intervalMs: number;
        if (typeof raw === 'number') {
          intervalMs = raw;
        } else {
          const match = String(raw).match(/^(\d+(?:\.\d+)?)\s*(ms|s|sec|min|h|hours?)$/i);
          if (match) {
            const num = parseFloat(match[1]);
            const unit = match[2].toLowerCase();
            const multiplier = unit === 'h' || unit === 'hour' || unit === 'hours' ? 3600000
              : unit === 'min' ? 60000
              : unit === 's' || unit === 'sec' ? 1000
              : 1;
            intervalMs = num * multiplier;
          } else {
            intervalMs = parseFloat(raw) || 0;
          }
        }
        if (intervalMs < 1000) {
          isValid = false;
          errorMessage = t('array_table_widget.update_interval_minimum');
        }
      }
      return { isValid, errorMessage };
    }

    case 'remote_devices': {
      let isValid = !!dataToSave.id && !!dataToSave.name && !!dataToSave.protocol;
      let errorMessage = t('array_table_widget.remote_device_fields_required');

      if (isValid && dataToSave.protocol === 'esphome_api') {
        isValid = !!dataToSave.esphome_api?.host;
        if (!isValid) {
          errorMessage = t('remote_devices.esphome_host_required') || 'ESPHome host is required';
        }
      }
      return { isValid, errorMessage };
    }

    case 'template': {
      const hasPlatform = !!dataToSave.platform;
      if (dataToSave.platform === 'thermostat') {
        return {
          isValid: hasPlatform && !!dataToSave.sensor_id && !!dataToSave.output_id,
          errorMessage: t('template.thermostat_fields_required'),
        };
      } else if (dataToSave.platform === 'alarm_control_panel') {
        return { isValid: hasPlatform, errorMessage: t('template.alarm_fields_required') };
      } else if (dataToSave.platform === 'gate_cover') {
        const mode = dataToSave.control_mode || 'cycle';
        const isValid = mode === 'separate'
          ? hasPlatform && !!dataToSave.id && (!!dataToSave.open_output || !!dataToSave.close_output)
          : hasPlatform && !!dataToSave.id && !!dataToSave.pulse_output;
        return { isValid, errorMessage: t('template.gate_cover_fields_required') };
      }
      return { isValid: hasPlatform, errorMessage: t('template.platform_required') };
    }

    case 'adc':
      return { isValid: !!dataToSave.pin, errorMessage: t('adc.pin_required') };

    case 'schedule':
    case 'virtual_switch':
      // The identifier is made from the name, so a name that slugifies to
      // nothing ("!!!") is the failure to catch here, not a missing id.
      return {
        isValid: !!resolveId(dataToSave),
        errorMessage: t('array_table_widget.name_required'),
      };

    default:
      return { isValid: true, errorMessage: '' };
  }
}

/**
 * Check if all available items are used (no more can be added).
 */
export function areAllItemsUsed(
  sectionType: string,
  value: readonly unknown[],
  schema: unknown,
  deviceType: string | undefined,
  allBinarySensors: readonly InputEntry[],
  allEvents: readonly InputEntry[],
): boolean {
  if (sectionType === 'output') {
    const type = deviceType?.toLowerCase() || '';
    let outputCount: number;
    if (type.includes('32') || type.includes('cm')) {
      outputCount = 32;
    } else if (type.includes('24')) {
      outputCount = 24;
    } else {
      outputCount = 49;
    }
    return value.filter(o => (o as OutputEntry).boneio_output).length >= outputCount;
  }

  if (sectionType === 'binary_sensor' || sectionType === 'event' || sectionType === 'local_inputs') {
    const usedFromBS = allBinarySensors.filter(hasBoneioInput).map(s => s.boneio_input.toUpperCase());
    const usedFromEV = allEvents.filter(hasBoneioInput).map(e => e.boneio_input.toUpperCase());
    const allUsed = [...new Set([...usedFromBS, ...usedFromEV])];
    const totalInputs = (schema as JsonSchema | null | undefined)?.items?.properties?.boneio_input?.enum?.length || 0;
    return allUsed.length >= totalInputs;
  }

  return false;
}
