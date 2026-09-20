import React, { useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import { EDGES, type SwitchEntry } from '../helpers/virtualSwitchEdges';

interface Area {
  id: string;
  name: string;
}

interface VirtualSwitchTableProps {
  items: SwitchEntry[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

/** How many actions each edge carries, for the Actions column. */
function edgeCounts(item: SwitchEntry): Record<string, number> {
  return Object.fromEntries(EDGES.map((edge) => [edge, (item.actions?.[edge] || []).length]));
}

const VirtualSwitchTable: React.FC<VirtualSwitchTableProps> = ({
  items,
  allAreas,
  onEdit,
  onDelete,
}) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('virtual_switch');

  const indexedItems = useMemo(
    () => items.map((item, index) => ({ item, originalIndex: index })),
    [items],
  );

  const sortedItems = useMemo(
    () =>
      sortItems(indexedItems, {
        name: (item: SwitchEntry) => (item.name || item.id || '').toLowerCase(),
        id: (item: SwitchEntry) => (item.id || '').toLowerCase(),
        actions: (item: SwitchEntry) => {
          const counts = edgeCounts(item);
          return EDGES.reduce((total, edge) => total + counts[edge], 0);
        },
        area: (item: SwitchEntry) => {
          const area = allAreas.find((a) => a.id === item.area);
          return (area?.name || item.area || '').toLowerCase();
        },
      }),
    [indexedItems, sortItems, allAreas],
  );

  /** The badges shared by the desktop row and the mobile card. */
  const actionBadges = (item: SwitchEntry) => {
    const counts = edgeCounts(item);
    const total = EDGES.reduce((sum, edge) => sum + counts[edge], 0);
    if (total === 0) {
      // Not an error — a flag that only conditions read is the original point
      // of a virtual switch, and most of them stay that way.
      return <span className="text-base-content/50 text-xs">{t('virtual_switch.flag_only')}</span>;
    }
    return (
      <div className="flex flex-wrap gap-1">
        {EDGES.filter((edge) => counts[edge] > 0).map((edge) => (
          <span key={edge} className="badge badge-info badge-sm">
            {`${t(`virtual_switch.${edge}`)}: ${counts[edge]}`}
          </span>
        ))}
      </div>
    );
  };

  const restoreLabel = (item: SwitchEntry) =>
    item.restore_state === false
      ? `${t('virtual_switch.initial')}: ${item.initial ? 'ON' : 'OFF'}`
      : t('virtual_switch.restored');

  return (
    <div className="space-y-2">
      {isSorted && (
        <div className="flex justify-end">
          <ResetSortButton isSorted={isSorted} onReset={resetSort} />
        </div>
      )}

      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {sortedItems.map(({ item, originalIndex }) => (
          <MobileCard
            key={originalIndex}
            title={item.name || item.id}
            subtitle={item.name ? item.id : undefined}
            onEdit={() => onEdit(originalIndex)}
            onDelete={() => onDelete(originalIndex)}
            fields={[
              { label: t('virtual_switch.column_actions'), value: actionBadges(item) },
              { label: t('virtual_switch.column_restore'), value: restoreLabel(item) },
            ]}
          />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
        <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('virtual_switch.column_name')}</SortableHeader>
              <SortableHeader column="id" sortConfig={sortConfig} onToggleSort={toggleSort}>ID</SortableHeader>
              <SortableHeader column="actions" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('virtual_switch.column_actions')}</SortableHeader>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('virtual_switch.area')}</SortableHeader>
              <Th>{t('virtual_switch.column_restore')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => (
              <Tr key={originalIndex}>
                <Td>{item.name || item.id}</Td>
                <Td className="font-mono text-xs">{item.id}</Td>
                <Td>{actionBadges(item)}</Td>
                <Td>{allAreas.find((a) => a.id === item.area)?.name || item.area || '-'}</Td>
                <Td className="text-xs">{restoreLabel(item)}</Td>
                <Td>
                  <TableActions
                    onEdit={() => onEdit(originalIndex)}
                    onDelete={() => onDelete(originalIndex)}
                    editTitle={t('array_table_widget.edit_item')}
                    deleteTitle={t('array_table_widget.delete_item')}
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

export default VirtualSwitchTable;
