import { useState, useEffect, useCallback } from 'react';
import { useAuth } from './useAuth';
import { useApiAvailability } from './useApiAvailability';

// State models matching Python Pydantic models

export interface InputState {
  name: string;
  state: string;
  type: string;
  pin: string;
  timestamp: number;
  boneio_input: string;
}

export interface InputEvent {
  event_type: 'input';
  entity_id: string;
  click_type: string;
  duration: number | null;
  state: InputState;
}

export interface OutputState {
  id: string;
  name: string;
  state: string;
  type: string;
  expander_id: string | null;
  pin: number;
  timestamp: number | null;
}

export interface OutputEvent {
  event_type: 'output';
  entity_id: string;
  state: OutputState;
}

export interface CoverState {
  id: string;
  name: string;
  state: string;
  position: number;
  current_operation: string;
  timestamp: number | null;
  tilt: number;  // Tilt position (0-100)
  kind: string;
}

export interface CoverEvent {
  event_type: 'cover';
  entity_id: string;
  state: CoverState;
}

export interface SensorState {
  id: string;
  name: string;
  state: number | string | null;
  unit: string | null;
  timestamp: number | null;
}

export interface ModbusDeviceState {
  id: string;
  name: string;
  state: number | string | null;
  unit: string | null;
  timestamp: number | null;
  device_group: string;
  coordinator_id: string;  // Coordinator ID for API calls
  entity_type?: string | null;  // 'select', 'switch', 'sensor', 'writeable_sensor', 'writeable_sensor_discrete', etc.
  x_mapping?: Record<string, string> | null;  // Value mapping for select/switch (e.g., {"1": "Auto", "2": "Cool"})
  payload_on?: string | null;  // For switch entities
  payload_off?: string | null;  // For switch entities
}

export interface SensorEvent {
  event_type: 'sensor';
  entity_id: string;
  state: SensorState;
}

export interface ModbusDeviceEvent {
  event_type: 'modbus_device';
  entity_id: string;
  state: ModbusDeviceState;
}

export type StateUpdate = InputEvent | OutputEvent | SensorEvent | CoverEvent | ModbusDeviceEvent;

// Type guards

export function isInputEvent(data: StateUpdate): data is InputEvent {
  return data.event_type === 'input';
}

export function isOutputEvent(data: StateUpdate): data is OutputEvent {
  return data.event_type === 'output';
}

export function isCoverEvent(data: StateUpdate): data is CoverEvent {
  return data.event_type === 'cover';
}

export function isSensorEvent(data: StateUpdate): data is SensorEvent {
  return data.event_type === 'sensor';
}

export function isModbusDeviceEvent(data: StateUpdate): data is ModbusDeviceEvent {
  return data.event_type === 'modbus_device';
}

interface WebSocketHookResult {
  error: string | null;
  addMessageListener: (callback: (message: StateUpdate) => void) => () => void;
}

// Singleton WebSocket instance and listeners
let globalWs: WebSocket | null = null;
let globalMessageListeners = new Set<(message: StateUpdate) => void>();
let globalConnecting = false;
let globalPingInterval: number | null = null;
let globalReconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 30;
const RECONNECT_DELAY = 5000;
let activeConnections = 0;

export const closeWebSocket = () => {
  if (globalWs) {
    globalWs.close();
    globalWs = null;
  }
  if (globalPingInterval) {
    clearInterval(globalPingInterval);
    globalPingInterval = null;
  }
  globalMessageListeners.clear();
  globalConnecting = false;
  globalReconnectAttempts = 0;
  activeConnections = 0;
};

const setupWebSocket = async (
  setError: (error: string | null) => void,
  isAuthRequired: boolean,
  isApiAvailable: boolean
) => {
  if (!isApiAvailable) {
    console.log('API not available, delaying WebSocket connection');
    return;
  }

  // Don't attempt to reconnect if we already have a connection
  if (globalWs?.readyState === WebSocket.OPEN || globalConnecting) {
    return;
  }

  globalConnecting = true;
  try {
    const baseUrl = import.meta.env.VITE_API_URL || '';
    const wsUrl = `${baseUrl.replace(/^http/, 'ws')}/ws/state`;
    
    // Get token if authentication is required
    const token = isAuthRequired && localStorage.getItem('token') || null;
    const protocols = token ? [`token.${token}`] : undefined;
    
    // Create WebSocket with protocol
    globalWs = new WebSocket(wsUrl, protocols);

    globalWs.onopen = () => {
      console.log('WebSocket connection established successfully');
      setError(null);
      globalConnecting = false;
      globalReconnectAttempts = 0;

      // Start ping interval
      if (globalPingInterval) {
        clearInterval(globalPingInterval);
      }
      globalPingInterval = window.setInterval(() => {
        if (globalWs?.readyState === WebSocket.OPEN) {
          globalWs.send('ping');
        }
      }, 30000);
    };

    globalWs.onmessage = (event) => {
      try {
        if (event.data === 'pong') {
          return;
        }
        const message: StateUpdate = JSON.parse(event.data);
        globalMessageListeners.forEach((listener) => {
          try {
            listener(message);
          } catch (e) {
            console.error('Error in message listener:', e);
          }
        });
      } catch (e) {
        console.error('Error processing WebSocket message:', e);
      }
    };

    globalWs.onclose = () => {
      if (globalPingInterval) {
        clearInterval(globalPingInterval);
        globalPingInterval = null;
      }

      globalWs = null;
      globalConnecting = false;

      if (activeConnections > 0 && globalReconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        console.log(`WebSocket closed. Attempting to reconnect (${globalReconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS})...`);
        globalReconnectAttempts++;
        setTimeout(() => setupWebSocket(setError, isAuthRequired, isApiAvailable), RECONNECT_DELAY);
      } else if (globalReconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        setError('WebSocket connection failed after multiple attempts');
      }
    };

    globalWs.onerror = (event) => {
      console.error('WebSocket error:', event);
    };
  } catch (e) {
    console.error('Error creating WebSocket:', e);
    setError('Failed to create WebSocket connection');
    globalConnecting = false;
  }
};

export function useWebSocket(): WebSocketHookResult {
  const [error, setError] = useState<string | null>(null);
  const { isAuthRequired } = useAuth();
  const { isApiAvailable } = useApiAvailability();

  useEffect(() => {
    // Don't attempt to connect if API is not available
    if (!isApiAvailable) {
      return;
    }

    activeConnections++;
    console.log('Setting up WebSocket connection, API available:', isApiAvailable);

    const connect = () => {
      setupWebSocket(setError, isAuthRequired, isApiAvailable);
    };

    // Add a small delay before the initial connection attempt
    const initialConnectTimeout = setTimeout(connect, 500);

    return () => {
      clearTimeout(initialConnectTimeout);
      activeConnections--;
      if (activeConnections === 0) {
        closeWebSocket();
      }
    };
  }, [isAuthRequired, isApiAvailable]);

  const addMessageListener = useCallback((callback: (message: StateUpdate) => void) => {
    globalMessageListeners.add(callback);
    return () => {
      globalMessageListeners.delete(callback);
    };
  }, []);

  return { error, addMessageListener };
}
