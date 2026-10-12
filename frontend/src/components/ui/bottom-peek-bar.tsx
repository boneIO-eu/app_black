import React, { useRef, ReactNode, useEffect, useState } from 'react';
import { ChevronsUpDown } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

/**
 * Props for the BottomPeekBar component.
 */
export interface BottomPeekBarProps {
  /** Whether the expanded sheet is open */
  open: boolean;
  /** Callback when open state changes */
  onOpenChange: (open: boolean) => void;
  /** Icon element shown in the peek bar */
  icon?: ReactNode;
  /** Label text shown in the peek bar */
  label: string;
  /** Optional indicator (e.g. unsaved dot) shown after the label */
  indicator?: ReactNode;
  /** Optional action buttons rendered below the label (e.g. Save/Restore) */
  actions?: ReactNode;
  /** Title shown in the expanded bottom sheet header */
  sheetTitle: string;
  /** Content rendered inside the expanded bottom sheet */
  children: ReactNode;
  /** Additional className for the sheet content */
  sheetClassName?: string;
}

const SWIPE_THRESHOLD = 30;

/** Breakpoint matching Tailwind's `lg` (1024px). */
function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return isDesktop;
}

/**
 * Reusable bottom peek bar with swipe-to-expand bottom sheet.
 *
 * Shows a fixed bar at the bottom of the screen with a drag handle,
 * icon, and label. Supports:
 * - Tap to expand
 * - Swipe down on the sheet header to collapse
 *
 * The bar opens on a tap only. It sits where the thumb scrolls the page, so
 * a swipe up on it opened the sheet by accident, and blocking touch scrolling
 * there to tell the two apart made the page hard to scroll.
 *
 * Only renders on mobile (hidden on lg+).
 *
 * From `sm` up the Dialog opens as a centred modal, not a sheet, so the bar
 * drops its drag handle there and shows a picker chevron instead — a handle
 * promises something that slides up out of the bar, and nothing does.
 *
 * @example
 * ```tsx
 * <BottomPeekBar
 *   open={isOpen}
 *   onOpenChange={setIsOpen}
 *   icon={<span>🖥</span>}
 *   label="Urządzenia Modbus"
 *   sheetTitle="Sekcje Konfiguracji"
 * >
 *   <SectionList ... />
 * </BottomPeekBar>
 * ```
 */
export function BottomPeekBar({
  open,
  onOpenChange,
  icon,
  label,
  indicator,
  actions,
  sheetTitle,
  children,
  sheetClassName = '',
}: BottomPeekBarProps) {
  const touchStartY = useRef<number | null>(null);
  const isDesktop = useIsDesktop();

  // Force-close if screen becomes desktop-sized
  useEffect(() => {
    if (isDesktop && open) onOpenChange(false);
  }, [isDesktop, open, onOpenChange]);

  /** Handle touch start — record initial Y position. */
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY;
  };

  /** Handle touch move — a swipe down on the sheet header closes it. */
  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return;
    const dy = touchStartY.current - e.touches[0].clientY;

    if (dy < -SWIPE_THRESHOLD) {
      touchStartY.current = null;
      onOpenChange(false);
    }
  };

  /** Reset touch tracking. */
  const handleTouchEnd = () => {
    touchStartY.current = null;
  };

  // Don't render anything on desktop
  if (isDesktop) return null;

  return (
    <div className="lg:hidden">
      {/* Fixed bottom peek bar */}
      <div
        // Sits on top of the app's bottom navigation, which below xl is always
        // there and already pads for the iOS home indicator. The wrapper lets
        // touches through, so the gradient above the bar does not catch them;
        // only the bar itself takes them.
        className="fixed inset-x-0 z-40 pointer-events-none"
        style={{ bottom: 'var(--bottom-nav-h, 0px)' }}
      >
        {/* Top shadow gradient */}
        <div className="h-6 bg-gradient-to-t from-base-200/95 to-transparent" />
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          className="pointer-events-auto w-full bg-base-200/95 backdrop-blur-sm border-t border-base-content/10 active:bg-base-300 transition-colors"
        >
          {/* Drag handle — phones only, where the sheet really slides up */}
          <div className="flex justify-center pt-2 sm:hidden">
            <div className="w-8 h-1 rounded-full bg-base-content/20" />
          </div>
          {/* Content */}
          <div className={`flex items-center justify-center gap-2.5 px-4 py-2 sm:pt-3 ${actions ? 'pb-1' : 'pb-3'}`}>
            {icon && <span className="text-lg">{icon}</span>}
            <span className="font-semibold text-sm text-base-content truncate">
              {label}
            </span>
            {indicator}
            <ChevronsUpDown aria-hidden className="hidden sm:block w-4 h-4 shrink-0 text-base-content/40" />
          </div>
        </button>
        {/* Action buttons (e.g. Save/Restore) */}
        {actions && (
          <div className="pointer-events-auto bg-base-200/95 backdrop-blur-sm px-3 pb-3 flex gap-2">
            {actions}
          </div>
        )}
      </div>

      {/* Expanded bottom sheet */}
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={`p-0 gap-0 max-h-[85vh] overflow-y-auto sm:max-w-md ${sheetClassName}`}>
          {/* Swipeable header with drag handle */}
          <div
            className="touch-none cursor-grab active:cursor-grabbing"
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            {/* Drag handle */}
            <div className="flex justify-center pt-3 sm:hidden">
              <div className="w-10 h-1 rounded-full bg-base-content/20" />
            </div>
            <DialogHeader className="px-5 pt-3 pb-3 sticky top-0 bg-base-100 z-10 border-b border-base-300">
              <DialogTitle>{sheetTitle}</DialogTitle>
            </DialogHeader>
          </div>
          <div className="p-4">
            {children}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default BottomPeekBar;
