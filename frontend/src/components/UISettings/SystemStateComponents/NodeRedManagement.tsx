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
  FaExternalLinkAlt,
  FaServer,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { useNodeRedManagement, NodeRedBackup } from '../hooks/useNodeRedManagement';
import { SettingsCard, StatusTile, NoticeCallout } from '../ui';

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
    <div className="space-y-6">
      {/* Service Status Tile */}
      <StatusTile
        icon={<FaServer />}
        label={t('nodered_management.service_status') || 'Status usługi'}
        value={status?.running ? t('nodered_management.status_running') : t('nodered_management.status_stopped')}
        badge={
          <span
            className={`badge ${
              status?.running ? 'badge-success' : 'badge-error'
            } badge-sm font-semibold`}
          >
            {status?.version ? `v${status.version}` : (status?.running ? 'Online' : 'Offline')}
          </span>
        }
        action={
          status?.running ? (
            <a
              href="/nodered"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-sm btn-primary gap-2 font-medium"
            >
              <FaExternalLinkAlt className="w-3 h-3" />
              {t('nodered_management.open_nodered') || 'Otwórz Node-RED'}
            </a>
          ) : undefined
        }
      />

      {error && (
        <NoticeCallout
          variant="error"
          message={error}
          action={
            <button className="btn btn-ghost btn-xs btn-circle" onClick={() => setError(null)}>
              ×
            </button>
          }
        />
      )}

      {/* ── UPDATE SECTION ── */}
      <SettingsCard
        icon={<FaDownload />}
        title={t('nodered_management.update_title')}
        action={
          updateInfo?.update_available ? (
            <span className="badge badge-success badge-sm font-semibold">
              {t('nodered_management.update_available')}
            </span>
          ) : undefined
        }
      >
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-6">
              <div>
                <span className="text-xs text-base-content/60 block">
                  {t('nodered_management.current_version')}
                </span>
                <span className="font-mono text-sm font-bold text-base-content">
                  {updateInfo?.current_version || status?.version || '—'}
                </span>
              </div>
              {updateInfo?.latest_version && (
                <div>
                  <span className="text-xs text-base-content/60 block">
                    {t('nodered_management.latest_version')}
                  </span>
                  <span className="font-mono text-sm font-bold text-success">
                    {updateInfo.latest_version}
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <button
                className="btn btn-outline btn-sm gap-2"
                onClick={checkUpdates}
                disabled={isCheckingUpdate || isUpdating}
              >
                {isCheckingUpdate ? <FaSpinner className="animate-spin" /> : <FaDownload className="text-xs" />}
                {t('nodered_management.check_for_updates')}
              </button>

              {updateInfo?.update_available && (
                <button
                  className="btn btn-primary btn-sm gap-2"
                  onClick={handleUpdate}
                  disabled={isUpdating}
                >
                  {isUpdating ? <FaSpinner className="animate-spin" /> : <FaDownload className="text-xs" />}
                  {t('nodered_management.update_now')}
                </button>
              )}
            </div>
          </div>

          {/* Update Progress Indicator */}
          {isUpdating && updateProgress && (
            <div className="p-3.5 bg-base-200/60 border border-base-200 rounded-xl space-y-2">
              <div className="flex justify-between text-xs font-semibold text-base-content">
                <span>{updateProgress.step}</span>
                <span>{updateProgress.progress}%</span>
              </div>
              <progress
                className="progress progress-primary w-full"
                value={updateProgress.progress}
                max="100"
              />
              {updateProgress.log.length > 0 && (
                <div className="mt-2 bg-black/40 text-white p-2.5 rounded-lg text-xs font-mono max-h-24 overflow-y-auto">
                  {updateProgress.log.map((logStr, i) => (
                    <div key={i}>{logStr}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </SettingsCard>

      {/* ── BACKUP SECTION ── */}
      <SettingsCard
        icon={<FaFileArchive />}
        title={t('nodered_management.backup_title')}
        description={t('nodered_management.backup_description')}
      >
        <div className="relative space-y-4">
          {/* Restoring overlay */}
          {(isRestoringBackup || isUploadingRestore) && (
            <div className="absolute inset-0 bg-base-100/80 backdrop-blur-sm rounded-xl z-10 flex flex-col items-center justify-center gap-1.5 p-6">
              <FaSpinner className="animate-spin text-warning h-8 w-8" />
              <p className="text-sm font-semibold text-warning">{t('nodered_management.restoring_backup')}</p>
              <p className="text-xs text-base-content/60">{t('nodered_management.restoring_hint')}</p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              className="btn btn-primary btn-sm gap-2"
              onClick={handleCreateBackup}
              disabled={isCreatingBackup || isRestoringBackup || isUploadingRestore || isUpdating}
            >
              {isCreatingBackup ? <FaSpinner className="animate-spin" /> : <FaFileArchive className="text-xs" />}
              {t('nodered_management.create_backup')}
            </button>

            <button
              className="btn btn-outline btn-sm gap-2"
              onClick={() => setShowUploadDialog(true)}
              disabled={isRestoringBackup || isUploadingRestore || isUpdating}
            >
              <FaUpload className="text-xs" />
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

          <NoticeCallout
            variant="info"
            message={t('nodered_management.backup_limit_info')}
          />

          {/* List of Node-RED backups */}
          {showBackupsList && backups.length > 0 && (
            <div className="overflow-x-auto mt-2 border border-base-200 rounded-xl">
              <table className="table table-sm w-full">
                <thead>
                  <tr className="bg-base-200/50">
                    <th>{t('nodered_management.version')}</th>
                    <th>{t('nodered_management.date')}</th>
                    <th>{t('nodered_management.size')}</th>
                    <th>SHA256</th>
                    <th className="text-right">{t('nodered_management.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {backups.map((backup) => (
                    <tr key={backup.path} className="hover:bg-base-200/40">
                      <td className="font-mono text-xs font-semibold">{backup.version}</td>
                      <td className="text-xs text-base-content/70">{backup.timestamp}</td>
                      <td className="text-xs text-base-content/70">{formatSize(backup.size)}</td>
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
                            <FaUndo className="text-xs" />
                            {t('nodered_management.restore_backup')}
                          </button>
                          <button
                            className="btn btn-ghost btn-xs"
                            onClick={() => downloadBackup(backup.path, backup.filename)}
                            title={t('nodered_management.download_backup')}
                          >
                            <FaDownload className="text-xs" />
                          </button>
                          <button
                            className="btn btn-ghost btn-xs text-error hover:bg-error/10"
                            onClick={() => handleDeleteBackup(backup)}
                            title={t('nodered_management.delete_backup')}
                          >
                            <FaTrash className="text-xs" />
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
      </SettingsCard>

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
  );
}
