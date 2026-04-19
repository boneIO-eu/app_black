import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface RemoteDevice {
  id: string;
  name?: string;
  protocol?: string;
  [key: string]: any;
}

interface RemoteDeviceSelectProps {
  /** Currently selected remote device ID */
  value: string;
  /** Called when a new device is selected */
  onChange: (value: string) => void;
  /** List of all available remote devices */
  allRemoteDevices: RemoteDevice[];
  /** Placeholder text */
  placeholder?: string;
  /** Label text */
  label?: string;
  /** Optional protocol filter - only show devices matching this protocol */
  protocolFilter?: string[];
}

/**
 * RemoteDeviceSelect - Reusable widget for selecting a remote device.
 * 
 * Shows device name, ID, and protocol badge (ESPHome / WLED / MQTT).
 * Used in RemoteOutputAction and RemoteCoverAction forms.
 */
const RemoteDeviceSelect: React.FC<RemoteDeviceSelectProps> = ({
  value,
  onChange,
  allRemoteDevices,
  placeholder = 'Select remote device...',
  label,
  protocolFilter,
}) => {
  const filteredDevices = allRemoteDevices.filter((device) => {
    if (!device.id) return false;
    if (protocolFilter && protocolFilter.length > 0) {
      return protocolFilter.includes(device.protocol || '');
    }
    return true;
  });

  const getProtocolLabel = (protocol?: string): string => {
    switch (protocol) {
      case 'esphome_api': return 'ESPHome';
      case 'wled': return 'WLED';
      default: return 'MQTT';
    }
  };

  return (
    <div className="form-control mb-3">
      {label && (
        <label className="label">
          <span className="label-text font-medium">{label}</span>
        </label>
      )}
      <Select value={value || ''} onValueChange={onChange}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {filteredDevices.map((device) => (
            <SelectItem key={device.id} value={device.id}>
              <div className="flex flex-col">
                <span>{device.name || device.id}</span>
                <span className="text-xs opacity-60 protocol text-left">
                  {getProtocolLabel(device.protocol)}
                </span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
};

export default RemoteDeviceSelect;
