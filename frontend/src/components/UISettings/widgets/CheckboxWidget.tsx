import { useCallback } from 'react';
import { WidgetProps, StrictRJSFSchema, RJSFSchema, FormContextType } from '@rjsf/utils';

/** The `CheckboxWidget` component renders a single checkbox input with DaisyUI styling.
 *
 * Features:
 * - Simple boolean input with DaisyUI checkbox styling
 * - Handles required, disabled, and readonly states
 * - No label rendering (handled by the parent FieldTemplate)
 * - Proper onChange handling for boolean values
 * - Manages focus and blur events for accessibility
 *
 * @param props - The `WidgetProps` for this component
 */
export default function CheckboxWidget<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any,
>(props: WidgetProps<T, S, F>) {
  const {
    id,
    htmlName,
    value,
    required,
    disabled,
    hideLabel,
    label,
    readonly,
    options,
    schema,
    onChange,
    onFocus,
    onBlur,
  } = props;
  const description = options.description || schema.description;

  /** Handle focus events
   */
  const handleFocus: React.FocusEventHandler<HTMLInputElement> = useCallback(() => {
    if (onFocus) {
      onFocus(id, value);
    }
  }, [onFocus, id, value]);

  /** Handle blur events
   */
  const handleBlur: React.FocusEventHandler<HTMLInputElement> = useCallback(() => {
    if (onBlur) {
      onBlur(id, value);
    }
  }, [onBlur, id, value]);

  /** Handle change events
   *
   * @param event - The change event
   */
  const handleChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      onChange(event.target.checked);
    },
    [onChange],
  );

  const input = (
    <input
      type='checkbox'
      id={id}
      name={htmlName || id}
      checked={value}
      required={required}
      disabled={disabled || readonly}
      onChange={handleChange}
      onFocus={handleFocus}
      onBlur={handleBlur}
      className='toggle toggle-success'
    />
  );

  return hideLabel || !label ? (
    input
  ) : (
    <fieldset className="fieldset border-base-300 rounded-box w-64 border p-4">
      <legend className="fieldset-legend">{description}</legend>
      <label className='label cursor-pointer justify-start'>
        <div className='mr-2'>{input}</div>
        <span className='label-text'>
          {label}
          {required && <span className='text-error ml-1'>*</span>}
        </span>
      </label>
    </fieldset>
  );
}