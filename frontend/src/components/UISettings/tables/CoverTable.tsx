import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

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
            <Th>{t('covers.platform')}</Th>
            <Th>{t('covers.open_relay')}</Th>
            <Th>{t('covers.close_relay')}</Th>
            <Th>{t('covers.times')}</Th>
            <Th>{t('outputs.area')}</Th>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {filteredItems.map(({ item, originalIndex }) => {
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
                  {item.platform ? (
                    <span className="badge badge-info badge-sm">{item.platform}</span>
                  ) : (
                    '-'
                  )}
                </Td>
                <Td className="uppercase">{item.open_relay || '-'}</Td>
                <Td className="uppercase">{item.close_relay || '-'}</Td>
                <Td>
                  <div className="text-xs capitalize">
                    <div>{t('covers.open')}: {item.open_time ? `${item.open_time}ms` : '-'}</div>
                    <div>{t('covers.close')}: {item.close_time ? `${item.close_time}ms` : '-'}</div>
                    {item.tilt_duration && <div>{t('covers.tilt')}: {item.tilt_duration}ms</div>}
                    {item.actuator_activation_duration && <div>{t('covers.actuator_duration').replace(' Activation Duration', '').replace(' Aktywacji Siłownika', '')}: {item.actuator_activation_duration}ms</div>}
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
