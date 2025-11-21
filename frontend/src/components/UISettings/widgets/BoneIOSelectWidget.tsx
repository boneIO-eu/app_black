import { useCallback } from 'react';
import {
  ariaDescribedByIds,
  enumOptionsIndexForValue,
  enumOptionsValueForIndex,
  FormContextType,
  RJSFSchema,
  StrictRJSFSchema,
  WidgetProps,
} from '@rjsf/utils';

/** The `BoneIOSelectWidget` component renders a select input for BoneIO device types
 * 
 * This widget filters out duplicate enum values that differ only in case or type,
 * keeping only the preferred versions (e.g., "32X10A" over "32x10a", "Cover Mix" over "cover mix")
 *
 * @param props - The `WidgetProps` for this component
 */
export default function BoneIOSelectWidget<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any,
>({
  schema,
  id,
  options,
  required,
  disabled,
  placeholder,
  readonly,
  value,
  multiple,
  autofocus,
  onChange,
  onBlur,
  onFocus,
}: WidgetProps<T, S, F>) {
  const { enumOptions, emptyValue: optEmptyVal } = options;

  // Define preferred values for device_type and hw_version
  const preferredValues: Record<string, string[]> = {
    'device_type': ['32X10A', '24X16A', 'Cover', 'Cover Mix'],
    'version': ['0.7', '0.8']
  };

  // Determine field name from id (e.g., "root_device_type" -> "device_type")
  const fieldName = id.split('_').slice(1).join('_');
  
  // Filter enum options to only include preferred values
  const filteredOptions = (enumOptions || []).reduce((acc, option, index) => {
    const labelStr = String(option.label);
    
    // Check if this field has preferred values defined
    const preferred = preferredValues[fieldName];
    if (preferred) {
      // Only include if it matches a preferred value (case-insensitive)
      if (preferred.some(pref => pref.toLowerCase() === labelStr.toLowerCase())) {
        // Find the exact preferred version
        const preferredVersion = preferred.find(pref => pref.toLowerCase() === labelStr.toLowerCase());
        
        // Only add if we haven't already added this preferred version
        const alreadyAdded = acc.some(opt => String(opt.label) === preferredVersion);
        if (!alreadyAdded && preferredVersion) {
          acc.push({ 
            label: preferredVersion, 
            value: option.value,
            originalIndex: index 
          });
        }
      }
    } else {
      // No filtering for other fields
      acc.push({ ...option, originalIndex: index });
    }
    
    return acc;
  }, [] as Array<{ label: any; value: any; originalIndex: number }>);

  const _onChange = useCallback(
    ({ target: { value } }: React.ChangeEvent<HTMLSelectElement>) => {
      const selectedOption = filteredOptions[Number(value)];
      if (selectedOption) {
        onChange(enumOptionsValueForIndex<S>(String(selectedOption.originalIndex), enumOptions, optEmptyVal));
      }
    },
    [onChange, enumOptions, optEmptyVal, filteredOptions],
  );

  const _onBlur = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) => {
      const selectedOption = filteredOptions[Number(value)];
      if (selectedOption) {
        onBlur(id, enumOptionsValueForIndex<S>(String(selectedOption.originalIndex), enumOptions, optEmptyVal));
      }
    },
    [onBlur, id, enumOptions, optEmptyVal, filteredOptions],
  );

  const _onFocus = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) => {
      const selectedOption = filteredOptions[Number(value)];
      if (selectedOption) {
        onFocus(id, enumOptionsValueForIndex<S>(String(selectedOption.originalIndex), enumOptions, optEmptyVal));
      }
    },
    [onFocus, id, enumOptions, optEmptyVal, filteredOptions],
  );

  // Find selected value in filtered options
  const originalSelectedIndex = enumOptionsIndexForValue<S>(value, enumOptions, multiple);
  const selectedIndexInFiltered = filteredOptions.findIndex(
    opt => opt.originalIndex === Number(originalSelectedIndex)
  );

  return (
    <select
      id={id}
      name={id}
      value={selectedIndexInFiltered >= 0 ? selectedIndexInFiltered : ''}
      required={required}
      disabled={disabled || readonly}
      autoFocus={autofocus}
      className='select select-bordered w-full'
      onBlur={_onBlur}
      onFocus={_onFocus}
      onChange={_onChange}
      aria-describedby={ariaDescribedByIds(id)}
    >
      {!multiple && schema.default === undefined && (
        <option value='' disabled>
          {placeholder || 'Select...'}
        </option>
      )}
      {filteredOptions.map(({ label }, i: number) => (
        <option key={i} value={String(i)}>
          {label}
        </option>
      ))}
    </select>
  );
}
