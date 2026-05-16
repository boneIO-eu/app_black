/**
 * Section-specific validation for ArrayTableWidget save operations.
 * Determines required fields and validates items before saving.
 */
import { getOutputStats, isExpanderOutput } from '../modules/expander';
import type { ExpanderOutputStats } from '../modules/expander';

interface ValidationResult {
  isValid: boolean;
  errorMessage: string;
}

/** @deprecated Use ExpanderOutputStats from modules/expander instead. */
export type OutputStats = ExpanderOutputStats;

/** Re-exported for backwards compatibility with consumers importing from this file. */
export { getOutputStats };

/**
 * Validate an item before saving based on section type.
 * Returns validation result with error message if invalid.
 */
export function validateItem(
  sectionType: string,
  dataToSave: any,
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
      // Accept either boneio_output (board) or id starting with EX_ (expander)
      return {
        isValid: !!dataToSave.boneio_output || isExpanderOutput(dataToSave),
        errorMessage: t('array_table_widget.boneio_output_required'),
      };

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

    default:
      return { isValid: true, errorMessage: '' };
  }
}

/**
 * Check if all available items are used (no more can be added).
 */
export function areAllItemsUsed(
  sectionType: string,
  value: any[],
  schema: any,
  deviceType: string | undefined,
  allBinarySensors: any[],
  allEvents: any[],
): boolean {
  if (sectionType === 'output') {
    const { boardCapacity, boardUsed, expanderCapacity, expanderUsed } = getOutputStats(value, deviceType);
    const boardFull = boardUsed >= boardCapacity;
    const expanderFull = expanderCapacity === 0 || expanderUsed >= expanderCapacity;
    // Blocked only when both are full (or no expander configured → only board matters)
    return expanderCapacity === 0 ? boardFull : boardFull && expanderFull;
  }

  if (sectionType === 'binary_sensor' || sectionType === 'event' || sectionType === 'local_inputs') {
    const usedFromBS = allBinarySensors.filter(s => s.boneio_input).map(s => s.boneio_input.toUpperCase());
    const usedFromEV = allEvents.filter(e => e.boneio_input).map(e => e.boneio_input.toUpperCase());
    const allUsed = [...new Set([...usedFromBS, ...usedFromEV])];
    const totalInputs = schema?.items?.properties?.boneio_input?.enum?.length || 0;
    return allUsed.length >= totalInputs;
  }

  return false;
}
