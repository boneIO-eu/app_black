import React from 'react';
import { ObjectFieldTemplateProps } from '@rjsf/utils';

/**
 * Custom object field template for better DaisyUI styling
 */
const ObjectFieldTemplate: React.FC<ObjectFieldTemplateProps> = (props) => {
  const { title, description, properties, required } = props;

  return (
    <div className="space-y-4">
      {title && (
        <h3 className="text-lg font-semibold">
          {title}
          {required && <span className="text-error ml-1">*</span>}
        </h3>
      )}
      
      {description && (
        <p className="text-sm text-base-content/70 mb-4">
          {description}
        </p>
      )}
      
      <div className="space-y-4">
        {properties.map((element) => (
          <div key={element.name} className="w-full">
            {element.content}
          </div>
        ))}
      </div>
    </div>
  );
};

export default ObjectFieldTemplate;
