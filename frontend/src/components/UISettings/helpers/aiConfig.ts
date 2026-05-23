import type {
  Action,
  AreaEntity,
  BinarySensorEntity,
  CoverEntity,
  EventEntity,
  OutputEntity,
  RemoteDeviceEntity,
} from '@/types/config';
import { normalizeOutputs } from './outputUtils';
import { normalizeCovers } from './coverUtils';
import { validateAction } from '../ActionFields/helpers';

export type AiEntityType = 'event' | 'binary_sensor';

type TranslationFn = (key: string) => string;

type SupportedEntity = EventEntity | BinarySensorEntity;

type SupportedActionSlot =
  | 'single'
  | 'double'
  | 'triple'
  | 'long'
  | 'double_then_long'
  | 'single_then_long'
  | 'double_then_single'
  | 'pressed'
  | 'released';

interface BuildAiConfigPromptParams<T extends SupportedEntity> {
  entityType: AiEntityType;
  data: T;
  schema?: any;
  allOutputs?: OutputEntity[];
  allOutputGroups?: any[];
  allCovers?: CoverEntity[];
  allAreas?: AreaEntity[];
  allRemoteDevices?: RemoteDeviceEntity[];
  /** All currently configured inputs (events + binary sensors) so AI knows what's already in use. */
  allConfiguredInputs?: SupportedEntity[];
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
}

interface ApplyAiConfigResponseParams<T extends SupportedEntity>
  extends BuildAiConfigPromptParams<T> {
  responseText: string;
  t: TranslationFn;
}

interface ApplyAiConfigResponseResult<T extends SupportedEntity> {
  data?: T;
  errors: string[];
}

interface RemoteOutputOption {
  id: string;
  name?: string;
  type?: string;
}

interface RemoteCoverOption {
  id: string;
  name?: string;
}

interface ParsedAiResponse {
  version?: number;
  entity_type?: string;
  apply_to?: string;
  changes?: Record<string, any>;
}

const BONEIO_BLACK_DOCS_URL = 'https://boneio.eu/docs/black';

const EVENT_ALLOWED_FIELDS = new Set([
  'name',
  'boneio_input',
  'area',
  'bounce_time',
  'clear_message',
  'show_in_ha',
  'inverted',
  'device_class',
  'double_click_duration',
  'long_press_duration',
  'sequence_window_duration',
  'sequence_mode',
  'enable_triple_click',
  'long_press_mqtt_mode',
  'max_long_press_duration',
  'mqtt_sequences',
  'actions',
]);

const BINARY_SENSOR_ALLOWED_FIELDS = new Set([
  'name',
  'boneio_input',
  'area',
  'bounce_time',
  'clear_message',
  'show_in_ha',
  'inverted',
  'device_class',
  'initial_send',
  'kind',
  'actions',
]);

const ACTION_ALLOWED_FIELDS = new Set([
  'action',
  'boneio_output',
  'boneio_cover',
  'pin',
  'topic',
  'action_cover',
  'action_output',
  'action_mqtt_msg',
  'boneio_id',
  'remote_device',
  'output_id',
  'cover_id',
  'data',
  'brightness',
  'brightness_step',
  'color_temp',
  'transition',
  'presets',
  'colors',
  'effect',
  'palette',
  'effect_speed',
  'effect_intensity',
  'rgb',
  'min_duration',
  'max_duration',
  'repeat',
  'repeat_interval',
]);

/**
 * Returns the list of action slots supported by a specific entity type.
 */
function getAllowedActionSlots(entityType: AiEntityType): SupportedActionSlot[] {
  if (entityType === 'event') {
    return ['single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'];
  }

  return ['pressed', 'released'];
}

/**
 * Returns the list of top-level fields that AI is allowed to change.
 */
function getAllowedFields(entityType: AiEntityType): Set<string> {
  return entityType === 'event' ? EVENT_ALLOWED_FIELDS : BINARY_SENSOR_ALLOWED_FIELDS;
}

/**
 * Builds a stable help URL for the current WebUI instance.
 */
function getWebUiHelpUrl(): string {
  if (typeof window === 'undefined') {
    return '/help';
  }

  return `${window.location.origin}/help`;
}

/**
 * Returns local outputs and output groups in a normalized shape for AI context.
 */
function getLocalOutputOptions(allOutputs: OutputEntity[] = [], allOutputGroups: any[] = [], allAreas: AreaEntity[] = []) {
  const areaMap = new Map(allAreas.map((area) => [area.id, area.name]));
  const outputs = normalizeOutputs(allOutputs as Array<OutputEntity & { boneio_output?: string }>).map((output) => ({
    id: output.id,
    name: output.name || output.id,
    output_type: output.kind || 'switch',
    area: output.area,
    area_name: output.area ? areaMap.get(output.area) || output.area : undefined,
    kind: 'output',
  }));
  const groups = (allOutputGroups || [])
    .filter((group) => group && typeof group === 'object' && group.id)
    .map((group) => ({
      id: group.id,
      name: group.name || group.id,
      area: group.area,
      area_name: group.area ? areaMap.get(group.area) || group.area : undefined,
      kind: 'group',
    }));

  return [...outputs, ...groups];
}

/**
 * Returns local covers in a normalized shape for AI context.
 */
function getLocalCoverOptions(allCovers: CoverEntity[] = [], allAreas: AreaEntity[] = []) {
  const areaMap = new Map(allAreas.map((area) => [area.id, area.name]));

  return normalizeCovers(allCovers).map((cover) => ({
    id: cover.id,
    name: cover.name || cover.id,
    area: cover.area,
    area_name: cover.area ? areaMap.get(cover.area) || cover.area : undefined,
  }));
}

/**
 * Returns available remote outputs/entities for a given remote device.
 */
function getRemoteOutputOptions(device: RemoteDeviceEntity): RemoteOutputOption[] {
  if (device.protocol === 'esphome_api') {
    const switches = (device.esphome_api?.switches || []).map((entity) => ({
      id: entity.id,
      name: entity.name || entity.id,
      type: 'switch',
    }));
    const lights = (device.esphome_api?.lights || []).map((entity) => ({
      id: entity.id,
      name: entity.name || entity.id,
      type: 'light',
    }));

    return [...switches, ...lights];
  }

  if (device.protocol === 'wled') {
    const segments = (device.wled?.segments || []).map((segment) => ({
      id: String(segment.id),
      name: segment.name || `Segment ${segment.id}`,
      type: 'wled_segment',
    }));

    return [{ id: 'main', name: 'All LEDs', type: 'wled_main' }, ...segments];
  }

  return (device.mqtt?.outputs || []).map((entity) => ({
    id: entity.id,
    name: entity.name || entity.id,
    type: 'mqtt_output',
  }));
}

/**
 * Returns available remote covers for a given remote device.
 */
function getRemoteCoverOptions(device: RemoteDeviceEntity): RemoteCoverOption[] {
  if (device.protocol === 'esphome_api') {
    return (device.esphome_api?.covers || []).map((entity) => ({
      id: entity.id,
      name: entity.name || entity.id,
    }));
  }

  return (device.mqtt?.covers || []).map((entity) => ({
    id: entity.id,
    name: entity.name || entity.id,
  }));
}

/**
 * Returns available remote binary sensors (inputs) for a given remote device.
 */
function getRemoteBinarySensorOptions(device: RemoteDeviceEntity): { id: string; name?: string }[] {
  const configured = device.esphome_api?.binary_sensors || [];
  const discovered = device.esphome_api?._discovered_binary_sensors || [];

  // Merge configured + discovered, deduplicating by ID
  const seen = new Set<string>();
  const result: { id: string; name?: string }[] = [];

  for (const sensor of [...configured, ...discovered]) {
    if (!seen.has(sensor.id)) {
      seen.add(sensor.id);
      result.push({ id: sensor.id, name: sensor.name || sensor.id });
    }
  }

  return result;
}

/**
 * Builds the structured context sent to an external AI assistant.
 */
export function buildAiConfigContext<T extends SupportedEntity>({
  entityType,
  data,
  schema,
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allRemoteDevices = [],
  allConfiguredInputs = [],
  actionTypeOptions,
  actionOutputOptions,
  actionCoverOptions,
}: BuildAiConfigPromptParams<T>) {
  // Build a compact summary of already-configured inputs so AI knows
  // which pins are in use and what they do (prevents overwriting).
  const configuredInputsSummary = allConfiguredInputs
    .filter((input) => input.boneio_input || (input as any).input_id)
    .map((input) => {
      const actions = input.actions || {};
      const actionSummary: Record<string, string[]> = {};
      for (const [slot, slotActions] of Object.entries(actions)) {
        if (Array.isArray(slotActions) && slotActions.length > 0) {
          actionSummary[slot] = slotActions.map((a: any) => {
            if (a.action === 'output') return `output:${a.boneio_output || '?'} ${a.action_output || 'TOGGLE'}`;
            if (a.action === 'cover') return `cover:${a.boneio_cover || '?'} ${a.action_cover || 'TOGGLE'}`;
            if (a.action === 'remote_output') return `remote:${a.remote_device || '?'}/${a.output_id || '?'}`;
            if (a.action === 'remote_cover') return `remote_cover:${a.remote_device || '?'}/${a.cover_id || '?'}`;
            if (a.action === 'mqtt') return `mqtt:${a.topic || '?'}`;
            return a.action || '?';
          });
        }
      }
      return {
        input: input.boneio_input || (input as any).input_id,
        name: input.name,
        mode: (input as any)._type || entityType,
        area: input.area,
        actions: Object.keys(actionSummary).length > 0 ? actionSummary : undefined,
      };
    });

  return {
    version: 1,
    entity_type: entityType,
    mode: 'edit_current_form',
    documentation_url: BONEIO_BLACK_DOCS_URL,
    webui_help_url: getWebUiHelpUrl(),
    current_entity: data,
    available_inputs: schema?.items?.properties?.boneio_input?.enum || [],
    configured_inputs: configuredInputsSummary,
    allowed_action_slots: getAllowedActionSlots(entityType),
    available_action_types: actionTypeOptions,
    action_output_options: actionOutputOptions,
    action_cover_options: actionCoverOptions,
    available_outputs: getLocalOutputOptions(allOutputs, allOutputGroups, allAreas),
    available_covers: getLocalCoverOptions(allCovers, allAreas),
    available_areas: allAreas.map((area) => ({ id: area.id, name: area.name })),
    available_remote_devices: allRemoteDevices.map((device) => ({
      id: device.id,
      name: device.name || device.id,
      protocol: device.protocol || 'mqtt',
      outputs: getRemoteOutputOptions(device),
      covers: getRemoteCoverOptions(device),
      binary_sensors: getRemoteBinarySensorOptions(device),
    })),
  };
}

/**
 * Builds the final prompt text that the user can paste into an external AI chat.
 */
export function buildAiConfigPrompt<T extends SupportedEntity>(params: BuildAiConfigPromptParams<T>): string {
  const context = buildAiConfigContext(params);

  return [
    'You are helping configure boneIO Black WebUI.',
    'Use only values from the provided JSON context.',
    'Do not invent IDs, action types, click types, outputs, covers, or remote devices.',
    'Return only valid JSON with no markdown, no explanations, and no code fences.',
    'The JSON response must have this shape:',
    '{"version":1,"entity_type":"event|binary_sensor","apply_to":"current_form","changes":{...}}',
    'Only include fields that should be changed.',
    'For actions, use the exact field names expected by boneIO, e.g. action, boneio_output, action_output, boneio_cover, action_cover, remote_device, output_id, cover_id.',
    'When clearing an optional scalar field, use null. When clearing actions for a slot, use an empty array.',
    '',
    'Output types and action guidance:',
    '- Each output in available_outputs has an output_type field: "light" or "switch".',
    '- For "switch" outputs: use action_output values like TOGGLE, ON, OFF.',
    '- For "light" outputs: you can also use BRIGHTNESS_UP, BRIGHTNESS_DOWN, BRIGHTNESS_UP_CYCLE, BRIGHTNESS_DOWN_CYCLE, SET_BRIGHTNESS, CYCLE_COLOR, CYCLE_PRESET.',
    '- Use the action_output_options list from the context to see all valid values.',
    '',
    'Remote devices:',
    '- available_remote_devices lists devices connected via ESPHome API, WLED, or MQTT.',
    '- Each remote device has outputs, covers, and binary_sensors arrays.',
    '- To control a remote output, use action: "remote_output", remote_device: "<device_id>", output_id: "<output_id>", action_output: "TOGGLE".',
    '- To control a remote cover, use action: "remote_cover", remote_device: "<device_id>", cover_id: "<cover_id>", action_cover: "TOGGLE".',
    '- Remote device binary_sensors are available as inputs for remote input configuration.',
    '',
    'Context JSON:',
    JSON.stringify(context, null, 2),
  ].join('\n');
}

/**
 * Parses the raw AI response and extracts a JSON object.
 */
function parseAiResponse(responseText: string): ParsedAiResponse {
  const trimmed = responseText.trim();
  const fencedMatch = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const normalized = fencedMatch ? fencedMatch[1].trim() : trimmed;

  return JSON.parse(normalized) as ParsedAiResponse;
}

/**
 * Returns a copy of an action with unknown keys removed.
 */
function sanitizeActionObject(action: Record<string, any>): Action {
  const sanitizedEntries = Object.entries(action).filter(([key]) => ACTION_ALLOWED_FIELDS.has(key));

  return Object.fromEntries(sanitizedEntries) as Action;
}

/**
 * Validates and normalizes a single AI-generated action.
 */
function validateAndNormalizeAction(
  action: Record<string, any>,
  actionIndex: number,
  slot: string,
  localOutputIds: Set<string>,
  localCoverIds: Set<string>,
  remoteOutputs: Map<string, Set<string>>,
  remoteCovers: Map<string, Set<string>>,
  actionTypeOptions: string[],
  actionOutputOptions: string[],
  actionCoverOptions: string[],
  t: TranslationFn,
): { action?: Action; errors: string[] } {
  const errors: string[] = [];

  if (!action || typeof action !== 'object' || Array.isArray(action)) {
    return { errors: [`${slot}[${actionIndex + 1}]: ${t('event_form.ai_invalid_action_object')}`] };
  }

  const sanitized = sanitizeActionObject(action);
  const normalizedActionType = typeof sanitized.action === 'string' ? sanitized.action.toLowerCase() : '';
  const allowedActionTypes = new Set(actionTypeOptions.map((option) => option.toLowerCase()));

  if (!normalizedActionType || !allowedActionTypes.has(normalizedActionType)) {
    return { errors: [`${slot}[${actionIndex + 1}]: ${t('event_form.ai_invalid_action_type')}`] };
  }

  sanitized.action = normalizedActionType as Action['action'];

  if (sanitized.action_output !== undefined) {
    const actionOutput = String(sanitized.action_output).toUpperCase();
    if (!actionOutputOptions.includes(actionOutput)) {
      errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_invalid_output_action')}`);
    }
    sanitized.action_output = actionOutput as Action['action_output'];
  }

  if (sanitized.action_cover !== undefined) {
    const actionCover = String(sanitized.action_cover).toUpperCase();
    if (!actionCoverOptions.includes(actionCover)) {
      errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_invalid_cover_action')}`);
    }
    sanitized.action_cover = actionCover as Action['action_cover'];
  }

  if (normalizedActionType === 'output' && sanitized.boneio_output && !localOutputIds.has(sanitized.boneio_output)) {
    errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_unknown_output')}`);
  }

  if (normalizedActionType === 'cover' && sanitized.boneio_cover && !localCoverIds.has(sanitized.boneio_cover)) {
    errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_unknown_cover')}`);
  }

  if (normalizedActionType === 'remote_output') {
    const outputIds = sanitized.remote_device ? remoteOutputs.get(sanitized.remote_device) : undefined;
    if (sanitized.remote_device && !outputIds) {
      errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_unknown_remote_device')}`);
    }
    if (sanitized.remote_device && sanitized.output_id && outputIds && !outputIds.has(String(sanitized.output_id))) {
      errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_unknown_remote_output')}`);
    }
  }

  if (normalizedActionType === 'remote_cover') {
    const coverIds = sanitized.remote_device ? remoteCovers.get(sanitized.remote_device) : undefined;
    if (sanitized.remote_device && !coverIds) {
      errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_unknown_remote_device')}`);
    }
    if (sanitized.remote_device && sanitized.cover_id && coverIds && !coverIds.has(String(sanitized.cover_id))) {
      errors.push(`${slot}[${actionIndex + 1}]: ${t('event_form.ai_unknown_remote_cover')}`);
    }
  }

  const validationError = validateAction(sanitized, t);
  if (validationError) {
    errors.push(`${slot}[${actionIndex + 1}]: ${validationError}`);
  }

  if (errors.length > 0) {
    return { errors };
  }

  return { action: sanitized, errors: [] };
}

/**
 * Applies a validated AI JSON patch to the current form data.
 */
export function applyAiConfigResponse<T extends SupportedEntity>({
  entityType,
  data,
  responseText,
  schema,
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allRemoteDevices = [],
  actionTypeOptions,
  actionOutputOptions,
  actionCoverOptions,
  t,
}: ApplyAiConfigResponseParams<T>): ApplyAiConfigResponseResult<T> {
  let parsed: ParsedAiResponse;

  try {
    parsed = parseAiResponse(responseText);
  } catch {
    return { errors: [t('event_form.ai_invalid_json')] };
  }

  if (parsed.version !== undefined && parsed.version !== 1) {
    return { errors: [t('event_form.ai_unsupported_version')] };
  }

  if (parsed.entity_type && parsed.entity_type !== entityType) {
    return { errors: [t('event_form.ai_wrong_entity_type')] };
  }

  if (parsed.apply_to && parsed.apply_to !== 'current_form') {
    return { errors: [t('event_form.ai_invalid_apply_target')] };
  }

  if (!parsed.changes || typeof parsed.changes !== 'object' || Array.isArray(parsed.changes)) {
    return { errors: [t('event_form.ai_missing_changes')] };
  }

  const allowedFields = getAllowedFields(entityType);
  const allowedInputs = new Set<string>(schema?.items?.properties?.boneio_input?.enum || []);
  const localOutputIds = new Set(getLocalOutputOptions(allOutputs, allOutputGroups, allAreas).map((output) => output.id));
  const localCoverIds = new Set(getLocalCoverOptions(allCovers, allAreas).map((cover) => cover.id));
  const remoteOutputs = new Map<string, Set<string>>(
    allRemoteDevices.map((device) => [device.id, new Set(getRemoteOutputOptions(device).map((output) => String(output.id)))]),
  );
  const remoteCovers = new Map<string, Set<string>>(
    allRemoteDevices.map((device) => [device.id, new Set(getRemoteCoverOptions(device).map((cover) => String(cover.id)))]),
  );
  const nextData: Record<string, any> = { ...data };
  const errors: string[] = [];

  for (const key of Object.keys(parsed.changes)) {
    if (!allowedFields.has(key)) {
      errors.push(`${t('event_form.ai_unknown_field')}: ${key}`);
    }
  }

  if (errors.length > 0) {
    return { errors };
  }

  for (const [field, rawValue] of Object.entries(parsed.changes)) {
    if (field === 'actions') {
      if (!rawValue || typeof rawValue !== 'object' || Array.isArray(rawValue)) {
        errors.push(t('event_form.ai_invalid_actions_shape'));
        continue;
      }

      const allowedSlots = new Set(getAllowedActionSlots(entityType));
      const nextActions: Record<string, Action[] | undefined> = { ...(data.actions || {}) };

      for (const [slot, slotValue] of Object.entries(rawValue)) {
        if (!allowedSlots.has(slot as SupportedActionSlot)) {
          errors.push(`${t('event_form.ai_unknown_action_slot')}: ${slot}`);
          continue;
        }

        if (!Array.isArray(slotValue)) {
          errors.push(`${slot}: ${t('event_form.ai_action_slot_must_be_array')}`);
          continue;
        }

        const normalizedActions: Action[] = [];
        slotValue.forEach((action, index) => {
          const result = validateAndNormalizeAction(
            action,
            index,
            slot,
            localOutputIds,
            localCoverIds,
            remoteOutputs,
            remoteCovers,
            actionTypeOptions,
            actionOutputOptions,
            actionCoverOptions,
            t,
          );

          if (result.errors.length > 0) {
            errors.push(...result.errors);
            return;
          }

          if (result.action) {
            normalizedActions.push(result.action);
          }
        });

        nextActions[slot] = normalizedActions;
      }

      nextData.actions = nextActions;
      continue;
    }

    if (field === 'mqtt_sequences') {
      if (entityType !== 'event') {
        errors.push(t('event_form.ai_field_not_supported'));
        continue;
      }

      if (!rawValue || typeof rawValue !== 'object' || Array.isArray(rawValue)) {
        errors.push(t('event_form.ai_invalid_mqtt_sequences'));
        continue;
      }

      const nextSequences = { ...((data as EventEntity).mqtt_sequences || {}) };
      for (const [sequenceKey, sequenceValue] of Object.entries(rawValue)) {
        if (!['double_then_long', 'single_then_long', 'double_then_single'].includes(sequenceKey)) {
          errors.push(`${t('event_form.ai_unknown_sequence_key')}: ${sequenceKey}`);
          continue;
        }
        if (typeof sequenceValue !== 'boolean') {
          errors.push(`${sequenceKey}: ${t('event_form.ai_boolean_required')}`);
          continue;
        }
        nextSequences[sequenceKey as keyof typeof nextSequences] = sequenceValue;
      }

      nextData.mqtt_sequences = nextSequences;
      continue;
    }

    if (field === 'boneio_input') {
      if (rawValue !== null && typeof rawValue !== 'string') {
        errors.push(`${field}: ${t('event_form.ai_string_required')}`);
        continue;
      }
      if (typeof rawValue === 'string' && allowedInputs.size > 0 && !allowedInputs.has(rawValue)) {
        errors.push(t('event_form.ai_unknown_input'));
        continue;
      }
      nextData[field] = rawValue === null ? undefined : rawValue;
      continue;
    }

    if (['clear_message', 'show_in_ha', 'inverted', 'enable_triple_click', 'initial_send'].includes(field)) {
      if (rawValue !== null && typeof rawValue !== 'boolean') {
        errors.push(`${field}: ${t('event_form.ai_boolean_required')}`);
        continue;
      }
      nextData[field] = rawValue === null ? undefined : rawValue;
      continue;
    }

    if (field === 'name' || field === 'area' || field === 'device_class' || field === 'sequence_mode' || field === 'long_press_mqtt_mode' || field === 'kind') {
      if (rawValue !== null && typeof rawValue !== 'string') {
        errors.push(`${field}: ${t('event_form.ai_string_required')}`);
        continue;
      }
      nextData[field] = rawValue === null ? undefined : rawValue;
      continue;
    }

    if (field === 'bounce_time' || field === 'double_click_duration' || field === 'long_press_duration' || field === 'sequence_window_duration' || field === 'max_long_press_duration') {
      const isValidScalar = rawValue === null || typeof rawValue === 'string' || typeof rawValue === 'number';
      if (!isValidScalar) {
        errors.push(`${field}: ${t('event_form.ai_scalar_required')}`);
        continue;
      }
      nextData[field] = rawValue === null ? undefined : rawValue;
      continue;
    }

    nextData[field] = rawValue;
  }

  if (errors.length > 0) {
    return { errors };
  }

  return { data: nextData as T, errors: [] };
}
