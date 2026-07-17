/**
 * InputTypeSwitcher - Toggle between binary_sensor and event mode for local_inputs.
 * Shows a segmented control at the top of the form. When switching modes,
 * it transforms the data (actions, fields) and warns about data loss.
 */
import React, { useState } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

interface InputTypeSwitcherProps {
  /** Current _type value: 'binary_sensor' or 'event' */
  currentType: 'binary_sensor' | 'event';
  /** Current form data */
  data: any;
  /** Callback when type is switched — receives transformed data */
  onSwitch: (newData: any) => void;
}

/** Fields that are specific to binary_sensor and should be removed when switching to event. */
const BS_ONLY_FIELDS = ['device_class', 'show_in_ha', 'inverted', 'initial_send', 'clear_message'];

/** Fields that are specific to event and should be removed when switching to binary_sensor. */
const EVENT_ONLY_FIELDS = [
  'double_click_duration', 'long_press_duration', 'sequence_window_duration',
  'sequence_mode', 'enable_triple_click', 'long_press_mqtt_mode',
  'max_long_press_duration', 'mqtt_sequences',
];

/** Event action types that get lost when switching to binary_sensor. */
const EVENT_ACTION_TYPES = ['single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'];

/** Binary sensor action types that get lost when switching to event. */
const BS_ACTION_TYPES = ['pressed', 'released'];

/**
 * Count total actions across given action types.
 */
function countActions(actions: any, types: string[]): number {
  if (!actions || typeof actions !== 'object') return 0;
  return types.reduce((sum, type) => {
    const arr = actions[type];
    return sum + (Array.isArray(arr) ? arr.length : 0);
  }, 0);
}

/**
 * Transform data when switching from event → binary_sensor.
 * Maps single → pressed actions as a best-effort migration.
 */
function eventToBinarySensor(data: any): any {
  const { _type, ...rest } = data;
  const newData: any = { ...rest, _type: 'binary_sensor' };

  // Best-effort action migration: single → pressed
  const oldActions = data.actions || {};
  const newActions: any = {};

  if (oldActions.single?.length > 0) {
    newActions.pressed = [...oldActions.single];
  }
  // No good mapping for double/triple/long/sequences → released, so we skip them

  newData.actions = newActions;

  // Remove event-only fields
  EVENT_ONLY_FIELDS.forEach(field => delete newData[field]);

  return newData;
}

/**
 * Transform data when switching from binary_sensor → event.
 * Maps pressed → single actions as a best-effort migration.
 */
function binarySensorToEvent(data: any): any {
  const { _type, ...rest } = data;
  const newData: any = { ...rest, _type: 'event' };

  // Best-effort action migration: pressed → single
  const oldActions = data.actions || {};
  const newActions: any = {};

  if (oldActions.pressed?.length > 0) {
    newActions.single = [...oldActions.pressed];
  }
  // released has no equivalent in event, so we drop it

  newData.actions = newActions;

  // Remove binary_sensor-only fields
  BS_ONLY_FIELDS.forEach(field => delete newData[field]);

  return newData;
}

/**
 * Segmented control for switching input type with data transformation and loss warnings.
 */
const InputTypeSwitcher: React.FC<InputTypeSwitcherProps> = ({ currentType, data, onSwitch }) => {
  const { t } = useTranslation();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingType, setPendingType] = useState<'binary_sensor' | 'event' | null>(null);
  const [lostActionCount, setLostActionCount] = useState(0);

  const handleTypeChange = (newType: 'binary_sensor' | 'event') => {
    if (newType === currentType) return;

    // Check if switching would lose actions
    const losingTypes = newType === 'binary_sensor' ? EVENT_ACTION_TYPES : BS_ACTION_TYPES;
    const lostCount = countActions(data.actions, losingTypes);

    if (lostCount > 0) {
      setPendingType(newType);
      setLostActionCount(lostCount);
      setConfirmOpen(true);
    } else {
      applySwitch(newType);
    }
  };

  const applySwitch = (newType: 'binary_sensor' | 'event') => {
    const transformed = newType === 'binary_sensor'
      ? eventToBinarySensor(data)
      : binarySensorToEvent(data);
    onSwitch(transformed);
  };

  const confirmSwitch = () => {
    if (pendingType) {
      applySwitch(pendingType);
    }
    setConfirmOpen(false);
    setPendingType(null);
    setLostActionCount(0);
  };

  const cancelSwitch = () => {
    setConfirmOpen(false);
    setPendingType(null);
    setLostActionCount(0);
  };

  return (
    <>
      {/* Segmented control */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-base-200 rounded-[var(--radius-field)]">
        <span className="text-sm font-medium text-base-content/70 shrink-0">{t('common.type')}:</span>
        <div className="join">
          <button
            type="button"
            className={`join-item btn btn-sm ${currentType === 'event' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => handleTypeChange('event')}
          >
            ⚡ {t('sections.event')}
          </button>
          <button
            type="button"
            className={`join-item btn btn-sm ${currentType === 'binary_sensor' ? 'btn-warning' : 'btn-ghost'}`}
            onClick={() => handleTypeChange('binary_sensor')}
          >
            🔘 {t('sections.binary_sensor')}
          </button>
        </div>
        <span className="text-xs text-base-content/50 basis-full sm:basis-auto">
          {currentType === 'event'
            ? t('inputs.type_event_hint')
            : t('inputs.type_binary_sensor_hint')}
        </span>
      </div>

      {/* Confirmation dialog for data loss */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-md bg-base-100">
          <DialogHeader>
            <DialogTitle className="text-warning flex items-center gap-2">
              ⚠️ {t('inputs.switch_type_warning_title')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-3">
            <p>{t('inputs.switch_type_warning_message')}</p>
            <div className="bg-base-200 rounded-lg p-3">
              <p className="text-sm">
                <span className="font-medium">{t('inputs.actions_to_lose')}: </span>
                <span className="badge badge-warning badge-sm">{lostActionCount}</span>
              </p>
              {pendingType === 'binary_sensor' && (
                <p className="text-xs text-base-content/60 mt-2">
                  {t('inputs.switch_to_bs_hint')}
                </p>
              )}
              {pendingType === 'event' && (
                <p className="text-xs text-base-content/60 mt-2">
                  {t('inputs.switch_to_event_hint')}
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <button type="button" onClick={cancelSwitch} className="btn btn-ghost">
              {t('common.cancel')}
            </button>
            <button type="button" onClick={confirmSwitch} className="btn btn-warning">
              {t('inputs.switch_type_confirm')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default InputTypeSwitcher;
