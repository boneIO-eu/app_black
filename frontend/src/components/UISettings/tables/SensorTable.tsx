import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
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

  return (
    <div>
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {items.map((item, index) => {
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';
          const effectiveId = item.id || item.address;
          const displayName = item.name || effectiveId || `${t('array_table_widget.sensor')} ${index + 1}`;

          return (
            <MobileCard
              key={index}
              title={displayName}
              subtitle={item.name && effectiveId ? `ID: ${effectiveId}` : undefined}
              onEdit={() => onEdit(index)}
              onDelete={() => onDelete(index)}
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
              <Th>{t('sensors.name')} / {t('sensors.id')}</Th>
              <Th>{t('sensors.address')}</Th>
              <Th>{t('sensors.area')}</Th>
              <Th>{t('sensors.platform')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {items.map((item, index) => {
              const areaName = item.area 
                ? allAreas.find(a => a.id === item.area)?.name || item.area 
                : '-';
              const effectiveId = item.id || item.address;
              const displayName = item.name || effectiveId || `${t('array_table_widget.sensor')} ${index + 1}`;
              
              return (
                <Tr key={index}>
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

export default SensorTable;
