import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { formatActionLabel } from './helpers';

interface VirtualSwitchActionProps {
  /** The action being edited. */
  action: Record<string, unknown>;
  /** Update one field on it. */
  onUpdate: (field: string, value: unknown) => void;
  /** Translation function. */
  t: (key: string) => string;
  /** Configured virtual switches. */
  allVirtualSwitches?: Array<Record<string, unknown>>;
  /** ON / OFF / TOGGLE — the same three verbs an output takes. */
  actionOutputOptions: string[];
}

/**
 * Set a virtual switch.
 *
 * A plain select rather than the searchable entity picker the outputs use:
 * those lists run to dozens of relays across areas, while virtual switches are
 * a handful of named modes and searching through four of them is friction for
 * nothing.
 */
const VirtualSwitchAction: React.FC<VirtualSwitchActionProps> = ({
  action,
  onUpdate,
  t,
  allVirtualSwitches = [],
  actionOutputOptions,
}) => {
  // Only the three verbs a flag understands. An output's list also carries
  // brightness and colour cycling, which mean nothing here.
  const verbs = actionOutputOptions.filter((option) =>
    ['ON', 'OFF', 'TOGGLE'].includes(option),
  );

  return (
    <>
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.virtual_switch')}</span>
        </label>
        {allVirtualSwitches.length > 0 ? (
          <Select
            value={(action.boneio_virtual_switch as string) || ''}
            onValueChange={(value) => onUpdate('boneio_virtual_switch', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('event_form.select_virtual_switch')} />
            </SelectTrigger>
            <SelectContent>
              {allVirtualSwitches
                .filter((vs) => !!vs.id)
                .map((vs) => (
                  <SelectItem key={vs.id as string} value={vs.id as string}>
                    {(vs.name as string) || (vs.id as string)}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        ) : (
          <div className="alert alert-info py-2 px-3 text-xs">
            <span>{t('event_form.no_virtual_switches')}</span>
          </div>
        )}
      </div>

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.action_output')}</span>
        </label>
        <Select
          value={(action.action_output as string) || 'TOGGLE'}
          onValueChange={(value) => onUpdate('action_output', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {verbs.map((option) => (
              <SelectItem key={option} value={option}>
                {formatActionLabel(option, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
  );
};

export default VirtualSwitchAction;
