import { useCallback } from 'react';
import {
  ariaDescribedByIds,
  FormContextType,
  RJSFSchema,
  StrictRJSFSchema,
  WidgetProps,
} from '@rjsf/utils';

interface Area {
  id: string;
  name: string;
}

/** The `AreaSelectWidget` component renders a select input for choosing areas
 *
 * Features:
 * - Reads available areas from formContext.areas
 * - Shows area name in dropdown, stores area id as value
 * - Supports optional "No area" selection
 *
 * @param props - The `WidgetProps` for this component
 */
export default function AreaSelectWidget<
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
  // Get areas from formContext
  const areas: Area[] = (formContext as any)?.areas || [];

  const _onChange = useCallback(
    ({ target: { value } }: React.ChangeEvent<HTMLSelectElement>) => {
      onChange(value || undefined);
    },
    [onChange],
  );

  const _onBlur = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) => {
      onBlur(id, value || undefined);
    },
    [onBlur, id],
  );

  const _onFocus = useCallback(
    ({ target: { value } }: React.FocusEvent<HTMLSelectElement>) => {
      onFocus(id, value || undefined);
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
        {placeholder || 'No area (main device)'}
      </option>
      {areas.map((area) => (
        <option key={area.id} value={area.id}>
          {area.name}
        </option>
      ))}
    </select>
  );
}

