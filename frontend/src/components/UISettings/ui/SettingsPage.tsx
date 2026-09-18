import React, { createContext, useContext, useEffect } from 'react';
import { cn } from '@/lib/utils';

export type SettingsPageWidth = 'narrow' | 'form' | 'wide' | 'full';

export interface SettingsPageProps {
  /**
   * How wide the content column is allowed to grow.
   *
   * `form` is the default and the one nearly every page wants: a single
   * column of fields, capped where a text line stops being comfortable to
   * read. `wide` is for pages that are mostly tables or two-column grids,
   * `narrow` for a page with one thing to decide at a time — a wizard step
   * reads worse the wider it gets — and `full` for the few that manage
   * their own width.
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
 *
 * Past the cap the column centres itself. Left-aligned, a 1152px form on a
 * 1900px window left a 400px dead band down the right-hand side — empty on
 * every page, and the only thing ever in it was the save button, stranded
 * 290px from the card it saves. Centred, the page reads as a document and
 * the bar below it has something to line up with.
 */
export const SETTINGS_PAGE_WIDTHS: Record<SettingsPageWidth, string> = {
  narrow: 'max-w-3xl',
  form: 'max-w-5xl 2xl:max-w-6xl',
  wide: 'max-w-6xl 2xl:max-w-7xl',
  full: 'max-w-none',
};

/**
 * How the shell learns which column the open section drew.
 *
 * The header above the page and the action bar below it centre themselves on
 * the same column as the cards, and the component that decides that column is
 * this one — so it says so, rather than the shell keeping a second list of
 * which section is how wide and the two drifting apart. Set by UISettings; a
 * no-op anywhere else, so a page still renders on its own.
 */
export const SectionColumnContext = createContext<
  (width: SettingsPageWidth | null) => void
>(() => {});

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
  const report = useContext(SectionColumnContext);
  useEffect(() => {
    report(width);
    return () => report(null);
  }, [report, width]);

  return (
    <div className={cn('stg-page w-full mx-auto', SETTINGS_PAGE_WIDTHS[width], 'space-y-5', className)}>
      {children}
    </div>
  );
};

export default SettingsPage;
