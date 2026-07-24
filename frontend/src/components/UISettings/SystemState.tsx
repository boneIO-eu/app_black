import React, { useState, useEffect, useCallback, useContext } from 'react';
import {
  FaDownload,
  FaUndo,
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
  FaHistory,
  FaClipboardCheck,
  FaPowerOff,
} from 'react-icons/fa';
import SelfTest from './SelfTest';
import FixAppPermissions from './FixAppPermissions';
import HardwareErrors from './HardwareErrors';
import MigrationsSection from './MigrationsSection';

import {
  DeviceControlSection,
  MqttPasswordsSection,
  HostnameSection,
  TimezoneSection,
  SslSection,
  FactoryResetSection,
  BackupSection,
  NodeRedManagement,
} from './SystemStateComponents';
import { WebSocketContext } from '../../App';
import { OutputEvent } from '../../hooks/useWebSocket';
import { useTranslation } from '@/hooks/useTranslation';
import { useNodeRedAvailability } from '@/hooks/useNodeRedAvailability';
import axios from '@/api/axios';

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
  current_is_prerelease?: boolean;
  latest_version?: string;
  latest_stable?: string;
  latest_prerelease?: string;
  update_available?: boolean;
  prerelease_update_available?: boolean;
  release_url?: string;
  published_at?: string;
  is_prerelease?: boolean;
  message?: string;
  available_versions?: VersionInfo[];
}

interface AvailableVersion {
  version: string;
  name: string;
  published_at: string;
  prerelease: boolean;
  is_current: boolean;
}

const SystemState: React.FC = () => {
  const { outputs } = useContext(WebSocketContext);
  const { isNodeRedAvailable } = useNodeRedAvailability();
  const { t } = useTranslation();
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [availableVersions, setAvailableVersions] = useState<AvailableVersion[]>([]);
  const [isChecking, setIsChecking] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSelfTest, setShowSelfTest] = useState(false);
  const [isTurningOffAll, setIsTurningOffAll] = useState(false);
  const [turnOffResult, setTurnOffResult] = useState<{ count: number; errors: string[] } | null>(
    null
  );
  const [turnOffProgress, setTurnOffProgress] = useState<{ current: number; total: number } | null>(
    null
  );
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);

  // Restart state
  const [restartRequired, setRestartRequired] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);

  // Hardware errors state
  const [hardwareErrors, setHardwareErrors] = useState<any[]>([]);

  // Fetch hardware errors
  const fetchHardwareErrors = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/hardware/errors');
      setHardwareErrors(data.errors || []);
    } catch (err) {
      console.error('Failed to fetch hardware errors:', err);
    }
  }, []);

  // Check for updates
  const checkForUpdates = useCallback(async () => {
    setIsChecking(true);
    setError(null);
    try {
      const { data } = await axios.get('/api/check_update');
      setUpdateInfo(data);

      // Check if backend returned an error
      if (data.status === 'error') {
        setError(data.message || t('software_update.failed_to_check_updates_backend'));
      }

      // Also publish update state to MQTT so HA sees the result
      await axios.post('/api/check_update_now').catch(() => {});
    } catch (err) {
      setError(t('software_update.failed_to_check_updates'));
      console.error('Error checking for updates:', err);
    } finally {
      setIsChecking(false);
    }
  }, []);

  // Fetch available versions for rollback
  const fetchAvailableVersions = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/update/available_versions');
      setAvailableVersions(data.versions || []);
    } catch (err) {
      console.error('Error fetching available versions:', err);
    }
  }, []);


  // Handle application restart
  const handleRestart = async () => {
    if (!confirm(t('device_management.restart_required'))) {
      return;
    }

    setIsRestarting(true);
    try {
      await axios.post('/api/restart');
      // The server will restart, so we won't get a response
    } catch (error) {
      // Expected - server is restarting
      console.log('Server is restarting...');
    }
  };

  // Poll update status
  const pollUpdateStatus = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/update/status');
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
      const { data } = await axios.post('/api/update', { version: version || selectedVersion });

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
          setError(status.error || t('software_update.update_failed'));
        }
      }, 1000);
    } catch (err) {
      setError(t('software_update.failed_to_start_update'));
      setIsUpdating(false);
    }
  };

  // Rollback to specific version
  const performRollback = async (version: string) => {
    // Check config compatibility before rollback
    try {
      const { data: compat } = await axios.get('/api/update/check_config_compat', {
        params: { target_version: version },
      });

      if (compat.compatible === false) {
        const forceRollback = confirm(
          `⚠️ ${t('software_update.config_incompatible') || 'Configuration may be incompatible!'}\n\n` +
          `${compat.message}\n\n` +
          `${t('software_update.force_rollback_prompt') || 'Do you want to force the rollback anyway? This may cause configuration errors.'}`
        );
        if (!forceRollback) {
          return;
        }
      } else {
        if (!confirm(t('software_update.confirm_rollback') + ` (${version})`)) {
          return;
        }
      }
    } catch {
      // If compat check fails, fall back to simple confirm
      if (!confirm(t('software_update.confirm_rollback') + ` (${version})`)) {
        return;
      }
    }

    setIsUpdating(true);
    try {
      const { data } = await axios.post('/api/update/rollback', { version });

      if (data.status === 'started') {
        // Start polling for status
        pollUpdateStatus();
      } else {
        setError(data.message);
        setIsUpdating(false);
      }
    } catch (err) {
      setError(t('software_update.rollback_failed'));
      setIsUpdating(false);
    }
  };

  // Turn off all outputs (frontend implementation - calls turn_off for each output)
  const turnOffAllOutputs = async () => {
    if (!confirm(t('settings.confirm_turn_off'))) {
      return;
    }

    // Filter outputs - skip cover types
    const outputsToTurnOff = outputs.filter(
      (o: OutputEvent) => o.state?.type !== 'cover' && o.state?.type !== 'none'
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
        await axios.post(`/api/outputs/${output.entity_id}/turn_off`);
        count++;
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
    fetchAvailableVersions();
    fetchHardwareErrors();
  }, [checkForUpdates, fetchAvailableVersions, fetchHardwareErrors]);

  // Format date
  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString('pl-PL', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-6">
      {/* System migrations (bootstrap + pending migrations) */}
      <MigrationsSection />

      {/* Hardware Errors - Separate Container */}
      <HardwareErrors errors={hardwareErrors} />

      {/* Software Update Card */}
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex lg:items-center justify-between flex-col lg:flex-row gap-2">
              <h2 className="text-2xl font-bold">{t('software_update.title')}</h2>
              <div>
                <button
                  className="btn btn-sm"
                  onClick={checkForUpdates}
                  disabled={isChecking || isUpdating}
                >
                  {isChecking ? (
                    <FaSpinner className="animate-spin" />
                  ) : (
                    t('software_update.check_for_updates')
                  )}
                </button>
              </div>
            </div>

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

            {/* Current Version */}
            <div>
              <h3 className="text-sm font-medium opacity-70 mb-1">{t('software_update.current_version')}</h3>
              <div className="flex lg:items-center gap-4 flex-col lg:flex-row">
                <span className="text-3xl font-mono font-bold text-primary">
                  {updateInfo?.current_version || '...'}
                </span>
                {updateInfo?.update_available && (
                  <span className="badge badge-success badge-lg">
                    {t('software_update.update_available')}
                  </span>
                )}
                {updateInfo?.status === 'success' && !updateInfo?.update_available && (
                  <span className="badge badge-info">{t('software_update.up_to_date')}</span>
                )}
              </div>
            </div>

            {/* Prerelease Available Card (for stable users) */}
            {updateInfo?.prerelease_update_available && !updateInfo?.update_available && (
              <div className="card bg-warning/10 border border-warning">
                <div className="card-body">
                  <h3 className="card-title text-warning">
                    <FaExclamationTriangle /> {t('software_update.prerelease_available')}
                  </h3>
                  <p className="text-sm opacity-70">
                    {t('software_update.prerelease_available_description')}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div>
                      <p className="text-sm opacity-70">{t('software_update.prerelease_version')}</p>
                      <p className="text-2xl font-mono font-bold">
                        {updateInfo.latest_prerelease}
                        <span className="badge badge-warning ml-2">dev</span>
                      </p>
                    </div>
                    <div>
                      <p className="text-sm opacity-70">{t('software_update.your_stable_version')}</p>
                      <p className="text-lg font-mono">
                        {updateInfo.current_version}
                        <span className="badge badge-success ml-2">stable</span>
                      </p>
                    </div>
                  </div>
                  <div className="alert alert-warning mt-4">
                    <FaExclamationTriangle />
                    <span className="text-sm">{t('software_update.prerelease_warning')}</span>
                  </div>
                  <div className="card-actions justify-end mt-4">
                    <a
                      href={
                        updateInfo.available_versions?.find(
                          v => v.version === updateInfo.latest_prerelease
                        )?.release_url
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-outline"
                    >
                      {t('software_update.view_release_notes')}
                    </a>
                    <button
                      className="btn btn-warning"
                      onClick={() => startUpdate(updateInfo.latest_prerelease)}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <>
                          <FaSpinner className="animate-spin" />
                          {t('software_update.updating')}
                        </>
                      ) : (
                        <>
                          <FaDownload />
                          {t('software_update.install_prerelease')}
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Update Available Card */}
            {updateInfo?.update_available && (
              <div className="card bg-success/10 border border-success">
                <div className="card-body">
                  <h3 className="card-title text-success">
                    <FaDownload /> {t('software_update.new_version_available')}
                  </h3>

                  {/* Version selector */}
                  <div className="form-control w-full max-w-xs">
                    <label className="label">
                      <span className="label-text">{t('software_update.select_version')}</span>
                    </label>
                    <select
                      className="select select-bordered"
                      value={selectedVersion || updateInfo.latest_version || ''}
                      onChange={e => setSelectedVersion(e.target.value)}
                    >
                      {updateInfo.available_versions?.map(ver => (
                        <option key={ver.version} value={ver.version}>
                          {ver.version} {ver.is_prerelease ? '(dev)' : ''}
                          {ver.version === updateInfo.latest_stable ? ' ⭐' : ''}
                        </option>
                      ))}
                    </select>
                    <label className="label">
                      <span className="label-text-alt">
                        {updateInfo.latest_stable && (
                          <span className="text-success">
                            ⭐ {t('software_update.recommended')}: {updateInfo.latest_stable}
                          </span>
                        )}
                      </span>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div>
                      <p className="text-sm opacity-70">{t('software_update.selected_version')}</p>
                      <p className="text-2xl font-mono font-bold">
                        {selectedVersion || updateInfo.latest_version}
                        {(selectedVersion || updateInfo.latest_version)
                          ?.toLowerCase()
                          .includes('dev') && <span className="badge badge-warning ml-2">dev</span>}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm opacity-70">{t('software_update.released')}</p>
                      <p className="text-lg">
                        {updateInfo.available_versions?.find(
                          v => v.version === (selectedVersion || updateInfo.latest_version)
                        )?.published_at
                          ? formatDate(
                              updateInfo.available_versions.find(
                                v => v.version === (selectedVersion || updateInfo.latest_version)
                              )!.published_at
                            )
                          : t('software_update.unknown')}
                      </p>
                    </div>
                  </div>

                  <div className="card-actions justify-end mt-4">
                    <a
                      href={
                        updateInfo.available_versions?.find(
                          v => v.version === (selectedVersion || updateInfo.latest_version)
                        )?.release_url || updateInfo.release_url
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-outline"
                    >
                      {t('software_update.view_release_notes')}
                    </a>
                    <button
                      className="btn btn-success"
                      onClick={() => startUpdate(selectedVersion || updateInfo.latest_version)}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <>
                          <FaSpinner className="animate-spin" />
                          {t('software_update.updating')}
                        </>
                      ) : (
                        <>
                          <FaDownload />
                          {t('software_update.update_to')}{' '}
                          {selectedVersion || updateInfo.latest_version}
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
                    {t('software_update.update_in_progress')}
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
                      <p className="text-sm font-medium mb-2">{t('software_update.log')}</p>
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
                        Update complete! Updated from {updateStatus.old_version} to{' '}
                        {updateStatus.new_version}. Restarting...
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

            {/* Available Versions Section */}
            <div className="divider"></div>
            <div>
              <div className="flex lg:items-center justify-between flex-col lg:flex-row gap-2">
                <h3 className="card-title">
                  <FaHistory />
                  {t('software_update.available_versions') || 'Available Versions'}
                </h3>
                <button
                  className="btn btn-outline btn-sm w-fit"
                  onClick={() => setShowVersions(!showVersions)}
                >
                  {showVersions
                    ? (t('software_update.hide_versions') || 'Hide versions ({count})').replace('{count}', String(availableVersions.length))
                    : (t('software_update.show_versions') || 'Show versions ({count})').replace('{count}', String(availableVersions.length))}
                </button>
              </div>
              <p className="text-sm opacity-70 mt-2">{t('software_update.version_info') || 'Select a version to install. You can rollback to any previous version.'}</p>
              {showVersions && (
                <div className="mt-4">
                  {availableVersions.length === 0 ? (
                    <p className="text-sm opacity-70">{t('software_update.no_versions') || 'No versions available'}</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="table table-sm">
                        <thead>
                          <tr>
                            <th>{t('software_update.version')}</th>
                            <th>{t('software_update.date')}</th>
                            <th>{t('software_update.type') || 'Type'}</th>
                            <th>{t('software_update.actions')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {availableVersions.map((ver: AvailableVersion) => (
                            <tr key={ver.version} className={ver.is_current ? 'bg-base-200' : ''}>
                              <td className="font-mono">
                                {ver.version}
                                {ver.is_current && <span className="badge badge-success badge-sm ml-2">{t('software_update.current') || 'Current'}</span>}
                              </td>
                              <td>{ver.published_at ? new Date(ver.published_at).toLocaleDateString() : '-'}</td>
                              <td>
                                {ver.prerelease ? (
                                  <span className="badge badge-warning badge-sm">Pre-release</span>
                                ) : (
                                  <span className="badge badge-success badge-sm">Stable</span>
                                )}
                              </td>
                              <td>
                                {!ver.is_current && (
                                  <button
                                    className="btn btn-warning btn-xs"
                                    onClick={() => performRollback(ver.version)}
                                    disabled={isUpdating}
                                  >
                                    <FaUndo />
                                    {t('software_update.install') || 'Install'}
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
            </div>
          </div>
        </div>
      </div>

      {/* Backup Card */}
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <h2 className="text-2xl font-bold">{t('backup.title')}</h2>
          <BackupSection />
        </div>
      </div>

      {/* Node-RED Management Card */}
      {isNodeRedAvailable && <NodeRedManagement />}

      {/* Device Management Card */}
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex lg:items-center justify-between flex-col lg:flex-row gap-2">
              <h2 className="text-2xl font-bold">{t('device_management.title')}</h2>
            </div>

            {/* Self Test Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaClipboardCheck />
                  {t('device_management.hardware_self_test')}
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  {t('device_management.self_test_description')}
                </p>
                <div className="card-actions">
                  <button
                    className="btn btn-secondary"
                    onClick={() => setShowSelfTest(true)}
                    disabled={isUpdating}
                  >
                    <FaClipboardCheck />
                    {t('device_management.start_self_test')}
                  </button>
                </div>
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
                    <p>{t('device_management.self_test_info_1')}</p>
                    <p>{t('device_management.self_test_info_2')}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Turn Off All Outputs Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">
                  <FaPowerOff />
                  {t('device_management.turn_off_all_outputs')}
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  {t('device_management.turn_off_all_description')}
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
                        {t('device_management.turning_off')}
                      </>
                    ) : (
                      <>
                        <FaPowerOff />
                        {t('device_management.turn_off_all_outputs')} (
                        {
                          outputs.filter(
                            (o: OutputEvent) =>
                              o.state?.type !== 'cover' && o.state?.type !== 'none'
                          ).length
                        }
                        )
                      </>
                    )}
                  </button>
                </div>
                {/* Progress bar during turn off */}
                {turnOffProgress && (
                  <div className="mt-4">
                    <div className="flex justify-between mb-1">
                      <span className="text-sm">{t('device_management.turning_off_outputs')}</span>
                      <span className="text-sm">
                        {turnOffProgress.current} / {turnOffProgress.total}
                      </span>
                    </div>
                    <progress
                      className="progress progress-error w-full"
                      value={turnOffProgress.current}
                      max={turnOffProgress.total}
                    />
                  </div>
                )}
                {turnOffResult && (
                  <div
                    className={`alert ${turnOffResult.errors.length > 0 ? 'alert-warning' : 'alert-success'} mt-4`}
                  >
                    <FaCheck />
                    <div className="text-sm">
                      <p>{t('device_management.turned_off_outputs').replace('{count}', String(turnOffResult.count))}</p>
                      {turnOffResult.errors.length > 0 && (
                        <p>{t('device_management.errors')}: {turnOffResult.errors.join(', ')}</p>
                      )}
                    </div>
                  </div>
                )}
                <div className="alert alert-warning mt-4">
                  <FaExclamationTriangle />
                  <div className="text-sm">
                    <p>{t('device_management.turn_off_warning_1')}</p>
                    <p>{t('device_management.turn_off_warning_2')}</p>
                  </div>
                </div>
              </div>
            </div>

            <DeviceControlSection />

            <HostnameSection />

            <TimezoneSection />

            <MqttPasswordsSection />

            <SslSection />

            <FactoryResetSection onRestartRequired={() => setRestartRequired(true)} />
          </div>
        </div>
      </div>

      {/* Fix App Permissions */}
      <FixAppPermissions />


      {/* Self Test Modal */}
      <SelfTest isOpen={showSelfTest} onClose={() => setShowSelfTest(false)} />

      {/* Restart required toast - persistent, with restart button */}
      {restartRequired && (
        <div className="toast toast-top toast-center z-50">
          <div className="alert alert-error shadow-lg">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="stroke-current shrink-0 h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div>
              <h3 className="font-bold">⚠️ {t('settings.app_restart_required')}</h3>
              <div className="text-xs">{t('settings.config_changed')}</div>
            </div>
            <button
              className="btn btn-sm btn-warning"
              onClick={handleRestart}
              disabled={isRestarting}
            >
              {isRestarting ? (
                <>
                  <span className="loading loading-spinner loading-xs"></span>
                  {t('settings.restarting')}
                </>
              ) : (
                `🔄 ${t('settings.restart_now')}`
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SystemState;
