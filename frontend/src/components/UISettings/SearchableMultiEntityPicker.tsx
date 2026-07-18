import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import type { AreaEntity } from '@/types/config';
import type { EntityItem } from './EntitySelectDropdown';

interface SearchableMultiEntityPickerProps {
  /** Currently selected entity IDs */
  value: string[];
  /** Called when the selection changes */
  onChange: (value: string[]) => void;
  /** Items to display in the picker */
  items: EntityItem[];
  /** Available areas for resolving area names */
  allAreas?: AreaEntity[];
  /** Placeholder text when nothing is selected */
  placeholder?: string;
  /** IDs to exclude from the list */
  excludeIds?: string[];
  /** Label for the picker (shown above the trigger) */
  label?: string;
  /** Whether at least one item must be selected */
  required?: boolean;
  /** Error message when validation fails */
  errorMessage?: string;
  /** Area ID to show first in the list (e.g. the parent entity's area) */
  preferredArea?: string;
}

/**
 * Multi-select entity picker rendered as a modal dialog.
 * Based on SearchableEntityPicker but allows selecting multiple items.
 *
 * Features:
 * - Search input with filtering
 * - Grouping by area
 * - Chip display of selected items in trigger
 * - Select all / deselect all in dialog
 * - Count badge in footer
 */
const SearchableMultiEntityPicker: React.FC<SearchableMultiEntityPickerProps> = ({
  value,
  onChange,
  items,
  allAreas = [],
  placeholder,
  excludeIds = [],
  label,
  required = false,
  errorMessage,
  preferredArea,
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  const resolvedPlaceholder = placeholder || t('entity_picker.select');

  // Filter out excluded IDs
  const filteredItems = useMemo(
    () => items.filter((item) => item.id && !excludeIds.includes(item.id)),
    [items, excludeIds]
  );

  /** Resolve area ID to area name. */
  const getAreaName = useCallback(
    (areaId: string): string => {
      if (!areaId) return '';
      const area = allAreas.find((a) => a.id === areaId);
      return area?.name || areaId;
    },
    [allAreas]
  );

  // Search-filtered items
  const searchFiltered = useMemo(() => {
    if (!search.trim()) return filteredItems;
    const q = search.toLowerCase().trim();
    return filteredItems.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.id.toLowerCase().includes(q) ||
        (item.area && getAreaName(item.area).toLowerCase().includes(q)) ||
        (item.badge && item.badge.toLowerCase().includes(q))
    );
  }, [filteredItems, search, getAreaName]);

  // Group items by area
  const grouped = useMemo(() => {
    const groups = new Map<string, EntityItem[]>();
    const noArea: EntityItem[] = [];

    for (const item of searchFiltered) {
      if (item.area) {
        const areaName = getAreaName(item.area);
        const key = areaName || item.area;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key)!.push(item);
      } else {
        noArea.push(item);
      }
    }

    // Resolve preferred area name for matching
    const preferredName = preferredArea ? (getAreaName(preferredArea) || preferredArea) : '';

    // Sort groups: preferred area first, then alphabetical
    const sorted = [...groups.entries()].sort(([a], [b]) => {
      if (preferredName) {
        const aMatch = a === preferredName;
        const bMatch = b === preferredName;
        if (aMatch && !bMatch) return -1;
        if (!aMatch && bMatch) return 1;
      }
      return a.localeCompare(b);
    });
    return { sorted, noArea };
  }, [searchFiltered, getAreaName, preferredArea]);

  // Focus search on open, reset search
  useEffect(() => {
    if (open) {
      setSearch('');
      const timer = setTimeout(() => searchRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Close picker on Escape without propagating to parent dialogs.
  // Uses capture phase to intercept before base-ui Dialog sees it.
  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        e.preventDefault();
        setOpen(false);
      }
    };
    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [open]);

  /** Toggle a single item's selection. */
  const toggleItem = (id: string) => {
    const next = value.includes(id)
      ? value.filter((v) => v !== id)
      : [...value, id];
    onChange(next);
  };

  /** Select all currently visible (search-filtered) items. */
  const selectAllVisible = () => {
    const visibleIds = searchFiltered.map((i) => i.id);
    const merged = Array.from(new Set([...value, ...visibleIds]));
    onChange(merged);
  };

  /** Deselect all currently visible (search-filtered) items. */
  const deselectAllVisible = () => {
    const visibleIds = new Set(searchFiltered.map((i) => i.id));
    onChange(value.filter((v) => !visibleIds.has(v)));
  };

  /** Handle backdrop/outside click to close. */
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        setOpen(false);
      }
    },
    []
  );

  // Selected items resolved for chip display
  const selectedItems = useMemo(
    () => value.map((id) => filteredItems.find((item) => item.id === id)).filter(Boolean) as EntityItem[],
    [value, filteredItems]
  );

  const allVisibleSelected = searchFiltered.length > 0 && searchFiltered.every((i) => value.includes(i.id));
  const hasError = required && value.length === 0;
  const hasResults = searchFiltered.length > 0;

  /** Render a single entity item in the list with a checkbox. */
  const renderItem = (item: EntityItem, showArea = true) => {
    const isSelected = value.includes(item.id);
    return (
      <label
        key={item.id}
        className={`
          flex items-center gap-3 w-full text-left px-3 py-2.5 rounded-lg transition-colors cursor-pointer
          ${isSelected ? 'bg-primary/10' : 'hover:bg-base-200 active:bg-base-300'}
        `}
      >
        <input
          type="checkbox"
          className="checkbox checkbox-sm checkbox-primary shrink-0"
          checked={isSelected}
          onChange={() => toggleItem(item.id)}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {item.badge && (
              <span className={`badge badge-xs ${item.badgeClass || 'badge-secondary'} shrink-0`}>
                {item.badge}
              </span>
            )}
            <span className="font-medium truncate">{item.name}</span>
          </div>
          {(item.id !== item.name || (showArea && item.area)) && (
            <div className="text-xs opacity-50 mt-0.5">
              {item.id !== item.name && `ID: ${item.id}`}
              {item.id !== item.name && showArea && item.area && ' • '}
              {showArea && item.area && `📍 ${getAreaName(item.area)}`}
            </div>
          )}
        </div>
      </label>
    );
  };

  /** Remove a single chip from selection. */
  const removeChip = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(value.filter((v) => v !== id));
  };

  return (
    <>
      {/* Label */}
      {label && (
        <label className="label">
          <span className="label-text font-medium">
            {label}
            {required && ' *'}
          </span>
        </label>
      )}

      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`
          flex w-full items-center justify-between rounded-[var(--radius-field)] border
          bg-transparent text-left text-sm transition-[color,box-shadow]
          hover:bg-base-200/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]
          outline-none min-h-10 py-1.5 px-3
          ${hasError ? 'border-error' : 'border-(--input-border)'}
        `}
      >
        <div className="flex-1 min-w-0">
          {selectedItems.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {selectedItems.slice(0, 5).map((item) => (
                <span
                  key={item.id}
                  className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                    item.disabledLabel
                      ? 'bg-warning/20 text-warning-content border border-warning/40'
                      : 'bg-primary/15 text-primary'
                  }`}
                >
                  {item.disabledLabel && <span className="text-warning">⚠</span>}
                  {item.name}
                  <span
                    onClick={(e) => removeChip(item.id, e)}
                    className="hover:text-error transition-colors cursor-pointer"
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') removeChip(item.id, e as any); }}
                  >
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </span>
                </span>
              ))}
              {selectedItems.length > 5 && (
                <span className="text-xs text-base-content/50 self-center">
                  +{selectedItems.length - 5}
                </span>
              )}
            </div>
          ) : (
            <span className="opacity-50">{resolvedPlaceholder}</span>
          )}
        </div>
        <svg className="h-4 w-4 shrink-0 opacity-50 ml-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m21 21-4.34-4.34M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z" />
        </svg>
      </button>

      {/* Error message */}
      {hasError && errorMessage && (
        <p className="text-xs text-error mt-1">{errorMessage}</p>
      )}

      {/* Multi-select picker dialog */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/40 animate-in fade-in-0 duration-150"
          onClick={handleBackdropClick}
        >
          <div
            className="bg-base-100 w-full max-w-lg sm:max-w-xl mx-2 sm:mx-auto mt-[10vh] sm:mt-0 rounded-xl border border-base-300 shadow-2xl flex flex-col max-h-[75vh] sm:max-h-[65vh] animate-in zoom-in-95 fade-in-0 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header with title and close */}
            <div className="flex items-center justify-between px-4 pt-4 pb-2">
              <h2 className="text-base font-semibold">{label || resolvedPlaceholder}</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg hover:bg-base-200 transition-colors"
              >
                <svg className="h-5 w-5 opacity-60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Search input */}
            <div className="px-4 pb-3">
              <div className="relative">
                <svg
                  className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 opacity-40"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="m21 21-4.34-4.34M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z" />
                </svg>
                <input
                  ref={searchRef}
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t('entity_picker.search_placeholder')}
                  className="input input-bordered w-full pl-9 h-10 bg-base-200/50 rounded-lg"
                  autoComplete="off"
                  autoCorrect="off"
                  spellCheck={false}
                />
                {search && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearch('');
                      searchRef.current?.focus();
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-base-300 transition-colors"
                  >
                    <svg className="h-4 w-4 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            </div>

            {/* Select all / Deselect all toolbar */}
            <div className="flex items-center justify-between px-4 pb-2 gap-2">
              <span className="text-xs text-base-content/50">
                {t('entity_picker.selected_count', { count: value.length })}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={allVisibleSelected ? deselectAllVisible : selectAllVisible}
                  className="btn btn-xs btn-ghost"
                >
                  {allVisibleSelected
                    ? t('entity_picker.deselect_all')
                    : t('entity_picker.select_all')}
                </button>
              </div>
            </div>

            {/* Results list */}
            <div className="flex-1 overflow-y-auto px-2 py-1 min-h-0 border-t border-base-200">
              {!hasResults && (
                <div className="text-center py-8 text-base-content/50">
                  <svg className="h-10 w-10 mx-auto mb-2 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="m21 21-4.34-4.34M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z" />
                  </svg>
                  <p>{t('entity_picker.no_results')}</p>
                </div>
              )}

              {/* Grouped items by area */}
              {hasResults && (
                <>
                  {grouped.sorted.map(([areaName, areaItems]) => (
                    <div key={areaName} className="mb-1">
                      <div className="text-xs font-semibold uppercase tracking-wider text-base-content/40 px-3 py-1.5 flex items-center gap-1">
                        <span>📍</span> {areaName}
                      </div>
                      <div className="space-y-0.5">
                        {areaItems.map((item) => renderItem(item, false))}
                      </div>
                    </div>
                  ))}

                  {/* Items without area */}
                  {grouped.noArea.length > 0 && (
                    <div className="mb-1">
                      {grouped.sorted.length > 0 && (
                        <div className="text-xs font-semibold uppercase tracking-wider text-base-content/40 px-3 py-1.5">
                          {t('entity_picker.no_area')}
                        </div>
                      )}
                      <div className="space-y-0.5">
                        {grouped.noArea.map((item) => renderItem(item))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Footer with count and done button */}
            <div className="border-t border-base-200 px-4 py-2.5 flex items-center justify-between shrink-0 rounded-b-xl">
              <span className="text-xs text-base-content/40">
                {search.trim()
                  ? t('entity_picker.showing_filtered', { count: searchFiltered.length, total: filteredItems.length })
                  : t('entity_picker.total_items', { count: filteredItems.length })}
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="btn btn-sm btn-primary"
              >
                {t('common.done')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default SearchableMultiEntityPicker;
