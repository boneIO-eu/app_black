import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface Area {
  id: string;
  name: string;
}

interface OutputGroupTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const OutputGroupTable: React.FC<OutputGroupTableProps> = ({ items, allAreas, onEdit, onDelete }) => {
  const { t } = useTranslation();
  console.log("all areas", items);

  return (
    <div className="overflow-x-auto">
      <Table className="table table-zebra w-full">
        <Thead>
          <Tr>
            <Th>{t('outputs.name')} / {t('outputs.id')}</Th>
            <Th>{t('outputs.title')}</Th>
            <Th>{t('outputs.output_type')}</Th>
            <Th>{t('outputs.area')}</Th>
            <Th>{t('groups.all_on_behaviour')}</Th>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {items.map((item, index) => {
            const outputs = Array.isArray(item.outputs) ? item.outputs : [];
            const displayName = item.name || item.id || `Group ${index + 1}`;
            const areaName = item.area 
              ? allAreas.find(a => a.id === item.area)?.name || item.area 
              : '-';

            return (
              <Tr key={index}>
                <Td>
                  <div>
                    <div className="font-medium">{displayName}</div>
                    {item.name && item.id && (
                      <div className="text-xs text-base-content/60">ID: {item.id}</div>
                    )}
                  </div>
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {outputs.length > 0 ? (
                      outputs.map((output: string, idx: number) => (
                        <span key={idx} className="badge badge-primary badge-sm uppercase">
                          {output}
                        </span>
                      ))
                    ) : (
                      <span className="text-warning">{t('array_table_widget.no_outputs')}</span>
                    )}
                  </div>
                </Td>
                <Td>
                  {item.output_type ? (
                    <span className="badge badge-info badge-sm">{item.output_type}</span>
                  ) : (
                    <span className="badge badge-info badge-sm">switch</span>
                  )}
                </Td>
                <Td>{areaName}</Td>
                <Td>
                  {item.all_on_behaviour ? (
                    <span className="badge badge-success badge-sm">Yes</span>
                  ) : (
                    <span className="badge badge-ghost badge-sm">No</span>
                  )}
                </Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(index)}
                    onDelete={() => onDelete(index)}
                  />
                </Td>
              </Tr>
            );
          })}
        </Tbody>
      </Table>
    </div>
  );
};

export default OutputGroupTable;
