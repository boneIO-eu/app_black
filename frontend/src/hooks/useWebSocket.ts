import { useState, useEffect, useCallback, useRef } from 'react';
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
  area: string | null;
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
  area: string | null;
  interlock_groups: string[];
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
  step?: number | null;  // Step value for numeric inputs
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

export interface GroupState {
  id: string;
  name: string;
  state: string;
  type: string;
  timestamp: number | null;
}

export interface GroupEvent {
  event_type: 'group';
  entity_id: string;
  state: GroupState;
}

export interface ConfigReloadEvent {
  event_type: 'config_reload';
  sections: string[];
}

export type StateUpdate = InputEvent | OutputEvent | SensorEvent | CoverEvent | ModbusDeviceEvent | GroupEvent | ConfigReloadEvent;

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

export function isGroupEvent(data: StateUpdate): data is GroupEvent {
  return data.event_type === 'group';
}

export function isConfigReloadEvent(data: StateUpdate): data is ConfigReloadEvent {
  return data.event_type === 'config_reload';
}

// Singleton WebSocket instance and listeners
let globalWs: WebSocket | null = null;
let globalMessageListeners = new Set<(message: StateUpdate) => void>();
let globalConnectionStateListeners = new Set<(connected: boolean) => void>();
let globalConnecting = false;
let globalPingInterval: number | null = null;
let globalReconnectAttempts = 0;
let globalReconnectTimeout: number | null = null;
const MAX_RECONNECT_ATTEMPTS = 30;
const INITIAL_RECONNECT_DELAY = 1000; // Start with 1 second
const MAX_RECONNECT_DELAY = 30000; // Max 30 seconds
const PING_INTERVAL = 15000; // 15 seconds - shorter for mobile browsers
let activeConnections = 0;
let globalIsConnected = false;

export const closeWebSocket = () => {
  if (globalWs) {
    globalWs.close();
    globalWs = null;
  }
  if (globalPingInterval) {
    clearInterval(globalPingInterval);
    globalPingInterval = null;
  }
  if (globalReconnectTimeout) {
    clearTimeout(globalReconnectTimeout);
    globalReconnectTimeout = null;
  }
  globalMessageListeners.clear();
  globalConnectionStateListeners.clear();
  globalConnecting = false;
  globalReconnectAttempts = 0;
  globalIsConnected = false;
  activeConnections = 0;
};

const notifyConnectionState = (connected: boolean) => {
  globalIsConnected = connected;
  globalConnectionStateListeners.forEach((listener) => {
    try {
      listener(connected);
    } catch (e) {
      console.error('Error in connection state listener:', e);
    }
  });
};

// Request full state resync from server via WebSocket
export const requestStateResync = () => {
  if (globalWs?.readyState === WebSocket.OPEN) {
    console.log('Requesting state resync from server...');
    globalWs.send('request_state');
  }
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
    
    console.log('🔌 WebSocket connecting to:', wsUrl);
    console.log('🔑 Auth required:', isAuthRequired);
    console.log('🎫 Token present:', !!token);
    console.log('📡 Protocols:', protocols);
    
    // Create WebSocket with protocol
    globalWs = new WebSocket(wsUrl, protocols);

    globalWs.onopen = () => {
      console.log('WebSocket connection established successfully');
      setError(null);
      globalConnecting = false;
      globalReconnectAttempts = 0;
      notifyConnectionState(true);

      // Start ping interval with shorter interval for mobile browsers
      if (globalPingInterval) {
        clearInterval(globalPingInterval);
      }
      globalPingInterval = window.setInterval(() => {
        if (globalWs?.readyState === WebSocket.OPEN) {
          try {
            globalWs.send('ping');
          } catch (e) {
            console.error('Error sending ping:', e);
          }
        }
      }, PING_INTERVAL);
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

    globalWs.onclose = (event) => {
      console.log(`WebSocket closed with code ${event.code}, reason: ${event.reason}`);
      
      if (globalPingInterval) {
        clearInterval(globalPingInterval);
        globalPingInterval = null;
      }

      if (globalReconnectTimeout) {
        clearTimeout(globalReconnectTimeout);
        globalReconnectTimeout = null;
      }

      globalWs = null;
      globalConnecting = false;
      notifyConnectionState(false);

      if (activeConnections > 0 && globalReconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
        const delay = Math.min(
          INITIAL_RECONNECT_DELAY * Math.pow(2, globalReconnectAttempts),
          MAX_RECONNECT_DELAY
        );
        console.log(`WebSocket closed. Reconnecting in ${delay}ms (attempt ${globalReconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS})...`);
        globalReconnectAttempts++;
        globalReconnectTimeout = window.setTimeout(() => {
          setupWebSocket(setError, isAuthRequired, isApiAvailable);
        }, delay);
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

export function useWebSocket() {
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const { isAuthRequired, isAuthenticated } = useAuth();
  const { isApiAvailable } = useApiAvailability();

  // Track if this is the first mount
  const isFirstMount = useRef(true);

  // Sync connection state
  useEffect(() => {
    const unsubscribe = addConnectionStateListener(setIsConnected);
    setIsConnected(globalIsConnected);
    return unsubscribe;
  }, []);

  useEffect(() => {
    // Don't attempt to connect if API is not available
    if (!isApiAvailable) {
      return;
    }

    // Don't attempt to connect if auth is required but user is not authenticated
    if (isAuthRequired && !isAuthenticated) {
      console.log('WebSocket: Auth required but user not authenticated, skipping connection');
      return;
    }

    // Only increment on first mount to avoid multiple connections
    if (isFirstMount.current) {
      activeConnections++;
      isFirstMount.current = false;
    }

    console.log('Setting up WebSocket connection, API available:', isApiAvailable);

    const connect = () => {
      setupWebSocket(setError, isAuthRequired, isApiAvailable);
    };

    // If WebSocket is already connected, don't reconnect
    if (globalWs?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected, skipping reconnect');
      return;
    }

    // Add a small delay before the initial connection attempt
    const initialConnectTimeout = setTimeout(connect, 500);

    return () => {
      clearTimeout(initialConnectTimeout);
      // Don't close WebSocket on dependency changes, only on unmount
    };
  }, [isAuthRequired, isAuthenticated, isApiAvailable]);

  // Separate cleanup effect that only runs on unmount
  useEffect(() => {
    return () => {
      activeConnections--;
      if (activeConnections === 0) {
        closeWebSocket();
      }
    };
  }, []);

  const addMessageListener = useCallback((callback: (message: StateUpdate) => void) => {
    globalMessageListeners.add(callback);
    return () => {
      globalMessageListeners.delete(callback);
    };
  }, []);

  const addConnectionStateListener = useCallback((callback: (connected: boolean) => void) => {
    globalConnectionStateListeners.add(callback);
    return () => {
      globalConnectionStateListeners.delete(callback);
    };
  }, []);

  return { error, addMessageListener, isConnected, addConnectionStateListener };
}
