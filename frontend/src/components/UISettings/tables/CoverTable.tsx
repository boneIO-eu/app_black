import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import { formatTimeperiod } from '@/utils/formatters';

interface Area {
  id: string;
  name: string;
}

interface CoverTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const CoverTable: React.FC<CoverTableProps> = ({ items, allAreas, onEdit, onDelete }) => {
  const { t } = useTranslation();
  const [filter, setFilter] = useState('');
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('cover');

  const filteredItems = useMemo(() => {
    if (!filter.trim()) return items.map((item, index) => ({ item, originalIndex: index }));
    const lowerFilter = filter.toLowerCase();
    return items
      .map((item, index) => ({ item, originalIndex: index }))
      .filter(({ item }) => 
        (item.name?.toLowerCase().includes(lowerFilter)) ||
        (item.id?.toLowerCase().includes(lowerFilter)) ||
        (item.open_relay?.toLowerCase().includes(lowerFilter)) ||
        (item.close_relay?.toLowerCase().includes(lowerFilter))
      );
  }, [items, filter]);

  // Sort filtered items
  const sortedItems = useMemo(() => {
    return sortItems(filteredItems, {
      name: (item: any) => (item.name || item.id || '').toLowerCase(),
      platform: (item: any) => (item.platform || (item.tilt_duration ? 'venetian' : 'time_based')).toLowerCase(),
      open_relay: (item: any) => (item.open_relay || '').toLowerCase(),
      close_relay: (item: any) => (item.close_relay || '').toLowerCase(),
      area: (item: any) => {
        const area = allAreas.find(a => a.id === item.area);
        return (area?.name || item.area || '').toLowerCase();
      },
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
          const displayId = item.id || (item.open_relay && item.close_relay 
            ? `cover_${item.open_relay}_${item.close_relay}`.toLowerCase() 
            : `Cover ${originalIndex + 1}`);
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';
          const platform = item.platform || (item.tilt_duration ? 'venetian' : 'time_based');

          return (
            <MobileCard
              key={originalIndex}
              title={item.name || displayId}
              subtitle={item.name ? displayId : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                { label: t('covers.platform'), value: <span className="badge badge-info badge-xs">{platform}</span> },
                { label: t('covers.open_relay'), value: item.open_relay?.toUpperCase() || '-' },
                { label: t('covers.close_relay'), value: item.close_relay?.toUpperCase() || '-' },
                { label: t('covers.times'), value: (
                  <span className="text-xs">
                    {item.open_time ? formatTimeperiod(item.open_time) : '-'} / {item.close_time ? formatTimeperiod(item.close_time) : '-'}
                  </span>
                )},
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
            <SortableHeader column="platform" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('covers.platform')}</SortableHeader>
            <SortableHeader column="open_relay" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('covers.open_relay')}</SortableHeader>
            <SortableHeader column="close_relay" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('covers.close_relay')}</SortableHeader>
            <Th>{t('covers.times')}</Th>
            <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.area')}</SortableHeader>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {sortedItems.map(({ item, originalIndex }) => {
            const displayId = item.id || (item.open_relay && item.close_relay 
              ? `cover_${item.open_relay}_${item.close_relay}`.toLowerCase() 
              : `Cover ${originalIndex + 1}`);
            const areaName = item.area 
              ? allAreas.find(a => a.id === item.area)?.name || item.area 
              : '-';

            return (
              <Tr key={originalIndex}>
                <Td>
                  <div>
                    {item.name && <div className="font-medium">{item.name}</div>}
                    <div className={item.name ? "text-xs text-base-content/60" : ""}>{displayId}</div>
                  </div>
                </Td>
                <Td>
                  <span className="badge badge-info badge-sm">
                    {item.platform || (item.tilt_duration ? 'venetian' : 'time_based')}
                  </span>
                </Td>
                <Td className="uppercase">{item.open_relay || '-'}</Td>
                <Td className="uppercase">{item.close_relay || '-'}</Td>
                <Td>
                  <div className="text-xs capitalize">
                    <div>{t('covers.open')}: {item.open_time ? formatTimeperiod(item.open_time) : '-'}</div>
                    <div>{t('covers.close')}: {item.close_time ? formatTimeperiod(item.close_time) : '-'}</div>
                    {item.tilt_duration && <div>{t('covers.tilt')}: {formatTimeperiod(item.tilt_duration)}</div>}
                    {item.actuator_activation_duration && <div>{t('covers.actuator_duration').replace(' Activation Duration', '').replace(' Aktywacji Siłownika', '')}: {formatTimeperiod(item.actuator_activation_duration)}</div>}
                  </div>
                </Td>
                <Td>{areaName}</Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(originalIndex)}
                    onDelete={() => onDelete(originalIndex)}
                    editTitle="Edit Item"
                    deleteTitle="Delete"
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

export default CoverTable;
