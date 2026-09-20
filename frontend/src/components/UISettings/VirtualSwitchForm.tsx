import React, { useEffect, useMemo } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import ActionRowList from './ActionFields/ActionRowList';
import AreaSelect from './widgets/AreaSelect';
import { CardSection, FormField, MoreOptions } from './ui';
import { resolveId } from './helpers/slugifyId';
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
 * What the dialog asks for, in the order it matters: what this flag is called,
 * and what it does. Everything else — how it comes up after a restart, how it
 * looks in Home Assistant — is behind "more options", because each has an
 * answer that is right for almost everybody, and together they were outweighing
 * the two fields that do not.
 *
 * The two action lists sit under each other rather than behind tabs: they are
 * written as a pair, and whatever `on_turn_on` changes, `on_turn_off` is what
 * puts back.
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
  const derivedId = resolveId(data);

  const entities = {
    allOutputs,
    allOutputGroups,
    allCovers,
    allAreas,
    allRemoteDevices,
    allBinarySensors,
    allRemoteInputs,
    allVirtualSwitches,
    savedOutputs,
    savedOutputGroups,
    savedCovers,
  };

  const errors = useMemo(() => {
    const found: string[] = [];
    const id = derivedId;
    if (!id) {
      found.push(t('virtual_switch.error_name_required'));
    } else if (existingItems.some((other, index) => index !== editingIndex && resolveId(other) === id)) {
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
  }, [data, derivedId, existingItems, editingIndex, t]);

  useEffect(() => {
    onValidationChange?.(errors.length > 0);
  }, [errors.length, onValidationChange]);

  const updateField = (field: keyof SwitchEntry, value: unknown) => onChange({ ...data, [field]: value });
  const setEdge = (edge: Edge, next: ActionEntry[]) => onChange(withEdgeActions(data, edge, next));

  /** What the collapsed row says it holds, so it can be ruled out without
   *  being opened. */
  const moreSummary = [
    data.restore_state === false
      ? `${t('virtual_switch.initial')}: ${data.initial ? 'ON' : 'OFF'}`
      : t('virtual_switch.restored'),
    data.show_in_ha === false ? t('virtual_switch.hidden_in_ha') : 'Home Assistant',
  ].join(' · ');

  return (
    <div className="space-y-4 py-2">
      {attemptedSubmit && errors.length > 0 && (
        <div className="alert alert-error">
          <ul className="list-disc list-inside text-sm">
            {errors.map((error) => <li key={error}>{error}</li>)}
          </ul>
        </div>
      )}

      {/* Name and description, which is what the panel calls them and what
          config.yaml calls them. The identifier is made from the name and
          shown under it rather than typed: it is a consequence, not a
          decision, and asking for both put two spellings of the same thing
          side by side. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <FormField
          label={t('common.name')}
          help={derivedId ? `→ ${derivedId}` : t('virtual_switch.id_hint')}
        >
          <input
            type="text"
            className="input input-bordered w-full"
            value={data.name || ''}
            onChange={(e) => updateField('name', e.target.value)}
          />
        </FormField>
        <FormField label={t('common.description')} help={t('common.description_hint')}>
          <input
            type="text"
            className="input input-bordered w-full"
            value={(data.description as string) || ''}
            onChange={(e) => updateField('description', e.target.value)}
          />
        </FormField>
      </div>

      {EDGES.map((edge) => (
        <CardSection
          key={edge}
          title={t(`virtual_switch.${edge}`)}
          description={edge === 'on_turn_on' ? t('virtual_switch.actions_hint') : undefined}
          divided
        >
          <ActionRowList
            actions={data.actions?.[edge] || []}
            onChange={(next) => setEdge(edge, next)}
            newAction={() => ({ action: 'output', action_output: edge === 'on_turn_on' ? 'ON' : 'OFF' })}
            emptyText={t(`virtual_switch.${edge}_empty`)}
            entities={entities}
            actionTypeOptions={ACTION_TYPE_OPTIONS}
            actionOutputOptions={ACTION_OUTPUT_OPTIONS}
            actionCoverOptions={ACTION_COVER_OPTIONS}
            attemptedSubmit={attemptedSubmit}
            excludeEntityId={derivedId}
            preferredArea={data.area}
          />
        </CardSection>
      ))}

      <MoreOptions label={t('common.more_options')} summary={moreSummary}>
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
            them, so they are not rendered when the switch is not announced. */}
        {data.show_in_ha !== false && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <FormField label={t('virtual_switch.icon')}>
              <input
                type="text"
                className="input input-bordered w-full font-mono"
                placeholder="mdi:weather-night"
                value={data.icon || ''}
                onChange={(e) => updateField('icon', e.target.value)}
              />
            </FormField>
            {/* AreaSelect's own label and hint are turned off and FormField's
                used instead: on its own it renders "Area" above "Area / Room"
                in a different size. */}
            <FormField label={t('virtual_switch.area')} help={t('outputs.area_hint')}>
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
        )}
      </MoreOptions>
    </div>
  );
};

export default VirtualSwitchForm;
