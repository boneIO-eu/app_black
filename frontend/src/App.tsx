import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { createContext, useEffect, useState, lazy, Suspense } from 'react';
import { getRouterBasename } from './api/basePath';

// Lazy-load ConfigEditor to keep Monaco out of the initial bundle
const ConfigEditor = lazy(() => import('./components/ConfigEditor'));
import LogViewer from './components/LogViewer';
import OutputsView from './components/OutputsView';
import InputsView from './components/InputsView';
import SensorView from './components/SensorView';
import ModbusView from './components/ModbusView';
import Tools from './components/Tools';
import HelpView from './components/HelpView';
import LoginView from './components/LoginView';
import Layout from './components/Layout';
import { useWebSocket, StateUpdate, isCoverEvent, InputEvent, OutputEvent, SensorEvent, CoverEvent, ModbusDeviceEvent, GroupEvent, isOutputEvent, isGroupEvent, isConfigReloadEvent } from './hooks/useWebSocket';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { useApiAvailability } from './hooks/useApiAvailability';
import NotAvailable from './components/NotAvailable';
import UISettings from './components/UISettings/UISettings';
import SystemState from './components/UISettings/SystemState';
import NodeRedView from './components/NodeRedView';
import TemplatesView from './components/TemplatesView';
import { ConfigProvider } from './contexts/ConfigContext';
import { TranslationProvider } from './contexts/TranslationContext';

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
  const { isAuthenticated, isLoading, isAuthRequired } = useAuth();
  const { isApiAvailable } = useApiAvailability();

  if (!isApiAvailable || isLoading) {
    return <NotAvailable />
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
  const { isApiAvailable } = useApiAvailability();
  const { error, addMessageListener, addConnectionStateListener } = useWebSocket();

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

  useEffect(() => {
    console.log("WebSocket state:", { isAuthenticated, isAuthRequired });
    
    // Clear states when not authenticated and auth is required
    if ((!isAuthenticated && isAuthRequired) || !isApiAvailable) {
      setOutputs([]);
      setInputs([]);
      setSensors([]);
      setModbusDevices([]);
      setCovers([]);
      setGroups([]);
      return;
    }

    // Only set up listeners if authenticated or auth not required
    if (isAuthenticated || !isAuthRequired) {
      const unsubscribe = addMessageListener((message: StateUpdate) => {
        if (isOutputEvent(message)) {
          setOutputs(prev => {
            const index = prev.findIndex(o => o.entity_id === message.entity_id);
            if (index >= 0) {
              const prevOutput = prev[index];
              // Check if state or name changed
              if (prevOutput.state.state === message.state.state &&
                  prevOutput.state.name === message.state.name) {
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
          if (sections.includes('all') || sections.includes('input') || sections.includes('event') || sections.includes('binary_sensor')) {
            setInputs([]);
          }
          if (sections.includes('all') || sections.includes('modbus_devices')) {
            setModbusDevices([]);
          }
          if (sections.includes('all') || sections.includes('modbus_devices') || sections.includes('sensor') || sections.includes('virtual_energy_sensor')) {
            setSensors([]);
          }
        }
      });

      return () => {
        unsubscribe();
      };
    }
  }, [addMessageListener, isAuthenticated, isAuthRequired, isApiAvailable]);

  if (!isApiAvailable){
    return <NotAvailable />
  }

  if (error && (isAuthenticated || !isAuthRequired)) {
    return <div>Error: {error}</div>;
  }

  return (
    <WebSocketContext.Provider value={{ outputs, inputs, sensors, modbus_devices, covers, groups }}>
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
              <Suspense fallback={
                <div className="flex items-center justify-center h-full">
                  <span className="loading loading-spinner loading-lg"></span>
                </div>
              }>
                <ConfigEditor />
              </Suspense>
            </Layout>
          </ProtectedRoute>
        } />
        {/* ConfigEditor2 (UISettings) - Temporarily disabled due to JSON Schema issues */}
        {/* TODO: Re-enable when JSON Schema validation problems are resolved */}
        <Route path="/settings" element={
          <ProtectedRoute>
            <Layout>
              <UISettings />
            </Layout>
          </ProtectedRoute>
        } />
        <Route path="/settings/:section" element={
          <ProtectedRoute>
            <Layout>
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
    </WebSocketContext.Provider>
  );
}

export default function App() {
  return (
    <Router basename={getRouterBasename()}>
      <AuthProvider>
        <ConfigProvider>
          <TranslationProvider>
            <AppContent />
          </TranslationProvider>
        </ConfigProvider>
      </AuthProvider>
    </Router>
  );
}
