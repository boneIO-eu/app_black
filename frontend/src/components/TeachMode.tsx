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
import {
  FaGraduationCap, FaTimes, FaCheck, FaExclamationTriangle,
  FaHandPointer, FaBolt, FaUndo, FaChevronDown, FaChevronUp,
  FaLink, FaList,
} from 'react-icons/fa';

/** Click types for event-type inputs. */
const EVENT_CLICK_TYPES = ['single', 'double', 'triple', 'long'] as const;
/** Click types for binary_sensor inputs. */
const BINARY_SENSOR_CLICK_TYPES = ['pressed', 'released'] as const;
/** Output action options. */
const OUTPUT_ACTIONS = ['TOGGLE', 'ON', 'OFF'] as const;
/** Cover action options. */
const COVER_ACTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP'] as const;

type SaveStatus = 'idle' | 'saving' | 'success' | 'error';
type TargetCategory = 'output' | 'remote_output' | 'cover' | 'remote_cover';
type RightTab = 'link' | 'bindings';

/** Extended EntityItem tracking action type and remote device. */
interface TeachEntityItem extends EntityItem {
  actionType: TargetCategory;
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

/** Parsed action binding from config. */
interface ActionBinding {
  clickType: string;
  actionType: string;
  target: string;
  action: string;
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
 * 2. User selects output from categorized picker (right panel)
 * 3. User picks click type + action → "Link"
 * 4. Loop back to step 1 for next input
 */
const TeachMode: React.FC<TeachModeProps> = ({ onClose }) => {
  const { t } = useTranslation();
  const { inputs, outputs, covers } = useContext(WebSocketContext);

  // Detected input from physical button press
  const [detectedInput, setDetectedInput] = useState<InputEvent | null>(null);
  // Selected output/cover target
  const [targetId, setTargetId] = useState('');
  const [targetCategory, setTargetCategory] = useState<TargetCategory>('output');
  // Click type and action
  const [clickType, setClickType] = useState('single');
  const [actionValue, setActionValue] = useState('TOGGLE');
  // Save state
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  // History log
  const [log, setLog] = useState<TeachLogEntry[]>([]);
  const [linkCount, setLinkCount] = useState(0);
  // Panel collapse
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  // Right panel tab
  const [rightTab, setRightTab] = useState<RightTab>('link');
  // Existing bindings for detected input
  const [bindings, setBindings] = useState<ActionBinding[]>([]);
  const [bindingsLoading, setBindingsLoading] = useState(false);

  // Track previous input states to detect changes
  const prevInputsRef = useRef<Map<string, { state: string; timestamp: number }>>(new Map());
  const isInitializedRef = useRef(false);

  const validInputs = useMemo(() => inputs.filter(isInputEvent), [inputs]);

  // Detect input events via WebSocket
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
        setDetectedInput(inputEvent);
        const isEvent = inputEvent.state.type === 'input';
        if (isEvent) {
          setClickType(currentState);
        } else {
          setClickType(currentState === 'pressed' || currentState === 'ON' ? 'pressed' : 'released');
        }
        setSaveStatus('idle');
        setErrorMessage('');
        // Collapse left panel on detect to give more space
        setLeftCollapsed(true);
      }

      prevInputsRef.current.set(inputEvent.entity_id, {
        state: currentState,
        timestamp: currentTimestamp
      });
    });
  }, [validInputs]);

  // Fetch existing bindings when input is detected
  useEffect(() => {
    if (!detectedInput) {
      setBindings([]);
      return;
    }

    const fetchBindings = async () => {
      setBindingsLoading(true);
      try {
        const resp = await axios.get('/api/config');
        const config = resp.data;
        const entityId = detectedInput.entity_id;
        const parsed: ActionBinding[] = [];

        for (const secName of ['event', 'binary_sensor']) {
          const entries = config[secName] || [];
          if (!Array.isArray(entries)) continue;

          for (const entry of entries) {
            if (!entry || typeof entry !== 'object') continue;
            const eid = String(entry.id || entry.pin || '');
            if (eid !== entityId) continue;

            // Parse actions from all click type keys
            for (const key of Object.keys(entry)) {
              if (!key.startsWith('actions_') && key !== 'actions_on_press' && key !== 'actions_on_release') continue;

              const ct = key.replace('actions_', '').replace('on_', '');
              const actions = entry[key];
              if (!Array.isArray(actions)) continue;

              for (const act of actions) {
                if (!act || typeof act !== 'object') continue;
                const at = act.action || act.action_type || '?';
                const target = act.boneio_output || act.boneio_cover || act.output_id || act.cover_id || act.topic || '?';
                const action = act.action_output || act.action_cover || act.action_mqtt_msg || '?';
                parsed.push({ clickType: ct, actionType: at, target, action });
              }
            }
          }
        }

        setBindings(parsed);
      } catch {
        setBindings([]);
      } finally {
        setBindingsLoading(false);
      }
    };

    fetchBindings();
  }, [detectedInput, linkCount]); // Re-fetch after new link

  // Build categorized entity items
  const localOutputItems: TeachEntityItem[] = useMemo(() => {
    return outputs
      .filter((o: OutputEvent) => !o.state.remote)
      .map((o: OutputEvent): TeachEntityItem => ({
        id: o.state.id || o.entity_id,
        name: o.state.name || o.state.id || o.entity_id,
        area: o.state.area || undefined,
        badge: o.state.type || undefined,
        badgeClass: o.state.type === 'light' ? 'badge-warning'
          : o.state.type === 'switch' ? 'badge-info'
          : o.state.type === 'valve' ? 'badge-accent'
          : 'badge-ghost',
        actionType: 'output',
      }));
  }, [outputs]);

  const remoteOutputItems: TeachEntityItem[] = useMemo(() => {
    return outputs
      .filter((o: OutputEvent) => o.state.remote)
      .map((o: OutputEvent): TeachEntityItem => {
        const entityId = o.entity_id;
        const parts = entityId.split('/');
        const remoteDevice = parts.length > 1 ? parts[0] : '';
        return {
          id: entityId,
          name: o.state.name || entityId,
          area: o.state.area || undefined,
          badge: `🌐 ${o.state.type || 'remote'}`,
          badgeClass: 'badge-secondary',
          actionType: 'remote_output',
          remoteDevice,
        };
      });
  }, [outputs]);

  const localCoverItems: TeachEntityItem[] = useMemo(() => {
    return covers
      .filter((c: CoverEvent) => !(c.state as any).remote)
      .map((c: CoverEvent): TeachEntityItem => ({
        id: c.state.id || c.entity_id,
        name: c.state.name || c.state.id || c.entity_id,
        badge: c.state.kind || 'cover',
        badgeClass: 'badge-accent',
        actionType: 'cover',
      }));
  }, [covers]);

  const remoteCoverItems: TeachEntityItem[] = useMemo(() => {
    return covers
      .filter((c: CoverEvent) => (c.state as any).remote)
      .map((c: CoverEvent): TeachEntityItem => {
        const entityId = c.entity_id;
        const parts = entityId.split('/');
        const remoteDevice = parts.length > 1 ? parts[0] : '';
        return {
          id: entityId,
          name: c.state.name || entityId,
          badge: `🌐 ${c.state.kind || 'cover'}`,
          badgeClass: 'badge-secondary',
          actionType: 'remote_cover',
          remoteDevice,
        };
      });
  }, [covers]);

  /** Available categories (only show tabs that have items). */
  const availableCategories = useMemo(() => {
    const cats: { key: TargetCategory; label: string; count: number }[] = [];
    if (localOutputItems.length > 0) cats.push({ key: 'output', label: t('teach_mode.cat_output'), count: localOutputItems.length });
    if (remoteOutputItems.length > 0) cats.push({ key: 'remote_output', label: t('teach_mode.cat_remote_output'), count: remoteOutputItems.length });
    if (localCoverItems.length > 0) cats.push({ key: 'cover', label: t('teach_mode.cat_cover'), count: localCoverItems.length });
    if (remoteCoverItems.length > 0) cats.push({ key: 'remote_cover', label: t('teach_mode.cat_remote_cover'), count: remoteCoverItems.length });
    return cats;
  }, [localOutputItems, remoteOutputItems, localCoverItems, remoteCoverItems, t]);

  const currentItems = useMemo(() => {
    switch (targetCategory) {
      case 'output': return localOutputItems;
      case 'remote_output': return remoteOutputItems;
      case 'cover': return localCoverItems;
      case 'remote_cover': return remoteCoverItems;
    }
  }, [targetCategory, localOutputItems, remoteOutputItems, localCoverItems, remoteCoverItems]);

  const isCoverCategory = targetCategory === 'cover' || targetCategory === 'remote_cover';
  const actionOptions = isCoverCategory ? COVER_ACTIONS : OUTPUT_ACTIONS;
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

      setTimeout(() => {
        setDetectedInput(null);
        setTargetId('');
        setSaveStatus('idle');
        setLeftCollapsed(false);
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
      <div className="bg-primary text-primary-content px-4 py-3 flex items-center justify-between shadow-lg shrink-0">
        <div className="flex items-center gap-3">
          <FaGraduationCap className="w-6 h-6" />
          <div>
            <h1 className="text-lg font-bold">{t('teach_mode.title')}</h1>
            <p className="text-xs opacity-80">
              {t('teach_mode.subtitle', { count: linkCount })}
            </p>
          </div>
        </div>
        <button className="btn btn-sm btn-ghost text-primary-content" onClick={onClose}>
          <FaTimes className="w-5 h-5" />
        </button>
      </div>

      {/* Main content - split layout */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left panel — Input detection */}
        <div className={clsx(
          'border-b md:border-b-0 md:border-r border-base-300 flex flex-col transition-all duration-300',
          leftCollapsed ? 'md:w-72' : 'md:w-1/2',
        )}>
          {/* Collapsible header */}
          <button
            className="p-4 bg-base-200/50 border-b border-base-300 flex items-center justify-between w-full hover:bg-base-200/80 transition-colors"
            onClick={() => setLeftCollapsed(!leftCollapsed)}
          >
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <span className="badge badge-primary badge-sm">1</span>
              {t('teach_mode.step_1')}
            </h2>
            {leftCollapsed ? <FaChevronDown className="w-3 h-3 text-base-content/50" /> : <FaChevronUp className="w-3 h-3 text-base-content/50" />}
          </button>

          {!leftCollapsed ? (
            <div className="flex-1 flex items-center justify-center p-6">
              {!detectedInput ? (
                <div className="text-center space-y-4">
                  <FaHandPointer className="w-16 h-16 text-base-content/20 mx-auto animate-pulse" />
                  <p className="text-lg text-base-content/50">{t('teach_mode.waiting')}</p>
                  <p className="text-sm text-base-content/30">{t('teach_mode.waiting_hint')}</p>
                </div>
              ) : (
                <div className="text-center space-y-4 w-full max-w-sm">
                  <FaCheck className="w-12 h-12 text-success mx-auto" />
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

                  <button
                    className="btn btn-ghost btn-sm gap-1"
                    onClick={() => { setDetectedInput(null); setSaveStatus('idle'); setLeftCollapsed(false); }}
                  >
                    <FaUndo className="w-3 h-3" />
                    {t('teach_mode.reset_input')}
                  </button>
                </div>
              )}
            </div>
          ) : detectedInput ? (
            /* Collapsed state with detected input summary */
            <div className="p-3 flex items-center gap-3">
              <FaCheck className="w-5 h-5 text-success shrink-0" />
              <div className="min-w-0">
                <p className="font-semibold text-sm truncate">{detectedInput.state.name}</p>
                <p className="text-xs text-base-content/50 truncate">{detectedInput.entity_id}</p>
              </div>
              <div className={clsx(
                'badge badge-sm shrink-0',
                detectedInput.state.state === 'single' && 'badge-success',
                detectedInput.state.state === 'double' && 'badge-warning',
                detectedInput.state.state === 'long' && 'badge-info',
              )}>
                {clickType}
              </div>
              <button
                className="btn btn-ghost btn-xs ml-auto shrink-0"
                onClick={() => { setDetectedInput(null); setSaveStatus('idle'); setLeftCollapsed(false); }}
              >
                <FaUndo className="w-3 h-3" />
              </button>
            </div>
          ) : (
            <div className="p-3 text-sm text-base-content/40 text-center">
              {t('teach_mode.waiting')}
            </div>
          )}
        </div>

        {/* Right panel — Output selection + Bindings */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Tab bar */}
          <div className="flex border-b border-base-300 bg-base-200/50 shrink-0">
            <button
              className={clsx(
                'flex-1 px-4 py-3 text-sm font-medium flex items-center justify-center gap-2 border-b-2 transition-colors',
                rightTab === 'link' ? 'border-primary text-primary' : 'border-transparent text-base-content/50 hover:text-base-content',
              )}
              onClick={() => setRightTab('link')}
            >
              <FaBolt className="w-3 h-3" />
              {t('teach_mode.tab_link')}
            </button>
            <button
              className={clsx(
                'flex-1 px-4 py-3 text-sm font-medium flex items-center justify-center gap-2 border-b-2 transition-colors',
                rightTab === 'bindings' ? 'border-primary text-primary' : 'border-transparent text-base-content/50 hover:text-base-content',
              )}
              onClick={() => setRightTab('bindings')}
            >
              <FaList className="w-3 h-3" />
              {t('teach_mode.tab_bindings')}
              {bindings.length > 0 && (
                <span className="badge badge-xs badge-primary">{bindings.length}</span>
              )}
            </button>
          </div>

          {/* Tab content */}
          {rightTab === 'link' ? (
            /* Link tab */
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Category tabs */}
              <div className="flex flex-wrap gap-1">
                {availableCategories.map(({ key, label, count }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => { setTargetCategory(key); setTargetId(''); setActionValue('TOGGLE'); }}
                    className={clsx(
                      'btn btn-sm gap-1',
                      targetCategory === key ? 'btn-primary' : 'btn-ghost border border-base-300',
                    )}
                  >
                    {label}
                    <span className="badge badge-xs badge-ghost">{count}</span>
                  </button>
                ))}
              </div>

              {/* Entity picker */}
              <SearchableEntityPicker
                value={targetId}
                onChange={setTargetId}
                items={currentItems}
                placeholder={t('teach_mode.select_target')}
                recentKey={targetCategory}
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
                    <FaLink className="w-5 h-5" />
                    {t('teach_mode.link')}
                  </>
                )}
              </button>

              {/* Status messages */}
              {saveStatus === 'error' && errorMessage && (
                <div className="alert alert-error text-sm py-2">
                  <FaExclamationTriangle className="w-4 h-4" />
                  <span>{errorMessage}</span>
                </div>
              )}
              {saveStatus === 'success' && (
                <div className="alert alert-success text-sm py-2">
                  <FaCheck className="w-4 h-4" />
                  <span>{t('quick_action.saved')}</span>
                </div>
              )}
            </div>
          ) : (
            /* Bindings tab */
            <div className="flex-1 overflow-y-auto p-4">
              {!detectedInput ? (
                <div className="text-center text-base-content/40 py-8">
                  <FaList className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p>{t('teach_mode.bindings_no_input')}</p>
                </div>
              ) : bindingsLoading ? (
                <div className="flex justify-center py-8">
                  <span className="loading loading-spinner loading-md" />
                </div>
              ) : bindings.length === 0 ? (
                <div className="text-center text-base-content/40 py-8">
                  <FaList className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p>{t('teach_mode.bindings_empty')}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-base-content/50 mb-3">
                    {t('teach_mode.bindings_for', { name: detectedInput.state.name })}
                  </p>
                  {bindings.map((b, i) => (
                    <div key={i} className="flex items-center gap-2 bg-base-200 rounded-lg px-3 py-2 text-sm">
                      <span className="badge badge-sm badge-primary">{b.clickType}</span>
                      <span className="text-base-content/50">→</span>
                      <span className="badge badge-sm badge-ghost">{b.actionType}</span>
                      <span className="font-medium truncate flex-1">{b.target}</span>
                      <span className="badge badge-sm badge-outline">{b.action}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Bottom log panel */}
      {log.length > 0 && (
        <div className="border-t border-base-300 bg-base-200/50 max-h-40 overflow-y-auto shrink-0">
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
