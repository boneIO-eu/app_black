import { useContext, memo, useState, useEffect, useRef, useCallback } from 'react';
import { WebSocketContext } from '../App';
import { formatTimestamp } from '../utils/formatters';
import ViewToggle from './ViewToggle';
import { isInputEvent, InputEvent } from '../hooks/useWebSocket';
import clsx from 'clsx';
import { useTranslation } from '../hooks/useTranslation';

interface ToastNotification {
  id: string;
  message: string;
  type: string;
}

// Separate component for individual input
const InputItem = memo(({ inputEvent, isGrid, t }: {
  inputEvent: InputEvent;
  isGrid: boolean;
  t: (key: string) => string;
}) => (
  <div
    className={`bg-base-200 text-secondary-content shadow-sm rounded-lg p-4 ${isGrid ? 'border-l-4' : 'border-l-8'} border-blue-500`}
  >
    <div className={`flex ${isGrid ? 'justify-between items-start' : 'flex-col gap-2'}`}>
      <div>
        <h3 className="font-semibold text-lg">{inputEvent.state.name}</h3>
        <p className="text-xs text-gray-500">{inputEvent.entity_id}</p>
        <p className="text-sm">{t('inputs.type')}: {inputEvent.state.type === "input" ? t('inputs.event_entity') : t('inputs.binary_sensor')}</p>
        <p className="text-xs text-gray-400">{t('inputs.area')}: {inputEvent.state.area || t('inputs.no_area')}</p>
      </div>
      <div className={`${isGrid ? 'text-right' : ''}`}>
        <span
          className={clsx('px-4 py-2 rounded-lg font-semibold',
            inputEvent.state.state === 'ON' ? 'bg-primary text-white' :
            inputEvent.state.state === 'single' ? 'bg-success text-black' :
            inputEvent.state.state === 'double' ? 'bg-warning text-black' :
            inputEvent.state.state === 'long' ? 'bg-info text-white' :
            inputEvent.state.state === 'pressed' ? 'bg-success text-black' :
            inputEvent.state.state === 'released' ? 'bg-warning text-black' :
            'bg-base-200 text-base-content'
          )}
        >
          {inputEvent.state.state}
        </span>
        <p className="text-gray-500 text-xs mt-2">
          {formatTimestamp(inputEvent.state.timestamp)}
        </p>
      </div>
    </div>
  </div>
));

export default function InputsView() {
  const { t } = useTranslation();
  const { inputs } = useContext(WebSocketContext);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('inputViewMode');
    return saved ? saved === 'grid' : true;
  });
  const [toasts, setToasts] = useState<ToastNotification[]>([]);
  const prevInputsRef = useRef<Map<string, string>>(new Map());

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('inputViewMode', gridView ? 'grid' : 'list');
  };

  // Add toast notification
  const addToast = useCallback((message: string, type: string) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts(prev => [...prev, { id, message, type }]);
    // Auto-remove after 3 seconds
    setTimeout(() => {
      setToasts(prev => prev.filter(toast => toast.id !== id));
    }, 3000);
  }, []);

  // Filter inputs to only include InputState objects
  const validInputs = inputs.filter(isInputEvent);

  // Initialize prevInputsRef on first render (to avoid showing toast on page load)
  const isInitializedRef = useRef(false);

  // Detect input state changes and show toast
  useEffect(() => {
    const eventTypes = ['single', 'double', 'long', 'pressed', 'released', 'triple', 'quadruple'];
    
    // On first render, just populate the ref without showing toasts
    if (!isInitializedRef.current) {
      validInputs.forEach((inputEvent: InputEvent) => {
        prevInputsRef.current.set(inputEvent.entity_id, inputEvent.state.state);
      });
      isInitializedRef.current = true;
      return;
    }
    
    validInputs.forEach((inputEvent: InputEvent) => {
      const prevState = prevInputsRef.current.get(inputEvent.entity_id);
      const currentState = inputEvent.state.state;
      
      // Only show toast for event types (not ON/OFF binary states)
      if (prevState !== currentState && eventTypes.includes(currentState)) {
        addToast(
          `${t('inputs.detected')} ${currentState} ${t('inputs.in')} ${inputEvent.state.name}`,
          currentState
        );
      }
      
      prevInputsRef.current.set(inputEvent.entity_id, currentState);
    });
  }, [validInputs, addToast, t]);
  
  if (validInputs.length === 0) {
    return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">{t('inputs.title')}</h2>
      </div>
      <div>
        No inputs configured.
      </div>
    </div>)
  }
  
  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">{t('inputs.title')}</h2>
        <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
      </div>
      <div className={isGrid 
        ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
        : "flex flex-col gap-4"
      }>
        {validInputs.map((inputEvent: InputEvent) => (
          <InputItem key={inputEvent.entity_id} inputEvent={inputEvent} isGrid={isGrid} t={t} />
        ))}
      </div>

      {/* Toast notifications for input events */}
      {toasts.length > 0 && (
        <div className="toast toast-top toast-end z-50">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={clsx(
                'alert shadow-lg animate-fade-in',
                toast.type === 'single' && 'alert-success',
                toast.type === 'double' && 'alert-warning',
                toast.type === 'long' && 'alert-info',
                toast.type === 'triple' && 'alert-secondary',
                toast.type === 'pressed' && 'alert-success',
                toast.type === 'released' && 'alert-warning',
                !['single', 'double', 'long', 'triple', 'pressed', 'released'].includes(toast.type) && 'alert-info'
              )}
            >
              <span>{toast.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
