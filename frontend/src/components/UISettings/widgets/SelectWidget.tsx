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

/** The `SelectWidget` component renders a native select input with DaisyUI styling
 *
 * Features:
 * - Native HTML select for better accessibility and mobile UX
 * - Supports both single and multiple selection
 * - Uses DaisyUI select styling
 * - Supports required, disabled, and readonly states
 * - Proper keyboard navigation and screen reader support
 *
 * @param props - The `WidgetProps` for this component
 */
export default function SelectWidget<
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

  const _onChange = useCallback(
    ({ target: { value } }: React.ChangeEvent<HTMLSelectElement>) =>
      onChange(enumOptionsValueForIndex<S>(value, enumOptions, optEmptyVal)),
    [onChange, enumOptions, optEmptyVal],
  );

  const _onBlur = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) =>
      onBlur(id, enumOptionsValueForIndex<S>(value, enumOptions, optEmptyVal)),
    [onBlur, id, enumOptions, optEmptyVal],
  );

  const _onFocus = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) =>
      onFocus(id, enumOptionsValueForIndex<S>(value, enumOptions, optEmptyVal)),
    [onFocus, id, enumOptions, optEmptyVal],
  );

  const selectedIndexes = enumOptionsIndexForValue<S>(value, enumOptions, multiple);

  return (
    <select
      id={id}
      name={id}
      value={typeof selectedIndexes === 'undefined' ? optEmptyVal : selectedIndexes}
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
      {(enumOptions || []).map(({ label }, i: number) => (
        <option key={i} value={String(i)}>
          {label}
        </option>
      ))}
    </select>
  );
}