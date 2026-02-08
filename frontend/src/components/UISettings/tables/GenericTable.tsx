import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
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
    <div>
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {items.map((item, index) => (
          <MobileCard
            key={index}
            title={item.id || item.name || `Item ${index + 1}`}
            onEdit={() => onEdit(index)}
            onDelete={() => onDelete(index)}
            fields={Object.entries(item)
              .filter(([key]) => key !== 'id' && key !== 'name')
              .slice(0, 4)
              .map(([key, value]) => ({
                label: key,
                value: typeof value === 'object' ? JSON.stringify(value) : String(value ?? '-'),
              }))}
          />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
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
    </div>
  );
};

export default GenericTable;
