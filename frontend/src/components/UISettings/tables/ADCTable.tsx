import React, { useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import type { AreaEntity } from '@/types/config';

interface ADCTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  allAreas?: AreaEntity[];
}

const ADCTable: React.FC<ADCTableProps> = ({ items, onEdit, onDelete, allAreas = [] }) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('adc');

  const indexedItems = useMemo(() =>
    items.map((item, index) => ({ item, originalIndex: index })),
    [items]
  );

  const sortedItems = useMemo(() => {
    return sortItems(indexedItems, {
      name: (item: any) => (item.name || item.id || item.pin || '').toLowerCase(),
      pin: (item: any) => (item.pin || '').toLowerCase(),
      filters: (item: any) => (item.filters || []).length,
    });
  }, [indexedItems, sortItems]);

  const formatFilters = (filters: any[]) => {
    if (!filters || filters.length === 0) return '-';
    return filters.map((f: any) => {
      const key = Object.keys(f)[0];
      return `${key}: ${f[key]}`;
    }).join(', ');
  };

  const getAreaName = (areaId?: string): string => {
    if (!areaId) return '-';
    const area = allAreas.find(a => a.id === areaId);
    return area?.name || areaId;
  };

  return (
    <div className="space-y-2">
      {isSorted && (
        <div className="flex justify-end">
          <ResetSortButton isSorted={isSorted} onReset={resetSort} />
        </div>
      )}
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {sortedItems.map(({ item, originalIndex }) => {
          const displayName = item.name || item.id || item.pin || `ADC ${originalIndex + 1}`;

          return (
            <MobileCard
              key={originalIndex}
              title={displayName}
              subtitle={item.pin ? `PIN: ${item.pin}${item.id ? ` · ID: ${item.id}` : ''}` : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                { label: t('adc.pin'), value: <span className="font-mono text-xs">{item.pin}</span> },
                { label: t('common.area'), value: getAreaName(item.area) },
                { label: t('adc.filters'), value: formatFilters(item.filters) },
                { label: t('adc.show_in_ha'), value: item.show_in_ha !== false ? '✓' : '✗' },
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
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('adc.name')}</SortableHeader>
              <SortableHeader column="pin" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('adc.pin')}</SortableHeader>
              <Th>{t('adc.id')}</Th>
              <Th>{t('common.area')}</Th>
              <SortableHeader column="filters" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('adc.filters')}</SortableHeader>
              <Th>{t('adc.show_in_ha')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const displayName = item.name || item.id || item.pin || `ADC ${originalIndex + 1}`;

              return (
                <Tr key={originalIndex}>
                  <Td>
                    <div className="font-medium">{displayName}</div>
                  </Td>
                  <Td className="font-mono text-sm">{item.pin || '-'}</Td>
                  <Td className="font-mono text-xs text-base-content/60">{item.id || '-'}</Td>
                  <Td className="text-sm">{getAreaName(item.area)}</Td>
                  <Td className="text-sm">{formatFilters(item.filters)}</Td>
                  <Td>
                    {item.show_in_ha !== false
                      ? <span className="badge badge-success badge-sm">HA</span>
                      : <span className="badge badge-ghost badge-sm">-</span>}
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
              );
            })}
          </Tbody>
        </Table>
      </div>
    </div>
  );
};

export default ADCTable;
