/**
 * RemoteOutputTable — dedicated table for remote output entries.
 *
 * Columns: Name/ID | Device | Output Entity | Type | Area | Actions
 */
import React, { useState, useMemo } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import { FaWifi } from 'react-icons/fa';

interface Area {
  id: string;
  name: string;
}

interface RemoteOutputTableProps {
  items: any[];
  allAreas: Area[];
  allRemoteDevices: any[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
}

const RemoteOutputTable: React.FC<RemoteOutputTableProps> = ({
  items,
  allAreas,
  allRemoteDevices,
  onEdit,
  onDelete,
}) => {
  const { t } = useTranslation();
  const [filter, setFilter] = useState('');
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('remote_outputs');

  /** Resolve device name from ID. */
  const getDeviceName = (deviceId: string) => {
    const device = allRemoteDevices.find((d: any) => d.id === deviceId);
    return device?.name || deviceId || '-';
  };

  // Filter items
  const filteredItems = useMemo(() => {
    if (!filter.trim()) return items.map((item, index) => ({ item, originalIndex: index }));
    const lowerFilter = filter.toLowerCase();
    return items
      .map((item, index) => ({ item, originalIndex: index }))
      .filter(({ item }) =>
        (item.name?.toLowerCase().includes(lowerFilter)) ||
        (item.id?.toLowerCase().includes(lowerFilter)) ||
        (item.device_id?.toLowerCase().includes(lowerFilter)) ||
        (item.output_id?.toLowerCase().includes(lowerFilter)) ||
        (getDeviceName(item.device_id)?.toLowerCase().includes(lowerFilter))
      );
  }, [items, filter, allRemoteDevices]);

  // Sort filtered items
  const sortedItems = useMemo(() => {
    return sortItems(filteredItems, {
      name: (item: any) => (item.name || item.id || '').toLowerCase(),
      device: (item: any) => getDeviceName(item.device_id).toLowerCase(),
      output_id: (item: any) => (item.output_id || '').toLowerCase(),
      output_type: (item: any) => (item.output_type || '').toLowerCase(),
      area: (item: any) => {
        const area = allAreas.find(a => a.id === item.area);
        return (area?.name || item.area || '').toLowerCase();
      },
    });
  }, [filteredItems, sortItems, allAreas, allRemoteDevices]);

  /** Badge for output type. */
  const typeBadge = (type: string) => {
    const colorMap: Record<string, string> = {
      switch: 'badge-info',
      light: 'badge-warning',
      valve: 'badge-success',
    };
    return (
      <span className={`badge badge-sm ${colorMap[type] || 'badge-ghost'}`}>
        {type === 'switch' ? t('outputs.categories.switches')
          : type === 'light' ? t('outputs.categories.lights')
          : type === 'valve' ? t('outputs.categories.valves')
          : type}
      </span>
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <FilterInput
            filter={filter}
            setFilter={setFilter}
            totalCount={items.length}
            filteredCount={sortedItems.length}
          />
        </div>
        <ResetSortButton isSorted={isSorted} onReset={resetSort} />
      </div>

      {/* Mobile card view */}
      <div className="sm:hidden space-y-2">
        {sortedItems.map(({ item, originalIndex }) => {
          const displayName = item.name || item.id || `Item ${originalIndex + 1}`;
          const areaName = item.area
            ? allAreas.find(a => a.id === item.area)?.name || item.area
            : '';

          return (
            <MobileCard
              key={originalIndex}
              title={displayName}
              subtitle={`📡 ${getDeviceName(item.device_id)}`}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                { label: t('remote_outputs.output_entity'), value: item.output_id || '-' },
                { label: t('remote_outputs.output_type'), value: typeBadge(item.output_type || 'switch') },
                ...(areaName ? [{ label: t('outputs.area'), value: areaName }] : []),
                { label: t('remote_outputs.on_disconnect'), value: item.on_disconnect === 'turn_off' ? <span className="badge badge-error badge-xs">OFF</span> : <span className="badge badge-ghost badge-xs">{t('remote_outputs.on_disconnect_ignore')}</span> },
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
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.name')} / ID</SortableHeader>
              <SortableHeader column="device" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('remote_devices.device')}</SortableHeader>
              <SortableHeader column="output_id" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('remote_outputs.output_entity')}</SortableHeader>
              <SortableHeader column="output_type" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('remote_outputs.output_type')}</SortableHeader>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.area')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const effectiveId = item.id || `${item.device_id}_${item.output_id}`;
              const displayName = item.name || effectiveId || `Item ${originalIndex + 1}`;
              const areaName = item.area
                ? allAreas.find(a => a.id === item.area)?.name || item.area
                : '-';

              return (
                <Tr key={originalIndex}>
                  <Td>
                    <div>
                      <div className="font-medium flex items-center gap-1.5">
                        <FaWifi className="text-xs text-primary opacity-60" />
                        {displayName}
                      </div>
                      {item.name && effectiveId && (
                        <div className="text-xs text-base-content/60">ID: {effectiveId}</div>
                      )}
                    </div>
                  </Td>
                  <Td>
                    <span className="text-sm">{getDeviceName(item.device_id)}</span>
                  </Td>
                  <Td>
                    <code className="text-xs bg-base-200 px-1.5 py-0.5 rounded">{item.output_id || '-'}</code>
                  </Td>
                  <Td>{typeBadge(item.output_type || 'switch')}</Td>
                  <Td>{areaName}</Td>
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

export default RemoteOutputTable;
