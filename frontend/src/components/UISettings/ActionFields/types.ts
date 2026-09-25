import type {
  AreaEntity,
  CoverEntity,
  ESPHomeLightEntity,
  ESPHomeSwitchEntity,
  OutputEntity,
  RemoteDeviceEntity,
  WLEDSegmentEntity,
} from '@/types/config';

export type Area = AreaEntity;
export type RemoteDevice = RemoteDeviceEntity;

/** Condition kinds the backend understands (`boneio/schema/actions.yaml`). */
export type ConditionType = 'time' | 'date' | 'state' | 'sun';

/** One condition on an action or a schedule. */
export type ActionCondition = {
  type: ConditionType;
  /** HH:MM for time, MM-DD for date, a sun anchor name for sun. */
  after?: string;
  before?: string;
  /** Sun only. Read as seconds when it comes from the backend, written as "-30min". */
  after_offset?: string | number;
  before_offset?: string | number;
  /** Sun only. */
  phase?: string;
  above?: number;
  below?: number;
  /** State only: entity kind (binary_sensor, cover, output, ...). */
  entity?: string;
  entity_id?: string;
  state?: string;
};

/** Several conditions combined with AND / OR. */
export type ActionConditionGroup = {
  mode?: 'and' | 'or';
  list?: ActionCondition[];
};

/** Extra data carried by cover actions. `tilt_position` is '' or null while
 *  the field is being edited, which is what the validator looks for. */
export type CoverActionData = {
  position?: number;
  tilt_position?: number | '' | null;
  always_open_till?: number;
};

/**
 * Every field an action edited here can carry.
 *
 * A `type` alias rather than an `interface` on purpose: it stays assignable to
 * `Record<string, unknown>` (`ActionEntry` in `helpers/actionSummary.ts`).
 * Field lists mirror `ALLOWED_FIELDS_BY_ACTION` and `SHARED_FIELDS` in
 * `helpers.ts`.
 */
export type ActionDef = {
  action?: string;

  // output / virtual_switch / output_over_mqtt / remote_output
  boneio_output?: string;
  boneio_virtual_switch?: string;
  action_output?: string;

  // cover / cover_over_mqtt / remote_cover
  boneio_cover?: string;
  action_cover?: string;
  /** Legacy ESPHome cover verb, still honoured by the validator. */
  action_esphome_cover?: string;
  data?: CoverActionData;
  restore_tilt?: boolean;

  // mqtt / *_over_mqtt
  topic?: string;
  action_mqtt_msg?: string;
  boneio_id?: string;

  // remote_output / remote_cover
  remote_device?: string;
  output_id?: string;
  cover_id?: string;
  brightness?: number;
  brightness_step?: number;
  color_temp?: number;
  rgb?: number[];
  /** Time period ("500ms"); legacy configs store seconds as a number. */
  transition?: string | number;
  effect?: number;
  palette?: number;
  effect_speed?: number;
  effect_intensity?: number;
  colors?: number[][];
  /** ESPHome effect names or WLED effect IDs. */
  presets?: (string | number)[];

  // shared
  min_duration?: number;
  max_duration?: number;
  repeat?: boolean;
  repeat_interval?: string;
  condition?: ActionCondition;
  conditions?: ActionConditionGroup;
  delay?: string;
  delay_cancel_on?: string[];

  /** @deprecated Use boneio_output or boneio_cover instead. */
  pin?: string;
};

/**
 * What callers hand the editor: either a typed action, or the raw record the
 * forms keep (`ActionEntry`, schedule entries). The editor reads it as an
 * `ActionDef` — the forms only ever put the fields above into it.
 */
export type ActionInput = ActionDef | Record<string, unknown>;

/** `onUpdate(field, value)` from the shared editors. `field` may be the
 *  `__batch` sentinel, with an object of fields as `value`. */
export type ActionUpdate = (field: string, value: unknown) => void;

/** An `output_group` entry as it comes from the config. */
export type OutputGroupRecord = Record<string, unknown>;

/** The fields of an output group the pickers use. */
export type OutputGroupEntity = {
  id: string;
  name?: string;
  area?: string;
};

/** A cover on a remote device, whichever protocol reported it. */
export type RemoteCoverEntity = {
  id: string;
  name?: string;
  kind?: string;
  supports_tilt?: boolean;
};

/** One selectable target of a remote_output action. `_type` tells them apart;
 *  plain MQTT outputs carry none. */
export type RemoteOutputEntity =
  | (ESPHomeSwitchEntity & { _type: 'switch' })
  | (ESPHomeLightEntity & { _type: 'light' })
  | { id: string; name: string; _type: 'wled_main' }
  | (Omit<WLEDSegmentEntity, 'id' | 'name'> & { id: string; name: string; _type: 'wled_segment' })
  | { id: string; name?: string; _type?: undefined };

export interface BaseActionProps {
  action: ActionDef;
  onUpdate: ActionUpdate;
  t: (key: string) => string;
}

export interface RemoteOutputActionProps extends BaseActionProps {
  allRemoteDevices: RemoteDevice[];
  actionOutputOptions: string[];
}

export interface RemoteCoverActionProps extends BaseActionProps {
  allRemoteDevices: RemoteDevice[];
  actionCoverOptions: string[];
}

export interface OutputActionProps extends BaseActionProps {
  allOutputs: OutputEntity[];
  allOutputGroups: OutputGroupRecord[];
  allAreas?: Area[];
  actionOutputOptions: string[];
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: OutputGroupRecord[];
  /** Area ID of the input being configured — used to prioritize outputs from the same area. */
  preferredArea?: string;
}

export interface CoverActionProps extends BaseActionProps {
  allCovers: CoverEntity[];
  allAreas: Area[];
  actionCoverOptions: string[];
  savedCovers?: CoverEntity[];
  isCoverSaved: (coverId: string) => boolean;
  /** Area ID of the input being configured — used to prioritize covers from the same area. */
  preferredArea?: string;
}

export type MqttActionProps = BaseActionProps;

export interface OutputOverMqttActionProps extends BaseActionProps {
  allOutputs: OutputEntity[];
  allOutputGroups: OutputGroupRecord[];
  actionOutputOptions: string[];
}

export interface CoverOverMqttActionProps extends BaseActionProps {
  allCovers: CoverEntity[];
  allAreas: Area[];
  actionCoverOptions: string[];
}
