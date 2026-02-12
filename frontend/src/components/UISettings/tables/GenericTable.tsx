import React, { useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface GenericTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

/**
 * Generic fallback table for unknown section types.
 */
const GenericTable: React.FC<GenericTableProps> = ({ items, onEdit, onDelete }) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('generic');

  const indexedItems = useMemo(() =>
    items.map((item, index) => ({ item, originalIndex: index })),
    [items]
  );

  const sortedItems = useMemo(() => {
    return sortItems(indexedItems, {
      name: (item: any) => (item.id || item.name || '').toLowerCase(),
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
            title={item.id || item.name || `Item ${originalIndex + 1}`}
            onEdit={() => onEdit(originalIndex)}
            onDelete={() => onDelete(originalIndex)}
            fields={Object.entries(item)
              .filter(([key]) => key !== 'id' && key !== 'name')
              .slice(0, 4)
              .map(([key, value]) => ({
                label: key,
                value: typeof value === 'object' ? JSON.stringify(value) : String(value ?? '-'),
              }))}
          />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
        <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.id')}/{t('outputs.name')}</SortableHeader>
              <Th>{t('array_table_widget.details')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => (
              <Tr key={originalIndex}>
                <Td>{item.id || item.name || `Item ${originalIndex + 1}`}</Td>
                <Td>
                  <pre className="text-xs">{JSON.stringify(item, null, 2)}</pre>
                </Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(originalIndex)}
                    onDelete={() => onDelete(originalIndex)}
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

export default GenericTable;
