import React from 'react';
import { cn } from '@/lib/utils';

/**
 * Shared grid/list layout classes for entity card views (Inputs, Outputs, etc.).
 * Ensures consistent responsive grid breakpoints and spacing across all entity views.
 */
export const ENTITY_GRID_CLASS = "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4";

/**
 * Grid class for sensor/modbus cards with charts — wider cards need single column on mobile.
 */
export const SENSOR_GRID_CLASS = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4";

export const ENTITY_LIST_CLASS = "flex flex-col gap-4";

interface EntityGridProps {
  /** Whether to display as grid (true) or list (false). */
  isGrid: boolean;
  /** Override grid class (e.g. for covers that use single column). */
  gridClassName?: string;
  /**
   * Heading for the group. Given one, the grid is wrapped in a card and the
   * heading sits on it. Pass `null` for a panel with no heading — a view
   * with a single group still wants the window, just not a label repeating
   * the page title. Omit it entirely for a bare grid.
   */
  title?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * Reusable responsive grid/list container for entity cards.
 * Used by InputsView, OutputsView, and any future entity views.
 *
 * With a `title` it draws the group as a panel: a card with the category on
 * it and the entities inset inside. Loose tiles separated by a hairline
 * divider left the page with no structure at this count — thirty outputs
 * read as one undifferentiated field of white rectangles — so a group is a
 * window, the same as a settings section.
 */
export function EntityGrid({ isGrid, gridClassName, title, children }: EntityGridProps) {
  const grid = (
    <div className={isGrid ? (gridClassName || ENTITY_GRID_CLASS) : ENTITY_LIST_CLASS}>
      {children}
    </div>
  );

  if (title === undefined) return grid;

  return <EntityPanel title={title}>{grid}</EntityPanel>;
}

interface EntityPanelProps {
  /** Heading for the group. `null` draws the panel without one. */
  title?: React.ReactNode;
  /** Controls that belong to the group, right-aligned in the header. */
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/**
 * One group of entities, as a window on the page.
 *
 * The dashboards used to separate groups with a hairline divider and leave
 * the tiles loose on the background. At thirty outputs that is not a group,
 * it is a field — so a group is a card with its name on it and the entities
 * inset inside, which is what a settings section looks like and therefore
 * what the rest of the app already taught you to read.
 */
export function EntityPanel({ title, action, className, children }: EntityPanelProps) {
  return (
    <section className={cn('stg-card p-4 sm:p-5 mb-5', className)}>
      {(title != null || action) && (
        <div className="flex items-center justify-between gap-2 mb-3.5">
          {title != null && (
            <h3 className="text-[15px] font-semibold tracking-tight flex items-center gap-2">
              {title}
            </h3>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
