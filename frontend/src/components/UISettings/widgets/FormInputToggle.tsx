import React from 'react';
import HelpLabel from '../components/HelpLabel';

interface FormInputToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  help?: string;
}

/**
 * Reusable toggle/checkbox form control with label and help text.
 */
export const FormInputToggle: React.FC<FormInputToggleProps> = ({
  label,
  checked,
  onChange,
  help,
}) => {
  return (
    <div className="form-control flex flex-col">
      <label className="label cursor-pointer justify-start gap-3">
        <input
          type="checkbox"
          className="toggle toggle-primary"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="label-text font-medium">{label}</span>
      </label>
      {help && <HelpLabel>{help}</HelpLabel>}
    </div>
  );
};
