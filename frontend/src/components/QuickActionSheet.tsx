import React, { useState, useCallback, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { useTranslation } from '@/hooks/useTranslation';
import type { InputEvent } from '@/hooks/useWebSocket';
import { useActionEditorData } from '@/hooks/useActionEditorData';
import InputActionEditor from '@/components/InputActionEditor';
import { validateAction } from '@/components/UISettings/ActionFields';
import { actionIsIncomplete, type ActionEntry } from '@/components/UISettings/helpers/actionSummary';
import { invalidateConfigCache } from '@/api/configCache';
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

/** Click types available for event-type inputs. */
const EVENT_CLICK_TYPES = [
  'single', 'double', 'triple', 'long',
  'double_then_long', 'single_then_long', 'double_then_single',
] as const;

/** Click types available for binary_sensor-type inputs. */
const BINARY_SENSOR_CLICK_TYPES = ['pressed', 'released'] as const;

/** What a new action starts as: the commonest thing a button does. */
const newAction = (): ActionEntry => ({ action: 'output', action_output: 'TOGGLE' });

/**
 * Quick Action Sheet — add one action to an input without leaving the Inputs
 * view. Opens from InputsView when an admin long-presses an input.
 *
 * The action itself is edited with the same fields as Settings → Inputs, so
 * everything that editor can set can be set here, then saved on its own via
 * POST /api/config/quick-action without a full section save.
 */
const QuickActionSheet: React.FC<QuickActionSheetProps> = ({
  open,
  onOpenChange,
  inputEvent,
}) => {
  const { t } = useTranslation();
  const { data: editorData, loading } = useActionEditorData(open);

  const [clickType, setClickType] = useState('single');
  const [action, setAction] = useState<ActionEntry>(newAction);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [attempted, setAttempted] = useState(false);

  // Reset the form each time the dialog opens
  useEffect(() => {
    if (open && inputEvent) {
      setClickType(inputEvent.state.type === 'input' ? 'single' : 'pressed');
      setAction(newAction());
      setSaveStatus('idle');
      setErrorMessage('');
      setAttempted(false);
    }
  }, [open, inputEvent]);

  const isEvent = inputEvent?.state.type === 'input';
  const clickTypes = isEvent ? EVENT_CLICK_TYPES : BINARY_SENSOR_CLICK_TYPES;
  const validationError = validateAction(action, t);

  const handleSave = useCallback(async () => {
    if (!inputEvent) return;
    setAttempted(true);
    if (validationError) return;

    setSaveStatus('saving');
    setErrorMessage('');

    try {
      await axios.post('/api/config/quick-action', {
        entity_id: inputEvent.entity_id,
        click_type: clickType,
        action_def: action,
      }, { timeout: 15_000 });
      // Settings reads the cached config; without this it would show the
      // input without the action just added.
      invalidateConfigCache();
      setSaveStatus('success');

      // Auto-close after success
      setTimeout(() => {
        onOpenChange(false);
      }, 1200);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string | { message?: string; errors?: string[] } } } };
      setSaveStatus('error');
      if (axiosErr.response?.status === 409) {
        setErrorMessage(t('quick_action.duplicate_action'));
      } else {
        const detail = axiosErr.response?.data?.detail;
        setErrorMessage(
          typeof detail === 'string' ? detail
            : detail?.errors?.join(' ') || detail?.message || t('quick_action.save_error')
        );
      }
    }
  }, [inputEvent, clickType, action, validationError, onOpenChange, t]);

  const canSave = !actionIsIncomplete(action) && saveStatus !== 'saving' && saveStatus !== 'success';

  if (!inputEvent) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="bg-base-100 p-0 gap-0 max-h-[90vh] overflow-y-auto sm:max-w-lg"
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

          {/* The action — same editor as Settings → Inputs */}
          {loading ? (
            <div className="flex justify-center py-8">
              <span className="loading loading-spinner loading-md text-primary" />
            </div>
          ) : (
            <InputActionEditor
              action={action}
              onChange={setAction}
              clickType={clickType}
              data={editorData}
              title={t('quick_action.action')}
              showValidation={attempted}
              excludeEntityId={inputEvent.entity_id}
              preferredArea={inputEvent.state.area || undefined}
            />
          )}

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
