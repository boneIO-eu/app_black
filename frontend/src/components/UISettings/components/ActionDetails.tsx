/**
 * ActionDetails - Renders expanded action details row for binary_sensor/event items.
 * Reusable component extracted from BinarySensorEventTable.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { normalizeCovers } from '../helpers/coverUtils';
import { normalizeOutputs } from '../helpers/outputUtils';

interface ActionDetailsProps {
  item: any;
  allAreas: any[];
  allOutputs: any[];
  allCovers: any[];
  allRemoteDevices: any[];
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
export function hasActions(item: any): boolean {
  if (!item.actions || typeof item.actions !== 'object') return false;
  return ACTION_TYPES.some(type => {
    const actions = item.actions?.[type];
    return Array.isArray(actions) && actions.length > 0;
  });
}

/**
 * Render condition badges for an action.
 */
function ConditionBadges({ action }: { action: any }) {
  const { t } = useTranslation();
  const conditions: any[] = [];
  let mode = 'and';

  if (action.conditions?.list?.length) {
    conditions.push(...action.conditions.list);
    mode = action.conditions.mode || 'and';
  } else if (action.condition) {
    conditions.push(action.condition);
  }

  if (conditions.length === 0) return null;

  const separator = mode === 'or' ? ` ${t('event_form.condition_mode_or').split(' ')[0]} ` : ' + ';

  const formatLabel = (cond: any): string => {
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
    if (cond.type === 'state') {
      const entity = cond.entity_id || cond.entity || '?';
      const state = cond.state?.replace('is_', '') || '?';
      return `🔍 ${entity} ${state}`;
    }
    return cond.type;
  };

  return (
    <div className="flex items-center gap-1 mt-0.5">
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
  action: any,
  allOutputs: any[],
  allCovers: any[],
  allAreas: any[],
  allRemoteDevices: any[],
): { details: string[]; areaName: string } {
  const details: string[] = [];
  let areaName = '';

  if (action.boneio_output) {
    const normalized = normalizeOutputs(allOutputs);
    const output = normalized.find((o: any) => o.id === action.boneio_output);
    details.push(output?.name ? `${output.name} (${action.boneio_output})` : action.boneio_output);
    if (output?.area) {
      const area = allAreas.find(a => a.id === output.area);
      areaName = area?.name || output.area;
    }
  } else if (action.boneio_cover) {
    const normalized = normalizeCovers(allCovers);
    const cover = normalized.find((c: any) => c.id === action.boneio_cover);
    details.push(cover?.name ? `${cover.name} (${action.boneio_cover})` : action.boneio_cover);
    if (cover?.area) {
      const area = allAreas.find(a => a.id === cover.area);
      areaName = area?.name || cover.area;
    }
  } else if (action.topic) {
    details.push(action.topic);
  } else if (action.remote_device) {
    const device = allRemoteDevices.find(rd => rd.id === action.remote_device);
    const deviceName = device?.name || action.remote_device;
    let targetName = '';
    if (action.output_id) {
      const remoteOutput = device?.mqtt?.outputs?.find((o: any) => o.id === action.output_id);
      targetName = remoteOutput?.name || action.output_id;
    } else if (action.cover_id) {
      const remoteCover = device?.mqtt?.covers?.find((c: any) => c.id === action.cover_id);
      targetName = remoteCover?.name || action.cover_id;
    }
    details.push(targetName ? `${deviceName} → ${targetName}` : deviceName);
  }

  if (action.action_output) details.push(action.action_output);
  else if (action.action_cover) details.push(action.action_cover);

  return { details, areaName };
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
    <div className="mt-2 space-y-2">
      {available.map(type => {
        const actions = item.actions?.[type];
        return (
          <div key={type} className="space-y-1.5">
            <div className="font-semibold text-xs text-base-content/70">{getLabel(type)}</div>
            <div className="space-y-1.5">
              {actions?.map((action: any, idx: number) => {
                const { details, areaName } = resolveActionTarget(action, allOutputs, allCovers, allAreas, allRemoteDevices);
                return (
                  <div key={idx} className="bg-base-100 rounded-lg p-2.5 text-xs space-y-1">
                    {/* Action type + target */}
                    <div className="flex items-start gap-2 min-w-0">
                      <span className="badge badge-primary badge-xs shrink-0 mt-0.5">
                        {action.action}
                      </span>
                      {details.length > 0 && (
                        <span className="text-base-content/80 break-all leading-tight">
                          {details.join(' ')}
                        </span>
                      )}
                    </div>
                    {/* Area */}
                    {areaName && (
                      <div className="text-base-content/50 pl-0.5">
                        📍 {areaName}
                      </div>
                    )}
                    {/* Conditions */}
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
