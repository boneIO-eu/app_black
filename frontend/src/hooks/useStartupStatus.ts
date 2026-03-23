import { useState, useEffect, useCallback } from 'react';
import { isStartupStatusEvent, StateUpdate, addGlobalMessageListener } from './useWebSocket';

/**
 * Hook that tracks backend startup progress via WebSocket.
 * 
 * Subscribes directly to the global WebSocket message listeners
 * without calling useWebSocket() to avoid interfering with the
 * WebSocket connection lifecycle (activeConnections counter).
 * 
 * Returns the current startup status message and whether startup
 * is still in progress. The banner should be shown while isStarting
 * is true, and hidden (with animation) once complete.
 */
export function useStartupStatus() {
  const [isStarting, setIsStarting] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [statusKey, setStatusKey] = useState('');

  const handleMessage = useCallback((message: StateUpdate) => {
    if (isStartupStatusEvent(message)) {
      if (message.complete) {
        // Brief delay so user sees the transition
        setTimeout(() => {
          setIsStarting(false);
          setStatusMessage('');
          setStatusKey('');
        }, 1500);
      } else {
        setIsStarting(true);
        setStatusMessage(message.message);
        setStatusKey(message.status);
      }
    }
  }, []);

  useEffect(() => {
    const unsubscribe = addGlobalMessageListener(handleMessage);
    return unsubscribe;
  }, [handleMessage]);

  return { isStarting, statusMessage, statusKey };
}
