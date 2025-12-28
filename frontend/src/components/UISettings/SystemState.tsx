import React, { useState, useEffect, useCallback, useContext, useRef } from 'react';
import {
  FaDownload,
  FaUndo,
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
  FaHistory,
  FaFileArchive,
  FaClipboardCheck,
  FaPowerOff,
  FaUpload,
  FaRedo,
} from 'react-icons/fa';
import SelfTest from './SelfTest';
import HardwareErrors from './HardwareErrors';
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

interface Backup {
  path: string;
  name: string;
  version: string;
  timestamp: string;
}

const SystemState: React.FC = () => {
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
  const [turnOffResult, setTurnOffResult] = useState<{ count: number; errors: string[] } | null>(
    null
  );
  const [turnOffProgress, setTurnOffProgress] = useState<{ current: number; total: number } | null>(
    null
  );
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreResult, setRestoreResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);

  // Factory reset state
  const [showFactoryReset, setShowFactoryReset] = useState(false);
  const [deviceTypes, setDeviceTypes] = useState<string[]>([]);
  const [selectedDeviceType, setSelectedDeviceType] = useState<string | null>(null);
  const [isResettingFactory, setIsResettingFactory] = useState(false);
  const [factoryResetResult, setFactoryResetResult] = useState<any>(null);
  const [configBackups, setConfigBackups] = useState<any[]>([]);
  const [showConfigBackups, setShowConfigBackups] = useState(false);

  // Restart state
  const [restartRequired, setRestartRequired] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);

  // MQTT Password state
  const [showMqttPasswords, setShowMqttPasswords] = useState(false);
  const [mqttAppUsername, setMqttAppUsername] = useState<string>('boneio'); // Username used by app
  const [mqttPasswords, setMqttPasswords] = useState<{
    [key: string]: { password: string; confirm: string };
  }>({
    boneio: { password: '', confirm: '' },
    homeassistant: { password: '', confirm: '' },
    mqtt: { password: '', confirm: '' },
  });
  const [changingPassword, setChangingPassword] = useState<string | null>(null);
  const [passwordResults, setPasswordResults] = useState<{
    [key: string]: { status: string; message: string };
  }>({});

  // Hardware errors state
  const [hardwareErrors, setHardwareErrors] = useState<any[]>([]);

  // Hostname state
  const [showHostnameSection, setShowHostnameSection] = useState(false);
  const [currentHostname, setCurrentHostname] = useState<string>('');
  const [newHostname, setNewHostname] = useState<string>('');
  const [isChangingHostname, setIsChangingHostname] = useState(false);
  const [hostnameResult, setHostnameResult] = useState<{ status: string; message: string } | null>(null);

  // SSL/TLS Certificates state
  const [showSslSettings, setShowSslSettings] = useState(false);
  const [sslConfig, setSslConfig] = useState<{
    mode: 'self_signed' | 'acme';
    domain: string;
    email: string;
  }>({ mode: 'self_signed', domain: '', email: '' });
  const [sslCertificate, setSslCertificate] = useState<{
    issuer?: string;
    valid_from?: string;
    valid_until?: string;
    is_self_signed: boolean;
  } | null>(null);
  const [isSavingSsl, setIsSavingSsl] = useState(false);
  const [sslResult, setSslResult] = useState<{ status: string; message: string } | null>(null);
  const [caddyRunning, setCaddyRunning] = useState<boolean | null>(null);

  // Fetch hardware errors
  const fetchHardwareErrors = useCallback(async () => {
    try {
      const response = await fetch('/api/hardware/errors');
      const data = await response.json();
      setHardwareErrors(data.errors || []);
    } catch (err) {
      console.error('Failed to fetch hardware errors:', err);
    }
  }, []);

  // Fetch current hostname
  const fetchHostname = useCallback(async () => {
    try {
      const response = await fetch('/api/hostname');
      const data = await response.json();
      setCurrentHostname(data.hostname || '');
      setNewHostname(data.hostname || '');
    } catch (err) {
      console.error('Failed to fetch hostname:', err);
    }
  }, []);

  // Fetch SSL/TLS configuration
  const fetchSslConfig = useCallback(async () => {
    try {
      const response = await fetch('/api/caddy/config');
      const data = await response.json();
      if (data.status === 'success') {
        setSslConfig({
          mode: data.config?.mode || 'self_signed',
          domain: data.config?.domain || '',
          email: data.config?.email || '',
        });
        if (data.certificate) {
          setSslCertificate(data.certificate);
        }
      }
    } catch (err) {
      console.error('Failed to fetch SSL config:', err);
    }
  }, []);

  // Test Caddy connection
  const testCaddyConnection = useCallback(async () => {
    try {
      const response = await fetch('/api/caddy/test');
      const data = await response.json();
      setCaddyRunning(data.running === true);
    } catch (err) {
      console.error('Failed to test Caddy connection:', err);
      setCaddyRunning(false);
    }
  }, []);

  // Save SSL configuration
  const saveSslConfig = async () => {
    if (sslConfig.mode === 'acme' && !sslConfig.domain.trim()) {
      setSslResult({ status: 'error', message: t('ssl_certificates.domain_required') });
      return;
    }

    setIsSavingSsl(true);
    setSslResult(null);

    try {
      const response = await fetch('/api/caddy/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sslConfig),
      });

      const data = await response.json();

      if (response.ok) {
        setSslResult({ 
          status: data.status === 'warning' ? 'warning' : 'success', 
          message: data.message || t('ssl_certificates.config_saved') 
        });
        // Refresh config
        await fetchSslConfig();
      } else {
        setSslResult({ status: 'error', message: data.detail || t('ssl_certificates.config_save_failed') });
      }
    } catch (err: any) {
      setSslResult({ status: 'error', message: err.message || t('ssl_certificates.config_save_failed') });
    } finally {
      setIsSavingSsl(false);
    }
  };

  // Change hostname
  const changeHostname = async () => {
    if (!newHostname.trim()) {
      setHostnameResult({ status: 'error', message: t('settings.hostname_empty') });
      return;
    }

    if (newHostname === currentHostname) {
      setHostnameResult({ status: 'error', message: t('settings.hostname_unchanged') });
      return;
    }

    setIsChangingHostname(true);
    setHostnameResult(null);

    try {
      const response = await fetch('/api/hostname', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hostname: newHostname }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('settings.hostname_change_failed'));
      }

      const data = await response.json();
      setCurrentHostname(data.hostname);
      setHostnameResult({ status: 'success', message: t('settings.hostname_changed') });
    } catch (err: any) {
      setHostnameResult({ status: 'error', message: err.message || t('settings.hostname_change_failed') });
    } finally {
      setIsChangingHostname(false);
    }
  };

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

  // Fetch device types for factory reset
  const fetchDeviceTypes = useCallback(async () => {
    try {
      const response = await fetch('/api/factory_reset/device_types');
      const data = await response.json();
      setDeviceTypes(data.device_types || []);
    } catch (err) {
      console.error('Error fetching device types:', err);
    }
  }, []);

  // Fetch config backups
  const fetchConfigBackups = useCallback(async () => {
    try {
      const response = await fetch('/api/factory_reset/config_backups');
      const data = await response.json();
      setConfigBackups(data.backups || []);
    } catch (err) {
      console.error('Error fetching config backups:', err);
    }
  }, []);

  // Handle application restart
  const handleRestart = async () => {
    if (!confirm(t('system_update.restart_required'))) {
      return;
    }

    setIsRestarting(true);
    try {
      await fetch('/api/restart', { method: 'POST' });
      // The server will restart, so we won't get a response
    } catch (error) {
      // Expected - server is restarting
      console.log('Server is restarting...');
    }
  };

  // Perform factory reset
  const performFactoryReset = async () => {
    if (!selectedDeviceType) return;

    setIsResettingFactory(true);
    setFactoryResetResult(null);

    try {
      const response = await fetch('/api/factory_reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_type: selectedDeviceType }),
      });
      const data = await response.json();
      setFactoryResetResult(data);

      if (data.status === 'success') {
        fetchConfigBackups();
        // Check if restart is required
        if (data.restart_required) {
          setRestartRequired(true);
        }
      }
    } catch (err) {
      setFactoryResetResult({ status: 'error', message: 'Failed to perform factory reset' });
    } finally {
      setIsResettingFactory(false);
    }
  };

  // Restore config backup
  const restoreConfigBackup = async (backupPath: string) => {
    try {
      const response = await fetch('/api/factory_reset/restore_backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_path: backupPath }),
      });
      const data = await response.json();
      setFactoryResetResult(data);
    } catch (err) {
      setFactoryResetResult({ status: 'error', message: 'Failed to restore backup' });
    }
  };

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
        body: JSON.stringify({ version: version || selectedVersion }),
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
        const response = await fetch(`/api/outputs/${output.entity_id}/turn_off`, {
          method: 'POST',
        });
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
    fetchHardwareErrors();
    fetchDeviceTypes();
    fetchConfigBackups();
    fetchHostname();
  }, [checkForUpdates, fetchBackups, fetchHardwareErrors, fetchDeviceTypes, fetchConfigBackups, fetchHostname]);

  // Load SSL config when section is opened
  useEffect(() => {
    if (showSslSettings) {
      fetchSslConfig();
      testCaddyConnection();
    }
  }, [showSslSettings, fetchSslConfig, testCaddyConnection]);

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

  // Fetch MQTT username from config
  const fetchMqttUsername = async () => {
    try {
      const response = await fetch('/api/mqtt/username');
      const data = await response.json();
      if (data.status === 'success' && data.username) {
        setMqttAppUsername(data.username);
      }
    } catch (err) {
      console.error('Failed to fetch MQTT username:', err);
      // Keep default 'boneio'
    }
  };

  // Change MQTT password
  const changeMqttPassword = async (username: string) => {
    const passwords = mqttPasswords[username];

    // Validate
    if (passwords.password !== passwords.confirm) {
      setPasswordResults({
        ...passwordResults,
        [username]: { status: 'error', message: t('mqtt_passwords.password_mismatch') },
      });
      return;
    }

    if (passwords.password.length < 8) {
      setPasswordResults({
        ...passwordResults,
        [username]: { status: 'error', message: t('mqtt_passwords.password_too_short') },
      });
      return;
    }

    setChangingPassword(username);
    setPasswordResults({ ...passwordResults, [username]: { status: '', message: '' } });

    try {
      const response = await fetch('/api/mqtt/change_password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username,
          new_password: passwords.password,
        }),
      });

      const data = await response.json();

      if (data.status === 'success') {
        setPasswordResults({
          ...passwordResults,
          [username]: { status: 'success', message: t('mqtt_passwords.password_changed') },
        });
        // Clear password fields
        setMqttPasswords({
          ...mqttPasswords,
          [username]: { password: '', confirm: '' },
        });
      } else {
        setPasswordResults({
          ...passwordResults,
          [username]: { status: 'error', message: data.message },
        });
      }
    } catch (err) {
      setPasswordResults({
        ...passwordResults,
        [username]: { status: 'error', message: String(err) },
      });
    } finally {
      setChangingPassword(null);
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-6">
      {/* Hardware Errors - Separate Container */}
      <HardwareErrors errors={hardwareErrors} />

      {/* System Update Card */}
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
                {isChecking ? (
                  <FaSpinner className="animate-spin" />
                ) : (
                  t('system_update.check_for_updates')
                )}
              </button>
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

            {/* Current Version Card */}
            <div className="card bg-base-200">
              <div className="card-body">
                <h3 className="card-title">{t('system_update.current_version')}</h3>
                <div className="flex items-center gap-4">
                  <span className="text-3xl font-mono font-bold text-primary">
                    {updateInfo?.current_version || '...'}
                  </span>
                  {updateInfo?.update_available && (
                    <span className="badge badge-success badge-lg">
                      {t('system_update.update_available')}
                    </span>
                  )}
                  {updateInfo?.status === 'success' && !updateInfo?.update_available && (
                    <span className="badge badge-info">{t('system_update.up_to_date')}</span>
                  )}
                </div>
              </div>
            </div>

            {/* Prerelease Available Card (for stable users) */}
            {updateInfo?.prerelease_update_available && !updateInfo?.update_available && (
              <div className="card bg-warning/10 border border-warning">
                <div className="card-body">
                  <h3 className="card-title text-warning">
                    <FaExclamationTriangle /> {t('system_update.prerelease_available')}
                  </h3>
                  <p className="text-sm opacity-70">
                    {t('system_update.prerelease_available_description')}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div>
                      <p className="text-sm opacity-70">{t('system_update.prerelease_version')}</p>
                      <p className="text-2xl font-mono font-bold">
                        {updateInfo.latest_prerelease}
                        <span className="badge badge-warning ml-2">dev</span>
                      </p>
                    </div>
                    <div>
                      <p className="text-sm opacity-70">{t('system_update.your_stable_version')}</p>
                      <p className="text-lg font-mono">
                        {updateInfo.current_version}
                        <span className="badge badge-success ml-2">stable</span>
                      </p>
                    </div>
                  </div>
                  <div className="alert alert-warning mt-4">
                    <FaExclamationTriangle />
                    <span className="text-sm">{t('system_update.prerelease_warning')}</span>
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
                      {t('system_update.view_release_notes')}
                    </a>
                    <button
                      className="btn btn-warning"
                      onClick={() => startUpdate(updateInfo.latest_prerelease)}
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
                          {t('system_update.install_prerelease')}
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
                            ⭐ {t('system_update.recommended')}: {updateInfo.latest_stable}
                          </span>
                        )}
                      </span>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div>
                      <p className="text-sm opacity-70">{t('system_update.selected_version')}</p>
                      <p className="text-2xl font-mono font-bold">
                        {selectedVersion || updateInfo.latest_version}
                        {(selectedVersion || updateInfo.latest_version)
                          ?.toLowerCase()
                          .includes('dev') && <span className="badge badge-warning ml-2">dev</span>}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm opacity-70">{t('system_update.released')}</p>
                      <p className="text-lg">
                        {updateInfo.available_versions?.find(
                          v => v.version === (selectedVersion || updateInfo.latest_version)
                        )?.published_at
                          ? formatDate(
                              updateInfo.available_versions.find(
                                v => v.version === (selectedVersion || updateInfo.latest_version)
                              )!.published_at
                            )
                          : t('system_update.unknown')}
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
                          {t('system_update.update_to')}{' '}
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
                        {t('system_update.turn_off_all_outputs')} (
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
                      <span className="text-sm">{t('system_update.turning_off_outputs')}</span>
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
                      <p>{t('system_update.turned_off_outputs').replace('{count}', String(turnOffResult.count))}</p>
                      {turnOffResult.errors.length > 0 && (
                        <p>{t('system_update.errors')}: {turnOffResult.errors.join(', ')}</p>
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
                <p className="text-sm opacity-70 mb-4">{t('system_update.backup_description')}</p>

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
                    className="btn btn-outline btn-sm"
                    onClick={() => setShowBackups(!showBackups)}
                  >
                    {showBackups
                      ? t('system_update.hide_backups').replace('{count}', String(backups.length))
                      : t('system_update.show_backups').replace('{count}', String(backups.length))}
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
                    <p>{t('system_update.backup_info_3')}</p>
                    <p>{t('system_update.backup_info_4')}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Hostname Change Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <div className="flex items-center justify-between">
                  <h3 className="card-title">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-6 w-6"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    {t('settings.hostname_title')}
                  </h3>
                  <button
                    className="btn btn-outline btn-sm"
                    onClick={() => setShowHostnameSection(!showHostnameSection)}
                  >
                    {showHostnameSection ? t('common.close') : t('settings.show_hostname_section')}
                  </button>
                </div>
                <p className="text-sm opacity-70 mt-2">{t('settings.hostname_description')}</p>

                {showHostnameSection && (
                  <div className="space-y-4 mt-4">
                    <div>
                      <label className="label">
                        <span className="label-text">{t('settings.current_hostname')}</span>
                      </label>
                      <input
                        type="text"
                        className="input input-bordered w-full"
                        value={currentHostname}
                        disabled
                      />
                    </div>

                    <div>
                      <label className="label">
                        <span className="label-text">{t('settings.new_hostname')}</span>
                      </label>
                      <input
                        type="text"
                        className="input input-bordered w-full"
                        value={newHostname}
                        onChange={e => setNewHostname(e.target.value)}
                        placeholder={t('settings.hostname_placeholder')}
                        disabled={isChangingHostname}
                      />
                      <label className="label">
                        <span className="label-text-alt">{t('settings.hostname_hint')}</span>
                      </label>
                    </div>

                    {hostnameResult && (
                      <div className={`alert ${hostnameResult.status === 'success' ? 'alert-success' : 'alert-error'}`}>
                        {hostnameResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
                        <span>{hostnameResult.message}</span>
                      </div>
                    )}

                    <button
                      className="btn btn-primary"
                      onClick={changeHostname}
                      disabled={isChangingHostname || !newHostname.trim() || newHostname === currentHostname}
                    >
                      {isChangingHostname ? (
                        <>
                          <FaSpinner className="animate-spin" />
                          {t('settings.changing_hostname')}
                        </>
                      ) : (
                        <>
                          <FaCheck />
                          {t('settings.change_hostname')}
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* MQTT Passwords Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <div className="flex items-center justify-between">
                  <h3 className="card-title">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-6 w-6"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                      />
                    </svg>
                    {t('mqtt_passwords.title')}
                  </h3>
                  <button
                    className="btn btn-outline btn-sm"
                    onClick={() => {
                      if (!showMqttPasswords) {
                        fetchMqttUsername();
                      }
                      setShowMqttPasswords(!showMqttPasswords);
                    }}
                  >
                    {showMqttPasswords ? t('common.close') : t('mqtt_passwords.show_section')}
                  </button>
                </div>
                <p className="text-sm opacity-70 mt-2">{t('mqtt_passwords.description')}</p>

                {showMqttPasswords && (
                  <>
                    {/* Security warning */}
                    <div
                      className={`alert ${window.location.protocol === 'https:' ? 'alert-success' : 'alert-warning'} mt-4`}
                    >
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
                      <span className="text-sm">
                        {window.location.protocol === 'https:'
                          ? t('mqtt_passwords.https_secure')
                          : t('mqtt_passwords.http_warning')}
                      </span>
                    </div>

                    <div className="space-y-6 mt-6">
                      {['boneio', 'homeassistant', 'mqtt'].map(username => (
                        <div key={username} className="card bg-base-100 shadow-sm">
                          <div className="card-body p-4">
                            <h4 className="font-semibold text-lg mb-3">
                              {t('mqtt_passwords.username')}: {username}
                            </h4>

                            {/* Warning for app's MQTT user */}
                            {username === mqttAppUsername && (
                              <div className="alert alert-warning mb-4">
                                <FaExclamationTriangle />
                                <span className="text-sm">{t('mqtt_passwords.boneio_user_warning')}</span>
                              </div>
                            )}

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <fieldset className="fieldset">
                                <legend className="fieldset-legend">
                                  {t('mqtt_passwords.new_password')}
                                </legend>
                                <input
                                  type="password"
                                  className="input input-bordered"
                                  value={mqttPasswords[username].password}
                                  onChange={e =>
                                    setMqttPasswords({
                                      ...mqttPasswords,
                                      [username]: {
                                        ...mqttPasswords[username],
                                        password: e.target.value,
                                      },
                                    })
                                  }
                                  disabled={changingPassword === username}
                                />
                              </fieldset>
                              <fieldset className="fieldset">
                                <legend className="fieldset-legend">
                                  {t('mqtt_passwords.confirm_password')}
                                </legend>
                                <input
                                  type="password"
                                  className="input input-bordered"
                                  value={mqttPasswords[username].confirm}
                                  onChange={e =>
                                    setMqttPasswords({
                                      ...mqttPasswords,
                                      [username]: {
                                        ...mqttPasswords[username],
                                        confirm: e.target.value,
                                      },
                                    })
                                  }
                                  disabled={changingPassword === username}
                                />
                              </fieldset>
                            </div>

                            <button
                              className="btn btn-primary btn-sm mt-4"
                              onClick={() => changeMqttPassword(username)}
                              disabled={
                                changingPassword === username ||
                                !mqttPasswords[username].password ||
                                !mqttPasswords[username].confirm
                              }
                            >
                              {changingPassword === username ? (
                                <>
                                  <FaSpinner className="animate-spin mr-2" />
                                  {t('mqtt_passwords.changing')}
                                </>
                              ) : (
                                t('mqtt_passwords.change_password')
                              )}
                            </button>

                            {passwordResults[username]?.message && (
                              <div
                                className={`alert ${passwordResults[username].status === 'success' ? 'alert-success' : 'alert-error'} mt-3`}
                              >
                                {passwordResults[username].status === 'success' ? (
                                  <FaCheck />
                                ) : (
                                  <FaExclamationTriangle />
                                )}
                                <span className="text-sm">{passwordResults[username].message}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* SSL/TLS Certificates Section */}
            <div className="card bg-base-200 hidden">
              <div className="card-body">
                <div className="flex items-center justify-between">
                  <h3 className="card-title">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-6 w-6"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                      />
                    </svg>
                    {t('ssl_certificates.title')}
                  </h3>
                  <div className="flex items-center gap-2">
                    {caddyRunning !== null && (
                      <span className={`badge ${caddyRunning ? 'badge-success' : 'badge-error'}`}>
                        {caddyRunning ? t('ssl_certificates.caddy_running') : t('ssl_certificates.caddy_not_running')}
                      </span>
                    )}
                    <button
                      className="btn btn-outline btn-sm"
                      onClick={() => setShowSslSettings(!showSslSettings)}
                    >
                      {showSslSettings ? t('common.close') : t('ssl_certificates.show_section')}
                    </button>
                  </div>
                </div>
                <p className="text-sm opacity-70 mt-2">{t('ssl_certificates.description')}</p>

                {showSslSettings && (
                  <div className="mt-4 space-y-4">
                    {/* Current Certificate Info */}
                    {sslCertificate && (
                      <div className={`alert ${sslCertificate.is_self_signed ? 'alert-warning' : 'alert-success'}`}>
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
                            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                          />
                        </svg>
                        <div className="text-sm">
                          <p className="font-semibold">{t('ssl_certificates.certificate_status')}</p>
                          <p>{sslCertificate.is_self_signed ? t('ssl_certificates.self_signed_info') : t('ssl_certificates.acme_info')}</p>
                          {sslCertificate.issuer && <p>{t('ssl_certificates.issuer')}: {sslCertificate.issuer}</p>}
                          {sslCertificate.valid_until && <p>{t('ssl_certificates.valid_until')}: {sslCertificate.valid_until}</p>}
                        </div>
                      </div>
                    )}

                    {/* Mode Selection */}
                    <div className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">{t('ssl_certificates.mode')}</span>
                      </label>
                      <div className="flex gap-4">
                        <label className="label cursor-pointer gap-2">
                          <input
                            type="radio"
                            name="ssl-mode"
                            className="radio radio-primary"
                            checked={sslConfig.mode === 'self_signed'}
                            onChange={() => setSslConfig({ ...sslConfig, mode: 'self_signed' })}
                          />
                          <span className="label-text">{t('ssl_certificates.mode_self_signed')}</span>
                        </label>
                        <label className="label cursor-pointer gap-2">
                          <input
                            type="radio"
                            name="ssl-mode"
                            className="radio radio-primary"
                            checked={sslConfig.mode === 'acme'}
                            onChange={() => setSslConfig({ ...sslConfig, mode: 'acme' })}
                          />
                          <span className="label-text">{t('ssl_certificates.mode_acme')}</span>
                        </label>
                      </div>
                    </div>

                    {/* ACME Settings */}
                    {sslConfig.mode === 'acme' && (
                      <>
                        <div className="alert alert-warning">
                          <FaExclamationTriangle />
                          <span className="text-sm">{t('ssl_certificates.acme_warning')}</span>
                        </div>

                        <div className="form-control">
                          <label className="label">
                            <span className="label-text">{t('ssl_certificates.domain')}</span>
                          </label>
                          <input
                            type="text"
                            className="input input-bordered w-full max-w-md"
                            value={sslConfig.domain}
                            onChange={e => setSslConfig({ ...sslConfig, domain: e.target.value })}
                            placeholder={t('ssl_certificates.domain_placeholder')}
                            disabled={isSavingSsl}
                          />
                          <label className="label">
                            <span className="label-text-alt">{t('ssl_certificates.domain_hint')}</span>
                          </label>
                        </div>

                        <div className="form-control">
                          <label className="label">
                            <span className="label-text">{t('ssl_certificates.email')}</span>
                          </label>
                          <input
                            type="email"
                            className="input input-bordered w-full max-w-md"
                            value={sslConfig.email}
                            onChange={e => setSslConfig({ ...sslConfig, email: e.target.value })}
                            placeholder={t('ssl_certificates.email_placeholder')}
                            disabled={isSavingSsl}
                          />
                          <label className="label">
                            <span className="label-text-alt">{t('ssl_certificates.email_hint')}</span>
                          </label>
                        </div>
                      </>
                    )}

                    {/* Result Alert */}
                    {sslResult && (
                      <div className={`alert ${sslResult.status === 'success' ? 'alert-success' : sslResult.status === 'warning' ? 'alert-warning' : 'alert-error'}`}>
                        {sslResult.status === 'success' ? <FaCheck /> : <FaExclamationTriangle />}
                        <span>{sslResult.message}</span>
                      </div>
                    )}

                    {/* Save Button */}
                    <button
                      className="btn btn-primary"
                      onClick={saveSslConfig}
                      disabled={isSavingSsl || (sslConfig.mode === 'acme' && !sslConfig.domain.trim())}
                    >
                      {isSavingSsl ? (
                        <>
                          <FaSpinner className="animate-spin" />
                          {t('ssl_certificates.saving')}
                        </>
                      ) : (
                        <>
                          <FaCheck />
                          {t('ssl_certificates.save_config')}
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Factory Reset Section */}
            <div className="card bg-base-200">
              <div className="card-body">
                <div className="flex items-center justify-between">
                  <h3 className="card-title">
                    <FaRedo />
                    {t('system_update.factory_reset')}
                  </h3>
                  <button
                    className="btn btn-outline btn-sm"
                    onClick={() => {
                      setShowFactoryReset(!showFactoryReset);
                      if (!showFactoryReset) {
                        fetchDeviceTypes();
                        fetchConfigBackups();
                      }
                    }}
                  >
                    {showFactoryReset ? t('common.close') : t('system_update.show_factory_reset')}
                  </button>
                </div>

                {showFactoryReset && (
                  <div className="mt-4 space-y-4">
                    <div className="alert alert-warning">
                      <FaExclamationTriangle />
                      <span>{t('system_update.factory_reset_warning')}</span>
                    </div>

                    <div className="form-control">
                      <label className="label">
                        <span className="label-text font-medium">
                          {t('system_update.select_device_type')}
                        </span>
                      </label>
                      <select
                        className="select select-bordered w-full max-w-xs"
                        value={selectedDeviceType || ''}
                        onChange={e => setSelectedDeviceType(e.target.value || null)}
                      >
                        <option value="">
                          {t('system_update.select_device_type_placeholder')}
                        </option>
                        {deviceTypes.map(type => (
                          <option key={type} value={type}>
                            {type === '24x16'
                              ? 'boneIO 24x16A'
                              : type === '32x10'
                                ? 'boneIO 32x10A'
                                : type === 'cover'
                                  ? 'boneIO Cover'
                                  : type === 'cover_mix'
                                    ? 'boneIO Cover Mix'
                                    : type}
                          </option>
                        ))}
                      </select>
                    </div>

                    <button
                      className="btn btn-outline btn-error"
                      onClick={performFactoryReset}
                      disabled={!selectedDeviceType || isResettingFactory}
                    >
                      {isResettingFactory ? (
                        <>
                          <FaSpinner className="animate-spin mr-2" />
                          {t('system_update.resetting')}
                        </>
                      ) : (
                        <>
                          <FaRedo className="mr-2" />
                          {t('system_update.reset_to_factory')}
                        </>
                      )}
                    </button>

                    {factoryResetResult && (
                      <div
                        className={`alert ${factoryResetResult.status === 'success' ? 'alert-success' : 'alert-error'} mt-4`}
                      >
                        {factoryResetResult.status === 'success' ? (
                          <FaCheck className="shrink-0" />
                        ) : (
                          <FaExclamationTriangle className="shrink-0" />
                        )}
                        <div className="text-sm min-w-0 flex-1">
                          <p className="wrap-break-word">{factoryResetResult.message}</p>
                          {factoryResetResult.backup_path && (
                            <p className="text-xs opacity-70 mt-1 break-all">
                              {t('system_update.backup_created')}: {factoryResetResult.backup_path}
                            </p>
                          )}
                          {factoryResetResult.copied_files && (
                            <p className="text-xs opacity-70 mt-1 wrap-break-word">
                              {t('system_update.copied_files')}:{' '}
                              {factoryResetResult.copied_files.join(', ')}
                            </p>
                          )}
                          {factoryResetResult.restart_required && (
                            <p className="text-xs font-semibold mt-2">
                              {t('system_update.restart_required')}
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Config Backups */}
                    <div className="divider">{t('system_update.config_backups')}</div>

                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        setShowConfigBackups(!showConfigBackups);
                        if (!showConfigBackups) fetchConfigBackups();
                      }}
                    >
                      {showConfigBackups
                        ? t('system_update.hide_config_backups').replace(
                            '{count}',
                            String(configBackups.length)
                          )
                        : t('system_update.show_config_backups').replace(
                            '{count}',
                            String(configBackups.length)
                          )}
                    </button>

                    {showConfigBackups && (
                      <div className="mt-2">
                        {configBackups.length === 0 ? (
                          <p className="text-sm opacity-70">
                            {t('system_update.no_config_backups')}
                          </p>
                        ) : (
                          <div className="overflow-x-auto">
                            <table className="table table-sm">
                              <thead>
                                <tr>
                                  <th>{t('system_update.date')}</th>
                                  <th>{t('system_update.files')}</th>
                                  <th>{t('system_update.actions')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {configBackups.map(backup => (
                                  <tr key={backup.path}>
                                    <td>{backup.timestamp.replace('_', ' ')}</td>
                                    <td>
                                      {backup.file_count} {t('system_update.yaml_files')}
                                    </td>
                                    <td>
                                      <button
                                        className="btn btn-warning btn-xs"
                                        onClick={() => restoreConfigBackup(backup.path)}
                                      >
                                        <FaUndo />
                                        {t('system_update.restore')}
                                      </button>
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
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
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
