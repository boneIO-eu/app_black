import React, { useState, useEffect } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '../../hooks/useTranslation';
import BinarySensorForm from './BinarySensorForm';
import EventForm from './EventForm';
import OutputForm from './OutputForm';
import OutputGroupForm from './OutputGroupForm';
import CoverForm from './CoverForm';
import ModbusDeviceForm from './ModbusDeviceForm';
import AreasForm from './AreasForm';
import SensorForm from './SensorForm';
import VirtualEnergySensorForm from './VirtualEnergySensorForm';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import AreasTable from './tables/AreasTable';
import OutputTable from './tables/OutputTable';
import OutputGroupTable from './tables/OutputGroupTable';
import CoverTable from './tables/CoverTable';
import BinarySensorEventTable from './tables/BinarySensorEventTable';
import ModbusDeviceTable from './tables/ModbusDeviceTable';
import SensorTable from './tables/SensorTable';
import VirtualEnergySensorTable from './tables/VirtualEnergySensorTable';
import GenericTable from './tables/GenericTable';

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
  sectionType?: 'binary_sensor' | 'event' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'sensor' | 'virtual_energy_sensor' | 'other';
  deviceType?: string;
  allBinarySensors?: any[];
  allEvents?: any[];
  allOutputs?: any[];
  allOutputGroups?: any[];
  allCovers?: any[];
  allAreas?: Area[];
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
}

/**
 * Custom table widget for array sections (e.g. event, binary_sensor) with modal editing.
 * Uses regular table with Edit buttons, @rjsf form only appears in modal.
 * This prevents automatic onChange calls during editing.
 */
const ArrayTableWidget: React.FC<ArrayTableWidgetProps> = ({ value = [], onChange, schema, title, uiSchema, sectionType = 'other', deviceType, allBinarySensors = [], allEvents = [], allOutputs = [], allOutputGroups = [], allCovers = [], allAreas = [], savedOutputs, savedOutputGroups, savedCovers, onUpdateEvents, onUpdateBinarySensors, onSaveSection }) => {
  const { t } = useTranslation();
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [hasValidationErrors, setHasValidationErrors] = useState(false);
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  const [interlockGroups, setInterlockGroups] = useState<string[]>([]);
  const [availableDallasSensors, setAvailableDallasSensors] = useState<{address: string, type: string}[]>([]);
  
  // State for delete confirmation dialog
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);
  const [affectedActions, setAffectedActions] = useState<{type: string, name: string, actionType: string}[]>([]);

  // Fetch interlock groups for output section
  useEffect(() => {
    if (sectionType === 'output') {
      fetch('/api/interlock-groups')
        .then(res => res.json())
        .then(data => {
          setInterlockGroups(data.groups || []);
        })
        .catch(err => {
          console.error('Failed to fetch interlock groups:', err);
        });
    }
  }, [sectionType]);

  // Callback to add new interlock group to local cache (before saving to backend)
  const handleInterlockGroupCreated = (groupName: string) => {
    setInterlockGroups(prev => {
      if (!prev.includes(groupName)) {
        return [...prev, groupName];
      }
      return prev;
    });
  };

  // Fetch available Dallas sensors for sensor section
  useEffect(() => {
    if (sectionType === 'sensor') {
      fetch('/api/dallas/available')
        .then(res => res.json())
        .then(data => {
          setAvailableDallasSensors(data.sensors || []);
        })
        .catch(err => {
          console.error('Failed to fetch Dallas sensors:', err);
        });
    }
  }, [sectionType]);

  // Format milliseconds to human-readable time
  const formatTimeperiod = (ms: number): string => {
    if (ms >= 60000) {
      const minutes = ms / 60000;
      return minutes % 1 === 0 ? `${minutes}min` : `${ms}ms`;
    } else if (ms >= 1000) {
      const seconds = ms / 1000;
      return seconds % 1 === 0 ? `${seconds}s` : `${ms}ms`;
    }
    return `${ms}ms`;
  };

  const handleEdit = (index: number) => {
    console.log('🔧 ArrayTableWidget: handleEdit called for index:', index);
    const item = { ...value[index] };
    
    // Migrate legacy 'id' field to 'name' for binary_sensor and event sections
    // This prevents duplicate fields when user edits old config with 'id' and form uses 'name'
    if ((sectionType === 'binary_sensor' || sectionType === 'event') && item.id && !item.name) {
      item.name = item.id;
      delete item.id;
    }
    
    setEditingItem(item);
    setEditingIndex(index);
    setAttemptedSubmit(false); // Reset przy otwieraniu modala
    setIsModalOpen(true);
  };

  const handleAdd = () => {
    console.log('➕ ArrayTableWidget: handleAdd called');
    setEditingIndex(null);
    setEditingItem({});
    setAttemptedSubmit(false); // Reset przy otwieraniu modala
    setIsModalOpen(true);
  };

  // Check if all outputs/inputs are used
  const areAllItemsUsed = () => {
    if (sectionType === 'output') {
      // Get available outputs based on device type
      const getOutputCount = (deviceType: string) => {
        const type = deviceType?.toLowerCase() || '';
        if (type.includes('32') || type.includes('cm')) {
          return 32; // 32x10A, Cover, Cover Mix
        } else if (type.includes('24')) {
          return 24; // 24x16A
        }
        return 49; // default fallback
      };

      const outputCount = getOutputCount(deviceType || '');
      const usedOutputs = value.filter(output => output.boneio_output).length;
      
      return usedOutputs >= outputCount;
    } else if (sectionType === 'binary_sensor' || sectionType === 'event') {
      // Check if all inputs are used (shared between binary_sensor and event)
      const usedInputsFromBinarySensors = allBinarySensors
        .filter(sensor => sensor.boneio_input)
        .map(sensor => sensor.boneio_input);
      
      const usedInputsFromEvents = allEvents
        .filter(event => event.boneio_input)
        .map(event => event.boneio_input);
      
      const allUsedInputs = [...new Set([...usedInputsFromBinarySensors, ...usedInputsFromEvents])];
      
      // Get total available inputs from schema (assuming it's the same for both)
      const totalInputs = (schema as any)?.items?.properties?.boneio_input?.enum?.length || 0;
      
      return allUsedInputs.length >= totalInputs;
    } else if (sectionType === 'output_group') {
      // Output groups don't have a fixed limit, so always allow adding
      return false;
    } else if (sectionType === 'cover') {
      // Covers don't have a fixed limit, so always allow adding
      return false;
    } else if (sectionType === 'modbus_devices') {
      // Modbus devices don't have a fixed limit, so always allow adding
      return false;
    }
    
    return false;
  };

  const handleSave = (e?: any) => {
    console.log('💾 ArrayTableWidget: handleSave called, calling onChange');
    
    // Oznacz że użytkownik próbował zapisać
    setAttemptedSubmit(true);
    
    // Block save if there are validation errors from child form
    if (hasValidationErrors) {
      console.log('❌ ArrayTableWidget: Save blocked due to validation errors');
      alert(t('array_table_widget.fix_validation_errors_before_saving'));
      return;
    }
    
    // If called from @rjsf onSubmit, e.formData contains the data
    const dataToSave = e?.formData || editingItem;
    
    // Validate required fields based on section type
    let isValid = false;
    let errorMessage = '';
    
    if (sectionType === 'binary_sensor') {
      isValid = !!dataToSave.boneio_input;
      errorMessage = t('array_table_widget.boneio_input_required');
    } else if (sectionType === 'event') {
      isValid = !!dataToSave.boneio_input;
      errorMessage = t('array_table_widget.boneio_input_required');
    } else if (sectionType === 'output') {
      isValid = !!dataToSave.boneio_output;
      errorMessage = t('array_table_widget.boneio_output_required');
    } else if (sectionType === 'output_group') {
      const hasId = !!dataToSave.id;
      const hasOutputs = !!dataToSave.outputs && (Array.isArray(dataToSave.outputs) ? dataToSave.outputs.length > 0 : true);
      isValid = hasId && hasOutputs;
      errorMessage = !hasId ? t('array_table_widget.id_required') : t('array_table_widget.at_least_one_output_required');
    } else if (sectionType === 'cover') {
      // ID is now optional (auto-generated from relays)
      isValid = !!dataToSave.open_relay && !!dataToSave.close_relay && !!dataToSave.open_time && !!dataToSave.close_time;
      errorMessage = t('array_table_widget.cover_fields_required');
    } else if (sectionType === 'modbus_devices') {
      // ID is now optional (auto-generated from address and model)
      isValid = !!dataToSave.address && !!dataToSave.model;
      errorMessage = t('array_table_widget.address_and_model_required');
      
      // Validate update_interval minimum (1 second = 1000ms)
      if (isValid && dataToSave.update_interval) {
        const interval = typeof dataToSave.update_interval === 'number' 
          ? dataToSave.update_interval 
          : parseInt(dataToSave.update_interval);
        
        if (interval < 1000) {
          isValid = false;
          errorMessage = t('array_table_widget.update_interval_minimum');
        }
      }
    } else {
      // For other sections, allow saving (or add specific validation)
      isValid = true;
    }
    
    if (!isValid) {
      alert(errorMessage);
      return;
    }
    
    // For binary_sensor and event, ensure we don't have both 'id' and 'name' fields
    // Remove legacy 'id' field if 'name' exists
    let cleanedData = { ...dataToSave };
    if ((sectionType === 'binary_sensor' || sectionType === 'event') && cleanedData.name && cleanedData.id) {
      delete cleanedData.id;
    }
    
    const newValue = [...value];
    if (editingIndex !== null) {
      newValue[editingIndex] = cleanedData;
    } else {
      newValue.push(cleanedData);
    }
    // Only call onChange when actually saving, not during editing
    console.log('🔄 ArrayTableWidget: calling onChange with:', newValue);
    onChange(newValue);
    setIsModalOpen(false);
    setEditingItem(null);
    setEditingIndex(null);
  };

  /**
   * Find all actions in events and binary_sensors that reference the given item ID.
   * Returns list of affected actions with their source (event/binary_sensor name and action type).
   */
  const findAffectedActions = (itemId: string): {type: string, name: string, actionType: string}[] => {
    const affected: {type: string, name: string, actionType: string}[] = [];
    
    // Check events
    allEvents.forEach((event: any) => {
      const eventName = event.name || event.boneio_input || t('array_table_widget.unknown_event');
      ['single', 'double', 'long'].forEach((pressType) => {
        const actions = event.actions?.[pressType] || [];
        actions.forEach((action: any) => {
          if (action.pin === itemId || action.boneio_output === itemId) {
            affected.push({
              type: t('array_table_widget.event'),
              name: eventName,
              actionType: `${pressType} → ${action.action || 'output'}`
            });
          }
        });
      });
    });
    
    // Check binary_sensors
    allBinarySensors.forEach((sensor: any) => {
      const sensorName = sensor.name || sensor.boneio_input || t('array_table_widget.unknown_sensor');
      ['pressed', 'released'].forEach((pressType) => {
        const actions = sensor.actions?.[pressType] || [];
        actions.forEach((action: any) => {
          if (action.pin === itemId || action.boneio_output === itemId) {
            affected.push({
              type: t('array_table_widget.binary_sensor'),
              name: sensorName,
              actionType: `${pressType} → ${action.action || 'output'}`
            });
          }
        });
      });
    });
    console.log("Affected actions:", affected);
    
    return affected;
  };

  /**
   * Remove actions that reference the given item ID from events and binary_sensors.
   * Returns the updated data for immediate saving.
   */
  const removeOrphanedActions = (itemId: string): { updatedEvents: any[] | null, updatedSensors: any[] | null } => {
    console.log('🗑️ removeOrphanedActions called with itemId:', itemId);
    
    let updatedEvents: any[] | null = null;
    let updatedSensors: any[] | null = null;
    
    // Update events
    if (onUpdateEvents) {
      updatedEvents = allEvents.map((event: any) => {
        const updatedActions: any = {};
        ['single', 'double', 'long'].forEach((pressType) => {
          const actions = event.actions?.[pressType] || [];
          const filtered = actions.filter((action: any) => {
            const shouldKeep = action.pin !== itemId && action.boneio_output !== itemId;
            if (!shouldKeep) {
              console.log(`🗑️ Removing action from event ${event.name || event.boneio_input}: ${pressType} -> boneio_output=${action.boneio_output}`);
            }
            return shouldKeep;
          });
          updatedActions[pressType] = filtered;
        });
        return { ...event, actions: updatedActions };
      });
      console.log('🗑️ Updated events:', updatedEvents);
      onUpdateEvents(updatedEvents);
    }
    
    // Update binary_sensors
    if (onUpdateBinarySensors) {
      updatedSensors = allBinarySensors.map((sensor: any) => {
        const updatedActions: any = {};
        ['pressed', 'released'].forEach((pressType) => {
          const actions = sensor.actions?.[pressType] || [];
          const filtered = actions.filter((action: any) => {
            const shouldKeep = action.pin !== itemId && action.boneio_output !== itemId;
            if (!shouldKeep) {
              console.log(`🗑️ Removing action from sensor ${sensor.name || sensor.boneio_input}: ${pressType} -> boneio_output=${action.boneio_output}`);
            }
            return shouldKeep;
          });
          updatedActions[pressType] = filtered;
        });
        return { ...sensor, actions: updatedActions };
      });
      console.log('🗑️ Updated sensors:', updatedSensors);
      onUpdateBinarySensors(updatedSensors);
    }
    
    return { updatedEvents, updatedSensors };
  };

  /**
   * Get the ID of an item being deleted based on section type.
   */
  const getItemId = (item: any): string => {
    if (sectionType === 'output') {
      return item.id || item.boneio_output || '';
    } else if (sectionType === 'output_group') {
      return item.id || '';
    } else if (sectionType === 'cover') {
      return item.id || (item.open_relay && item.close_relay 
        ? `cover_${item.open_relay}_${item.close_relay}`.toLowerCase()
        : '');
    }
    return '';
  };

  const handleDelete = (index: number) => {
    const item = value[index];
    
    // Only check for affected actions when deleting output, output_group, or cover
    if (sectionType === 'output' || sectionType === 'output_group' || sectionType === 'cover') {
      const itemId = getItemId(item);
      const affected = findAffectedActions(itemId);
      
      if (affected.length > 0) {
        // Show confirmation dialog
        setDeleteIndex(index);
        setAffectedActions(affected);
        setDeleteConfirmOpen(true);
        return;
      }
    }
    
    // No affected actions, delete directly
    const newValue = value.filter((_, i) => i !== index);
    onChange(newValue);
  };

  const confirmDelete = async () => {
    if (deleteIndex === null) return;
    
    const item = value[deleteIndex];
    const itemId = getItemId(item);
    
    // Check which sections have affected actions
    const hasEventActions = affectedActions.some(a => a.type === 'Event');
    const hasBinarySensorActions = affectedActions.some(a => a.type === 'Binary Sensor');
    
    // Remove orphaned actions first and get updated data
    const { updatedEvents, updatedSensors } = removeOrphanedActions(itemId);
    
    // Delete the item and get updated value
    const newValue = value.filter((_, i) => i !== deleteIndex);
    onChange(newValue);
    
    // Close dialog
    setDeleteConfirmOpen(false);
    setDeleteIndex(null);
    setAffectedActions([]);
    
    // Save all affected sections with the updated data directly
    if (onSaveSection) {
      // First save the current section (output/output_group/cover) with the item removed
      console.log(`🔄 Auto-saving ${sectionType} section with item removed:`, newValue);
      await onSaveSection(sectionType, newValue);
      
      // Then save event and binary_sensor sections with orphaned actions removed
      if (hasEventActions && updatedEvents) {
        console.log('🔄 Auto-saving event section with updated data:', updatedEvents);
        await onSaveSection('event', updatedEvents);
      }
      if (hasBinarySensorActions && updatedSensors) {
        console.log('🔄 Auto-saving binary_sensor section with updated data:', updatedSensors);
        await onSaveSection('binary_sensor', updatedSensors);
      }
    }
  };

  const cancelDelete = () => {
    setDeleteConfirmOpen(false);
    setDeleteIndex(null);
    setAffectedActions([]);
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    setEditingItem(null);
    setEditingIndex(null);
  };


  // Render appropriate table component based on section type
  const renderTable = () => {
    const commonProps = {
      items: value,
      onEdit: handleEdit,
      onDelete: handleDelete,
    };

    switch (sectionType) {
      case 'output':
        return <OutputTable {...commonProps} allAreas={allAreas} />;
      case 'output_group':
        return <OutputGroupTable {...commonProps} allAreas={allAreas} />;
      case 'cover':
        return <CoverTable {...commonProps} allAreas={allAreas} />;
      case 'binary_sensor':
      case 'event':
        return <BinarySensorEventTable {...commonProps} allAreas={allAreas} />;
      case 'modbus_devices':
        return <ModbusDeviceTable {...commonProps} allAreas={allAreas} formatTimeperiod={formatTimeperiod} />;
      case 'areas':
        return <AreasTable {...commonProps} />;
      case 'sensor':
        return <SensorTable {...commonProps} allAreas={allAreas} />;
      case 'virtual_energy_sensor':
        return <VirtualEnergySensorTable {...commonProps} allAreas={allAreas} />;
      default:
        return <GenericTable {...commonProps} />;
    }
  };


  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">{title || t('array_table_widget.items')}</h3>
        <div className={`tooltip tooltip-left ${areAllItemsUsed() ? 'tooltip-warning' : 'tooltip-info'}`} 
             data-tip={areAllItemsUsed() ? (sectionType === 'output' ? t('outputs.all_outputs_used') : t('inputs.all_inputs_used')) : t('settings.add_new')}>
          <button
            onClick={handleAdd}
            className="btn btn-primary btn-sm"
            disabled={areAllItemsUsed()}
          >
            <FaPlus className="mr-2" />
            {t('settings.add_new')}
          </button>
        </div>
      </div>

      {value.length > 0 ? (
        renderTable()
      ) : (
        <div className="text-center py-8 text-base-content/60">
          <p>{t('settings.no_items')}</p>
          <p className="text-sm">{t('settings.click_add_new')}</p>
        </div>
      )}

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
          </DialogHeader>
          
          {/* Scrollable content area */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden -mx-6 px-6 wrap-break-words [&_.label-text]:whitespace-normal [&_.label-text]:wrap-break-words [&_.label-text-alt]:whitespace-normal [&_.label-text-alt]:wrap-break-words [&_.form-control]:min-w-0">
            {/* Only render form when editingItem is not null */}
            {editingItem && (
              <>
                {/* Use custom form for binary_sensor/event/output, @rjsf for others */}
                {sectionType === 'binary_sensor' ? (
                  <BinarySensorForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allBinarySensors={allBinarySensors}
                    allEvents={allEvents}
                    allOutputs={allOutputs}
                    allOutputGroups={allOutputGroups}
                    allCovers={allCovers}
                    allAreas={allAreas}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                    savedOutputs={savedOutputs}
                    savedOutputGroups={savedOutputGroups}
                    savedCovers={savedCovers}
                  />
                ) : sectionType === 'event' ? (
                  <EventForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allBinarySensors={allBinarySensors}
                    allEvents={allEvents}
                    allOutputs={allOutputs}
                    allOutputGroups={allOutputGroups}
                    allCovers={allCovers}
                    allAreas={allAreas}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                    attemptedSubmit={attemptedSubmit}
                    savedOutputs={savedOutputs}
                    savedOutputGroups={savedOutputGroups}
                    savedCovers={savedCovers}
                  />
                ) : sectionType === 'output' ? (
                  <OutputForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    uiSchema={uiSchema}
                    deviceType={deviceType}
                    allOutputs={value}
                    allAreas={allAreas}
                    editingIndex={editingIndex}
                    interlockGroups={interlockGroups}
                    onInterlockGroupCreated={handleInterlockGroupCreated}
                  />
                ) : sectionType === 'output_group' ? (
                  <OutputGroupForm
                    data={editingItem}
                    onChange={setEditingItem}
                    schema={schema}
                    allOutputs={allOutputs}
                    allAreas={allAreas}
                  />
                ) : sectionType === 'cover' ? (
                  <CoverForm
                    data={editingItem}
                    onChange={setEditingItem}
                    schema={schema}
                    allOutputs={allOutputs}
                    allAreas={allAreas}
                  />
                ) : sectionType === 'modbus_devices' ? (
                  <ModbusDeviceForm
                    data={editingItem}
                    onChange={setEditingItem}
                    schema={schema}
                    areas={allAreas}
                  />
                ) : sectionType === 'areas' ? (
                  <AreasForm
                    data={editingItem}
                    onChange={setEditingItem}
                  />
                ) : sectionType === 'sensor' ? (
                  <SensorForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allAreas={allAreas}
                    availableSensors={availableDallasSensors}
                    existingSensors={value}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                  />
                ) : sectionType === 'virtual_energy_sensor' ? (
                  <VirtualEnergySensorForm
                    data={editingItem}
                    onChange={setEditingItem}
                    onSave={handleSave}
                    onCancel={handleCancel}
                    isNew={editingIndex === null}
                    schema={schema}
                    allAreas={allAreas}
                    allOutputs={allOutputs}
                    existingSensors={value}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
                  />
                ) : (
                  <div className="alert alert-warning">
                    <span>{t('array_table_widget.no_form_available').replace('{sectionType}', sectionType)}</span>
                  </div>
                )}
              </>
            )}
          </div>
          
          {/* Action buttons - fixed at bottom */}
          <DialogFooter className="shrink-0 mt-2">
            <button 
              type="button" 
              onClick={handleCancel} 
              className="btn btn-ghost"
            >
              {t('common.cancel')}
            </button>
            <button 
              type="button" 
              onClick={handleSave} 
              className="btn btn-primary"
              disabled={hasValidationErrors}
              title={hasValidationErrors ? t('settings.fix_validation_errors') : ''}
            >
              {editingIndex !== null ? t('settings.save_changes') : t('settings.add_item')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-md bg-base-100">
          <DialogHeader>
            <DialogTitle className="text-warning flex items-center gap-2">
              ⚠️ {t('settings.delete_warning_title')}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="mb-4">{t('settings.delete_warning_message')}</p>
            <div className="bg-base-200 rounded-lg p-3 max-h-48 overflow-y-auto">
              <p className="font-medium mb-2">{t('settings.affected_actions')} ({affectedActions.length}):</p>
              <ul className="space-y-1 text-sm">
                {affectedActions.map((action, idx) => (
                  <li key={idx} className="flex items-center gap-2">
                    <span className="badge badge-xs badge-outline">{action.type}</span>
                    <span className="font-medium">{action.name}</span>
                    <span className="text-base-content/60">→ {action.actionType}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <DialogFooter>
            <button 
              type="button" 
              onClick={cancelDelete} 
              className="btn btn-ghost"
            >
              {t('common.cancel')}
            </button>
            <button 
              type="button" 
              onClick={confirmDelete} 
              className="btn btn-error"
            >
              {t('settings.delete_and_remove_actions')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ArrayTableWidget;
