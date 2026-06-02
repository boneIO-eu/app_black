import React, { useState, useMemo, useCallback } from 'react';
import axios from '@/api/axios';
import { copyToClipboard } from '@/utils/clipboard';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import FilterInput from './FilterInput';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';

interface Area {
  id: string;
  name: string;
}

interface TemplateTableProps {
  items: any[];
  allAreas: Area[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onDuplicate?: (index: number) => void;
}

const PLATFORM_ICONS: Record<string, string> = {
  thermostat: '🌡️',
  alarm_control_panel: '🚨',
  irrigation: '💧',
  gate_cover: '🚪',
};

const TemplateTable: React.FC<TemplateTableProps> = ({ items, allAreas, onEdit, onDelete, onDuplicate }) => {
  const { t } = useTranslation();
  const [filter, setFilter] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('template');

  /**
   * Copy HA dashboard YAML for a specific irrigation controller to clipboard.
   */
  const handleCopyDashboard = useCallback(async (ctrlId: string) => {
    try {
      setCopiedId(ctrlId);
      const { data } = await axios.get(`/api/irrigation/dashboard?ctrl_id=${encodeURIComponent(ctrlId)}`);
      if (data?.yaml) {
        await copyToClipboard(data.yaml);
        setTimeout(() => setCopiedId(null), 2000);
      } else {
        setCopiedId(null);
      }
    } catch (err) {
      console.error('Failed to fetch dashboard YAML', err);
      setCopiedId(null);
    }
  }, []);

  const filteredItems = useMemo(() => {
    if (!filter.trim()) return items.map((item, index) => ({ item, originalIndex: index }));
    const lowerFilter = filter.toLowerCase();
    return items
      .map((item, index) => ({ item, originalIndex: index }))
      .filter(({ item }) =>
        (item.name?.toLowerCase().includes(lowerFilter)) ||
        (item.id?.toLowerCase().includes(lowerFilter)) ||
        (item.platform?.toLowerCase().includes(lowerFilter))
      );
  }, [items, filter]);

  const sortedItems = useMemo(() => {
    return sortItems(filteredItems, {
      name: (item: any) => (item.name || item.id || '').toLowerCase(),
      platform: (item: any) => (item.platform || '').toLowerCase(),
      area: (item: any) => {
        const area = allAreas.find(a => a.id === item.area);
        return (area?.name || item.area || '').toLowerCase();
      },
    });
  }, [filteredItems, sortItems, allAreas]);

  const getPlatformLabel = (platform: string) => {
    return t(`template.platform_${platform}`) || platform;
  };

  const getDetails = (item: any): string => {
    if (item.platform === 'thermostat') {
      const parts: string[] = [];
      if (item.sensor_id) parts.push(`${t('template.sensor_id')}: ${item.sensor_id}`);
      if (item.output_id) parts.push(`${t('template.output_id')}: ${item.output_id}`);
      if (item.target_temperature != null) parts.push(`${item.target_temperature}°C`);
      return parts.join(' | ');
    }
    if (item.platform === 'alarm_control_panel') {
      const parts: string[] = [];
      const zoneCount = item.zones?.length || 0;
      const outputCount = item.outputs?.length || 0;
      parts.push(`${zoneCount} ${t('template.zones_count')}`);
      parts.push(`${outputCount} ${t('template.outputs_count')}`);
      return parts.join(' | ');
    }
    return '';
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
          const areaName = item.area
            ? allAreas.find(a => a.id === item.area)?.name || item.area
            : '';
          const icon = PLATFORM_ICONS[item.platform] || '🧩';

          return (
            <MobileCard
              key={originalIndex}
              title={`${icon} ${item.name || item.id || `Template ${originalIndex + 1}`}`}
              subtitle={item.name ? item.id : undefined}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              onDuplicate={onDuplicate ? () => onDuplicate(originalIndex) : undefined}
              onDashboard={item.platform === 'irrigation' && item.id
                ? () => handleCopyDashboard(item.id)
                : undefined}
              fields={[
                { label: t('template.platform'), value: <span className="badge badge-primary badge-xs">{getPlatformLabel(item.platform)}</span> },
                { label: t('array_table_widget.details'), value: getDetails(item) || '-' },
                ...(areaName ? [{ label: t('outputs.area'), value: areaName }] : []),
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
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.name')} / {t('outputs.id')}</SortableHeader>
              <SortableHeader column="platform" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('template.platform')}</SortableHeader>
              <Th>{t('array_table_widget.details')}</Th>
              <SortableHeader column="area" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('outputs.area')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const areaName = item.area
                ? allAreas.find(a => a.id === item.area)?.name || item.area
                : '-';
              const icon = PLATFORM_ICONS[item.platform] || '🧩';

              return (
                <Tr key={originalIndex}>
                  <Td>
                    <div>
                      {item.name && <div className="font-medium">{icon} {item.name}</div>}
                      <div className={item.name ? "text-xs text-base-content/60" : ""}>{!item.name && `${icon} `}{item.id || `Template ${originalIndex + 1}`}</div>
                    </div>
                  </Td>
                  <Td>
                    <span className="badge badge-primary badge-sm">
                      {getPlatformLabel(item.platform)}
                    </span>
                  </Td>
                  <Td>
                    <div className="text-xs">
                      {getDetails(item) || '-'}
                    </div>
                  </Td>
                  <Td>{areaName}</Td>
                  <Td>
                    <TableActions
                      onEdit={() => onEdit(originalIndex)}
                      onDelete={() => onDelete(originalIndex)}
                      onDuplicate={onDuplicate ? () => onDuplicate(originalIndex) : undefined}
                      onDashboard={item.platform === 'irrigation' && item.id
                        ? () => handleCopyDashboard(item.id)
                        : undefined}
                      dashboardTitle={copiedId === item.id
                        ? t('irrigation.dashboard_copied')
                        : t('irrigation.copy_ha_dashboard')}
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

export default TemplateTable;
