import React, { useRef, ReactNode, useEffect, useState } from 'react';
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
 * - Tap to expand/collapse
 * - Swipe up on the bar to expand
 * - Swipe down on the sheet header to collapse
 *
 * Only renders on mobile (hidden on lg+).
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

  /** Handle touch move — detect swipe direction and trigger open/close. */
  const handleTouchMove = (e: React.TouchEvent, direction: 'up' | 'down') => {
    if (touchStartY.current === null) return;
    const dy = touchStartY.current - e.touches[0].clientY;

    if (direction === 'up' && dy > SWIPE_THRESHOLD) {
      touchStartY.current = null;
      onOpenChange(true);
    } else if (direction === 'down' && dy < -SWIPE_THRESHOLD) {
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
        className="fixed bottom-0 inset-x-0 z-40 safe-area-bottom touch-none"
        onTouchStart={handleTouchStart}
        onTouchMove={(e) => handleTouchMove(e, 'up')}
        onTouchEnd={handleTouchEnd}
      >
        {/* Top shadow gradient */}
        <div className="h-6 bg-gradient-to-t from-base-200/95 to-transparent pointer-events-none" />
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          className="w-full bg-base-200/95 backdrop-blur-sm border-t border-base-content/10 active:bg-base-300 transition-colors"
        >
          {/* Drag handle */}
          <div className="flex justify-center pt-2">
            <div className="w-8 h-1 rounded-full bg-base-content/20" />
          </div>
          {/* Content */}
          <div className={`flex items-center justify-center gap-2.5 px-4 py-2 ${actions ? 'pb-1' : 'pb-3'}`}>
            {icon && <span className="text-lg">{icon}</span>}
            <span className="font-semibold text-sm text-base-content truncate">
              {label}
            </span>
            {indicator}
          </div>
        </button>
        {/* Action buttons (e.g. Save/Restore) */}
        {actions && (
          <div className="bg-base-200/95 backdrop-blur-sm px-3 pb-3 flex gap-2">
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
            onTouchMove={(e) => handleTouchMove(e, 'down')}
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
