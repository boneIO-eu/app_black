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

interface ModbusDeviceTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  formatTimeperiod: (ms: number) => string;
}

const ModbusDeviceTable: React.FC<ModbusDeviceTableProps> = ({ 
  items, 
  allAreas,
  onEdit, 
  onDelete,
  formatTimeperiod 
}) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('modbus_devices');

  // Wrap items with originalIndex for sorting
  const indexedItems = useMemo(() => 
    items.map((item, index) => ({ item, originalIndex: index })),
    [items]
  );

  // Sort items
  const sortedItems = useMemo(() => {
    return sortItems(indexedItems, {
      name: (item: any) => (item.name || item.id || '').toLowerCase(),
      model: (item: any) => (item.model || '').toLowerCase(),
      address: (item: any) => Number(item.address) || 0,
      update_interval: (item: any) => Number(item.update_interval) || 0,
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
          const displayId = item.id || (item.address && item.model 
            ? `${item.address}_${item.model}`.toLowerCase() 
            : `Device ${originalIndex + 1}`);
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';

          return (
            <MobileCard
              key={originalIndex}
              title={item.name || displayId}
              subtitle={item.name ? displayId : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                ...(item.model ? [{ label: t('modbus.model'), value: <span className="badge badge-info h-auto py-0.5 px-2 text-[10px] uppercase font-medium">{item.model}</span> }] : []),
                { label: t('modbus.address'), value: item.address || '-' },
                ...(item.update_interval ? [{ label: t('modbus.update_interval'), value: formatTimeperiod(item.update_interval) }] : []),
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
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('modbus.name_id')}</SortableHeader>
              <SortableHeader column="model" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('modbus.model')}</SortableHeader>
              <SortableHeader column="address" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('modbus.address')}</SortableHeader>
              <SortableHeader column="update_interval" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('modbus.update_interval')}</SortableHeader>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.area')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const displayId = item.id || (item.address && item.model 
                ? `${item.address}_${item.model}`.toLowerCase() 
                : `Device ${originalIndex + 1}`);
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
                    {item.model ? (
                      <span className="badge badge-info h-auto py-0.5 px-2 text-xs uppercase font-medium max-w-[120px] truncate" title={item.model}>
                        {item.model}
                      </span>
                    ) : (
                      '-'
                    )}
                  </Td>
                  <Td>{item.address || '-'}</Td>
                  <Td>{item.update_interval ? formatTimeperiod(item.update_interval) : '-'}</Td>
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

export default ModbusDeviceTable;
