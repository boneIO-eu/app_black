import { createContext } from 'react';
import type {
  CoverEvent,
  GroupEvent,
  InputEvent,
  ModbusDeviceEvent,
  OutputEvent,
  SensorEvent,
} from '@/hooks/useWebSocket';

/**
 * The live entity states, filled by AppContent from the WebSocket.
 *
 * Kept out of App.tsx on purpose. Exported from there, a component module
 * exporting a non-component broke Fast Refresh, so every edit re-stamped
 * App.tsx; a view loaded lazily afterwards imported the new copy and read a
 * second, never-provided context — an empty Outputs page with the socket
 * delivering states the whole time. This file imports nothing that changes,
 * so there is only ever one context object.
 */
export const WebSocketContext = createContext<{
  outputs: OutputEvent[];
  inputs: InputEvent[];
  sensors: SensorEvent[];
  modbus_devices: ModbusDeviceEvent[];
  covers: CoverEvent[];
  groups: GroupEvent[];
}>({
  outputs: [],
  inputs: [],
  sensors: [],
  modbus_devices: [],
  covers: [],
  groups: [],
});
