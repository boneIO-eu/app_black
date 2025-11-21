import React from 'react';
import { FieldTemplateProps } from '@rjsf/utils';

/**
 * Custom field template for better DaisyUI styling
 */
const FieldTemplate: React.FC<FieldTemplateProps> = (props) => {
  const {
    id,
    classNames,
    style,
    label,
    help,
    required,
    description,
    errors,
    children,
    hidden,
    displayLabel,
    schema,
  } = props;

  if (hidden) {
    return <div style={{ display: 'none' }}>{children}</div>;
  }

  // For boolean fields (checkboxes), let the widget handle the label
  // For object fields, let ObjectFieldTemplate handle the description
  const isBoolean = schema?.type === 'boolean';
  const isObject = schema?.type === 'object';

  return (
    <div className={`form-control w-full ${classNames || ''}`} style={style}>
      {!isBoolean && displayLabel && label && (
        <label htmlFor={id} className="label">
          <span className="label-text font-medium">
            {label}
            {required && <span className="text-error ml-1">*</span>}
          </span>
        </label>
      )}
      
      <div className="w-full">
        {children}
      </div>
      
      {!isBoolean && !isObject && description && (
        <label className="label">
          <span className="label-text-alt text-base-content/70">
            {description}
          </span>
        </label>
      )}
      
      {errors && (
        <label className="label">
          <span className="label-text-alt text-error">
            {errors}
          </span>
        </label>
      )}
      
      {help && (
        <label className="label">
          <span className="label-text-alt text-info">
            {help}
          </span>
        </label>
      )}
    </div>
  );
};

export default FieldTemplate;
