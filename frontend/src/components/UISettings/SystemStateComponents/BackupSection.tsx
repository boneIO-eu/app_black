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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

interface MismatchData {
  backupMeta: any;
  currentSerial: string;
  onConfirm: (keepOld: boolean) => void;
  onCancel: () => void;
}

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
  const [mismatchData, setMismatchData] = useState<MismatchData | null>(null);

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
      setError(t('backup.error'));
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
      setError(t('backup.error'));
      console.error('Error downloading backup:', err);
    }
  };

  const deleteBackup = async (backupPath: string, filename: string) => {
    if (!confirm(`${t('device_management.confirm_delete_backup') || 'Delete backup'} ${filename}?`)) return;
    try {
      const { data } = await axios.delete('/api/config/delete_backup', { data: { backup_path: backupPath } });
      if (data.status === 'success') {
        await fetchAvailableBackups();
        alert(data.message);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(t('backup.error'));
      console.error('Error deleting backup:', err);
    }
  };

  const handleRestoreResponse = async (data: any) => {
    if (data.status === 'success') {
      setRestoreResult(data);
      if (confirm(t('device_management.restore_success_restart'))) {
        await axios.post('/api/restart');
        setTimeout(() => window.location.reload(), 3000);
      }
    } else {
      setError(data.message || t('device_management.restore_failed'));
    }
  };

  const performPathRestore = async (backupPath: string, keepOld: boolean) => {
    setIsRestoring(true);
    try {
      const { data } = await axios.post(
        '/api/config/restore_backup',
        { backup_path: backupPath, override_serial: keepOld },
        { timeout: 30000 }
      );
      await handleRestoreResponse(data);
    } catch (err) {
      setError(t('device_management.restore_failed'));
      console.error('Error restoring config:', err);
    } finally {
      setIsRestoring(false);
    }
  };

  const restoreFromBackup = async (backupPath: string) => {
    setIsRestoring(true);
    setError(null);
    setRestoreResult(null);
    try {
      const { data: inspectData } = await axios.post('/api/config/inspect_backup_path', { backup_path: backupPath });
      
      if (inspectData.serial_mismatch) {
        setMismatchData({
          backupMeta: inspectData.backup_meta,
          currentSerial: inspectData.current_serial,
          onConfirm: (keepOld: boolean) => {
            setMismatchData(null);
            performPathRestore(backupPath, keepOld);
          },
          onCancel: () => {
            setMismatchData(null);
            setIsRestoring(false);
          }
        });
      } else {
        if (confirm(t('device_management.confirm_restore'))) {
          await performPathRestore(backupPath, false);
        } else {
          setIsRestoring(false);
        }
      }
    } catch (err) {
      setError(t('device_management.restore_failed'));
      console.error('Error inspecting backup path:', err);
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
      setError(t('backup.error'));
      console.error('Error downloading config:', err);
    } finally {
      setIsDownloading(false);
    }
  };

  const performFileRestore = async (file: File, keepOld: boolean) => {
    setIsRestoring(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('override_serial', keepOld ? 'true' : 'false');
      const { data } = await axios.post('/api/config/restore', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      });
      await handleRestoreResponse(data);
    } catch (err) {
      setError(t('device_management.restore_failed'));
      console.error('Error restoring config:', err);
    } finally {
      setIsRestoring(false);
    }
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setIsRestoring(true);
      setError(null);
      setRestoreResult(null);
      try {
        const formData = new FormData();
        formData.append('file', file);
        const { data: inspectData } = await axios.post('/api/config/inspect_backup_file', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });

        if (inspectData.serial_mismatch) {
          setMismatchData({
            backupMeta: inspectData.backup_meta,
            currentSerial: inspectData.current_serial,
            onConfirm: (keepOld: boolean) => {
              setMismatchData(null);
              performFileRestore(file, keepOld);
            },
            onCancel: () => {
              setMismatchData(null);
              setIsRestoring(false);
            }
          });
        } else {
          if (confirm(t('device_management.confirm_restore'))) {
            await performFileRestore(file, false);
          } else {
            setIsRestoring(false);
          }
        }
      } catch (err) {
        setError(t('device_management.restore_failed'));
        console.error('Error inspecting backup file:', err);
        setIsRestoring(false);
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
                {t('device_management.backup_created')}: {restoreResult.backup_path}
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
                  ? (t('device_management.hide_backups') || 'Hide backups ({count})').replace('{count}', String(availableBackups.length))
                  : (t('device_management.show_backups') || 'Show backups ({count})').replace('{count}', String(availableBackups.length))}
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
      {mismatchData && (
        <Dialog open={true} onOpenChange={(open) => { if (!open) mismatchData.onCancel(); }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-warning">
                <FaExclamationTriangle />
                {t('device_management.serial_mismatch_title') || 'Serial Number Mismatch'}
              </DialogTitle>
            </DialogHeader>
            <div className="py-4 text-sm space-y-4">
              <p>
                {t('device_management.serial_mismatch_desc') || 
                  'The uploaded configuration backup was created on a device with a different serial number:'}
              </p>
              
              <div className="bg-base-300 p-3 rounded-lg font-mono text-xs space-y-1">
                <div>
                  <span className="opacity-60">{t('device_management.backup_serial') || 'Backup Serial'}:</span>{' '}
                  <span className="text-warning font-semibold">
                    {mismatchData.backupMeta?.effective_serial || 'Unknown'}
                  </span>
                </div>
                {mismatchData.backupMeta?.hostname && (
                  <div>
                    <span className="opacity-60">{t('device_management.backup_hostname') || 'Backup Hostname'}:</span>{' '}
                    <span>{mismatchData.backupMeta.hostname}</span>
                  </div>
                )}
                {mismatchData.backupMeta?.created_at && (
                  <div>
                    <span className="opacity-60">{t('device_management.backup_created_at') || 'Created At'}:</span>{' '}
                    <span>{new Date(mismatchData.backupMeta.created_at).toLocaleString()}</span>
                  </div>
                )}
                <div>
                  <span className="opacity-60">{t('device_management.current_serial') || 'Current Serial'}:</span>{' '}
                  <span className="text-info font-semibold">{mismatchData.currentSerial}</span>
                </div>
              </div>

              <div className="alert alert-warning text-xs">
                <FaExclamationTriangle className="shrink-0" />
                <span>
                  {t('device_management.serial_override_warning') ||
                    'WARNING: If both controllers are running at the same time on the same MQTT broker with the same serial number, conflicts will occur!'}
                </span>
              </div>
            </div>
            <DialogFooter className="flex flex-col sm:flex-row gap-2">
              <button
                className="btn btn-warning btn-sm"
                onClick={() => mismatchData.onConfirm(true)}
              >
                {t('device_management.keep_old_serial') || 'Keep Old Serial'}
              </button>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => mismatchData.onConfirm(false)}
              >
                {t('device_management.use_new_serial') || 'Use New Serial'}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={mismatchData.onCancel}
              >
                {t('common.cancel') || 'Cancel'}
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
        </div>
      </div>
    </div>
  );
}
