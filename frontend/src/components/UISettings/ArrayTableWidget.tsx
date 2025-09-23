import React, { useState } from "react";
import { FaEdit, FaTrash, FaPlus } from "react-icons/fa";
import { Form } from '@rjsf/shadcn';
import validator from '@rjsf/validator-ajv8';
import { RJSFSchema, UiSchema } from "@rjsf/utils";

export interface ArrayTableWidgetProps {
  value: any[];
  onChange: (value: any[]) => void;
  schema: RJSFSchema;
  title?: string;
  uiSchema?: UiSchema;
}

/**
 * Custom table widget for array sections (e.g. event, binary_sensor) with modal editing.
 * Uses regular table with Edit buttons, @rjsf form only appears in modal.
 * This prevents automatic onChange calls during editing.
 */
const ArrayTableWidget: React.FC<ArrayTableWidgetProps> = ({ value = [], onChange, schema, title, uiSchema }) => {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [showModal, setShowModal] = useState(false);

  const handleEdit = (index: number) => {
    console.log('🔧 ArrayTableWidget: handleEdit called for index:', index);
    setEditingIndex(index);
    setEditingItem({ ...value[index] });
    setShowModal(true);
  };

  const handleAdd = () => {
    console.log('➕ ArrayTableWidget: handleAdd called');
    setEditingIndex(null);
    setEditingItem({});
    setShowModal(true);
  };

  const handleSave = (e?: any) => {
    console.log('💾 ArrayTableWidget: handleSave called, calling onChange');
    // If called from @rjsf onSubmit, e.formData contains the data
    const dataToSave = e?.formData || editingItem;
    
    const newValue = [...value];
    if (editingIndex !== null) {
      newValue[editingIndex] = dataToSave;
    } else {
      newValue.push(dataToSave);
    }
    // Only call onChange when actually saving, not during editing
    onChange(newValue);
    setShowModal(false);
    setEditingItem(null);
    setEditingIndex(null);
  };

  const handleDelete = (index: number) => {
    const newValue = value.filter((_, i) => i !== index);
    onChange(newValue);
  };

  const handleCancel = () => {
    setShowModal(false);
    setEditingItem(null);
    setEditingIndex(null);
  };
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">{title || 'Items'}</h3>
        <button
          onClick={handleAdd}
          className="btn btn-primary btn-sm"
        >
          <FaPlus className="mr-2" />
          Add New
        </button>
      </div>

      {value.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="table table-zebra w-full">
            <thead>
              <tr>
                <th>ID</th>
                <th>BoneIO Input</th>
                <th>Pin</th>
                <th>Has Actions</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {value.map((item, index) => (
                <tr key={index}>
                  <td>{item.id || `Item ${index + 1}`}</td>
                  <td>{item.boneio_input || '-'}</td>
                  <td>{item.pin || '-'}</td>
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
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-8 text-base-content/60">
          <p>No items configured</p>
          <p className="text-sm">Click "Add New" to create your first item</p>
        </div>
      )}

      {/* Edit Modal with @rjsf Form */}
      {showModal && (
        <div className="modal modal-open">
          <div className="modal-box max-w-4xl">
            <h3 className="font-bold text-lg mb-4">
              {editingIndex !== null ? 'Edit Item' : 'Add New Item'}
            </h3>
            
            {/* @rjsf Form - only renders in modal, doesn't trigger parent onChange until save */}
            <Form
              schema={(schema as any)?.items || {}}
              uiSchema={uiSchema}
              formData={editingItem}
              validator={validator}
              onChange={(e) => setEditingItem(e.formData)}
              onSubmit={handleSave}
              className="space-y-4"
            >
              <div className="modal-action">
                <button 
                  type="button" 
                  onClick={handleCancel} 
                  className="btn btn-ghost"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="btn btn-primary"
                >
                  {editingIndex !== null ? 'Save Changes' : 'Add Item'}
                </button>
              </div>
            </Form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ArrayTableWidget;
