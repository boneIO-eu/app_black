import React, { useState, useContext, useMemo, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
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
  FaLink, FaList, FaHistory, FaMousePointer, FaBan, FaFilter,
  FaNetworkWired, FaPlay, FaPencilAlt, FaTrash, FaSave, FaClock, FaExternalLinkAlt,
} from 'react-icons/fa';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { FormInputToggle } from '@/components/UISettings/widgets/FormInputToggle';

/** Click types for event-type inputs. */
const EVENT_CLICK_TYPES = ['single', 'double', 'triple', 'long'] as const;
/** Sequence click types (multi-gesture combos). */
const SEQUENCE_CLICK_TYPES = ['double_then_long', 'single_then_long', 'double_then_single'] as const;
/** Click types for binary_sensor inputs. */
const BINARY_SENSOR_CLICK_TYPES = ['pressed', 'released'] as const;
/** Output action options. */
const OUTPUT_ACTIONS = ['TOGGLE', 'ON', 'OFF'] as const;
/** Cover action options. */
const COVER_ACTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP'] as const;

const IGNORED_STORAGE_KEY = 'boneio-teach-ignored';
const MAX_RECENT_EVENTS = 15;

type SaveStatus = 'idle' | 'saving' | 'success' | 'error';
type TargetCategory = 'output' | 'remote_output' | 'cover' | 'remote_cover';
type RightTab = 'link' | 'bindings';

/** Extract a human-readable detail string from an axios-like error. */
function extractErrorDetail(err: unknown, fallback: string): string {
  const axErr = err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string } | undefined;
  const detail = axErr?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message;
  if (typeof axErr?.message === 'string') return axErr.message;
  return fallback;
}

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
  /** Index inside the action list of its click type (used by PUT/DELETE) */
  index: number;
  actionType: string;
  target: string;
  action: string;
  remoteDevice?: string | null;
  /** Raw action dict as stored in the YAML config */
  raw: Record<string, unknown>;
}

/** Binding currently being edited (identifies it server-side). */
interface EditingBinding {
  clickType: string;
  index: number;
}

/** Recent event entry for diagnostics. */
interface RecentEvent {
  entityId: string;
  name: string;
  state: string;
  area?: string | null;
  type: string;
  timestamp: number;
}

interface TeachModeProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Close teach mode */
  onClose: () => void;
}

/**
 * Teach Mode — full-screen/modal overlay for linking inputs to outputs.
 *
 * Features:
 * - Auto-detect input from physical button press (with area filter)
 * - Manual input selection from picker
 * - Auto-ignore sensors (binary_sensor type) to prevent motion sensor spam
 * - Ignored inputs list with un-ignore capability
 * - Recent events diagnostics log
 * - Categorized output picker (Output / Remote Output / Cover / Remote Cover)
 * - Current bindings viewer
 */
const TeachMode: React.FC<TeachModeProps> = ({ open, onClose }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
  // Binding being edited (null = creating a new one)
  const [editing, setEditing] = useState<EditingBinding | null>(null);
  // Binding pending delete confirmation ("clickType:index")
  const [deleteCandidate, setDeleteCandidate] = useState<string | null>(null);
  // Bumped whenever bindings must be re-fetched
  const [bindingsVersion, setBindingsVersion] = useState(0);

  // --- NEW: Area filter ---
  const [areaFilter, setAreaFilter] = useState<string>('');

  // --- NEW: Auto-ignore binary sensors ---
  const [autoIgnoreSensors, setAutoIgnoreSensors] = useState(true);

  // --- Capture sequences toggle ---
  const [captureSequences, setCaptureSequences] = useState(false);

  // --- NEW: Ignored entity IDs ---
  const [ignoredIds, setIgnoredIds] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(IGNORED_STORAGE_KEY);
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });

  // --- NEW: Collapsible sections ---
  const [showManualPicker, setShowManualPicker] = useState(false);
  const [showIgnored, setShowIgnored] = useState(false);
  const [showRecentEvents, setShowRecentEvents] = useState(false);

  // --- NEW: Recent events ---
  const [recentEvents, setRecentEvents] = useState<RecentEvent[]>([]);

  // Track previous input states to detect changes
  const prevInputsRef = useRef<Map<string, { state: string; timestamp: number }>>(new Map());

  const validInputs = useMemo(() => inputs.filter(isInputEvent), [inputs]);

  // Unique areas from all entities (inputs + outputs + covers) for area filter
  const allAreas = useMemo(() => {
    const areas = new Map<string, string>();
    validInputs.forEach((input: InputEvent) => {
      if (input.state.area) areas.set(input.state.area, input.state.area);
    });
    outputs.forEach((o: OutputEvent) => {
      if (o.state.area) areas.set(o.state.area, o.state.area);
    });
    covers.forEach((c: CoverEvent) => {
      if ((c.state as any).area) areas.set((c.state as any).area, (c.state as any).area);
    });
    return [...areas.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [validInputs, outputs, covers]);

  /** Persist ignored IDs to localStorage. */
  const persistIgnored = useCallback((ids: Set<string>) => {
    try {
      localStorage.setItem(IGNORED_STORAGE_KEY, JSON.stringify([...ids]));
    } catch { /* quota exceeded — ignore */ }
  }, []);

  /** Add an entity to the ignored list. */
  const addIgnored = useCallback((entityId: string) => {
    setIgnoredIds((prev) => {
      const next = new Set(prev);
      next.add(entityId);
      persistIgnored(next);
      return next;
    });
  }, [persistIgnored]);

  /** Remove an entity from the ignored list. */
  const removeIgnored = useCallback((entityId: string) => {
    setIgnoredIds((prev) => {
      const next = new Set(prev);
      next.delete(entityId);
      persistIgnored(next);
      return next;
    });
  }, [persistIgnored]);

  // Build input items for manual picker
  const inputItems: EntityItem[] = useMemo(() => {
    return validInputs.map((input: InputEvent): EntityItem => ({
      id: input.entity_id,
      name: input.state.name || input.entity_id,
      area: input.state.area || undefined,
      badge: input.state.type === 'input' ? 'event' : 'binary',
      badgeClass: input.state.type === 'input' ? 'badge-info' : 'badge-warning',
    }));
  }, [validInputs]);

  /** Input items filtered by area filter (used in manual picker and ignore picker). */
  const filteredInputItems = useMemo(() => {
    if (!areaFilter) return inputItems;
    return inputItems.filter((item) => item.area === areaFilter);
  }, [inputItems, areaFilter]);

  // Detect input events via WebSocket — runs CONTINUOUSLY (even when dialog closed).
  // Events are always collected into recentEvents so the user sees them when opening the dialog.
  // Auto-selection of detected input only happens when the dialog is open.
  useEffect(() => {
    const baseEventTypes = ['single', 'double', 'long', 'pressed', 'released', 'triple'];
    const sequenceTypes = ['double_then_long', 'single_then_long', 'double_then_single'];
    const eventTypes = captureSequences ? [...baseEventTypes, ...sequenceTypes] : baseEventTypes;

    validInputs.forEach((inputEvent: InputEvent) => {
      const prevData = prevInputsRef.current.get(inputEvent.entity_id);
      const currentState = inputEvent.state.state;
      const currentTimestamp = inputEvent.state.timestamp;

      // First time seeing this input — just record it, no event
      if (!prevData) {
        prevInputsRef.current.set(inputEvent.entity_id, {
          state: currentState,
          timestamp: currentTimestamp
        });
        return;
      }

      // Detect change: timestamp must differ from last seen value.
      if (prevData.timestamp !== currentTimestamp && eventTypes.includes(currentState)) {
        // Add to recent events log (always, even when dialog is closed)
        setRecentEvents((prev) => [{
          entityId: inputEvent.entity_id,
          name: inputEvent.state.name,
          state: currentState,
          area: inputEvent.state.area,
          type: inputEvent.state.type,
          timestamp: Date.now(),
        }, ...prev].slice(0, MAX_RECENT_EVENTS));

        // Auto-select input only when dialog is open
        if (open) {
          // Check if ignored
          if (ignoredIds.has(inputEvent.entity_id)) {
            // Skip — on ignored list
          } else if (autoIgnoreSensors && inputEvent.state.type !== 'input') {
            // Auto-ignore: binary_sensor detected → add to ignored list
            addIgnored(inputEvent.entity_id);
          } else if (areaFilter && inputEvent.state.area !== areaFilter) {
            // Skip — wrong area
          } else {
            // Accept this input!
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
        }
      }

      // Always update prevInputsRef
      prevInputsRef.current.set(inputEvent.entity_id, {
        state: currentState,
        timestamp: currentTimestamp
      });
    });
  }, [validInputs, open, ignoredIds, autoIgnoreSensors, areaFilter, addIgnored, captureSequences]);

  /** Handle manual input selection from picker. */
  const handleManualSelect = useCallback((entityId: string) => {
    const input = validInputs.find((i: InputEvent) => i.entity_id === entityId);
    if (!input) return;
    setDetectedInput(input);
    setClickType(input.state.type === 'input' ? 'single' : 'pressed');
    setSaveStatus('idle');
    setErrorMessage('');
    setLeftCollapsed(true);
    setShowManualPicker(false);
  }, [validInputs]);

  /** Handle selecting an input from recent events. */
  const handleRecentEventSelect = useCallback((entityId: string, state: string) => {
    const input = validInputs.find((i: InputEvent) => i.entity_id === entityId);
    if (!input) return;
    setDetectedInput(input);
    const isEvent = input.state.type === 'input';
    if (isEvent) {
      setClickType(state);
    } else {
      setClickType(state === 'pressed' || state === 'ON' ? 'pressed' : 'released');
    }
    setSaveStatus('idle');
    setErrorMessage('');
    setLeftCollapsed(true);
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
        const resp = await axios.get('/api/config/input-actions', {
          params: { entity_id: detectedInput.entity_id },
        });
        const list = Array.isArray(resp.data?.actions) ? resp.data.actions : [];
        setBindings(list.map((a: Record<string, unknown>): ActionBinding => ({
          clickType: String(a.click_type ?? '?'),
          index: Number(a.index ?? 0),
          actionType: String(a.action_type ?? '?'),
          target: String(a.target ?? '?'),
          action: String(a.action ?? '?'),
          remoteDevice: (a.remote_device as string | null) ?? null,
          raw: (a.raw as Record<string, unknown>) ?? {},
        })));
      } catch {
        setBindings([]);
      } finally {
        setBindingsLoading(false);
      }
    };

    fetchBindings();
  }, [detectedInput, linkCount, bindingsVersion]);

  // Build categorized entity items (exclude 'none' and 'cover' outputs —
  // none has no HA entity, cover must be controlled via cover entities only)
  const localOutputItems: TeachEntityItem[] = useMemo(() => {
    return outputs
      .filter((o: OutputEvent) => {
        if (o.state.remote) return false;
        const ot = o.state.type?.toLowerCase();
        return ot !== 'none' && ot !== 'cover';
      })
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
  const clickTypes = detectedInput?.state.type === 'input'
    ? (captureSequences ? [...EVENT_CLICK_TYPES, ...SEQUENCE_CLICK_TYPES] : EVENT_CLICK_TYPES)
    : BINARY_SENSOR_CLICK_TYPES;

  const selectedItem = useMemo(
    () => currentItems.find((item) => item.id === targetId),
    [currentItems, targetId]
  );

  /** Build the target-specific part of a quick-action payload. */
  const buildTargetPayload = useCallback((): Record<string, string> | null => {
    if (!selectedItem || !targetId) return null;
    const payload: Record<string, string> = {
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
    return payload;
  }, [selectedItem, targetId, actionValue]);

  /** Leave edit mode and clear the target selection. */
  const handleCancelEdit = useCallback(() => {
    setEditing(null);
    setTargetId('');
    setSaveStatus('idle');
    setErrorMessage('');
  }, []);

  /** Navigate to the full config editor for the current input. */
  const handleGoToSettings = useCallback(() => {
    if (!detectedInput) return;
    const section = detectedInput.state.remote ? 'remote_inputs' : 'local_inputs';
    onClose();
    navigate(`/settings/${section}?edit=${encodeURIComponent(detectedInput.entity_id)}`);
  }, [detectedInput, navigate, onClose]);

  /** Load an existing binding into the link form for editing. */
  const handleStartEdit = useCallback((b: ActionBinding) => {
    const raw = b.raw as Record<string, string | undefined>;
    let category: TargetCategory | null = null;
    let nextTargetId = '';

    switch (b.actionType) {
      case 'output':
        category = 'output';
        nextTargetId = raw.boneio_output || '';
        break;
      case 'cover':
        category = 'cover';
        nextTargetId = raw.boneio_cover || '';
        break;
      case 'remote_output':
        category = 'remote_output';
        nextTargetId = `${raw.remote_device || raw.boneio_id || ''}/${raw.output_id || ''}`;
        break;
      case 'remote_cover':
        category = 'remote_cover';
        nextTargetId = `${raw.remote_device || raw.boneio_id || ''}/${raw.cover_id || ''}`;
        break;
    }

    if (!category) {
      setErrorMessage(t('teach_mode.edit_unsupported'));
      setRightTab('link');
      setSaveStatus('error');
      return;
    }

    setEditing({ clickType: b.clickType, index: b.index });
    setTargetCategory(category);
    setTargetId(nextTargetId);
    setActionValue(b.action && b.action !== '?' ? b.action : 'TOGGLE');
    setClickType(b.clickType);
    setRightTab('link');
    setSaveStatus('idle');
    setErrorMessage('');
  }, [t]);

  /** Delete a binding after the inline confirmation. */
  const handleDeleteBinding = useCallback(async (b: ActionBinding) => {
    if (!detectedInput) return;
    setBindingsLoading(true);
    try {
      await axios.delete('/api/config/quick-action', {
        data: {
          entity_id: detectedInput.entity_id,
          click_type: b.clickType,
          index: b.index,
        },
        timeout: 15_000,
      });
      setDeleteCandidate(null);
      if (editing && editing.clickType === b.clickType && editing.index === b.index) {
        setEditing(null);
        setTargetId('');
      }
      setBindingsVersion((v) => v + 1);
    } catch (err: unknown) {
      setErrorMessage(extractErrorDetail(err, t('quick_action.save_error')));
      setSaveStatus('error');
      setBindingsLoading(false);
      return;
    }
    setBindingsLoading(false);
  }, [detectedInput, editing, t]);

  const handleLink = useCallback(async () => {
    if (!detectedInput || !targetId || !selectedItem) return;

    const targetPayload = buildTargetPayload();
    if (!targetPayload) return;

    setSaveStatus('saving');
    setErrorMessage('');

    try {
      if (editing) {
        await axios.put('/api/config/quick-action', {
          entity_id: detectedInput.entity_id,
          click_type: editing.clickType,
          index: editing.index,
          new_click_type: clickType,
          ...targetPayload,
        }, { timeout: 15_000 });

        setSaveStatus('success');
        setEditing(null);
        setBindingsVersion((v) => v + 1);

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
          setSaveStatus('idle');
          setTargetId('');
          setRightTab('bindings');
        }, 1000);
        return;
      }

      const payload: Record<string, string> = {
        entity_id: detectedInput.entity_id,
        click_type: clickType,
        ...targetPayload,
      };

      await axios.post('/api/config/quick-action', payload, { timeout: 15_000 });
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

    } catch (err: unknown) {
      setSaveStatus('error');
      const msg = extractErrorDetail(err, t('quick_action.save_error'));
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
  }, [detectedInput, targetId, selectedItem, clickType, actionValue, editing, buildTargetPayload, t]);

  // --- Test action ---
  const [testStatus, setTestStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [testError, setTestError] = useState<string | null>(null);

  /**
   * Build the action definition in the same format as YAML config,
   * and execute it via POST /api/test-action.
   */
  const handleTestAction = useCallback(async () => {
    if (!targetId || !selectedItem) return;
    setTestStatus('loading');
    setTestError(null);

    try {
      const actionDef: Record<string, string> = {};

      switch (selectedItem.actionType) {
        case 'output':
          actionDef.action = 'output';
          actionDef.boneio_output = targetId;
          actionDef.action_output = actionValue;
          break;
        case 'cover':
          actionDef.action = 'cover';
          actionDef.boneio_cover = targetId;
          actionDef.action_cover = actionValue;
          break;
        case 'remote_output':
          actionDef.action = 'remote_output';
          actionDef.boneio_id = selectedItem.remoteDevice || '';
          actionDef.output_id = targetId.includes('/') ? targetId.split('/').slice(1).join('/') : targetId;
          actionDef.action_output = actionValue;
          break;
        case 'remote_cover':
          actionDef.action = 'remote_cover';
          actionDef.boneio_id = selectedItem.remoteDevice || '';
          actionDef.cover_id = targetId.includes('/') ? targetId.split('/').slice(1).join('/') : targetId;
          actionDef.action_cover = actionValue;
          break;
      }

      await axios.post('/api/test-action', { action: actionDef });
      setTestStatus('success');
      setTimeout(() => setTestStatus('idle'), 2000);
    } catch (err: unknown) {
      setTestError(extractErrorDetail(err, 'Test failed'));
      setTestStatus('error');
      setTimeout(() => { setTestStatus('idle'); setTestError(null); }, 4000);
    }
  }, [targetId, selectedItem, actionValue]);

  const canTest = targetId && selectedItem && testStatus !== 'loading';

  const canLink = detectedInput && targetId && selectedItem && saveStatus !== 'saving' && saveStatus !== 'success';

  // Ignored items resolved to names
  const ignoredItems = useMemo(() => {
    return [...ignoredIds].map((eid) => {
      const input = validInputs.find((i: InputEvent) => i.entity_id === eid);
      return { id: eid, name: input?.state.name || eid, area: input?.state.area || undefined };
    });
  }, [ignoredIds, validInputs]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        className="p-0 gap-0 max-h-[92vh] sm:max-h-[90vh] sm:max-w-5xl flex flex-col overflow-y-auto sm:overflow-hidden"
      >
        {/* Header bar */}
        <DialogHeader className="bg-base-200/80 backdrop-blur-md text-base-content px-6 py-4 flex flex-row items-center justify-between shadow-sm shrink-0 border-b border-base-300">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-base-300 rounded-xl text-primary">
              <FaGraduationCap className="w-6 h-6" />
            </div>
            <div>
              <DialogTitle className="text-lg font-bold tracking-tight">{t('teach_mode.title')}</DialogTitle>
              <p className="text-xs text-base-content/60 font-medium">
                {t('teach_mode.subtitle', { count: linkCount })}
              </p>
            </div>
          </div>
          <button className="btn btn-sm btn-circle btn-ghost text-base-content/60 hover:text-base-content hover:bg-base-300" onClick={onClose}>
            <FaTimes className="w-5 h-5" />
          </button>
        </DialogHeader>

        {/* Main content - split layout */}
        <div className="flex-1 flex flex-col md:flex-row overflow-y-auto md:overflow-hidden">
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
              {leftCollapsed ? <FaChevronDown className="w-3 h-3 text-base-content/40" /> : <FaChevronUp className="w-3 h-3 text-base-content/40" />}
            </button>

            {!leftCollapsed ? (
              <div className="flex-1 overflow-y-auto">
                {/* Area filter — always visible at top */}
                <div className="p-3 px-6 bg-base-200/30 border-b border-base-200 space-y-2">
                  <label className="flex items-center gap-2 text-xs font-semibold text-base-content/60 uppercase tracking-wider">
                    <FaFilter className="w-3 h-3" />
                    {t('teach_mode.area_filter')}
                  </label>
                  <select
                    className="select select-sm select-bordered w-full"
                    value={areaFilter}
                    onChange={(e) => setAreaFilter(e.target.value)}
                  >
                    <option value="">{t('teach_mode.all_areas')}</option>
                    {allAreas.map(({ id, name }) => (
                      <option key={id} value={id}>{name}</option>
                    ))}
                  </select>
                  {areaFilter && (
                    <p className="text-xs text-info flex items-center gap-1.5">
                      <FaFilter className="w-3 h-3 shrink-0" />
                      {t('teach_mode.area_filter_active', { area: areaFilter })}
                    </p>
                  )}
                </div>

                {/* Detected input or waiting */}
                {!detectedInput ? (
                  <div className="p-6 space-y-4">
                    {/* Waiting animation */}
                    <div className="text-center space-y-3">
                      <div className="relative inline-flex items-center justify-center">
                        <span className="absolute inline-flex h-16 w-16 rounded-full bg-primary/10 animate-ping" />
                        <div className="relative p-4 bg-primary/5 rounded-full border border-primary/10">
                          <FaHandPointer className="w-8 h-8 text-primary/60" />
                        </div>
                      </div>
                      <p className="text-base font-bold tracking-tight text-base-content/70">{t('teach_mode.waiting')}</p>
                      <p className="text-xs text-base-content/40">{t('teach_mode.waiting_hint')}</p>
                    </div>

                    {/* Auto-ignore sensors toggle */}
                    <FormInputToggle
                      variant="card"
                      label={t('teach_mode.auto_ignore')}
                      description={t('teach_mode.auto_ignore_hint')}
                      checked={autoIgnoreSensors}
                      onChange={setAutoIgnoreSensors}
                      toggleSize="toggle-sm"
                      toggleColor="toggle-primary"
                    />

                    {/* Capture sequences toggle */}
                    <FormInputToggle
                      variant="card"
                      label={t('teach_mode.capture_sequences')}
                      description={t('teach_mode.capture_sequences_hint')}
                      checked={captureSequences}
                      onChange={setCaptureSequences}
                      toggleSize="toggle-sm"
                      toggleColor="toggle-secondary"
                    />
                  </div>
                ) : (
                  <div className="p-6">
                    <div className="text-center space-y-4 w-full max-w-sm mx-auto p-5 rounded-2xl bg-base-100 border border-base-200 shadow-lg">
                      <div className="inline-flex p-3 bg-success/10 rounded-full text-success">
                        <FaCheck className="w-7 h-7" />
                      </div>
                      <div className="space-y-1">
                        <h3 className="text-lg font-extrabold tracking-tight">{detectedInput.state.name}</h3>
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
                      <div className="form-control space-y-2 pt-2 border-t border-base-200">
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
                                'btn btn-xs transition-all duration-200 font-medium px-3',
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
                  </div>
                )}

                {/* Collapsible sections (always visible below) */}
                <div className="border-t border-base-200">
                  {/* Manual picker */}
                  <button
                    className="w-full p-3 px-6 flex items-center justify-between text-sm font-medium text-base-content/70 hover:bg-base-200/40 transition-colors border-b border-base-200"
                    onClick={() => setShowManualPicker(!showManualPicker)}
                  >
                    <span className="flex items-center gap-2">
                      <FaMousePointer className="w-3.5 h-3.5 text-primary/60" />
                      {t('teach_mode.manual_select')}
                    </span>
                    {showManualPicker ? <FaChevronUp className="w-3 h-3 text-base-content/30" /> : <FaChevronDown className="w-3 h-3 text-base-content/30" />}
                  </button>
                  {showManualPicker && (
                    <div className="p-4 border-b border-base-200 bg-base-200/20">
                      <SearchableEntityPicker
                        value=""
                        onChange={handleManualSelect}
                        items={filteredInputItems}
                        placeholder={t('teach_mode.manual_placeholder')}
                        recentKey="teach-inputs"
                        nested
                      />
                    </div>
                  )}

                  {/* Ignored inputs */}
                  <button
                    className="w-full p-3 px-6 flex items-center justify-between text-sm font-medium text-base-content/70 hover:bg-base-200/40 transition-colors border-b border-base-200"
                    onClick={() => setShowIgnored(!showIgnored)}
                  >
                    <span className="flex items-center gap-2">
                      <FaBan className="w-3.5 h-3.5 text-error/60" />
                      {t('teach_mode.ignored_title')}
                      {ignoredItems.length > 0 && (
                        <span className="badge badge-xs badge-error text-xxs font-bold">{ignoredItems.length}</span>
                      )}
                    </span>
                    {showIgnored ? <FaChevronUp className="w-3 h-3 text-base-content/30" /> : <FaChevronDown className="w-3 h-3 text-base-content/30" />}
                  </button>
                  {showIgnored && (
                    <div className="p-4 border-b border-base-200 bg-base-200/20 max-h-64 overflow-y-auto space-y-3">
                      {/* Manual ignore picker */}
                      <SearchableEntityPicker
                        value=""
                        onChange={(id) => addIgnored(id)}
                        items={filteredInputItems}
                        excludeIds={[...ignoredIds]}
                        placeholder={t('teach_mode.add_to_ignored')}
                        recentKey="teach-ignore"
                        compact
                        nested
                      />

                      {/* List of ignored items */}
                      {ignoredItems.length === 0 ? (
                        <p className="text-xs text-base-content/40 text-center py-2">{t('teach_mode.ignored_empty')}</p>
                      ) : (
                        <div className="space-y-1.5">
                          {ignoredItems.map((item) => (
                            <div key={item.id} className="flex items-center gap-2 text-xs bg-base-100 rounded-lg px-3 py-2 border border-base-200">
                              <FaBan className="w-3 h-3 text-error/40 shrink-0" />
                              <span className="font-medium truncate flex-1">{item.name}</span>
                              {item.area && <span className="badge badge-xs badge-ghost text-xxs">{item.area}</span>}
                              <button
                                className="btn btn-ghost btn-xs btn-circle text-success/60 hover:text-success"
                                onClick={() => removeIgnored(item.id)}
                                title={t('teach_mode.unignore')}
                              >
                                <FaUndo className="w-3 h-3" />
                              </button>
                            </div>
                          ))}
                          <button
                            className="btn btn-ghost btn-xs text-error/60 w-full mt-1"
                            onClick={() => { setIgnoredIds(new Set()); persistIgnored(new Set()); }}
                          >
                            {t('teach_mode.clear_ignored')}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Recent events (diagnostics) */}
                  <button
                    className="w-full p-3 px-6 flex items-center justify-between text-sm font-medium text-base-content/70 hover:bg-base-200/40 transition-colors"
                    onClick={() => setShowRecentEvents(!showRecentEvents)}
                  >
                    <span className="flex items-center gap-2">
                      <FaNetworkWired className="w-3.5 h-3.5 text-info/60" />
                      {t('teach_mode.recent_events')}
                      {recentEvents.length > 0 && (
                        <span className="badge badge-xs badge-info text-xxs font-bold">{recentEvents.length}</span>
                      )}
                    </span>
                    {showRecentEvents ? <FaChevronUp className="w-3 h-3 text-base-content/30" /> : <FaChevronDown className="w-3 h-3 text-base-content/30" />}
                  </button>
                  {showRecentEvents && (
                    <div className="p-4 bg-base-200/20 max-h-48 overflow-y-auto">
                      {recentEvents.length === 0 ? (
                        <p className="text-xs text-base-content/40 text-center py-2">{t('teach_mode.recent_events_empty')}</p>
                      ) : (
                        <div className="space-y-1.5">
                          {recentEvents.map((evt, i) => (
                            <button
                              key={`${evt.entityId}-${evt.timestamp}-${i}`}
                              className="w-full flex items-center gap-2 text-xs bg-base-100 rounded-lg px-3 py-2 border border-base-200 hover:border-primary/30 hover:bg-primary/5 transition-colors text-left"
                              onClick={() => handleRecentEventSelect(evt.entityId, evt.state)}
                            >
                              <span className={clsx(
                                'badge badge-xs font-bold uppercase border-0',
                                evt.type === 'input' ? 'bg-info/20 text-info' : 'bg-warning/20 text-warning-content',
                              )}>
                                {evt.state}
                              </span>
                              <span className="font-medium truncate flex-1">{evt.name}</span>
                              {evt.area && <span className="badge badge-xs badge-ghost text-xxs">{evt.area}</span>}
                              {ignoredIds.has(evt.entityId) && <FaBan className="w-3 h-3 text-error/40 shrink-0" />}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : detectedInput ? (
              /* Collapsed state with detected input summary + click type selector */
              <div className="p-4 space-y-3 bg-primary/5 border-b border-primary/10">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-success/15 rounded-lg text-success shrink-0">
                    <FaCheck className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-sm truncate text-base-content">{detectedInput.state.name}</p>
                    <p className="text-xxs font-mono text-base-content/40 truncate">{detectedInput.entity_id}</p>
                  </div>
                  <button
                    className="btn btn-ghost btn-xs btn-circle text-base-content/40 hover:text-base-content/80 shrink-0"
                    onClick={() => { setDetectedInput(null); setSaveStatus('idle'); setLeftCollapsed(false); }}
                  >
                    <FaUndo className="w-3 h-3" />
                  </button>
                </div>
                {/* Click type selector — always visible so user can change it */}
                <div className="flex flex-wrap gap-1 justify-center">
                  {clickTypes.map((ct) => (
                    <button
                      key={ct}
                      type="button"
                      onClick={() => setClickType(ct)}
                      className={clsx(
                        'btn btn-xs transition-all duration-200 font-medium px-2',
                        clickType === ct ? 'btn-primary shadow-sm shadow-primary/20 scale-[1.03]' : 'btn-ghost border border-base-300',
                      )}
                    >
                      {t(`quick_action.click_types.${ct}`)}
                    </button>
                  ))}
                </div>
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
                {editing ? (
                  <><FaPencilAlt className="w-3.5 h-3.5" />{t('teach_mode.tab_edit')}</>
                ) : (
                  <><FaBolt className="w-3.5 h-3.5" />{t('teach_mode.tab_link')}</>
                )}
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
              <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-2xl mx-auto w-full">
                {/* Edit mode banner */}
                {editing && (
                  <div className="flex items-center gap-3 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3">
                    <FaPencilAlt className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span className="text-xs font-semibold text-base-content/75 flex-1">
                      {t('teach_mode.editing_binding', {
                        clickType: t(`quick_action.click_types.${editing.clickType}`),
                      })}
                    </span>
                    <button className="btn btn-ghost btn-xs" onClick={handleCancelEdit}>
                      {t('common.cancel')}
                    </button>
                  </div>
                )}

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
                          'btn btn-sm flex-1 gap-1.5 font-medium transition-all duration-200',
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
                    preferredArea={detectedInput?.state.area || undefined}
                    nested
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
                          {t(`quick_action.actions.${opt}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Test + Link buttons */}
                <div className="flex gap-2">
                  <button
                    className={clsx(
                      'btn gap-2 h-11 font-semibold transition-all duration-200 active:scale-[0.98] shrink-0',
                      testStatus === 'success' ? 'btn-success' :
                        testStatus === 'error' ? 'btn-error' :
                          'btn-info btn-outline',
                    )}
                    disabled={!canTest}
                    onClick={handleTestAction}
                    title={t('teach_mode.test_action')}
                  >
                    {testStatus === 'loading' ? (
                      <span className="loading loading-spinner loading-sm" />
                    ) : testStatus === 'success' ? (
                      <FaCheck className="w-4 h-4" />
                    ) : (
                      <FaPlay className="w-4 h-4" />
                    )}
                    {t('teach_mode.test_action')}
                  </button>
                  <button
                    className="btn btn-primary flex-1 gap-2 h-11 text-base font-semibold shadow-lg shadow-primary/20 transition-all duration-200 active:scale-[0.98]"
                    disabled={!canLink}
                    onClick={handleLink}
                  >
                    {saveStatus === 'saving' ? (
                      <span className="loading loading-spinner loading-sm" />
                    ) : editing ? (
                      <>
                        <FaSave className="w-4 h-4" />
                        {t('teach_mode.save_binding')}
                      </>
                    ) : (
                      <>
                        <FaLink className="w-4 h-4" />
                        {t('teach_mode.link')}
                      </>
                    )}
                  </button>
                </div>

                {/* Test error */}
                {testStatus === 'error' && testError && (
                  <div className="alert alert-error text-sm py-2 rounded-xl border border-error/10 shadow-sm">
                    <FaExclamationTriangle className="w-3.5 h-3.5" />
                    <span className="text-xs">{testError}</span>
                  </div>
                )}

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
                    <p className="text-xs font-semibold text-base-content/50 uppercase tracking-wider mb-2 flex items-center gap-2">
                      <span className="flex-1">{t('teach_mode.bindings_for', { name: detectedInput.state.name })}</span>
                      <button
                        className="btn btn-ghost btn-xs gap-1 text-primary normal-case font-semibold"
                        onClick={handleGoToSettings}
                        title={t('teach_mode.edit_in_settings')}
                      >
                        <FaExternalLinkAlt className="w-2.5 h-2.5" />
                        {t('teach_mode.edit_in_settings')}
                      </button>
                    </p>
                    <div className="space-y-2">
                      {bindings.map((b) => {
                        const key = `${b.clickType}:${b.index}`;
                        const isEditing = editing?.clickType === b.clickType && editing?.index === b.index;
                        const confirmDelete = deleteCandidate === key;
                        return (
                          <div
                            key={key}
                            className={clsx(
                              'flex items-center gap-3 bg-base-100 border shadow-sm rounded-xl px-4 py-3 text-sm transition-colors',
                              isEditing ? 'border-primary/50 ring-1 ring-primary/20' : 'border-base-200 hover:border-base-300',
                            )}
                          >
                            <span className="badge badge-sm font-bold text-xxs bg-primary/10 text-primary border-0 px-2 py-1 uppercase">{t(`quick_action.click_types.${b.clickType}`, { defaultValue: b.clickType })}</span>
                            <span className="text-base-content/30 font-medium">→</span>
                            <span className="badge badge-sm font-semibold text-xxs bg-base-200 text-base-content/65 border-0 px-2 py-1 uppercase">{t(`quick_action.${b.actionType}`, { defaultValue: b.actionType })}</span>
                            <span className="font-bold text-base-content/80 truncate flex-1 font-mono text-xs">{b.target}</span>
                            <span className="badge badge-sm font-bold text-xxs badge-outline border-base-300 text-base-content/70 px-2 py-1 uppercase">{t(`quick_action.actions.${b.action}`, { defaultValue: b.action })}</span>
                            {Boolean(b.raw.condition || b.raw.conditions) && (
                              <span
                                className="badge badge-sm font-semibold text-xxs bg-warning/10 text-warning border-0 px-2 py-1 gap-1"
                                title={t('teach_mode.has_conditions')}
                              >
                                <FaClock className="w-2.5 h-2.5" />
                                {t('teach_mode.has_conditions_short')}
                              </span>
                            )}

                            {confirmDelete ? (
                              <div className="flex items-center gap-1 shrink-0">
                                <button
                                  className="btn btn-error btn-xs font-semibold"
                                  onClick={() => handleDeleteBinding(b)}
                                >
                                  {t('teach_mode.confirm_delete')}
                                </button>
                                <button
                                  className="btn btn-ghost btn-xs"
                                  onClick={() => setDeleteCandidate(null)}
                                >
                                  {t('common.cancel')}
                                </button>
                              </div>
                            ) : (
                              <div className="flex items-center gap-0.5 shrink-0">
                                <button
                                  className="btn btn-ghost btn-xs btn-circle text-base-content/40 hover:text-primary"
                                  onClick={() => handleStartEdit(b)}
                                  title={t('teach_mode.edit_binding')}
                                >
                                  <FaPencilAlt className="w-3 h-3" />
                                </button>
                                <button
                                  className="btn btn-ghost btn-xs btn-circle text-base-content/40 hover:text-error"
                                  onClick={() => setDeleteCandidate(key)}
                                  title={t('teach_mode.delete_binding')}
                                >
                                  <FaTrash className="w-3 h-3" />
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })}
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
                      <span className="bg-base-200 text-base-content/60 px-1.5 py-0.5 rounded">{t(`quick_action.click_types.${entry.clickType}`)}</span>
                      <span className="bg-base-200 text-base-content/60 px-1.5 py-0.5 rounded">{t(`quick_action.actions.${entry.action}`)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default TeachMode;
