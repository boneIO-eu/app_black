import React, { useState } from 'react';
import { FaChevronDown, FaChevronRight, FaExclamationTriangle, FaPlus, FaTrash } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import ActionFields, { cleanActionFields } from '../ActionFields';
import { applyActionUpdate } from './helpers';
import {
  actionIsIncomplete,
  actionSummary,
  type ActionEntry,
} from '../helpers/actionSummary';
import type { BinarySensorEntity, CoverEntity, OutputEntity } from '@/types/config';
import type { Area, RemoteDevice } from './types';

/** The entity lists ActionFields takes, forwarded to it whole.
 *
 * Spelled out rather than Pick<ActionFieldsProps>: the copy in `types.ts` is
 * missing the three condition lists that ActionFields actually declares, so
 * deriving from it would quietly drop them. */
interface ActionEntities {
  allOutputs: OutputEntity[];
  allOutputGroups: Record<string, unknown>[];
  allCovers: CoverEntity[];
  allAreas: Area[];
  allRemoteDevices?: RemoteDevice[];
  allBinarySensors?: BinarySensorEntity[];
  allRemoteInputs?: Array<Record<string, unknown>>;
  allVirtualSwitches?: Array<Record<string, unknown>>;
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: Record<string, unknown>[];
  savedCovers?: CoverEntity[];
}

export interface ActionRowListProps {
  /** The list being edited. */
  actions: ActionEntry[];
  /** Called with the whole new list. */
  onChange: (actions: ActionEntry[]) => void;
  /** What a freshly added row starts as. */
  newAction: () => ActionEntry;
  /** Shown in place of the list when it is empty. */
  emptyText: string;
  /** Entity lists, forwarded to the editor and used for the summaries. */
  entities: ActionEntities;
  /** Mirrors boneio/schema/actions.yaml. */
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
  attemptedSubmit?: boolean;
  /** Id of the entity being edited, kept out of its own condition pickers. */
  excludeEntityId?: string;
  preferredArea?: string;
}

/**
 * A list of actions as one-line rows, each expanding in place to the editor.
 *
 * The editor card is about the same height whether the action says one thing
 * or ten, so three actions used to be a page of scrolling in which nothing was
 * legible at a glance. A row says what it does — "Turn on Living room ·
 * 2 conditions" — and opens only when there is a reason to.
 *
 * One open at a time. Two open editors is the stacked layout again, in less
 * space.
 */
const ActionRowList: React.FC<ActionRowListProps> = ({
  actions,
  onChange,
  newAction,
  emptyText,
  entities,
  actionTypeOptions,
  actionOutputOptions,
  actionCoverOptions,
  attemptedSubmit = false,
  excludeEntityId,
  preferredArea,
}) => {
  const { t } = useTranslation();
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const add = () => {
    onChange([...actions, newAction()]);
    // Open it: an action is added in order to be filled in.
    setOpenIndex(actions.length);
  };

  const remove = (index: number) => {
    onChange(actions.filter((_, i) => i !== index));
    setOpenIndex(null);
  };

  const update = (index: number, field: string, value: unknown) => {
    onChange(
      actions.map((current, i) => {
        if (i !== index) return current;
        // Switching the action type drops fields that belonged to the old one;
        // anything else is an ordinary field update, including the `__batch`
        // sentinel the shared editors use.
        return field === 'action'
          ? (cleanActionFields(String(value), current) as ActionEntry)
          : applyActionUpdate(current, field, value);
      }),
    );
  };

  return (
    <div className="space-y-1">
      {actions.length === 0 && <p className="text-sm text-base-content/60 py-1">{emptyText}</p>}

      {actions.map((action, index) => {
        const open = openIndex === index;
        const incomplete = actionIsIncomplete(action);
        return (
          <div key={index} className="rounded-lg border border-base-300 overflow-hidden">
            <div
              className={`flex items-center gap-2 px-2 py-1.5 cursor-pointer hover:bg-base-200/60 ${open ? 'bg-base-200/60' : ''}`}
              onClick={() => setOpenIndex(open ? null : index)}
            >
              {open ? <FaChevronDown className="w-2.5 h-2.5 opacity-50 shrink-0" />
                    : <FaChevronRight className="w-2.5 h-2.5 opacity-50 shrink-0" />}
              <span className="text-sm truncate grow">
                {actionSummary(action, t, entities)}
              </span>
              {incomplete && (
                <FaExclamationTriangle
                  className="w-3 h-3 text-warning shrink-0"
                  title={t('array_table_widget.incomplete_action')}
                />
              )}
              <button
                type="button"
                className="btn btn-ghost btn-xs btn-square text-error shrink-0"
                onClick={(e) => { e.stopPropagation(); remove(index); }}
                title={t('array_table_widget.delete_item')}
              >
                <FaTrash className="w-3 h-3" />
              </button>
            </div>

            {open && (
              <div className="border-t border-base-300 p-2">
                <ActionFields
                  action={action}
                  index={index}
                  onUpdate={(field, value) => update(index, field, value)}
                  onRemove={() => remove(index)}
                  actionTypeOptions={actionTypeOptions}
                  actionOutputOptions={actionOutputOptions}
                  actionCoverOptions={actionCoverOptions}
                  showValidation={attemptedSubmit}
                  excludeEntityId={excludeEntityId}
                  preferredArea={preferredArea}
                  {...entities}
                />
              </div>
            )}
          </div>
        );
      })}

      <button type="button" className="btn btn-ghost btn-sm text-primary gap-1" onClick={add}>
        <FaPlus className="w-2.5 h-2.5" />
        {t('inputs.add_action')}
      </button>
    </div>
  );
};

export default ActionRowList;
