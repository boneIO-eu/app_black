/**
 * BinarySensorEventTable - Table for binary_sensor, event, local_inputs, and remote_inputs.
 * Uses ActionDetails for expanded row rendering.
 */
import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import ActionDetails, { hasActions } from '../components/ActionDetails';
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

  // Detect if this is a merged view (local_inputs or remote_inputs).
  // local_inputs use _type metadata (injected during merge), remote_inputs use 'mode' from YAML schema.
  const isMergedView = items.some((item: any) => item._type || item.mode);
  const isRemoteView = items.some((item: any) => item._device_name);

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

  const toggleRow = (index: number) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(index)) newExpanded.delete(index);
    else newExpanded.add(index);
    setExpandedRows(newExpanded);
  };

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
    const indices = items.map((item, index) => ({ item, index })).filter(({ item }) => hasActions(item)).map(({ index }) => index);
    return indices.length > 0 && indices.every(i => expandedRows.has(i));
  })();

  const extraCols = (isMergedView ? 1 : 0) + (isRemoteView ? 1 : 0);

  return (
    <div className="space-y-2">
      <FilterInput filter={filter} setFilter={setFilter} totalCount={items.length} filteredCount={sortedItems.length} />
      <div className="flex items-center justify-end gap-2">
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
          const areaName = item.area ? allAreas.find(a => a.id === item.area)?.name || item.area : '';
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
                ...(isMergedView ? [{
                  label: t('common.type'),
                  value: (() => {
                    const itemType = (item as any)._type || (item as any).mode;
                    if (itemType === 'binary_sensor') return <span className="badge badge-warning badge-xs">{t('sections.binary_sensor')}</span>;
                    if (itemType === 'event') return <span className="badge badge-primary badge-xs">{t('sections.event')}</span>;
                    return '–';
                  })(),
                }] : []),
                { label: t('inputs.has_actions'), value: itemHasActions
                  ? <span className="badge badge-success badge-xs">{t('common.yes')}</span>
                  : <span className="badge badge-ghost badge-xs">{t('common.no')}</span>
                },
                { label: t('inputs.area'), value: areaName || '–' },
              ]}
            >
              {isExpanded && itemHasActions && (
                <ActionDetails item={item} allAreas={allAreas} allOutputs={allOutputs} allCovers={allCovers} allRemoteDevices={allRemoteDevices} />
              )}
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
              <SortableHeader column="boneio_input" sortConfig={sortConfig} onToggleSort={toggleSort}>{isRemoteView ? 'ID' : t('inputs.boneio_input')}</SortableHeader>
              {isMergedView && <Th>{t('common.type')}</Th>}
              {isRemoteView && <Th>{t('remote_devices.device')}</Th>}
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('inputs.area')}</SortableHeader>
              <SortableHeader column="has_actions" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('inputs.has_actions')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const areaName = item.area ? allAreas.find(a => a.id === item.area)?.name || item.area : '-';
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
                          <svg className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                      )}
                    </Td>
                    <Td className={itemHasActions ? 'cursor-pointer' : ''} onClick={() => itemHasActions && toggleRow(originalIndex)}>
                      {item.name || `${t('array_table_widget.item')} ${originalIndex + 1}`}
                    </Td>
                    <Td className={`uppercase ${itemHasActions ? 'cursor-pointer' : ''}`} onClick={() => itemHasActions && toggleRow(originalIndex)}>
                      {(item as any).boneio_input?.toUpperCase() || (item as any).id || '-'}
                    </Td>
                    {isMergedView && (
                      <Td>
                        {(() => {
                          const itemType = (item as any)._type || (item as any).mode;
                          if (itemType === 'binary_sensor') return <span className="badge badge-warning badge-sm">{t('sections.binary_sensor')}</span>;
                          if (itemType === 'event') return <span className="badge badge-primary badge-sm">{t('sections.event')}</span>;
                          return null;
                        })()}
                      </Td>
                    )}
                    {isRemoteView && (
                      <Td>
                        {(item as any)._device_name && (
                          <span className="badge badge-accent badge-sm">{(item as any)._device_name}</span>
                        )}
                      </Td>
                    )}
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
                      <td colSpan={6 + extraCols} className="p-0">
                        <ActionDetails item={item} allAreas={allAreas} allOutputs={allOutputs} allCovers={allCovers} allRemoteDevices={allRemoteDevices} />
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
