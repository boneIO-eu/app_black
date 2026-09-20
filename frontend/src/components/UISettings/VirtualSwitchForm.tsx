import React, { useEffect, useMemo } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '../../hooks/useTranslation';
import ActionFields, { cleanActionFields } from './ActionFields';
import { applyActionUpdate } from './ActionFields/helpers';
import AreaSelect from './widgets/AreaSelect';
import { CardSection, FormField } from './ui';
import { sanitizeId } from './helpers/idValidation';
import type { CoverEntity, OutputEntity, BinarySensorEntity } from '@/types/config';
import type { RemoteDevice } from './ActionFields/types';
import {
  EDGES,
  withEdgeActions,
  type ActionEntry,
  type Edge,
  type SwitchEntry,
} from './helpers/virtualSwitchEdges';

// Mirrors boneio/schema/actions.yaml.
const ACTION_TYPE_OPTIONS = ['output', 'cover', 'virtual_switch', 'mqtt', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'];
const ACTION_OUTPUT_OPTIONS = ['TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET'];
const ACTION_COVER_OPTIONS = ['TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE'];

interface Area {
  id: string;
  name: string;
}

interface VirtualSwitchFormProps {
  data: SwitchEntry;
  onChange: (data: SwitchEntry) => void;
  // The entity lists are passed straight through to the shared action editor,
  // which types them itself; re-declaring the shapes here would only give this
  // form an opinion about entities it never reads.
  allOutputs?: OutputEntity[];
  allOutputGroups?: Record<string, unknown>[];
  allCovers?: CoverEntity[];
  allAreas?: Area[];
  allRemoteDevices?: RemoteDevice[];
  allBinarySensors?: BinarySensorEntity[];
  allRemoteInputs?: Record<string, unknown>[];
  allVirtualSwitches?: Record<string, unknown>[];
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: Record<string, unknown>[];
  savedCovers?: CoverEntity[];
  existingItems?: SwitchEntry[];
  editingIndex?: number | null;
  onValidationChange?: (hasErrors: boolean) => void;
  attemptedSubmit?: boolean;
}

/**
 * Editor for one virtual switch.
 *
 * One scrolling page: the flag's settings, then what happens when it goes on,
 * then when it goes off. The two lists sit under each other rather than behind
 * tabs because they are usually written as a pair — whatever `on_turn_on`
 * changes, `on_turn_off` is what puts it back, and checking that by memory
 * across a tab switch is how one of them ends up forgotten.
 */
const VirtualSwitchForm: React.FC<VirtualSwitchFormProps> = ({
  data,
  onChange,
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allRemoteDevices = [],
  allBinarySensors = [],
  allRemoteInputs = [],
  allVirtualSwitches = [],
  savedOutputs,
  savedOutputGroups,
  savedCovers,
  existingItems = [],
  editingIndex = null,
  onValidationChange,
  attemptedSubmit = false,
}) => {
  const { t } = useTranslation();
  const errors = useMemo(() => {
    const found: string[] = [];
    const id = (data.id || '').trim();
    if (!id) {
      found.push(t('virtual_switch.error_id_required'));
    } else if (
      existingItems.some((other, index) => index !== editingIndex && other.id === id)
    ) {
      found.push(t('virtual_switch.error_id_duplicate'));
    }

    // The runtime refuses this one at load time, but it is worth saying here:
    // the change that would run the actions is the one they are trying to make.
    for (const edge of EDGES) {
      const sets = (data.actions?.[edge] || []).some(
        (action) => action.action === 'virtual_switch' && action.boneio_virtual_switch === id,
      );
      if (sets) found.push(t('virtual_switch.error_sets_itself'));
    }
    return found;
  }, [data, existingItems, editingIndex, t]);

  useEffect(() => {
    onValidationChange?.(errors.length > 0);
  }, [errors.length, onValidationChange]);

  const updateField = (field: keyof SwitchEntry, value: unknown) => {
    onChange({ ...data, [field]: value });
  };

  const setEdge = (edge: Edge, next: ActionEntry[]) => onChange(withEdgeActions(data, edge, next));

  const renderEdge = (edge: Edge) => {
    const actions = data.actions?.[edge] || [];
    return (
      <CardSection
        key={edge}
        title={t(`virtual_switch.${edge}`)}
        description={edge === 'on_turn_on' ? t('virtual_switch.actions_hint') : undefined}
        divided
        action={
          <button
            type="button"
            className="btn btn-ghost btn-sm text-primary"
            onClick={() =>
              setEdge(edge, [
                ...actions,
                { action: 'output', action_output: edge === 'on_turn_on' ? 'ON' : 'OFF' },
              ])
            }
          >
            <FaPlus className="mr-2" />
            {t('inputs.add_action')}
          </button>
        }
      >
        <div className="space-y-3">
          {actions.length > 0 ? (
            actions.map((action, index) => (
              <ActionFields
                key={index}
                action={action}
                index={index}
                onUpdate={(field, value) =>
                  setEdge(
                    edge,
                    actions.map((current, i) => {
                      if (i !== index) return current;
                      // Switching the action type drops fields that belonged to
                      // the old one; anything else is an ordinary field update,
                      // including the `__batch` sentinel the shared editors use.
                      return field === 'action'
                        ? (cleanActionFields(value, current) as ActionEntry)
                        : applyActionUpdate(current, field, value);
                    }),
                  )
                }
                onRemove={() => setEdge(edge, actions.filter((_, i) => i !== index))}
                allOutputs={allOutputs}
                allOutputGroups={allOutputGroups}
                allCovers={allCovers}
                allAreas={allAreas}
                allRemoteDevices={allRemoteDevices}
                allBinarySensors={allBinarySensors}
                allRemoteInputs={allRemoteInputs}
                allVirtualSwitches={allVirtualSwitches}
                actionTypeOptions={ACTION_TYPE_OPTIONS}
                actionOutputOptions={ACTION_OUTPUT_OPTIONS}
                actionCoverOptions={ACTION_COVER_OPTIONS}
                showValidation={attemptedSubmit}
                savedOutputs={savedOutputs}
                savedOutputGroups={savedOutputGroups}
                savedCovers={savedCovers}
                excludeEntityId={data.id}
                preferredArea={data.area}
              />
            ))
          ) : (
            <p className="text-sm text-base-content/60">{t(`virtual_switch.${edge}_empty`)}</p>
          )}
        </div>
      </CardSection>
    );
  };

  return (
    <div className="space-y-4 py-2">
      {attemptedSubmit && errors.length > 0 && (
        <div className="alert alert-error">
          <ul className="list-disc list-inside text-sm">
            {errors.map((error) => <li key={error}>{error}</li>)}
          </ul>
        </div>
      )}

      {/* Identity. Two wide fields rather than four cramped ones: the icon and
          the area are Home Assistant cosmetics and live with the rest of that
          below, where they are not squeezed next to what a switch actually is. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <FormField label={t('outputs.display_name')} help={t('common.optional')}>
          <input
            type="text"
            className="input input-bordered input-sm w-full"
            value={data.name || ''}
            onChange={(e) => updateField('name', e.target.value)}
          />
        </FormField>
        <FormField label="ID" help={t('virtual_switch.id_hint')}>
          <input
            type="text"
            className="input input-bordered input-sm w-full font-mono"
            value={data.id || ''}
            onChange={(e) => updateField('id', sanitizeId(e.target.value))}
          />
        </FormField>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <label className="cursor-pointer flex items-center gap-2">
          <input
            type="checkbox"
            className="toggle toggle-sm"
            checked={data.restore_state !== false}
            onChange={(e) => updateField('restore_state', e.target.checked)}
          />
          <span className="text-sm">{t('virtual_switch.restore_state')}</span>
        </label>
        <label className="cursor-pointer flex items-center gap-2">
          <input
            type="checkbox"
            className="toggle toggle-sm"
            checked={data.initial === true}
            onChange={(e) => updateField('initial', e.target.checked)}
            disabled={data.restore_state !== false}
          />
          <span className={`text-sm ${data.restore_state !== false ? 'opacity-40' : ''}`}>
            {t('virtual_switch.initial_on')}
          </span>
        </label>
        <label className="cursor-pointer flex items-center gap-2">
          <input
            type="checkbox"
            className="toggle toggle-sm"
            checked={data.show_in_ha !== false}
            onChange={(e) => updateField('show_in_ha', e.target.checked)}
          />
          <span className="text-sm">{t('virtual_switch.show_in_ha')}</span>
        </label>
      </div>

      {/* The icon and the area are discovery fields and nothing else reads
          them, so they are here rather than at the top — and not here at all
          when the switch is not announced. */}
      {data.show_in_ha !== false && (
        <CardSection title={t('virtual_switch.section_ha')} divided>
          <div className="space-y-3">
            <FormField label={t('virtual_switch.icon')} className="sm:max-w-xs">
              <input
                type="text"
                className="input input-bordered input-sm w-full font-mono"
                placeholder="mdi:weather-night"
                value={data.icon || ''}
                onChange={(e) => updateField('icon', e.target.value)}
              />
            </FormField>
            {/* AreaSelect's own label and hint are turned off and FormField's
                used instead, so the two fields in this group are labelled the
                same way; on its own it renders "Area" above "Area / Room" in a
                different size. Width-capped because its chips are a hardcoded
                two columns: across the whole dialog they stop reading as chips
                and start reading as a menu. */}
            <FormField label={t('virtual_switch.area')} help={t('outputs.area_hint')} className="sm:max-w-md">
              <AreaSelect
                value={data.area || ''}
                areas={allAreas}
                onChange={(value) => updateField('area', value)}
                hideLabel
                hideHint
                compact
              />
            </FormField>
          </div>
        </CardSection>
      )}

      {EDGES.map((edge) => renderEdge(edge))}
    </div>
  );
};

export default VirtualSwitchForm;
