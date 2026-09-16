/**
 * SectionHeader - the page header shared by every settings section.
 */
import { useState } from 'react';
import { FaQuestion } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { ALL_SECTIONS } from '../constants/sectionDefinitions';

interface SectionHeaderProps {
  sectionName: string;
  sectionTitle: string;
  sectionDescription?: string;
  children?: React.ReactNode;
}

/**
 * Header component with section title and description.
 *
 * It used to carry Save and Restore in its top right. They moved to
 * SettingsActionBar at the bottom of the content column, which is the one
 * place every section is now committed from — see the note there.
 *
 * Glass over the scrolling canvas rather than a flat `bg-base-200` bar: in
 * the light theme base-200 is 98% lightness, so the old header was a slightly
 * grey rectangle that read as nothing at all. The section's own icon comes
 * from the same list the sidebar draws from, so the page you land on is
 * visibly the row you clicked.
 */
export default function SectionHeader({
  sectionName,
  sectionTitle,
  sectionDescription,
  children,
}: SectionHeaderProps) {
  const { t } = useTranslation();
  const [helpOpen, setHelpOpen] = useState(false);
  const icon = ALL_SECTIONS.find(s => s.name === sectionName)?.icon;
  const description =
    sectionDescription
    || t(`sections.descriptions.${sectionName}`)
    || t('settings.configure_settings').replace('{section}', sectionTitle);

  return (
    <div className="stg-header px-4 py-3.5 lg:px-6 lg:py-4 shrink-0 z-20">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div className="flex items-start gap-3.5 min-w-0">
          {icon && (
            <div className="stg-chip w-11 h-11 rounded-xl hidden sm:flex items-center justify-center text-xl shrink-0">
              <span aria-hidden="true">{icon}</span>
            </div>
          )}
          <div className="min-w-0">
            <h1 className="text-xl lg:text-[26px] font-bold tracking-tight text-base-content flex items-center gap-2 leading-tight">
              {sectionTitle}
              {(sectionName === 'remote_devices' || sectionName === 'remote_inputs' || sectionName === 'remote_outputs') && (
                <span className="badge badge-warning badge-sm">{t('navigation.experimental')}</span>
              )}
              {/* The description moved in here. Several of them run to three
                  or four lines, which on a phone pushed the actual settings
                  below the fold before anything had been read. It is
                  orientation, not instruction — worth a tap, not a permanent
                  quarter of the screen. */}
              {description && (
                <button
                  type="button"
                  className="btn btn-circle btn-ghost btn-sm lg:btn-md shrink-0 bg-base-content/5 hover:bg-primary/10 text-base-content/50 hover:text-primary"
                  onClick={() => setHelpOpen(true)}
                  aria-label={t('common.help')}
                  title={description}
                >
                  <FaQuestion className="w-3 h-3 lg:w-3.5 lg:h-3.5" />
                </button>
              )}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {children}
        </div>
      </div>

      <Dialog open={helpOpen} onOpenChange={setHelpOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {icon && <span aria-hidden="true">{icon}</span>}
              {sectionTitle}
            </DialogTitle>
            <DialogDescription className="text-[13px] leading-relaxed whitespace-pre-line">
              {description}
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
