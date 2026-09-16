import React from 'react';
import { FaSave, FaUndo } from 'react-icons/fa';
import { cn } from '@/lib/utils';
import { SETTINGS_PAGE_WIDTHS, type SettingsPageWidth } from './SettingsPage';

export interface SettingsActionBarProps {
  /** Whether the section has edits waiting to be written. */
  dirty: boolean;
  /** Save is in flight. */
  saving?: boolean;
  /** Block saving even while dirty — a field failed validation. */
  saveDisabled?: boolean;
  /** Commit the section. */
  onSave: () => void;
  /** Throw the edits away. Omit for sections that cannot be restored. */
  onRestore?: () => void;
  /** Localised labels, so this stays free of the translation hook. */
  labels: {
    save: string;
    restore: string;
    unsaved: string;
  };
  /**
   * Match the content column this bar belongs to, so the buttons line up
   * with the right edge of the cards above them instead of floating off at
   * the window edge.
   */
  width?: SettingsPageWidth;
  className?: string;
}

/**
 * The one place a settings section is committed from.
 *
 * Settings used to commit from three different places depending on where the
 * page came from: the top right of the header for schema-driven sections, the
 * footer of a card for the pages moved over from the old System screen, and a
 * bar at the bottom on phones. Same-looking pages, three different answers to
 * "where do I click save".
 *
 * This is that one answer, in the same place at every width: pinned to the
 * bottom of the content column, where the form ends. Per-item operations —
 * changing one broker password, rebooting, creating a backup — stay in their
 * own card's footer, because they act on that card rather than on the
 * section; they are right-aligned there, so everything that does something
 * still lives in the bottom-right corner of whatever it applies to.
 */
export const SettingsActionBar: React.FC<SettingsActionBarProps> = ({
  dirty,
  saving = false,
  saveDisabled = false,
  onSave,
  onRestore,
  labels,
  width = 'form',
  className = '',
}) => {
  return (
    <div
      className={cn(
        // Sticky inside the scrolling pane rather than a sibling below it.
        // A sibling sits outside the scroll container, so whenever the
        // content was long enough to scroll it was a scrollbar's width wider
        // than the cards and the button no longer lined up with their right
        // edge. In here it shares their content box, so it lines up whether
        // or not a scrollbar is present.
        //
        // The negative side margins let the glass span the pane's full width
        // while the row inside keeps the content column's own padding. The
        // pane deliberately has no bottom padding — this bar is what closes
        // it — so there is nothing to cancel underneath.
        //
        // The content above is a flex child that grows, so this sits at the
        // bottom edge however short the section is; `sticky` keeps it there
        // once the section is long enough to scroll. Header at the top, this
        // at the bottom, content between.
        'stg-actionbar sticky bottom-0 z-10',
        '-mx-4 px-4 py-3 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8',
        className,
      )}
    >
      <div
        className={cn(
          'w-full flex items-center justify-between gap-3',
          SETTINGS_PAGE_WIDTHS[width],
        )}
      >
        <span
          className={cn(
            'flex items-center gap-2 text-[13px] font-medium text-warning transition-opacity',
            dirty ? 'opacity-100' : 'opacity-0',
          )}
          aria-hidden={!dirty}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-warning animate-pulse" />
          <span className="hidden sm:inline">{labels.unsaved}</span>
        </span>

        <div className="flex items-center gap-2">
          {onRestore && dirty && (
            <button
              type="button"
              className="btn btn-ghost btn-sm gap-2 text-warning"
              onClick={onRestore}
            >
              <FaUndo className="text-xs" />
              {labels.restore}
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary btn-sm gap-2 shadow-sm"
            onClick={onSave}
            disabled={!dirty || saveDisabled || saving}
          >
            {saving ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <FaSave className="text-xs" />
            )}
            {labels.save}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsActionBar;
