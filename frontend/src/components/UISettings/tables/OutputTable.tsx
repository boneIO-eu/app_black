import React, { useState, useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
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
  const [filter, setFilter] = useState('');

  // Filter items by name, id or boneio_output
  const filteredItems = useMemo(() => {
    if (!filter.trim()) return items.map((item, index) => ({ item, originalIndex: index }));
    const lowerFilter = filter.toLowerCase();
    return items
      .map((item, index) => ({ item, originalIndex: index }))
      .filter(({ item }) => 
        (item.name?.toLowerCase().includes(lowerFilter)) ||
        (item.id?.toLowerCase().includes(lowerFilter)) ||
        (item.boneio_output?.toLowerCase().includes(lowerFilter))
      );
  }, [items, filter]);

  return (
    <div className="space-y-2">
      <FilterInput 
        filter={filter} 
        setFilter={setFilter} 
        totalCount={items.length} 
        filteredCount={filteredItems.length} 
      />

      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {filteredItems.map(({ item, originalIndex }) => {
          const isMomentary = item.momentary_turn_on || item.momentary_turn_off;
          const effectiveId = item.id || item.boneio_output;
          const displayName = item.name || effectiveId || `Item ${originalIndex + 1}`;
          const areaName = item.area 
            ? allAreas.find(a => a.id === item.area)?.name || item.area 
            : '';

          return (
            <MobileCard
              key={originalIndex}
              title={displayName}
              subtitle={item.boneio_output ? item.boneio_output.toUpperCase() : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                ...(item.output_type ? [{ label: t('outputs.output_type'), value: <span className="badge badge-info badge-xs">{item.output_type}</span> }] : []),
                ...(areaName ? [{ label: t('outputs.area'), value: areaName }] : []),
                ...(item.interlock_group ? [{ label: t('outputs.interlock_group'), value: <span className="badge badge-error badge-xs">{item.interlock_group}</span> }] : []),
                { label: t('outputs.restore_state'), value: item.restore_state ? <span className="badge badge-success badge-xs">{t('common.yes')}</span> : <span className="badge badge-ghost badge-xs">{t('common.no')}</span> },
                ...(isMomentary ? [{ label: t('outputs.momentary'), value: <span className="badge badge-warning badge-xs">{t('common.yes')}</span> }] : []),
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
            {filteredItems.map(({ item, originalIndex }) => {
              const isMomentary = item.momentary_turn_on || item.momentary_turn_off;
              const effectiveId = item.id || item.boneio_output;
              const displayName = item.name || effectiveId || `Item ${originalIndex + 1}`;
              const areaName = item.area 
                ? allAreas.find(a => a.id === item.area)?.name || item.area 
                : '-';

              return (
                <Tr key={originalIndex}>
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
                      onEdit={() => onEdit(originalIndex)}
                      onDelete={() => onDelete(originalIndex)}
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
    </div>
  );
};

export default OutputTable;
