import { useState, useCallback } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
  FaUndo,
  FaRedo,
} from 'react-icons/fa';
import SettingsCard from '../components/SettingsCard';
import HelpLabel from '../components/HelpLabel';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

interface FactoryResetSectionProps {
  onRestartRequired: () => void;
}

/**
 * Section for performing factory reset and managing config backups.
 */
export default function FactoryResetSection({ onRestartRequired }: FactoryResetSectionProps) {
  const { t } = useTranslation();
  const [showFactoryReset, setShowFactoryReset] = useState(false);
  const [deviceTypes, setDeviceTypes] = useState<string[]>([]);
  const [hardwareVersions, setHardwareVersions] = useState<string[]>([]);
  const [hardwareSensors, setHardwareSensors] = useState<Record<string, { temp_sensor: string; has_ina219: boolean }>>({});
  const [selectedDeviceType, setSelectedDeviceType] = useState<string | null>(null);
  const [selectedHardwareVersion, setSelectedHardwareVersion] = useState<string>('0.8');
  const [isResettingFactory, setIsResettingFactory] = useState(false);
  const [factoryResetResult, setFactoryResetResult] = useState<any>(null);
  const [configBackups, setConfigBackups] = useState<any[]>([]);
  const [showConfigBackups, setShowConfigBackups] = useState(false);

  const fetchDeviceTypes = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/factory_reset/device_types');
      setDeviceTypes(data.device_types || []);
    } catch (err) {
      console.error('Error fetching device types:', err);
    }
  }, []);

  const fetchHardwareVersions = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/factory_reset/hardware_versions');
      setHardwareVersions(data.versions || []);
      setHardwareSensors(data.sensors || {});
    } catch (err) {
      console.error('Error fetching hardware versions:', err);
    }
  }, []);

  const fetchConfigBackups = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/factory_reset/config_backups');
      setConfigBackups(data.backups || []);
    } catch (err) {
      console.error('Error fetching config backups:', err);
    }
  }, []);

  const performFactoryReset = async () => {
    if (!selectedDeviceType) return;

    setIsResettingFactory(true);
    setFactoryResetResult(null);

    try {
      const { data } = await axios.post('/api/factory_reset', {
        device_type: selectedDeviceType,
        version: selectedHardwareVersion,
      });
      setFactoryResetResult(data);

      if (data.status === 'success') {
        fetchConfigBackups();
        if (data.restart_required) {
          onRestartRequired();
        }
      }
    } catch (err) {
      setFactoryResetResult({ status: 'error', message: 'Failed to perform factory reset' });
    } finally {
      setIsResettingFactory(false);
    }
  };

  const restoreConfigBackup = async (backupPath: string) => {
    try {
      const { data } = await axios.post('/api/factory_reset/restore_backup', { backup_path: backupPath });
      setFactoryResetResult(data);
    } catch (err) {
      setFactoryResetResult({ status: 'error', message: 'Failed to restore backup' });
    }
  };

  return (
    <SettingsCard
      icon={<FaRedo />}
      title={t('device_management.factory_reset')}
      toggleButtonText={t('device_management.show_factory_reset')}
      toggleButtonTextExpanded={t('common.close')}
      isExpanded={showFactoryReset}
      onToggle={() => {
        setShowFactoryReset(!showFactoryReset);
        if (!showFactoryReset) {
          fetchDeviceTypes();
          fetchHardwareVersions();
          fetchConfigBackups();
        }
      }}
      expandableContent={
        <div className="space-y-4">
          <div className="alert alert-warning">
            <FaExclamationTriangle />
            <span>{t('device_management.factory_reset_warning')}</span>
          </div>

          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">
                {t('device_management.select_device_type')}
              </span>
            </label>
            <select
              className="select select-bordered w-full max-w-xs"
              value={selectedDeviceType || ''}
              onChange={e => setSelectedDeviceType(e.target.value || null)}
            >
              <option value="">
                {t('device_management.select_device_type_placeholder')}
              </option>
              {deviceTypes.map(type => (
                <option key={type} value={type}>
                  {type === '24x16'
                    ? 'boneIO 24x16A'
                    : type === '32x10'
                      ? 'boneIO 32x10A'
                      : type === '48x4'
                        ? 'boneIO 48x4A (DISCONTINUED)'
                        : type === 'cover'
                          ? 'boneIO Cover'
                          : type === 'cover_mix'
                            ? 'boneIO Cover Mix'
                            : type}
                </option>
              ))}
            </select>
          </div>

          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">
                {t('device_management.select_hardware_version')}
              </span>
            </label>
            <select
              className="select select-bordered w-full max-w-xs"
              value={selectedHardwareVersion}
              onChange={e => setSelectedHardwareVersion(e.target.value)}
            >
              {hardwareVersions.map(version => (
                <option key={version} value={version}>
                  v{version}
                  {hardwareSensors[version] && (
                    ` (${hardwareSensors[version].temp_sensor}${hardwareSensors[version].has_ina219 ? ' + INA219' : ''})`
                  )}
                </option>
              ))}
            </select>
            <HelpLabel>{t('device_management.hardware_version_help')}</HelpLabel>
          </div>

          <button
            className="btn btn-outline btn-error"
            onClick={performFactoryReset}
            disabled={!selectedDeviceType || isResettingFactory}
          >
            {isResettingFactory ? (
              <>
                <FaSpinner className="animate-spin mr-2" />
                {t('device_management.resetting')}
              </>
            ) : (
              <>
                <FaRedo className="mr-2" />
                {t('device_management.reset_to_factory')}
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
                    {t('device_management.backup_created')}: {factoryResetResult.backup_path}
                  </p>
                )}
                {factoryResetResult.copied_files && (
                  <p className="text-xs opacity-70 mt-1 wrap-break-word">
                    {t('device_management.copied_files')}:{' '}
                    {factoryResetResult.copied_files.join(', ')}
                  </p>
                )}
                {factoryResetResult.restart_required && (
                  <p className="text-xs font-semibold mt-2">
                    {t('device_management.restart_required')}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Config Backups */}
          <div className="divider">{t('device_management.config_backups')}</div>

          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setShowConfigBackups(!showConfigBackups);
              if (!showConfigBackups) fetchConfigBackups();
            }}
          >
            {showConfigBackups
              ? t('device_management.hide_config_backups').replace(
                  '{count}',
                  String(configBackups.length)
                )
              : t('device_management.show_config_backups').replace(
                  '{count}',
                  String(configBackups.length)
                )}
          </button>

          {showConfigBackups && (
            <div className="mt-2">
              {configBackups.length === 0 ? (
                <p className="text-sm opacity-70">
                  {t('device_management.no_config_backups')}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="table table-sm">
                    <thead>
                      <tr>
                        <th>{t('device_management.date')}</th>
                        <th>{t('device_management.files')}</th>
                        <th>{t('device_management.actions')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {configBackups.map(backup => (
                        <tr key={backup.path}>
                          <td>{backup.timestamp.replace('_', ' ')}</td>
                          <td>
                            {backup.file_count} {t('device_management.yaml_files')}
                          </td>
                          <td>
                            <button
                              className="btn btn-warning btn-xs"
                              onClick={() => restoreConfigBackup(backup.path)}
                            >
                              <FaUndo />
                              {t('device_management.restore')}
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
      }
    />
  );
}
