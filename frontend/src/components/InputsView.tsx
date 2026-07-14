import { useContext, memo, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { WebSocketContext } from '../App';
import { formatTimestamp } from '../utils/formatters';
import ViewToggle from './ViewToggle';
import { isInputEvent, InputEvent } from '../hooks/useWebSocket';
import clsx from 'clsx';
import { useTranslation } from '../hooks/useTranslation';
import { copyToClipboard } from '@/utils/clipboard';
import { FaSortAmountDown, FaSortAlphaDown, FaClock, FaCopy, FaCog, FaWifi, FaBolt } from 'react-icons/fa';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LongPressWrapper } from '@/components/ui/LongPressWrapper';
import QuickActionSheet from '@/components/QuickActionSheet';

interface ToastNotification {
  id: string;
  message: string;
  type: string;
  inputName?: string;
  duration?: number;
  entityId?: string;
}

type SortMode = 'name' | 'recent';

// Separate component for duration display - updates independently without re-rendering parent
const DurationDisplay = memo(({ duration }: { duration: number | null }) => {
  if (duration === null || duration === undefined) return null;
  return (
    <span className="ml-2 text-xs opacity-80">
      ({duration.toFixed(1)}s)
    </span>
  );
});

// Separate component for individual input
const InputItem = memo(({ inputEvent, isGrid, t, isHighlighted, onCopy, onLongPress, duration, isRemote }: {
  inputEvent: InputEvent;
  isGrid: boolean;
  t: (key: string) => string;
  isHighlighted?: boolean;
  onCopy: (name: string) => void;
  onLongPress: (inputEvent: InputEvent) => void;
  duration: number | null;
  isRemote?: boolean;
}) => {
  const isLongState = inputEvent.state.state === 'long';

  return (
    <LongPressWrapper
      onClick={() => onCopy(inputEvent.state.name)}
      onLongPress={() => onLongPress(inputEvent)}
      preventDefaultOnTouchStart={false}
      className={clsx(
        'bg-base-200 text-secondary-content shadow-sm rounded-lg p-4 cursor-pointer hover:bg-base-300 select-none touch-manipulation',
        isGrid ? 'border-l-4' : 'border-l-8',
        isRemote ? 'border-purple-500' : 'border-blue-500',
        // Only apply transition when highlighted to avoid flash on duration updates
        isHighlighted && 'ring-4 ring-primary shadow-lg shadow-primary/30 scale-[1.02] transition-all duration-500'
      )}
      title={t('inputs.long_press_to_edit')}
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
            className={clsx('px-4 py-2 rounded-lg font-semibold inline-flex items-center',
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
            {isLongState && <DurationDisplay duration={duration} />}
          </span>
          <p className="text-gray-500 text-xs mt-2">
            {formatTimestamp(inputEvent.state.timestamp)}
          </p>
        </div>
      </div>
    </LongPressWrapper>
  );
}, (prevProps, nextProps) => {
  // Custom comparison - optimized for long press to reduce re-renders
  const prevState = prevProps.inputEvent.state;
  const nextState = nextProps.inputEvent.state;

  // Always re-render if state type changed (e.g., from 'long' to 'released')
  if (prevState.state !== nextState.state) {
    return false;
  }

  // For long press, throttle duration updates - only re-render every 500ms worth of duration change
  // This significantly reduces CPU usage while still showing progress
  if (nextState.state === 'long') {
    const sameCore = (
      prevProps.inputEvent.entity_id === nextProps.inputEvent.entity_id &&
      prevState.name === nextState.name &&
      prevProps.isGrid === nextProps.isGrid &&
      prevProps.isHighlighted === nextProps.isHighlighted
    );

    if (!sameCore) return false;

    // Throttle duration display updates - only re-render if duration changed by >= 0.5s
    const prevDur = prevProps.duration ?? 0;
    const nextDur = nextProps.duration ?? 0;
    const durationDiff = Math.abs(nextDur - prevDur);

    // Skip re-render if duration change is less than 0.5s
    if (durationDiff < 0.5) {
      return true; // Same, skip re-render
    }

    return false; // Re-render to update duration display
  }

  // For other states, use standard comparison
  return (
    prevProps.inputEvent.entity_id === nextProps.inputEvent.entity_id &&
    prevState.state === nextState.state &&
    prevState.timestamp === nextState.timestamp &&
    prevProps.isGrid === nextProps.isGrid &&
    prevProps.isHighlighted === nextProps.isHighlighted &&
    prevProps.duration === nextProps.duration
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

  // Throttle refs for long press updates (to reduce CPU usage)
  const lastLongPressUpdateRef = useRef<Map<string, number>>(new Map());
  const LONG_PRESS_THROTTLE_MS = 500; // Update toast max every 500ms

  const handleViewToggle = (gridView: boolean) => {
    setIsGrid(gridView);
    localStorage.setItem('inputViewMode', gridView ? 'grid' : 'list');
  };

  const handleSortChange = (mode: SortMode) => {
    setSortMode(mode);
    localStorage.setItem('inputSortMode', mode);
  };

  // Add or update toast notification with max 4 toasts limit
  const addOrUpdateToast = useCallback((message: string, type: string, inputName?: string, duration?: number, entityId?: string) => {
    setToasts(prev => {
      // For long press events, check if we already have a toast for this input
      if (type === 'long' && entityId) {
        const existingIndex = prev.findIndex(t => t.type === 'long' && t.entityId === entityId);
        if (existingIndex !== -1) {
          // Update existing toast
          const updated = [...prev];
          updated[existingIndex] = {
            ...updated[existingIndex],
            message,
            duration
          };
          return updated;
        }
      }

      // Create new toast
      const id = `${Date.now()}-${Math.random()}`;
      const newToast = { id, message, type, inputName, duration, entityId };
      const newToasts = [...prev, newToast];

      // Auto-remove after 3 seconds (only for non-long events)
      if (type !== 'long') {
        setTimeout(() => {
          setToasts(prev => prev.filter(toast => toast.id !== id));
        }, 3000);
      }

      // Keep only last 4 toasts (remove oldest if exceeding limit)
      return newToasts.slice(-4);
    });
  }, []);

  // Remove toast by entity_id (used when long press ends)
  const removeToastByEntity = useCallback((entityId: string) => {
    setToasts(prev => prev.filter(toast => toast.entityId !== entityId));
  }, []);

  // Copy input name to clipboard
  const [copiedName, setCopiedName] = useState<string | null>(null);

  const handleCopyName = useCallback((name: string) => {
    copyToClipboard(name).then(() => {
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

  // Quick action sheet state
  const [quickAction, setQuickAction] = useState<{ open: boolean; inputEvent: InputEvent | null }>({
    open: false,
    inputEvent: null
  });

  const handleOpenQuickAction = useCallback(() => {
    if (!longPressDialog.inputEvent) return;
    setQuickAction({ open: true, inputEvent: longPressDialog.inputEvent });
    setLongPressDialog({ open: false, inputEvent: null });
  }, [longPressDialog.inputEvent]);

  const handleGoToSettings = useCallback(() => {
    if (!longPressDialog.inputEvent) return;
    // Use entity_id for filtering instead of name to avoid duplicates
    const inputId = longPressDialog.inputEvent.entity_id;
    const isRemote = longPressDialog.inputEvent.state.remote;
    // Navigate to settings with edit query param
    const section = isRemote ? 'remote_inputs' : 'local_inputs';
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
        // Throttle long press updates to reduce CPU usage
        if (currentState === 'long') {
          const lastUpdate = lastLongPressUpdateRef.current.get(inputEvent.entity_id) || 0;
          const nowMs = Date.now();
          if (nowMs - lastUpdate < LONG_PRESS_THROTTLE_MS) {
            // Skip this update, too soon
            return;
          }
          lastLongPressUpdateRef.current.set(inputEvent.entity_id, nowMs);
        }

        const time = new Date(currentTimestamp * 1000).toLocaleTimeString('pl-PL', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit'
        });

        // For long press, include duration in message
        let message = `[${time}] ${t('inputs.detected')} ${currentState} ${t('inputs.in')} ${inputEvent.state.name}`;
        if (currentState === 'long' && inputEvent.duration !== null && inputEvent.duration !== undefined) {
          message += ` (${inputEvent.duration.toFixed(1)}s)`;
        }

        addOrUpdateToast(
          message,
          currentState,
          inputEvent.state.name,
          inputEvent.duration ?? undefined,
          inputEvent.entity_id
        );
      }

      // Remove long press toast when state changes from 'long' to something else
      if (prevData && prevData.state === 'long' && currentState !== 'long') {
        removeToastByEntity(inputEvent.entity_id);
        // Clean up throttle ref
        lastLongPressUpdateRef.current.delete(inputEvent.entity_id);
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
  }, [validInputs, addOrUpdateToast, removeToastByEntity, t]);

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

  // Split inputs into local and remote
  const localInputs = useMemo(
    () => sortedInputs.filter(i => !i.state.remote),
    [sortedInputs]
  );
  const remoteInputs = useMemo(
    () => sortedInputs.filter(i => i.state.remote),
    [sortedInputs]
  );
  const hasBothSections = localInputs.length > 0 && remoteInputs.length > 0;

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
      {/* Local inputs section */}
      {localInputs.length > 0 && (
        <>
          {hasBothSections && (
            <h3 className="text-lg font-semibold mb-2 mt-2">{t('inputs.local_inputs')}</h3>
          )}
          <div className={isGrid
            ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
            : "flex flex-col gap-4"
          }>
            {localInputs.map((inputEvent: InputEvent) => (
              <InputItem
                key={inputEvent.entity_id}
                inputEvent={inputEvent}
                isGrid={isGrid}
                t={t}
                isHighlighted={recentlyChanged.has(inputEvent.entity_id)}
                onCopy={handleCopyName}
                onLongPress={handleLongPress}
                duration={inputEvent.duration}
              />
            ))}
          </div>
        </>
      )}

      {/* Remote inputs section */}
      {remoteInputs.length > 0 && (
        <>
          <h3 className="text-lg font-semibold mb-2 mt-6 flex items-center gap-2">
            <FaWifi className="w-4 h-4 text-purple-400" />
            {t('inputs.remote_inputs')}
          </h3>
          <div className={isGrid
            ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4"
            : "flex flex-col gap-4"
          }>
            {remoteInputs.map((inputEvent: InputEvent) => (
              <InputItem
                key={inputEvent.entity_id}
                inputEvent={inputEvent}
                isGrid={isGrid}
                t={t}
                isHighlighted={recentlyChanged.has(inputEvent.entity_id)}
                onCopy={handleCopyName}
                onLongPress={handleLongPress}
                duration={inputEvent.duration}
                isRemote
              />
            ))}
          </div>
        </>
      )}

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
              onClick={() => toast.inputName && handleCopyName(toast.inputName)}
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

      {/* Long press dialog - choose quick action or go to settings */}
      <Dialog open={longPressDialog.open} onOpenChange={(open) => setLongPressDialog({ open, inputEvent: open ? longPressDialog.inputEvent : null })}>
        <DialogContent
          className={[
            'bg-base-100 p-0 gap-0',
            // Mobile: bottom sheet
            'top-auto bottom-0 left-0 translate-x-0 translate-y-0',
            'max-w-full rounded-t-2xl rounded-b-none',
            // Desktop: centered modal
            'sm:top-[50%] sm:left-[50%] sm:bottom-auto',
            'sm:translate-x-[-50%] sm:translate-y-[-50%]',
            'sm:max-w-sm sm:rounded-lg',
          ].join(' ')}
        >
          {/* Drag handle - mobile only */}
          <div className="flex justify-center pt-3 sm:hidden">
            <div className="w-10 h-1 rounded-full bg-base-content/20" />
          </div>
          <DialogHeader className="px-5 pt-4 pb-0 sm:pt-5">
            <DialogTitle className="text-center">
              {longPressDialog.inputEvent?.state.name}
            </DialogTitle>
            <p className="text-xs text-base-content/50 text-center">
              {longPressDialog.inputEvent?.entity_id}
            </p>
          </DialogHeader>
          <div className="px-5 py-4 space-y-2">
            {/* Quick Action button */}
            <button
              className="btn btn-primary btn-block gap-2 h-14 text-base"
              onClick={handleOpenQuickAction}
            >
              <FaBolt className="w-5 h-5" />
              {t('quick_action.title')}
            </button>
            {/* Go to settings button */}
            <button
              className="btn btn-ghost btn-block gap-2 h-12"
              onClick={handleGoToSettings}
            >
              <FaCog className="w-4 h-4" />
              {t('inputs.go_to_settings')}
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Quick Action Sheet */}
      <QuickActionSheet
        open={quickAction.open}
        onOpenChange={(open) => setQuickAction({ open, inputEvent: open ? quickAction.inputEvent : null })}
        inputEvent={quickAction.inputEvent}
      />
    </div>
  );
}
