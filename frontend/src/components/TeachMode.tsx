import React, { useState, useContext, useMemo, useCallback, useEffect, useRef } from 'react';
import { WebSocketContext } from '@/App';
import { useTranslation } from '@/hooks/useTranslation';
import type { InputEvent, OutputEvent, CoverEvent } from '@/hooks/useWebSocket';
import { isInputEvent } from '@/hooks/useWebSocket';
import type { EntityItem } from '@/components/UISettings/EntitySelectDropdown';
import SearchableEntityPicker from '@/components/UISettings/SearchableEntityPicker';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import axios from '@/api/axios';
import clsx from 'clsx';
import { FaGraduationCap, FaTimes, FaCheck, FaExclamationTriangle, FaHandPointer, FaBolt, FaUndo } from 'react-icons/fa';

/** Click types for event-type inputs. */
const EVENT_CLICK_TYPES = ['single', 'double', 'triple', 'long'] as const;
/** Click types for binary_sensor inputs. */
const BINARY_SENSOR_CLICK_TYPES = ['pressed', 'released'] as const;
/** Output action options. */
const OUTPUT_ACTIONS = ['TOGGLE', 'ON', 'OFF'] as const;
/** Cover action options. */
const COVER_ACTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP'] as const;

type SaveStatus = 'idle' | 'saving' | 'success' | 'error';

/** Extended EntityItem tracking action type and remote device. */
interface TeachEntityItem extends EntityItem {
  actionType: 'output' | 'cover' | 'remote_output' | 'remote_cover';
  remoteDevice?: string;
}

/** Log entry for teach mode history. */
interface TeachLogEntry {
  id: string;
  inputName: string;
  inputEntityId: string;
  targetName: string;
  clickType: string;
  action: string;
  status: 'success' | 'error';
  message?: string;
  timestamp: number;
}

interface TeachModeProps {
  /** Close teach mode */
  onClose: () => void;
}

/**
 * Teach Mode — full-screen overlay for linking inputs to outputs.
 *
 * Flow:
 * 1. User presses physical button → input detected (left panel)
 * 2. User selects output from picker (right panel)
 * 3. User picks click type + action
 * 4. Saves via POST /api/config/quick-action
 * 5. Loop back to step 1 for next input
 */
const TeachMode: React.FC<TeachModeProps> = ({ onClose }) => {
  const { t } = useTranslation();
  const { inputs, outputs, covers } = useContext(WebSocketContext);

  // Detected input from physical button press
  const [detectedInput, setDetectedInput] = useState<InputEvent | null>(null);
  // Selected output/cover target
  const [targetId, setTargetId] = useState('');
  const [targetMode, setTargetMode] = useState<'output' | 'cover'>('output');
  // Click type and action
  const [clickType, setClickType] = useState('single');
  const [actionValue, setActionValue] = useState('TOGGLE');
  // Save state
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  // History log
  const [log, setLog] = useState<TeachLogEntry[]>([]);
  // Counter for linking
  const [linkCount, setLinkCount] = useState(0);

  // Track previous input states to detect changes
  const prevInputsRef = useRef<Map<string, { state: string; timestamp: number }>>(new Map());
  const isInitializedRef = useRef(false);

  const validInputs = useMemo(() => inputs.filter(isInputEvent), [inputs]);

  // Detect input events (same logic as InputsView)
  useEffect(() => {
    const eventTypes = ['single', 'double', 'long', 'pressed', 'released', 'triple',
      'double_then_long', 'single_then_long', 'double_then_single'];
    const now = Date.now() / 1000;

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

      const isRecent = (now - currentTimestamp) < 5;
      const hasChanged = prevData && prevData.timestamp !== currentTimestamp && isRecent;

      if (hasChanged && eventTypes.includes(currentState)) {
        // Detected a new event — set it as current input
        setDetectedInput(inputEvent);
        // Auto-set click type based on event
        const isEvent = inputEvent.state.type === 'input';
        if (isEvent) {
          setClickType(currentState);
        } else {
          setClickType(currentState === 'pressed' || currentState === 'ON' ? 'pressed' : 'released');
        }
        // Reset save state for new pairing
        setSaveStatus('idle');
        setErrorMessage('');
      }

      prevInputsRef.current.set(inputEvent.entity_id, {
        state: currentState,
        timestamp: currentTimestamp
      });
    });
  }, [validInputs]);

  /** Build unified output items (local + remote). */
  const outputItems: TeachEntityItem[] = useMemo(() => {
    const items: TeachEntityItem[] = [];

    outputs
      .filter((o: OutputEvent) => !o.state.remote)
      .forEach((o: OutputEvent) => {
        items.push({
          id: o.state.id || o.entity_id,
          name: o.state.name || o.state.id || o.entity_id,
          area: o.state.area || undefined,
          badge: o.state.type || undefined,
          badgeClass: o.state.type === 'light' ? 'badge-warning'
            : o.state.type === 'switch' ? 'badge-info'
            : o.state.type === 'valve' ? 'badge-accent'
            : 'badge-ghost',
          actionType: 'output',
        });
      });

    outputs
      .filter((o: OutputEvent) => o.state.remote)
      .forEach((o: OutputEvent) => {
        const entityId = o.entity_id;
        const parts = entityId.split('/');
        const remoteDevice = parts.length > 1 ? parts[0] : '';

        items.push({
          id: entityId,
          name: o.state.name || entityId,
          area: o.state.area || undefined,
          badge: `🌐 ${o.state.type || 'remote'}`,
          badgeClass: 'badge-secondary',
          actionType: 'remote_output',
          remoteDevice,
        });
      });

    return items;
  }, [outputs]);

  /** Build unified cover items (local + remote). */
  const coverItems: TeachEntityItem[] = useMemo(() => {
    const items: TeachEntityItem[] = [];

    covers
      .filter((c: CoverEvent) => !(c.state as any).remote)
      .forEach((c: CoverEvent) => {
        items.push({
          id: c.state.id || c.entity_id,
          name: c.state.name || c.state.id || c.entity_id,
          badge: c.state.kind || 'cover',
          badgeClass: 'badge-accent',
          actionType: 'cover',
        });
      });

    covers
      .filter((c: CoverEvent) => (c.state as any).remote)
      .forEach((c: CoverEvent) => {
        const entityId = c.entity_id;
        const parts = entityId.split('/');
        const remoteDevice = parts.length > 1 ? parts[0] : '';

        items.push({
          id: entityId,
          name: c.state.name || entityId,
          badge: `🌐 ${c.state.kind || 'cover'}`,
          badgeClass: 'badge-secondary',
          actionType: 'remote_cover',
          remoteDevice,
        });
      });

    return items;
  }, [covers]);

  const currentItems = targetMode === 'cover' ? coverItems : outputItems;
  const actionOptions = targetMode === 'cover' ? COVER_ACTIONS : OUTPUT_ACTIONS;
  const clickTypes = detectedInput?.state.type === 'input' ? EVENT_CLICK_TYPES : BINARY_SENSOR_CLICK_TYPES;

  const selectedItem = useMemo(
    () => currentItems.find((item) => item.id === targetId),
    [currentItems, targetId]
  );

  /** Save the link. */
  const handleLink = useCallback(async () => {
    if (!detectedInput || !targetId || !selectedItem) return;

    setSaveStatus('saving');
    setErrorMessage('');

    try {
      const payload: Record<string, string> = {
        entity_id: detectedInput.entity_id,
        click_type: clickType,
        action_type: selectedItem.actionType,
        action: actionValue,
      };

      switch (selectedItem.actionType) {
        case 'output':
          payload.output_id = targetId;
          break;
        case 'cover':
          payload.cover_id = targetId;
          break;
        case 'remote_output': {
          payload.remote_device = selectedItem.remoteDevice || '';
          const parts = targetId.split('/');
          payload.output_id = parts.length > 1 ? parts.slice(1).join('/') : targetId;
          break;
        }
        case 'remote_cover': {
          payload.remote_device = selectedItem.remoteDevice || '';
          const coverParts = targetId.split('/');
          payload.cover_id = coverParts.length > 1 ? coverParts.slice(1).join('/') : targetId;
          break;
        }
      }

      await axios.post('/api/config/quick-action', payload);
      setSaveStatus('success');
      setLinkCount((c) => c + 1);

      // Add to log
      setLog((prev) => [{
        id: `${Date.now()}-${Math.random()}`,
        inputName: detectedInput.state.name,
        inputEntityId: detectedInput.entity_id,
        targetName: selectedItem.name,
        clickType,
        action: actionValue,
        status: 'success',
        timestamp: Date.now(),
      }, ...prev]);

      // Reset for next pairing after short delay
      setTimeout(() => {
        setDetectedInput(null);
        setTargetId('');
        setSaveStatus('idle');
      }, 1000);

    } catch (err: any) {
      setSaveStatus('error');
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || t('quick_action.save_error');
      setErrorMessage(msg);

      setLog((prev) => [{
        id: `${Date.now()}-${Math.random()}`,
        inputName: detectedInput.state.name,
        inputEntityId: detectedInput.entity_id,
        targetName: selectedItem.name,
        clickType,
        action: actionValue,
        status: 'error',
        message: msg,
        timestamp: Date.now(),
      }, ...prev]);
    }
  }, [detectedInput, targetId, selectedItem, clickType, actionValue, t]);

  const canLink = detectedInput && targetId && selectedItem && saveStatus !== 'saving' && saveStatus !== 'success';

  return (
    <div className="fixed inset-0 z-50 bg-base-100 flex flex-col">
      {/* Header bar */}
      <div className="bg-primary text-primary-content px-4 py-3 flex items-center justify-between shadow-lg">
        <div className="flex items-center gap-3">
          <FaGraduationCap className="w-6 h-6" />
          <div>
            <h1 className="text-lg font-bold">{t('teach_mode.title')}</h1>
            <p className="text-xs opacity-80">
              {t('teach_mode.subtitle', { count: linkCount })}
            </p>
          </div>
        </div>
        <button
          className="btn btn-sm btn-ghost text-primary-content"
          onClick={onClose}
        >
          <FaTimes className="w-5 h-5" />
        </button>
      </div>

      {/* Main content - split layout */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left panel — Input detection */}
        <div className="md:w-1/2 border-b md:border-b-0 md:border-r border-base-300 flex flex-col">
          <div className="p-4 bg-base-200/50 border-b border-base-300">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <span className="badge badge-primary badge-sm">1</span>
              {t('teach_mode.step_1')}
            </h2>
          </div>

          <div className="flex-1 flex items-center justify-center p-6">
            {!detectedInput ? (
              /* Waiting for input */
              <div className="text-center space-y-4">
                <div className="relative">
                  <FaHandPointer className="w-16 h-16 text-base-content/20 mx-auto animate-pulse" />
                </div>
                <p className="text-lg text-base-content/50">{t('teach_mode.waiting')}</p>
                <p className="text-sm text-base-content/30">{t('teach_mode.waiting_hint')}</p>
              </div>
            ) : (
              /* Input detected */
              <div className="text-center space-y-4 w-full max-w-sm">
                <div className="relative">
                  <FaCheck className="w-12 h-12 text-success mx-auto" />
                </div>
                <div>
                  <h3 className="text-xl font-bold">{detectedInput.state.name}</h3>
                  <p className="text-sm text-base-content/50">{detectedInput.entity_id}</p>
                </div>
                <div className={clsx(
                  'badge badge-lg',
                  detectedInput.state.state === 'single' && 'badge-success',
                  detectedInput.state.state === 'double' && 'badge-warning',
                  detectedInput.state.state === 'long' && 'badge-info',
                  detectedInput.state.state === 'pressed' && 'badge-success',
                  detectedInput.state.state === 'released' && 'badge-warning',
                )}>
                  {detectedInput.state.state}
                </div>

                {/* Click type override */}
                <div className="form-control">
                  <label className="label pb-1 justify-center">
                    <span className="label-text font-medium text-sm">{t('quick_action.click_type')}</span>
                  </label>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {clickTypes.map((ct) => (
                      <button
                        key={ct}
                        type="button"
                        onClick={() => setClickType(ct)}
                        className={`btn btn-sm ${clickType === ct ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
                      >
                        {t(`quick_action.click_types.${ct}`)}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Reset button */}
                <button
                  className="btn btn-ghost btn-sm gap-1"
                  onClick={() => { setDetectedInput(null); setSaveStatus('idle'); }}
                >
                  <FaUndo className="w-3 h-3" />
                  {t('teach_mode.reset_input')}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right panel — Output selection */}
        <div className="md:w-1/2 flex flex-col">
          <div className="p-4 bg-base-200/50 border-b border-base-300">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <span className="badge badge-primary badge-sm">2</span>
              {t('teach_mode.step_2')}
            </h2>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Target mode toggle */}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setTargetMode('output'); setTargetId(''); setActionValue('TOGGLE'); }}
                className={`btn btn-sm flex-1 ${targetMode === 'output' ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
              >
                {t('quick_action.output')}
              </button>
              {coverItems.length > 0 && (
                <button
                  type="button"
                  onClick={() => { setTargetMode('cover'); setTargetId(''); setActionValue('TOGGLE'); }}
                  className={`btn btn-sm flex-1 ${targetMode === 'cover' ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
                >
                  {t('quick_action.cover')}
                </button>
              )}
            </div>

            {/* Entity picker */}
            <SearchableEntityPicker
              value={targetId}
              onChange={setTargetId}
              items={currentItems}
              placeholder={targetMode === 'cover' ? t('quick_action.select_cover') : t('quick_action.select_output')}
              recentKey={targetMode === 'cover' ? 'covers' : 'outputs'}
            />

            {/* Action selector */}
            <div className="form-control">
              <label className="label pb-1">
                <span className="label-text font-medium text-sm">{t('quick_action.action')}</span>
              </label>
              <Select value={actionValue} onValueChange={setActionValue}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-base-100">
                  {actionOptions.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Link button */}
            <button
              className="btn btn-primary btn-block gap-2 h-14 text-base"
              disabled={!canLink}
              onClick={handleLink}
            >
              {saveStatus === 'saving' ? (
                <span className="loading loading-spinner loading-sm" />
              ) : (
                <>
                  <FaBolt className="w-5 h-5" />
                  {t('teach_mode.link')}
                </>
              )}
            </button>

            {/* Error message */}
            {saveStatus === 'error' && errorMessage && (
              <div className="alert alert-error text-sm py-2">
                <FaExclamationTriangle className="w-4 h-4" />
                <span>{errorMessage}</span>
              </div>
            )}

            {/* Success message */}
            {saveStatus === 'success' && (
              <div className="alert alert-success text-sm py-2">
                <FaCheck className="w-4 h-4" />
                <span>{t('quick_action.saved')}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom log panel */}
      {log.length > 0 && (
        <div className="border-t border-base-300 bg-base-200/50 max-h-40 overflow-y-auto">
          <div className="p-2 px-4">
            <h3 className="text-xs font-semibold text-base-content/50 mb-1">{t('teach_mode.history')}</h3>
            <div className="space-y-1">
              {log.slice(0, 10).map((entry) => (
                <div
                  key={entry.id}
                  className={clsx(
                    'text-xs py-1 px-2 rounded flex items-center gap-2',
                    entry.status === 'success' ? 'bg-success/10 text-success' : 'bg-error/10 text-error'
                  )}
                >
                  {entry.status === 'success' ? <FaCheck className="w-3 h-3 shrink-0" /> : <FaExclamationTriangle className="w-3 h-3 shrink-0" />}
                  <span className="font-medium">{entry.inputName}</span>
                  <span className="opacity-60">→</span>
                  <span>{entry.targetName}</span>
                  <span className="badge badge-xs badge-ghost">{entry.clickType}</span>
                  <span className="badge badge-xs badge-ghost">{entry.action}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TeachMode;
