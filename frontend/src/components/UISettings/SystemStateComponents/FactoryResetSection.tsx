import { useState, useCallback, useEffect } from 'react';
import {
  FaCheck,
  FaExclamationTriangle,
  FaSpinner,
  FaUndo,
  FaRedo,
  FaFileArchive,
} from 'react-icons/fa';
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
  const [deviceTypes, setDeviceTypes] = useState<string[]>([]);
  const [hardwareVersions, setHardwareVersions] = useState<string[]>([]);
  const [hardwareSensors, setHardwareSensors] = useState<Record<string, { temp_sensor: string; has_ina219: boolean; power_sensor?: string | null }>>({});
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

  useEffect(() => {
    fetchDeviceTypes();
    fetchHardwareVersions();
    fetchConfigBackups();
  }, [fetchDeviceTypes, fetchHardwareVersions, fetchConfigBackups]);

  const performFactoryReset = async () => {
    if (!selectedDeviceType) return;

    if (!confirm(t('device_management.confirm_factory_reset') || 'Are you sure you want to perform a factory reset? All settings will be replaced with defaults.')) {
      return;
    }

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
    <div className="space-y-6">
      {/* Factory Reset Action Card */}
      <div className="card bg-base-200/50 border border-error/30 shadow-sm">
        <div className="card-body p-4 sm:p-6 space-y-4">
          <h3 className="text-base font-semibold flex items-center gap-2 text-error">
            <FaRedo />
            {t('device_management.factory_reset')}
          </h3>

          <div className="alert alert-warning text-sm">
            <FaExclamationTriangle className="shrink-0" />
            <span>{t('device_management.factory_reset_warning')}</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl">
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">
                  {t('device_management.select_device_type')}
                </span>
              </label>
              <select
                className="select select-bordered select-sm w-full"
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
                className="select select-bordered select-sm w-full"
                value={selectedHardwareVersion}
                onChange={e => setSelectedHardwareVersion(e.target.value)}
              >
                {hardwareVersions.map(version => (
                  <option key={version} value={version}>
                    v{version}
                    {hardwareSensors[version] && (
                      ` (${hardwareSensors[version].temp_sensor}${
                        hardwareSensors[version].power_sensor
                          ? ` + ${hardwareSensors[version].power_sensor!.toUpperCase()}`
                          : hardwareSensors[version].has_ina219
                          ? ' + INA219'
                          : ''
                      })`
                    )}
                  </option>
                ))}
              </select>
              <HelpLabel>{t('device_management.hardware_version_help')}</HelpLabel>
            </div>
          </div>

          <div>
            <button
              className="btn btn-error btn-sm"
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
          </div>

          {factoryResetResult && (
            <div
              className={`alert ${factoryResetResult.status === 'success' ? 'alert-success' : 'alert-error'} text-sm mt-2`}
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
        </div>
      </div>

      {/* Config Backups Card */}
      <div className="card bg-base-200/50 border border-base-content/10 shadow-sm">
        <div className="card-body p-4 sm:p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold flex items-center gap-2">
              <FaFileArchive className="text-secondary" />
              {t('device_management.config_backups')}
            </h3>

            <button
              className="btn btn-outline btn-sm"
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
          </div>

          {showConfigBackups && (
            <div>
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
      </div>
    </div>
  );
}
