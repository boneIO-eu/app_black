import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FaBolt, FaChevronDown, FaChevronRight, FaSpinner } from 'react-icons/fa';
import axios from '@/api/axios';
import { useTranslation } from '../../../hooks/useTranslation';
import { useTableSort } from '@/hooks/useTableSort';
import { addGlobalMessageListener, isScheduleEvent, type StateUpdate } from '@/hooks/useWebSocket';
import TableActions from './TableActions';
import MobileCard from './MobileCard';
import SortableHeader, { ResetSortButton } from './SortableHeader';
import { Table, Td, Tr, Th, Thead, Tbody } from '@/components/ui/table';
import {
  actionTypes,
  formatAgo,
  formatExact,
  formatFire,
  triggerSummary,
  OUTCOME_BADGE,
  type ScheduleEntry,
  type ScheduleOutcome,
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
 * whether it did, and what came of it. And a schedule is the one thing in
 * Settings nobody can test by pressing a button — without "run now" the only
 * way to find out whether it works is to wait until evening.
 *
 * Status arrives twice over: fetched once so the page is correct on arrival,
 * then pushed over the WebSocket. A schedule fires a few times a day, so
 * polling for it would be almost all waste, and a table that only refreshes on
 * save is worse than one that refreshes never — it looks current.
 */
const ScheduleTable: React.FC<ScheduleTableProps> = ({ items, onEdit, onDelete, isDirty = false }) => {
  const { t, language } = useTranslation();
  const { sortConfig, toggleSort, resetSort, sortItems, isSorted } = useTableSort('schedule');
  const [status, setStatus] = useState<Record<string, ScheduleStatus>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
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

  useEffect(() => {
    // Subscribed straight to the global listeners rather than through
    // useWebSocket(), which owns the connection's lifecycle counter — a second
    // owner here would close the socket when this table unmounts.
    return addGlobalMessageListener((data: StateUpdate) => {
      if (!isScheduleEvent(data)) return;
      setStatus((previous) => ({
        ...previous,
        [data.entity_id]: data.state as unknown as ScheduleStatus,
      }));
    });
  }, []);

  const runNow = async (id: string) => {
    setRunning(id);
    setError(null);
    try {
      const { data } = await axios.post(`/api/schedule/${encodeURIComponent(id)}/run`);
      setStatus((previous) => ({ ...previous, [id]: data as ScheduleStatus }));
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || t('schedule.run_failed'));
    } finally {
      setRunning(null);
    }
  };

  const toggleEnabled = async (id: string, enabled: boolean) => {
    setToggling(id);
    setError(null);
    try {
      const { data } = await axios.post(`/api/schedule/${encodeURIComponent(id)}/enable`, { enabled });
      setStatus((previous) => ({ ...previous, [id]: data as ScheduleStatus }));
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || t('schedule.toggle_failed'));
    } finally {
      setToggling(null);
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
        last: (item: ScheduleEntry) => status[resolveId(item)]?.last_fire || '',
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

  /**
   * When it last fired and how that went.
   *
   * `skipped_condition` gets its own colour rather than being folded into
   * "nothing happened": the schedule did fire and its condition told it not to
   * act, and those two look identical from outside unless we say so.
   */
  const lastRunCell = (state: ScheduleStatus | undefined) => {
    if (!state?.last_fire) return <span className="opacity-50">{t('schedule.never_ran')}</span>;
    const outcome = state.last_outcome as ScheduleOutcome | null;
    return (
      <div className="flex flex-col gap-0.5" title={formatExact(state.last_fire)}>
        <span>{formatAgo(state.last_fire, language)}</span>
        {outcome && (
          <span className={`badge badge-xs ${OUTCOME_BADGE[outcome] || 'badge-ghost'}`}>
            {t(`schedule.outcome_${outcome}`)}
          </span>
        )}
      </div>
    );
  };

  /** "Run it now", with the reason it is unavailable when it is. */
  const runButton = (item: ScheduleEntry, extraClass = '') => {
    const id = resolveId(item);
    const state = status[id];
    const title = isDirty
      ? t('schedule.run_needs_save')
      : !state
        ? t('schedule.run_not_loaded')
        : t('schedule.run_now');
    return (
      <button
        type="button"
        className={`btn btn-ghost btn-xs btn-square ${extraClass}`}
        onClick={() => runNow(id)}
        disabled={!state || isDirty || running === id}
        title={title}
      >
        {running === id ? <FaSpinner className="animate-spin w-3 h-3" /> : <FaBolt className="w-3 h-3" />}
      </button>
    );
  };

  /**
   * The on/off switch.
   *
   * Shows what the controller is actually doing, which can differ from
   * `enabled:` in the config: switching it here (or in Home Assistant) is
   * remembered across restarts, until somebody edits the config, which is
   * treated as the more deliberate statement and wins.
   */
  const enableToggle = (item: ScheduleEntry) => {
    const id = resolveId(item);
    const state = status[id];
    const on = state ? state.enabled : item.enabled !== false;
    const overridden = state && state.config_enabled !== undefined && state.config_enabled !== state.enabled;
    return (
      <input
        type="checkbox"
        className="toggle toggle-sm toggle-success"
        checked={on}
        disabled={!state || isDirty || toggling === id}
        onChange={(event) => toggleEnabled(id, event.target.checked)}
        title={
          isDirty
            ? t('schedule.run_needs_save')
            : overridden
              ? t('schedule.overrides_config')
              : t('schedule.enabled')
        }
      />
    );
  };

  /** The last runs, newest first. */
  const historyList = (state: ScheduleStatus | undefined) => {
    const history = [...(state?.history || [])].reverse();
    if (history.length === 0) {
      return <div className="text-xs opacity-60 py-2">{t('schedule.no_history')}</div>;
    }
    return (
      <ul className="text-xs space-y-1 py-2">
        {history.map((run, index) => (
          <li key={`${run.at}-${index}`} className="flex flex-wrap items-center gap-2">
            <span className="font-mono opacity-70 whitespace-nowrap">{formatExact(run.at)}</span>
            <span className={`badge badge-xs ${OUTCOME_BADGE[run.outcome] || 'badge-ghost'}`}>
              {t(`schedule.outcome_${run.outcome}`)}
            </span>
            <span className="opacity-60">{t(`schedule.source_${run.source}`)}</span>
            {run.error && <span className="text-error">{run.error}</span>}
          </li>
        ))}
      </ul>
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
        {sortedItems.map(({ item, originalIndex }) => {
          const state = status[resolveId(item)];
          return (
            <MobileCard
              key={originalIndex}
              title={item.name || resolveId(item)}
              subtitle={resolveId(item)}
              onEdit={() => onEdit(originalIndex)}
              onDelete={() => onDelete(originalIndex)}
              fields={[
                { label: t('schedule.enabled'), value: enableToggle(item) },
                { label: t('schedule.column_trigger'), value: triggerSummary(item, t) },
                { label: t('schedule.column_actions'), value: actionBadges(item) },
                { label: t('schedule.column_next'), value: formatFire(state?.next_fire ?? null) },
                { label: t('schedule.column_last'), value: lastRunCell(state) },
                { label: t('schedule.run_now'), value: runButton(item) },
                { label: t('schedule.history'), value: historyList(state) },
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
              <Th className="w-8">{''}</Th>
              <Th className="w-12">{t('schedule.enabled')}</Th>
              <SortableHeader column="name" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('schedule.column_name')}</SortableHeader>
              <SortableHeader column="trigger" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('schedule.column_trigger')}</SortableHeader>
              <Th>{t('schedule.column_actions')}</Th>
              <SortableHeader column="next" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('schedule.column_next')}</SortableHeader>
              <SortableHeader column="last" sortConfig={sortConfig} onToggleSort={toggleSort}>{t('schedule.column_last')}</SortableHeader>
              <Th>{t('outputs.actions')}</Th>
            </Tr>
          </Thead>
          <Tbody>
            {sortedItems.map(({ item, originalIndex }) => {
              const id = resolveId(item);
              const state = status[id];
              const off = state ? !state.enabled : item.enabled === false;
              const isOpen = expanded === id;
              return (
                <React.Fragment key={originalIndex}>
                  <Tr className={off ? 'opacity-50' : ''}>
                    <Td>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs btn-square"
                        onClick={() => setExpanded(isOpen ? null : id)}
                        title={t('schedule.history')}
                        aria-expanded={isOpen}
                      >
                        {isOpen ? <FaChevronDown className="w-3 h-3" /> : <FaChevronRight className="w-3 h-3" />}
                      </button>
                    </Td>
                    <Td>{enableToggle(item)}</Td>
                    <Td>
                      <div className="min-w-0">
                        <div className="truncate">{item.name || id}</div>
                        <div className="text-xs opacity-50 font-mono truncate">{id}</div>
                        {off && <span className="badge badge-ghost badge-xs">{t('schedule.disabled')}</span>}
                      </div>
                    </Td>
                    <Td className="whitespace-nowrap text-xs">{triggerSummary(item, t)}</Td>
                    <Td>{actionBadges(item)}</Td>
                    <Td className="font-mono text-xs whitespace-nowrap">{formatFire(state?.next_fire ?? null)}</Td>
                    <Td className="text-xs whitespace-nowrap">
                      {lastRunCell(state)}
                      {state?.last_error && (
                        <div className="text-error text-xs truncate max-w-48" title={state.last_error}>
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
                  {isOpen && (
                    <Tr>
                      <Td colSpan={8} className="bg-base-200/50">
                        <div className="px-2">
                          <div className="font-medium text-xs uppercase opacity-60">{t('schedule.history')}</div>
                          {historyList(state)}
                        </div>
                      </Td>
                    </Tr>
                  )}
                </React.Fragment>
              );
            })}
          </Tbody>
        </Table>
      </div>
    </div>
  );
};

export default ScheduleTable;
