import React from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface Area {
  id: string;
  name: string;
}

interface OutputTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const OutputTable: React.FC<OutputTableProps> = ({ items, allAreas, onEdit, onDelete }) => {
  const { t } = useTranslation();

  return (
    <div className="overflow-x-auto">
      <Table className="table table-zebra w-full">
        <Thead>
          <Tr>
            <Th>{t('outputs.name')} / {t('outputs.id')}</Th>
            <Th>{t('outputs.boneio_output')}</Th>
            <Th>{t('outputs.output_type')}</Th>
            <Th>{t('outputs.area')}</Th>
            <Th>{t('outputs.interlock_group')}</Th>
            <Th>{t('outputs.restore_state')}</Th>
            <Th>{t('outputs.momentary')}</Th>
            <Th>{t('outputs.actions')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {items.map((item, index) => {
            const isMomentary = item.momentary_turn_on || item.momentary_turn_off;
            const effectiveId = item.id || item.boneio_output;
            const displayName = item.name || effectiveId || `Item ${index + 1}`;
            const areaName = item.area 
              ? allAreas.find(a => a.id === item.area)?.name || item.area 
              : '-';

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
                <Td className="uppercase">{item.boneio_output || '-'}</Td>
                <Td>
                  {item.output_type ? (
                    <span className="badge badge-info badge-sm">{item.output_type}</span>
                  ) : (
                    '-'
                  )}
                </Td>
                <Td>{areaName}</Td>
                <Td>
                  {item.interlock_group ? (
                    <span className="badge badge-error badge-sm" title={`Interlock: ${item.interlock_group}`}>
                      {item.interlock_group}
                    </span>
                  ) : (
                    <span className="text-base-content/40">-</span>
                  )}
                </Td>
                <Td>
                  {item.restore_state !== undefined ? (
                    item.restore_state ? (
                      <span className="badge badge-success badge-sm">{t('common.yes')}</span>
                    ) : (
                      <span className="badge badge-ghost badge-sm">{t('common.no')}</span>
                    )
                  ) : (
                    '-'
                  )}
                </Td>
                <Td>
                  {isMomentary ? (
                    <span className="badge badge-warning badge-sm">{t('common.yes')}</span>
                  ) : (
                    <span className="badge badge-ghost badge-sm">{t('common.no')}</span>
                  )}
                </Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(index)}
                    onDelete={() => onDelete(index)}
                    editTitle={t('outputs.edit')}
                    deleteTitle={t('outputs.delete')}
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

export default OutputTable;
