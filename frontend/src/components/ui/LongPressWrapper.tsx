import React, { useRef } from 'react';
import { suppressNextPointerRelease } from '@/utils/longPress';

interface LongPressWrapperProps {
    children: React.ReactNode;
    onLongPress: () => void;
    onClick?: (e: React.MouseEvent) => void;
    className?: string;
    style?: React.CSSProperties;
    title?: string;
    preventDefaultOnTouchStart?: boolean;
}

/**
 * Selector for interactive elements that should NOT trigger long press.
 * Includes buttons, links, form controls, and Radix UI combobox/listbox portals.
 */
const INTERACTIVE_SELECTOR = 'button, a, input, select, textarea, [role="combobox"], [role="listbox"], [role="option"], [data-radix-select-viewport], [data-select="trigger"], [data-popover]';

/**
 * Wraps children with long-press detection for both mouse and touch.
 *
 * After holding for 500ms `onLongPress` fires immediately (instant feedback).
 * The trailing pointer-release events are suppressed so they don't
 * dismiss any dialog that `onLongPress` opened.
 */
export const LongPressWrapper: React.FC<LongPressWrapperProps> = ({
    children,
    onLongPress,
    onClick,
    className,
    style,
    title,
    preventDefaultOnTouchStart = false,
}) => {
    const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isLongPress = useRef(false);

    const handlePressStart = (e: React.MouseEvent | React.TouchEvent) => {
        // Only react to left mouse button (button 0); ignore right-click (2) and middle (1).
        if ('button' in e && e.button !== 0) return;

        // Ignore clicks on interactive elements (buttons, links, form controls, dropdowns)
        if ((e.target as Element).closest(INTERACTIVE_SELECTOR)) return;

        if (preventDefaultOnTouchStart && e.type === 'touchstart') {
            try { e.preventDefault(); } catch { /* ignore passivity errors */ }
        }

        isLongPress.current = false;
        longPressTimer.current = setTimeout(() => {
            isLongPress.current = true;
            // Suppress the trailing pointer-release so @base-ui Dialog
            // backdrop doesn't dismiss the dialog we're about to open.
            suppressNextPointerRelease();
            onLongPress();
        }, 500);

        // Safety: clear the timer on window-level release events (capture phase).
        // This handles the case where mouseup lands on a Portal element
        // (e.g. Base UI Select dropdown) outside this wrapper's DOM tree,
        // or if the select trigger calls stopPropagation() during bubbling.
        const clearOnRelease = () => handlePressEnd();
        window.addEventListener('pointerup', clearOnRelease, { capture: true, once: true });
        window.addEventListener('mouseup', clearOnRelease, { capture: true, once: true });
        window.addEventListener('touchend', clearOnRelease, { capture: true, once: true });
    };

    const handlePressEnd = () => {
        if (longPressTimer.current) {
            clearTimeout(longPressTimer.current);
            longPressTimer.current = null;
        }
    };

    const handleTouchMove = () => {
        // Cancel long press if user moves finger (scrolling)
        handlePressEnd();
    };

    const handleClick = (e: React.MouseEvent) => {
        if ((e.target as Element).closest(INTERACTIVE_SELECTOR)) return;
        if (!isLongPress.current && onClick) {
            onClick(e);
        }
    };

    return (
        <div
            onClick={handleClick}
            onMouseDown={handlePressStart}
            onMouseUp={handlePressEnd}
            onMouseLeave={handlePressEnd}
            onTouchStart={handlePressStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handlePressEnd}
            onContextMenu={(e) => {
                if (!(e.target as Element).closest(INTERACTIVE_SELECTOR)) {
                    e.preventDefault();
                }
            }}
            className={className ? `cursor-pointer select-none ${className}` : "cursor-pointer select-none"}
            style={{ WebkitTouchCallout: 'none', WebkitUserSelect: 'none', ...style }}
            title={title}
        >
            {children}
        </div>
    );
};
