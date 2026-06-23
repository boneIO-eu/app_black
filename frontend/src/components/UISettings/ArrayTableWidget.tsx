import React, { useState, useEffect, useRef } from 'react';
import axios from '@/api/axios';
import { copyToClipboard } from '@/utils/clipboard';
import { FaPlus, FaDownload, FaUpload } from 'react-icons/fa';
import { useTranslation } from '../../hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

// Extracted components & hooks
import { useItemActions } from './hooks/useItemActions';
import { useImportExport } from './hooks/useImportExport';
import { validateItem, areAllItemsUsed } from './helpers/itemValidation';
import FormRenderer from './components/FormRenderer';
import TableRenderer from './components/TableRenderer';
import DeleteConfirmDialog from './components/DeleteConfirmDialog';
import ImportDialog from './components/ImportDialog';
import TemplatePicker from './components/TemplatePicker';
import { AddModbusDeviceWizard } from './AddModbusDeviceWizard';
import type { AffectedAction } from './hooks/useItemActions';

interface Area {
  id: string;
  name: string;
}

export interface ArrayTableWidgetProps {
  value: any[];
  onChange: (value: any[]) => void;
  schema: any;
  title?: string;
  uiSchema?: any;
  sectionType?: 'binary_sensor' | 'event' | 'local_inputs' | 'remote_inputs' | 'remote_outputs' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'sensor' | 'virtual_energy_sensor' | 'remote_devices' | 'template' | 'adc' | 'board_sensors' | 'other';
  deviceType?: string;
  allBinarySensors?: any[];
  allEvents?: any[];
  allOutputs?: any[];
  allOutputGroups?: any[];
  allCovers?: any[];
  allAreas?: Area[];
  allSensors?: any[];
  allModbusDevices?: any[];
  allVirtualEnergySensors?: any[];
  allRemoteDevices?: any[];
  allRemoteInputs?: any[];
  /** Saved (committed) data for comparison - items not in saved are shown as disabled */
  savedOutputs?: any[];
  savedOutputGroups?: any[];
  savedCovers?: any[];
  /** Callback to update events when orphaned actions need to be removed */
  onUpdateEvents?: (newEvents: any[]) => void;
  /** Callback to update binary_sensors when orphaned actions need to be removed */
  onUpdateBinarySensors?: (newBinarySensors: any[]) => void;
  /** Callback to save a section after orphaned actions are removed.
   * If data is provided, it will be saved directly instead of using formData.
   */
  onSaveSection?: (sectionName: string, data?: any) => Promise<void>;
  /** Name of item to auto-open for editing (from URL query param) */
  editItemName?: string;
  /** Callback when edit item has been opened (to clear URL query param) */
  onEditItemOpened?: () => void;
}

/** Check if section is an input-type (binary_sensor, event, or merged local_inputs). */
const isInputSection = (s: string) => s === 'binary_sensor' || s === 'event' || s === 'local_inputs';

/**
 * Custom table widget for array sections (e.g. event, binary_sensor) with modal editing.
 * Uses regular table with Edit buttons, @rjsf form only appears in modal.
 * This prevents automatic onChange calls during editing.
 */
const ArrayTableWidget: React.FC<ArrayTableWidgetProps> = ({ value = [], onChange, schema, title, uiSchema, sectionType = 'other', deviceType, allBinarySensors = [], allEvents = [], allOutputs = [], allOutputGroups = [], allCovers = [], allAreas = [], allSensors = [], allModbusDevices = [], allVirtualEnergySensors = [], allRemoteDevices = [], allRemoteInputs = [], savedOutputs, savedOutputGroups, savedCovers, onUpdateEvents, onUpdateBinarySensors, onSaveSection, editItemName, onEditItemOpened }) => {
  const { t } = useTranslation();
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [hasValidationErrors, setHasValidationErrors] = useState(false);
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  const [interlockGroups, setInterlockGroups] = useState<string[]>([]);
  const [availableDallasSensors, setAvailableDallasSensors] = useState<{ address: string, type: string }[]>([]);
  // Snapshot of item when modal opened — used for dirty tracking
  const originalItemRef = useRef<string | null>(null);

  // Delete confirmation state
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);
  const [affectedActions, setAffectedActions] = useState<AffectedAction[]>([]);

  // Template picker & AI wizard
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const editItemProcessedRef = useRef<string | null>(null);
  const [wizardCopied, setWizardCopied] = useState(false);
  const [isModbusWizardOpen, setIsModbusWizardOpen] = useState(false);

  // Extracted hooks
  const { findItemsUsingArea, findAffectedActions, removeOrphanedActions } = useItemActions({
    allEvents, allBinarySensors, allOutputs, allOutputGroups, allCovers,
    allSensors, allModbusDevices, allVirtualEnergySensors,
    onUpdateEvents, onUpdateBinarySensors,
  });

  const {
    fileInputRef, importDialogOpen, importData, importMode, importError,
    setImportMode, handleExport, handleFileSelect, confirmImport, cancelImport,
  } = useImportExport({ sectionType, value, onChange });

  // ─── Data Fetching ──────────────────────────────────────────────

  // Collect interlock groups from config data + runtime API.
  // Config data is the primary source (works even when outputs are not instantiated).
  useEffect(() => {
    if (sectionType !== 'output' && sectionType !== 'remote_outputs') return;

    // 1. Extract groups from all config items (local + remote outputs)
    const configGroups = new Set<string>();
    const scanItem = (item: any) => {
      const g = item?.interlock_group;
      if (Array.isArray(g)) {
        g.forEach((name: string) => { if (name) configGroups.add(name); });
      } else if (typeof g === 'string' && g) {
        configGroups.add(g);
      }
    };
    allOutputs.forEach(scanItem);
    value.forEach(scanItem);

    // 2. Merge with runtime API (may have groups not yet in config)
    axios.get('/api/interlock-groups')
      .then(res => {
        (res.data.groups || []).forEach((g: string) => configGroups.add(g));
        setInterlockGroups(Array.from(configGroups).sort());
      })
      .catch(() => {
        // API failed — use config-only groups
        setInterlockGroups(Array.from(configGroups).sort());
      });
  }, [sectionType, allOutputs, value]);

  const handleInterlockGroupCreated = (groupName: string) => {
    setInterlockGroups(prev => prev.includes(groupName) ? prev : [...prev, groupName].sort());
  };

  useEffect(() => {
    if (sectionType === 'sensor') {
      axios.get('/api/dallas/available')
        .then(res => setAvailableDallasSensors(res.data.sensors || []))
        .catch(err => console.error('Failed to fetch Dallas sensors:', err));
    }
  }, [sectionType]);

  // ─── Auto-Open from URL ─────────────────────────────────────────

  useEffect(() => {
    if (!editItemName || value.length === 0 || editItemProcessedRef.current === editItemName) return;

    const index = value.findIndex((item: any) => {
      if (item.name === editItemName || item.id === editItemName) return true;
      if (item.boneio_input === editItemName || item.boneio_output === editItemName) return true;
      if (sectionType === 'cover' && item.open_relay && item.close_relay) {
        if (`cover_${item.open_relay}_${item.close_relay}`.toLowerCase().replace(/ /g, '_') === editItemName) return true;
      }
      if (sectionType === 'modbus_devices' && item.address && item.model) {
        if (`${item.address}_${item.model}`.toLowerCase().replace(/ /g, '_') === editItemName) return true;
      }
      return false;
    });

    if (index !== -1) {
      editItemProcessedRef.current = editItemName;
      const item = { ...value[index] };
      if (isInputSection(sectionType) && item.id && !item.name) {
        item.name = item.id;
        delete item.id;
      }
      setEditingItem(item);
      setEditingIndex(index);
      originalItemRef.current = JSON.stringify(item);
      setHasValidationErrors(false);
      setAttemptedSubmit(false);
      setIsModalOpen(true);
      onEditItemOpened?.();
    }
  }, [editItemName, value, sectionType, onEditItemOpened]);

  // ─── CRUD Handlers ──────────────────────────────────────────────

  const handleEdit = (index: number) => {
    const item = JSON.parse(JSON.stringify(value[index]));
    if (isInputSection(sectionType) && item.id && !item.name) {
      item.name = item.id;
      delete item.id;
    }
    setEditingItem(item);
    setEditingIndex(index);
    originalItemRef.current = JSON.stringify(item);
    setHasValidationErrors(false);
    setAttemptedSubmit(false);
    setIsModalOpen(true);
  };

  /**
   * Duplicate an item: deep-copy it, adjust id/name to avoid conflicts,
   * then open it as a new item for editing.
   */
  const handleDuplicate = (index: number) => {
    const item = JSON.parse(JSON.stringify(value[index]));
    // Append suffix to avoid id/name collision
    if (item.id) item.id = `${item.id}_copy`;
    if (item.name) item.name = `${item.name} (copy)`;
    // For irrigation zones, also reset zone IDs to avoid conflicts
    if (item.zones && Array.isArray(item.zones)) {
      item.zones = item.zones.map((z: any) => ({
        ...z,
        id: z.id ? `${z.id}_copy` : undefined,
      }));
    }
    setEditingItem(item);
    setEditingIndex(null); // null = creating a new item
    originalItemRef.current = null;
    setHasValidationErrors(false);
    setAttemptedSubmit(false);
    setIsModalOpen(true);
  };

  const handleAdd = () => {
    setEditingIndex(null);
    if (sectionType === 'modbus_devices') {
      setIsModbusWizardOpen(true);
      return;
    }
    if (sectionType === 'remote_devices') {
      setEditingItem({ protocol: 'mqtt', device_type: 'boneio_black' });
    } else if (sectionType === 'template') {
      setShowTemplatePicker(true);
      return;
    } else if (sectionType === 'local_inputs') {
      setEditingItem({ _type: 'event' });
    } else {
      setEditingItem({});
    }
    originalItemRef.current = null;
    setHasValidationErrors(false);
    setAttemptedSubmit(false);
    setIsModalOpen(true);
  };

  const handleTemplatePlatformSelect = (platform: string) => {
    setShowTemplatePicker(false);
    setEditingItem({ platform, _autoId: true });
    originalItemRef.current = null;
    setHasValidationErrors(false);
    setAttemptedSubmit(false);
    setIsModalOpen(true);
  };

  const handleAddFromDiscovery = (device: any) => {
    setEditingIndex(null);
    if (device.protocol === 'esphome_api' || device.esphome_api) {
      setEditingItem({
        id: device.id, name: device.name || device.id, protocol: 'esphome_api', device_type: 'esphome',
        esphome_api: {
          host: device.esphome_api?.host || '', port: device.esphome_api?.port || 6053,
          password: device.esphome_api?.password || '', encryption_key: device.esphome_api?.encryption_key || '',
          switches: device.esphome_api?.switches || [], lights: device.esphome_api?.lights || [],
          covers: device.esphome_api?.covers || [],
        },
      });
    } else if (device.protocol === 'wled' || device.wled) {
      setEditingItem({
        id: device.id, name: device.name || device.id, protocol: 'wled', device_type: 'wled',
        wled: { host: device.wled?.host || '', port: device.wled?.port || 80, segments: device.wled?.segments || [] },
      });
    } else {
      setEditingItem({
        id: device.id, name: device.name || device.id, protocol: device.protocol || 'mqtt',
        device_type: device.device_type || 'boneio_black',
        mqtt: { outputs: device.mqtt?.outputs || device.outputs || [], covers: device.mqtt?.covers || device.covers || [] },
      });
    }
    originalItemRef.current = null;
    setHasValidationErrors(false);
    setAttemptedSubmit(false);
    setIsModalOpen(true);
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    setEditingItem(null);
    setEditingIndex(null);
  };

  const handleSave = (e?: any) => {
    setAttemptedSubmit(true);
    if (hasValidationErrors) {
      alert(t('array_table_widget.fix_validation_errors_before_saving'));
      return;
    }

    const dataToSave = e?.formData || editingItem;
    const { isValid, errorMessage } = validateItem(sectionType, dataToSave, t);
    if (!isValid) {
      alert(errorMessage);
      return;
    }

    // Clean legacy id/name duplication
    let cleanedData = { ...dataToSave };
    if (isInputSection(sectionType) && cleanedData.name && cleanedData.id) {
      delete cleanedData.id;
    }

    // Auto-generate template ID
    if (sectionType === 'template') {
      delete cleanedData._autoId;
      if (!cleanedData.id) {
        const baseName = (cleanedData.name || cleanedData.platform || 'template').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
        const existingIds = new Set(value.filter((_: any, i: number) => i !== editingIndex).map((item: any) => item.id));
        let candidateId = baseName;
        let suffix = 2;
        while (existingIds.has(candidateId)) { candidateId = `${baseName}_${suffix}`; suffix++; }
        cleanedData.id = candidateId;
      }
    }

    const newValue = [...value];
    if (editingIndex !== null) {
      newValue[editingIndex] = cleanedData;
    } else {
      newValue.push(cleanedData);
    }
    onChange(newValue);
    setIsModalOpen(false);
    setEditingItem(null);
    setEditingIndex(null);
  };

  // ─── Delete Logic ───────────────────────────────────────────────

  const getItemId = (item: any): string => {
    if (sectionType === 'output') return item.id || item.boneio_output || '';
    if (sectionType === 'output_group') return item.id || '';
    if (sectionType === 'cover') return item.id || (item.open_relay && item.close_relay ? `cover_${item.open_relay}_${item.close_relay}`.toLowerCase() : '');
    if (sectionType === 'remote_devices') return item.id || '';
    return '';
  };

  const handleDelete = (index: number) => {
    const item = value[index];

    if (sectionType === 'areas') {
      const affected = findItemsUsingArea(item.id);
      if (affected.length > 0) {
        setDeleteIndex(index);
        setAffectedActions(affected);
        setDeleteConfirmOpen(true);
        return;
      }
    }

    if (['output', 'output_group', 'cover', 'remote_devices'].includes(sectionType)) {
      const itemId = getItemId(item);
      const affected = findAffectedActions(itemId, sectionType === 'remote_devices');
      if (affected.length > 0) {
        setDeleteIndex(index);
        setAffectedActions(affected);
        setDeleteConfirmOpen(true);
        return;
      }
    }

    onChange(value.filter((_, i) => i !== index));
  };

  const confirmDelete = async () => {
    if (deleteIndex === null) return;
    const item = value[deleteIndex];

    if (sectionType === 'areas') {
      const newValue = value.filter((_, i) => i !== deleteIndex);
      onChange(newValue);
      setDeleteConfirmOpen(false);
      setDeleteIndex(null);
      setAffectedActions([]);
      if (onSaveSection) await onSaveSection(sectionType, newValue);
      return;
    }

    const itemId = getItemId(item);
    const isRemoteDevice = sectionType === 'remote_devices';
    const hasEventActions = affectedActions.some(a => a.type === t('array_table_widget.event'));
    const hasBSActions = affectedActions.some(a => a.type === t('array_table_widget.binary_sensor'));
    const { updatedEvents, updatedSensors } = removeOrphanedActions(itemId, isRemoteDevice);

    const newValue = value.filter((_, i) => i !== deleteIndex);
    onChange(newValue);
    setDeleteConfirmOpen(false);
    setDeleteIndex(null);
    setAffectedActions([]);

    if (onSaveSection) {
      await onSaveSection(sectionType, newValue);
      if (hasEventActions && updatedEvents) await onSaveSection('event', updatedEvents);
      if (hasBSActions && updatedSensors) await onSaveSection('binary_sensor', updatedSensors);
    }
  };

  const cancelDelete = () => {
    setDeleteConfirmOpen(false);
    setDeleteIndex(null);
    setAffectedActions([]);
  };

  // ─── AI Wizard ──────────────────────────────────────────────────

  const handleAiWizard = async () => {
    try {
      const { buildAiWizardPrompt } = await import('./helpers/aiWizardPrompt');
      const entityType = sectionType === 'event' ? 'event' : 'binary_sensor';
      const getEnum = (path: string) => path.split('.').reduce((o: any, k: string) => o?.[k], schema) || [];
      const actionTypeOptions = getEnum('items.properties.actions.properties.single.items.properties.action.enum') ||
        getEnum('items.properties.actions.properties.pressed.items.properties.action.enum') ||
        ['mqtt', 'output', 'cover', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'];
      const actionOutputOptions = getEnum('items.properties.actions.properties.single.items.properties.action_output.enum') ||
        getEnum('items.properties.actions.properties.pressed.items.properties.action_output.enum') ||
        ['TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET'];
      const actionCoverOptions = getEnum('items.properties.actions.properties.single.items.properties.action_cover.enum') ||
        getEnum('items.properties.actions.properties.pressed.items.properties.action_cover.enum') ||
        ['TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE'];

      const prompt = buildAiWizardPrompt({
        entityType: entityType as any, data: {} as any, schema,
        allOutputs, allOutputGroups, allCovers, allAreas, allRemoteDevices,
        allConfiguredInputs: value,
        actionTypeOptions, actionOutputOptions, actionCoverOptions,
      });
      await copyToClipboard(prompt);
      setWizardCopied(true);
      setTimeout(() => setWizardCopied(false), 3000);
    } catch (err) {
      console.error('Failed to copy wizard prompt:', err);
    }
  };

  // ─── Render ─────────────────────────────────────────────────────

  const allUsed = areAllItemsUsed(sectionType, value, schema, deviceType, allBinarySensors, allEvents);

  return (
    <div className="space-y-4">
      {/* Hidden file input for import */}
      <input type="file" ref={fileInputRef} onChange={handleFileSelect} accept=".yaml,.yml,.json" className="hidden" />

      {/* Toolbar */}
      <div className="flex justify-between items-center flex-wrap gap-2">
        <h3 className="text-lg font-semibold">{title || t('array_table_widget.items')}</h3>
        <div className="flex gap-2 flex-wrap">
          <div className="tooltip tooltip-bottom" data-tip={t('import_export.export')}>
            <button onClick={handleExport} className="btn btn-ghost btn-sm" disabled={value.length === 0}>
              <FaDownload />
              <span className="hidden sm:inline ml-1">{t('import_export.export')}</span>
            </button>
          </div>
          <div className="tooltip tooltip-bottom" data-tip={t('import_export.import')}>
            <button onClick={() => fileInputRef.current?.click()} className="btn btn-ghost btn-sm">
              <FaUpload />
              <span className="hidden sm:inline ml-1">{t('import_export.import')}</span>
            </button>
          </div>

          {isInputSection(sectionType) && (
            <div className="tooltip tooltip-bottom" data-tip={t('event_form.ai_wizard_description')}>
              <button onClick={handleAiWizard} className="btn btn-outline btn-sm">
                {wizardCopied ? t('event_form.ai_prompt_copied_short') : t('event_form.ai_copy_wizard')}
              </button>
            </div>
          )}

          <div className={`tooltip tooltip-left ${allUsed ? 'tooltip-warning' : 'tooltip-info'}`}
            data-tip={allUsed ? (sectionType === 'output' ? t('outputs.all_outputs_used') : t('inputs.all_inputs_used')) : t('settings.add_new')}>
            <button onClick={handleAdd} className="btn btn-primary btn-sm" disabled={allUsed}>
              <FaPlus className="mr-2" />
              {t('settings.add_new')}
            </button>
          </div>
        </div>
      </div>

      {/* Table or empty state */}
      {value.length > 0 || sectionType === 'remote_devices' ? (
        <TableRenderer
          sectionType={sectionType}
          items={value}
          allAreas={allAreas}
          allOutputs={allOutputs}
          allCovers={allCovers}
          allRemoteDevices={allRemoteDevices}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onDuplicate={sectionType === 'template' ? handleDuplicate : undefined}
          onAddFromDiscovery={handleAddFromDiscovery}
        />
      ) : (
        <div className="text-center py-8 text-base-content/60">
          <p>{t('settings.no_items')}</p>
          <p className="text-sm">{t('settings.click_add_new')}</p>
        </div>
      )}

      {/* Template Platform Picker */}
      <TemplatePicker open={showTemplatePicker} onOpenChange={setShowTemplatePicker} onSelect={handleTemplatePlatformSelect} />

      {/* Edit Modal */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent className="max-w-4xl sm:max-w-3xl lg:w-[120vw] max-h-[80vh] flex flex-col gap-0 bg-base-100">
          <DialogHeader>
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
                value={value}
                interlockGroups={interlockGroups}
                availableDallasSensors={availableDallasSensors}
                onChange={setEditingItem}
                onSave={handleSave}
                onCancel={handleCancel}
                onValidationChange={setHasValidationErrors}
                onInterlockGroupCreated={handleInterlockGroupCreated}
                attemptedSubmit={attemptedSubmit}
              />
            )}
          </div>

          <DialogFooter className="shrink-0 mt-2">
            <button type="button" onClick={handleCancel} className="btn btn-ghost">
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="btn btn-primary"
              disabled={hasValidationErrors || (editingIndex !== null && originalItemRef.current !== null && JSON.stringify(editingItem) === originalItemRef.current)}
              title={hasValidationErrors ? t('settings.fix_validation_errors') : ''}
            >
              {editingIndex !== null ? t('settings.save_changes') : t('settings.add_item')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <DeleteConfirmDialog
        open={deleteConfirmOpen}
        onOpenChange={setDeleteConfirmOpen}
        sectionType={sectionType}
        affectedActions={affectedActions}
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
      />

      {/* Import Confirmation */}
      <ImportDialog
        open={importDialogOpen}
        onOpenChange={() => cancelImport()}
        importData={importData}
        importError={importError}
        importMode={importMode}
        onModeChange={setImportMode}
        onConfirm={confirmImport}
        onCancel={cancelImport}
      />

      {/* Modbus Device Wizard */}
      {sectionType === 'modbus_devices' && (
        <AddModbusDeviceWizard
          open={isModbusWizardOpen}
          onOpenChange={setIsModbusWizardOpen}
          allAreas={allAreas}
          allModbusDevices={value}
          onAdd={(deviceConfig) => {
            const newValue = [...value, deviceConfig];
            onChange(newValue);
          }}
        />
      )}
    </div>
  );
};

export default ArrayTableWidget;
