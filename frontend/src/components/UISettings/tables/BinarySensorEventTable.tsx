import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
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
                  if (action.boneio_output) {
                    const normalizedOutputs = normalizeOutputs(allOutputs as any);
                    const output = normalizedOutputs.find(o => o.id === action.boneio_output);
                    const displayText = output?.name 
                      ? `${output.name} (${action.boneio_output})` 
                      : action.boneio_output;
                    actionDetails.push(displayText);
                  } else if (action.boneio_cover) {
                    const normalizedCovers = normalizeCovers(allCovers);
                    const cover = normalizedCovers.find(c => c.id === action.boneio_cover);
                    const displayText = cover?.name 
                      ? `${cover.name} (${action.boneio_cover})` 
                      : action.boneio_cover;
                    actionDetails.push(displayText);
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
                    <div key={idx} className="badge badge-primary badge-sm gap-1">
                      <span className="font-mono text-xs">{action.action}</span>
                      {actionDetails.length > 0 && (
                        <span className="opacity-70">→ {actionDetails.join(' ')}</span>
                      )}
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
      <FilterInput 
        filter={filter} 
        setFilter={setFilter} 
        totalCount={items.length} 
        filteredCount={filteredItems.length} 
      />

      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {filteredItems.map(({ item, originalIndex }) => {
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
              <Th>{t('inputs.id')}/{t('inputs.name')}</Th>
              <Th>{t('inputs.boneio_input')}</Th>
              <Th>{t('inputs.area')}</Th>
              <Th>{t('inputs.has_actions')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {filteredItems.map(({ item, originalIndex }) => {
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
