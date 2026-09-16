import React from 'react';
import { cn } from '@/lib/utils';

export type SettingsPageWidth = 'form' | 'wide' | 'full';

export interface SettingsPageProps {
  /**
   * How wide the content column is allowed to grow.
   *
   * `form` is the default and the one nearly every page wants: a single
   * column of fields, capped where a text line stops being comfortable to
   * read. `wide` is for pages that are mostly tables or two-column grids,
   * `full` for the few that manage their own width.
   */
  width?: SettingsPageWidth;
  /** Additional container classes. */
  className?: string;
  children?: React.ReactNode;
}

/**
 * The caps are deliberately generous and step up again on very wide screens.
 * A single 768px column on a 1080p display left the right half of the window
 * empty; paired with `.stg-cols` inside the cards, this width is what stops a
 * short form from scrolling.
 */
export const SETTINGS_PAGE_WIDTHS: Record<SettingsPageWidth, string> = {
  form: 'max-w-5xl 2xl:max-w-6xl',
  wide: 'max-w-6xl 2xl:max-w-7xl',
  full: 'max-w-none',
};

/**
 * The outer shell every settings page renders into.
 *
 * It owns the two things that used to be decided per page and therefore
 * never matched: how wide the column is (pages variously picked max-w-lg,
 * max-w-2xl, max-w-3xl or nothing at all) and how much air sits between
 * cards. Pages that need something other than the default say so with
 * `width` instead of inventing a wrapper.
 */
export const SettingsPage: React.FC<SettingsPageProps> = ({
  width = 'form',
  className = '',
  children,
}) => {
  return (
    <div className={cn('stg-page w-full', SETTINGS_PAGE_WIDTHS[width], 'space-y-5', className)}>
      {children}
    </div>
  );
};

export default SettingsPage;
