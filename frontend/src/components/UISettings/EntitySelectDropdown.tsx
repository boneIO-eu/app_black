import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AreaEntity } from '@/types/config';

/** A normalized entity item for display in the dropdown. */
export interface EntityItem {
  /** Unique identifier */
  id: string;
  /** Display name (falls back to id) */
  name: string;
  /** Optional area ID */
  area?: string;
  /** Optional badge label (e.g. "Group", "Cover") */
  badge?: string;
  /** Badge color class (defaults to badge-secondary) */
  badgeClass?: string;
  /** Whether this item is disabled (e.g. unsaved items) */
  disabled?: boolean;
  /** Warning label shown when disabled */
  disabledLabel?: string;
}

interface EntitySelectDropdownProps {
  /** Currently selected entity ID */
  value: string;
  /** Called when a new entity is selected */
  onChange: (value: string) => void;
  /** Items to display in the dropdown */
  items: EntityItem[];
  /** Available areas for resolving area names */
  allAreas?: AreaEntity[];
  /** Placeholder text when nothing is selected */
  placeholder?: string;
  /** IDs to exclude from the list */
  excludeIds?: string[];
  /** Use compact (small) size for the trigger */
  compact?: boolean;
}

/**
 * Reusable entity select dropdown that displays entity name, ID, and area.
 * Used for selecting outputs, covers, binary sensors, etc. in a consistent way.
 * Supports badges, disabled items, and area display.
 */
const EntitySelectDropdown: React.FC<EntitySelectDropdownProps> = ({
  value,
  onChange,
  items,
  allAreas = [],
  placeholder = 'Select...',
  excludeIds = [],
  compact = false,
}) => {
  // Filter out excluded IDs and empty IDs (Radix Select crashes on value="")
  const filteredItems = items.filter((item) => item.id && !excludeIds.includes(item.id));

  // Find selected item for display
  const selectedItem = filteredItems.find((item) => item.id === value);

  const getAreaName = (areaId: string): string => {
    if (!areaId) return '';
    const area = allAreas.find((a) => a.id === areaId);
    return area?.name || areaId;
  };

  const renderItemContent = (item: EntityItem) => {
    const showSubline = item.id !== item.name || item.area;
    return (
      <div className="flex flex-col">
        <span className="font-medium">
          {item.badge && (
            <span className={`badge badge-xs ${item.badgeClass || 'badge-secondary'} mr-1`}>
              {item.badge}
            </span>
          )}
          {item.disabled && item.disabledLabel && (
            <span className="badge badge-xs badge-warning mr-1">
              {item.disabledLabel}
            </span>
          )}
          {item.name}
        </span>
        {showSubline && (
          <span className="text-xs opacity-60">
            {item.id !== item.name && `ID: ${item.id}`}
            {item.id !== item.name && item.area && ' • '}
            {item.area && `📍 ${getAreaName(item.area)}`}
          </span>
        )}
      </div>
    );
  };

  return (
    <Select value={value || ''} onValueChange={onChange}>
      <SelectTrigger className={`w-full text-left [&>span]:items-start ${compact ? 'h-9' : 'input input-bordered h-auto min-h-10 py-1.5'}`}>
        <SelectValue placeholder={placeholder}>
          {selectedItem ? (
            renderItemContent(selectedItem)
          ) : (
            <span className="opacity-50">{placeholder}</span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="bg-base-100">
        {filteredItems.map((item) => (
          <SelectItem
            key={item.id}
            value={item.id}
            disabled={item.disabled}
            className={`focus:bg-base-200 hover:bg-base-200 data-highlighted:bg-base-200 ${item.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {renderItemContent(item)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};

export default EntitySelectDropdown;
