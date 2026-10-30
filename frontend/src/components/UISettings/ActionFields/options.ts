/**
 * The action types and commands the controller accepts, as its models in
 * boneio/core/config/models/inputs.py list them.
 *
 * The forms keep their own copy rather than reading the schema: there each
 * action type is its own schema behind a `$ref`, which the forms do not
 * follow. options.test.ts checks the copy against the generated schema.
 */
export const ACTION_TYPE_OPTIONS = [
  'output', 'cover', 'virtual_switch', 'mqtt', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover',
];
export const ACTION_OUTPUT_OPTIONS = [
  'TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE',
  'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET',
];
export const ACTION_COVER_OPTIONS = [
  'TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'SET_POSITION', 'TILT',
  'TILT_OPEN', 'TILT_CLOSE',
];
