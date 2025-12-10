import React, { useState, useEffect, useCallback, useContext, useRef } from 'react';
import { FaDownload, FaUndo, FaCheck, FaExclamationTriangle, FaSpinner, FaHistory, FaFileArchive, FaClipboardCheck, FaPowerOff, FaUpload } from 'react-icons/fa';
import SelfTest from './SelfTest';
import { WebSocketContext } from '../../App';
import { OutputEvent } from '../../hooks/useWebSocket';
import { useTranslation } from '@/hooks/useTranslation';

interface UpdateStatus {
  status: 'idle' | 'running' | 'success' | 'error';
  progress: number;
  step: string;
  log: string[];
  error: string | null;
  backup_path: string | null;
  old_version: string | null;
  new_version: string | null;
}

interface VersionInfo {
  version: string;
  is_prerelease: boolean;
  release_url: string;
  published_at: string;
}

interface UpdateInfo {
  status: string;
  current_version: string;
  latest_version?: string;
  latest_stable?: string;
  latest_prerelease?: string;
  update_available?: boolean;
  release_url?: string;
  published_at?: string;
  is_prerelease?: boolean;
  message?: string;
  available_versions?: VersionInfo[];
}

interface Backup {
  path: string;
  name: string;
  version: string;
  timestamp: string;
}

const SystemUpdate: React.FC = () => {
  const { outputs } = useContext(WebSocketContext);
  const { t } = useTranslation();
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [isChecking, setIsChecking] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [showBackups, setShowBackups] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [showSelfTest, setShowSelfTest] = useState(false);
  const [isTurningOffAll, setIsTurningOffAll] = useState(false);
  const [turnOffResult, setTurnOffResult] = useState<{ count: number; errors: string[] } | null>(null);
  const [turnOffProgress, setTurnOffProgress] = useState<{ current: number; total: number } | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreResult, setRestoreResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);

  // Check for updates
  const checkForUpdates = useCallback(async () => {
    setIsChecking(true);
    setError(null);
    try {
      const response = await fetch('/api/check_update');
      const data = await response.json();
      setUpdateInfo(data);
      
      // Check if backend returned an error
      if (data.status === 'error') {
        setError(data.message || t('system_update.failed_to_check_updates_backend'));
      }
    } catch (err) {
      setError(t('system_update.failed_to_check_updates'));
      console.error('Error checking for updates:', err);
    } finally {
      setIsChecking(false);
    }
  }, []);

  // Fetch backups
  const fetchBackups = useCallback(async () => {
    try {
      const response = await fetch('/api/update/backups');
      const data = await response.json();
      setBackups(data.backups || []);
    } catch (err) {
      console.error('Error fetching backups:', err);
    }
  }, []);

  // Poll update status
  const pollUpdateStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/update/status');
      const data = await response.json();
      setUpdateStatus(data);
      return data;
    } catch (err) {
      // Server might be restarting
      return null;
    }
  }, []);

  // Start update with specific version
  const startUpdate = async (version?: string) => {
    setIsUpdating(true);
    setError(null);
    
    try {
      const response = await fetch('/api/update', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version: version || selectedVersion })
      });
      const data = await response.json();
      
      if (data.status === 'error') {
        setError(data.message);
        setIsUpdating(false);
        return;
      }
      
      // Start polling for status
      const pollInterval = setInterval(async () => {
        const status = await pollUpdateStatus();
        
        if (!status) {
          // Server is restarting, wait and reload
          clearInterval(pollInterval);
          setTimeout(() => {
            window.location.reload();
          }, 5000);
          return;
        }
        
        if (status.status === 'success') {
          clearInterval(pollInterval);
          // Server will restart, wait and reload
          setTimeout(() => {
            window.location.reload();
          }, 3000);
        } else if (status.status === 'error') {
          clearInterval(pollInterval);
          setIsUpdating(false);
          setError(status.error || t('system_update.update_failed'));
        }
      }, 1000);
      
    } catch (err) {
      setError(t('system_update.failed_to_start_update'));
      setIsUpdating(false);
    }
  };

  // Rollback
  const performRollback = async () => {
    if (!confirm(t('system_update.confirm_rollback'))) {
      return;
    }
    
    try {
      const response = await fetch('/api/update/rollback', { method: 'POST' });
      const data = await response.json();
      
      if (data.status === 'success') {
        alert(`${data.message}\n\nClick OK to restart the application.`);
        // Trigger restart
        await fetch('/api/restart', { method: 'POST' });
        setTimeout(() => {
          window.location.reload();
        }, 3000);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(t('system_update.rollback_failed'));
    }
  };

  // Download config as tar.gz
  const downloadConfig = async () => {
    setIsDownloading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/config/download');
      
      if (!response.ok) {
        throw new Error('Failed to download configuration');
      }
      
      // Get filename from Content-Disposition header or use default
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = 'boneio_config.tar.gz';
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/);
        if (match) {
          filename = match[1];
        }
      }
      
      // Create blob and download
      const blob = await response.blob();
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

  // Restore config from tar.gz
  const restoreConfig = async (file: File) => {
    setIsRestoring(true);
    setError(null);
    setRestoreResult(null);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await fetch('/api/config/restore', {
        method: 'POST',
        body: formData,
      });
      
      const data = await response.json();
      
      if (data.status === 'success') {
        setRestoreResult(data);
        
        // Ask user if they want to restart
        if (confirm(t('system_update.restore_success_restart'))) {
          await fetch('/api/restart', { method: 'POST' });
          setTimeout(() => {
            window.location.reload();
          }, 3000);
        }
      } else {
        setError(data.message);
      }
      
    } catch (err) {
      setError(t('system_update.restore_failed'));
      console.error('Error restoring config:', err);
    } finally {
      setIsRestoring(false);
    }
  };

  // Handle file input change
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (confirm(t('system_update.confirm_restore'))) {
        restoreConfig(file);
      }
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Turn off all outputs (frontend implementation - calls turn_off for each output)
  const turnOffAllOutputs = async () => {
    if (!confirm(t('settings.confirm_turn_off'))) {
      return;
    }
    
    // Filter outputs - skip cover types
    const outputsToTurnOff = outputs.filter((o: OutputEvent) => 
      o.state?.type !== 'cover' && o.state?.type !== 'none'
    );
    
    if (outputsToTurnOff.length === 0) {
      setError(t('settings.no_outputs_to_turn_off'));
      return;
    }
    
    setIsTurningOffAll(true);
    setTurnOffResult(null);
    setTurnOffProgress({ current: 0, total: outputsToTurnOff.length });
    setError(null);
    
    let count = 0;
    const errors: string[] = [];
    
    for (let i = 0; i < outputsToTurnOff.length; i++) {
      const output = outputsToTurnOff[i];
      setTurnOffProgress({ current: i + 1, total: outputsToTurnOff.length });
      
      try {
        const response = await fetch(`/api/outputs/${output.entity_id}/turn_off`, { method: 'POST' });
        if (response.ok) {
          count++;
        } else {
          errors.push(output.entity_id);
        }
      } catch (err) {
        console.error(`Error turning off output ${output.entity_id}:`, err);
        errors.push(output.entity_id);
      }
      
      // Small delay between requests to avoid overwhelming the device
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    
    setTurnOffResult({ count, errors });
    setTurnOffProgress(null);
    setIsTurningOffAll(false);
  };

  // Initial load
  useEffect(() => {
    checkForUpdates();
    fetchBackups();
  }, [checkForUpdates, fetchBackups]);

  // Format date
  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString('pl-PL', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="container mx-auto p-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold">{t('system_update.title')}</h2>
              <button
                className="btn btn-ghost btn-sm"
                onClick={checkForUpdates}
                disabled={isChecking || isUpdating}
              >
                {isChecking ? <FaSpinner className="animate-spin" /> : t('system_update.check_for_updates')}
              </button>
            </div>

            {/* Error Alert */}
            {error && (
              <div className="alert alert-error">
                <FaExclamationTriangle />
                <span>{error}</span>
                <button className="btn btn-ghost btn-sm" onClick={() => setError(null)}>×</button>
              </div>
            )}

            {/* Current Version Card */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">{t('system_update.current_version')}</h3>
                <div className="flex items-center gap-4">
                  <span className="text-3xl font-mono font-bold text-primary">
                    {updateInfo?.current_version || '...'}
                  </span>
                  {updateInfo?.update_available && (
                    <span className="badge badge-success badge-lg">{t('system_update.update_available')}</span>
                  )}
                  {updateInfo?.status === 'success' && !updateInfo?.update_available && (
                    <span className="badge badge-info">{t('system_update.up_to_date')}</span>
                  )}
                </div>
              </div>
            </div>

            {/* Update Available Card */}
            {updateInfo?.update_available && (
              <div className="card bg-success/10 border border-success">
                <div className="card-body">
                  <h3 className="card-title text-success">
                    <FaDownload /> {t('system_update.new_version_available')}
                  </h3>
                  
                  {/* Version selector */}
                  <div className="form-control w-full max-w-xs">
                    <label className="label">
                      <span className="label-text">{t('system_update.select_version')}</span>
                    </label>
                    <select 
                      className="select select-bordered"
                      value={selectedVersion || updateInfo.latest_version || ''}
                      onChange={(e) => setSelectedVersion(e.target.value)}
                    >
                      {updateInfo.available_versions?.map((ver) => (
                        <option key={ver.version} value={ver.version}>
                          {ver.version} {ver.is_prerelease ? '(dev)' : ''} 
                          {ver.version === updateInfo.latest_stable ? ' ⭐' : ''}
                        </option>
                      ))}
                    </select>
                    <label className="label">
                      <span className="label-text-alt">
                        {updateInfo.latest_stable && (
                          <span className="text-success">⭐ {t('system_update.recommended')}: {updateInfo.latest_stable}</span>
                        )}
                      </span>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div>
                      <p className="text-sm opacity-70">{t('system_update.selected_version')}</p>
                      <p className="text-2xl font-mono font-bold">
                        {selectedVersion || updateInfo.latest_version}
                        {(selectedVersion || updateInfo.latest_version)?.toLowerCase().includes('dev') && (
                          <span className="badge badge-warning ml-2">dev</span>
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm opacity-70">{t('system_update.released')}</p>
                      <p className="text-lg">
                        {updateInfo.available_versions?.find(v => v.version === (selectedVersion || updateInfo.latest_version))?.published_at 
                          ? formatDate(updateInfo.available_versions.find(v => v.version === (selectedVersion || updateInfo.latest_version))!.published_at) 
                          : t('system_update.unknown')}
                      </p>
                    </div>
                  </div>

                  <div className="card-actions justify-end mt-4">
                    <a
                      href={updateInfo.available_versions?.find(v => v.version === (selectedVersion || updateInfo.latest_version))?.release_url || updateInfo.release_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-ghost"
                    >
                      {t('system_update.view_release_notes')}
                    </a>
                    <button
                      className="btn btn-success"
                      onClick={() => startUpdate(selectedVersion || updateInfo.latest_version)}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <>
                          <FaSpinner className="animate-spin" />
                          {t('system_update.updating')}
                        </>
                      ) : (
                        <>
                          <FaDownload />
                          {t('system_update.update_to')} {selectedVersion || updateInfo.latest_version}
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Update Progress */}
            {isUpdating && updateStatus && (
              <div className="card bg-base-200">
                <div className="card-body">
                  <h3 className="card-title">
                    <FaSpinner className="animate-spin" />
                    {t('system_update.update_in_progress')}
                  </h3>
                  
                  {/* Progress Bar */}
                  <div className="w-full">
                    <div className="flex justify-between mb-1">
                      <span className="text-sm font-medium">{updateStatus.step}</span>
                      <span className="text-sm font-medium">{updateStatus.progress}%</span>
                    </div>
                    <progress 
                      className="progress progress-primary w-full" 
                      value={updateStatus.progress} 
                      max="100"
                    />
                  </div>

                  {/* Log */}
                  {updateStatus.log.length > 0 && (
                    <div className="mt-4">
                      <p className="text-sm font-medium mb-2">{t('system_update.log')}</p>
                      <div className="bg-base-300 rounded-lg p-3 max-h-40 overflow-y-auto font-mono text-xs">
                        {updateStatus.log.map((msg, i) => (
                          <div key={i} className="py-0.5">
                            {msg}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {updateStatus.status === 'success' && (
                    <div className="alert alert-success mt-4">
                      <FaCheck />
                      <span>
                        Update complete! Updated from {updateStatus.old_version} to {updateStatus.new_version}.
                        Restarting...
                      </span>
                    </div>
                  )}

                  {updateStatus.status === 'error' && (
                    <div className="alert alert-error mt-4">
                      <FaExclamationTriangle />
                      <span>{updateStatus.error}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Self Test Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaClipboardCheck />
                  {t('system_update.hardware_self_test')}
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  {t('system_update.self_test_description')}
                </p>
                <div className="card-actions">
                  <button
                    className="btn btn-secondary"
                    onClick={() => setShowSelfTest(true)}
                    disabled={isUpdating}
                  >
                    <FaClipboardCheck />
                    {t('system_update.start_self_test')}
                  </button>
                </div>
                <div className="alert alert-info mt-4">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                  <div className="text-sm">
                    <p>{t('system_update.self_test_info_1')}</p>
                    <p>{t('system_update.self_test_info_2')}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Turn Off All Outputs Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaPowerOff />
                  {t('system_update.turn_off_all_outputs')}
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  {t('system_update.turn_off_all_description')}
                </p>
                <div className="card-actions">
                  <button
                    className="btn btn-error"
                    onClick={turnOffAllOutputs}
                    disabled={isUpdating || isTurningOffAll || outputs.length === 0}
                  >
                    {isTurningOffAll ? (
                      <>
                        <FaSpinner className="animate-spin" />
                        {t('system_update.turning_off')}
                      </>
                    ) : (
                      <>
                        <FaPowerOff />
                        {t('system_update.turn_off_all_outputs')} ({outputs.filter((o: OutputEvent) => o.state?.type !== 'cover' && o.state?.type !== 'none').length})
                      </>
                    )}
                  </button>
                </div>
                {/* Progress bar during turn off */}
                {turnOffProgress && (
                  <div className="mt-4">
                    <div className="flex justify-between mb-1">
                      <span className="text-sm">{t('system_update.turning_off_outputs')}</span>
                      <span className="text-sm">{turnOffProgress.current} / {turnOffProgress.total}</span>
                    </div>
                    <progress 
                      className="progress progress-error w-full" 
                      value={turnOffProgress.current} 
                      max={turnOffProgress.total}
                    />
                  </div>
                )}
                {turnOffResult && (
                  <div className={`alert ${turnOffResult.errors.length > 0 ? 'alert-warning' : 'alert-success'} mt-4`}>
                    <FaCheck />
                    <div className="text-sm">
                      <p>Turned off {turnOffResult.count} outputs.</p>
                      {turnOffResult.errors.length > 0 && (
                        <p>Errors: {turnOffResult.errors.join(', ')}</p>
                      )}
                    </div>
                  </div>
                )}
                <div className="alert alert-warning mt-4">
                  <FaExclamationTriangle />
                  <div className="text-sm">
                    <p>{t('system_update.turn_off_warning_1')}</p>
                    <p>{t('system_update.turn_off_warning_2')}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Configuration Backup Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaFileArchive />
                  {t('system_update.configuration_backup')}
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  {t('system_update.backup_description')}
                </p>
                
                {/* Backup/Restore buttons */}
                <div className="card-actions gap-2">
                  <button
                    className="btn btn-primary"
                    onClick={downloadConfig}
                    disabled={isDownloading || isUpdating || isRestoring}
                  >
                    {isDownloading ? (
                      <>
                        <FaSpinner className="animate-spin" />
                        {t('system_update.preparing')}
                      </>
                    ) : (
                      <>
                        <FaDownload />
                        {t('system_update.download_config')}
                      </>
                    )}
                  </button>
                  
                  <button
                    className="btn btn-secondary"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isDownloading || isUpdating || isRestoring}
                  >
                    {isRestoring ? (
                      <>
                        <FaSpinner className="animate-spin" />
                        {t('system_update.restoring')}
                      </>
                    ) : (
                      <>
                        <FaUpload />
                        {t('system_update.restore_config')}
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
                  <div className={`alert ${restoreResult.validation_status === 'success' ? 'alert-success' : 'alert-warning'} mt-4`}>
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
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                  <div className="text-sm">
                    <p>{t('system_update.backup_info_1')}</p>
                    <p>{t('system_update.backup_info_2')}</p>
                    <p className="mt-2 font-semibold">{t('system_update.restore_info')}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Backups Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <div className="flex items-center justify-between">
                  <h3 className="card-title">
                    <FaHistory />
                    {t('system_update.auto_update_backups')}
                  </h3>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setShowBackups(!showBackups)}
                  >
                    {showBackups ? `Hide Backups (${backups.length})` : `Show Backups (${backups.length})`}
                  </button>
                </div>

                {showBackups && (
                  <div className="mt-4">
                    {backups.length === 0 ? (
                      <p className="text-sm opacity-70">{t('system_update.no_backups')}</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="table table-sm">
                          <thead>
                            <tr>
                              <th>{t('system_update.version')}</th>
                              <th>{t('system_update.date')}</th>
                              <th>{t('system_update.actions')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {backups.map((backup, index) => (
                              <tr key={backup.path}>
                                <td className="font-mono">{backup.version}</td>
                                <td>{backup.timestamp.replace('_', ' ')}</td>
                                <td>
                                  {index === 0 && (
                                    <button
                                      className="btn btn-warning btn-xs"
                                      onClick={performRollback}
                                      disabled={isUpdating}
                                    >
                                      <FaUndo />
                                      {t('system_update.rollback')}
                                    </button>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                <div className="alert alert-info mt-4">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                  <div className="text-sm">
                    <p>{t('system_update.backup_info_3')}</p>
                    <p>{t('system_update.backup_info_4')}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      {/* Self Test Modal */}
      <SelfTest isOpen={showSelfTest} onClose={() => setShowSelfTest(false)} />
    </div>
  );
};

export default SystemUpdate;
