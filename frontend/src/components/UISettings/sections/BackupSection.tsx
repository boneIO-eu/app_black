import React, { useRef } from 'react';
import {
  FaFileArchive,
  FaDownload,
  FaUpload,
  FaSpinner,
  FaCheck,
  FaExclamationTriangle,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';

interface BackupSectionProps {
  isCreatingBackup: boolean;
  isRestoringBackup: boolean;
  backupResult: { status: string; message: string } | null;
  onCreateBackup: () => void;
  onRestoreBackup: (file: File) => void;
}

export const BackupSection: React.FC<BackupSectionProps> = ({
  isCreatingBackup,
  isRestoringBackup,
  backupResult,
  onCreateBackup,
  onRestoreBackup,
}) => {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onRestoreBackup(file);
    }
  };

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h3 className="card-title">
          <FaFileArchive />
          {t('device_management.configuration_backup')}
        </h3>
        <p className="text-sm opacity-70 mb-4">{t('device_management.backup_description')}</p>

        <div className="flex gap-2 flex-wrap">
          <button
            className="btn btn-primary"
            onClick={onCreateBackup}
            disabled={isCreatingBackup || isRestoringBackup}
          >
            {isCreatingBackup ? (
              <>
                <FaSpinner className="animate-spin" />
                {t('device_management.create_backup') || 'Create Backup'}
              </>
            ) : (
              <>
                <FaDownload />
                {t('device_management.download_config')}
              </>
            )}
          </button>

          <button
            className="btn btn-secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={isCreatingBackup || isRestoringBackup}
          >
            {isRestoringBackup ? (
              <>
                <FaSpinner className="animate-spin" />
                {t('device_management.restoring')}
              </>
            ) : (
              <>
                <FaUpload />
                {t('device_management.restore_config')}
              </>
            )}
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept=".tar.gz,.tgz"
            onChange={handleFileSelect}
            className="hidden"
          />
        </div>

        {backupResult && (
          <div
            className={`alert ${backupResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-4`}
          >
            {backupResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
            <span>{backupResult.message}</span>
          </div>
        )}

        <div className="alert alert-warning mt-4">
          <FaExclamationTriangle />
          <div className="text-sm">
            <p>{t('device_management.backup_warning') || 'Warning: Restoring will replace current configuration. A backup of current config will be created automatically.'}</p>
          </div>
        </div>
      </div>
    </div>
  );
};
