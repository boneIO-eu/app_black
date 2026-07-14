import type { AreaEntity, CoverEntity, OutputEntity, RemoteDeviceEntity } from '@/types/config';

export type Area = AreaEntity;
export type RemoteDevice = RemoteDeviceEntity;

export interface ActionFieldsProps {
  action: any;
  index: number;
  onUpdate: (field: string, value: any) => void;
  onRemove: () => void;
  allOutputs: OutputEntity[];
  allOutputGroups: any[];
  allCovers: CoverEntity[];
  allAreas: Area[];
  allRemoteDevices?: RemoteDevice[];
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
  showValidation?: boolean;
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: any[];
  savedCovers?: CoverEntity[];
  clickType?: 'single' | 'double' | 'triple' | 'long' | 'double_then_long' | 'single_then_long' | 'double_then_single' | 'pressed' | 'released';
}

export interface BaseActionProps {
  action: any;
  onUpdate: (field: string, value: any) => void;
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
  allOutputGroups: any[];
  allAreas?: Area[];
  actionOutputOptions: string[];
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: any[];
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

export interface MqttActionProps extends BaseActionProps {}

export interface OutputOverMqttActionProps extends BaseActionProps {
  allOutputs: OutputEntity[];
  allOutputGroups: any[];
  actionOutputOptions: string[];
}

export interface CoverOverMqttActionProps extends BaseActionProps {
  allCovers: CoverEntity[];
  allAreas: Area[];
  actionCoverOptions: string[];
}
