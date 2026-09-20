import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FaBolt, FaSpinner } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import {
  actionTypes,
  formatFire,
  triggerSummary,
  type ScheduleEntry,
  type ScheduleStatus,
} from '../helpers/scheduleTrigger';
import { resolveId } from '../helpers/slugifyId';

interface ScheduleTableProps {
  items: ScheduleEntry[];
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  /** True while the section has edits that have not been saved. */
  isDirty?: boolean;
}

/**
 * The schedules list.
 *
 * The only table here that fetches something. Every other section is fully
 * described by its configuration, but a schedule is not: the configuration
 * says when it should fire and only the running controller says when it will,
 * or why it did not. And a schedule is the one thing in Settings nobody can
 * test by pressing a button — without "run now" the only way to find out
 * whether it works is to wait until evening. Both of those belong on the row,
 * so the fetch lives here rather than being threaded through the widget for
 * one section's sake.
 */
const ScheduleTable: React.FC<ScheduleTableProps> = ({ items, onEdit, onDelete, isDirty = false }) => {
  const { t } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('schedule');
  const [status, setStatus] = useState<Record<string, ScheduleStatus>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/schedule');
      const byId: Record<string, ScheduleStatus> = {};
      for (const entry of data.schedules || []) byId[entry.id] = entry;
      setStatus(byId);
    } catch (err) {
      // Not worth a visible error: the rest of the row is still correct, and
      // "next firing" simply reads as unknown.
      console.error('Failed to load schedule status:', err);
    }
  }, []);

  useEffect(() => {
    // Refetches after a save, because saving replaces `items`.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchStatus();
  }, [fetchStatus, items]);

  const runNow = async (id: string) => {
    setRunning(id);
    setError(null);
    try {
      await axios.post(`/api/schedule/${encodeURIComponent(id)}/run`);
      await fetchStatus();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || t('schedule.run_failed'));
    } finally {
      setRunning(null);
    }
  };

  const indexedItems = useMemo(
    () => items.map((item, index) => ({ item, originalIndex: index })),
    [items],
  );

  const sortedItems = useMemo(
    () =>
      sortItems(indexedItems, {
        name: (item: ScheduleEntry) => (item.name || '').toLowerCase(),
        trigger: (item: ScheduleEntry) => triggerSummary(item, t).toLowerCase(),
        next: (item: ScheduleEntry) => status[resolveId(item)]?.next_fire || '￿',
      }),
    [indexedItems, sortItems, status, t],
  );

  const actionBadges = (item: ScheduleEntry) => {
    const types = actionTypes(item);
    if (types.length === 0) {
      // A schedule with no actions fires and does nothing, which is almost
      // always half-finished config rather than intent.
      return <span className="badge badge-warning badge-sm">{t('schedule.no_actions')}</span>;
    }
    return (
      <div className="flex flex-wrap gap-1">
        {types.map((type) => <span key={type} className="badge badge-info badge-sm">{type}</span>)}
      </div>
    );
  };

  /** "Run it now", with the reason it is unavailable when it is. */
  const runButton = (item: ScheduleEntry, extraClass = '') => {
    const state = status[resolveId(item)];
    const title = isDirty
      ? t('schedule.run_needs_save')
      : !state
        ? t('schedule.run_not_loaded')
        : t('schedule.run_now');
    return (
      <button
        type="button"
        className={`btn btn-ghost btn-xs btn-square ${extraClass}`}
        onClick={() => runNow(resolveId(item))}
        disabled={!state || isDirty || running === resolveId(item)}
        title={title}
      >
        {running === resolveId(item) ? <FaSpinner className="animate-spin w-3 h-3" /> : <FaBolt className="w-3 h-3" />}
      </button>
    );
  };

  return (
    <div className="space-y-2">
      {error && <div className="alert alert-error text-sm">{error}</div>}
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
            title={item.name || resolveId(item)}
            subtitle={resolveId(item)}
            onEdit={() => onEdit(originalIndex)}
            onDelete={() => onDelete(originalIndex)}
            fields={[
              { label: t('schedule.column_trigger'), value: triggerSummary(item, t) },
              { label: t('schedule.column_actions'), value: actionBadges(item) },
              { label: t('schedule.column_next'), value: formatFire(status[resolveId(item)]?.next_fire ?? null) },
              { label: t('schedule.run_now'), value: runButton(item) },
              ...(status[resolveId(item)]?.last_error
                ? [{ label: t('schedule.last_error'), value: <span className="text-error text-xs">{status[resolveId(item)]!.last_error}</span> }]
                : []),
            ]}
          />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block overflow-x-auto">
        <Table className="table table-zebra w-full">
          <Thead>
            <Tr>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('schedule.column_name')}</SortableHeader>
              <SortableHeader column="trigger" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('schedule.column_trigger')}</SortableHeader>
              <Th>{t('schedule.column_actions')}</Th>
              <SortableHeader column="next" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('schedule.column_next')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const state = status[resolveId(item)];
              const disabled = item.enabled === false;
              return (
                <Tr key={originalIndex} className={disabled ? 'opacity-50' : ''}>
                  <Td>
                    <div className="min-w-0">
                      <div className="truncate">{item.name || resolveId(item)}</div>
                      <div className="text-xs opacity-50 font-mono truncate">{resolveId(item)}</div>
                      {disabled && <span className="badge badge-ghost badge-xs">{t('schedule.disabled')}</span>}
                    </div>
                  </Td>
                  <Td className="whitespace-nowrap text-xs">{triggerSummary(item, t)}</Td>
                  <Td>{actionBadges(item)}</Td>
                  <Td className="font-mono text-xs whitespace-nowrap">
                    {formatFire(state?.next_fire ?? null)}
                    {state?.last_error && (
                      <div className="text-error text-xs font-sans truncate max-w-48" title={state.last_error}>
                        {state.last_error}
                      </div>
                    )}
                  </Td>
                  <Td>
                    <div className="flex items-center gap-1">
                      {runButton(item)}
                      <TableActions
                        onEdit={() => onEdit(originalIndex)}
                        onDelete={() => onDelete(originalIndex)}
                        editTitle={t('array_table_widget.edit_item')}
                        deleteTitle={t('array_table_widget.delete_item')}
                      />
                    </div>
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

export default ScheduleTable;
