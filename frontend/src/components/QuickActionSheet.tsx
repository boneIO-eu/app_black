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
 * 2. Target output or cover (via SearchableEntityPicker)
 * 3. Action (Toggle/On/Off)
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
  const [actionType, setActionType] = useState<'output' | 'cover'>('output');
  const [targetId, setTargetId] = useState('');
  const [actionValue, setActionValue] = useState('TOGGLE');
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  // Reset form when input changes
  React.useEffect(() => {
    if (open && inputEvent) {
      const isEvent = inputEvent.state.type === 'input';
      setClickType(isEvent ? 'single' : 'pressed');
      setActionType('output');
      setTargetId('');
      setActionValue('TOGGLE');
      setSaveStatus('idle');
      setErrorMessage('');
    }
  }, [open, inputEvent]);

  const isEvent = inputEvent?.state.type === 'input';
  const clickTypes = isEvent ? EVENT_CLICK_TYPES : BINARY_SENSOR_CLICK_TYPES;
  const actionOptions = actionType === 'cover' ? COVER_ACTIONS : OUTPUT_ACTIONS;

  /** Convert outputs to EntityItem[] for SearchableEntityPicker. */
  const outputItems: EntityItem[] = useMemo(() => {
    return outputs
      .filter((o: OutputEvent) => o.state.type?.toLowerCase() !== 'cover')
      .map((o: OutputEvent): EntityItem => ({
        id: o.state.id || o.entity_id,
        name: o.state.name || o.state.id || o.entity_id,
        area: o.state.area || undefined,
        badge: o.state.type || undefined,
        badgeClass: o.state.type === 'light' ? 'badge-warning'
          : o.state.type === 'switch' ? 'badge-info'
          : o.state.type === 'valve' ? 'badge-accent'
          : 'badge-ghost',
      }));
  }, [outputs]);

  /** Convert covers to EntityItem[] for SearchableEntityPicker. */
  const coverItems: EntityItem[] = useMemo(() => {
    return covers.map((c: CoverEvent): EntityItem => ({
      id: c.state.id || c.entity_id,
      name: c.state.name || c.state.id || c.entity_id,
      badge: c.state.kind || 'cover',
      badgeClass: 'badge-accent',
    }));
  }, [covers]);

  const currentItems = actionType === 'cover' ? coverItems : outputItems;

  /** Handle save. */
  const handleSave = useCallback(async () => {
    if (!inputEvent || !targetId) return;

    setSaveStatus('saving');
    setErrorMessage('');

    try {
      const payload: Record<string, string> = {
        entity_id: inputEvent.entity_id,
        click_type: clickType,
        action_type: actionType,
        action: actionValue,
      };

      if (actionType === 'cover') {
        payload.cover_id = targetId;
      } else {
        payload.output_id = targetId;
      }

      await axios.post('/api/config/quick-action', payload);
      setSaveStatus('success');

      // Auto-close after success
      setTimeout(() => {
        onOpenChange(false);
      }, 1200);
    } catch (err: any) {
      setSaveStatus('error');
      const detail = err.response?.data?.detail;
      setErrorMessage(
        typeof detail === 'string' ? detail
          : detail?.message || t('quick_action.save_error')
      );
    }
  }, [inputEvent, targetId, clickType, actionType, actionValue, onOpenChange, t]);

  const canSave = targetId && saveStatus !== 'saving' && saveStatus !== 'success';

  if (!inputEvent) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-base-100 sm:max-w-md p-0 gap-0">
        <DialogHeader className="px-5 pt-5 pb-0">
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

          {/* Action type toggle (output vs cover) */}
          <div className="form-control">
            <label className="label pb-1">
              <span className="label-text font-medium text-sm">{t('quick_action.target_type')}</span>
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setActionType('output'); setTargetId(''); setActionValue('TOGGLE'); }}
                className={`btn btn-sm flex-1 ${actionType === 'output' ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
              >
                {t('quick_action.output')}
              </button>
              {covers.length > 0 && (
                <button
                  type="button"
                  onClick={() => { setActionType('cover'); setTargetId(''); setActionValue('TOGGLE'); }}
                  className={`btn btn-sm flex-1 ${actionType === 'cover' ? 'btn-primary' : 'btn-ghost border border-base-300'}`}
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
                {actionType === 'cover' ? t('quick_action.select_cover') : t('quick_action.select_output')}
              </span>
            </label>
            <SearchableEntityPicker
              value={targetId}
              onChange={setTargetId}
              items={currentItems}
              placeholder={actionType === 'cover' ? t('quick_action.select_cover') : t('quick_action.select_output')}
              recentKey={actionType === 'cover' ? 'covers' : 'outputs'}
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
                    {opt}
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
