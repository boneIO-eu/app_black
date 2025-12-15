import React, { useState, useEffect } from 'react';
import { FaEdit, FaTrash, FaPlus } from 'react-icons/fa';
import { useTranslation } from '../../hooks/useTranslation';
import BinarySensorForm from './BinarySensorForm';
import EventForm from './EventForm';
import OutputForm from './OutputForm';
import OutputGroupForm from './OutputGroupForm';
import CoverForm from './CoverForm';
import ModbusDeviceForm from './ModbusDeviceForm';
import AreasForm from './AreasForm';
import SensorForm from './SensorForm';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

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
  sectionType?: 'binary_sensor' | 'event' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'sensor' | 'other';
  deviceType?: string;
  allBinarySensors?: any[];
  allEvents?: any[];
  allOutputs?: any[];
  allOutputGroups?: any[];
  allCovers?: any[];
  allAreas?: Area[];
}

/**
 * Custom table widget for array sections (e.g. event, binary_sensor) with modal editing.
 * Uses regular table with Edit buttons, @rjsf form only appears in modal.
 * This prevents automatic onChange calls during editing.
 */
const ArrayTableWidget: React.FC<ArrayTableWidgetProps> = ({ value = [], onChange, schema, title, uiSchema, sectionType = 'other', deviceType, allBinarySensors = [], allEvents = [], allOutputs = [], allOutputGroups = [], allCovers = [], allAreas = [] }) => {
  const { t } = useTranslation();
  
  // Debug: log allCovers when in event/binary_sensor section
  if (sectionType === 'event' || sectionType === 'binary_sensor') {
    console.log('🎯 ArrayTableWidget allCovers:', allCovers, 'sectionType:', sectionType);
  }
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [hasValidationErrors, setHasValidationErrors] = useState(false);
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  const [interlockGroups, setInterlockGroups] = useState<string[]>([]);
  const [availableDallasSensors, setAvailableDallasSensors] = useState<{address: string, type: string}[]>([]);

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
      alert('Please fix validation errors before saving');
      return;
    }
    
    // If called from @rjsf onSubmit, e.formData contains the data
    const dataToSave = e?.formData || editingItem;
    
    // Validate required fields based on section type
    let isValid = false;
    let errorMessage = '';
    
    if (sectionType === 'binary_sensor') {
      isValid = !!dataToSave.boneio_input;
      errorMessage = 'BoneIO Input is required';
    } else if (sectionType === 'event') {
      isValid = !!dataToSave.boneio_input;
      errorMessage = 'BoneIO Input is required';
    } else if (sectionType === 'output') {
      isValid = !!dataToSave.boneio_output;
      errorMessage = 'BoneIO Output is required';
    } else if (sectionType === 'output_group') {
      const hasId = !!dataToSave.id;
      const hasOutputs = !!dataToSave.outputs && (Array.isArray(dataToSave.outputs) ? dataToSave.outputs.length > 0 : true);
      isValid = hasId && hasOutputs;
      errorMessage = !hasId ? 'ID is required' : 'At least one output is required';
    } else if (sectionType === 'cover') {
      // ID is now optional (auto-generated from relays)
      isValid = !!dataToSave.open_relay && !!dataToSave.close_relay && !!dataToSave.open_time && !!dataToSave.close_time;
      errorMessage = 'Open relay, close relay, open time and close time are required';
    } else if (sectionType === 'modbus_devices') {
      // ID is now optional (auto-generated from address and model)
      isValid = !!dataToSave.address && !!dataToSave.model;
      errorMessage = 'Address and model are required';
      
      // Validate update_interval minimum (1 second = 1000ms)
      if (isValid && dataToSave.update_interval) {
        const interval = typeof dataToSave.update_interval === 'number' 
          ? dataToSave.update_interval 
          : parseInt(dataToSave.update_interval);
        
        if (interval < 1000) {
          isValid = false;
          errorMessage = 'Update interval must be at least 1 second (1000ms)';
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

  const handleDelete = (index: number) => {
    const newValue = value.filter((_, i) => i !== index);
    onChange(newValue);
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    setEditingItem(null);
    setEditingIndex(null);
  };


  // Render table headers based on section type
  const renderTableHeaders = () => {
    if (sectionType === 'output') {
      return (
        <tr>
          <th>{t('outputs.name')} / {t('outputs.id')}</th>
          <th>{t('outputs.boneio_output')}</th>
          <th>{t('outputs.type')}</th>
          <th>{t('outputs.area')}</th>
          <th>{t('outputs.interlock')}</th>
          <th>{t('outputs.restore')}</th>
          <th>{t('outputs.momentary')}</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    } else if (sectionType === 'output_group') {
      return (
        <tr>
          <th>{t('outputs.name')} / {t('outputs.id')}</th>
          <th>{t('groups.member_outputs')}</th>
          <th>{t('outputs.type')}</th>
          <th>{t('groups.all_on')}</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    } else if (sectionType === 'cover') {
      return (
        <tr>
          <th>{t('outputs.name')} / {t('outputs.id')}</th>
          <th>{t('covers.platform')}</th>
          <th>{t('covers.open_relay')}</th>
          <th>{t('covers.close_relay')}</th>
          <th>{t('covers.times')}</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    } else if (sectionType === 'modbus_devices') {
      return (
        <tr>
          <th>{t('modbus.name_id')}</th>
          <th>{t('modbus.model')}</th>
          <th>{t('modbus.address')}</th>
          <th>{t('modbus.update_interval')}</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    } else if (sectionType === 'binary_sensor' || sectionType === 'event') {
      return (
        <tr>
          <th>{t('inputs.id')}/{t('inputs.name')}</th>
          <th>{t('inputs.boneio_input')}</th>
          <th>{t('inputs.area')}</th>
          <th>{t('inputs.has_actions')}</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    } else if (sectionType === 'areas') {
      return (
        <tr>
          <th>{t('areas.id')}</th>
          <th>{t('areas.name')}</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    } else if (sectionType === 'sensor') {
      return (
        <tr>
          <th>{t('sensors.name')} / {t('sensors.id')}</th>
          <th>{t('sensors.address')}</th>
          <th>{t('sensors.area')}</th>
          <th>{t('sensors.platform')}</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    } else {
      return (
        <tr>
          <th>{t('outputs.id')}/{t('outputs.name')}</th>
          <th>Details</th>
          <th>{t('outputs.actions')}</th>
        </tr>
      );
    }
  };

  // Render table rows based on section type
  const renderTableRows = () => {
    if (sectionType === 'modbus_devices') {
      return value.map((item, index) => {
        // Generate display ID if not set
        const displayId = item.id || (item.address && item.model 
          ? `${item.address}_${item.model}`.toLowerCase() 
          : `Device ${index + 1}`);
        return (
          <tr key={index}>
            <td>
              <div>
                {item.name && <div className="font-medium">{item.name}</div>}
                <div className={item.name ? "text-xs text-base-content/60" : ""}>{displayId}</div>
              </div>
            </td>
            <td>
              {item.model ? (
                <span className="badge badge-info badge-sm uppercase">{item.model}</span>
              ) : (
                '-'
              )}
            </td>
            <td>{item.address || '-'}</td>
            <td>{item.update_interval ? formatTimeperiod(item.update_interval) : '-'}</td>
            <td>
              <div className="flex space-x-1">
                <button
                  onClick={() => handleEdit(index)}
                  className="btn btn-ghost btn-xs"
                  title="Edit Item"
                >
                  <FaEdit />
                </button>
                <button
                  onClick={() => handleDelete(index)}
                  className="btn btn-ghost btn-xs text-error"
                  title="Delete"
                >
                  <FaTrash />
                </button>
              </div>
            </td>
          </tr>
        );
      });
    } else if (sectionType === 'cover') {
      return value.map((item, index) => {
        // Generate display ID if not set
        const displayId = item.id || (item.open_relay && item.close_relay 
          ? `cover_${item.open_relay}_${item.close_relay}`.toLowerCase() 
          : `Cover ${index + 1}`);
        return (
          <tr key={index}>
            <td>
              <div>
                {item.name && <div className="font-medium">{item.name}</div>}
                <div className={item.name ? "text-xs text-base-content/60" : ""}>{displayId}</div>
              </div>
            </td>
            <td>
              {item.platform ? (
                <span className="badge badge-info badge-sm">{item.platform}</span>
              ) : (
                '-'
              )}
            </td>
            <td className="uppercase">{item.open_relay || '-'}</td>
            <td className="uppercase">{item.close_relay || '-'}</td>
            <td>
              <div className="text-xs">
                <div>Open: {item.open_time ? `${item.open_time}ms` : '-'}</div>
                <div>Close: {item.close_time ? `${item.close_time}ms` : '-'}</div>
                {item.tilt_duration && <div>Tilt: {item.tilt_duration}ms</div>}
                {item.actuator_activation_duration && <div>Actuator: {item.actuator_activation_duration}ms</div>}
              </div>
            </td>
            <td>
              <div className="flex space-x-1">
                <button
                  onClick={() => handleEdit(index)}
                  className="btn btn-ghost btn-xs"
                  title="Edit Item"
                >
                  <FaEdit />
                </button>
                <button
                  onClick={() => handleDelete(index)}
                  className="btn btn-ghost btn-xs text-error"
                  title="Delete"
                >
                  <FaTrash />
                </button>
              </div>
            </td>
          </tr>
        );
      });
    } else if (sectionType === 'output_group') {
      return value.map((item, index) => {
        const outputs = Array.isArray(item.outputs) ? item.outputs : [];
        const displayName = item.name || item.id || `Group ${index + 1}`;
        return (
          <tr key={index}>
            <td>
              <div>
                <div className="font-medium">{displayName}</div>
                {item.name && item.id && (
                  <div className="text-xs text-base-content/60">ID: {item.id}</div>
                )}
              </div>
            </td>
            <td>
              <div className="flex flex-wrap gap-1">
                {outputs.length > 0 ? (
                  outputs.map((output: string, idx: number) => (
                    <span key={idx} className="badge badge-primary badge-sm uppercase">
                      {output}
                    </span>
                  ))
                ) : (
                  <span className="text-warning">No outputs</span>
                )}
              </div>
            </td>
            <td>
              {item.output_type ? (
                <span className="badge badge-info badge-sm">{item.output_type}</span>
              ) : (
                '-'
              )}
            </td>
            <td>
              {item.all_on_behaviour ? (
                <span className="badge badge-success badge-sm">Yes</span>
              ) : (
                <span className="badge badge-ghost badge-sm">No</span>
              )}
            </td>
            <td>
              <div className="flex space-x-1">
                <button
                  onClick={() => handleEdit(index)}
                  className="btn btn-ghost btn-xs"
                  title="Edit Item"
                >
                  <FaEdit />
                </button>
                <button
                  onClick={() => handleDelete(index)}
                  className="btn btn-ghost btn-xs text-error"
                  title="Delete"
                >
                  <FaTrash />
                </button>
              </div>
            </td>
          </tr>
        );
      });
    } else if (sectionType === 'output') {
      return value.map((item, index) => {
        const isMomentary = item.momentary_turn_on || item.momentary_turn_off;
        // effective_id: id > boneio_output
        const effectiveId = item.id || item.boneio_output;
        const displayName = item.name || effectiveId || `Item ${index + 1}`;
        // Find area name from allAreas
        const areaName = item.area 
          ? allAreas.find(a => a.id === item.area)?.name || item.area 
          : '-';
        return (
          <tr key={index}>
            <td>
              <div>
                <div className="font-medium">{displayName}</div>
                {item.name && effectiveId && (
                  <div className="text-xs text-base-content/60">ID: {effectiveId}</div>
                )}
              </div>
            </td>
            <td className="uppercase">{item.boneio_output || '-'}</td>
            <td>
              {item.output_type ? (
                <span className="badge badge-info badge-sm">{item.output_type}</span>
              ) : (
                '-'
              )}
            </td>
            <td>{areaName}</td>
            <td>
              {item.interlock_group ? (
                <span className="badge badge-error badge-sm" title={`Interlock: ${item.interlock_group}`}>
                  {item.interlock_group}
                </span>
              ) : (
                <span className="text-base-content/40">-</span>
              )}
            </td>
            <td>
              {item.restore_state !== undefined ? (
                item.restore_state ? (
                  <span className="badge badge-success badge-sm">Yes</span>
                ) : (
                  <span className="badge badge-ghost badge-sm">No</span>
                )
              ) : (
                '-'
              )}
            </td>
            <td>
              {isMomentary ? (
                <span className="badge badge-warning badge-sm">Yes</span>
              ) : (
                <span className="badge badge-ghost badge-sm">No</span>
              )}
            </td>
            <td>
              <div className="flex space-x-1">
                <button
                  onClick={() => handleEdit(index)}
                  className="btn btn-ghost btn-xs"
                  title={t('outputs.edit')}
                >
                  <FaEdit />
                </button>
                <button
                  onClick={() => handleDelete(index)}
                  className="btn btn-ghost btn-xs text-error"
                  title={t('outputs.delete')}
                >
                  <FaTrash />
                </button>
              </div>
            </td>
          </tr>
        );
      });
    } else if (sectionType === 'binary_sensor' || sectionType === 'event') {
      return value.map((item, index) => {
        // Find area name from allAreas
        const areaName = item.area 
          ? allAreas.find(a => a.id === item.area)?.name || item.area 
          : '-';
        
        return (
          <tr key={index}>
            <td>{item.name || `Item ${index + 1}`}</td>
            <td className="uppercase">{item.boneio_input || '-'}</td>
            <td>{areaName}</td>
            <td>
              {item.actions ? (
                <span className="badge badge-success badge-sm">Yes</span>
              ) : (
                <span className="badge badge-ghost badge-sm">No</span>
              )}
            </td>
            <td>
              <div className="flex space-x-1">
                <button
                  onClick={() => handleEdit(index)}
                  className="btn btn-ghost btn-xs"
                  title="Edit Item"
                >
                  <FaEdit />
                </button>
                <button
                  onClick={() => handleDelete(index)}
                  className="btn btn-ghost btn-xs text-error"
                  title="Delete"
                >
                  <FaTrash />
                </button>
              </div>
            </td>
          </tr>
        );
      });
    } else if (sectionType === 'areas') {
      return value.map((item, index) => (
        <tr key={index}>
          <td className="font-mono">{item.id || `area_${index + 1}`}</td>
          <td>{item.name || '-'}</td>
          <td>
            <div className="flex space-x-1">
              <button
                onClick={() => handleEdit(index)}
                className="btn btn-ghost btn-xs"
                title="Edit Area"
              >
                <FaEdit />
              </button>
              <button
                onClick={() => handleDelete(index)}
                className="btn btn-ghost btn-xs text-error"
                title="Delete"
              >
                <FaTrash />
              </button>
            </div>
          </td>
        </tr>
      ));
    } else if (sectionType === 'sensor') {
      return value.map((item, index) => {
        // Find area name from allAreas
        const areaName = item.area 
          ? allAreas.find(a => a.id === item.area)?.name || item.area 
          : '-';
        const effectiveId = item.id || item.address;
        const displayName = item.name || effectiveId || `Sensor ${index + 1}`;
        
        return (
          <tr key={index}>
            <td>
              <div>
                <div className="font-medium">{displayName}</div>
                {item.name && effectiveId && (
                  <div className="text-xs text-base-content/60">ID: {effectiveId}</div>
                )}
              </div>
            </td>
            <td className="font-mono text-sm">{item.address || '-'}</td>
            <td>{areaName}</td>
            <td>
              <span className="badge badge-info badge-sm">{item.platform || 'gpio_onewire'}</span>
            </td>
            <td>
              <div className="flex space-x-1">
                <button
                  onClick={() => handleEdit(index)}
                  className="btn btn-ghost btn-xs"
                  title={t('outputs.edit')}
                >
                  <FaEdit />
                </button>
                <button
                  onClick={() => handleDelete(index)}
                  className="btn btn-ghost btn-xs text-error"
                  title={t('outputs.delete')}
                >
                  <FaTrash />
                </button>
              </div>
            </td>
          </tr>
        );
      });
    } else {
      return value.map((item, index) => (
        <tr key={index}>
          <td>{item.id || item.name || `Item ${index + 1}`}</td>
          <td>{JSON.stringify(item, null, 2)}</td>
          <td>
            <div className="flex space-x-1">
              <button
                onClick={() => handleEdit(index)}
                className="btn btn-ghost btn-xs"
                title="Edit Item"
              >
                <FaEdit />
              </button>
              <button
                onClick={() => handleDelete(index)}
                className="btn btn-ghost btn-xs text-error"
                title="Delete"
              >
                <FaTrash />
              </button>
            </div>
          </td>
        </tr>
      ));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">{title || 'Items'}</h3>
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
        <div className="overflow-x-auto">
          <table className="table table-zebra w-full">
            <thead>
              {renderTableHeaders()}
            </thead>
            <tbody>
              {renderTableRows()}
            </tbody>
          </table>
        </div>
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
              {editingIndex !== null ? t('settings.edit_item') : t('settings.add_new_item')}
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
                ) : (
                  <div className="alert alert-warning">
                    <span>No form available for section type: {sectionType}</span>
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
    </div>
  );
};

export default ArrayTableWidget;
