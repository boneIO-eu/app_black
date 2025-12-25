import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface GenericTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

/**
 * Generic fallback table for unknown section types.
 */
const GenericTable: React.FC<GenericTableProps> = ({ items, onEdit, onDelete }) => {
  const { t } = useTranslation();

  return (
    <div className="overflow-x-auto">
      <Table className="table table-zebra w-full">
        <Thead>
          <Tr>
            <Th>{t('outputs.id')}/{t('outputs.name')}</Th>
            <Th>{t('array_table_widget.details')}</Th>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {items.map((item, index) => (
            <Tr key={index}>
              <Td>{item.id || item.name || `Item ${index + 1}`}</Td>
              <Td>
                <pre className="text-xs">{JSON.stringify(item, null, 2)}</pre>
              </Td>
              <Td>
                <TableActions
                  onEdit={() => onEdit(index)}
                  onDelete={() => onDelete(index)}
                />
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </div>
  );
};

export default GenericTable;
