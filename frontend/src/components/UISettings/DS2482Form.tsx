/**
 * DS2482Form - Form for managing DS2482 1-Wire I2C bridge expanders.
 *
 * On board v1.0+, the built-in DS2482 at address 0x18 is shown as
 * read-only (non-editable). Users can add additional DS2482 devices.
 */

import React, { useEffect, useState } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { useConfig } from '../../contexts/ConfigContext';
import { sanitizeId } from './helpers/idValidation';

interface DS2482Data {
  id?: string;
  address?: string;
}

interface DS2482FormProps {
  data: DS2482Data;
  onChange: (data: DS2482Data) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  existingItems?: DS2482Data[];
  editingIndex?: number | null;
  onValidationChange?: (hasErrors: boolean) => void;
}

/** Default built-in DS2482 config for board v1.0+ */
const BUILTIN_DS2482: DS2482Data = {
  id: 'ds2482_bus',
  address: '0x18',
};

const DS2482Form: React.FC<DS2482FormProps> = ({
  data,
  onChange,
  existingItems = [],
  editingIndex,
  onValidationChange,
}) => {
  const { t } = useTranslation();
  const { ds2482Supported } = useConfig();
  const [errors, setErrors] = useState<Record<string, string>>({});

  /** Whether the current item is the built-in (non-editable) DS2482 */
  const isBuiltin =
    ds2482Supported &&
    data.address === BUILTIN_DS2482.address &&
    data.id === BUILTIN_DS2482.id;

  const handleChange = (field: string, value: string) => {
    const updated = { ...data, [field]: value };
    if (field === 'id') {
      updated.id = sanitizeId(value);
    }
    onChange(updated);
  };

  // Validate form
  useEffect(() => {
    const newErrors: Record<string, string> = {};

    if (!data.id) {
      newErrors.id = 'id_required';
    }

    if (!data.address) {
      newErrors.address = 'address_required';
    }

    // Check for duplicate IDs
    if (data.id) {
      const duplicateIndex = existingItems.findIndex(
        (item, idx) => item.id === data.id && idx !== editingIndex
      );
      if (duplicateIndex !== -1) {
        newErrors.id = 'duplicate_id';
      }
    }

    setErrors(newErrors);
    onValidationChange?.(Object.keys(newErrors).length > 0);
  }, [data, existingItems, editingIndex, onValidationChange]);

  return (
    <div className="space-y-4">
      {isBuiltin && (
        <div className="alert alert-info text-sm">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{t('ds2482.builtin_info')}</span>
        </div>
      )}

      {/* ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('ds2482.id')}</span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full font-mono ${errors.id ? 'input-error' : ''}`}
          value={data.id || ''}
          onChange={(e) => handleChange('id', e.target.value)}
          placeholder="ds2482_bus"
          disabled={isBuiltin}
        />
        {errors.id && (
          <label className="label">
            <span className="label-text-alt text-error">{t(`ds2482.errors.${errors.id}`)}</span>
          </label>
        )}
      </div>

      {/* I2C Address */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('ds2482.address')}</span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full font-mono ${errors.address ? 'input-error' : ''}`}
          value={data.address || ''}
          onChange={(e) => handleChange('address', e.target.value)}
          placeholder="0x18"
          disabled={isBuiltin}
        />
        <label className="label">
          <span className="label-text-alt">{t('ds2482.address_hint')}</span>
        </label>
        {errors.address && (
          <label className="label">
            <span className="label-text-alt text-error">{t(`ds2482.errors.${errors.address}`)}</span>
          </label>
        )}
      </div>
    </div>
  );
};

export default DS2482Form;
