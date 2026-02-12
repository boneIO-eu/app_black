import React, { useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface Area {
  id: string;
  name: string;
}

interface SensorTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const SensorTable: React.FC<SensorTableProps> = ({ items, allAreas, onEdit, onDelete }) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('sensor');

  const indexedItems = useMemo(() =>
    items.map((item, index) => ({ item, originalIndex: index })),
    [items]
  );

  const sortedItems = useMemo(() => {
    return sortItems(indexedItems, {
      name: (item: any) => (item.name || item.id || item.address || '').toLowerCase(),
      address: (item: any) => (item.address || '').toLowerCase(),
      area: (item: any) => {
        const area = allAreas.find(a => a.id === item.area);
        return (area?.name || item.area || '').toLowerCase();
      },
      platform: (item: any) => (item.platform || 'gpio_onewire').toLowerCase(),
    });
  }, [indexedItems, sortItems, allAreas]);

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
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';
          const effectiveId = item.id || item.address;
          const displayName = item.name || effectiveId || `${t('array_table_widget.sensor')} ${originalIndex + 1}`;

          return (
            <MobileCard
              key={originalIndex}
              title={displayName}
              subtitle={item.name && effectiveId ? `ID: ${effectiveId}` : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                ...(item.address ? [{ label: t('sensors.address'), value: <span className="font-mono text-xs">{item.address}</span> }] : []),
                { label: t('sensors.platform'), value: <span className="badge badge-info badge-xs">{item.platform || 'gpio_onewire'}</span> },
                ...(areaName ? [{ label: t('sensors.area'), value: areaName }] : []),
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
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('sensors.name')} / {t('sensors.id')}</SortableHeader>
              <SortableHeader column="address" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('sensors.address')}</SortableHeader>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('sensors.area')}</SortableHeader>
              <SortableHeader column="platform" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('sensors.platform')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const areaName = item.area 
                ? allAreas.find(a => a.id === item.area)?.name || item.area 
                : '-';
              const effectiveId = item.id || item.address;
              const displayName = item.name || effectiveId || `${t('array_table_widget.sensor')} ${originalIndex + 1}`;
              
              return (
                <Tr key={originalIndex}>
                  <Td>
                    <div>
                      <div className="font-medium">{displayName}</div>
                      {item.name && effectiveId && (
                        <div className="text-xs text-base-content/60">ID: {effectiveId}</div>
                      )}
                    </div>
                  </Td>
                  <Td className="font-mono text-sm">{item.address || '-'}</Td>
                  <Td>{areaName}</Td>
                  <Td>
                    <span className="badge badge-info badge-sm">{item.platform || 'gpio_onewire'}</span>
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

export default SensorTable;
