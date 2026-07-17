import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import FormRenderer from './FormRenderer';

/**
 * Props for the reusable edit-item dialog.
 *
 * This dialog wraps FormRenderer with a standard Dialog shell so that both
 * ArrayTableWidget and BindingMatrix (and future consumers) render the exact
 * same editing experience without duplicating the Dialog + FormRenderer wiring.
 */
export interface EditItemDialogProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Called when the dialog should close. */
  onOpenChange: (open: boolean) => void;
  /** The item being edited (deep-cloned snapshot). */
  editingItem: any;
  /** Index of the item in the section array (null = new item). */
  editingIndex: number | null;
  /** Section type key for FormRenderer routing. */
  sectionType: string;
  /** JSON schema for the section. */
  schema: any;
  /** Optional UI schema overrides. */
  uiSchema?: any;
  /** Device type (for output forms). */
  deviceType?: string;
  /** All binary sensors for EventForm cross-references. */
  allBinarySensors?: any[];
  /** All events for EventForm cross-references. */
  allEvents?: any[];
  /** All outputs for form dropdowns. */
  allOutputs?: any[];
  /** All output groups for form dropdowns. */
  allOutputGroups?: any[];
  /** All covers for form dropdowns. */
  allCovers?: any[];
  /** All areas for area select. */
  allAreas?: any[];
  /** All sensors. */
  allSensors?: any[];
  /** All modbus devices. */
  allModbusDevices?: any[];
  /** All remote devices. */
  allRemoteDevices?: any[];
  /** All remote inputs. */
  allRemoteInputs?: any[];
  /** Saved (committed) outputs for comparison. */
  savedOutputs?: any[];
  /** Saved (committed) output groups. */
  savedOutputGroups?: any[];
  /** Saved (committed) covers. */
  savedCovers?: any[];
  /** Full section value array. */
  value?: any[];
  /** Interlock groups list. */
  interlockGroups?: string[];
  /** Available Dallas sensors. */
  availableDallasSensors?: { address: string; type: string }[];
  /** Called when editingItem changes. */
  onChange: (item: any) => void;
  /** Called when user clicks Save. */
  onSave: () => void;
  /** Called when user clicks Cancel. */
  onCancel: () => void;
  /** Called when validation state changes. */
  onValidationChange?: (hasErrors: boolean) => void;
  /** Called when a new interlock group is created. */
  onInterlockGroupCreated?: (group: string) => void;
  /** Whether the form was submitted (for showing validation errors). */
  attemptedSubmit?: boolean;
  /** Whether the save button should be disabled (externally). */
  saveDisabled?: boolean;
  /** Whether a save is in progress. */
  isSaving?: boolean;
  /** Optional initial tab for EventForm. */
  initialTab?: string;
}

/**
 * EditItemDialog — reusable dialog that wraps FormRenderer.
 *
 * Extracted from ArrayTableWidget so that both the table views and the
 * BindingMatrix share the exact same editing dialog without code duplication.
 */
const EditItemDialog: React.FC<EditItemDialogProps> = ({
  open,
  onOpenChange,
  editingItem,
  editingIndex,
  sectionType,
  schema,
  uiSchema,
  deviceType,
  allBinarySensors = [],
  allEvents = [],
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allSensors = [],
  allModbusDevices = [],
  allRemoteDevices = [],
  allRemoteInputs = [],
  savedOutputs,
  savedOutputGroups,
  savedCovers,
  value,
  interlockGroups = [],
  availableDallasSensors = [],
  onChange,
  onSave,
  onCancel,
  onValidationChange,
  onInterlockGroupCreated,
  attemptedSubmit = false,
  saveDisabled = false,
  isSaving = false,
  initialTab,
}) => {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl lg:max-w-4xl flex flex-col gap-0 bg-base-100">
        <DialogHeader className="pb-4">
          <DialogTitle>
            {editingIndex !== null ? (
              <>
                {t('settings.edit_item')}
                {editingItem && (editingItem.id || editingItem.name || editingItem.boneio_output || editingItem.boneio_input) && (
                  <span className="font-normal text-base-content/70">
                    {' - '}
                    {editingItem.id || editingItem.name || ''}
                    {(editingItem.id || editingItem.name) && (editingItem.boneio_output || editingItem.boneio_input) && ' '}
                    {editingItem.boneio_output && <span className="text-sm">({editingItem.boneio_output})</span>}
                    {editingItem.boneio_input && <span className="text-sm">({editingItem.boneio_input})</span>}
                  </span>
                )}
              </>
            ) : t('settings.add_new_item')}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {editingIndex !== null ? t('settings.edit_item') : t('settings.add_new_item')}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!saveDisabled && !isSaving) {
              onSave();
            }
          }}
          className="flex flex-col flex-1 min-h-0"
        >
          <div className="flex-1 overflow-y-auto overflow-x-hidden -mx-6 px-6 wrap-break-words [&_.label-text]:whitespace-normal [&_.label-text]:wrap-break-words [&_.label-text-alt]:whitespace-normal [&_.label-text-alt]:wrap-break-words [&_.form-control]:min-w-0">
            {editingItem && (
              <FormRenderer
                sectionType={sectionType}
                editingItem={editingItem}
                editingIndex={editingIndex}
                schema={schema}
                uiSchema={uiSchema}
                deviceType={deviceType}
                allBinarySensors={allBinarySensors}
                allEvents={allEvents}
                allOutputs={allOutputs}
                allOutputGroups={allOutputGroups}
                allCovers={allCovers}
                allAreas={allAreas}
                allSensors={allSensors}
                allModbusDevices={allModbusDevices}
                allRemoteDevices={allRemoteDevices}
                allRemoteInputs={allRemoteInputs}
                savedOutputs={savedOutputs}
                savedOutputGroups={savedOutputGroups}
                savedCovers={savedCovers}
                value={value || []}
                interlockGroups={interlockGroups}
                availableDallasSensors={availableDallasSensors}
                onChange={onChange}
                onSave={onSave}
                onCancel={onCancel}
                onValidationChange={onValidationChange || (() => { })}
                onInterlockGroupCreated={onInterlockGroupCreated || (() => { })}
                attemptedSubmit={attemptedSubmit}
                initialTab={initialTab}
              />
            )}
          </div>

          <DialogFooter className="shrink-0 mt-2">
            <button type="button" onClick={onCancel} className="btn btn-ghost">
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={saveDisabled || isSaving}
              title={saveDisabled ? t('settings.fix_validation_errors') : ''}
            >
              {isSaving ? (
                <><span className="loading loading-spinner loading-xs" /> {t('settings.saving')}</>
              ) : (
                editingIndex !== null ? t('settings.save_changes') : t('settings.add_item')
              )}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default EditItemDialog;
