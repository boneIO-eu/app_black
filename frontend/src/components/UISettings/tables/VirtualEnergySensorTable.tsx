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

interface VirtualEnergySensorTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const VirtualEnergySensorTable: React.FC<VirtualEnergySensorTableProps> = ({ 
  items, 
  allAreas, 
  onEdit, 
  onDelete 
}) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('virtual_energy_sensor');

  const indexedItems = useMemo(() =>
    items.map((item, index) => ({ item, originalIndex: index })),
    [items]
  );

  const sortedItems = useMemo(() => {
    return sortItems(indexedItems, {
      name: (item: any) => (item.name || '').toLowerCase(),
      output_id: (item: any) => (item.output_id || '').toLowerCase(),
      sensor_type: (item: any) => (item.sensor_type || '').toLowerCase(),
      area: (item: any) => {
        const area = allAreas.find(a => a.id === item.area);
        return (area?.name || item.area || '').toLowerCase();
      },
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
          const areaName = item.area === '_same_as_output_'
            ? t('virtual_energy_sensor.same_area_as_output')
            : item.area 
              ? allAreas.find(a => a.id === item.area)?.name || item.area 
              : '';

          return (
            <MobileCard
              key={originalIndex}
              title={item.name || `Sensor ${originalIndex + 1}`}
              subtitle={item.output_id ? item.output_id.toUpperCase() : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                ...(item.sensor_type ? [{ label: t('virtual_energy_sensor.sensor_type'), value: <span className="badge badge-info badge-xs">{item.sensor_type}</span> }] : []),
                ...(areaName ? [{ label: t('virtual_energy_sensor.area'), value: areaName }] : []),
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
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('virtual_energy_sensor.name')}</SortableHeader>
              <SortableHeader column="output_id" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('virtual_energy_sensor.output_id')}</SortableHeader>
              <SortableHeader column="sensor_type" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('virtual_energy_sensor.sensor_type')}</SortableHeader>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('virtual_energy_sensor.area')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const areaName = item.area === '_same_as_output_'
                ? t('virtual_energy_sensor.same_area_as_output')
                : item.area 
                  ? allAreas.find(a => a.id === item.area)?.name || item.area 
                  : '-';
              
              return (
                <Tr key={originalIndex}>
                  <Td>{item.name || `Sensor ${originalIndex + 1}`}</Td>
                  <Td className="uppercase">{item.output_id || '-'}</Td>
                  <Td>
                    {item.sensor_type ? (
                      <span className="badge badge-info badge-sm">{item.sensor_type}</span>
                    ) : (
                      '-'
                    )}
                  </Td>
                  <Td>{areaName}</Td>
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

export default VirtualEnergySensorTable;
