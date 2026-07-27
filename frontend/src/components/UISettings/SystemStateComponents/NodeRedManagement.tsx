import { useState, useRef, useCallback } from 'react';
import {
  FaExclamationTriangle,
  FaSpinner,
  FaDownload,
  FaFileArchive,
  FaUndo,
  FaTrash,
  FaUpload,
  FaCopy,
  FaCheck,
  FaShieldAlt,
  FaTimes,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { useNodeRedManagement, NodeRedBackup } from '../hooks/useNodeRedManagement';

/**
 * Compute SHA256 hash of a File using the Web Crypto API.
 *
 * Returns the hex-encoded digest string.
 */
async function computeFileSha256(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export default function NodeRedManagement() {
  const { t } = useTranslation();
  const {
    status,
    backups,
    updateInfo,
    updateProgress,
    isLoadingStatus,
    isLoadingBackups,
    isCheckingUpdate,
    isCreatingBackup,
    isRestoringBackup,
    isUploadingRestore,
    isUpdating,
    error,
    setError,
    createBackup,
    restoreBackup,
    deleteBackup,
    downloadBackup,
    uploadRestore,
    checkUpdates,
    performUpdate,
  } = useNodeRedManagement();

  const [showBackupsList, setShowBackupsList] = useState(false);

  // Upload restore dialog state
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadSha256Input, setUploadSha256Input] = useState('');
  const [computedSha256, setComputedSha256] = useState<string | null>(null);
  const [isComputingHash, setIsComputingHash] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // SHA256 copy feedback
  const [copiedSha256, setCopiedSha256] = useState<string | null>(null);

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

  const handleCopySha256 = useCallback(async (sha256: string) => {
    try {
      await navigator.clipboard.writeText(sha256);
      setCopiedSha256(sha256);
      setTimeout(() => setCopiedSha256(null), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = sha256;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopiedSha256(sha256);
      setTimeout(() => setCopiedSha256(null), 2000);
    }
  }, []);

  /** Handle file selection for upload restore. */
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadFile(file);
    setComputedSha256(null);

    // Compute SHA256 of the selected file
    setIsComputingHash(true);
    try {
      const hash = await computeFileSha256(file);
      setComputedSha256(hash);
    } catch (err) {
      console.error('Failed to compute SHA256:', err);
    } finally {
      setIsComputingHash(false);
    }
  }, []);

  /** Submit upload restore. */
  const handleUploadRestore = useCallback(async () => {
    if (!uploadFile) return;

    // If user provided SHA256 for verification, pass it to server
    const sha256ToVerify = uploadSha256Input.trim() || undefined;

    const success = await uploadRestore(uploadFile, sha256ToVerify);
    if (success) {
      setShowUploadDialog(false);
      setUploadFile(null);
      setUploadSha256Input('');
      setComputedSha256(null);
      alert(t('nodered_management.backup_restored'));
    }
  }, [uploadFile, uploadSha256Input, uploadRestore, t]);

  const closeUploadDialog = useCallback(() => {
    setShowUploadDialog(false);
    setUploadFile(null);
    setUploadSha256Input('');
    setComputedSha256(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  // SHA256 verification status
  const sha256VerifyStatus = (() => {
    if (!uploadSha256Input.trim() || !computedSha256) return null;
    const input = uploadSha256Input.trim().toLowerCase();
    const computed = computedSha256.toLowerCase();
    return input === computed ? 'match' : 'mismatch';
  })();

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
        <div className="border border-base-content/10 rounded-lg p-4 bg-base-100/50 relative">
          {/* Restoring overlay */}
          {(isRestoringBackup || isUploadingRestore) && (
            <div className="absolute inset-0 bg-base-100/80 backdrop-blur-sm rounded-lg z-10 flex flex-col items-center justify-center gap-1 pt-8">
              <FaSpinner className="animate-spin text-warning h-8 w-8" />
              <p className="text-sm font-semibold text-warning">{t('nodered_management.restoring_backup')}</p>
              <p className="text-xs opacity-60">{t('nodered_management.restoring_hint')}</p>
            </div>
          )}
          <h3 className="text-lg font-semibold flex items-center gap-2 mb-2">
            <FaFileArchive className="text-primary" />
            <span>{t('nodered_management.backup_title')}</span>
          </h3>
          <p className="text-sm opacity-70 mb-4">
            {t('nodered_management.backup_description')}
          </p>

          <div className="flex flex-wrap gap-2 mb-4">
            <button
              className="btn btn-primary btn-sm gap-2"
              onClick={handleCreateBackup}
              disabled={isCreatingBackup || isRestoringBackup || isUploadingRestore || isUpdating}
            >
              {isCreatingBackup ? <FaSpinner className="animate-spin" /> : <FaFileArchive />}
              {t('nodered_management.create_backup')}
            </button>

            <button
              className="btn btn-warning btn-sm gap-2"
              onClick={() => setShowUploadDialog(true)}
              disabled={isRestoringBackup || isUploadingRestore || isUpdating}
            >
              <FaUpload />
              {t('nodered_management.upload_restore')}
            </button>

            {backups.length > 0 && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowBackupsList(!showBackupsList)}
              >
                {showBackupsList 
                  ? t('device_management.hide_backups', { count: backups.length })
                  : t('device_management.show_backups', { count: backups.length })}
              </button>
            )}
            {isLoadingBackups && (
              <span className="flex items-center gap-2 text-sm opacity-60">
                <FaSpinner className="animate-spin h-3 w-3" />
                {t('common.loading')}
              </span>
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
                    <th>SHA256</th>
                    <th className="text-right">{t('nodered_management.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {backups.map((backup) => (
                    <tr key={backup.path} className="hover:bg-base-200/50">
                      <td className="font-mono text-xs">{backup.version}</td>
                      <td className="text-xs">{backup.timestamp}</td>
                      <td className="text-xs">{formatSize(backup.size)}</td>
                      <td className="text-xs">
                        {backup.sha256 ? (
                          <button
                            className="btn btn-ghost btn-xs gap-1 font-mono"
                            onClick={() => handleCopySha256(backup.sha256!)}
                            title={t('nodered_management.copy_sha256')}
                          >
                            <span className="max-w-[80px] truncate">{backup.sha256.slice(0, 12)}…</span>
                            {copiedSha256 === backup.sha256
                              ? <FaCheck className="text-success w-3 h-3" />
                              : <FaCopy className="w-3 h-3 opacity-60" />}
                          </button>
                        ) : (
                          <span className="opacity-40">—</span>
                        )}
                      </td>
                      <td className="text-right">
                        <div className="flex gap-1 justify-end">
                          <button
                            className="btn btn-warning btn-xs gap-1"
                            onClick={() => handleRestoreBackup(backup)}
                            disabled={isRestoringBackup || isUploadingRestore || isUpdating}
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

        {/* ── UPLOAD RESTORE DIALOG ── */}
        {showUploadDialog && (
          <>
            {/* Backdrop */}
            <div className="fixed inset-0 bg-black/50 z-40" onClick={closeUploadDialog} />
            {/* Dialog */}
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <div className="bg-base-100 rounded-xl shadow-2xl border border-base-300 w-full max-w-lg">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-base-300">
                  <h3 className="text-lg font-bold flex items-center gap-2">
                    <FaUpload className="text-warning" />
                    {t('nodered_management.upload_restore_title')}
                  </h3>
                  <button className="btn btn-ghost btn-sm btn-circle" onClick={closeUploadDialog}>
                    <FaTimes />
                  </button>
                </div>

                {/* Body */}
                <div className="p-4 space-y-4">
                  {/* File select */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('nodered_management.select_backup_file')}</span>
                    </label>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".tar.gz,.tgz"
                      className="file-input file-input-bordered file-input-sm w-full"
                      onChange={handleFileSelect}
                    />
                    {uploadFile && (
                      <label className="label">
                        <span className="label-text-alt">
                          {uploadFile.name} — {formatSize(uploadFile.size)}
                        </span>
                      </label>
                    )}
                  </div>

                  {/* Computed SHA256 */}
                  {(isComputingHash || computedSha256) && (
                    <div className="bg-base-200/60 rounded-lg p-3">
                      <div className="flex items-center gap-2 text-xs font-semibold mb-1">
                        <FaShieldAlt className="text-info" />
                        SHA256
                      </div>
                      {isComputingHash ? (
                        <div className="flex items-center gap-2 text-xs opacity-60">
                          <FaSpinner className="animate-spin" />
                          {t('nodered_management.sha256_computing')}
                        </div>
                      ) : computedSha256 ? (
                        <div className="flex items-center gap-1">
                          <code className="text-xs font-mono break-all flex-1 select-all">
                            {computedSha256}
                          </code>
                          <button
                            className="btn btn-ghost btn-xs shrink-0"
                            onClick={() => handleCopySha256(computedSha256)}
                            title={t('nodered_management.copy_sha256')}
                          >
                            {copiedSha256 === computedSha256
                              ? <FaCheck className="text-success" />
                              : <FaCopy className="opacity-60" />}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )}

                  {/* SHA256 verification input */}
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text text-sm">{t('nodered_management.sha256_optional')}</span>
                    </label>
                    <input
                      type="text"
                      className={`input input-bordered input-sm font-mono text-xs w-full ${
                        sha256VerifyStatus === 'match' ? 'input-success' :
                        sha256VerifyStatus === 'mismatch' ? 'input-error' : ''
                      }`}
                      placeholder={t('nodered_management.sha256_placeholder')}
                      value={uploadSha256Input}
                      onChange={e => setUploadSha256Input(e.target.value)}
                    />
                    {sha256VerifyStatus === 'match' && (
                      <label className="label">
                        <span className="label-text-alt text-success flex items-center gap-1">
                          <FaCheck className="w-3 h-3" />
                          {t('nodered_management.sha256_match')}
                        </span>
                      </label>
                    )}
                    {sha256VerifyStatus === 'mismatch' && (
                      <label className="label">
                        <span className="label-text-alt text-error flex items-center gap-1">
                          <FaExclamationTriangle className="w-3 h-3" />
                          {t('nodered_management.sha256_mismatch')}
                        </span>
                      </label>
                    )}
                  </div>

                  {/* Warning */}
                  <div className="alert alert-warning text-xs">
                    <FaExclamationTriangle className="shrink-0" />
                    <span>{t('nodered_management.upload_restore_warning')}</span>
                  </div>
                </div>

                {/* Footer */}
                <div className="flex justify-end gap-2 p-4 border-t border-base-300">
                  <button className="btn btn-ghost btn-sm" onClick={closeUploadDialog}>
                    {t('common.cancel')}
                  </button>
                  <button
                    className="btn btn-warning btn-sm gap-2"
                    disabled={
                      !uploadFile
                      || isUploadingRestore
                      || sha256VerifyStatus === 'mismatch'
                      || isComputingHash
                    }
                    onClick={handleUploadRestore}
                  >
                    {isUploadingRestore ? <FaSpinner className="animate-spin" /> : <FaUndo />}
                    {t('nodered_management.restore_backup')}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
