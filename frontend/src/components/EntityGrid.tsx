import React from 'react';

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
  children: React.ReactNode;
}

/**
 * Reusable responsive grid/list container for entity cards.
 * Used by InputsView, OutputsView, and any future entity views.
 */
export function EntityGrid({ isGrid, gridClassName, children }: EntityGridProps) {
  return (
    <div className={isGrid ? (gridClassName || ENTITY_GRID_CLASS) : ENTITY_LIST_CLASS}>
      {children}
    </div>
  );
}
