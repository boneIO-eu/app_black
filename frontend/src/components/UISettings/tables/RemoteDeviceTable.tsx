import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface RemoteDeviceTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const RemoteDeviceTable: React.FC<RemoteDeviceTableProps> = ({ items, onEdit, onDelete }) => {
  const { t } = useTranslation();

  return (
    <div className="overflow-x-auto">
      <Table className="table table-zebra w-full">
        <Thead>
          <Tr>
            <Th>{t('remote_devices.device_id')}</Th>
            <Th>{t('remote_devices.device_name')}</Th>
            <Th>{t('remote_devices.protocol')}</Th>
            <Th>{t('remote_devices.device_type')}</Th>
            <Th>{t('remote_devices.topic_prefix')}</Th>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {items.map((item, index) => (
            <Tr key={index}>
              <Td className="font-mono">{item.id || '-'}</Td>
              <Td>{item.name || '-'}</Td>
              <Td>
                <span className="badge badge-primary badge-sm">
                  {item.protocol?.toUpperCase() || 'MQTT'}
                </span>
              </Td>
              <Td>
                <span className="badge badge-outline badge-sm">
                  {item.device_type === 'boneio_black' ? 'boneIO Black' : 
                   item.device_type === 'esphome' ? 'ESPHome' : 
                   item.device_type || 'generic'}
                </span>
              </Td>
              <Td className="font-mono text-sm">{item.mqtt?.topic_prefix || '-'}</Td>
              <Td>
                <TableActions
                  onEdit={() => onEdit(index)}
                  onDelete={() => onDelete(index)}
                  editTitle={t('remote_devices.edit')}
                  deleteTitle={t('remote_devices.delete')}
                />
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </div>
  );
};

export default RemoteDeviceTable;
