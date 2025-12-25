import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface AreasTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const AreasTable: React.FC<AreasTableProps> = ({ items, onEdit, onDelete }) => {
  const { t } = useTranslation();

  return (
    <div className="overflow-x-auto">
      <Table className="table table-zebra w-full">
        <Thead>
          <Tr>
            <Th>{t('areas.id')}</Th>
            <Th>{t('areas.name')}</Th>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {items.map((item, index) => (
            <Tr key={index}>
              <Td className="font-mono">{item.id || `area_${index + 1}`}</Td>
              <Td>{item.name || '-'}</Td>
              <Td>
                <TableActions
                  onEdit={() => onEdit(index)}
                  onDelete={() => onDelete(index)}
                  editTitle={t('array_table_widget.edit_area')}
                  deleteTitle={t('array_table_widget.delete_item')}
                />
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </div>
  );
};

export default AreasTable;
