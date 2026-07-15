import { convertTimeperiodToMilliseconds } from '../helpers/configSchemaUtils';

/**
 * Fields allowed per action type. When switching action type,
 * only these fields (plus 'action') are preserved.
 */
const ALLOWED_FIELDS_BY_ACTION: Record<string, string[]> = {
  output: ['boneio_output', 'action_output'],
  cover: ['boneio_cover', 'action_cover', 'data', 'restore_tilt'],
  mqtt: ['topic', 'action_mqtt_msg'],
  output_over_mqtt: ['boneio_id', 'boneio_output', 'action_output', 'action_mqtt_msg'],
  cover_over_mqtt: ['boneio_id', 'boneio_cover', 'action_cover', 'action_mqtt_msg', 'data'],
  remote_output: [
    'remote_device', 'output_id', 'action_output',
    'brightness', 'brightness_step', 'color_temp', 'rgb', 'transition',
    'effect', 'palette', 'effect_speed', 'effect_intensity',
    'colors', 'presets',
  ],
  remote_cover: ['remote_device', 'cover_id', 'action_cover', 'data', 'restore_tilt'],
};

/** Fields shared across all action types (always preserved). */
const SHARED_FIELDS = ['action', 'min_duration', 'max_duration', 'repeat', 'repeat_interval', 'condition', 'conditions', 'delay', 'delay_cancel_on'];

/**
 * Returns a clean action object containing only fields valid for the given action type.
 * Used when user switches action type to prevent stale fields from the previous type.
 * @param newActionType - The new action type string
 * @param currentAction - The current action object (may contain fields from old type)
 * @returns New action object with only valid fields
 */
export const cleanActionFields = (newActionType: string, currentAction: Record<string, any> = {}): Record<string, any> => {
  const allowed = ALLOWED_FIELDS_BY_ACTION[newActionType.toLowerCase()] || [];
  const keepSet = new Set([...SHARED_FIELDS, ...allowed]);

  const cleaned: Record<string, any> = { action: newActionType };
  for (const key of Object.keys(currentAction)) {
    if (key !== 'action' && keepSet.has(key) && currentAction[key] !== undefined) {
      cleaned[key] = currentAction[key];
    }
  }
  return cleaned;
};

/**
 * Formats an action option string into a human-readable label.
 * E.g. 'BRIGHTNESS_UP_CYCLE' -> 'Brightness Up Cycle'
 * @param option - The action option string (e.g. 'TOGGLE', 'BRIGHTNESS_UP_CYCLE')
 * @param t - Optional translation function for i18n support
 * @returns Formatted/translated label string
 */
export const formatActionLabel = (option: string, t?: (key: string) => string): string => {
  if (t) {
    const key = `actions.${option.toLowerCase()}`;
    const translated = t(key);
    // If translation key is found (not returned as-is), use it
    if (translated !== key) return translated;
  }
  return option.split('_').map(word => word.charAt(0) + word.slice(1).toLowerCase()).join(' ');
};

/**
 * Validates a single condition and returns an error message if invalid.
 * @param condition - The condition object to validate
 * @param t - Translation function
 * @returns Error message string or null if valid
 */
export const validateCondition = (condition: any, t: (key: string) => string): string | null => {
  if (!condition || !condition.type) {
    return t('event_form.validation_condition_type_required');
  }

  if (condition.type === 'time') {
    if (!condition.after && !condition.before) {
      return t('event_form.validation_condition_time_required');
    }
    // Validate HH:MM format
    const timeRegex = /^\d{1,2}:\d{2}(:\d{2})?$/;
    if (condition.after && !timeRegex.test(condition.after)) {
      return t('event_form.validation_condition_time_format');
    }
    if (condition.before && !timeRegex.test(condition.before)) {
      return t('event_form.validation_condition_time_format');
    }
  }

  if (condition.type === 'date') {
    if (!condition.after && !condition.before) {
      return t('event_form.validation_condition_date_required');
    }
    // Validate MM-DD format
    const dateRegex = /^\d{2}-\d{2}$/;
    if (condition.after && !dateRegex.test(condition.after)) {
      return t('event_form.validation_condition_date_format');
    }
    if (condition.before && !dateRegex.test(condition.before)) {
      return t('event_form.validation_condition_date_format');
    }
  }

  if (condition.type === 'state') {
    if (!condition.entity) {
      return t('event_form.validation_condition_entity_required');
    }
    if (!condition.entity_id) {
      return t('event_form.validation_condition_entity_id_required');
    }
    if (!condition.state) {
      return t('event_form.validation_condition_state_required');
    }
  }

  return null;
};

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
  
  // TILT action requires tilt_position
  if (['cover', 'cover_over_mqtt', 'remote_cover', 'esphome_cover'].includes(actionType)) {
    const coverAction = action.action_cover || action.action_esphome_cover;
    if (coverAction === 'TILT' && (action.data?.tilt_position === undefined || action.data?.tilt_position === null || action.data?.tilt_position === '')) {
      return t('event_form.validation_tilt_position_required');
    }
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

  // Validate conditions
  if (action.condition) {
    const err = validateCondition(action.condition, t);
    if (err) return err;
  }
  if (action.conditions?.list) {
    for (const cond of action.conditions.list) {
      const err = validateCondition(cond, t);
      if (err) return err;
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

// ---------------------------------------------------------------------------
// Remote Cover Tilt Support Utilities
// ---------------------------------------------------------------------------

/** Tilt-related cover actions that only apply to covers with tilt support. */
export const TILT_ACTIONS = ['TILT', 'TILT_OPEN', 'TILT_CLOSE'];

/**
 * Determines if a cover supports tilt based on discovery data.
 * Checks supports_tilt flag first, then falls back to kind field.
 * Returns false when tilt support is unknown (safe default).
 * @param cover - Cover object from remote device (ESPHome or MQTT)
 * @returns true if the cover supports tilt control
 */
export const coverSupportsTilt = (cover: any): boolean => {
  if (!cover) return false;
  // Both ESPHome and MQTT covers may provide supports_tilt from discovery
  if ('supports_tilt' in cover) return !!cover.supports_tilt;
  // Fallback: check 'kind' field from BoneIO discovery
  if ('kind' in cover) return cover.kind === 'venetian';
  // Unknown — hide tilt by default (safer UX)
  return false;
};

/**
 * Filters cover action options based on tilt support.
 * Removes TILT, TILT_OPEN, TILT_CLOSE when cover does not support tilt.
 * @param actionOptions - Full list of cover action option strings
 * @param selectedCover - Currently selected cover object (or null/undefined)
 * @returns Filtered list of action options
 */
export const filterCoverActionsByTilt = (
  actionOptions: string[],
  selectedCover: any,
): string[] => {
  // If no cover selected yet, show all options
  if (!selectedCover) return actionOptions;
  if (coverSupportsTilt(selectedCover)) return actionOptions;
  return actionOptions.filter(opt => !TILT_ACTIONS.includes(opt));
};
