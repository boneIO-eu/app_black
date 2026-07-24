import { useState } from 'react';
import {
  FaExclamationTriangle,
  FaSpinner,
  FaDownload,
  FaFileArchive,
  FaUndo,
  FaTrash,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { useNodeRedManagement, NodeRedBackup } from '../hooks/useNodeRedManagement';

export default function NodeRedManagement() {
  const { t } = useTranslation();
  const {
    status,
    backups,
    updateInfo,
    updateProgress,
    isLoadingStatus,
    isCheckingUpdate,
    isCreatingBackup,
    isRestoringBackup,
    isUpdating,
    error,
    setError,
    createBackup,
    restoreBackup,
    deleteBackup,
    downloadBackup,
    checkUpdates,
    performUpdate,
  } = useNodeRedManagement();

  const [showBackupsList, setShowBackupsList] = useState(false);

  const handleCreateBackup = async () => {
    const success = await createBackup();
    if (success) {
      alert(t('nodered_management.backup_created'));
    }
  };

  const handleRestoreBackup = async (backup: NodeRedBackup) => {
    if (confirm(`${t('nodered_management.confirm_restore')}\n${t('nodered_management.restore_warning')}`)) {
      const success = await restoreBackup(backup.path);
      if (success) {
        alert(t('nodered_management.backup_restored'));
      }
    }
  };

  const handleDeleteBackup = async (backup: NodeRedBackup) => {
    if (confirm(t('nodered_management.confirm_delete'))) {
      const success = await deleteBackup(backup.path);
      if (success) {
        alert(t('nodered_management.backup_deleted'));
      }
    }
  };

  const handleUpdate = async () => {
    if (confirm(`${t('nodered_management.confirm_update')}\n${t('nodered_management.update_warning')}`)) {
      await performUpdate();
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  if (isLoadingStatus && !status) {
    return (
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body items-center justify-center p-8">
          <FaSpinner className="animate-spin text-primary h-8 w-8" />
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-base-200 shadow-xl">
      <div className="card-body">
        {/* Title & Status */}
        <div className="flex lg:items-center justify-between flex-col lg:flex-row gap-2 mb-4">
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <span>Node-RED</span>
              {status && (
                <span className={`badge ${status.running ? 'badge-success' : 'badge-error'} badge-sm`}>
                  {status.running ? t('nodered_management.status_running') : t('nodered_management.status_stopped')}
                </span>
              )}
            </h2>
            <p className="text-sm opacity-70 mt-1">
              {t('nodered_management.title')}
            </p>
          </div>
          {status && (
            <div className="text-right">
              <span className="text-xs opacity-60 block">{t('nodered_management.current_version')}</span>
              <span className="font-mono font-bold text-primary">{status.version}</span>
            </div>
          )}
        </div>

        {error && (
          <div className="alert alert-error my-2">
            <FaExclamationTriangle className="shrink-0" />
            <span>{error}</span>
            <button className="btn btn-outline btn-sm btn-circle" onClick={() => setError(null)}>
              ×
            </button>
          </div>
        )}

        {/* ── UPDATE SECTION ── */}
        <div className="border border-base-content/10 rounded-lg p-4 bg-base-100/50 mb-6">
          <h3 className="text-lg font-semibold flex items-center gap-2 mb-2">
            <span>{t('nodered_management.update_title')}</span>
            {updateInfo?.update_available && (
              <span className="badge badge-success badge-sm">{t('nodered_management.update_available')}</span>
            )}
          </h3>

          {updateInfo && (
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mt-2">
              <div className="flex gap-6">
                <div>
                  <span className="text-xs opacity-60 block">{t('nodered_management.current_version')}</span>
                  <span className="font-mono">{updateInfo.current_version}</span>
                </div>
                <div>
                  <span className="text-xs opacity-60 block">{t('nodered_management.latest_version')}</span>
                  <span className="font-mono font-bold text-success">{updateInfo.latest_version}</span>
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  className="btn btn-outline btn-sm"
                  onClick={checkUpdates}
                  disabled={isCheckingUpdate || isUpdating}
                >
                  {isCheckingUpdate ? <FaSpinner className="animate-spin" /> : t('nodered_management.check_for_updates')}
                </button>
                
                {updateInfo.update_available && (
                  <button
                    className="btn btn-success btn-sm gap-2"
                    onClick={handleUpdate}
                    disabled={isUpdating}
                  >
                    {isUpdating ? <FaSpinner className="animate-spin" /> : <FaDownload />}
                    {t('nodered_management.update_now')}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Update Progress Indicator */}
          {isUpdating && updateProgress && (
            <div className="mt-4 p-3 bg-base-300/50 rounded-lg">
              <div className="flex justify-between text-sm mb-1 font-medium">
                <span>{updateProgress.step}</span>
                <span>{updateProgress.progress}%</span>
              </div>
              <progress
                className="progress progress-primary w-full"
                value={updateProgress.progress}
                max="100"
              />
              {updateProgress.log.length > 0 && (
                <div className="mt-2 bg-black/30 p-2 rounded text-xs font-mono max-h-24 overflow-y-auto">
                  {updateProgress.log.map((logStr, i) => (
                    <div key={i}>{logStr}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── BACKUP SECTION ── */}
        <div className="border border-base-content/10 rounded-lg p-4 bg-base-100/50">
          <h3 className="text-lg font-semibold flex items-center gap-2 mb-2">
            <FaFileArchive className="text-primary" />
            <span>{t('nodered_management.backup_title')}</span>
          </h3>
          <p className="text-sm opacity-70 mb-4">
            {t('nodered_management.backup_description')}
          </p>

          <div className="flex gap-2 mb-4">
            <button
              className="btn btn-primary btn-sm gap-2"
              onClick={handleCreateBackup}
              disabled={isCreatingBackup || isRestoringBackup || isUpdating}
            >
              {isCreatingBackup ? <FaSpinner className="animate-spin" /> : <FaFileArchive />}
              {t('nodered_management.create_backup')}
            </button>

            {backups.length > 0 && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowBackupsList(!showBackupsList)}
              >
                {showBackupsList 
                  ? `${t('device_management.hide_backups') || 'Hide backups'} (${backups.length})` 
                  : `${t('device_management.show_backups') || 'Show backups'} (${backups.length})`}
              </button>
            )}
          </div>

          <div className="alert alert-info text-xs py-2 mb-4">
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
            <span>{t('nodered_management.backup_limit_info')}</span>
          </div>

          {/* List of Node-RED backups */}
          {showBackupsList && backups.length > 0 && (
            <div className="overflow-x-auto mt-2">
              <table className="table table-sm w-full">
                <thead>
                  <tr>
                    <th>{t('nodered_management.version')}</th>
                    <th>{t('nodered_management.date')}</th>
                    <th>{t('nodered_management.size')}</th>
                    <th className="text-right">{t('nodered_management.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {backups.map((backup) => (
                    <tr key={backup.path} className="hover:bg-base-200/50">
                      <td className="font-mono text-xs">{backup.version}</td>
                      <td className="text-xs">{backup.timestamp}</td>
                      <td className="text-xs">{formatSize(backup.size)}</td>
                      <td className="text-right">
                        <div className="flex gap-1 justify-end">
                          <button
                            className="btn btn-warning btn-xs gap-1"
                            onClick={() => handleRestoreBackup(backup)}
                            disabled={isRestoringBackup || isUpdating}
                            title={t('nodered_management.restore_backup')}
                          >
                            <FaUndo />
                            {t('nodered_management.restore_backup')}
                          </button>
                          <button
                            className="btn btn-info btn-xs"
                            onClick={() => downloadBackup(backup.path, backup.filename)}
                            title={t('nodered_management.download_backup')}
                          >
                            <FaDownload />
                          </button>
                          <button
                            className="btn btn-error btn-xs"
                            onClick={() => handleDeleteBackup(backup)}
                            title={t('nodered_management.delete_backup')}
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

          {showBackupsList && backups.length === 0 && (
            <p className="text-sm opacity-60 mt-2 italic">{t('nodered_management.no_backups')}</p>
          )}
        </div>
      </div>
    </div>
  );
}
