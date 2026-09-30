/**
 * ActionDetails - Renders expanded action details row for binary_sensor/event items.
 * Reusable component extracted from BinarySensorEventTable.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { normalizeCovers } from '../helpers/coverUtils';
import { normalizeOutputs } from '../helpers/outputUtils';
import type { AreaEntity, CoverEntity, OutputEntity, RemoteDeviceEntity } from '@/types/config';
import type { ActionCondition, ActionDef } from '../ActionFields/types';

/** A binary_sensor / event item: only its action lists are read here. */
interface ActionDetailsItem {
  actions?: Record<string, ActionDef[] | undefined>;
}

interface ActionDetailsProps {
  item: ActionDetailsItem;
  allAreas: AreaEntity[];
  allOutputs: OutputEntity[];
  allCovers: CoverEntity[];
  allRemoteDevices: RemoteDeviceEntity[];
}

/**
 * Labels and emojis for each action type.
 */
function useActionLabels() {
  const { t } = useTranslation();

  return (actionType: string): string => {
    const labels: Record<string, string> = {
      pressed: `🔽 ${t('inputs.pressed_actions')}`,
      released: `🔼 ${t('inputs.released_actions')}`,
      single: `👆 ${t('event_form.single_click')}`,
      double: `👆👆 ${t('event_form.double_click')}`,
      triple: `👆👆👆 ${t('event_form.triple_click')}`,
      long: `⏱️ ${t('event_form.long_click')}`,
      double_then_long: `👆👆⏱️ ${t('event_form.double_then_long')}`,
      single_then_long: `👆⏱️ ${t('event_form.single_then_long')}`,
      double_then_single: `👆👆👆 ${t('event_form.double_then_single')}`,
    };
    return labels[actionType] || actionType;
  };
}

/** All supported action trigger types. */
const ACTION_TYPES = ['pressed', 'released', 'single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'];

/**
 * Check if item has any configured actions.
 */
export function hasActions(item: { actions?: unknown }): boolean {
  if (!item.actions || typeof item.actions !== 'object') return false;
  const itemActions = item.actions as Record<string, unknown>;
  return ACTION_TYPES.some(type => {
    const actions = itemActions[type];
    return Array.isArray(actions) && actions.length > 0;
  });
}

/**
 * Render condition badges for an action.
 */
function ConditionBadges({ action }: { action: ActionDef }) {
  const { t } = useTranslation();
  const conditions: ActionCondition[] = [];
  let mode = 'and';

  if (action.conditions?.list?.length) {
    conditions.push(...action.conditions.list);
    mode = action.conditions.mode || 'and';
  } else if (action.condition) {
    conditions.push(action.condition);
  }

  if (conditions.length === 0) return null;

  const separator = mode === 'or' ? ` ${t('event_form.condition_mode_or').split(' ')[0]} ` : ' + ';

  const formatLabel = (cond: ActionCondition): string => {
    if (!cond?.type) return '';
    if (cond.type === 'time') {
      const parts: string[] = [];
      if (cond.after) parts.push(cond.after);
      if (cond.before) parts.push(cond.before);
      return `🕐 ${parts.join('–') || '?'}`;
    }
    if (cond.type === 'date') {
      const parts: string[] = [];
      if (cond.after) parts.push(cond.after);
      if (cond.before) parts.push(cond.before);
      return `📅 ${parts.join('–') || '?'}`;
    }
    if (cond.type === 'sun') {
      if (cond.phase) return `☀ ${t(`sun.phase_${cond.phase}`)}`;
      if (cond.above !== undefined || cond.below !== undefined) {
        const above = cond.above !== undefined ? `>${cond.above}°` : '';
        const below = cond.below !== undefined ? `<${cond.below}°` : '';
        return `☀ ${[above, below].filter(Boolean).join(' ')}`;
      }
      // Offsets arrive as seconds from the backend; minutes is what anyone
      // reading a badge wants, and the sign carries the direction.
      const offset = (value: string | number | undefined) => {
        if (value === undefined || value === null || value === '') return '';
        const minutes = typeof value === 'number'
          ? Math.round(value / 60)
          : parseInt(String(value), 10);
        if (!minutes || isNaN(minutes)) return '';
        // A leading space and a real minus sign: "Sunset-15m" reads as one word.
        return minutes > 0 ? ` +${minutes}m` : ` \u2212${Math.abs(minutes)}m`;
      };
      const parts: string[] = [];
      if (cond.after) parts.push(`${t(`sun.anchor_${cond.after}`)}${offset(cond.after_offset)}`);
      if (cond.before) parts.push(`${t(`sun.anchor_${cond.before}`)}${offset(cond.before_offset)}`);
      return `☀ ${parts.join('–') || '?'}`;
    }
    if (cond.type === 'state') {
      const entity = cond.entity_id || cond.entity || '?';
      const state = cond.state?.replace('is_', '') || '?';
      return `🔍 ${entity} ${state}`;
    }
    return cond.type;
  };

  return (
    <div className="flex items-center gap-1">
      <span className="badge badge-warning badge-xs gap-0.5 opacity-80" title={t('event_form.conditions')}>
        {conditions.map((c, i) => (
          <span key={i}>
            {i > 0 && <span className="opacity-60">{separator}</span>}
            {formatLabel(c)}
          </span>
        ))}
      </span>
    </div>
  );
}

/**
 * Resolve action target display text (output name, cover name, remote device).
 */
function resolveActionTarget(
  action: ActionDef,
  allOutputs: OutputEntity[],
  allCovers: CoverEntity[],
  allAreas: AreaEntity[],
  allRemoteDevices: RemoteDeviceEntity[],
): { target: string; verb: string; areaName: string } {
  let target = '';
  let areaName = '';

  if (action.boneio_output) {
    const normalized = normalizeOutputs(allOutputs);
    const output = normalized.find((o) => o.id === action.boneio_output);
    target = output?.name ? `${output.name} (${action.boneio_output})` : action.boneio_output;
    if (output?.area) {
      const area = allAreas.find(a => a.id === output.area);
      areaName = area?.name || output.area;
    }
  } else if (action.boneio_cover) {
    const normalized = normalizeCovers(allCovers);
    const cover = normalized.find((c) => c.id === action.boneio_cover);
    target = cover?.name ? `${cover.name} (${action.boneio_cover})` : action.boneio_cover;
    if (cover?.area) {
      const area = allAreas.find(a => a.id === cover.area);
      areaName = area?.name || cover.area;
    }
  } else if (action.topic) {
    target = action.topic;
  } else if (action.remote_device) {
    const device = allRemoteDevices.find(rd => rd.id === action.remote_device);
    const deviceName = device?.name || action.remote_device;
    let targetName = '';
    if (action.output_id) {
      const remoteOutput = device?.mqtt?.outputs?.find((o) => o.id === action.output_id);
      targetName = remoteOutput?.name || action.output_id;
    } else if (action.cover_id) {
      const remoteCover = device?.mqtt?.covers?.find((c) => c.id === action.cover_id);
      targetName = remoteCover?.name || action.cover_id;
    }
    target = targetName ? `${deviceName} → ${targetName}` : deviceName;
  }

  const verb = action.action_output || action.action_cover || '';

  return { target, verb, areaName };
}

/**
 * Renders the expanded action details panel for a binary_sensor/event item.
 */
const ActionDetails: React.FC<ActionDetailsProps> = ({ item, allAreas, allOutputs, allCovers, allRemoteDevices }) => {
  const getLabel = useActionLabels();

  if (!item.actions) return null;

  const available = ACTION_TYPES.filter(type => {
    const actions = item.actions?.[type];
    return Array.isArray(actions) && actions.length > 0;
  });

  if (available.length === 0) return null;

  return (
    <div className="divide-y divide-base-300/60">
      {available.map(type => {
        const actions = item.actions?.[type];
        return (
          <div key={type} className="grid grid-cols-1 sm:grid-cols-[10rem_1fr] gap-x-4 gap-y-1 py-2 text-xs">
            <div className="font-semibold text-base-content/70 sm:pt-0.5">{getLabel(type)}</div>
            <div className="space-y-1.5 min-w-0">
              {actions?.map((action: ActionDef, idx: number) => {
                const { target, verb, areaName } = resolveActionTarget(action, allOutputs, allCovers, allAreas, allRemoteDevices);
                return (
                  <div key={idx} className="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0">
                    <span className="badge badge-primary badge-xs shrink-0">{action.action}</span>
                    {target && (
                      <span className="text-base-content/80 break-all">{target}</span>
                    )}
                    {verb && (
                      <span className="badge badge-ghost badge-xs font-mono uppercase shrink-0">{verb}</span>
                    )}
                    {areaName && (
                      <span className="text-base-content/50 shrink-0">📍 {areaName}</span>
                    )}
                    <ConditionBadges action={action} />
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default ActionDetails;
