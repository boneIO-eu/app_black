import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { createContext, useEffect, useState } from 'react';
import ConfigEditor from './components/ConfigEditor';
import LogViewer from './components/LogViewer';
import OutputsView from './components/OutputsView';
import InputsView from './components/InputsView';
import SensorView from './components/SensorView';
import HelpView from './components/HelpView';
import LoginView from './components/LoginView';
import Layout from './components/Layout';
import { useWebSocket, StateUpdate, isCoverState } from './hooks/useWebSocket';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { useApiAvailability } from './hooks/useApiAvailability';
import NotAvailable from './components/NotAvailable';
// import UISettings from './components/UISettings/UISettings';

export const WebSocketContext = createContext<{
  outputs: StateUpdate['data'][];
  inputs: StateUpdate['data'][];
  sensors: StateUpdate['data'][];
  covers: StateUpdate['data'][];
}>({
  outputs: [],
  inputs: [],
  sensors: [],
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
  const [outputs, setOutputs] = useState<StateUpdate['data'][]>([]);
  const [inputs, setInputs] = useState<StateUpdate['data'][]>([]);
  const [sensors, setSensors] = useState<StateUpdate['data'][]>([]);
  const [covers, setCovers] = useState<StateUpdate['data'][]>([]);
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
      setCovers([]);
      return;
    }

    // Only set up listeners if authenticated or auth not required
    if (isAuthenticated || !isAuthRequired) {
      const unsubscribe = addMessageListener((message: StateUpdate) => {
        if (message.type === 'output') {
          setOutputs(prev => {
            const index = prev.findIndex(o => o.name === message.data.name);
            if (index >= 0) {
              const prevOutput = prev[index];
              if (prevOutput.state === message.data.state) {
                return prev; // No change needed
              }
              const newOutputs = [...prev];
              newOutputs[index] = message.data;
              return newOutputs;
            }
            return [...prev, message.data];
          });
        } else if (message.type === 'input') {
          setInputs(prev => {
            const index = prev.findIndex(i => i.name === message.data.name);
            if (index >= 0) {
              const prevInput = prev[index];
              if (prevInput.state === message.data.state) {
                return prev; // No change needed
              }
              const newInputs = [...prev];
              newInputs[index] = message.data;
              return newInputs;
            }
            return [...prev, message.data];
          });
        } else if (message.type === 'modbus_device' || message.type === 'sensor') {
          setSensors(prev => {
            const index = prev.findIndex(s => s.name === message.data.name);
            if (index >= 0) {
              const prevSensor = prev[index];
              if (prevSensor.state === message.data.state) {
                return prev; // No change needed
              }
              const newSensors = [...prev];
              newSensors[index] = message.data; 
              return newSensors;
            }
            return [...prev, message.data];
          });
        } else if (message.type === 'cover') {
          setCovers(prev => {
            const index = prev.findIndex(c => c.name === message.data.name);
            if (index >= 0) {
              const prevCover = prev[index];
              if (isCoverState(prevCover) && isCoverState(message.data) && 
                  prevCover.state === message.data.state && 
                  prevCover.position === message.data.position && 
                  prevCover.tilt === message.data.tilt &&
                  prevCover.current_operation === message.data.current_operation) {
                return prev; // No change needed
              }
              const newCovers = [...prev];
              newCovers[index] = message.data;
              return newCovers;
            }
            return [...prev, message.data];
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
    <WebSocketContext.Provider value={{ outputs, inputs, sensors, covers }}>
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
        {/* <Route path="/settings" element={
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
        } /> */}
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
