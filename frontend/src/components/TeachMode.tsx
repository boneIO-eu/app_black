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
  FaLink, FaList, FaHistory
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
  }, [detectedInput, linkCount]);

  // Build categorized entity items
  const localOutputItems: TeachEntityItem[] = useMemo(() => {
    return outputs
      .filter((o: OutputEvent) => !o.state.remote)
      .map((o: OutputEvent): TeachEntityItem => ({
        id: o.state.id || o.entity_id,
        name: o.state.name || o.state.id || o.entity_id,
        area: o.state.area || undefined,
        badge: o.state.type || undefined,
        badgeClass: o.state.type === 'light' ? 'badge-warning text-warning-content'
          : o.state.type === 'switch' ? 'badge-info text-info-content'
          : o.state.type === 'valve' ? 'badge-accent text-accent-content'
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
          badgeClass: 'badge-secondary text-secondary-content',
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
        badgeClass: 'badge-accent text-accent-content',
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
          badgeClass: 'badge-secondary text-secondary-content',
          actionType: 'remote_cover',
          remoteDevice,
        };
      });
  }, [covers]);

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
    <div className="fixed inset-0 z-50 bg-gradient-to-br from-base-100 via-base-100 to-base-200 flex flex-col font-sans">
      {/* Header bar */}
      <div className="bg-gradient-to-r from-primary to-primary-focus text-primary-content px-6 py-4 flex items-center justify-between shadow-xl shrink-0 border-b border-primary/20">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-white/10 rounded-xl">
            <FaGraduationCap className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">{t('teach_mode.title')}</h1>
            <p className="text-xs text-white/70 font-medium">
              {t('teach_mode.subtitle', { count: linkCount })}
            </p>
          </div>
        </div>
        <button className="btn btn-sm btn-circle btn-ghost text-white hover:bg-white/10" onClick={onClose}>
          <FaTimes className="w-5 h-5" />
        </button>
      </div>

      {/* Main content - split layout */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left panel — Input detection */}
        <div className={clsx(
          'border-b md:border-b-0 md:border-r border-base-300 flex flex-col transition-all duration-300 bg-base-100',
          leftCollapsed ? 'md:w-80 shrink-0' : 'md:w-1/2',
        )}>
          {/* Collapsible header */}
          <button
            className="p-4 bg-base-200/40 border-b border-base-300 flex items-center justify-between w-full hover:bg-base-200/70 transition-all duration-200"
            onClick={() => setLeftCollapsed(!leftCollapsed)}
          >
            <h2 className="font-semibold text-sm flex items-center gap-2 text-base-content/80">
              <span className="badge badge-primary badge-sm font-bold text-xs">1</span>
              {t('teach_mode.step_1')}
            </h2>
            {leftCollapsed ? <FaChevronDown className="w-4.5 h-4.5 text-base-content/40 hover:text-base-content/75" /> : <FaChevronUp className="w-4.5 h-4.5 text-base-content/40 hover:text-base-content/75" />}
          </button>

          {!leftCollapsed ? (
            <div className="flex-1 flex items-center justify-center p-8 bg-gradient-to-b from-transparent to-base-200/10">
              {!detectedInput ? (
                <div className="text-center space-y-5 max-w-sm">
                  <div className="relative inline-flex items-center justify-center">
                    <span className="absolute inline-flex h-20 w-20 rounded-full bg-primary/10 animate-ping" />
                    <div className="relative p-6 bg-primary/5 rounded-full border border-primary/10">
                      <FaHandPointer className="w-12 h-12 text-primary/60" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xl font-bold tracking-tight text-base-content/70">{t('teach_mode.waiting')}</p>
                    <p className="text-sm text-base-content/40 leading-relaxed">{t('teach_mode.waiting_hint')}</p>
                  </div>
                </div>
              ) : (
                <div className="text-center space-y-6 w-full max-w-sm p-6 rounded-2xl bg-base-100 border border-base-200 shadow-xl shadow-base-200/30">
                  <div className="inline-flex p-3 bg-success/10 rounded-full text-success">
                    <FaCheck className="w-8 h-8" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-xl font-extrabold tracking-tight">{detectedInput.state.name}</h3>
                    <p className="text-xs font-mono text-base-content/40 bg-base-200/50 py-1 px-2.5 rounded-md inline-block">{detectedInput.entity_id}</p>
                  </div>
                  <div className={clsx(
                    'badge badge-lg font-bold text-xs uppercase px-4 py-2 border-0',
                    detectedInput.state.state === 'single' && 'bg-success/20 text-success',
                    detectedInput.state.state === 'double' && 'bg-warning/20 text-warning-content',
                    detectedInput.state.state === 'long' && 'bg-info/20 text-info-content',
                    detectedInput.state.state === 'pressed' && 'bg-success/20 text-success',
                    detectedInput.state.state === 'released' && 'bg-warning/20 text-warning-content',
                  )}>
                    {detectedInput.state.state}
                  </div>

                  {/* Click type override */}
                  <div className="form-control space-y-2 pt-2 border-t border-base-100">
                    <label className="label pb-1 justify-center">
                      <span className="label-text font-semibold text-xs text-base-content/50 uppercase tracking-wider">{t('quick_action.click_type')}</span>
                    </label>
                    <div className="flex flex-wrap gap-1.5 justify-center">
                      {clickTypes.map((ct) => (
                        <button
                          key={ct}
                          type="button"
                          onClick={() => setClickType(ct)}
                          className={clsx(
                            'btn btn-xs rounded-lg transition-all duration-200 font-medium px-3',
                            clickType === ct ? 'btn-primary shadow-sm shadow-primary/20 scale-[1.03]' : 'btn-ghost border border-base-300',
                          )}
                        >
                          {t(`quick_action.click_types.${ct}`)}
                        </button>
                      ))}
                    </div>
                  </div>

                  <button
                    className="btn btn-ghost btn-xs gap-1.5 text-base-content/40 hover:text-base-content/80 mt-2"
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
            <div className="p-4 flex items-center gap-3 bg-primary/5 border-b border-primary/10">
              <div className="p-2 bg-success/15 rounded-lg text-success shrink-0">
                <FaCheck className="w-4 h-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-bold text-sm truncate text-base-content">{detectedInput.state.name}</p>
                <p className="text-xxs font-mono text-base-content/40 truncate">{detectedInput.entity_id}</p>
              </div>
              <div className={clsx(
                'badge badge-sm font-bold text-xxs uppercase shrink-0',
                detectedInput.state.state === 'single' && 'bg-success/20 text-success border-0',
                detectedInput.state.state === 'double' && 'bg-warning/20 text-warning-content border-0',
                detectedInput.state.state === 'long' && 'bg-info/20 text-info-content border-0',
              )}>
                {clickType}
              </div>
              <button
                className="btn btn-ghost btn-xs btn-circle text-base-content/40 hover:text-base-content/80 shrink-0"
                onClick={() => { setDetectedInput(null); setSaveStatus('idle'); setLeftCollapsed(false); }}
              >
                <FaUndo className="w-3 h-3" />
              </button>
            </div>
          ) : (
            <div className="p-5 text-sm text-base-content/40 text-center flex items-center justify-center gap-2">
              <span className="loading loading-ring loading-xs" />
              {t('teach_mode.waiting')}
            </div>
          )}
        </div>

        {/* Right panel — Output selection + Bindings */}
        <div className="flex-1 flex flex-col min-w-0 bg-base-200/30">
          {/* Tab bar */}
          <div className="flex border-b border-base-300 bg-base-100 shadow-sm shrink-0 px-2">
            <button
              className={clsx(
                'flex-1 py-3.5 text-sm font-semibold flex items-center justify-center gap-2 border-b-2 transition-all duration-200',
                rightTab === 'link' ? 'border-primary text-primary font-bold' : 'border-transparent text-base-content/50 hover:text-base-content/85',
              )}
              onClick={() => setRightTab('link')}
            >
              <FaBolt className="w-3.5 h-3.5" />
              {t('teach_mode.tab_link')}
            </button>
            <button
              className={clsx(
                'flex-1 py-3.5 text-sm font-semibold flex items-center justify-center gap-2 border-b-2 transition-all duration-200',
                rightTab === 'bindings' ? 'border-primary text-primary font-bold' : 'border-transparent text-base-content/50 hover:text-base-content/85',
              )}
              onClick={() => setRightTab('bindings')}
            >
              <FaList className="w-3.5 h-3.5" />
              {t('teach_mode.tab_bindings')}
              {bindings.length > 0 && (
                <span className="badge badge-sm badge-primary text-xxs font-bold px-1.5">{bindings.length}</span>
              )}
            </button>
          </div>

          {/* Tab content */}
          {rightTab === 'link' ? (
            /* Link tab */
            <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-2xl mx-auto w-full">
              {/* Category tabs */}
              <div className="space-y-2">
                <label className="label-text font-semibold text-xs text-base-content/50 uppercase tracking-wider block">
                  {t('teach_mode.step_2')}
                </label>
                <div className="flex flex-wrap gap-1.5 bg-base-100 p-1.5 rounded-xl border border-base-200 shadow-sm">
                  {availableCategories.map(({ key, label, count }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => { setTargetCategory(key); setTargetId(''); setActionValue('TOGGLE'); }}
                      className={clsx(
                        'btn btn-sm rounded-lg flex-1 gap-1.5 font-medium transition-all duration-200',
                        targetCategory === key
                          ? 'btn-primary shadow-sm shadow-primary/10'
                          : 'btn-ghost text-base-content/60 hover:bg-base-200/50',
                      )}
                    >
                      {label}
                      <span className={clsx(
                        'badge badge-xs font-semibold',
                        targetCategory === key ? 'bg-primary-content text-primary border-0' : 'badge-ghost',
                      )}>{count}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Entity picker */}
              <div className="space-y-2">
                <SearchableEntityPicker
                  value={targetId}
                  onChange={setTargetId}
                  items={currentItems}
                  placeholder={t('teach_mode.select_target')}
                  recentKey={targetCategory}
                />
              </div>

              {/* Action selector */}
              <div className="form-control space-y-2">
                <label className="label-text font-semibold text-xs text-base-content/50 uppercase tracking-wider">
                  {t('quick_action.action')}
                </label>
                <Select value={actionValue} onValueChange={setActionValue}>
                  <SelectTrigger className="w-full bg-base-100 border-base-200 shadow-sm rounded-xl h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-base-100 border-base-200">
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
                className="btn btn-primary btn-block gap-2 h-13 text-base font-semibold shadow-lg shadow-primary/20 rounded-xl transition-all duration-200 active:scale-[0.98]"
                disabled={!canLink}
                onClick={handleLink}
              >
                {saveStatus === 'saving' ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : (
                  <>
                    <FaLink className="w-4 h-4" />
                    {t('teach_mode.link')}
                  </>
                )}
              </button>

              {/* Status messages */}
              {saveStatus === 'error' && errorMessage && (
                <div className="alert alert-error text-sm py-3 rounded-xl border border-error/10 shadow-sm">
                  <FaExclamationTriangle className="w-4 h-4" />
                  <span>{errorMessage}</span>
                </div>
              )}
              {saveStatus === 'success' && (
                <div className="alert alert-success text-sm py-3 rounded-xl border border-success/10 shadow-sm">
                  <FaCheck className="w-4 h-4" />
                  <span>{t('quick_action.saved')}</span>
                </div>
              )}
            </div>
          ) : (
            /* Bindings tab */
            <div className="flex-1 overflow-y-auto p-6 max-w-2xl mx-auto w-full">
              {!detectedInput ? (
                <div className="text-center text-base-content/40 py-12 bg-base-100 rounded-2xl border border-dashed border-base-300">
                  <FaList className="w-10 h-10 mx-auto mb-3 opacity-25" />
                  <p className="font-medium text-sm">{t('teach_mode.bindings_no_input')}</p>
                </div>
              ) : bindingsLoading ? (
                <div className="flex justify-center py-12">
                  <span className="loading loading-ring loading-md text-primary" />
                </div>
              ) : bindings.length === 0 ? (
                <div className="text-center text-base-content/40 py-12 bg-base-100 rounded-2xl border border-dashed border-base-300">
                  <FaList className="w-10 h-10 mx-auto mb-3 opacity-25" />
                  <p className="font-medium text-sm">{t('teach_mode.bindings_empty')}</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs font-semibold text-base-content/50 uppercase tracking-wider mb-2">
                    {t('teach_mode.bindings_for', { name: detectedInput.state.name })}
                  </p>
                  <div className="space-y-2">
                    {bindings.map((b, i) => (
                      <div key={i} className="flex items-center gap-3 bg-base-100 border border-base-200 shadow-sm rounded-xl px-4 py-3 text-sm hover:border-base-300 transition-colors">
                        <span className="badge badge-sm font-bold text-xxs bg-primary/10 text-primary border-0 px-2 py-1 uppercase">{b.clickType}</span>
                        <span className="text-base-content/30 font-medium">→</span>
                        <span className="badge badge-sm font-semibold text-xxs bg-base-200 text-base-content/65 border-0 px-2 py-1 uppercase">{b.actionType}</span>
                        <span className="font-bold text-base-content/80 truncate flex-1 font-mono text-xs">{b.target}</span>
                        <span className="badge badge-sm font-bold text-xxs badge-outline border-base-300 text-base-content/70 px-2 py-1 uppercase">{b.action}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Bottom log panel */}
      {log.length > 0 && (
        <div className="border-t border-base-300 bg-base-100 shrink-0 shadow-2xl">
          <div className="p-3 px-6 max-h-40 overflow-y-auto">
            <h3 className="text-xxs font-bold text-base-content/40 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <FaHistory className="w-3 h-3" />
              {t('teach_mode.history')}
            </h3>
            <div className="space-y-1.5">
              {log.slice(0, 10).map((entry) => (
                <div
                  key={entry.id}
                  className={clsx(
                    'text-xs py-2 px-3 rounded-lg flex items-center gap-3 border shadow-sm transition-all duration-200',
                    entry.status === 'success' 
                      ? 'bg-success/5 border-success/10 text-success' 
                      : 'bg-error/5 border-error/10 text-error'
                  )}
                >
                  {entry.status === 'success' ? <FaCheck className="w-3.5 h-3.5 shrink-0" /> : <FaExclamationTriangle className="w-3.5 h-3.5 shrink-0" />}
                  <span className="font-bold text-base-content/85">{entry.inputName}</span>
                  <span className="opacity-50 font-medium">→</span>
                  <span className="font-semibold text-base-content/85">{entry.targetName}</span>
                  <div className="flex items-center gap-1 ml-auto shrink-0 font-bold text-xxs uppercase">
                    <span className="bg-base-200 text-base-content/60 px-1.5 py-0.5 rounded">{entry.clickType}</span>
                    <span className="bg-base-200 text-base-content/60 px-1.5 py-0.5 rounded">{entry.action}</span>
                  </div>
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
