import React from 'react';
import { sanitizeId } from './helpers/idValidation';
import { useTranslation } from '@/hooks/useTranslation';

interface AreasFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Areas item editing.
 * Fields: id, name
 */
const AreasForm: React.FC<AreasFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  return (
    <div className="space-y-4">
      {/* ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('areas.area_id')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.id || ''}
          onChange={(e) => handleChange('id', sanitizeId(e.target.value))}
          placeholder="living_room"
          required
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('areas.id_hint')}</span>
        </label>
      </div>

      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('areas.area_name')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder="Living Room"
          required
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('areas.name_hint')}</span>
        </label>
      </div>
    </div>
  );
};

export default AreasForm;
