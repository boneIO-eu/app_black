import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
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

  return (
    <div className="space-y-2">
      <FilterInput 
        filter={filter} 
        setFilter={setFilter} 
        totalCount={items.length} 
        filteredCount={filteredItems.length} 
      />

      <div className="overflow-x-auto">
      <Table className="table table-zebra w-full">
        <Thead>
          <Tr>
            <Th>{t('outputs.name')} / {t('outputs.id')}</Th>
            <Th>{t('outputs.title')}</Th>
            <Th>{t('outputs.output_type')}</Th>
            <Th>{t('outputs.area')}</Th>
            <Th>{t('groups.all_on_behaviour')}</Th>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {filteredItems.map(({ item, originalIndex }) => {
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
