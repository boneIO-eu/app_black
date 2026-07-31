import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { createContext, useEffect, useRef, useState, lazy, Suspense } from 'react';
import { getRouterBasename } from './api/basePath';

// Lazy-load all route-level components for code splitting.
// Only Layout, auth, and context providers are eagerly loaded since they're
// needed on every page. Everything else loads on-demand when the route is visited.
const lazyImports = {
  ConfigEditor: () => import('./components/ConfigEditor'),
  LogViewer: () => import('./components/LogViewer'),
  OutputsView: () => import('./components/OutputsView'),
  InputsView: () => import('./components/InputsView'),
  SensorView: () => import('./components/SensorView'),
  ModbusView: () => import('./components/ModbusView'),
  Tools: () => import('./components/Tools'),
  HelpView: () => import('./components/HelpView'),
  UISettings: () => import('./components/UISettings/UISettings'),
  SystemState: () => import('./components/UISettings/SystemState'),
  NodeRedView: () => import('./components/NodeRedView'),
  TemplatesView: () => import('./components/TemplatesView'),
} as const;

const ConfigEditor = lazy(lazyImports.ConfigEditor);
const LogViewer = lazy(lazyImports.LogViewer);
const OutputsView = lazy(lazyImports.OutputsView);
const InputsView = lazy(lazyImports.InputsView);
const SensorView = lazy(lazyImports.SensorView);
const ModbusView = lazy(lazyImports.ModbusView);
const Tools = lazy(lazyImports.Tools);
const HelpView = lazy(lazyImports.HelpView);
const UISettings = lazy(lazyImports.UISettings);
const SystemState = lazy(lazyImports.SystemState);
const NodeRedView = lazy(lazyImports.NodeRedView);
const TemplatesView = lazy(lazyImports.TemplatesView);

/**
 * Prefetch all lazy route chunks in the background after initial render.
 * Uses requestIdleCallback (with setTimeout fallback) to avoid blocking
 * the main thread. ConfigEditor/Monaco is excluded since it's 4MB and
 * only needed when user explicitly visits the YAML editor.
 */
function prefetchRouteChunks() {
  const schedule = window.requestIdleCallback || ((cb: () => void) => setTimeout(cb, 100));
  // Prefetch everything except ConfigEditor (Monaco is too large)
  const toPrefetch = [
    lazyImports.InputsView,
    lazyImports.SensorView,
    lazyImports.ModbusView,
    lazyImports.UISettings,
    lazyImports.LogViewer,
    lazyImports.Tools,
    lazyImports.TemplatesView,
    lazyImports.HelpView,
    lazyImports.SystemState,
    lazyImports.NodeRedView,
  ];
  // Stagger imports so they don't all fire at once
  toPrefetch.forEach((importFn, i) => {
    schedule(() => {
      importFn().catch(() => {/* ignore prefetch errors */});
    }, { timeout: 1000 + i * 200 });
  });
}

import LoginView from './components/LoginView';
import Layout from './components/Layout';
import { useWebSocket, StateUpdate, isCoverEvent, InputEvent, OutputEvent, SensorEvent, CoverEvent, ModbusDeviceEvent, GroupEvent, isOutputEvent, isGroupEvent, isConfigReloadEvent } from './hooks/useWebSocket';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { AppInitProvider, useAppInit } from './contexts/AppInitContext';
import NotAvailable from './components/NotAvailable';
import { ConfigProvider } from './contexts/ConfigContext';
import { TranslationProvider } from './contexts/TranslationContext';
import { appendModbusHistoryPointToStorage, clearModbusHistoryStorage } from './hooks/useModbusHistory';

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

// Protected route component
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading: authLoading, isAuthRequired } = useAuth();
  const { isApiAvailable, isLoading: initLoading } = useAppInit();

  // API confirmed unavailable after retries — show error screen
  if (!isApiAvailable && !initLoading) {
    return <NotAvailable />
  }

  // Still loading init data or auth — show spinner inside layout shell
  if (initLoading || authLoading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-full min-h-[60vh]">
          <span className="loading loading-spinner loading-lg text-primary"></span>
        </div>
      </Layout>
    );
  }
  
  if (!isAuthenticated && isAuthRequired) {
    return <LoginView />
  }
  
  return <>{children}</>;
}

function AppContent() {
  const [outputs, setOutputs] = useState<OutputEvent[]>([]);
  const [inputs, setInputs] = useState<InputEvent[]>([]);
  const [sensors, setSensors] = useState<SensorEvent[]>([]);
  const [modbus_devices, setModbusDevices] = useState<ModbusDeviceEvent[]>([]);
  const [covers, setCovers] = useState<CoverEvent[]>([]);
  const [groups, setGroups] = useState<GroupEvent[]>([]);
  const { isAuthenticated, isAuthRequired } = useAuth();
  const { isApiAvailable } = useAppInit();
  const { error, addMessageListener, addConnectionStateListener } = useWebSocket();

  // Select all text in number inputs on focus for better mobile UX.
  // Without this, tapping a number input on mobile places the cursor at the end,
  // forcing users to manually delete the old value before typing a new one.
  useEffect(() => {
    const handler = (e: FocusEvent) => {
      const target = e.target;
      if (target instanceof HTMLInputElement && target.type === 'number') {
        // requestAnimationFrame ensures the selection happens after the browser
        // has finished its default focus handling (needed for iOS Safari)
        requestAnimationFrame(() => target.select());
      }
    };
    document.addEventListener('focusin', handler);
    return () => document.removeEventListener('focusin', handler);
  }, []);

  // Prefetch other route chunks in the background after initial render.
  // Uses requestIdleCallback so prefetching starts as soon as the browser
  // is idle (often < 1s), rather than waiting a fixed delay.
  // If the user navigates before prefetch completes, React.lazy still loads
  // the chunk on-demand with a Suspense spinner — prefetch just makes it instant.
  useEffect(() => {
    const idle = window.requestIdleCallback || ((cb: () => void) => setTimeout(cb, 1000));
    const handle = idle(() => prefetchRouteChunks(), { timeout: 5000 });
    return () => {
      if (window.cancelIdleCallback) {
        window.cancelIdleCallback(handle as number);
      }
    };
  }, []);

  // Listen to WebSocket connection state changes and request state resync on reconnect
  // Note: Initial state is sent automatically by backend on WebSocket connect
  // This handles reconnection scenarios where we need to resync
  useEffect(() => {
    if (!isAuthenticated && isAuthRequired) return;
    if (!isApiAvailable) return;
    
    const unsubscribe = addConnectionStateListener((connected) => {
      if (connected) {
        // Backend sends initial state on connect, but for reconnects we may need to request it
        // The backend will send all states via WebSocket messages
        console.log('WebSocket connected/reconnected');
      }
    });
    
    return unsubscribe;
  }, [addConnectionStateListener, isAuthenticated, isAuthRequired, isApiAvailable]);

  // Use a ref to hold the latest message handler so the listener subscription
  // never needs to be torn down and re-created. This eliminates the race window
  // where messages are lost during React's cleanup→setup transition.
  const messageHandlerRef = useRef<((message: StateUpdate) => void) | null>(null);

  // Determine whether we should process incoming messages
  const shouldProcess = (isAuthenticated || !isAuthRequired) && isApiAvailable;

  // Update the handler ref whenever dependencies change
  useEffect(() => {
    if (!shouldProcess) {
      // Clear states when not authenticated / API not available
      messageHandlerRef.current = null;
      setOutputs([]);
      setInputs([]);
      setSensors([]);
      setModbusDevices([]);
      setCovers([]);
      setGroups([]);
      return;
    }

    // Set the handler that the stable listener will delegate to
    messageHandlerRef.current = (message: StateUpdate) => {
      if (isOutputEvent(message)) {
        setOutputs(prev => {
          const index = prev.findIndex(o => o.entity_id === message.entity_id);
          if (index >= 0) {
            const prevOutput = prev[index];
            // Check if state or name changed
            if (prevOutput.state.state === message.state.state &&
                prevOutput.state.name === message.state.name &&
                prevOutput.state.brightness === message.state.brightness &&
                prevOutput.state.timestamp === message.state.timestamp) {
              return prev; // No change needed
            }
            const newOutputs = [...prev];
            newOutputs[index] = message;
            return newOutputs;
          }
          return [...prev, message];
        });
      } else if (message.event_type === 'input') {
        setInputs(prev => {
          const index = prev.findIndex(i => i.entity_id === message.entity_id);
          if (index >= 0) {
            const prevInput = prev[index];
            // Check both state and timestamp to detect duplicate events
            if (prevInput.state.state === message.state.state && 
                prevInput.state.timestamp === message.state.timestamp) {
              return prev; // No change needed
            }
            const newInputs = [...prev];
            newInputs[index] = message;
            return newInputs;
          }
          return [...prev, message];
        });
      } else if (message.event_type === 'modbus_device') {
        appendModbusHistoryPointToStorage(message.state);
        setModbusDevices(prev => {
          const index = prev.findIndex(s => s.entity_id === message.entity_id);
          if (index >= 0) {
            const prevDevice = prev[index];
            if (prevDevice.state.state === message.state.state &&
                prevDevice.state.timestamp === message.state.timestamp) {
              return prev; // No change needed
            }
            const newDevices = [...prev];
            newDevices[index] = message; 
            return newDevices;
          }
          return [...prev, message];
        });
      } else if (message.event_type === 'sensor') {
        setSensors(prev => {
          const index = prev.findIndex(s => s.entity_id === message.entity_id);
          if (index >= 0) {
            const prevSensor = prev[index];
            if (prevSensor.state.state === message.state.state &&
                prevSensor.state.timestamp === message.state.timestamp) {
              return prev; // No change needed
            }
            const newSensors = [...prev];
            newSensors[index] = message; 
            return newSensors;
          }
          return [...prev, message];
        });
      } else if (message.event_type === 'cover') {
        setCovers(prev => {
          const index = prev.findIndex(c => c.state.name === message.state.name);
          if (index >= 0) {
            const prevCover = prev[index];
            if (isCoverEvent(prevCover) && isCoverEvent(message) && 
                prevCover.state.state === message.state.state && 
                prevCover.state.position === message.state.position && 
                prevCover.state.tilt === message.state.tilt &&
                prevCover.state.current_operation === message.state.current_operation) {
              return prev; // No change needed
            }
            const newCovers = [...prev];
            newCovers[index] = message;
            return newCovers;
          }
          return [...prev, message];
        });
      } else if (isGroupEvent(message)) {
        setGroups(prev => {
          const index = prev.findIndex(g => g.entity_id === message.entity_id);
          if (index >= 0) {
            const prevGroup = prev[index];
            // Check if state or name changed
            if (prevGroup.state.state === message.state.state &&
                prevGroup.state.name === message.state.name) {
              return prev; // No change needed
            }
            const newGroups = [...prev];
            newGroups[index] = message;
            return newGroups;
          }
          return [...prev, message];
        });
      } else if (isConfigReloadEvent(message)) {
        // Config was reloaded - clear old states
        // New states will be sent by backend after reload
        console.log('🔄 Config reload event received, clearing states for sections:', message.sections);
        const sections = message.sections;
        
        if (sections.includes('all') || sections.includes('output') || sections.includes('output_group')) {
          setOutputs([]);
          setGroups([]);
        }
        if (sections.includes('all') || sections.includes('cover')) {
          setCovers([]);
        }
        if (sections.includes('all') || sections.includes('input') || sections.includes('event') || sections.includes('binary_sensor') || sections.includes('remote_devices')) {
          setInputs([]);
        }
        if (sections.includes('all') || sections.includes('modbus_devices')) {
          setModbusDevices([]);
          clearModbusHistoryStorage();
        }
        if (sections.includes('all') || sections.includes('modbus_devices') || sections.includes('sensor') || sections.includes('virtual_energy_sensor')) {
          setSensors([]);
        }
      }
    };
  }, [isAuthenticated, isAuthRequired, isApiAvailable]);

  // Subscribe a single, stable listener on mount that delegates to the ref.
  // This listener is NEVER unsubscribed during the component's lifetime,
  // so there is no window where messages can be lost.
  useEffect(() => {
    const stableListener = (message: StateUpdate) => {
      messageHandlerRef.current?.(message);
    };
    const unsubscribe = addMessageListener(stableListener);
    return () => {
      unsubscribe();
    };
  }, [addMessageListener]);

  if (!isApiAvailable){
    return <NotAvailable />
  }

  if (error && (isAuthenticated || !isAuthRequired)) {
    return <div>Error: {error}</div>;
  }

  return (
    <WebSocketContext.Provider value={{ outputs, inputs, sensors, modbus_devices, covers, groups }}>
      <Suspense fallback={
        <Layout>
          <div className="flex items-center justify-center h-full min-h-[60vh]">
            <span className="loading loading-spinner loading-lg text-primary"></span>
          </div>
        </Layout>
      }>
      <Routes>
        <Route path="/" element={
          <ProtectedRoute>
            <Layout>
              <OutputsView error={error} />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/inputs" element={
          <ProtectedRoute>
            <Layout>
              <InputsView />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/config" element={
          <ProtectedRoute>
            <Layout configEditor={true}>
              <ConfigEditor />
            </Layout>
          </ProtectedRoute>
        } />
        {/* ConfigEditor2 (UISettings) - Temporarily disabled due to JSON Schema issues */}
        {/* TODO: Re-enable when JSON Schema validation problems are resolved */}
        <Route path="/settings" element={
          <ProtectedRoute>
            <Layout configEditor>
              <UISettings />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/settings/:section" element={
          <ProtectedRoute>
            <Layout configEditor>
              <UISettings />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/logs" element={
          <ProtectedRoute>
            <Layout>
              <LogViewer />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/sensors" element={
          <ProtectedRoute>
            <Layout>
              <SensorView />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/modbus" element={
          <ProtectedRoute>
            <Layout>
              <ModbusView />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/templates" element={
          <ProtectedRoute>
            <Layout>
              <TemplatesView />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/tools" element={
          <ProtectedRoute>
            <Layout>
              <Tools />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/help" element={
          <ProtectedRoute>
            <Layout>
              <HelpView />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/system" element={
          <ProtectedRoute>
            <Layout>
              <SystemState />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/nodered" element={
          <ProtectedRoute>
            <Layout>
              <NodeRedView />
            </Layout>
          </ProtectedRoute>
        } />
      </Routes>
      </Suspense>
    </WebSocketContext.Provider>
  );
}

export default function App() {
  return (
    <Router basename={getRouterBasename()}>
      <AppInitProvider>
        <AuthProvider>
          <ConfigProvider>
            <TranslationProvider>
              <AppContent />
            </TranslationProvider>
          </ConfigProvider>
        </AuthProvider>
      </AppInitProvider>
    </Router>
  );
}
