import React, { useState, useEffect, useCallback, useContext } from 'react';
import { FaDownload, FaUndo, FaCheck, FaExclamationTriangle, FaSpinner, FaHistory, FaFileArchive, FaClipboardCheck, FaPowerOff } from 'react-icons/fa';
import SelfTest from './SelfTest';
import { WebSocketContext } from '../../App';
import { OutputEvent } from '../../hooks/useWebSocket';

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

interface UpdateInfo {
  status: string;
  current_version: string;
  latest_version?: string;
  update_available?: boolean;
  release_url?: string;
  published_at?: string;
  is_prerelease?: boolean;
  message?: string;
}

interface Backup {
  path: string;
  name: string;
  version: string;
  timestamp: string;
}

const SystemUpdate: React.FC = () => {
  const { outputs } = useContext(WebSocketContext);
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
        setError(data.message || 'Failed to check for updates');
      }
    } catch (err) {
      setError('Failed to check for updates - network error');
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

  // Start update
  const startUpdate = async () => {
    setIsUpdating(true);
    setError(null);
    
    try {
      const response = await fetch('/api/update', { method: 'POST' });
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
          setError(status.error || 'Update failed');
        }
      }, 1000);
      
    } catch (err) {
      setError('Failed to start update');
      setIsUpdating(false);
    }
  };

  // Rollback
  const performRollback = async () => {
    if (!confirm('Are you sure you want to rollback to the previous version?')) {
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
      setError('Rollback failed');
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
      setError('Failed to download configuration');
      console.error('Error downloading config:', err);
    } finally {
      setIsDownloading(false);
    }
  };

  // Turn off all outputs (frontend implementation - calls turn_off for each output)
  const turnOffAllOutputs = async () => {
    if (!confirm('Are you sure you want to turn off ALL outputs?\n\nThis action cannot be undone.')) {
      return;
    }
    
    // Filter outputs - skip cover types
    const outputsToTurnOff = outputs.filter((o: OutputEvent) => 
      o.state?.type !== 'cover' && o.state?.type !== 'none'
    );
    
    if (outputsToTurnOff.length === 0) {
      setError('No outputs to turn off');
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
              <h2 className="text-2xl font-bold">System Update</h2>
              <button
                className="btn btn-ghost btn-sm"
                onClick={checkForUpdates}
                disabled={isChecking || isUpdating}
              >
                {isChecking ? <FaSpinner className="animate-spin" /> : 'Check for Updates'}
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
                <h3 className="card-title">Current Version</h3>
                <div className="flex items-center gap-4">
                  <span className="text-3xl font-mono font-bold text-primary">
                    {updateInfo?.current_version || '...'}
                  </span>
                  {updateInfo?.update_available && (
                    <span className="badge badge-success badge-lg">Update Available!</span>
                  )}
                  {updateInfo?.status === 'success' && !updateInfo?.update_available && (
                    <span className="badge badge-info">Up to date</span>
                  )}
                </div>
              </div>
            </div>

            {/* Update Available Card */}
            {updateInfo?.update_available && (
              <div className="card bg-success/10 border border-success">
                <div className="card-body">
                  <h3 className="card-title text-success">
                    <FaDownload /> New Version Available
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm opacity-70">Latest Version</p>
                      <p className="text-2xl font-mono font-bold">{updateInfo.latest_version}</p>
                    </div>
                    <div>
                      <p className="text-sm opacity-70">Released</p>
                      <p className="text-lg">{updateInfo.published_at ? formatDate(updateInfo.published_at) : 'Unknown'}</p>
                    </div>
                  </div>
                  {updateInfo.is_prerelease && (
                    <div className="badge badge-warning">Pre-release</div>
                  )}
                  <div className="card-actions justify-end mt-4">
                    <a
                      href={updateInfo.release_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-ghost"
                    >
                      View Release Notes
                    </a>
                    <button
                      className="btn btn-success"
                      onClick={startUpdate}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <>
                          <FaSpinner className="animate-spin" />
                          Updating...
                        </>
                      ) : (
                        <>
                          <FaDownload />
                          Update Now
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
                    Update in Progress
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
                      <p className="text-sm font-medium mb-2">Log:</p>
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
                  Hardware Self Test
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  Test all outputs and inputs on your device to verify they are working correctly.
                </p>
                <div className="card-actions">
                  <button
                    className="btn btn-secondary"
                    onClick={() => setShowSelfTest(true)}
                    disabled={isUpdating}
                  >
                    <FaClipboardCheck />
                    Start Self Test
                  </button>
                </div>
                <div className="alert alert-info mt-4">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                  <div className="text-sm">
                    <p>The test will toggle each output and wait for input events.</p>
                    <p>You can skip or fail individual tests as needed.</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Turn Off All Outputs Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaPowerOff />
                  Turn Off All Outputs
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  Turn off all outputs and clear saved relay states. Useful after testing or before shipping.
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
                        Turning off...
                      </>
                    ) : (
                      <>
                        <FaPowerOff />
                        Turn Off All Outputs ({outputs.filter((o: OutputEvent) => o.state?.type !== 'cover' && o.state?.type !== 'none').length})
                      </>
                    )}
                  </button>
                </div>
                {/* Progress bar during turn off */}
                {turnOffProgress && (
                  <div className="mt-4">
                    <div className="flex justify-between mb-1">
                      <span className="text-sm">Turning off outputs...</span>
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
                    <p>This will turn off ALL outputs immediately.</p>
                    <p>Saved relay states will be cleared - outputs will not restore on restart.</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Configuration Backup Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaFileArchive />
                  Configuration Backup
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  Download your current configuration files as a compressed archive.
                </p>
                <div className="card-actions">
                  <button
                    className="btn btn-primary"
                    onClick={downloadConfig}
                    disabled={isDownloading || isUpdating}
                  >
                    {isDownloading ? (
                      <>
                        <FaSpinner className="animate-spin" />
                        Preparing...
                      </>
                    ) : (
                      <>
                        <FaFileArchive />
                        Download Config (.tar.gz)
                      </>
                    )}
                  </button>
                </div>
                <div className="alert alert-info mt-4">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                  <div className="text-sm">
                    <p>The archive contains all YAML configuration files from your device.</p>
                    <p>Use this to backup your configuration before making major changes.</p>
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
                    Auto update Backups
                  </h3>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setShowBackups(!showBackups)}
                  >
                    {showBackups ? 'Hide' : 'Show'} Backups ({backups.length})
                  </button>
                </div>

                {showBackups && (
                  <div className="mt-4">
                    {backups.length === 0 ? (
                      <p className="text-sm opacity-70">No backups available yet.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="table table-sm">
                          <thead>
                            <tr>
                              <th>Version</th>
                              <th>Date</th>
                              <th>Actions</th>
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
                                      Rollback
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
                    <p>Backups are created automatically before each update.</p>
                    <p>The last 5 backups are kept. Use rollback if an update causes issues.</p>
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
