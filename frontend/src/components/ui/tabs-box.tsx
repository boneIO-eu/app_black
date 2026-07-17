import React, { ReactNode, useRef, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * Tab definition for the TabsBox component.
 */
export interface Tab {
  /** Unique identifier for the tab */
  id: string;
  /** Label displayed on the tab */
  label: string;
  /** Optional icon element rendered before the label */
  icon?: ReactNode;
  /** Optional badge count to display next to the label */
  badge?: number;
  /** Badge variant - primary uses accent color, secondary uses muted */
  badgeVariant?: 'primary' | 'secondary';
  /** Content to render when this tab is active */
  content: ReactNode;
}

/**
 * Props for the TabsBox component.
 */
export interface TabsBoxProps {
  /** Array of tab definitions */
  tabs: Tab[];
  /** Currently active tab ID */
  activeTab: string;
  /** Callback when tab changes */
  onTabChange: (tabId: string) => void;
  /** Unique name for the radio group (required for multiple TabsBox on same page) */
  name: string;
  /** Additional className for the container */
  className?: string;
  /** Whether to render a bordered content area below the tabs */
  bordered?: boolean;
}

/**
 * Reusable underline-style tabs component.
 *
 * Renders horizontal scrollable tabs with an animated underline indicator.
 * Supports optional badge counts and bordered content areas.
 *
 * @example
 * ```tsx
 * const [activeTab, setActiveTab] = useState('basic');
 *
 * <TabsBox
 *   name="my_form_tabs"
 *   activeTab={activeTab}
 *   onTabChange={setActiveTab}
 *   tabs={[
 *     { id: 'basic', label: 'Basic Settings', content: <BasicForm /> },
 *     { id: 'advanced', label: 'Advanced', badge: 3, content: <AdvancedForm /> },
 *   ]}
 * />
 * ```
 */
export const TabsBox: React.FC<TabsBoxProps> = ({
  tabs,
  activeTab,
  onTabChange,
  name: _name,
  className = '',
  bordered = true,
}) => {
  const tabListRef = useRef<HTMLDivElement>(null);
  const [indicatorStyle, setIndicatorStyle] = useState<React.CSSProperties>({});
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  /** Check if the tab list overflows and update fade states. */
  const updateScrollFades = () => {
    const el = tabListRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 2);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  };

  // Update underline indicator position when active tab changes
  useEffect(() => {
    const tabList = tabListRef.current;
    if (!tabList) return;

    const activeButton = tabList.querySelector<HTMLButtonElement>(
      `[data-tab-id="${activeTab}"]`
    );
    if (!activeButton) return;

    const listRect = tabList.getBoundingClientRect();
    const btnRect = activeButton.getBoundingClientRect();

    setIndicatorStyle({
      left: btnRect.left - listRect.left + tabList.scrollLeft,
      width: btnRect.width,
    });

    updateScrollFades();
  }, [activeTab, tabs]);

  // Listen for scroll events on the tab list
  useEffect(() => {
    const el = tabListRef.current;
    if (!el) return;
    el.addEventListener('scroll', updateScrollFades, { passive: true });
    // Check initial state after mount
    updateScrollFades();
    return () => el.removeEventListener('scroll', updateScrollFades);
  }, []);

  return (
    <div className={className}>
      {/* Tab headers */}
      <div className="relative border-b border-base-300">
        <div
          ref={tabListRef}
          role="tablist"
          className="relative flex overflow-x-auto no-scrollbar"
          onScroll={updateScrollFades}
        >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              data-tab-id={tab.id}
              aria-selected={isActive}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                'relative px-3 py-2 text-xs sm:text-sm sm:px-4 sm:py-2.5 font-medium text-center transition-colors duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-t-md',
                isActive
                  ? 'text-primary'
                  : 'text-base-content/50 hover:text-base-content/80'
              )}
            >
              {tab.icon && <span className="mr-1.5 inline-flex items-center">{tab.icon}</span>}
              {tab.badge !== undefined && tab.badge > 0 ? (
                (() => {
                  const words = tab.label.split(' ');
                  const lastWord = words.pop();
                  const prefix = words.join(' ');
                  return (
                    <>
                      {prefix && <>{prefix} </>}
                      <span className="whitespace-nowrap">
                        {lastWord}
                        <span
                          className={cn(
                            'ml-1 inline-flex items-center justify-center min-w-[1.1rem] h-4 px-1 text-[10px] font-semibold rounded-full align-middle',
                            tab.badgeVariant === 'secondary'
                              ? 'bg-base-300 text-base-content/60'
                              : isActive
                                ? 'bg-primary/15 text-primary'
                                : 'bg-base-300 text-base-content/50'
                          )}
                        >
                          {tab.badge}
                        </span>
                      </span>
                    </>
                  );
                })()
              ) : (
                tab.label
              )}
            </button>
          );
        })}

        {/* Animated underline indicator */}
        <div
          className="absolute bottom-0 h-0.5 bg-primary rounded-full transition-all duration-200 ease-out"
          style={indicatorStyle}
        />
        </div>

        {/* Scroll affordance fades */}
        {canScrollLeft && (
          <div className="absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-base-100 to-transparent pointer-events-none z-10" />
        )}
        {canScrollRight && (
          <div className="absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-base-100 to-transparent pointer-events-none z-10" />
        )}
      </div>

      {/* Tab content */}
      {bordered ? (
        <div className="border border-t-0 border-base-300 rounded-b-lg bg-base-100 p-4">
          {tabs.map((tab) =>
            activeTab === tab.id ? (
              <div key={tab.id}>{tab.content}</div>
            ) : null
          )}
        </div>
      ) : (
        tabs.map((tab) =>
          activeTab === tab.id ? (
            <div key={tab.id} className="pt-4">
              {tab.content}
            </div>
          ) : null
        )
      )}
    </div>
  );
};

export default TabsBox;
