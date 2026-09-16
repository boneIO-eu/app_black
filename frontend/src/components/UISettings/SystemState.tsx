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
import {
  SettingsPage,
  SettingsCard,
  StatGrid,
  FormField,
  FormActions,
  NoticeCallout,
  CodeBlock,
  EmptyState,
} from './ui';

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
    const selected = selectedVersion || updateInfo?.latest_version;
    const selectedRelease = updateInfo?.available_versions?.find(v => v.version === selected);

    return (
      <SettingsPage width="wide">
        {/* Error */}
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

        {/* Installed version */}
        <SettingsCard
          footer={
            <FormActions>
              <button
                className="btn btn-primary btn-sm gap-2"
                onClick={checkForUpdates}
                disabled={isChecking || isUpdating}
              >
                {isChecking ? (
                  <>
                    <FaSpinner className="animate-spin" />
                    {t('software_update.checking') || 'Checking...'}
                  </>
                ) : (
                  t('software_update.check_for_updates')
                )}
              </button>
            </FormActions>
          }
        >
          <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-base-content/50 block">
                {t('software_update.current_version')}
              </span>
              <span className="text-3xl sm:text-4xl font-mono font-bold text-primary leading-none mt-1.5 block">
                {updateInfo?.current_version || '…'}
              </span>
            </div>
            <div className="pb-1">
              {updateInfo?.update_available && (
                <span className="badge badge-success badge-sm font-semibold">
                  {t('software_update.update_available')}
                </span>
              )}
              {updateInfo?.status === 'success' && !updateInfo?.update_available && (
                <span className="badge badge-ghost badge-sm">{t('software_update.up_to_date')}</span>
              )}
            </div>
          </div>
        </SettingsCard>

        {/* Prerelease available to someone on stable */}
        {updateInfo?.prerelease_update_available && !updateInfo?.update_available && (
          <SettingsCard
            variant="accent"
            icon={<FaExclamationTriangle />}
            title={t('software_update.prerelease_available')}
            description={t('software_update.prerelease_available_description')}
            footer={
              <FormActions>
                <a
                  href={
                    updateInfo.available_versions?.find(
                      v => v.version === updateInfo.latest_prerelease
                    )?.release_url
                  }
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-ghost btn-sm"
                >
                  {t('software_update.view_release_notes')}
                </a>
                <button
                  className="btn btn-warning btn-sm gap-2"
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
              </FormActions>
            }
          >
            <div className="space-y-4">
              <StatGrid
                columns={2}
                items={[
                  {
                    label: t('software_update.prerelease_version'),
                    mono: true,
                    value: (
                      <>
                        {updateInfo.latest_prerelease}
                        <span className="badge badge-warning badge-xs ml-2">dev</span>
                      </>
                    ),
                  },
                  {
                    label: t('software_update.your_stable_version'),
                    mono: true,
                    value: (
                      <>
                        {updateInfo.current_version}
                        <span className="badge badge-success badge-xs ml-2">stable</span>
                      </>
                    ),
                  },
                ]}
              />
              <NoticeCallout variant="warning" message={t('software_update.prerelease_warning')} />
            </div>
          </SettingsCard>
        )}

        {/* Update available */}
        {updateInfo?.update_available && (
          <SettingsCard
            variant="accent"
            icon={<FaDownload />}
            title={t('software_update.new_version_available')}
            footer={
              <FormActions>
                <a
                  href={selectedRelease?.release_url || updateInfo.release_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-ghost btn-sm"
                >
                  {t('software_update.view_release_notes')}
                </a>
                <button
                  className="btn btn-primary btn-sm gap-2"
                  onClick={() => startUpdate(selected)}
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
                      {t('software_update.update_to')} {selected}
                    </>
                  )}
                </button>
              </FormActions>
            }
          >
            <div className="space-y-4">
              <FormField
                label={t('software_update.select_version')}
                help={
                  updateInfo.latest_stable
                    ? `⭐ ${t('software_update.recommended')}: ${updateInfo.latest_stable}`
                    : undefined
                }
                className="max-w-sm"
              >
                <select
                  className="select select-bordered w-full font-mono"
                  value={selected || ''}
                  onChange={e => setSelectedVersion(e.target.value)}
                >
                  {updateInfo.available_versions?.map(ver => (
                    <option key={ver.version} value={ver.version}>
                      {ver.version} {ver.is_prerelease ? '(dev)' : ''}
                      {ver.version === updateInfo.latest_stable ? ' ⭐' : ''}
                    </option>
                  ))}
                </select>
              </FormField>

              <StatGrid
                columns={2}
                items={[
                  {
                    label: t('software_update.selected_version'),
                    mono: true,
                    value: (
                      <>
                        {selected}
                        {selected?.toLowerCase().includes('dev') && (
                          <span className="badge badge-warning badge-xs ml-2">dev</span>
                        )}
                      </>
                    ),
                  },
                  {
                    label: t('software_update.released'),
                    value: selectedRelease?.published_at
                      ? formatDate(selectedRelease.published_at)
                      : t('software_update.unknown'),
                  },
                ]}
              />
            </div>
          </SettingsCard>
        )}

        {/* Update progress */}
        {isUpdating && updateStatus && (
          <SettingsCard
            icon={<FaSpinner className="animate-spin" />}
            title={t('software_update.update_in_progress')}
          >
            <div className="space-y-4">
              <div>
                <div className="flex justify-between mb-1.5 text-[13px] font-medium">
                  <span>{updateStatus.step}</span>
                  <span className="font-mono">{updateStatus.progress}%</span>
                </div>
                <progress
                  className="progress progress-primary w-full"
                  value={updateStatus.progress}
                  max="100"
                />
              </div>

              {updateStatus.log.length > 0 && (
                <CodeBlock label={t('software_update.log')} maxHeight="10rem">
                  {updateStatus.log.join('\n')}
                </CodeBlock>
              )}

              {updateStatus.status === 'success' && (
                <NoticeCallout
                  variant="success"
                  message={`Update complete! Updated from ${updateStatus.old_version} to ${updateStatus.new_version}. Restarting...`}
                />
              )}

              {updateStatus.status === 'error' && (
                <NoticeCallout variant="error" message={updateStatus.error} />
              )}
            </div>
          </SettingsCard>
        )}

        {/* Available versions / rollback */}
        <SettingsCard
          icon={<FaHistory />}
          title={t('software_update.available_versions') || 'Available Versions'}
          description={
            t('software_update.version_info') ||
            'Select a version to install. You can rollback to any previous version.'
          }
          collapsible
          open={showVersions}
          onOpenChange={setShowVersions}
          summary={availableVersions.length}
        >
          {showVersions ? (
            availableVersions.length === 0 ? (
              <EmptyState
                icon={<FaHistory />}
                title={t('software_update.no_versions') || 'No versions available'}
              />
            ) : (
              <div className="stg-inset overflow-x-auto">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>{t('software_update.version')}</th>
                      <th>{t('software_update.date')}</th>
                      <th>{t('software_update.type') || 'Type'}</th>
                      <th className="text-right">{t('software_update.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {availableVersions.map((ver: AvailableVersion) => (
                      <tr key={ver.version} className={ver.is_current ? 'bg-primary/5' : ''}>
                        <td className="font-mono">
                          {ver.version}
                          {ver.is_current && (
                            <span className="badge badge-success badge-xs ml-2">
                              {t('software_update.current') || 'Current'}
                            </span>
                          )}
                        </td>
                        <td>{ver.published_at ? new Date(ver.published_at).toLocaleDateString() : '-'}</td>
                        <td>
                          {ver.prerelease ? (
                            <span className="badge badge-warning badge-xs">Pre-release</span>
                          ) : (
                            <span className="badge badge-ghost badge-xs">Stable</span>
                          )}
                        </td>
                        <td className="text-right">
                          {!ver.is_current && (
                            <button
                              className="btn btn-warning btn-xs gap-1.5"
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
            )
          ) : null}
        </SettingsCard>
      </SettingsPage>
    );
  }

  if (section === 'hardware_errors') {
    // HardwareErrors renders nothing when the list is empty, which was right
    // as a banner at the top of a page and is a blank screen as a section of
    // its own. A controller with no faults should say so.
    const faults = hardwareErrors.filter((e: { type?: string }) => e.type !== 'can_sudoers');
    return (
      <SettingsPage width="wide">
        {faults.length === 0 && (
          <SettingsCard>
            <EmptyState
              icon={<FaCheck className="text-success" />}
              title={t('device_management.hardware_errors_title')}
              description={t('device_management.no_hardware_errors')}
            />
          </SettingsCard>
        )}
        {/* Hardware Errors - Separate Container */}
        <HardwareErrors errors={hardwareErrors} />
      </SettingsPage>
    );
  }

  const switchableOutputs = outputs.filter(
    (o: OutputEvent) => o.state?.type !== 'cover' && o.state?.type !== 'none'
  ).length;

  return (
    <SettingsPage width="wide">
      {/* Self test */}
      <SettingsCard
        icon={<FaClipboardCheck />}
        title={t('device_management.hardware_self_test')}
        description={t('device_management.self_test_description')}
        footer={
          <FormActions>
            <button
              className="btn btn-primary btn-sm gap-2"
              onClick={() => setShowSelfTest(true)}
              disabled={isUpdating}
            >
              <FaClipboardCheck />
              {t('device_management.start_self_test')}
            </button>
          </FormActions>
        }
      >
        <NoticeCallout
          variant="info"
          message={
            <>
              <span className="block">{t('device_management.self_test_info_1')}</span>
              <span className="block">{t('device_management.self_test_info_2')}</span>
            </>
          }
        />
      </SettingsCard>

      {/* Turn off all outputs */}
      <SettingsCard
        variant="danger"
        icon={<FaPowerOff />}
        title={t('device_management.turn_off_all_outputs')}
        description={t('device_management.turn_off_all_description')}
        footer={
          <FormActions>
            <button
              className="btn btn-error btn-sm gap-2"
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
                  {t('device_management.turn_off_all_outputs')} ({switchableOutputs})
                </>
              )}
            </button>
          </FormActions>
        }
      >
        <div className="space-y-3">
          <NoticeCallout
            variant="warning"
            message={
              <>
                <span className="block">{t('device_management.turn_off_warning_1')}</span>
                <span className="block">{t('device_management.turn_off_warning_2')}</span>
              </>
            }
          />

          {/* Progress bar during turn off */}
          {turnOffProgress && (
            <div className="stg-inset p-3.5">
              <div className="flex justify-between mb-1.5 text-xs font-medium">
                <span>{t('device_management.turning_off_outputs')}</span>
                <span className="font-mono">
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
            <NoticeCallout
              variant={turnOffResult.errors.length > 0 ? 'warning' : 'success'}
              message={
                <>
                  <span className="block">
                    {t('device_management.turned_off_outputs', { count: turnOffResult.count })}
                  </span>
                  {turnOffResult.errors.length > 0 && (
                    <span className="block">
                      {t('device_management.errors')}: {turnOffResult.errors.join(', ')}
                    </span>
                  )}
                </>
              }
            />
          )}
        </div>
      </SettingsCard>

      {/* Fix App Permissions */}
      <FixAppPermissions />

      {/* Restart application */}
      <SettingsCard
        icon={<FaRedo />}
        title={t('device_management.restart_app')}
        description={t('device_management.restart_app_description')}
        footer={
          <FormActions>
            <button
              className="btn btn-warning btn-sm gap-2"
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
          </FormActions>
        }
      >
        <NoticeCallout variant="warning" message={t('device_management.restart_app_warning')} />
      </SettingsCard>

      {/* Self Test Modal */}
      <SelfTest isOpen={showSelfTest} onClose={() => setShowSelfTest(false)} />
    </SettingsPage>
  );
};

export default SystemState;
