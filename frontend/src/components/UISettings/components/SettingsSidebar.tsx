/**
 * SettingsSidebar - Sidebar navigation for configuration sections.
 *
 * Mobile: Sticky section selector that opens a bottom sheet with the full list.
 * Desktop: Always-visible sidebar with section list.
 */
import { FaCheck, FaExclamationTriangle, FaUndo, FaSave } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { BottomPeekBar } from '@/components/ui/bottom-peek-bar';
import { useSecurityPosture } from '@/hooks/useSecurityPosture';
import { SECTION_GROUPS } from '../constants/sectionDefinitions';

interface SectionConfig {
  name: string;
  title: string;
  icon: string;
  translationKey: string;
  badge?: string;
  group?: string;
}

interface ConfigSection {
  name: string;
  schema: any;
  normalizedSchema: any;
  uiSchema: any;
  data: Record<string, any>;
}

interface SettingsSidebarProps {
  sections: ConfigSection[];
  reloadSections: SectionConfig[];
  restartSections: SectionConfig[];
  configSections: SectionConfig[];
  activeSection: string;
  saveStatus: Record<string, 'idle' | 'saving' | 'success' | 'error'>;
  unsavedChanges: Record<string, boolean>;
  isSidebarOpen: boolean;
  onSidebarToggle: (open: boolean) => void;
  onNavigate: (sectionName: string) => void;
  /** Called when Save button is pressed in mobile bottom bar */
  onSave?: () => void;
  /** Called when Restore button is pressed in mobile bottom bar */
  onRestore?: () => void;
  /** Whether the save button should be disabled */
  saveDisabled?: boolean;
}

/**
 * Single section button component.
 */
function SectionButton({
  sectionConfig,
  isActive,
  status,
  hasUnsavedChanges,
  onClick,
}: {
  sectionConfig: SectionConfig | undefined;
  isActive: boolean;
  status: 'idle' | 'saving' | 'success' | 'error' | undefined;
  hasUnsavedChanges: boolean;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg transition-all duration-200 flex items-center justify-between group ${
        isActive
          ? 'bg-primary text-primary-content shadow-md'
          : 'bg-base-100 hover:bg-base-300 text-base-content'
      }`}
    >
      <div className="flex items-center space-x-3 min-w-0">
        <span className="text-lg">{sectionConfig?.icon || '⚙️'}</span>
        <div className="min-w-0">
          <div className="font-medium flex items-center gap-2">
            <span className="truncate">{sectionConfig?.title}</span>
            {sectionConfig?.badge && (
              <span className="badge badge-xs badge-warning font-bold uppercase whitespace-nowrap">
                {t(`settings.badge_${sectionConfig.badge}`)}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center space-x-2">
        {hasUnsavedChanges && (
          <div className="w-2 h-2 bg-warning rounded-full" title="Unsaved changes"></div>
        )}
        {status === 'success' && (
          <FaCheck className="text-success" title="Saved successfully" />
        )}
        {status === 'error' && (
          <FaExclamationTriangle className="text-error" title="Save failed" />
        )}
        {status === 'saving' && (
          <div className="loading loading-spinner loading-xs"></div>
        )}
      </div>
    </button>
  );
}

/**
 * Section list component - renders a list of section buttons.
 */
function SectionList({
  sections,
  filterSections,
  configSections,
  activeSection,
  saveStatus,
  unsavedChanges,
  onNavigate,
}: {
  sections: ConfigSection[];
  filterSections: SectionConfig[];
  configSections: SectionConfig[];
  activeSection: string;
  saveStatus: Record<string, 'idle' | 'saving' | 'success' | 'error'>;
  unsavedChanges: Record<string, boolean>;
  onNavigate: (sectionName: string) => void;
}) {
  return (
    <div className="space-y-2">
      {sections
        .filter(s => filterSections.some(fs => fs.name === s.name))
        .map((section) => {
          const sectionConfig = configSections.find(s => s.name === section.name);
          return (
            <SectionButton
              key={section.name}
              sectionConfig={sectionConfig}
              isActive={activeSection === section.name}
              status={saveStatus[section.name]}
              hasUnsavedChanges={unsavedChanges[section.name] || false}
              onClick={() => onNavigate(section.name)}
            />
          );
        })}
    </div>
  );
}

/**
 * Sidebar content - shared between mobile bottom sheet and desktop sidebar.
 */
function SidebarContent({
  sections,
  configSections,
  activeSection,
  saveStatus,
  unsavedChanges,
  onNavigate,
}: Omit<SettingsSidebarProps, 'isSidebarOpen' | 'onSidebarToggle'>) {
  const { t } = useTranslation();

  // One pass over the declared groups instead of a hand-written box per
  // concern. Adding a section is now an entry in sectionDefinitions; the
  // sidebar does not need to know it exists.
  const grouped = SECTION_GROUPS.map(group => ({
    ...group,
    entries: configSections.filter(section => section.group === group.name),
  })).filter(group => group.entries.length > 0);

  // A count on the access group, so it says there is something to do before it
  // is opened. Nothing outstanding shows no badge rather than a zero.
  const { posture } = useSecurityPosture();
  const outstanding = posture?.summary.actionable ?? 0;

  // Show skeleton while config sections are still loading
  const isLoading = sections.length === 0;

  if (isLoading) {
    return (
      <>
        {/* Skeleton for reload sections */}
        <div className="mb-4 space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-12 w-full rounded-lg" />
          ))}
        </div>
        {/* Skeleton for restart sections */}
        <div className="border border-warning/20 rounded-xl bg-warning/5 p-3">
          <div className="skeleton h-4 w-40 mb-2" />
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="skeleton h-12 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      {grouped.map(group => (
        <div key={group.name} className="mb-4 border border-base-content/10 rounded-xl bg-base-200/40 p-3">
          <div className="flex items-center gap-2 mb-2 px-1">
            <span className="text-sm font-semibold opacity-80">
              {group.icon} {t(group.translationKey)}
            </span>
            {group.name === 'access' && outstanding > 0 && (
              <span className="badge badge-error badge-sm">{outstanding}</span>
            )}
          </div>
          <SectionList
            sections={sections}
            filterSections={group.entries}
            configSections={configSections}
            activeSection={activeSection}
            saveStatus={saveStatus}
            unsavedChanges={unsavedChanges}
            onNavigate={onNavigate}
          />
        </div>
      ))}
    </>
  );
}

/**
 * Main SettingsSidebar component.
 *
 * Mobile: sticky dropdown bar showing active section. Tap opens bottom sheet.
 * Desktop: always-visible sidebar panel.
 */
export default function SettingsSidebar({
  sections,
  reloadSections,
  restartSections,
  configSections,
  activeSection,
  saveStatus,
  unsavedChanges,
  isSidebarOpen,
  onSidebarToggle,
  onNavigate,
  onSave,
  onRestore,
  saveDisabled,
}: SettingsSidebarProps) {
  const { t } = useTranslation();
  const activeSectionConfig = configSections.find(s => s.name === activeSection);
  const hasActiveUnsaved = activeSection === 'mqtt'
    ? (unsavedChanges['mqtt'] || unsavedChanges['lox_udp'] || false)
    : (unsavedChanges[activeSection] || false);
  const isSaving = saveStatus[activeSection] === 'saving';

  /** Navigate to section and close mobile bottom sheet. */
  const handleMobileNavigate = (sectionName: string) => {
    onNavigate(sectionName);
    onSidebarToggle(false);
  };

  /** Action buttons for bottom bar — only when active section has unsaved changes. */
  const actionButtons = hasActiveUnsaved ? (
    <>
      <button
        type="button"
        className="btn btn-sm btn-ghost flex-1"
        onClick={onRestore}
      >
        <FaUndo className="text-xs" />
        {t('settings.restore')}
      </button>
      <button
        type="button"
        className="btn btn-sm btn-primary flex-1 animate-subtle-glow"
        onClick={onSave}
        disabled={saveDisabled || isSaving}
      >
        {isSaving ? (
          <span className="loading loading-spinner loading-xs" />
        ) : (
          <FaSave className="text-xs" />
        )}
        {t('settings.save')}
      </button>
    </>
  ) : undefined;
  
  return (
    <>
      {/* Mobile: bottom peek bar + sheet */}
      <BottomPeekBar
        open={isSidebarOpen}
        onOpenChange={onSidebarToggle}
        icon={activeSectionConfig?.icon || '⚙️'}
        label={activeSectionConfig?.title || t('settings.configuration_sections')}
        indicator={
          hasActiveUnsaved
            ? <span className="flex-shrink-0 w-2 h-2 bg-warning rounded-full" />
            : undefined
        }
        actions={actionButtons}
        sheetTitle={t('settings.configuration_sections')}
      >
        <SidebarContent
          sections={sections}
          reloadSections={reloadSections}
          restartSections={restartSections}
          configSections={configSections}
          activeSection={activeSection}
          saveStatus={saveStatus}
          unsavedChanges={unsavedChanges}
          onNavigate={handleMobileNavigate}
        />
      </BottomPeekBar>

      {/* Desktop version - always visible sidebar */}
      <div className="hidden lg:block w-80 bg-base-200 border-r border-base-content/10 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-xl font-bold text-base-content mb-4">{t('settings.configuration_sections')}</h2>
          <SidebarContent
            sections={sections}
            reloadSections={reloadSections}
            restartSections={restartSections}
            configSections={configSections}
            activeSection={activeSection}
            saveStatus={saveStatus}
            unsavedChanges={unsavedChanges}
            onNavigate={onNavigate}
          />
        </div>
      </div>
    </>
  );
}
