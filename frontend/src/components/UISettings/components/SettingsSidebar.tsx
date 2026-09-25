/**
 * SettingsSidebar - Sidebar navigation for configuration sections.
 *
 * Mobile: Sticky section selector that opens a bottom sheet with the full list.
 * Desktop: Always-visible sidebar with section list.
 */
import { useState } from 'react';
import { FaCheck, FaExclamationTriangle, FaSearch, FaTimes } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { BottomPeekBar } from '@/components/ui/bottom-peek-bar';
import { useSecurityPosture } from '@/hooks/useSecurityPosture';
import { SECTION_GROUPS } from '../constants/sectionDefinitions';
import type { ConfigSection } from '../types/section';

interface SectionConfig {
  name: string;
  title: string;
  icon: string;
  translationKey: string;
  badge?: string;
  group?: string;
}

interface SettingsSidebarProps {
  sections: ConfigSection[];
  /**
   * Every section, with its group and title. The reload/restart split used to
   * come in as two more lists because it decided which box an entry sat in;
   * the groups decide that now, and what saving costs is carried by the badge.
   */
  configSections: SectionConfig[];
  activeSection: string;
  saveStatus: Record<string, 'idle' | 'saving' | 'success' | 'error'>;
  unsavedChanges: Record<string, boolean>;
  isSidebarOpen: boolean;
  onSidebarToggle: (open: boolean) => void;
  onNavigate: (sectionName: string) => void;
}

/**
 * Single section button component.
 */
function SectionButton({
  sectionConfig,
  isActive,
  status,
  hasUnsavedChanges,
  countBadge,
  onClick,
}: {
  sectionConfig: SectionConfig | undefined;
  isActive: boolean;
  status: 'idle' | 'saving' | 'success' | 'error' | undefined;
  hasUnsavedChanges: boolean;
  /** Findings waiting in this section, shown on the row as well as the group. */
  countBadge?: number;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 rounded-xl transition-colors duration-150 flex items-start justify-between gap-2 group ${
        isActive
          ? 'bg-primary text-primary-content shadow-sm'
          : 'text-base-content hover:bg-base-content/6'
      }`}
    >
      <div className="flex items-start gap-3 min-w-0 flex-1">
        <span className="text-lg leading-6 shrink-0">{sectionConfig?.icon || '⚙️'}</span>
        <div className="min-w-0 flex-1">
          {/* Wrapped, not truncated. These names used to end in an ellipsis —
              "Czujniki sterowni…", "Aktualizacja oprogramo…" — which tells you
              there is more without telling you what, on the one list in the
              app you pick from without having seen the names anywhere else.
              A second line costs less than a name you cannot read. */}
          <div className="font-medium wrap-break-word leading-6">
            {sectionConfig?.title}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0 mt-0.5">
        {/* The same count the group header carries. On the header alone it
            only says "something in here", and with the group open there are
            three rows it could mean. Repeating it is how a folder and the
            item inside it both show a count. */}
        {countBadge !== undefined && countBadge > 0 && (
          <span className="badge badge-error badge-sm">{countBadge}</span>
        )}
        {/* Against the right edge, where the badges line up with each other
            instead of sitting wherever each title happens to end. */}
        {sectionConfig?.badge && (
          <span
            className="badge badge-xs badge-warning font-bold uppercase whitespace-nowrap"
            title={t(`settings.badge_${sectionConfig.badge}_title`)}
          >
            {t(`settings.badge_${sectionConfig.badge}`)}
          </span>
        )}
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
  outstanding,
  onNavigate,
}: {
  sections: ConfigSection[];
  filterSections: SectionConfig[];
  configSections: SectionConfig[];
  activeSection: string;
  saveStatus: Record<string, 'idle' | 'saving' | 'success' | 'error'>;
  unsavedChanges: Record<string, boolean>;
  /** Security findings still to act on, shown on the security row. */
  outstanding?: number;
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
              countBadge={section.name === 'security' ? outstanding : undefined}
              onClick={() => onNavigate(section.name)}
            />
          );
        })}
    </div>
  );
}

/**
 * Sidebar content.
 *
 * Thirty-seven sections in seven groups is 2569px of list in a 689px sheet —
 * measured, not guessed. Fully expanded, that is close to four screens of
 * scrolling on a phone to reach anything near the bottom. So neither surface
 * shows everything at once any more, and each does it the way its own shape
 * allows:
 *
 * **Desktop** keeps the persistent column and collapses it to an accordion,
 * with the active section's group open. The column sits beside the form rather
 * than covering it, which is the whole reason a sidebar beats a menu there —
 * turning it into a separate step would throw that away.
 *
 * **Mobile** is already a modal sheet: opening it covers the content and
 * choosing dismisses it. Since it is a separate screen regardless, making it
 * two costs one tap and no context. Groups first as tiles, then that group's
 * sections — the arrangement every phone's own settings app uses.
 *
 * **The filter spans both**, and is the fast path for anyone who knows the
 * name. With text in it, groups stop mattering and matches are listed flat.
 */
function SidebarContent({
  sections,
  configSections,
  activeSection,
  saveStatus,
  unsavedChanges,
  onNavigate,
  variant,
}: Omit<SettingsSidebarProps, 'isSidebarOpen' | 'onSidebarToggle'> & {
  variant: 'desktop' | 'mobile';
}) {
  const { t } = useTranslation();

  const [filter, setFilter] = useState('');
  // Which group is open. Desktop starts on the active section's group; mobile
  // starts on none, which is what shows the tiles.
  const groupOfActive = configSections.find(s => s.name === activeSection)?.group ?? null;
  const [openGroup, setOpenGroup] = useState<string | null>(
    variant === 'desktop' ? groupOfActive : null,
  );

  // Following a link from elsewhere — a security finding's Fix button, say —
  // must open the group it landed in, or the sidebar would disagree with the
  // page beside it. React's own pattern for adjusting state when a prop
  // changes: compare during render, no effect, no ref.
  const [syncedTo, setSyncedTo] = useState(activeSection);
  if (syncedTo !== activeSection) {
    setSyncedTo(activeSection);
    if (variant === 'desktop' && groupOfActive && groupOfActive !== openGroup) {
      setOpenGroup(groupOfActive);
    }
  }

  const { posture } = useSecurityPosture();
  const outstanding = posture?.summary.actionable ?? 0;

  const grouped = SECTION_GROUPS.map(group => ({
    ...group,
    entries: configSections.filter(section => section.group === group.name),
  })).filter(group => group.entries.length > 0);

  const query = filter.trim().toLowerCase();
  const matches = query
    ? configSections.filter(section => section.title.toLowerCase().includes(query))
    : [];

  const isLoading = sections.length === 0;

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="skeleton h-12 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  const searchBox = (
    <label className="input input-sm bg-base-100 border-base-content/10 flex items-center gap-2 mb-3 focus-within:outline-none focus-within:ring-2 focus-within:ring-primary/30">
      <FaSearch className="w-3.5 h-3.5 opacity-40 shrink-0" />
      <input
        type="text"
        className="grow border-0 bg-transparent focus:outline-none min-w-0"
        placeholder={t('settings.filter_placeholder')}
        value={filter}
        onChange={e => setFilter(e.target.value)}
        autoComplete="off"
      />
      {filter && (
        <button
          className="opacity-40 hover:opacity-100 shrink-0"
          onClick={() => setFilter('')}
          aria-label={t('settings.filter_clear')}
        >
          <FaTimes className="w-3 h-3" />
        </button>
      )}
    </label>
  );

  if (query) {
    return (
      <>
        {searchBox}
        {matches.length === 0 ? (
          <p className="text-sm opacity-60 px-1 py-4">{t('settings.filter_empty')}</p>
        ) : (
          <SectionList
            sections={sections}
            filterSections={matches}
            configSections={configSections}
            activeSection={activeSection}
            saveStatus={saveStatus}
            unsavedChanges={unsavedChanges}
            outstanding={outstanding}
            onNavigate={onNavigate}
          />
        )}
      </>
    );
  }

  // Mobile, no group chosen yet: the tiles.
  if (variant === 'mobile' && openGroup === null) {
    return (
      <>
        {searchBox}
        <div className="grid grid-cols-2 gap-2">
          {grouped.map(group => (
            <button
              key={group.name}
              className="btn h-auto py-4 flex flex-col gap-1 normal-case"
              onClick={() => setOpenGroup(group.name)}
            >
              <span className="text-2xl" aria-hidden="true">{group.icon}</span>
              <span className="text-sm font-medium">{t(group.translationKey)}</span>
              {/* A bare number rather than "N items": Polish inflects the
                  noun three ways by count and this `t` has no plural forms,
                  so any phrasing would be wrong for some of them. */}
              <span className="text-xs opacity-60 flex items-center gap-1.5">
                {group.entries.length}
                {group.name === 'access' && outstanding > 0 && (
                  <span className="badge badge-error badge-xs">{outstanding}</span>
                )}
              </span>
            </button>
          ))}
        </div>
      </>
    );
  }

  // Mobile, inside a group: back plus that group's sections.
  if (variant === 'mobile') {
    const group = grouped.find(g => g.name === openGroup);
    if (!group) return searchBox;
    return (
      <>
        {searchBox}
        <button
          className="btn btn-sm btn-ghost gap-2 mb-2"
          onClick={() => setOpenGroup(null)}
        >
          ← {t('settings.all_groups')}
        </button>
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="text-sm font-semibold opacity-80">
            {group.icon} {t(group.translationKey)}
          </span>
        </div>
        <SectionList
          sections={sections}
          filterSections={group.entries}
          configSections={configSections}
          activeSection={activeSection}
          saveStatus={saveStatus}
          unsavedChanges={unsavedChanges}
          outstanding={outstanding}
          onNavigate={onNavigate}
        />
      </>
    );
  }

  // Desktop: accordion.
  return (
    <>
      {searchBox}
      {grouped.map(group => {
        const isOpen = openGroup === group.name;
        const holdsActive = group.entries.some(e => e.name === activeSection);
        return (
          <div
            key={group.name}
            className={`mb-2 rounded-xl border ${holdsActive ? 'border-primary/30 bg-primary/5' : 'border-base-content/8 bg-base-100/70'}`}
          >
            <button
              className="w-full flex items-center gap-2 px-3 py-2.5 text-left"
              onClick={() => setOpenGroup(isOpen ? null : group.name)}
              aria-expanded={isOpen}
            >
              <span aria-hidden="true">{group.icon}</span>
              <span className="text-sm font-semibold opacity-80 flex-1">
                {t(group.translationKey)}
              </span>
              {group.name === 'access' && outstanding > 0 && (
                <span className="badge badge-error badge-sm">{outstanding}</span>
              )}
              <span className="text-xs opacity-50">
                {isOpen ? '▾' : `${group.entries.length} ▸`}
              </span>
            </button>
            {isOpen && (
              <div className="px-3 pb-3">
                <SectionList
                  sections={sections}
                  filterSections={group.entries}
                  configSections={configSections}
                  activeSection={activeSection}
                  saveStatus={saveStatus}
                  unsavedChanges={unsavedChanges}
                  outstanding={outstanding}
                  onNavigate={onNavigate}
                />
              </div>
            )}
          </div>
        );
      })}
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
  configSections,
  activeSection,
  saveStatus,
  unsavedChanges,
  isSidebarOpen,
  onSidebarToggle,
  onNavigate,
}: SettingsSidebarProps) {
  const { t } = useTranslation();
  const activeSectionConfig = configSections.find(s => s.name === activeSection);
  const hasActiveUnsaved = activeSection === 'mqtt'
    ? (unsavedChanges['mqtt'] || unsavedChanges['lox_udp'] || false)
    : (unsavedChanges[activeSection] || false);

  /** Navigate to section and close mobile bottom sheet. */
  const handleMobileNavigate = (sectionName: string) => {
    onNavigate(sectionName);
    onSidebarToggle(false);
  };

  // Save and Restore used to live here too, which is how the same button
  // ended up in three different places depending on the section and the
  // window width. They are in SettingsActionBar now, at the bottom of the
  // content column at every size — this bar is navigation.
  
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
        sheetTitle={t('settings.configuration_sections')}
      >
        <SidebarContent
          sections={sections}
          configSections={configSections}
          activeSection={activeSection}
          saveStatus={saveStatus}
          unsavedChanges={unsavedChanges}
          onNavigate={handleMobileNavigate}
          variant="mobile"
        />
      </BottomPeekBar>

      {/* Desktop version - always visible sidebar */}
      <div className="hidden lg:block w-80 shrink-0 stg-canvas border-r border-base-content/8 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-base-content/45 mb-3 px-1">
            {t('settings.configuration_sections')}
          </h2>
          <SidebarContent
            sections={sections}
            configSections={configSections}
            activeSection={activeSection}
            saveStatus={saveStatus}
            unsavedChanges={unsavedChanges}
            onNavigate={onNavigate}
            variant="desktop"
          />
        </div>
      </div>
    </>
  );
}
