import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
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

  return (
    <div>
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {items.map((item, index) => {
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';

          return (
            <MobileCard
              key={index}
              title={item.name || `Sensor ${index + 1}`}
              subtitle={item.output_id ? item.output_id.toUpperCase() : undefined}
              onEdit={() => onEdit(index)}
              onDelete={() => onDelete(index)}
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
              <Th>{t('virtual_energy_sensor.name')}</Th>
              <Th>{t('virtual_energy_sensor.output_id')}</Th>
              <Th>{t('virtual_energy_sensor.sensor_type')}</Th>
              <Th>{t('virtual_energy_sensor.area')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {items.map((item, index) => {
              const areaName = item.area 
                ? allAreas.find(a => a.id === item.area)?.name || item.area 
                : '-';
              
              return (
                <Tr key={index}>
                  <Td>{item.name || `Sensor ${index + 1}`}</Td>
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
                      onEdit={() => onEdit(index)}
                      onDelete={() => onDelete(index)}
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
