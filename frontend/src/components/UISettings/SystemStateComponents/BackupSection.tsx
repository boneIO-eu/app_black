import { useState, useCallback, useEffect, useRef } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
  FaDownload,
  FaUpload,
  FaFileArchive,
  FaUndo,
  FaTrash,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

/**
 * Section for configuration backup, restore, download, and management.
 */
export default function BackupSection() {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreResult, setRestoreResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [availableBackups, setAvailableBackups] = useState<any[]>([]);
  const [showAvailableBackups, setShowAvailableBackups] = useState(false);

  const fetchAvailableBackups = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/config/backups');
      setAvailableBackups(data.backups || []);
    } catch (err) {
      console.error('Error fetching available backups:', err);
    }
  }, []);

  useEffect(() => {
    fetchAvailableBackups();
  }, [fetchAvailableBackups]);

  const createBackupOnDisk = async () => {
    setIsDownloading(true);
    setError(null);
    try {
      const { data } = await axios.post('/api/config/create_backup');
      if (data.status === 'success') {
        await fetchAvailableBackups();
        alert(data.message);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(t('system_update.failed_to_check_updates'));
      console.error('Error creating backup:', err);
    } finally {
      setIsDownloading(false);
    }
  };

  const downloadBackupFromDisk = async (backupPath: string, filename: string) => {
    try {
      const response = await axios.get(`/api/config/download_backup?backup_path=${encodeURIComponent(backupPath)}`, { responseType: 'blob' });
      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(t('system_update.failed_to_check_updates'));
      console.error('Error downloading backup:', err);
    }
  };

  const deleteBackup = async (backupPath: string, filename: string) => {
    if (!confirm(`${t('system_update.confirm_delete_backup') || 'Delete backup'} ${filename}?`)) return;
    try {
      const { data } = await axios.delete('/api/config/delete_backup', { data: { backup_path: backupPath } });
      if (data.status === 'success') {
        await fetchAvailableBackups();
        alert(data.message);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(t('system_update.failed_to_check_updates'));
      console.error('Error deleting backup:', err);
    }
  };

  const restoreFromBackup = async (backupPath: string) => {
    if (!confirm(t('system_update.confirm_restore'))) return;
    setIsRestoring(true);
    setError(null);
    setRestoreResult(null);
    try {
      const { data } = await axios.post('/api/config/restore_backup', { backup_path: backupPath }, { timeout: 30000 });
      if (data.status === 'success') {
        setRestoreResult(data);
        if (data.restart_required) {
          if (confirm(t('system_update.restore_success_restart'))) {
            await axios.post('/api/restart');
            setTimeout(() => window.location.reload(), 3000);
          }
        }
      } else {
        setError(data.message || t('system_update.restore_failed'));
      }
    } catch (err) {
      setError(t('system_update.restore_failed'));
      console.error('Error restoring from backup:', err);
    } finally {
      setIsRestoring(false);
    }
  };

  const downloadConfig = async () => {
    setIsDownloading(true);
    setError(null);
    try {
      const response = await axios.get('/api/config/download', { responseType: 'blob' });
      const contentDisposition = response.headers['content-disposition'];
      let filename = 'boneio_config.tar.gz';
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/);
        if (match) filename = match[1];
      }
      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(t('system_update.failed_to_check_updates'));
      console.error('Error downloading config:', err);
    } finally {
      setIsDownloading(false);
    }
  };

  const restoreConfig = async (file: File) => {
    setIsRestoring(true);
    setError(null);
    setRestoreResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await axios.post('/api/config/restore', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      });
      if (data.status === 'success') {
        setRestoreResult(data);
        if (confirm(t('system_update.restore_success_restart'))) {
          await axios.post('/api/restart');
          setTimeout(() => window.location.reload(), 3000);
        }
      } else {
        setError(data.message || t('system_update.restore_failed'));
      }
    } catch (err) {
      setError(t('system_update.restore_failed'));
      console.error('Error restoring config:', err);
    } finally {
      setIsRestoring(false);
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (confirm(t('system_update.confirm_restore'))) {
        restoreConfig(file);
      }
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
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

        {/* Error Alert */}
        {error && (
          <div className="alert alert-error">
            <FaExclamationTriangle />
            <span>{error}</span>
            <button className="btn btn-outline btn-sm" onClick={() => setError(null)}>
              ×
            </button>
          </div>
        )}

        {/* Backup/Restore buttons */}
        <div className="card-actions gap-2">
          <button
            className="btn btn-primary"
            onClick={downloadConfig}
            disabled={isDownloading || isRestoring}
          >
            {isDownloading ? (
              <>
                <FaSpinner className="animate-spin" />
                {t('device_management.preparing')}
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
            disabled={isDownloading || isRestoring}
          >
            {isRestoring ? (
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

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".tar.gz,.tgz"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
        </div>

        {/* Restore result */}
        {restoreResult && (
          <div
            className={`alert ${restoreResult.validation_status === 'success' ? 'alert-success' : 'alert-warning'} mt-4`}
          >
            <FaCheck />
            <div className="text-sm">
              <p>{restoreResult.message}</p>
              <p className="text-xs opacity-70 mt-1">
                {t('system_update.backup_created')}: {restoreResult.backup_path}
              </p>
              {restoreResult.validation_status === 'warning' && (
                <p className="text-xs mt-1">{restoreResult.validation_message}</p>
              )}
            </div>
          </div>
        )}

        <div className="alert alert-info mt-4">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            className="stroke-current shrink-0 w-6 h-6"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            ></path>
          </svg>
          <div className="text-sm">
            <p>{t('device_management.backup_info_1')}</p>
            <p>{t('device_management.backup_info_2')}</p>
            <p className="mt-2 font-semibold">{t('device_management.restore_info')}</p>
          </div>
        </div>

        {/* Available Backups on Disk */}
        <div className="mt-4">
          <div className="flex gap-2 mb-2">
            <button
              className="btn btn-primary btn-sm"
              onClick={createBackupOnDisk}
              disabled={isDownloading || isRestoring}
            >
              {isDownloading ? (
                <>
                  <FaSpinner className="animate-spin" />
                  {t('device_management.preparing')}
                </>
              ) : (
                <>
                  <FaFileArchive />
                  {t('device_management.create_backup') || 'Create Backup'}
                </>
              )}
            </button>

            {availableBackups.length > 0 && (
              <button
                className="btn btn-sm"
                onClick={() => {
                  setShowAvailableBackups(!showAvailableBackups);
                  if (!showAvailableBackups) fetchAvailableBackups();
                }}
              >
                {showAvailableBackups
                  ? (t('system_update.hide_backups') || 'Hide backups ({count})').replace('{count}', String(availableBackups.length))
                  : (t('system_update.show_backups') || 'Show backups ({count})').replace('{count}', String(availableBackups.length))}
              </button>
            )}
          </div>

          <div className="alert alert-info text-xs mt-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              className="stroke-current shrink-0 w-4 h-4"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              ></path>
            </svg>
            <span>{t('device_management.backup_limit_info') || 'Maximum 10 backups are kept. Oldest backups are automatically removed when creating new ones.'}</span>
          </div>

          {showAvailableBackups && availableBackups.length > 0 && (
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>{t('device_management.version')}</th>
                    <th>{t('device_management.date')}</th>
                    <th>{t('device_management.files')}</th>
                    <th>{t('device_management.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {availableBackups.map((backup: any) => (
                    <tr key={backup.path}>
                      <td className="font-mono">{backup.version}</td>
                      <td className="text-xs">{backup.timestamp}</td>
                      <td>{backup.file_count} {t('device_management.yaml_files')}</td>
                      <td>
                        <div className="flex gap-1">
                          <button
                            className="btn btn-warning btn-xs"
                            onClick={() => restoreFromBackup(backup.path)}
                            disabled={isRestoring}
                            title={t('device_management.restore')}
                          >
                            <FaUndo />
                            {t('device_management.restore')}
                          </button>
                          <button
                            className="btn btn-info btn-xs"
                            onClick={() => downloadBackupFromDisk(backup.path, backup.filename)}
                            title={t('device_management.download_config')}
                          >
                            <FaDownload />
                          </button>
                          <button
                            className="btn btn-error btn-xs"
                            onClick={() => deleteBackup(backup.path, backup.filename)}
                            title={t('device_management.delete') || 'Delete'}
                          >
                            <FaTrash />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
