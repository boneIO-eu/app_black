import React, { useState, useEffect, useCallback, useContext } from 'react';
import {
  FaRedo,
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

/** Which block of the old System page to render. */
export type SystemSection = 'update' | 'tools' | 'hardware_errors';

interface SystemStateProps {
  section?: SystemSection;
}

import { useLocation } from 'react-router-dom';
import { WebSocketContext } from '../../App';
import { OutputEvent } from '../../hooks/useWebSocket';
import { useTranslation } from '@/hooks/useTranslation';
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

/**
 * What was the System page, now a set of Settings sections.
 *
 * @param section Which block to render.
 */
const SystemState: React.FC<SystemStateProps> = ({ section = 'tools' }) => {
  const { outputs } = useContext(WebSocketContext);
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

  // React Router does not scroll to a #fragment on navigation, so a deep link
  // from the Security section would land at the top of a long page and look
  // like it did nothing. The frame waits for the sections below to mount.
  const { hash } = useLocation();
  useEffect(() => {
    if (!hash) return;
    const id = requestAnimationFrame(() => {
      document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' });
    });
    return () => cancelAnimationFrame(id);
  }, [hash]);

  // Restart state
  // The restart banner lives in Settings now, with the sections that raise it.
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
    if (!confirm(t('device_management.restart_app_confirm'))) {
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

  // Rendered a piece at a time.
  //
  // The page this came from is gone; its blocks are now Settings sections.
  // They are selected by prop rather than split into separate files because
  // the software-update flow installs firmware, and separating three hundred
  // lines of its markup from the state that drives it — with no way to
  // rehearse a real update from here — is where a subtle break would come
  // from. The state stays where it was; only one branch is ever mounted.
  //
  // Splitting it properly is worth doing once an update can be exercised
  // end to end on a spare controller.
  if (section === 'update') {
    return (
      <div className="space-y-6">
        {/* Error Alert */}
        {error && (
          <div className="alert alert-error text-sm">
            <FaExclamationTriangle className="shrink-0" />
            <span>{error}</span>
            <button className="btn btn-outline btn-sm btn-circle ml-auto" onClick={() => setError(null)}>
              ×
            </button>
          </div>
        )}

        {/* Software Update Status Card */}
        <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
          <div className="card-body p-4 sm:p-6 space-y-5">
            {/* Current Version & Check */}
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="text-xs opacity-60 font-medium uppercase tracking-wider block">
                  {t('software_update.current_version')}
                </span>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-2xl sm:text-3xl font-mono font-bold text-primary">
                    {updateInfo?.current_version || '...'}
                  </span>
                  {updateInfo?.update_available && (
                    <span className="badge badge-success badge-sm font-semibold">
                      {t('software_update.update_available')}
                    </span>
                  )}
                  {updateInfo?.status === 'success' && !updateInfo?.update_available && (
                    <span className="badge badge-info badge-sm">{t('software_update.up_to_date')}</span>
                  )}
                </div>
              </div>
              <button
                className="btn btn-sm btn-primary"
                onClick={checkForUpdates}
                disabled={isChecking || isUpdating}
              >
                {isChecking ? (
                  <>
                    <FaSpinner className="animate-spin mr-1" />
                    {t('software_update.checking') || 'Checking...'}
                  </>
                ) : (
                  t('software_update.check_for_updates')
                )}
              </button>
            </div>

            {/* Prerelease Available Card (for stable users) */}
            {updateInfo?.prerelease_update_available && !updateInfo?.update_available && (
              <div className="card bg-warning/10 border border-warning/30">
                <div className="card-body p-4 sm:p-5">
                  <h3 className="card-title text-warning text-base">
                    <FaExclamationTriangle /> {t('software_update.prerelease_available')}
                  </h3>
                  <p className="text-sm opacity-70">
                    {t('software_update.prerelease_available_description')}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div>
                      <p className="text-xs opacity-60">{t('software_update.prerelease_version')}</p>
                      <p className="text-xl font-mono font-bold">
                        {updateInfo.latest_prerelease}
                        <span className="badge badge-warning badge-xs ml-2">dev</span>
                      </p>
                    </div>
                    <div>
                      <p className="text-xs opacity-60">{t('software_update.your_stable_version')}</p>
                      <p className="text-base font-mono">
                        {updateInfo.current_version}
                        <span className="badge badge-success badge-xs ml-2">stable</span>
                      </p>
                    </div>
                  </div>
                  <div className="alert alert-warning text-xs mt-3">
                    <FaExclamationTriangle className="shrink-0" />
                    <span>{t('software_update.prerelease_warning')}</span>
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
                      className="btn btn-outline btn-sm"
                    >
                      {t('software_update.view_release_notes')}
                    </a>
                    <button
                      className="btn btn-warning btn-sm"
                      onClick={() => startUpdate(updateInfo.latest_prerelease)}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <>
                          <FaSpinner className="animate-spin mr-1" />
                          {t('software_update.updating')}
                        </>
                      ) : (
                        <>
                          <FaDownload className="mr-1" />
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
              <div className="card bg-success/10 border border-success/30">
                <div className="card-body p-4 sm:p-5">
                  <h3 className="card-title text-success text-base">
                    <FaDownload /> {t('software_update.new_version_available')}
                  </h3>

                  {/* Version selector */}
                  <div className="form-control w-full max-w-xs">
                    <label className="label p-0 pb-1">
                      <span className="label-text text-xs font-medium">{t('software_update.select_version')}</span>
                    </label>
                    <select
                      className="select select-bordered select-sm"
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
                    <label className="label p-0 pt-1">
                      <span className="label-text-alt text-xs">
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
                      <p className="text-xs opacity-60">{t('software_update.selected_version')}</p>
                      <p className="text-xl font-mono font-bold">
                        {selectedVersion || updateInfo.latest_version}
                        {(selectedVersion || updateInfo.latest_version)
                          ?.toLowerCase()
                          .includes('dev') && <span className="badge badge-warning badge-xs ml-2">dev</span>}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs opacity-60">{t('software_update.released')}</p>
                      <p className="text-base">
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
                      className="btn btn-outline btn-sm"
                    >
                      {t('software_update.view_release_notes')}
                    </a>
                    <button
                      className="btn btn-success btn-sm"
                      onClick={() => startUpdate(selectedVersion || updateInfo.latest_version)}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <>
                          <FaSpinner className="animate-spin mr-1" />
                          {t('software_update.updating')}
                        </>
                      ) : (
                        <>
                          <FaDownload className="mr-1" />
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
              <div className="card bg-base-100 border border-base-content/10 shadow-sm">
                <div className="card-body p-4 sm:p-5">
                  <h3 className="card-title text-base">
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
          </div>
        </div>

        {/* Available Versions / Rollback Card */}
        <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
          <div className="card-body p-4 sm:p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base font-semibold flex items-center gap-2">
                <FaHistory className="text-secondary" />
                {t('software_update.available_versions') || 'Available Versions'}
              </h3>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => setShowVersions(!showVersions)}
              >
                {showVersions
                  ? t('software_update.hide_versions', { count: availableVersions.length })
                  : t('software_update.show_versions', { count: availableVersions.length })}
              </button>
            </div>
            <p className="text-sm opacity-70">{t('software_update.version_info') || 'Select a version to install. You can rollback to any previous version.'}</p>
            {showVersions && (
              <div className="mt-2">
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
                              {ver.is_current && <span className="badge badge-success badge-xs ml-2">{t('software_update.current') || 'Current'}</span>}
                            </td>
                            <td>{ver.published_at ? new Date(ver.published_at).toLocaleDateString() : '-'}</td>
                            <td>
                              {ver.prerelease ? (
                                <span className="badge badge-warning badge-xs">Pre-release</span>
                              ) : (
                                <span className="badge badge-success badge-xs">Stable</span>
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
    );
  }

  if (section === 'hardware_errors') {
    // HardwareErrors renders nothing when the list is empty, which was right
    // as a banner at the top of a page and is a blank screen as a section of
    // its own. A controller with no faults should say so.
    const faults = hardwareErrors.filter((e: { type?: string }) => e.type !== 'can_sudoers');
    return (
      <div className="space-y-6">
        {faults.length === 0 && (
          <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
            <div className="card-body p-4 sm:p-6">
              <h3 className="card-title text-base">{t('device_management.hardware_errors_title')}</h3>
              <p className="text-sm opacity-70">{t('device_management.no_hardware_errors')}</p>
            </div>
          </div>
        )}
        {/* Hardware Errors - Separate Container */}
        <HardwareErrors errors={hardwareErrors} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Self Test Section */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6 space-y-4">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <FaClipboardCheck className="text-primary" />
            {t('device_management.hardware_self_test')}
          </h3>
          <p className="text-sm opacity-70">
            {t('device_management.self_test_description')}
          </p>
          <div>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setShowSelfTest(true)}
              disabled={isUpdating}
            >
              <FaClipboardCheck />
              {t('device_management.start_self_test')}
            </button>
          </div>
          <div className="alert alert-info text-xs">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              className="stroke-current shrink-0 w-5 h-5"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              ></path>
            </svg>
            <div className="space-y-1">
              <p>{t('device_management.self_test_info_1')}</p>
              <p>{t('device_management.self_test_info_2')}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Turn Off All Outputs Section */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6 space-y-4">
          <h3 className="text-base font-semibold flex items-center gap-2 text-error">
            <FaPowerOff />
            {t('device_management.turn_off_all_outputs')}
          </h3>
          <p className="text-sm opacity-70">
            {t('device_management.turn_off_all_description')}
          </p>
          <div>
            <button
              className="btn btn-error btn-sm"
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
            <div className="mt-2">
              <div className="flex justify-between mb-1">
                <span className="text-xs">{t('device_management.turning_off_outputs')}</span>
                <span className="text-xs">
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
              className={`alert ${turnOffResult.errors.length > 0 ? 'alert-warning' : 'alert-success'} text-sm mt-2`}
            >
              <FaCheck className="shrink-0" />
              <div className="text-sm">
                <p>{t('device_management.turned_off_outputs', { count: turnOffResult.count })}</p>
                {turnOffResult.errors.length > 0 && (
                  <p>{t('device_management.errors')}: {turnOffResult.errors.join(', ')}</p>
                )}
              </div>
            </div>
          )}
          <div className="alert alert-warning text-xs mt-2">
            <FaExclamationTriangle className="shrink-0" />
            <div className="space-y-0.5">
              <p>{t('device_management.turn_off_warning_1')}</p>
              <p>{t('device_management.turn_off_warning_2')}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Fix App Permissions */}
      <FixAppPermissions />

      {/* Restart Application Section */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6 space-y-4">
          <h3 className="text-base font-semibold flex items-center gap-2 text-warning">
            <FaRedo />
            {t('device_management.restart_app')}
          </h3>
          <p className="text-sm opacity-70">
            {t('device_management.restart_app_description')}
          </p>
          <div>
            <button
              className="btn btn-warning btn-sm"
              onClick={handleRestart}
              disabled={isRestarting}
            >
              {isRestarting ? (
                <>
                  <FaSpinner className="animate-spin" />
                  {t('settings.restarting')}
                </>
              ) : (
                <>
                  <FaRedo />
                  {t('device_management.restart_app')}
                </>
              )}
            </button>
          </div>
          <div className="alert alert-warning text-xs mt-2">
            <FaExclamationTriangle className="shrink-0" />
            <p>{t('device_management.restart_app_warning')}</p>
          </div>
        </div>
      </div>

      {/* Self Test Modal */}
      <SelfTest isOpen={showSelfTest} onClose={() => setShowSelfTest(false)} />
    </div>
  );
};

export default SystemState;
