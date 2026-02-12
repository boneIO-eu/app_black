import { convertTimeperiodToMilliseconds } from '../helpers/configSchemaUtils';

/**
 * Validates an action and returns an error message if invalid.
 * @param action - The action object to validate
 * @param t - Translation function
 * @returns Error message string or null if valid
 */
export const validateAction = (action: any, t: (key: string) => string): string | null => {
  if (!action.action) return t('event_form.validation_action_type_required');
  
  const actionType = action.action.toLowerCase();
  
  if (actionType === 'output' || actionType === 'output_over_mqtt') {
    if (!action.boneio_output) return t('event_form.validation_output_required');
  }
  
  if (actionType === 'cover' || actionType === 'cover_over_mqtt') {
    if (!action.boneio_cover) return t('event_form.validation_cover_required');
  }
  
  if (actionType === 'mqtt') {
    if (!action.topic) return t('event_form.validation_topic_required');
  }
  
  if (actionType === 'output_over_mqtt' || actionType === 'cover_over_mqtt') {
    if (!action.boneio_id) return t('event_form.validation_boneio_id_required');
  }
  
  if (actionType === 'remote_output') {
    if (!action.remote_device) return t('event_form.validation_remote_device_required');
    if (!action.output_id) return t('event_form.validation_output_id_required');
    if (action.action_output === 'CYCLE_COLOR' && (!action.colors || action.colors.length === 0)) {
      return t('event_form.validation_colors_required');
    }
    if (action.action_output === 'CYCLE_PRESET' && (!action.presets || action.presets.length === 0)) {
      return t('event_form.validation_presets_required');
    }
  }
  
  if (actionType === 'remote_cover') {
    if (!action.remote_device) return t('event_form.validation_remote_device_required');
    if (!action.cover_id) return t('event_form.validation_cover_id_required');
  }
  
  // Transition must not exceed repeat_interval when repeat is enabled
  if (action.repeat && action.transition) {
    const transitionMs = convertTimeperiodToMilliseconds(action.transition);
    const repeatMs = convertTimeperiodToMilliseconds(action.repeat_interval || '800ms');
    if (transitionMs > repeatMs) {
      return t('event_form.validation_transition_exceeds_repeat');
    }
  }
  
  return null;
};

/**
 * Converts RGB array to hex color string.
 * @param rgb - Array of [r, g, b] values (0-255)
 * @returns Hex color string like '#ffffff'
 */
export const rgbToHex = (rgb: number[]): string => {
  if (!rgb || rgb.length < 3) return '#ffffff';
  return '#' + rgb.slice(0, 3).map(c => c.toString(16).padStart(2, '0')).join('');
};

/**
 * Converts hex color string to RGB array.
 * @param hex - Hex color string like '#ffffff' or 'ffffff'
 * @returns Array of [r, g, b] values (0-255)
 */
export const hexToRgb = (hex: string): number[] => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? [
    parseInt(result[1], 16),
    parseInt(result[2], 16),
    parseInt(result[3], 16)
  ] : [255, 255, 255];
};
