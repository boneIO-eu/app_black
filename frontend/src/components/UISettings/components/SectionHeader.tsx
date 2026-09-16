/**
 * SectionHeader - Header component for configuration section with action buttons.
 */
import { FaSave, FaEye, FaEyeSlash, FaUndo } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface SectionHeaderProps {
  sectionName: string;
  sectionTitle: string;
  sectionDescription?: string;
  showYamlPreview?: boolean;
  hasUnsavedChanges?: boolean;
  saveDisabled?: boolean;
  saveStatus?: 'idle' | 'saving' | 'success' | 'error';
  onToggleYamlPreview?: () => void;
  onRestore?: () => void;
  onSave?: () => void;
  hideYamlPreview?: boolean;
  children?: React.ReactNode;
}

/**
 * Header component with section title and action buttons.
 */
export default function SectionHeader({
  sectionName,
  sectionTitle,
  sectionDescription,
  showYamlPreview = false,
  hasUnsavedChanges = false,
  saveDisabled = false,
  saveStatus = 'idle',
  onToggleYamlPreview,
  onRestore,
  onSave,
  hideYamlPreview = false,
  children,
}: SectionHeaderProps) {
  const { t } = useTranslation();
  
  return (
    <div className="bg-base-200 border-b border-base-content/10 p-3 lg:p-4">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-base-content flex items-center gap-2">
            {sectionTitle}
            {(sectionName === 'remote_devices' || sectionName === 'remote_inputs' || sectionName === 'remote_outputs') && (
              <span className="badge badge-warning badge-sm">{t('navigation.experimental')}</span>
            )}
          </h1>
          <p className="text-sm text-base-content/70 mt-1">
            {sectionDescription || t(`sections.descriptions.${sectionName}`) || t('settings.configure_settings').replace('{section}', sectionTitle)}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {children}
          {!hideYamlPreview && onToggleYamlPreview && (
            <button
              onClick={onToggleYamlPreview}
              className="btn btn-ghost btn-sm"
              title={showYamlPreview ? t('settings.hide_yaml') : t('settings.show_yaml')}
            >
              {showYamlPreview ? <FaEyeSlash /> : <FaEye />}
              YAML
            </button>
          )}
          {/* Save/Restore — hidden on mobile, shown in bottom bar instead */}
          {hasUnsavedChanges && onRestore && (
            <button
              onClick={onRestore}
              className="btn btn-warning btn-sm hidden lg:inline-flex"
              title="Restore to last saved state"
            >
              <FaUndo />
              {t('settings.restore')}
            </button>
          )}
          {onSave && (
            <button
              onClick={onSave}
              disabled={!hasUnsavedChanges || saveDisabled}
              className="btn btn-primary btn-sm hidden lg:inline-flex"
            >
              {saveStatus === 'saving' ? (
                <div className="loading loading-spinner loading-xs"></div>
              ) : (
                <FaSave />
              )}
              {t('settings.save')} {sectionTitle}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
