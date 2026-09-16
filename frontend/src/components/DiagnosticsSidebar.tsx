import type { ReactNode } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { useConfig } from '@/contexts/ConfigContext';
import { BottomPeekBar } from '@/components/ui/bottom-peek-bar';
import { cn } from '@/lib/utils';
import { useCaptureWindow } from '../hooks/useCaptureWindow';
import {
  DIAGNOSTICS_GROUPS,
  DIAGNOSTICS_SECTIONS,
  type DiagnosticsSectionDef,
} from './diagnosticsSections';

interface SidebarProps {
  activeSection: string;
  onNavigate: (section: string) => void;
  isSheetOpen: boolean;
  onSheetOpenChange: (open: boolean) => void;
}

/** One row. Same shape as the settings sidebar, minus the save bookkeeping. */
function SectionButton({
  section,
  isActive,
  disabled,
  badge,
  onClick,
}: {
  section: DiagnosticsSectionDef;
  isActive: boolean;
  disabled: boolean;
  badge?: ReactNode;
  onClick: () => void;
}) {
  const { t } = useTranslation();

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'w-full text-left px-3 py-2.5 rounded-xl transition-colors duration-150 flex items-start gap-3',
        isActive
          ? 'bg-primary text-primary-content shadow-sm'
          : 'text-base-content hover:bg-base-content/6',
        disabled && 'opacity-40 cursor-not-allowed hover:bg-transparent',
      )}
    >
      <span className="text-lg leading-6 shrink-0" aria-hidden="true">{section.icon}</span>
      {/* Wrapped, not truncated. A name that ends in "…" tells you there is
          more without telling you what, and these are the only labels in the
          app you pick from without seeing them elsewhere first. */}
      <span className="font-medium min-w-0 flex-1 wrap-break-word leading-6">
        {t(section.titleKey)}
      </span>
      {badge}
    </button>
  );
}

/**
 * The list itself, shared by the desktop rail and the mobile sheet.
 *
 * Grouped like the settings tree, but never folded. Settings collapses its
 * groups because there are forty-odd sections and a rail that long is a wall;
 * here there are six, and all of them fit with room to spare. A chevron that
 * only ever hides something you can already see is a control that costs a
 * click and returns nothing.
 */
function SidebarContent({
  activeSection,
  onNavigate,
}: {
  activeSection: string;
  onNavigate: (section: string) => void;
}) {
  const { t } = useTranslation();
  const { canSupported } = useConfig();
  const { state: capture, clock } = useCaptureWindow();

  return (
    <>
      {DIAGNOSTICS_GROUPS.map(group => {
        const entries = DIAGNOSTICS_SECTIONS.filter(s => s.group === group.name);
        const holdsActive = entries.some(s => s.name === activeSection);

        return (
          <div
            key={group.name}
            className={cn(
              'mb-2 rounded-xl border',
              holdsActive
                ? 'border-primary/30 bg-primary/5'
                : 'border-base-content/8 bg-base-100/70',
            )}
          >
            <h3 className="flex items-center gap-2 px-3 py-2.5 text-sm font-semibold opacity-80">
              <span aria-hidden="true">{group.icon}</span>
              <span className="flex-1 wrap-break-word">{t(group.titleKey)}</span>
            </h3>

            <div className="px-3 pb-3 space-y-1">
              {entries.map(section => (
                <SectionButton
                  key={section.name}
                  section={section}
                  isActive={activeSection === section.name}
                  disabled={Boolean(section.requiresCan) && !canSupported}
                  badge={
                    section.name === 'support' && capture.active ? (
                      <span className="badge badge-warning badge-sm font-mono shrink-0">
                        {clock}
                      </span>
                    ) : undefined
                  }
                  onClick={() => onNavigate(section.name)}
                />
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}

/**
 * Diagnostics navigation — the settings sidebar's shape, with what this page
 * does not have taken out: no search over five entries, no unsaved-changes
 * dots for pages that save nothing.
 */
export default function DiagnosticsSidebar({
  activeSection,
  onNavigate,
  isSheetOpen,
  onSheetOpenChange,
}: SidebarProps) {
  const { t } = useTranslation();
  const active = DIAGNOSTICS_SECTIONS.find(s => s.name === activeSection);

  const navigateAndClose = (section: string) => {
    onNavigate(section);
    onSheetOpenChange(false);
  };

  return (
    <>
      {/* Mobile: bottom peek bar + sheet */}
      <BottomPeekBar
        open={isSheetOpen}
        onOpenChange={onSheetOpenChange}
        icon={active?.icon ?? '🩺'}
        label={active ? t(active.titleKey) : t('diagnostics.page_title')}
        sheetTitle={t('diagnostics.sections')}
      >
        <SidebarContent activeSection={activeSection} onNavigate={navigateAndClose} />
      </BottomPeekBar>

      {/* Desktop: always-visible rail */}
      <div className="hidden lg:block w-72 shrink-0 stg-canvas border-r border-base-content/8 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-base-content/45 mb-3 px-1">
            {t('diagnostics.sections')}
          </h2>
          <SidebarContent activeSection={activeSection} onNavigate={onNavigate} />
        </div>
      </div>
    </>
  );
}
