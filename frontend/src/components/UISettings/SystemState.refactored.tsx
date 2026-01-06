import React, { useState, useEffect, useCallback, useContext } from 'react';
import { FaClipboardCheck } from 'react-icons/fa';
import SelfTest from './SelfTest';
import HardwareErrors from './HardwareErrors';
import { WebSocketContext } from '../../App';
import { OutputEvent } from '../../hooks/useWebSocket';
import { useTranslation } from '@/hooks/useTranslation';

// Import custom hooks
import { useSystemUpdate } from './hooks/useSystemUpdate';
import { useDevicePower } from './hooks/useDevicePower';
import { useHostname } from './hooks/useHostname';
import { useConfigBackup } from './hooks/useConfigBackup';

// Import section components
import { UpdateSection } from './sections/UpdateSection';
import { PowerSection } from './sections/PowerSection';
import { BackupSection } from './sections/BackupSection';
import { TurnOffOutputsSection } from './sections/TurnOffOutputsSection';

const SystemState: React.FC = () => {
  const { t } = useTranslation();
  const websocket = useContext(WebSocketContext);

  // Hardware errors state
  const [hardwareErrors, setHardwareErrors] = useState<any[]>([]);

  // Outputs state for turn off functionality
  const [outputs, setOutputs] = useState<any[]>([]);
  const [isTurningOff, setIsTurningOff] = useState(false);
  const [turnOffProgress, setTurnOffProgress] = useState(0);
  const [turnOffResult, setTurnOffResult] = useState<{ status: string; message: string } | null>(null);

  // Restart required state
  const [restartRequired, setRestartRequired] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);

  // Use custom hooks
  const {
    updateInfo,
    isChecking,
    isUpdating,
    updateStatus,
    error,
    checkForUpdates,
    startUpdate,
  } = useSystemUpdate();

  const {
    isRebooting,
    rebootResult,
    isShuttingDown,
    shutdownResult,
    rebootDevice,
    shutdownDevice,
  } = useDevicePower();

  const {
    showHostnameSection,
    setShowHostnameSection,
    currentHostname,
    newHostname,
    setNewHostname,
    isChangingHostname,
    hostnameResult,
    fetchCurrentHostname,
    changeHostname,
  } = useHostname();

  const {
    backups,
    isCreatingBackup,
    isRestoringBackup,
    backupResult,
    fetchBackups,
    createBackup,
    restoreBackup,
  } = useConfigBackup();

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

  // Fetch outputs for turn off functionality
  const fetchOutputs = useCallback(async () => {
    try {
      const response = await fetch('/api/outputs');
      const data = await response.json();
      setOutputs(data.outputs || []);
    } catch (err) {
      console.error('Failed to fetch outputs:', err);
    }
  }, []);

  // Turn off all outputs
  const turnOffAllOutputs = async () => {
    if (!confirm(t('settings.confirm_turn_off'))) {
      return;
    }

    setIsTurningOff(true);
    setTurnOffProgress(0);
    setTurnOffResult(null);

    const activeOutputs = outputs.filter(
      (o) => o.state === 'ON' || o.state === 'on' || o.state === true
    );

    try {
      for (let i = 0; i < activeOutputs.length; i++) {
        const output = activeOutputs[i];
        await fetch(`/api/output/${output.id}/off`, { method: 'POST' });
        setTurnOffProgress(Math.round(((i + 1) / activeOutputs.length) * 100));
      }

      setTurnOffResult({ status: 'success', message: t('system_update.all_outputs_off') });
      await fetchOutputs();
    } catch (err) {
      setTurnOffResult({ status: 'error', message: t('system_update.turn_off_failed') });
    } finally {
      setIsTurningOff(false);
    }
  };

  // Restart application
  const restartApp = async () => {
    setIsRestarting(true);
    try {
      await fetch('/api/restart', { method: 'POST' });
      setTimeout(() => {
        window.location.reload();
      }, 3000);
    } catch (err) {
      console.error('Failed to restart:', err);
      setIsRestarting(false);
    }
  };

  // WebSocket listener for output state changes
  useEffect(() => {
    if (!websocket) return;

    const handleOutputEvent = (event: OutputEvent) => {
      setOutputs((prev) =>
        prev.map((o) => (o.id === event.entity_id ? { ...o, state: event.state } : o))
      );
    };

    websocket.addEventListener('output', handleOutputEvent);

    return () => {
      websocket.removeEventListener('output', handleOutputEvent);
    };
  }, [websocket]);

  // Initial data fetch
  useEffect(() => {
    checkForUpdates();
    fetchBackups();
    fetchHardwareErrors();
    fetchCurrentHostname();
    fetchOutputs();
  }, [checkForUpdates, fetchBackups, fetchHardwareErrors, fetchCurrentHostname, fetchOutputs]);

  return (
    <div className="container mx-auto p-4 space-y-6">
      {/* Hardware Errors - Separate Container */}
      <HardwareErrors errors={hardwareErrors} />

      {/* System Update Section */}
      <UpdateSection
        updateInfo={updateInfo}
        isChecking={isChecking}
        isUpdating={isUpdating}
        updateStatus={updateStatus}
        error={error}
        onCheckForUpdates={checkForUpdates}
        onStartUpdate={startUpdate}
      />

      {/* Restart Required Alert */}
      {restartRequired && (
        <div className="alert alert-warning">
          <span>{t('settings.app_restart_required')}</span>
          <button className="btn btn-sm" onClick={restartApp} disabled={isRestarting}>
            {isRestarting ? t('settings.restarting') : t('settings.restart_now')}
          </button>
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
          <SelfTest />
        </div>
      </div>

      {/* Turn Off All Outputs Section */}
      <TurnOffOutputsSection
        outputs={outputs}
        isTurningOff={isTurningOff}
        turnOffProgress={turnOffProgress}
        turnOffResult={turnOffResult}
        onTurnOffAll={turnOffAllOutputs}
      />

      {/* Power Management Sections (Reboot & Shutdown) */}
      <PowerSection
        isRebooting={isRebooting}
        rebootResult={rebootResult}
        isShuttingDown={isShuttingDown}
        shutdownResult={shutdownResult}
        onReboot={rebootDevice}
        onShutdown={shutdownDevice}
      />

      {/* Configuration Backup Section */}
      <BackupSection
        isCreatingBackup={isCreatingBackup}
        isRestoringBackup={isRestoringBackup}
        backupResult={backupResult}
        onCreateBackup={createBackup}
        onRestoreBackup={restoreBackup}
      />

      {/* Hostname Section - Can be added later if needed */}
      {/* MQTT Password Section - Can be added later if needed */}
      {/* SSL/TLS Section - Can be added later if needed */}
    </div>
  );
};

export default SystemState;
