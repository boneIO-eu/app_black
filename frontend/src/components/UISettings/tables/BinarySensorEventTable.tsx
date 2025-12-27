import React, { useState } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface Area {
  id: string;
  name: string;
}

interface BinarySensorEventTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const BinarySensorEventTable: React.FC<BinarySensorEventTableProps> = ({ 
  items, 
  allAreas, 
  onEdit, 
  onDelete 
}) => {
  const { t } = useTranslation();
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  /**
   * Check if item has any actions (for binary_sensor: pressed/released, for event: single/double/long)
   */
  const hasActions = (item: any): boolean => {
    if (!item.actions || typeof item.actions !== 'object') return false;
    
    // Check all possible action types (pressed, released, single, double, triple, long, sequences)
    const actionTypes = ['pressed', 'released', 'single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'];
    
    return actionTypes.some(type => {
      const actions = item.actions[type];
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
  const renderActionDetails = (item: any) => {
    if (!item.actions) return null;

    const actionTypes = ['pressed', 'released', 'single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'];
    const availableActions = actionTypes.filter(type => {
      const actions = item.actions[type];
      return Array.isArray(actions) && actions.length > 0;
    });

    if (availableActions.length === 0) return null;

    return (
      <div className="p-4 bg-base-200 space-y-3">
        {availableActions.map(type => {
          const actions = item.actions[type];
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
                {actions.map((action: any, idx: number) => (
                  <div key={idx} className="badge badge-primary badge-sm gap-1">
                    <span className="font-mono text-xs">{action.action}</span>
                    {action.boneio_output && <span className="opacity-70">→ {action.boneio_output}</span>}
                    {action.boneio_cover && <span className="opacity-70">→ {action.boneio_cover}</span>}
                    {action.topic && <span className="opacity-70">→ {action.topic}</span>}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="overflow-x-auto">
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
          {items.map((item, index) => {
            const areaName = item.area 
              ? allAreas.find(a => a.id === item.area)?.name || item.area 
              : '-';
            const isExpanded = expandedRows.has(index);
            const itemHasActions = hasActions(item);
            
            return (
              <React.Fragment key={index}>
                <Tr>
                  <Td className="w-8 p-2">
                    {itemHasActions && (
                      <button
                        onClick={() => toggleRow(index)}
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
                  <Td>{item.name || `${t('array_table_widget.item')} ${index + 1}`}</Td>
                  <Td className="uppercase">{item.boneio_input || '-'}</Td>
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
                      onEdit={() => onEdit(index)}
                      onDelete={() => onDelete(index)}
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
  );
};

export default BinarySensorEventTable;
