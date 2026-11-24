import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

/** A `modbus` section entry, as far as this table reads it. */
export interface ModbusBusRow {
  id?: string;
  port?: string;
  baudrate?: number | string;
  bytesize?: number | string;
  parity?: string;
  stopbits?: number | string;
}

interface ModbusBusTableProps {
  items: ModbusBusRow[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

/** "9600 8N1", with the section's defaults for what the entry leaves out. */
const lineSettings = (bus: ModbusBusRow) =>
  `${bus.baudrate ?? 9600} ${bus.bytesize ?? 8}${bus.parity ?? 'N'}${bus.stopbits ?? 1}`;

/**
 * The buses in config order, unsorted: the first one is where a device without `bus` goes.
 */
const ModbusBusTable: React.FC<ModbusBusTableProps> = ({ items, onEdit, onDelete }) => {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {items.map((item, index) => (
          <MobileCard
            key={index}
            title={item.id || `${t('modbus_config.bus')} ${index + 1}`}
            onEdit={() => onEdit(index)}
            onDelete={() => onDelete(index)}
            fields={[
              { label: t('modbus_config.port'), value: item.port || '-' },
              { label: t('modbus_config.line_settings'), value: lineSettings(item) },
            ]}
          />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
        <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <Th>{t('modbus_config.bus_id')}</Th>
              <Th>{t('modbus_config.port')}</Th>
              <Th>{t('modbus_config.line_settings')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {items.map((item, index) => (
              <Tr key={index}>
                <Td className="font-medium">{item.id || '-'}</Td>
                <Td><span className="font-mono text-xs break-all">{item.port || '-'}</span></Td>
                <Td>{lineSettings(item)}</Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(index)}
                    onDelete={() => onDelete(index)}
                    editTitle="Edit Item"
                    deleteTitle="Delete"
                  />
                </Td>
              </Tr>
            ))}
          </Tbody>
        </Table>
      </div>
    </div>
  );
};

export default ModbusBusTable;
