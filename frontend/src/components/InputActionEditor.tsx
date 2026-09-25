import React, { useCallback } from 'react';
import ActionFields, { cleanActionFields } from '@/components/UISettings/ActionFields';
import { applyActionUpdate } from '@/components/UISettings/ActionFields/helpers';
import type { ActionEntry } from '@/components/UISettings/helpers/actionSummary';
import {
  ACTION_COVER_OPTIONS,
  ACTION_OUTPUT_OPTIONS,
  INPUT_ACTION_TYPES,
  type ActionEditorData,
} from '@/hooks/useActionEditorData';

type ClickType = React.ComponentProps<typeof ActionFields>['clickType'];

interface InputActionEditorProps {
  /** The action being edited. */
  action: ActionEntry;
  /** Called with the whole new action. */
  onChange: (action: ActionEntry) => void;
  /** Click type it will be stored under — decides which timing options show. */
  clickType: string;
  /** Entity lists from useActionEditorData. */
  data: ActionEditorData;
  /** Header text for the card. */
  title?: string;
  /** Show the validation message (after a save attempt). */
  showValidation?: boolean;
  /** Input being configured, kept out of its own condition pickers. */
  excludeEntityId?: string;
  /** Area of the input, so its own area's entities come first. */
  preferredArea?: string;
}

/**
 * One input action, edited with the same fields as Settings → Inputs.
 *
 * Teach Mode and the quick action render this instead of their own target and
 * command pickers, so anything the input editor can set — every action type,
 * brightness, tilt, presets, conditions, delay, repeat, press thresholds — can
 * be set from them too, and a new option added to the editor reaches both.
 */
const InputActionEditor: React.FC<InputActionEditorProps> = ({
  action,
  onChange,
  clickType,
  data,
  title,
  showValidation = false,
  excludeEntityId,
  preferredArea,
}) => {
  // Same rules as the input editor's updateAction: switching the type drops
  // the old type's fields, and choosing another remote device or output
  // clears what only made sense for the previous one.
  const handleUpdate = useCallback((field: string, value: unknown) => {
    if (field === 'action') {
      onChange(cleanActionFields(String(value), action) as ActionEntry);
    } else if (field === 'remote_device') {
      onChange(applyActionUpdate(action, '__batch', {
        remote_device: value, output_id: undefined, cover_id: undefined, presets: undefined, colors: undefined,
      }));
    } else if (field === 'output_id') {
      onChange(applyActionUpdate(action, '__batch', { output_id: value, presets: undefined, colors: undefined }));
    } else {
      onChange(applyActionUpdate(action, field, value));
    }
  }, [action, onChange]);

  return (
    <ActionFields
      action={action}
      index={0}
      title={title}
      onUpdate={handleUpdate}
      allOutputs={data.allOutputs}
      allOutputGroups={data.allOutputGroups}
      allCovers={data.allCovers}
      allAreas={data.allAreas}
      allRemoteDevices={data.allRemoteDevices}
      actionTypeOptions={INPUT_ACTION_TYPES}
      actionOutputOptions={ACTION_OUTPUT_OPTIONS}
      actionCoverOptions={ACTION_COVER_OPTIONS}
      showValidation={showValidation}
      clickType={clickType as ClickType}
      allBinarySensors={data.allBinarySensors}
      allRemoteInputs={data.allRemoteInputs}
      allVirtualSwitches={data.allVirtualSwitches}
      excludeEntityId={excludeEntityId}
      preferredArea={preferredArea}
    />
  );
};

export default InputActionEditor;
