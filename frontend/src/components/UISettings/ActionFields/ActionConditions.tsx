import React from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { OutputEntity, CoverEntity, BinarySensorEntity, AreaEntity } from '@/types/config';
import SearchableEntityPicker from '../SearchableEntityPicker';
import type { EntityItem } from '../EntitySelectDropdown';
import { validateCondition } from './helpers';

interface SingleCondition {
  type: 'time' | 'date' | 'state';
  after?: string;
  before?: string;
  entity?: string;
  entity_id?: string;
  state?: string;
}

interface ActionConditionsProps {
  /** The current action object */
  action: any;
  /** Callback to update a field on the action */
  onUpdate: (field: string, value: any) => void;
  /** Translation function */
  t: (key: string) => string;
  /** Available outputs for state condition entity selection */
  allOutputs?: OutputEntity[];
  /** Available covers for state condition entity selection */
  allCovers?: CoverEntity[];
  /** Available binary sensors for state condition entity selection */
  allBinarySensors?: BinarySensorEntity[];
  /** Available remote inputs (binary sensors from ESPHome/CAN) for state conditions */
  allRemoteInputs?: Array<Record<string, unknown>>;
  /** Available areas for displaying area names in entity selectors */
  allAreas?: AreaEntity[];
  /** Whether to show validation errors */
  showValidation?: boolean;
  /** Entity ID to exclude from binary_sensor list (prevents self-reference loops) */
  excludeEntityId?: string;
}

const CONDITION_TYPES = ['time', 'date', 'state'] as const;
const ENTITY_TYPES = ['binary_sensor', 'cover', 'output', 'remote_output', 'remote_input'] as const;

const STATE_OPTIONS: Record<string, string[]> = {
  binary_sensor: ['is_on', 'is_off'],
  cover: ['is_open', 'is_closed'],
  output: ['is_on', 'is_off'],
  remote_output: ['is_on', 'is_off'],
  remote_input: ['is_on', 'is_off'],
};

/**
 * ActionConditions component — renders UI for configuring conditions
 * on an action (time, date, state).
 * 
 * Supports both single `condition` and multiple `conditions` with AND/OR mode.
 * The internal representation always uses `conditions` (list with mode).
 * On save, if there's exactly 1 condition it's stored as `condition` (single).
 */
const ActionConditions: React.FC<ActionConditionsProps> = ({
  action,
  onUpdate,
  t,
  allOutputs = [],
  allCovers = [],
  allBinarySensors = [],
  allRemoteInputs = [],
  allAreas = [],
  showValidation = false,
  excludeEntityId,
}) => {
  // Normalize: read from either `condition` (single) or `conditions` (multi)
  const getConditionsList = (): SingleCondition[] => {
    if (action.conditions?.list?.length) {
      return action.conditions.list;
    }
    if (action.condition) {
      return [action.condition];
    }
    return [];
  };

  const getMode = (): 'and' | 'or' => {
    return action.conditions?.mode || 'and';
  };

  const conditionsList = getConditionsList();
  const mode = getMode();
  const hasConditions = conditionsList.length > 0;

  /**
   * Updates the conditions on the action object.
   * Single condition → `condition` field; multiple → `conditions` field.
   * Uses a single batch update to avoid stale-state overwrites.
   */
  const updateConditions = (newList: SingleCondition[], newMode?: 'and' | 'or') => {
    const effectiveMode = newMode ?? mode;

    if (newList.length === 0) {
      // Remove all condition fields
      onUpdate('__batch', { condition: undefined, conditions: undefined });
    } else if (newList.length === 1) {
      // Single condition — store as `condition`
      onUpdate('__batch', { condition: newList[0], conditions: undefined });
    } else {
      // Multiple conditions — store as `conditions` with mode
      onUpdate('__batch', { conditions: { mode: effectiveMode, list: newList }, condition: undefined });
    }
  };

  const addCondition = () => {
    const newCondition: SingleCondition = { type: 'time', after: '', before: '' };
    updateConditions([...conditionsList, newCondition]);
  };

  const removeCondition = (index: number) => {
    const newList = conditionsList.filter((_, i) => i !== index);
    updateConditions(newList);
  };

  const updateSingleCondition = (index: number, field: string, value: any) => {
    const newList = [...conditionsList];
    const updated = { ...newList[index], [field]: value };

    // When changing type, reset type-specific fields
    if (field === 'type') {
      if (value === 'time') {
        delete updated.entity;
        delete updated.entity_id;
        delete updated.state;
        // Always clear — date format (MM-DD) is incompatible with time (HH:MM)
        updated.after = '';
        updated.before = '';
      } else if (value === 'date') {
        delete updated.entity;
        delete updated.entity_id;
        delete updated.state;
        // Always clear — time format (HH:MM) is incompatible with date (MM-DD)
        updated.after = '';
        updated.before = '';
      } else if (value === 'state') {
        delete updated.after;
        delete updated.before;
        updated.entity = '';
        updated.entity_id = '';
        updated.state = '';
      }
    }

    // When changing entity type, reset entity_id and state
    if (field === 'entity') {
      updated.entity_id = '';
      updated.state = '';
    }

    newList[index] = updated;
    updateConditions(newList);
  };

  /**
   * Get available entity items for SearchableEntityPicker based on entity type.
   * Returns items with id, name, area, and a badge indicating the entity type.
   * For 'output', includes both local and remote outputs (with 📡 badge).
   */
  const getEntityItems = (entityType: string): EntityItem[] => {
    switch (entityType) {
      case 'binary_sensor':
        return allBinarySensors
          .filter(bs => {
            const bsId = bs.id || bs.boneio_input || bs.name || '';
            if (!bsId) return false;
            if (excludeEntityId && bsId === excludeEntityId) return false;
            return true;
          })
          .map(bs => {
            const id = bs.id || bs.boneio_input || bs.name || '';
            return {
              id,
              name: bs.name || id,
              area: bs.area,
            };
          });
      case 'cover':
        return allCovers
          .filter(c => !!(c.id || c.open_relay))
          .map(c => {
            const id = c.id || (c.open_relay && c.close_relay
              ? `cover_${c.open_relay}_${c.close_relay}`.toLowerCase()
              : '');
            return {
              id,
              name: c.name || id,
              area: c.area,
            };
          })
          .filter(item => !!item.id);
      case 'output':
        return allOutputs
          .filter(o => !o.remote_source && (o.boneio_output || o.id))
          .map(o => {
            const effectiveId = o.id || o.boneio_output || '';
            return {
              id: effectiveId,
              name: o.name || effectiveId,
              area: o.area,
            };
          })
          .filter(item => !!item.id);
      case 'remote_output':
        return allOutputs
          .filter(o => !!o.remote_source && (o.device_id || o.id))
          .map(o => {
            const effectiveId = o.id || `${o.device_id}_${o.output_id}`;
            return {
              id: effectiveId,
              name: o.name || effectiveId,
              area: o.area,
              badge: `📡 ${o.device_id || o.remote_source}`,
              badgeClass: 'badge-info',
            };
          })
          .filter(item => !!item.id);
      case 'remote_input':
        return (allRemoteInputs || [])
          .filter((ri: Record<string, unknown>) => {
            const riId = (ri.id as string) || `${ri.device_id}_${ri.input_id}`;
            return !!riId;
          })
          .map((ri: Record<string, unknown>) => {
            const riId = (ri.id as string) || `${ri.device_id}_${ri.input_id}`;
            const deviceName = (ri._device_name as string) || (ri.device_id as string) || '';
            return {
              id: riId,
              name: (ri.name as string) || riId,
              area: ri.area as string | undefined,
              badge: deviceName ? `📡 ${deviceName}` : undefined,
              badgeClass: 'badge-info',
            };
          })
          .filter(item => !!item.id);
      default:
        return [];
    }
  };

  /**
   * Renders a single condition row.
   */
  const renderCondition = (condition: SingleCondition, index: number) => {
    const condError = showValidation ? validateCondition(condition, t) : null;

    return (
      <div key={index} className={`border rounded-lg p-3 mb-2 bg-base-200/50 ${condError ? 'border-error' : 'border-base-300'}`}>
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium">
            {t('event_form.condition')} {conditionsList.length > 1 ? `#${index + 1}` : ''}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-xs text-error"
            onClick={() => removeCondition(index)}
            title={t('event_form.remove_condition')}
          >
            <FaTrash className="w-3 h-3" />
          </button>
        </div>

        {condError && (
          <div className="alert alert-error py-1 px-3 mb-2 text-xs">
            <span>{condError}</span>
          </div>
        )}

        {/* Condition Type */}
        <div className="form-control mb-2">
          <label className="label py-1">
            <span className="label-text text-sm">{t('event_form.condition_type')}</span>
          </label>
          <Select
            value={condition.type}
            onValueChange={(value) => updateSingleCondition(index, 'type', value)}
          >
            <SelectTrigger className="w-full h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CONDITION_TYPES.map((ct) => (
                <SelectItem key={ct} value={ct}>
                  {t(`event_form.condition_type_${ct}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Time condition fields */}
        {condition.type === 'time' && (
          <div className="grid grid-cols-2 gap-2">
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text text-sm">{t('event_form.condition_after')}</span>
              </label>
              <input
                type="time"
                className={`input input-bordered input-sm w-full ${showValidation && !condition.after && !condition.before ? 'input-error' : ''}`}
                value={condition.after || ''}
                onChange={(e) => updateSingleCondition(index, 'after', e.target.value)}
                title={t('event_form.condition_time_after_hint')}
              />
            </div>
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text text-sm">{t('event_form.condition_before')}</span>
              </label>
              <input
                type="time"
                className={`input input-bordered input-sm w-full ${showValidation && !condition.after && !condition.before ? 'input-error' : ''}`}
                value={condition.before || ''}
                onChange={(e) => updateSingleCondition(index, 'before', e.target.value)}
                title={t('event_form.condition_time_before_hint')}
              />
            </div>
            <div className="col-span-2">
              <span className="text-xs opacity-60">{t('event_form.condition_midnight_crossover')}</span>
            </div>
          </div>
        )}

        {/* Date condition fields */}
        {condition.type === 'date' && (
          <div className="grid grid-cols-2 gap-2">
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text text-sm">{t('event_form.condition_after')}</span>
              </label>
              <input
                type="text"
                className={`input input-bordered input-sm w-full ${showValidation && !condition.after && !condition.before ? 'input-error' : ''}`}
                placeholder="MM-DD"
                value={condition.after || ''}
                onChange={(e) => updateSingleCondition(index, 'after', e.target.value)}
                title={t('event_form.condition_date_after_hint')}
                pattern="\d{2}-\d{2}"
              />
            </div>
            <div className="form-control">
              <label className="label py-1">
                <span className="label-text text-sm">{t('event_form.condition_before')}</span>
              </label>
              <input
                type="text"
                className={`input input-bordered input-sm w-full ${showValidation && !condition.after && !condition.before ? 'input-error' : ''}`}
                placeholder="MM-DD"
                value={condition.before || ''}
                onChange={(e) => updateSingleCondition(index, 'before', e.target.value)}
                title={t('event_form.condition_date_before_hint')}
                pattern="\d{2}-\d{2}"
              />
            </div>
            <div className="col-span-2">
              <span className="text-xs opacity-60">{t('event_form.condition_year_crossover')}</span>
            </div>
          </div>
        )}

        {/* State condition fields */}
        {condition.type === 'state' && (
          <>
            <div className="form-control mb-2">
              <label className="label py-1">
                <span className="label-text text-sm">{t('event_form.condition_entity')}</span>
              </label>
              <Select
                value={condition.entity || ''}
                onValueChange={(value) => updateSingleCondition(index, 'entity', value)}
              >
                <SelectTrigger className="w-full h-9">
                  <SelectValue placeholder={t('event_form.condition_entity')} />
                </SelectTrigger>
                <SelectContent>
                  {ENTITY_TYPES.map((et) => (
                    <SelectItem key={et} value={et}>
                      {t(`event_form.condition_entity_${et}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {condition.entity && (
              <>
                <div className="form-control mb-2">
                  <label className="label py-1">
                    <span className="label-text text-sm">{t('event_form.condition_entity_id')}</span>
                  </label>
                  {getEntityItems(condition.entity).length > 0 ? (
                  <SearchableEntityPicker
                      value={condition.entity_id || ''}
                      onChange={(value) => updateSingleCondition(index, 'entity_id', value)}
                      items={getEntityItems(condition.entity)}
                      allAreas={allAreas}
                      placeholder={t('event_form.condition_entity_id')}
                      compact
                      recentKey={`condition-${condition.entity}`}
                    />
                  ) : (condition.entity === 'remote_input' || condition.entity === 'remote_output') ? (
                    <div className="alert alert-info py-2 px-3 text-xs">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-4 h-4"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                      <span>{t(`event_form.condition_entity_${condition.entity}_empty`)}</span>
                    </div>
                  ) : (
                    <input
                      type="text"
                      className="input input-bordered input-sm w-full text-only"
                      value={condition.entity_id || ''}
                      onChange={(e) => updateSingleCondition(index, 'entity_id', e.target.value)}
                    />
                  )}
                </div>

                <div className="form-control mb-2">
                  <label className="label py-1">
                    <span className="label-text text-sm">{t('event_form.condition_state')}</span>
                  </label>
                  <Select
                    value={condition.state || ''}
                    onValueChange={(value) => updateSingleCondition(index, 'state', value)}
                  >
                    <SelectTrigger className="w-full h-9">
                      <SelectValue placeholder={t('event_form.condition_state')} />
                    </SelectTrigger>
                    <SelectContent>
                      {(STATE_OPTIONS[condition.entity] || []).map((st) => (
                        <SelectItem key={st} value={st}>
                          {t(`event_form.condition_state_${st}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}
          </>
        )}
      </div>
    );
  };

  return (
    <div className="form-control mb-3">
      <div className="divider text-xs opacity-70 my-1">{t('event_form.conditions')}</div>

      {!hasConditions ? (
        <button
          type="button"
          className="btn btn-ghost btn-sm text-primary w-full"
          onClick={addCondition}
        >
          <FaPlus className="w-3 h-3 mr-1" />
          {t('event_form.add_condition')}
        </button>
      ) : (
        <>
          {/* Mode selector — only show when there are 2+ conditions */}
          {conditionsList.length > 1 && (
            <div className="form-control mb-2">
              <label className="label py-1">
                <span className="label-text text-sm font-medium">{t('event_form.condition_mode')}</span>
              </label>
              <Select
                value={mode}
                onValueChange={(value: string) => updateConditions(conditionsList, value as 'and' | 'or')}
              >
                <SelectTrigger className="w-full h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="and">{t('event_form.condition_mode_and')}</SelectItem>
                  <SelectItem value="or">{t('event_form.condition_mode_or')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Render each condition */}
          {conditionsList.map((cond, idx) => renderCondition(cond, idx))}

          {/* Add another condition button */}
          <button
            type="button"
            className="btn btn-ghost btn-xs text-primary"
            onClick={addCondition}
          >
            <FaPlus className="w-3 h-3 mr-1" />
            {t('event_form.add_condition')}
          </button>
        </>
      )}

      {hasConditions && (
        <p className="text-xs opacity-50 mt-1">{t('event_form.condition_hint')}</p>
      )}
    </div>
  );
};

export default ActionConditions;
