import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import { normalizeCovers } from '../helpers/coverUtils';
import { normalizeOutputs } from '../helpers/outputUtils';
import type { BinarySensorEntity, EventEntity, AreaEntity, OutputEntity, CoverEntity } from '@/types/config';

type BinarySensorOrEventEntity = BinarySensorEntity | EventEntity;

interface RemoteDeviceEntity {
  id: string;
  name?: string;
  mqtt?: {
    outputs?: { id: string; name?: string }[];
    covers?: { id: string; name?: string }[];
  };
}

interface BinarySensorEventTableProps {
  items: BinarySensorOrEventEntity[];
  allAreas: AreaEntity[];
  allOutputs?: OutputEntity[];
  allCovers?: CoverEntity[];
  allRemoteDevices?: RemoteDeviceEntity[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const BinarySensorEventTable: React.FC<BinarySensorEventTableProps> = ({ 
  items, 
  allAreas,
  allOutputs = [],
  allCovers = [],
  allRemoteDevices = [],
  onEdit, 
  onDelete 
}) => {
  const { t } = useTranslation();
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState('');
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('binary_sensor_event');

  /**
   * Check if item has any actions (for binary_sensor: pressed/released, for event: single/double/long)
   */
  const hasActions = (item: BinarySensorOrEventEntity): boolean => {
    if (!item.actions || typeof item.actions !== 'object') return false;
    
    // Check all possible action types (pressed, released, single, double, triple, long, sequences)
    const actionTypes = ['pressed', 'released', 'single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'];
    
    return actionTypes.some(type => {
      const actions = item.actions?.[type];
      return Array.isArray(actions) && actions.length > 0;
    });
  };

  // Filter items by name or boneio_input
  const filteredItems = useMemo(() => {
    if (!filter.trim()) return items.map((item, index) => ({ item, originalIndex: index }));
    const lowerFilter = filter.toLowerCase();
    return items
      .map((item, index) => ({ item, originalIndex: index }))
      .filter(({ item }) => 
        (item.name?.toLowerCase().includes(lowerFilter)) ||
        (item.boneio_input?.toLowerCase().includes(lowerFilter)) ||
        (item.id?.toLowerCase().includes(lowerFilter))
      );
  }, [items, filter]);

  // Sort filtered items
  const sortedItems = useMemo(() => {
    return sortItems(filteredItems, {
      name: (item: any) => (item.name || '').toLowerCase(),
      boneio_input: (item: any) => (item.boneio_input || '').toLowerCase(),
      area: (item: any) => {
        const area = allAreas.find(a => a.id === item.area);
        return (area?.name || item.area || '').toLowerCase();
      },
      has_actions: (item: any) => hasActions(item),
    });
  }, [filteredItems, sortItems, allAreas]);

  /**
   * Toggle row expansion
   */
  const toggleRow = (index: number) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedRows(newExpanded);
  };

  /**
   * Expand or collapse all rows that have actions
   */
  const toggleExpandAll = () => {
    const indicesWithActions = items
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => hasActions(item))
      .map(({ index }) => index);

    if (expandedRows.size >= indicesWithActions.length && indicesWithActions.every(i => expandedRows.has(i))) {
      setExpandedRows(new Set());
    } else {
      setExpandedRows(new Set(indicesWithActions));
    }
  };

  const allExpanded = (() => {
    const indicesWithActions = items
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => hasActions(item))
      .map(({ index }) => index);
    return indicesWithActions.length > 0 && indicesWithActions.every(i => expandedRows.has(i));
  })();

  /**
   * Format a single condition into a short label.
   */
  const formatConditionLabel = (cond: any): string => {
    if (!cond?.type) return '';
    if (cond.type === 'time') {
      const parts: string[] = [];
      if (cond.after) parts.push(`${cond.after}`);
      if (cond.before) parts.push(`${cond.before}`);
      return `🕐 ${parts.join('–') || '?'}`;
    }
    if (cond.type === 'date') {
      const parts: string[] = [];
      if (cond.after) parts.push(`${cond.after}`);
      if (cond.before) parts.push(`${cond.before}`);
      return `📅 ${parts.join('–') || '?'}`;
    }
    if (cond.type === 'state') {
      const entity = cond.entity_id || cond.entity || '?';
      const state = cond.state?.replace('is_', '') || '?';
      return `🔍 ${entity} ${state}`;
    }
    return cond.type;
  };

  /**
   * Render condition badges for an action.
   */
  const renderConditionBadges = (action: any) => {
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

    return (
      <div className="flex items-center gap-1 mt-0.5">
        <span className="badge badge-warning badge-xs gap-0.5 opacity-80" title={t('event_form.conditions')}>
          {conditions.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="opacity-60">{separator}</span>}
              {formatConditionLabel(c)}
            </span>
          ))}
        </span>
      </div>
    );
  };

  /**
   * Render action details for expanded row
   */
  const renderActionDetails = (item: BinarySensorOrEventEntity) => {
    if (!item.actions) return null;

    const actionTypes = ['pressed', 'released', 'single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'];
    const availableActions = actionTypes.filter(type => {
      const actions = item.actions?.[type];
      return Array.isArray(actions) && actions.length > 0;
    });

    if (availableActions.length === 0) return null;

    return (
      <div className="p-4 bg-base-200 space-y-3">
        {availableActions.map(type => {
          const actions = item.actions?.[type];
          // Get emoji and translation key for action type
          const getActionLabel = (actionType: string) => {
            switch (actionType) {
              case 'pressed':
                return `🔽 ${t('inputs.pressed_actions')}`;
              case 'released':
                return `🔼 ${t('inputs.released_actions')}`;
              case 'single':
                return `👆 ${t('event_form.single_click')}`;
              case 'double':
                return `👆👆 ${t('event_form.double_click')}`;
              case 'triple':
                return `👆👆👆 ${t('event_form.triple_click')}`;
              case 'long':
                return `⏱️ ${t('event_form.long_click')}`;
              case 'double_then_long':
                return `👆👆⏱️ ${t('event_form.double_then_long')}`;
              case 'single_then_long':
                return `👆⏱️ ${t('event_form.single_then_long')}`;
              case 'double_then_single':
                return `👆👆👆 ${t('event_form.double_then_single')}`;
              default:
                return actionType;
            }
          };

          return (
            <div key={type} className="space-y-1">
              <div className="font-semibold text-sm">
                {getActionLabel(type)}
              </div>
              <div className="flex flex-wrap gap-2">
                {actions?.map((action, idx: number) => {
                  // Build action details string
                  const actionDetails = [];
                  
                  // Add target (output/cover/topic/remote device)
                  let targetAreaName = '';
                  if (action.boneio_output) {
                    const normalizedOutputs = normalizeOutputs(allOutputs as any);
                    const output = normalizedOutputs.find(o => o.id === action.boneio_output);
                    const displayText = output?.name 
                      ? `${output.name} (${action.boneio_output})` 
                      : action.boneio_output;
                    actionDetails.push(displayText);
                    if (output?.area) {
                      const area = allAreas.find(a => a.id === output.area);
                      targetAreaName = area?.name || output.area;
                    }
                  } else if (action.boneio_cover) {
                    const normalizedCovers = normalizeCovers(allCovers);
                    const cover = normalizedCovers.find(c => c.id === action.boneio_cover);
                    const displayText = cover?.name 
                      ? `${cover.name} (${action.boneio_cover})` 
                      : action.boneio_cover;
                    actionDetails.push(displayText);
                    if (cover?.area) {
                      const area = allAreas.find(a => a.id === cover.area);
                      targetAreaName = area?.name || cover.area;
                    }
                  } else if (action.topic) {
                    actionDetails.push(action.topic);
                  } else if (action.remote_device) {
                    const remoteDevice = allRemoteDevices.find(rd => rd.id === action.remote_device);
                    const deviceName = remoteDevice?.name || action.remote_device;
                    
                    // Find remote output or cover name
                    let targetName = '';
                    if (action.output_id) {
                      const remoteOutput = remoteDevice?.mqtt?.outputs?.find(o => o.id === action.output_id);
                      targetName = remoteOutput?.name 
                        ? `${remoteOutput.name} (${action.output_id})` 
                        : action.output_id;
                    } else if (action.cover_id) {
                      const remoteCover = remoteDevice?.mqtt?.covers?.find(c => c.id === action.cover_id);
                      targetName = remoteCover?.name 
                        ? `${remoteCover.name} (${action.cover_id})` 
                        : action.cover_id;
                    }
                    
                    actionDetails.push(`${deviceName}/${targetName}`);
                  }
                  
                  // Add action type (ON/OFF/TOGGLE for outputs, OPEN/CLOSE/etc for covers)
                  if (action.action_output) {
                    actionDetails.push(action.action_output);
                  } else if (action.action_cover) {
                    actionDetails.push(action.action_cover);
                  }
                  
                  return (
                    <div key={idx} className="inline-flex flex-col">
                      <div className="badge badge-primary badge-sm gap-1">
                        <span className="font-mono text-xs">{action.action}</span>
                        {actionDetails.length > 0 && (
                          <span className="opacity-70">→ {actionDetails.join(' ')}</span>
                        )}
                        {targetAreaName && (
                          <span className="opacity-50">[{targetAreaName}]</span>
                        )}
                      </div>
                      {renderConditionBadges(action)}
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

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <FilterInput 
            filter={filter} 
            setFilter={setFilter} 
            totalCount={items.length} 
            filteredCount={sortedItems.length} 
          />
        </div>
        <button
          onClick={toggleExpandAll}
          className="btn btn-ghost btn-xs gap-1 text-base-content/60 hover:text-base-content"
          title={allExpanded ? t('inputs.collapse_all') : t('inputs.expand_all')}
        >
          <svg className={`w-3 h-3 transition-transform ${allExpanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          {allExpanded ? t('inputs.collapse_all') : t('inputs.expand_all')}
        </button>
        <ResetSortButton isSorted={isSorted} onReset={resetSort} />
      </div>

      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {sortedItems.map(({ item, originalIndex }) => {
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';
          const isExpanded = expandedRows.has(originalIndex);
          const itemHasActions = hasActions(item);

          return (
            <MobileCard
              key={originalIndex}
              title={item.name || `${t('array_table_widget.item')} ${originalIndex + 1}`}
              subtitle={item.boneio_input ? item.boneio_input.toUpperCase() : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              onClick={itemHasActions ? () => toggleRow(originalIndex) : undefined}
              fields={[
                ...(areaName ? [{ label: t('inputs.area'), value: areaName }] : []),
                { label: t('inputs.has_actions'), value: itemHasActions
                  ? <span className="badge badge-success badge-xs">{t('common.yes')}</span>
                  : <span className="badge badge-ghost badge-xs">{t('common.no')}</span>
                },
              ]}
            >
              {isExpanded && itemHasActions && renderActionDetails(item)}
            </MobileCard>
          );
        })}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
        <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <Th className="w-8"> </Th>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('inputs.id')}/{t('inputs.name')}</SortableHeader>
              <SortableHeader column="boneio_input" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('inputs.boneio_input')}</SortableHeader>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('inputs.area')}</SortableHeader>
              <SortableHeader column="has_actions" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('inputs.has_actions')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const areaName = item.area 
                ? allAreas.find(a => a.id === item.area)?.name || item.area 
                : '-';
              const isExpanded = expandedRows.has(originalIndex);
              const itemHasActions = hasActions(item);
              
              return (
                <React.Fragment key={originalIndex}>
                  <Tr>
                    <Td className="w-8 p-2">
                      {itemHasActions && (
                        <button
                          onClick={() => toggleRow(originalIndex)}
                          className="btn btn-ghost btn-xs p-1 min-h-0 h-6 w-6"
                          title={isExpanded ? 'Collapse' : 'Expand'}
                        >
                          <svg
                            className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                      )}
                    </Td>
                    <Td 
                      className={itemHasActions ? 'cursor-pointer' : ''}
                      onClick={() => itemHasActions && toggleRow(originalIndex)}
                    >
                      {item.name || `${t('array_table_widget.item')} ${originalIndex + 1}`}
                    </Td>
                    <Td 
                      className={`uppercase ${itemHasActions ? 'cursor-pointer' : ''}`}
                      onClick={() => itemHasActions && toggleRow(originalIndex)}
                    >
                      {item.boneio_input || '-'}
                    </Td>
                    <Td>{areaName}</Td>
                    <Td>
                      {itemHasActions ? (
                        <span className="badge badge-success badge-sm">{t('common.yes')}</span>
                      ) : (
                        <span className="badge badge-ghost badge-sm">{t('common.no')}</span>
                      )}
                    </Td>
                    <Td>
                      <TableActions
                        onEdit={() => onEdit(originalIndex)}
                        onDelete={() => onDelete(originalIndex)}
                        editTitle={t('array_table_widget.edit_item')}
                        deleteTitle={t('array_table_widget.delete_item')}
                      />
                    </Td>
                  </Tr>
                  {isExpanded && itemHasActions && (
                    <tr>
                      <td colSpan={6} className="p-0">
                        {renderActionDetails(item)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </Tbody>
        </Table>
      </div>
    </div>
  );
};

export default BinarySensorEventTable;
