import { useState, useCallback } from 'react';
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
  versions?: VersionInfo[];
  error?: string;
}

export const useSystemUpdate = () => {
  const { t } = useTranslation();
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkForUpdates = useCallback(async () => {
    setIsChecking(true);
    setError(null);
    try {
      const { data } = await axios.get('/api/check_update');
      setUpdateInfo(data);

      if (data.error) {
        setError(data.error);
      }

      // Also publish update state to MQTT so HA sees the result
      await axios.post('/api/check_update_now').catch(() => {});
    } catch (err) {
      setError(t('system_update.check_failed'));
      console.error('Failed to check for updates:', err);
    } finally {
      setIsChecking(false);
    }
  }, [t]);

  const startUpdate = useCallback(async (version?: string) => {
    setIsUpdating(true);
    setUpdateStatus({
      status: 'running',
      progress: 0,
      step: t('system_update.starting'),
      log: [],
      error: null,
      backup_path: null,
      old_version: null,
      new_version: null,
    });

    try {
      const { data } = await axios.post('/api/update', { version });

      if (data.status === 'started') {
        pollUpdateStatus();
      } else {
        setUpdateStatus({
          status: 'error',
          progress: 0,
          step: t('system_update.failed'),
          log: [],
          error: data.message || t('system_update.update_failed'),
          backup_path: null,
          old_version: null,
          new_version: null,
        });
        setIsUpdating(false);
      }
    } catch (err) {
      setUpdateStatus({
        status: 'error',
        progress: 0,
        step: t('system_update.failed'),
        log: [],
        error: String(err),
        backup_path: null,
        old_version: null,
        new_version: null,
      });
      setIsUpdating(false);
    }
  }, [t]);

  const pollUpdateStatus = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const { data } = await axios.get('/api/update_status');
        setUpdateStatus(data);

        if (data.status === 'success' || data.status === 'error') {
          clearInterval(interval);
          setIsUpdating(false);
          if (data.status === 'success') {
            setTimeout(() => checkForUpdates(), 2000);
          }
        }
      } catch (err) {
        console.error('Failed to poll update status:', err);
        clearInterval(interval);
        setIsUpdating(false);
      }
    }, 1000);
  }, [checkForUpdates]);

  return {
    updateInfo,
    isChecking,
    isUpdating,
    updateStatus,
    error,
    checkForUpdates,
    startUpdate,
  };
};
