import React, { useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface AreasTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const AreasTable: React.FC<AreasTableProps> = ({ items, onEdit, onDelete }) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('areas');

  const indexedItems = useMemo(() =>
    items.map((item, index) => ({ item, originalIndex: index })),
    [items]
  );

  const sortedItems = useMemo(() => {
    return sortItems(indexedItems, {
      id: (item: any) => (item.id || '').toLowerCase(),
      name: (item: any) => (item.name || '').toLowerCase(),
    });
  }, [indexedItems, sortItems]);

  return (
    <div className="space-y-2">
      {isSorted && (
        <div className="flex justify-end">
          <ResetSortButton isSorted={isSorted} onReset={resetSort} />
        </div>
      )}
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {sortedItems.map(({ item, originalIndex }) => (
          <MobileCard
            key={originalIndex}
            title={item.name || '-'}
            subtitle={item.id || `area_${originalIndex + 1}`}
            onEdit={() => onEdit(originalIndex)}
            onDelete={() => onDelete(originalIndex)}
            fields={[]}
          />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
        <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <SortableHeader column="id" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('areas.id')}</SortableHeader>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('areas.name')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => (
              <Tr key={originalIndex}>
                <Td className="font-mono">{item.id || `area_${originalIndex + 1}`}</Td>
                <Td>{item.name || '-'}</Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(originalIndex)}
                    onDelete={() => onDelete(originalIndex)}
                    editTitle={t('array_table_widget.edit_area')}
                    deleteTitle={t('array_table_widget.delete_item')}
                  />
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </div>
    </div>
  );
};

export default AreasTable;
