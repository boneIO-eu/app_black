import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface Area {
  id: string;
  name: string;
}

interface OutputGroupTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const OutputGroupTable: React.FC<OutputGroupTableProps> = ({ items, allAreas, onEdit, onDelete }) => {
  const { t } = useTranslation();
  const [filter, setFilter] = useState('');
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('output_group');

  const filteredItems = useMemo(() => {
    if (!filter.trim()) return items.map((item, index) => ({ item, originalIndex: index }));
    const lowerFilter = filter.toLowerCase();
    return items
      .map((item, index) => ({ item, originalIndex: index }))
      .filter(({ item }) => {
        const outputs = Array.isArray(item.outputs) ? item.outputs : [];
        return (
          (item.name?.toLowerCase().includes(lowerFilter)) ||
          (item.id?.toLowerCase().includes(lowerFilter)) ||
          outputs.some((o: string) => o.toLowerCase().includes(lowerFilter))
        );
      });
  }, [items, filter]);

  // Sort filtered items
  const sortedItems = useMemo(() => {
    return sortItems(filteredItems, {
      name: (item: any) => (item.name || item.id || '').toLowerCase(),
      outputs: (item: any) => (Array.isArray(item.outputs) ? item.outputs.length : 0),
      output_type: (item: any) => (item.output_type || 'switch').toLowerCase(),
      area: (item: any) => {
        const area = allAreas.find(a => a.id === item.area);
        return (area?.name || item.area || '').toLowerCase();
      },
      all_on_behaviour: (item: any) => !!item.all_on_behaviour,
    });
  }, [filteredItems, sortItems, allAreas]);

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
        <ResetSortButton isSorted={isSorted} onReset={resetSort} />
      </div>

      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {sortedItems.map(({ item, originalIndex }) => {
          const outputs = Array.isArray(item.outputs) ? item.outputs : [];
          const displayName = item.name || item.id || `Group ${originalIndex + 1}`;
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';

          return (
            <MobileCard
              key={originalIndex}
              title={displayName}
              subtitle={item.name && item.id ? `ID: ${item.id}` : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                { label: t('outputs.title'), value: outputs.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {outputs.map((output: string, idx: number) => (
                      <span key={idx} className="badge badge-primary badge-xs uppercase">{output}</span>
                    ))}
                  </div>
                ) : <span className="text-warning text-xs">{t('array_table_widget.no_outputs')}</span> },
                { label: t('outputs.output_type'), value: <span className="badge badge-info badge-xs">{item.output_type || 'switch'}</span> },
                ...(areaName ? [{ label: t('outputs.area'), value: areaName }] : []),
              ]}
            />
          );
        })}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
      <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.name')} / {t('outputs.id')}</SortableHeader>
              <SortableHeader column="outputs" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.title')}</SortableHeader>
              <SortableHeader column="output_type" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.output_type')}</SortableHeader>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.area')}</SortableHeader>
              <SortableHeader column="all_on_behaviour" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('groups.all_on_behaviour')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
        <Tbody>
          {sortedItems.map(({ item, originalIndex }) => {
            const outputs = Array.isArray(item.outputs) ? item.outputs : [];
            const displayName = item.name || item.id || `Group ${originalIndex + 1}`;
            const areaName = item.area 
              ? allAreas.find(a => a.id === item.area)?.name || item.area 
              : '-';

            return (
              <Tr key={originalIndex}>
                <Td>
                  <div>
                    <div className="font-medium">{displayName}</div>
                    {item.name && item.id && (
                      <div className="text-xs text-base-content/60">ID: {item.id}</div>
                    )}
                  </div>
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {outputs.length > 0 ? (
                      outputs.map((output: string, idx: number) => (
                        <span key={idx} className="badge badge-primary badge-sm uppercase">
                          {output}
                        </span>
                      ))
                    ) : (
                      <span className="text-warning">{t('array_table_widget.no_outputs')}</span>
                    )}
                  </div>
                </Td>
                <Td>
                  {item.output_type ? (
                    <span className="badge badge-info badge-sm">{item.output_type}</span>
                  ) : (
                    <span className="badge badge-info badge-sm">switch</span>
                  )}
                </Td>
                <Td>{areaName}</Td>
                <Td>
                  {item.all_on_behaviour ? (
                    <span className="badge badge-success badge-sm">Yes</span>
                  ) : (
                    <span className="badge badge-ghost badge-sm">No</span>
                  )}
                </Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(originalIndex)}
                    onDelete={() => onDelete(originalIndex)}
                  />
                </Td>
              </Tr>
            );
          })}
        </Tbody>
      </Table>
      </div>
    </div>
  );
};

export default OutputGroupTable;
