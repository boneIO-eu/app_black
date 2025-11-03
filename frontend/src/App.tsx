import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { createContext, useEffect, useState } from 'react';
import ConfigEditor from './components/ConfigEditor';
import LogViewer from './components/LogViewer';
import OutputsView from './components/OutputsView';
import InputsView from './components/InputsView';
import SensorView from './components/SensorView';
import ModbusView from './components/ModbusView';
import HelpView from './components/HelpView';
import LoginView from './components/LoginView';
import Layout from './components/Layout';
import { useWebSocket, StateUpdate, isCoverEvent, InputEvent, OutputEvent, SensorEvent, CoverEvent, ModbusDeviceEvent, isOutputEvent } from './hooks/useWebSocket';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { useApiAvailability } from './hooks/useApiAvailability';
import NotAvailable from './components/NotAvailable';
import UISettings from './components/UISettings/UISettings';

export const WebSocketContext = createContext<{
  outputs: OutputEvent[];
  inputs: InputEvent[];
  sensors: SensorEvent[];
  modbus_devices: ModbusDeviceEvent[];
  covers: CoverEvent[];
}>({
  outputs: [],
  inputs: [],
  sensors: [],
  modbus_devices: [],
  covers: [],
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
  const { isAuthenticated, isAuthRequired } = useAuth();
  const { isApiAvailable } = useApiAvailability();
  const { error, addMessageListener } = useWebSocket();

  useEffect(() => {
    console.log("WebSocket state:", { isAuthenticated, isAuthRequired });
    
    // Clear states when not authenticated and auth is required
    if ((!isAuthenticated && isAuthRequired) || !isApiAvailable) {
      setOutputs([]);
      setInputs([]);
      setSensors([]);
      setModbusDevices([]);
      setCovers([]);
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
              if (prevOutput.state.state === message.state.state) {
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
            const index = prev.findIndex(i => i.state.name === message.state.name);
            if (index >= 0) {
              const prevInput = prev[index];
              if (prevInput.state.state === message.state.state) {
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
            const index = prev.findIndex(s => s.state.name === message.state.name);
            if (index >= 0) {
              const prevDevice = prev[index];
              if (prevDevice.state.state === message.state.state) {
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
            const index = prev.findIndex(s => s.state.name === message.state.name);
            if (index >= 0) {
              const prevSensor = prev[index];
              if (prevSensor.state.state === message.state.state) {
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
    <WebSocketContext.Provider value={{ outputs, inputs, sensors, modbus_devices, covers }}>
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
        <Route path="/help" element={
          <ProtectedRoute>
            <Layout>
              <HelpView />
            </Layout>
          </ProtectedRoute>
        } />
      </Routes>
    </WebSocketContext.Provider>
  );
}

export default function App() {
  return (
    <Router>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </Router>
  );
}
