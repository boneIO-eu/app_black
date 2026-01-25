import type { CoverEntity, OutputEntity } from '@/types/config';

export interface Area {
  id: string;
  name: string;
}

export interface RemoteDevice {
  id: string;
  name?: string;
  protocol?: string;
  mqtt?: {
    outputs?: { id: string; name?: string }[];
    covers?: { id: string; name?: string }[];
  };
  esphome_api?: {
    host?: string;
    switches?: { id: string; name?: string; key?: number }[];
    lights?: { 
      id: string; 
      name?: string; 
      key?: number; 
      supports_brightness?: boolean; 
      supports_color_temp?: boolean; 
      supports_rgb?: boolean; 
      min_mireds?: number; 
      max_mireds?: number 
    }[];
    covers?: { 
      id: string; 
      name?: string; 
      key?: number; 
      supports_position?: boolean; 
      supports_tilt?: boolean 
    }[];
  };
  wled?: {
    host?: string;
    port?: number;
    segments?: { 
      id: number; 
      name?: string; 
      start?: number; 
      stop?: number; 
      len?: number; 
      supports_rgb?: boolean 
    }[];
    effects?: { id: number; name: string }[];
    palettes?: { id: number; name: string }[];
  };
}

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
  actionOutputOptions: string[];
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: any[];
}

export interface CoverActionProps extends BaseActionProps {
  allCovers: CoverEntity[];
  allAreas: Area[];
  actionCoverOptions: string[];
  savedCovers?: CoverEntity[];
  isCoverSaved: (coverId: string) => boolean;
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
