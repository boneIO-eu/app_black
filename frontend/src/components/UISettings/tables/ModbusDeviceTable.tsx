import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
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

  return (
    <div>
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {items.map((item, index) => {
          const displayId = item.id || (item.address && item.model 
            ? `${item.address}_${item.model}`.toLowerCase() 
            : `Device ${index + 1}`);
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';

          return (
            <MobileCard
              key={index}
              title={item.name || displayId}
              subtitle={item.name ? displayId : undefined}
              onEdit={() => onEdit(index)}
              onDelete={() => onDelete(index)}
              fields={[
                ...(item.model ? [{ label: t('modbus.model'), value: <span className="badge badge-info badge-xs uppercase">{item.model}</span> }] : []),
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
              <Th>{t('modbus.name_id')}</Th>
              <Th>{t('modbus.model')}</Th>
              <Th>{t('modbus.address')}</Th>
              <Th>{t('modbus.update_interval')}</Th>
              <Th>{t('outputs.area')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {items.map((item, index) => {
              const displayId = item.id || (item.address && item.model 
                ? `${item.address}_${item.model}`.toLowerCase() 
                : `Device ${index + 1}`);
              const areaName = item.area 
                ? allAreas.find(a => a.id === item.area)?.name || item.area 
                : '-';

              return (
                <Tr key={index}>
                  <Td>
                    <div>
                      {item.name && <div className="font-medium">{item.name}</div>}
                      <div className={item.name ? "text-xs text-base-content/60" : ""}>{displayId}</div>
                    </div>
                  </Td>
                  <Td>
                    {item.model ? (
                      <span className="badge badge-info badge-sm uppercase">{item.model}</span>
                    ) : (
                      '-'
                    )}
                  </Td>
                  <Td>{item.address || '-'}</Td>
                  <Td>{item.update_interval ? formatTimeperiod(item.update_interval) : '-'}</Td>
                  <Td>{areaName}</Td>
                  <Td>
                    <TableActions
                      onEdit={() => onEdit(index)}
                      onDelete={() => onDelete(index)}
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
