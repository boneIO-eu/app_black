import React, { useRef } from 'react';

interface LongPressWrapperProps {
    children: React.ReactNode;
    onLongPress: () => void;
    onClick?: (e: React.MouseEvent) => void;
    className?: string;
    style?: React.CSSProperties;
    title?: string;
    preventDefaultOnTouchStart?: boolean;
}

export const LongPressWrapper: React.FC<LongPressWrapperProps> = ({
    children,
    onLongPress,
    onClick,
    className,
    style,
    title,
    preventDefaultOnTouchStart = false,
}) => {
    const longPressTimer = useRef<NodeJS.Timeout | null>(null);
    const isLongPress = useRef(false);

    const handlePressStart = (e: React.MouseEvent | React.TouchEvent) => {
        // Ignore clicks on buttons/links
        if ((e.target as Element).closest('button, a')) return;

        if (preventDefaultOnTouchStart && e.type === 'touchstart') {
            try { e.preventDefault(); } catch { /* ignore passivity errors */ }
        }

        isLongPress.current = false;
        longPressTimer.current = setTimeout(() => {
            isLongPress.current = true;
            onLongPress();
        }, 500);
    };

    const handlePressEnd = () => {
        if (longPressTimer.current) {
            clearTimeout(longPressTimer.current);
            longPressTimer.current = null;
        }
    };

    const handleClick = (e: React.MouseEvent) => {
        if ((e.target as Element).closest('button, a')) return;
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
            onTouchEnd={handlePressEnd}
            onContextMenu={(e) => {
                if (!(e.target as Element).closest('button, a')) {
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
