import React, { useState, useEffect } from "react";
import { FaEdit, FaTrash, FaPlus } from "react-icons/fa";
import BinarySensorForm from './BinarySensorForm';
import EventForm from './EventForm';
import OutputForm from './OutputForm';
import OutputGroupForm from './OutputGroupForm';
import CoverForm from './CoverForm';
import ModbusDeviceForm from './ModbusDeviceForm';
import AreasForm from './AreasForm';

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
  sectionType?: 'binary_sensor' | 'event' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'other';
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
const ArrayTableWidget: React.FC<ArrayTableWidgetProps> = ({ value = [], onChange, schema, title, uiSchema, sectionType = 'other', deviceType, allBinarySensors = [], allEvents = [], allOutputs = [], allOutputGroups: _allOutputGroups = [], allCovers = [], allAreas = [] }) => {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [hasValidationErrors, setHasValidationErrors] = useState(false);
  const [interlockGroups, setInterlockGroups] = useState<string[]>([]);

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
    setEditingItem(item);
    setEditingIndex(index);
    (document.getElementById('edit_modal') as HTMLDialogElement)?.showModal();
  };

  const handleAdd = () => {
    console.log('➕ ArrayTableWidget: handleAdd called');
    setEditingIndex(null);
    setEditingItem({});
    (document.getElementById('edit_modal') as HTMLDialogElement)?.showModal();
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
    
    const newValue = [...value];
    if (editingIndex !== null) {
      newValue[editingIndex] = dataToSave;
    } else {
      newValue.push(dataToSave);
    }
    // Only call onChange when actually saving, not during editing
    console.log('🔄 ArrayTableWidget: calling onChange with:', newValue);
    onChange(newValue);
    (document.getElementById('edit_modal') as HTMLDialogElement)?.close();
    setEditingItem(null);
    setEditingIndex(null);
  };

  const handleDelete = (index: number) => {
    const newValue = value.filter((_, i) => i !== index);
    onChange(newValue);
  };

  const handleCancel = () => {
    (document.getElementById('edit_modal') as HTMLDialogElement)?.close();
    setEditingItem(null);
    setEditingIndex(null);
  };

  // Render table headers based on section type
  const renderTableHeaders = () => {
    if (sectionType === 'output') {
      return (
        <tr>
          <th>Name / ID</th>
          <th>BoneIO Output</th>
          <th>Type</th>
          <th>Restore</th>
          <th>Momentary</th>
          <th>Actions</th>
        </tr>
      );
    } else if (sectionType === 'output_group') {
      return (
        <tr>
          <th>Name / ID</th>
          <th>Member Outputs</th>
          <th>Type</th>
          <th>All On</th>
          <th>Actions</th>
        </tr>
      );
    } else if (sectionType === 'cover') {
      return (
        <tr>
          <th>Name / ID</th>
          <th>Platform</th>
          <th>Open Relay</th>
          <th>Close Relay</th>
          <th>Times</th>
          <th>Actions</th>
        </tr>
      );
    } else if (sectionType === 'modbus_devices') {
      return (
        <tr>
          <th>Name / ID</th>
          <th>Model</th>
          <th>Address</th>
          <th>Update Interval</th>
          <th>Actions</th>
        </tr>
      );
    } else if (sectionType === 'binary_sensor' || sectionType === 'event') {
      return (
        <tr>
          <th>ID/Name</th>
          <th>BoneIO INPUT</th>
          <th>Area</th>
          <th>Has Actions</th>
          <th>Actions</th>
        </tr>
      );
    } else if (sectionType === 'areas') {
      return (
        <tr>
          <th>ID</th>
          <th>Name</th>
          <th>Actions</th>
        </tr>
      );
    } else {
      return (
        <tr>
          <th>ID/Name</th>
          <th>Details</th>
          <th>Actions</th>
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
             data-tip={areAllItemsUsed() ? (sectionType === 'output' ? 'All outputs are currently in use' : 'All inputs are currently in use') : 'Add new item'}>
          <button
            onClick={handleAdd}
            className="btn btn-primary btn-sm"
            disabled={areAllItemsUsed()}
          >
            <FaPlus className="mr-2" />
            Add New
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
          <p>No items configured</p>
          <p className="text-sm">Click "Add New" to create your first item</p>
        </div>
      )}

      {/* Edit Modal */}
      <dialog id="edit_modal" className="modal">
        <div className="modal-box max-w-4xl h-[60vh] flex flex-col">
          <h3 className="font-bold text-lg mb-4">
            {editingIndex !== null ? 'Edit Item' : 'Add New Item'}
          </h3>
          
          {/* Scrollable content area */}
          <div className="flex-1 overflow-y-auto">
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
                    allCovers={allCovers}
                    allAreas={allAreas}
                    editingIndex={editingIndex}
                    onValidationChange={setHasValidationErrors}
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
                ) : (
                  <div className="alert alert-warning">
                    <span>No form available for section type: {sectionType}</span>
                  </div>
                )}
              </>
            )}
          </div>
          
          {/* Modal actions at bottom */}
          <div className="modal-action border-t border-base-300 pt-4">
            <form method="dialog">
              <button 
                type="submit" 
                className="btn btn-ghost"
                onClick={handleCancel}
              >
                Cancel
              </button>
            </form>
            <button 
              type="button" 
              onClick={handleSave} 
              className="btn btn-primary"
              disabled={hasValidationErrors}
              title={hasValidationErrors ? 'Please fix validation errors before saving' : ''}
            >
              {editingIndex !== null ? 'Save Changes' : 'Add Item'}
            </button>
          </div>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </div>
  );
};

export default ArrayTableWidget;
