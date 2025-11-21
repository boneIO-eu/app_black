import { useCallback } from 'react';
import {
  ariaDescribedByIds,
  FormContextType,
  RJSFSchema,
  StrictRJSFSchema,
  WidgetProps,
} from '@rjsf/utils';

/** The `OutputSelectWidget` component renders a select for choosing outputs
 * 
 * This widget dynamically populates options from the output configuration section.
 * It extracts output IDs from formContext.formData.output array.
 *
 * @param props - The `WidgetProps` for this component
 */
export default function OutputSelectWidget<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any,
>({
  id,
  required,
  disabled,
  placeholder,
  readonly,
  value,
  autofocus,
  onChange,
  onBlur,
  onFocus,
  formContext,
}: WidgetProps<T, S, F>) {
  // Extract output IDs from formContext
  const outputs = formContext?.formData?.output || [];
  const outputOptions = Array.isArray(outputs)
    ? outputs
        .filter((output: any) => output && typeof output === 'object' && output.id)
        .map((output: any) => ({
          label: output.id,
          value: output.id,
        }))
    : [];

  const _onChange = useCallback(
    ({ target: { value } }: React.ChangeEvent<HTMLSelectElement>) => {
      onChange(value === '' ? undefined : value);
    },
    [onChange],
  );

  const _onBlur = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) => {
      onBlur(id, value === '' ? undefined : value);
    },
    [onBlur, id],
  );

  const _onFocus = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) => {
      onFocus(id, value === '' ? undefined : value);
    },
    [onFocus, id],
  );

  return (
    <select
      id={id}
      name={id}
      value={value || ''}
      required={required}
      disabled={disabled || readonly}
      autoFocus={autofocus}
      className='select select-bordered w-full'
      onBlur={_onBlur}
      onFocus={_onFocus}
      onChange={_onChange}
      aria-describedby={ariaDescribedByIds(id)}
    >
      <option value=''>
        {placeholder || 'Select output...'}
      </option>
      {outputOptions.map(({ label, value: optValue }, i: number) => (
        <option key={i} value={optValue}>
          {label}
        </option>
      ))}
    </select>
  );
}
