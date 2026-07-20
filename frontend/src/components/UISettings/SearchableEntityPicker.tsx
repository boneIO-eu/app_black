import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from '@/hooks/useTranslation';
import type { AreaEntity } from '@/types/config';
import type { EntityItem } from './EntitySelectDropdown';

const RECENT_STORAGE_KEY = 'boneio-recent-entities';
const MAX_RECENT = 5;

interface SearchableEntityPickerProps {
  /** Currently selected entity ID */
  value: string;
  /** Called when a new entity is selected */
  onChange: (value: string) => void;
  /** Items to display in the picker */
  items: EntityItem[];
  /** Available areas for resolving area names */
  allAreas?: AreaEntity[];
  /** Placeholder text when nothing is selected */
  placeholder?: string;
  /** IDs to exclude from the list */
  excludeIds?: string[];
  /** Use compact (small) size for the trigger */
  compact?: boolean;
  /** Storage key suffix for recent items (default: 'default') */
  recentKey?: string;
  /** Area ID to prioritize (items from this area appear first). */
  preferredArea?: string;
  /** When true, renders without dark backdrop (for use inside another dialog). */
  nested?: boolean;
}

/**
 * Searchable entity picker rendered as a modal dialog.
 * Features search input, grouping by area, colored badges, and recent items.
 * Redesigned to match Home Assistant entity picker UX:
 * - Full-width dialog on mobile, wider on desktop
 * - Click outside to close
 * - Compact, scrollable list with clear sections
 */
const SearchableEntityPicker: React.FC<SearchableEntityPickerProps> = ({
  value,
  onChange,
  items,
  allAreas = [],
  placeholder,
  excludeIds = [],
  compact = false,
  recentKey = 'default',
  preferredArea,
  nested = false,
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

  // Find selected item for display
  const selectedItem = filteredItems.find((item) => item.id === value);

  // Recent items from localStorage
  const [recentIds, setRecentIds] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem(`${RECENT_STORAGE_KEY}-${recentKey}`);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  /** Save a recently used entity. */
  const addRecent = useCallback(
    (id: string) => {
      setRecentIds((prev) => {
        const next = [id, ...prev.filter((r) => r !== id)].slice(0, MAX_RECENT);
        try {
          localStorage.setItem(`${RECENT_STORAGE_KEY}-${recentKey}`, JSON.stringify(next));
        } catch {
          /* quota exceeded — ignore */
        }
        return next;
      });
    },
    [recentKey]
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

  // Recent items that exist in current items list
  const recentItems = useMemo(
    () =>
      recentIds
        .map((id) => filteredItems.find((item) => item.id === id))
        .filter((item): item is EntityItem => item != null),
    [recentIds, filteredItems]
  );

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

  /** Handle item selection. */
  const handleSelect = (id: string) => {
    onChange(id);
    addRecent(id);
    setOpen(false);
  };

  /** Handle backdrop/outside click to close. */
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      // Only close if clicking the backdrop itself, not its children
      if (e.target === e.currentTarget) {
        setOpen(false);
      }
    },
    []
  );

  /** Render a single entity item in the list. */
  const renderItem = (item: EntityItem, showArea = true) => (
    <button
      key={item.id}
      type="button"
      disabled={item.disabled}
      onClick={() => handleSelect(item.id)}
      className={`
        w-full text-left px-3 py-2.5 rounded-lg transition-colors
        ${item.id === value ? 'bg-primary/10 ring-1 ring-primary/30' : 'hover:bg-base-200 active:bg-base-300'}
        ${item.disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      <div className="flex items-center gap-2">
        {item.badge && (
          <span className={`badge badge-xs ${item.badgeClass || 'badge-secondary'} shrink-0`}>
            {item.badge}
          </span>
        )}
        {item.disabled && item.disabledLabel && (
          <span className="badge badge-xs badge-warning shrink-0">{item.disabledLabel}</span>
        )}
        <span className="font-medium truncate">{item.name}</span>
      </div>
      {(item.id !== item.name || (showArea && item.area)) && (
        <div className="text-xs opacity-50 mt-0.5 ml-0.5">
          {item.id !== item.name && `ID: ${item.id}`}
          {item.id !== item.name && showArea && item.area && ' • '}
          {showArea && item.area && `📍 ${getAreaName(item.area)}`}
        </div>
      )}
    </button>
  );

  const hasResults = searchFiltered.length > 0;
  const showRecent = recentItems.length > 0 && !search.trim();

  return (
    <>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`
          flex w-full items-center justify-between rounded-lg border border-(--input-border)
          bg-transparent text-left text-sm transition-[color,box-shadow]
          hover:bg-base-200/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]
          outline-none
          ${compact ? 'h-9 px-2' : 'input input-bordered h-auto min-h-10 py-1.5 px-3'}
        `}
      >
        <div className="flex-1 min-w-0">
          {selectedItem ? (
            <div className="flex flex-col [&>span]:items-start">
              <span className="font-medium truncate">
                {selectedItem.badge && (
                  <span className={`badge badge-xs ${selectedItem.badgeClass || 'badge-secondary'} mr-1`}>
                    {selectedItem.badge}
                  </span>
                )}
                {selectedItem.name}
              </span>
              {(selectedItem.id !== selectedItem.name || selectedItem.area) && (
                <span className="text-xs opacity-60">
                  {selectedItem.id !== selectedItem.name && `ID: ${selectedItem.id}`}
                  {selectedItem.id !== selectedItem.name && selectedItem.area && ' • '}
                  {selectedItem.area && `📍 ${getAreaName(selectedItem.area)}`}
                </span>
              )}
            </div>
          ) : (
            <span className="opacity-50">{resolvedPlaceholder}</span>
          )}
        </div>
        <svg className="h-4 w-4 shrink-0 opacity-50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m21 21-4.34-4.34M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z" />
        </svg>
      </button>

      {/* Entity picker dialog — HA-style: wider, click-outside-to-close */}
      {open && (() => {
        const pickerContent = (
          <div
            className={`fixed inset-0 flex items-start sm:items-center justify-center animate-in fade-in-0 duration-150 ${
              nested ? 'z-[100] bg-black/20' : 'z-50 bg-black/40'
            }`}
            onClick={handleBackdropClick}
          >
            <div
              className={`bg-base-100 w-full max-w-lg sm:max-w-xl mx-2 sm:mx-auto rounded-xl border border-base-300 shadow-2xl flex flex-col animate-in zoom-in-95 fade-in-0 duration-150 ${
                nested ? 'mt-[5vh] sm:mt-0 max-h-[70vh] sm:max-h-[60vh]' : 'mt-[10vh] sm:mt-0 max-h-[75vh] sm:max-h-[65vh]'
              }`}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header with title and close */}
              <div className="flex items-center justify-between px-4 pt-4 pb-2">
                <h2 className="text-base font-semibold">{resolvedPlaceholder}</h2>
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

              {/* Recent items section */}
              {showRecent && (
                <div className="mb-1">
                  <div className="text-xs font-semibold uppercase tracking-wider text-base-content/40 px-3 py-1.5">
                    {t('entity_picker.recent')}
                  </div>
                  <div className="space-y-0.5">
                    {recentItems.map((item) => renderItem(item))}
                  </div>
                  <div className="border-b border-base-200 mx-2 mt-1.5 mb-1" />
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

            {/* Item count footer */}
            <div className="border-t border-base-200 px-4 py-2 text-xs text-base-content/40 text-center shrink-0 rounded-b-xl">
              {search.trim()
                ? t('entity_picker.showing_filtered', { count: searchFiltered.length, total: filteredItems.length })
                : t('entity_picker.total_items', { count: filteredItems.length })
              }
            </div>
            </div>
          </div>
        );
        return nested ? createPortal(pickerContent, document.body) : pickerContent;
      })()}
    </>
  );
};

export default SearchableEntityPicker;
