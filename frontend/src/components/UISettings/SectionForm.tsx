import React from "react";
import { JSONSchema7 } from "json-schema";

export interface SectionFormProps {
  schema: JSONSchema7;
  uiSchema: any;
  formData: any;
  onChange: (data: any) => void;
  onSubmit: () => void;
  disabled?: boolean;
  children?: React.ReactNode;
}

/**
 * Renders a JSON schema-based form for a config section.
 * Wraps RJSF form with custom UI schema and logic.
 */
const SectionForm: React.FC<SectionFormProps> = ({
  formData,
  onSubmit,
  children,
}) => {
  // TODO: podłącz @rjsf/shadcn i custom widgety
  // Placeholder - tu będzie RJSF
  return (
    <form onSubmit={e => { e.preventDefault(); onSubmit(); }}>
      {/* TODO: <Form schema={schema} uiSchema={uiSchema} ... /> */}
      {children}
      <pre className="bg-base-200 p-2 mt-2 rounded text-xs overflow-x-auto">{JSON.stringify(formData, null, 2)}</pre>
    </form>
  );
};

export default SectionForm;
