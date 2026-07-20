import React, { useState, useContext, useMemo, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useTranslation } from '@/hooks/useTranslation';
import { WebSocketContext } from '@/App';
import type { InputEvent, OutputEvent, CoverEvent } from '@/hooks/useWebSocket';
import type { EntityItem } from '@/components/UISettings/EntitySelectDropdown';
import SearchableEntityPicker from '@/components/UISettings/SearchableEntityPicker';
import axios from '@/api/axios';
import { FaPlug, FaCheck, FaExclamationTriangle } from 'react-icons/fa';

type SaveStatus = 'idle' | 'saving' | 'success' | 'error';

/**
 * Extended EntityItem that tracks whether this is a local or remote entity
 * and optionally stores the remote_device id for remote entities.
 */
interface QuickEntityItem extends EntityItem {
  /** The action_type to use for this entity */
  actionType: 'output' | 'cover' | 'remote_output' | 'remote_cover';
  /** Remote device id (only for remote_output / remote_cover) */
  remoteDevice?: string;
}

interface QuickActionSheetProps {
  /** Whether the sheet is open */
  open: boolean;
  /** Called when the sheet should close */
  onOpenChange: (open: boolean) => void;
  /** The input event to configure */
  inputEvent: InputEvent | null;
}

/** Output action options for the action dropdown. */
const OUTPUT_ACTIONS = ['TOGGLE', 'ON', 'OFF'] as const;
/** Cover action options for the action dropdown. */
const COVER_ACTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP'] as const;

/** Click types available for event-type inputs. */
const EVENT_CLICK_TYPES = [
  'single', 'double', 'triple', 'long',
  'double_then_long', 'single_then_long', 'double_then_single',
] as const;

/** Click types available for binary_sensor-type inputs. */
const BINARY_SENSOR_CLICK_TYPES = ['pressed', 'released'] as const;

/**
 * Quick Action Sheet — a simplified dialog for adding an action to an input.
 * Opens from InputsView when user presses ⚡. Lets user pick:
 * 1. Click type (single/double/long)
 * 2. Target type (output or cover — includes both local and remote)
 * 3. Target entity (via SearchableEntityPicker)
 * 4. Action (Toggle/On/Off)
 * Then saves via POST /api/config/quick-action.
 */
const QuickActionSheet: React.FC<QuickActionSheetProps> = ({
  open,
  onOpenChange,
  inputEvent,
}) => {
  const { t } = useTranslation();
  const { outputs, covers } = useContext(WebSocketContext);

  // Form state
  const [clickType, setClickType] = useState('single');
  const [targetMode, setTargetMode] = useState<'output' | 'cover'>('output');
  const [targetId, setTargetId] = useState('');
  const [actionValue, setActionValue] = useState('TOGGLE');
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  // Reset form when input changes
  React.useEffect(() => {
    if (open && inputEvent) {
      const isEvent = inputEvent.state.type === 'input';
      setClickType(isEvent ? 'single' : 'pressed');
      setTargetMode('output');
      setTargetId('');
      setActionValue('TOGGLE');
      setSaveStatus('idle');
      setErrorMessage('');
    }
  }, [open, inputEvent]);

  const isEvent = inputEvent?.state.type === 'input';
  const clickTypes = isEvent ? EVENT_CLICK_TYPES : BINARY_SENSOR_CLICK_TYPES;
  const actionOptions = targetMode === 'cover' ? COVER_ACTIONS : OUTPUT_ACTIONS;

  /**
   * Build unified output items list (local + remote).
   * Each item carries its actionType and optional remoteDevice for the API call.
   */
  const outputItems: QuickEntityItem[] = useMemo(() => {
    const items: QuickEntityItem[] = [];

    // Local outputs
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

    // Remote outputs
    outputs
      .filter((o: OutputEvent) => o.state.remote)
      .forEach((o: OutputEvent) => {
        // entity_id for remote outputs is like "remote_device_id/output_id"
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

  /**
   * Build unified cover items list (local + remote).
   */
  const coverItems: QuickEntityItem[] = useMemo(() => {
    const items: QuickEntityItem[] = [];

    // Local covers
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

    // Remote covers
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

  /** Find the selected item to extract its actionType and remoteDevice. */
  const selectedItem = useMemo(
    () => currentItems.find((item) => item.id === targetId),
    [currentItems, targetId]
  );

  /** Handle save. */
  const handleSave = useCallback(async () => {
    if (!inputEvent || !targetId || !selectedItem) return;

    setSaveStatus('saving');
    setErrorMessage('');

    try {
      const payload: Record<string, string> = {
        entity_id: inputEvent.entity_id,
        click_type: clickType,
        action_type: selectedItem.actionType,
        action: actionValue,
      };

      // Set the right IDs based on action type
      switch (selectedItem.actionType) {
        case 'output':
          payload.output_id = targetId;
          break;
        case 'cover':
          payload.cover_id = targetId;
          break;
        case 'remote_output': {
          payload.remote_device = selectedItem.remoteDevice || '';
          // Extract output_id from entity_id (remove device prefix)
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

      // Auto-close after success
      setTimeout(() => {
        onOpenChange(false);
      }, 1200);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string | { message?: string } } } };
      if (axiosErr.response?.status === 409) {
        // Duplicate action — show warning, not error
        setSaveStatus('error');
        setErrorMessage(t('quick_action.duplicate_action'));
      } else {
        setSaveStatus('error');
        const detail = axiosErr.response?.data?.detail;
        setErrorMessage(
          typeof detail === 'string' ? detail
            : (detail as { message?: string })?.message || t('quick_action.save_error')
        );
      }
    }
  }, [inputEvent, targetId, selectedItem, clickType, actionValue, onOpenChange, t]);

  const canSave = targetId && saveStatus !== 'saving' && saveStatus !== 'success';

  if (!inputEvent) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="bg-base-100 p-0 gap-0 max-h-[90vh] overflow-y-auto sm:max-w-md"
      >
        <DialogHeader className="px-5 pt-4 pb-0 sm:pt-5">
          <DialogTitle className="flex items-center gap-2">
            <FaPlug className="w-4 h-4 text-primary" />
            {t('quick_action.title')}
          </DialogTitle>
          <p className="text-sm text-base-content/60 mt-1">
            {inputEvent.state.name}
            <span className="text-xs opacity-50 ml-2">({inputEvent.entity_id})</span>
          </p>
        </DialogHeader>

        <div className="px-5 py-4 space-y-4">
          {/* Click type selector */}
          <div className="form-control">
            <label className="label pb-1">
              <span className="label-text font-medium text-sm">{t('quick_action.click_type')}</span>
            </label>
            <div className="flex flex-wrap gap-2">
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

          {/* Target mode toggle (output vs cover) */}
          <div className="form-control">
            <label className="label pb-1">
              <span className="label-text font-medium text-sm">{t('quick_action.target_type')}</span>
            </label>
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
          </div>

          {/* Target entity picker */}
          <div className="form-control">
            <label className="label pb-1">
              <span className="label-text font-medium text-sm">
                {targetMode === 'cover' ? t('quick_action.select_cover') : t('quick_action.select_output')}
              </span>
            </label>
            <SearchableEntityPicker
              value={targetId}
              onChange={setTargetId}
              items={currentItems}
              placeholder={targetMode === 'cover' ? t('quick_action.select_cover') : t('quick_action.select_output')}
              recentKey={targetMode === 'cover' ? 'covers' : 'outputs'}
              preferredArea={inputEvent?.state.area || undefined}
              nested
            />
          </div>

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
                    {t(`quick_action.actions.${opt}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

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

        <DialogFooter className="px-5 pb-5 gap-2">
          <button
            className="btn btn-ghost"
            onClick={() => onOpenChange(false)}
          >
            {t('common.cancel')}
          </button>
          <button
            className="btn btn-primary"
            disabled={!canSave}
            onClick={handleSave}
          >
            {saveStatus === 'saving' ? (
              <span className="loading loading-spinner loading-sm" />
            ) : (
              t('quick_action.save')
            )}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default QuickActionSheet;
