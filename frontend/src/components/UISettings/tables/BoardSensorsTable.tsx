/**
 * BoardSensorsTable — table for LM75, INA219, MCP9808 board sensors.
 *
 * Uses the same UI components (Table, MobileCard, SortableHeader, TableActions)
 * as all other section tables for consistent UX.
 */
import React, { useMemo } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import { formatTimeperiod } from '@/utils/formatters';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

const TYPE_LABELS: Record<string, string> = {
  lm75: 'LM75',
  ina219: 'INA219',
  mcp9808: 'MCP9808',
};

const TYPE_BADGES: Record<string, string> = {
  lm75: 'badge-warning',
  ina219: 'badge-info',
  mcp9808: 'badge-success',
};

function formatAddress(address: number | string | undefined): string {
  if (address === undefined || address === null) return '-';
  if (typeof address === 'number') return `0x${address.toString(16).toUpperCase().padStart(2, '0')}`;
  return String(address);
}

/**
 * Build a display name for a board sensor entry.
 * Falls back to type label + address when id is not set (common for INA219).
 */
function getDisplayName(item: any): string {
  if (item.id) return item.id;
  const typeLabel = TYPE_LABELS[item._type] || item._type || 'Sensor';
  const addr = formatAddress(item.address);
  return addr !== '-' ? `${typeLabel} (${addr})` : typeLabel;
}

interface BoardSensorsTableProps {
  items: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const BoardSensorsTable: React.FC<BoardSensorsTableProps> = ({ items, onEdit, onDelete }) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('board_sensors');

  const indexedItems = useMemo(() =>
    items.map((item, index) => ({ item, originalIndex: index })),
    [items]
  );

  const sortedItems = useMemo(() => {
    return sortItems(indexedItems, {
      name: (item: any) => getDisplayName(item).toLowerCase(),
      type: (item: any) => (item._type || '').toLowerCase(),
      address: (item: any) => {
        const addr = item.address;
        return typeof addr === 'number' ? addr : parseInt(String(addr), 16) || 0;
      },
    });
  }, [indexedItems, sortItems]);

  return (
    <div className="space-y-2">
      {isSorted && (
        <div className="flex justify-end">
          <ResetSortButton isSorted={isSorted} onReset={resetSort} />
        </div>
      )}
      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {sortedItems.map(({ item, originalIndex }) => {
          const sensorType = item._type || 'lm75';
          const displayName = getDisplayName(item);
          const interval = formatTimeperiod(item.update_interval);
          const subSensors = Array.isArray(item.sensors)
            ? item.sensors.map((s: any) => s.id).join(', ')
            : '';

          return (
            <MobileCard
              key={originalIndex}
              title={displayName}
              subtitle={TYPE_LABELS[sensorType] || sensorType}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                { label: t('board_sensors.type'), value: <span className={`badge badge-xs ${TYPE_BADGES[sensorType] || 'badge-ghost'}`}>{TYPE_LABELS[sensorType] || sensorType}</span> },
                { label: t('board_sensors.address'), value: <span className="font-mono text-xs">{formatAddress(item.address)}</span> },
                ...(subSensors ? [{ label: t('board_sensors.ina_sensors'), value: subSensors }] : []),
                ...(interval ? [{ label: t('board_sensors.update_interval'), value: interval }] : []),
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
              <SortableHeader column="type" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('board_sensors.type')}</SortableHeader>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('board_sensors.id')}</SortableHeader>
              <SortableHeader column="address" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('board_sensors.address')}</SortableHeader>
              <Th>{t('board_sensors.update_interval')}</Th>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const sensorType = item._type || 'lm75';
              const interval = formatTimeperiod(item.update_interval);

              return (
                <Tr key={originalIndex}>
                  <Td>
                    <span className={`badge badge-sm ${TYPE_BADGES[sensorType] || 'badge-ghost'}`}>
                      {TYPE_LABELS[sensorType] || sensorType}
                    </span>
                  </Td>
                  <Td>
                    <div>
                      <span className="font-medium">{getDisplayName(item)}</span>
                      {Array.isArray(item.sensors) && item.sensors.length > 0 && (
                        <div className="text-xs text-base-content/60 mt-0.5">
                          {item.sensors.map((s: any) => s.id).join(', ')}
                        </div>
                      )}
                    </div>
                  </Td>
                  <Td className="font-mono text-sm">{formatAddress(item.address)}</Td>
                  <Td>{interval || '-'}</Td>
                  <Td>
                    <TableActions
                      onEdit={() => onEdit(originalIndex)}
                      onDelete={() => onDelete(originalIndex)}
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

export default BoardSensorsTable;
