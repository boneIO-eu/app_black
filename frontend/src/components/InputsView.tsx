import { useContext, memo, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { WebSocketContext } from '../App';
import { formatTimestamp } from '../utils/formatters';
import ViewToggle from './ViewToggle';
import { isInputEvent, InputEvent } from '../hooks/useWebSocket';
import clsx from 'clsx';
import { useTranslation } from '../hooks/useTranslation';
import { FaSortAmountDown, FaSortAlphaDown, FaClock, FaCopy, FaCog } from 'react-icons/fa';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

interface ToastNotification {
  id: string;
  message: string;
  type: string;
  inputName?: string;
}

type SortMode = 'name' | 'recent';

// Separate component for individual input
const InputItem = memo(({ inputEvent, isGrid, t, isHighlighted, onCopy, onLongPress }: {
  inputEvent: InputEvent;
  isGrid: boolean;
  t: (key: string) => string;
  isHighlighted?: boolean;
  onCopy: (name: string) => void;
  onLongPress: (inputEvent: InputEvent) => void;
}) => {
  const longPressTimer = useRef<NodeJS.Timeout | null>(null);
  const isLongPress = useRef(false);

  const handlePressStart = () => {
    isLongPress.current = false;
    longPressTimer.current = setTimeout(() => {
      isLongPress.current = true;
      onLongPress(inputEvent);
    }, 500);
  };

  const handlePressEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  const handleClick = () => {
    if (!isLongPress.current) {
      onCopy(inputEvent.state.name);
    }
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    e.preventDefault();
    handlePressStart();
  };

  return (
    <div
      onClick={handleClick}
      onMouseDown={handlePressStart}
      onMouseUp={handlePressEnd}
      onMouseLeave={handlePressEnd}
      onTouchStart={handleTouchStart}
      onTouchEnd={handlePressEnd}
      onContextMenu={(e) => e.preventDefault()}
      className={clsx(
        'bg-base-200 text-secondary-content shadow-sm rounded-lg p-4 transition-all duration-500 cursor-pointer hover:bg-base-300 select-none touch-none',
        isGrid ? 'border-l-4' : 'border-l-8',
        'border-blue-500',
        isHighlighted && 'ring-4 ring-primary shadow-lg shadow-primary/30 scale-[1.02]'
      )}
      title={t('inputs.long_press_to_edit')}
      style={{ WebkitTouchCallout: 'none', WebkitUserSelect: 'none' }}
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
  );
});

export default function InputsView() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { inputs } = useContext(WebSocketContext);
  const [isGrid, setIsGrid] = useState(() => {
    const saved = localStorage.getItem('inputViewMode');
    return saved ? saved === 'grid' : true;
  });
  const [sortMode, setSortMode] = useState<SortMode>(() => {
    const saved = localStorage.getItem('inputSortMode');
    return (saved as SortMode) || 'name';
  });
  const [toasts, setToasts] = useState<ToastNotification[]>([]);
  const prevInputsRef = useRef<Map<string, { state: string; timestamp: number }>>(new Map());
  const [recentlyChanged, setRecentlyChanged] = useState<Set<string>>(new Set());

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('inputViewMode', gridView ? 'grid' : 'list');
  };

  const handleSortChange = (mode: SortMode) => {
    setSortMode(mode);
    localStorage.setItem('inputSortMode', mode);
  };

  // Add toast notification with max 4 toasts limit
  const addToast = useCallback((message: string, type: string, inputName?: string) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts(prev => {
      const newToasts = [...prev, { id, message, type, inputName }];
      // Keep only last 4 toasts (remove oldest if exceeding limit)
      return newToasts.slice(-4);
    });
    // Auto-remove after 3 seconds
    setTimeout(() => {
      setToasts(prev => prev.filter(toast => toast.id !== id));
    }, 3000);
  }, []);

  // Copy input name to clipboard
  const [copiedName, setCopiedName] = useState<string | null>(null);
  
  const copyToClipboard = useCallback((name: string) => {
    navigator.clipboard.writeText(name).then(() => {
      setCopiedName(name);
      setTimeout(() => setCopiedName(null), 1500);
    });
  }, []);

  // Long press dialog state
  const [longPressDialog, setLongPressDialog] = useState<{ open: boolean; inputEvent: InputEvent | null }>({
    open: false,
    inputEvent: null
  });

  const handleLongPress = useCallback((inputEvent: InputEvent) => {
    setLongPressDialog({ open: true, inputEvent });
  }, []);

  const handleGoToSettings = useCallback(() => {
    if (!longPressDialog.inputEvent) return;
    // Use entity_id for filtering instead of name to avoid duplicates
    const inputId = longPressDialog.inputEvent.entity_id;
    const inputType = longPressDialog.inputEvent.state.type;
    // Navigate to settings with edit query param
    const section = inputType === 'input' ? 'event' : 'binary_sensor';
    navigate(`/settings/${section}?edit=${encodeURIComponent(inputId)}`);
    setLongPressDialog({ open: false, inputEvent: null });
  }, [longPressDialog.inputEvent, navigate]);

  // Filter inputs to only include InputState objects
  const validInputs = inputs.filter(isInputEvent);

  // Initialize prevInputsRef on first render (to avoid showing toast on page load)
  const isInitializedRef = useRef(false);

  // Detect input state changes, show toast and highlight
  useEffect(() => {
    const toastEventTypes = ['single', 'double', 'long', 'pressed', 'released', 'triple', 'double_then_long', 'single_then_long', 'double_then_single'];
    const highlightEventTypes = ['single', 'double', 'long', 'pressed', 'released', 'triple', 'double_then_long', 'single_then_long', 'double_then_single', 'ON', 'OFF'];
    const now = Date.now() / 1000; // Current time in seconds
    
    // On first render, just populate the ref without showing toasts
    if (!isInitializedRef.current) {
      validInputs.forEach((inputEvent: InputEvent) => {
        prevInputsRef.current.set(inputEvent.entity_id, {
          state: inputEvent.state.state,
          timestamp: inputEvent.state.timestamp
        });
      });
      isInitializedRef.current = true;
      return;
    }
    
    validInputs.forEach((inputEvent: InputEvent) => {
      const prevData = prevInputsRef.current.get(inputEvent.entity_id);
      const currentState = inputEvent.state.state;
      const currentTimestamp = inputEvent.state.timestamp;
      
      // Only consider as changed if: we have previous data AND timestamp changed
      // Also check if event is recent (within last 5 seconds) to avoid stale events on page load
      const isRecent = (now - currentTimestamp) < 5;
      const hasChanged = prevData && prevData.timestamp !== currentTimestamp && isRecent;
      
      // Show toast for event types (not ON/OFF binary states)
      if (hasChanged && toastEventTypes.includes(currentState)) {
        const time = new Date(currentTimestamp * 1000).toLocaleTimeString('pl-PL', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit'
        });
        addToast(
          `[${time}] ${t('inputs.detected')} ${currentState} ${t('inputs.in')} ${inputEvent.state.name}`,
          currentState,
          inputEvent.state.name
        );
      }
      
      // Highlight changed inputs
      if (hasChanged && highlightEventTypes.includes(currentState)) {
        setRecentlyChanged(prev => new Set(prev).add(inputEvent.entity_id));
        setTimeout(() => {
          setRecentlyChanged(prev => {
            const next = new Set(prev);
            next.delete(inputEvent.entity_id);
            return next;
          });
        }, 2000);
      }
      
      // Always update the ref (even for new items without prevData)
      prevInputsRef.current.set(inputEvent.entity_id, {
        state: currentState,
        timestamp: currentTimestamp
      });
    });
  }, [validInputs, addToast, t]);

  // Sort inputs based on selected mode
  const sortedInputs = useMemo(() => {
    const sorted = [...validInputs];
    if (sortMode === 'recent') {
      sorted.sort((a, b) => b.state.timestamp - a.state.timestamp);
    } else {
      sorted.sort((a, b) => (a.state.name || '').localeCompare(b.state.name || ''));
    }
    return sorted;
  }, [validInputs, sortMode]);
  
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
        <div className="flex items-center gap-2">
          {/* Sort dropdown */}
          <div className="dropdown dropdown-end">
            <label tabIndex={0} className="btn btn-sm btn-ghost gap-1">
              {sortMode === 'recent' ? <FaClock /> : <FaSortAlphaDown />}
              <span className="hidden sm:inline">{t(`inputs.sort_${sortMode}`)}</span>
              <FaSortAmountDown className="w-3 h-3" />
            </label>
            <ul tabIndex={0} className="dropdown-content z-1 menu p-2 shadow bg-base-100 rounded-box w-52">
              <li>
                <button 
                  onClick={() => handleSortChange('name')}
                  className={sortMode === 'name' ? 'active' : ''}
                >
                  <FaSortAlphaDown /> {t('inputs.sort_name')}
                </button>
              </li>
              <li>
                <button 
                  onClick={() => handleSortChange('recent')}
                  className={sortMode === 'recent' ? 'active' : ''}
                >
                  <FaClock /> {t('inputs.sort_recent')}
                </button>
              </li>
            </ul>
          </div>
          <ViewToggle isGrid={isGrid} onToggle={handleViewToggle} />
        </div>
      </div>
      <div className={isGrid 
        ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
        : "flex flex-col gap-4"
      }>
        {sortedInputs.map((inputEvent: InputEvent) => (
          <InputItem 
            key={inputEvent.entity_id} 
            inputEvent={inputEvent} 
            isGrid={isGrid} 
            t={t}
            isHighlighted={recentlyChanged.has(inputEvent.entity_id)}
            onCopy={copyToClipboard}
            onLongPress={handleLongPress}
          />
        ))}
      </div>

      {/* Copied feedback */}
      {copiedName && (
        <div className="toast toast-bottom toast-center z-50">
          <div className="alert alert-success shadow-lg">
            <FaCopy className="w-4 h-4" />
            <span>{t('inputs.copied')}: {copiedName}</span>
          </div>
        </div>
      )}

      {/* Toast notifications for input events */}
      {toasts.length > 0 && (
        <div className="toast toast-top toast-end z-50">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              onClick={() => toast.inputName && copyToClipboard(toast.inputName)}
              className={clsx(
                'alert shadow-lg animate-fade-in cursor-pointer hover:opacity-80',
                toast.type === 'single' && 'alert-success',
                toast.type === 'double' && 'alert-warning',
                toast.type === 'long' && 'alert-info',
                toast.type === 'triple' && 'alert-secondary',
                toast.type === 'pressed' && 'alert-success',
                toast.type === 'released' && 'alert-warning',
                !['single', 'double', 'long', 'triple', 'pressed', 'released'].includes(toast.type) && 'alert-info'
              )}
              title={toast.inputName ? t('inputs.click_to_copy') : undefined}
            >
              <span>{toast.message}</span>
            </div>
          ))}
        </div>
      )}

      {/* Long press dialog - go to settings */}
      <Dialog open={longPressDialog.open} onOpenChange={(open) => setLongPressDialog({ open, inputEvent: open ? longPressDialog.inputEvent : null })}>
        <DialogContent className="sm:max-w-md bg-base-200">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FaCog className="w-5 h-5" />
              {t('inputs.go_to_settings')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p>{t('inputs.go_to_settings_confirm')}</p>
            <p className="font-semibold mt-2">{longPressDialog.inputEvent?.state.name}</p>
          </div>
          <DialogFooter className="gap-2">
            <button 
              className="btn btn-ghost" 
              onClick={() => setLongPressDialog({ open: false, inputEvent: null })}
            >
              {t('common.cancel')}
            </button>
            <button 
              className="btn btn-primary" 
              onClick={handleGoToSettings}
            >
              {t('inputs.go_to_settings')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
