/**
 * TypeScript types for boneIO configuration entities.
 * Generated based on config.schema.json
 */

// ============================================
// Common types
// ============================================

/** GPIO mode options */
export type GpioMode = 'gpio' | 'gpio_pu' | 'gpio_pd' | 'gpio_input';

/** Device class for event entities */
export type EventDeviceClass = 'button' | 'doorbell' | 'motion';

/** Action types */
export type ActionType =
  | 'output' | 'OUTPUT' | 'Output'
  | 'cover' | 'COVER' | 'Cover'
  | 'mqtt' | 'MQTT' | 'Mqtt'
  | 'output_over_mqtt' | 'OUTPUT_OVER_MQTT' | 'Output_Over_Mqtt'
  | 'cover_over_mqtt' | 'COVER_OVER_MQTT' | 'Cover_Over_Mqtt'
  | 'remote_output' | 'REMOTE_OUTPUT' | 'Remote_Output'
  | 'remote_cover' | 'REMOTE_COVER' | 'Remote_Cover'
  | 'esphome_switch' | 'ESPHOME_SWITCH' | 'Esphome_Switch'
  | 'esphome_light' | 'ESPHOME_LIGHT' | 'Esphome_Light'
  | 'esphome_cover' | 'ESPHOME_COVER' | 'Esphome_Cover';

/** ESPHome light action options */
export type ESPHomeLightAction =
  | 'TOGGLE' | 'ON' | 'OFF'
  | 'BRIGHTNESS_UP' | 'BRIGHTNESS_DOWN'
  | 'BRIGHTNESS_UP_CYCLE' | 'BRIGHTNESS_DOWN_CYCLE'
  | 'SET_BRIGHTNESS';

/** Output action options */
export type OutputAction = 'TOGGLE' | 'ON' | 'OFF';

/** Cover action options */
export type CoverAction =
  | 'TOGGLE' | 'OPEN' | 'CLOSE' | 'STOP'
  | 'TOGGLE_OPEN' | 'TOGGLE_CLOSE' | 'SMART_TOGGLE'
  | 'TILT' | 'TILT_OPEN' | 'TILT_CLOSE';

/** BoneIO input pin identifiers (IN_01 to IN_49 on boards 0.5+, IN_01 to IN_52 on boards 0.2–0.4) */
export type BoneioInput = string;

// ============================================
// Action types
// ============================================

/** Extra data for cover actions (position, tilt, smart toggle) */
export interface ActionData {
  /** Position to set cover to (0-100) */
  position?: number;
  /** Tilt position to set cover to (0-100) */
  tilt_position?: number;
  /** Smart toggle threshold (0-100%) - cover opens if position <= this value */
  always_open_till?: number;
}

/** Single action configuration */
export interface Action {
  /** Type of action to perform */
  action: ActionType;
  /** Output ID to control (for output action) */
  boneio_output?: string;
  /** Cover ID to control (for cover action) */
  boneio_cover?: string;
  /** @deprecated Use boneio_output or boneio_cover instead */
  pin?: string;
  /** MQTT topic for mqtt action */
  topic?: string;
  /** Cover action type */
  action_cover?: CoverAction;
  /** Output action type */
  action_output?: OutputAction;
  /** MQTT message payload */
  action_mqtt_msg?: string;
  /** BoneIO device ID for remote actions */
  boneio_id?: string;
  /** Remote device ID (from remote_devices section) */
  remote_device?: string;
  /** Remote output ID (for remote_output action) */
  output_id?: string;
  /** Remote cover ID (for remote_cover action) */
  cover_id?: string;
  /** Extra data (for cover position/tilt) */
  data?: ActionData;
  /** Restore tilt position after cover movement (action-level, venetian only) */
  restore_tilt?: boolean;

  // ESPHome-specific fields
  /** ESPHome device ID (from remote_devices with protocol: esphome_api) */
  esphome_device?: string;
  /** ESPHome switch ID (object_id) */
  switch_id?: string;
  /** ESPHome light ID (object_id) */
  light_id?: string;
  /** ESPHome switch action */
  action_switch?: OutputAction;
  /** ESPHome light action */
  action_light?: ESPHomeLightAction;
  /** ESPHome cover action */
  action_esphome_cover?: CoverAction;
  /** Brightness (0-255) for light actions */
  brightness?: number;
  /** Brightness step (1-50%) for brightness up/down actions */
  brightness_step?: number;
  /** Color temperature in mireds */
  color_temp?: number;
  /** Transition time in seconds */
  transition?: number;
  /** Light/WLED presets for cycle actions */
  presets?: any;
  /** Light/WLED colors for cycle actions */
  colors?: any;
}

/** Action type keys for event entity */
export type EventActionType = 'single' | 'double' | 'long';

/** Actions configuration for event entity */
export interface EventActions {
  /** Actions triggered on single click */
  single?: Action[];
  /** Actions triggered on double click */
  double?: Action[];
  /** Actions triggered on long press */
  long?: Action[];
  /** Index signature for dynamic access */
  [key: string]: Action[] | undefined;
}

// ============================================
// Event entity
// ============================================

/** Event entity configuration */
export interface EventEntity {
  /** Display name in Home Assistant */
  name?: string;
  /** Unique ID for MQTT topic */
  id?: string;
  /** GPIO pin */
  pin?: string;
  /** BoneIO predefined input reference */
  boneio_input?: BoneioInput;
  /** @deprecated GPIO mode — now handled by kernel overlay, ignored at runtime */
  gpio_mode?: GpioMode;
  /** Bounce time in milliseconds */
  bounce_time?: number | string;
  /** Clear MQTT message after action (like Zigbee2MQTT) */
  clear_message?: boolean;
  /** Show entity in Home Assistant */
  show_in_ha?: boolean;
  /** Invert sensor state */
  inverted?: boolean;
  /** Device class for Home Assistant */
  device_class?: EventDeviceClass;
  /** Area/Room assignment */
  area?: string;
  /** Time window to detect double click (default: 220ms) */
  double_click_duration?: number | string;
  /** Time to detect long press (default: 400ms) */
  long_press_duration?: number | string;
  /** Time window to detect click sequences (default: 500ms) */
  sequence_window_duration?: number | string;
  /** Sequence mode: 'immediate' (default) or 'exclusive' */
  sequence_mode?: 'immediate' | 'exclusive';
  /** Enable triple click detection (default: false) */
  enable_triple_click?: boolean;
  /** Long press MQTT mode: 'single' (first only) or 'periodic' (all with duration) */
  long_press_mqtt_mode?: 'single' | 'periodic';
  /** Safety timeout for long press (default: 120s). Stops long press if RELEASE is missed. */
  max_long_press_duration?: number | string;
  /** Actions configuration */
  actions?: EventActions;
  /** MQTT sequences configuration - which sequences to publish to MQTT */
  mqtt_sequences?: {
    double_then_long?: boolean;
    single_then_long?: boolean;
    double_then_single?: boolean;
  };
}

// ============================================
// Binary sensor entity
// ============================================

/** Binary sensor device class */
export type BinarySensorDeviceClass =
  | 'door' | 'garage_door' | 'lock' | 'moisture'
  | 'motion' | 'occupancy' | 'opening' | 'presence'
  | 'smoke' | 'sound' | 'vibration' | 'window';

/** Binary sensor kind */
export type BinarySensorKind = 'sensor' | 'button';

/** Actions for binary sensor (pressed/released) */
export interface BinarySensorActions {
  /** Actions triggered on press */
  pressed?: Action[];
  /** Actions triggered on release */
  released?: Action[];
  /** Index signature for dynamic access */
  [key: string]: Action[] | undefined;
}

/** Binary sensor entity configuration */
export interface BinarySensorEntity {
  /** Display name in Home Assistant */
  name?: string;
  /** Unique ID for MQTT topic */
  id?: string;
  /** GPIO pin */
  pin?: string;
  /** BoneIO predefined input reference */
  boneio_input?: BoneioInput;
  /** @deprecated GPIO mode — now handled by kernel overlay, ignored at runtime */
  gpio_mode?: GpioMode;
  /** Bounce time in milliseconds */
  bounce_time?: number | string;
  /** Show entity in Home Assistant */
  show_in_ha?: boolean;
  /** Invert sensor state */
  inverted?: boolean;
  /** Send initial state on startup */
  initial_send?: boolean;
  /** Clear MQTT message after action (like Zigbee2MQTT) */
  clear_message?: boolean;
  /** Sensor kind (sensor or button) */
  kind?: BinarySensorKind;
  /** Device class for Home Assistant */
  device_class?: BinarySensorDeviceClass;
  /** Area/Room assignment */
  area?: string;
  /** Actions configuration */
  actions?: BinarySensorActions;
}

// ============================================
// Input entity (alias for binary sensor)
// ============================================

export type InputEntity = BinarySensorEntity;

// ============================================
// Cover entity
// ============================================

/** Cover device type */
export type CoverDeviceType =
  | 'cover' | 'Cover' | 'COVER'
  | 'cover mix' | 'Cover Mix' | 'COVER MIX'
  | 'roller' | 'Roller' | 'ROLLER'
  | 'time based' | 'Time Based' | 'TIME BASED';

/** Cover entity configuration */
export interface CoverEntity {
  /** Display name in Home Assistant */
  name?: string;
  /** Unique ID for MQTT topic */
  id?: string;
  /** Open relay/output pin */
  open_relay?: string;
  /** Close relay/output pin */
  close_relay?: string;
  /** Open time in milliseconds */
  open_time?: number | string;
  /** Close time in milliseconds */
  close_time?: number | string;
  /** Device type */
  device_type?: CoverDeviceType;
  /** Show entity in Home Assistant */
  show_in_ha?: boolean;
  /** Area/Room assignment */
  area?: string;
  /** Restore last state on startup */
  restore_state?: boolean;
  /** Tilt time in milliseconds (for blinds) */
  tilt_time?: number | string;
  /** Cover platform: 'time_based' (standard) or 'venetian' (with tilt support) */
  platform?: 'time_based' | 'venetian';
}

// ============================================
// Output entity
// ============================================

/** Output kind */
export type OutputKind = 'light' | 'switch';

/** Output entity configuration */
export interface OutputEntity {
  /** Display name in Home Assistant */
  name?: string;
  /** Unique ID for MQTT topic */
  id?: string;
  /** GPIO pin or MCP address */
  pin?: string;
  /** Output kind (light or switch) */
  kind?: OutputKind;
  /** Show entity in Home Assistant */
  show_in_ha?: boolean;
  /** Area/Room assignment */
  area?: string;
  /** Restore last state on startup */
  restore_state?: boolean;
  /** Momentary output duration */
  momentary_turn_on?: number | string;
  /** Momentary output duration */
  momentary_turn_off?: number | string;
  /** Board-level output identifier (local outputs only) */
  boneio_output?: string;
  /** Output type: switch, light, cover, valve */
  output_type?: string;
  /** Remote source protocol: esphome_api, can, mqtt, wled (remote outputs only) */
  remote_source?: string;
  /** Remote device ID (remote outputs only) */
  device_id?: string;
  /** Remote output/entity ID on the remote device (remote outputs only) */
  output_id?: string;
}

// ============================================
// Area entity
// ============================================

/** Area/Room configuration */
export interface AreaEntity {
  /** Area ID */
  id: string;
  /** Display name */
  name: string;
}

// ============================================
// ESPHome entity types
// ============================================

/** ESPHome switch entity */
export interface ESPHomeSwitchEntity {
  /** Switch ID (object_id) */
  id: string;
  /** Display name */
  name?: string;
  /** Entity key (from discovery) */
  key?: number;
}

/** ESPHome light entity with capabilities */
export interface ESPHomeLightEntity {
  /** Light ID (object_id) */
  id: string;
  /** Display name */
  name?: string;
  /** Entity key (from discovery) */
  key?: number;
  /** Supports brightness control */
  supports_brightness?: boolean;
  /** Supports color temperature */
  supports_color_temp?: boolean;
  /** Supports RGB color */
  supports_rgb?: boolean;
  /** Supports RGBW color */
  supports_rgbw?: boolean;
  /** Minimum color temperature in mireds */
  min_mireds?: number;
  /** Maximum color temperature in mireds */
  max_mireds?: number;
}

/** ESPHome cover entity */
export interface ESPHomeCoverEntity {
  /** Cover ID (object_id) */
  id: string;
  /** Display name */
  name?: string;
  /** Entity key (from discovery) */
  key?: number;
  /** Supports position control */
  supports_position?: boolean;
  /** Supports tilt control */
  supports_tilt?: boolean;
}

/** ESPHome binary sensor entity */
export interface ESPHomeBinarySensorEntity {
  /** Binary sensor ID (object_id) */
  id: string;
  /** Display name */
  name?: string;
  /** Entity key (from discovery) */
  key?: number;
  /** Custom input ID (overrides auto-generated {device_id}_{sensor_id}) */
  input_id?: string;
  /** Operating mode: binary_sensor (pressed/released) or event (single/double/long) */
  mode?: 'binary_sensor' | 'event';
  /** Device class for HA (e.g. door, motion, window) */
  device_class?: BinarySensorDeviceClass;
  /** Area/Room assignment */
  area?: string;
  /** Show in Home Assistant */
  show_in_ha?: boolean;
  /** Invert state */
  inverted?: boolean;
  /** Double click window in ms (event mode) */
  double_click_duration?: number;
  /** Long press threshold in ms (event mode) */
  long_press_duration?: number;
  /** Sequence mode: immediate or exclusive (event mode) */
  sequence_mode?: 'immediate' | 'exclusive';
  /** Long press MQTT mode (event mode) */
  long_press_mqtt_mode?: 'single' | 'periodic';
  /** Enable triple click detection (event mode) */
  enable_triple_click?: boolean;
  /** Actions on state change */
  actions?: BinarySensorActions | EventActions;
}

/** ESPHome API configuration */
export interface ESPHomeApiConfig {
  /** IP address or hostname */
  host: string;
  /** API port (default 6053) */
  port?: number;
  /** API password */
  password?: string;
  /** Encryption key (base64) */
  encryption_key?: string;
  /** Discovered/configured switches */
  switches?: ESPHomeSwitchEntity[];
  /** Discovered/configured lights */
  lights?: ESPHomeLightEntity[];
  /** Discovered/configured covers */
  covers?: ESPHomeCoverEntity[];
  /** Discovered/configured binary sensors */
  binary_sensors?: ESPHomeBinarySensorEntity[];
  /** Runtime-only: all discovered binary sensors (before user selection) */
  _discovered_binary_sensors?: ESPHomeBinarySensorEntity[];
}

/** WLED segment entity */
export interface WLEDSegmentEntity {
  /** Segment ID */
  id: number;
  /** Display name */
  name?: string;
  /** Start LED index */
  start?: number;
  /** Stop LED index */
  stop?: number;
  /** LED count */
  len?: number;
  /** Supports RGB color */
  supports_rgb?: boolean;
}

/** WLED effect entity */
export interface WLEDEffectEntity {
  /** Effect ID */
  id: number;
  /** Effect name */
  name: string;
}

/** WLED palette entity */
export interface WLEDPaletteEntity {
  /** Palette ID */
  id: number;
  /** Palette name */
  name: string;
}

/** WLED configuration */
export interface WLEDConfig {
  /** IP address or hostname */
  host: string;
  /** HTTP port (default 80) */
  port?: number;
  /** Discovered/configured segments */
  segments?: WLEDSegmentEntity[];
  /** Discovered effects */
  effects?: WLEDEffectEntity[];
  /** Discovered palettes */
  palettes?: WLEDPaletteEntity[];
}

/** Remote device protocol */
export type RemoteDeviceProtocol = 'mqtt' | 'esphome_api' | 'wled';

/** Remote device type */
export type RemoteDeviceType = 'boneio_black' | 'esphome' | 'wled' | 'generic';

/** Remote device entity */
export interface RemoteDeviceEntity {
  /** Device ID */
  id: string;
  /** Display name */
  name?: string;
  /** Communication protocol */
  protocol?: RemoteDeviceProtocol;
  /** Device type */
  device_type?: RemoteDeviceType;
  /** MQTT configuration (for protocol: mqtt) */
  mqtt?: {
    outputs?: { id: string; name?: string }[];
    covers?: { id: string; name?: string; kind?: string; supports_tilt?: boolean }[];
  };
  /** ESPHome API configuration (for protocol: esphome_api) */
  esphome_api?: ESPHomeApiConfig;
  /** WLED configuration (for protocol: wled) */
  wled?: WLEDConfig;
}

// ============================================
// Full config type
// ============================================

/** Complete boneIO configuration */
export interface BoneIOConfig {
  mqtt?: Record<string, any>;
  web?: Record<string, any>;
  oled?: Record<string, any>;
  modbus?: Record<string, any>;
  dallas?: Record<string, any>;
  lm75?: Record<string, any>;
  pca9685?: Record<string, any>;
  mcp23017?: Record<string, any>;
  pcf8575?: Record<string, any>;
  output?: OutputEntity[];
  input?: InputEntity[];
  binary_sensor?: BinarySensorEntity[];
  event?: EventEntity[];
  cover?: CoverEntity[];
  areas?: AreaEntity[];
  sensor?: Record<string, any>[];
  adc?: Record<string, any>[];
  modbus_devices?: Record<string, any>[];
  output_group?: Record<string, any>[];
}
