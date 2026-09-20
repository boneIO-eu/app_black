import React, { useEffect, useMemo, useState } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '../../hooks/useTranslation';
import { TabsBox } from '@/components/ui/tabs-box';
import ActionFields, { cleanActionFields } from './ActionFields';
import { applyActionUpdate } from './ActionFields/helpers';
import AreaSelect from './widgets/AreaSelect';
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
  /** Opens straight on one of the action tabs, e.g. from a deep link. */
  initialTab?: string;
}

/**
 * Editor for one virtual switch.
 *
 * Laid out like the input forms rather than as one long page: the two action
 * lists are tabs, exactly as `single`/`double`/`long` are on an input. A
 * virtual switch is the same kind of thing — something that happens, with a
 * list of actions per case — so it should not need to be learned twice.
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
  initialTab,
}) => {
  const { t } = useTranslation();
  const validTabs = new Set<string>(['basic', ...EDGES]);
  const [activeTab, setActiveTab] = useState<string>(
    initialTab && validTabs.has(initialTab) ? initialTab : 'basic',
  );

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
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-semibold">{t(`virtual_switch.${edge}_actions`)}</h3>
          <button
            type="button"
            className="btn btn-primary btn-sm"
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
        </div>

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
          <div className="text-center py-8 text-base-content/60">
            <p>{t(`virtual_switch.${edge}_empty`)}</p>
            <p className="text-sm">{t('event_form.click_add_action')}</p>
          </div>
        )}
      </div>
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

      <TabsBox
        name="virtual_switch_tabs"
        activeTab={activeTab}
        onTabChange={setActiveTab}
        tabs={[
          {
            id: 'basic',
            label: t('settings.basic_settings'),
            content: (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('outputs.display_name')}</span>
                    </label>
                    <input
                      type="text"
                      className="input w-full"
                      value={data.name || ''}
                      onChange={(e) => updateField('name', e.target.value)}
                    />
                    <label className="label">
                      <span className="label-text-alt">{t('common.optional')}</span>
                    </label>
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">ID</span>
                    </label>
                    <input
                      type="text"
                      className="input w-full font-mono"
                      value={data.id || ''}
                      onChange={(e) => updateField('id', sanitizeId(e.target.value))}
                    />
                    <label className="label">
                      <span className="label-text-alt">{t('virtual_switch.id_hint')}</span>
                    </label>
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('virtual_switch.icon')}</span>
                    </label>
                    <input
                      type="text"
                      className="input w-full font-mono"
                      placeholder="mdi:weather-night"
                      value={data.icon || ''}
                      onChange={(e) => updateField('icon', e.target.value)}
                    />
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('virtual_switch.area')}</span>
                    </label>
                    <AreaSelect
                      value={data.area || ''}
                      areas={allAreas}
                      onChange={(value) => updateField('area', value)}
                    />
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-6">
                  <label className="label cursor-pointer gap-2">
                    <input
                      type="checkbox"
                      className="toggle toggle-sm"
                      checked={data.restore_state !== false}
                      onChange={(e) => updateField('restore_state', e.target.checked)}
                    />
                    <span className="label-text">{t('virtual_switch.restore_state')}</span>
                  </label>
                  <label className="label cursor-pointer gap-2">
                    <input
                      type="checkbox"
                      className="toggle toggle-sm"
                      checked={data.initial === true}
                      onChange={(e) => updateField('initial', e.target.checked)}
                      disabled={data.restore_state !== false}
                    />
                    <span className="label-text">{t('virtual_switch.initial_on')}</span>
                  </label>
                  <label className="label cursor-pointer gap-2">
                    <input
                      type="checkbox"
                      className="toggle toggle-sm"
                      checked={data.show_in_ha !== false}
                      onChange={(e) => updateField('show_in_ha', e.target.checked)}
                    />
                    <span className="label-text">{t('virtual_switch.show_in_ha')}</span>
                  </label>
                </div>

                <div className="alert alert-info">
                  <span className="text-sm">{t('virtual_switch.actions_hint')}</span>
                </div>
              </div>
            ),
          },
          ...EDGES.map((edge) => ({
            id: edge,
            label: t(`virtual_switch.${edge}`),
            badge: data.actions?.[edge]?.length || undefined,
            content: renderEdge(edge),
          })),
        ]}
      />
    </div>
  );
};

export default VirtualSwitchForm;
