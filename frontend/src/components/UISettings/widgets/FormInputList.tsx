import React from 'react';
import HelpLabel from '../components/HelpLabel';

interface FormInputListProps<T> {
  label: string;
  items: T[];
  onChange: (items: T[]) => void;
  renderItem: (item: T, index: number, updateItem: (newItem: T) => void) => React.ReactNode;
  help?: string;
  required?: boolean;
}

/**
 * Reusable list input form control.
 * Handles rendering an array of items, abstracting away the array immutability updates.
 */
export function FormInputList<T>({
  label,
  items,
  onChange,
  renderItem,
  help,
  required,
}: FormInputListProps<T>) {
  const handleUpdateItem = (index: number, newItem: T) => {
    const newItems = [...items];
    newItems[index] = newItem;
    onChange(newItems);
  };

  return (
    <div className="form-control">
      <label className="label">
        <span className="label-text font-medium">
          {label}
          {required && <span className="text-error ml-1">*</span>}
        </span>
      </label>
      <div className="space-y-2">
        {items.map((item, idx) => (
          <React.Fragment key={idx}>
            {renderItem(item, idx, (newItem: T) => handleUpdateItem(idx, newItem))}
          </React.Fragment>
        ))}
      </div>
      {help && <HelpLabel>{help}</HelpLabel>}
    </div>
  );
}
