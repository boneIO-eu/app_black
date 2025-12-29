import React, { ReactNode } from 'react';

/**
 * Tab definition for the TabsBox component.
 */
export interface Tab {
  /** Unique identifier for the tab */
  id: string;
  /** Label displayed on the tab */
  label: string;
  /** Optional badge count to display next to the label */
  badge?: number;
  /** Badge variant - primary or secondary */
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
}

/**
 * Reusable DaisyUI tabs component with tabs-box styling.
 * Uses radio inputs for proper tab behavior and includes bordered content area.
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
  name,
  className = '',
}) => {
  return (
    <div className={className}>
      {/* Tab headers */}
      <div role="tablist" className="tabs tabs-box">
        {tabs.map((tab) => (
          <input
            key={tab.id}
            type="radio"
            name={name}
            role="tab"
            className="tab"
            aria-label={`${tab.label}${tab.badge ? ` (${tab.badge})` : ''}`}
            checked={activeTab === tab.id}
            onChange={() => onTabChange(tab.id)}
          />
        ))}
      </div>

      {/* Tab content with border */}
      <div className="border border-base-300 rounded-b-box bg-base-100 p-4">
        {tabs.map((tab) => (
          activeTab === tab.id && (
            <div key={tab.id}>
              {tab.content}
            </div>
          )
        ))}
      </div>
    </div>
  );
};

export default TabsBox;
