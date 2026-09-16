import { useState, useCallback, useEffect } from 'react';
import {
  FaSpinner,
  FaUndo,
  FaRedo,
  FaFileArchive,
} from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import {
  SettingsPage,
  SettingsCard,
  FormField,
  FormActions,
  NoticeCallout,
  EmptyState,
} from '../ui';

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
    <SettingsPage>
      {/* Factory reset */}
      <SettingsCard
        variant="danger"
        icon={<FaRedo />}
        title={t('device_management.factory_reset')}
        footer={
          <FormActions>
            <button
              className="btn btn-error btn-sm gap-2"
              onClick={performFactoryReset}
              disabled={!selectedDeviceType || isResettingFactory}
            >
              {isResettingFactory ? (
                <>
                  <FaSpinner className="animate-spin" />
                  {t('device_management.resetting')}
                </>
              ) : (
                <>
                  <FaRedo />
                  {t('device_management.reset_to_factory')}
                </>
              )}
            </button>
          </FormActions>
        }
      >
        <div className="space-y-4">
          <NoticeCallout
            variant="warning"
            message={t('device_management.factory_reset_warning')}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FormField label={t('device_management.select_device_type')}>
              <select
                className="select select-bordered w-full"
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
            </FormField>

            <FormField
              label={t('device_management.select_hardware_version')}
              help={t('device_management.hardware_version_help')}
            >
              <select
                className="select select-bordered w-full"
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
            </FormField>
          </div>

          {factoryResetResult && (
            <NoticeCallout
              variant={factoryResetResult.status === 'success' ? 'success' : 'error'}
              message={
                <>
                  <span className="block wrap-break-word">{factoryResetResult.message}</span>
                  {factoryResetResult.backup_path && (
                    <span className="block text-xs opacity-70 mt-1 break-all">
                      {t('device_management.backup_created')}: {factoryResetResult.backup_path}
                    </span>
                  )}
                  {factoryResetResult.copied_files && (
                    <span className="block text-xs opacity-70 mt-1 wrap-break-word">
                      {t('device_management.copied_files')}:{' '}
                      {factoryResetResult.copied_files.join(', ')}
                    </span>
                  )}
                  {factoryResetResult.restart_required && (
                    <span className="block text-xs font-semibold mt-2">
                      {t('device_management.restart_required')}
                    </span>
                  )}
                </>
              }
            />
          )}
        </div>
      </SettingsCard>

      {/* Config backups */}
      <SettingsCard
        icon={<FaFileArchive />}
        title={t('device_management.config_backups')}
        collapsible
        open={showConfigBackups}
        onOpenChange={(next) => {
          setShowConfigBackups(next);
          if (next) fetchConfigBackups();
        }}
        summary={configBackups.length}
      >
        {showConfigBackups ? (
          configBackups.length === 0 ? (
            <EmptyState
              icon={<FaFileArchive />}
              title={t('device_management.no_config_backups')}
            />
          ) : (
            <div className="stg-inset overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>{t('device_management.date')}</th>
                    <th>{t('device_management.files')}</th>
                    <th className="text-right">{t('device_management.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {configBackups.map(backup => (
                    <tr key={backup.path}>
                      <td className="font-mono text-xs">{backup.timestamp.replace('_', ' ')}</td>
                      <td>
                        {backup.file_count} {t('device_management.yaml_files')}
                      </td>
                      <td className="text-right">
                        <button
                          className="btn btn-warning btn-xs gap-1.5"
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
          )
        ) : null}
      </SettingsCard>
    </SettingsPage>
  );
}
