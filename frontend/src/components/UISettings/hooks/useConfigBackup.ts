import { useState, useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';

interface Backup {
  filename: string;
  size: number;
  created_at: string;
}

export const useConfigBackup = () => {
  const { t } = useTranslation();
  const [backups, setBackups] = useState<Backup[]>([]);
  const [isCreatingBackup, setIsCreatingBackup] = useState(false);
  const [isRestoringBackup, setIsRestoringBackup] = useState(false);
  const [backupResult, setBackupResult] = useState<{ status: string; message: string } | null>(null);

  const fetchBackups = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/backups');
      setBackups(data.backups || []);
    } catch (err) {
      console.error('Failed to fetch backups:', err);
    }
  }, []);

  const createBackup = async () => {
    setIsCreatingBackup(true);
    setBackupResult(null);

    try {
      const response = await axios.post('/api/backup', null, { responseType: 'blob' });
      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `boneio-config-${new Date().toISOString().split('T')[0]}.tar.gz`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setBackupResult({ status: 'success', message: t('system_update.backup_created') });
      await fetchBackups();
    } catch (err) {
      setBackupResult({ status: 'error', message: t('system_update.backup_failed') });
    } finally {
      setIsCreatingBackup(false);
    }
  };

  const restoreBackup = async (file: File) => {
    setIsRestoringBackup(true);
    setBackupResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const { data } = await axios.post('/api/restore', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      if (data.status === 'success') {
        setBackupResult({ status: 'success', message: data.message || t('system_update.restore_success') });
      } else {
        setBackupResult({ status: 'error', message: data.message || t('system_update.restore_failed') });
      }
    } catch (err) {
      setBackupResult({ status: 'error', message: t('system_update.restore_failed') });
    } finally {
      setIsRestoringBackup(false);
    }
  };

  return {
    backups,
    isCreatingBackup,
    isRestoringBackup,
    backupResult,
    fetchBackups,
    createBackup,
    restoreBackup,
  };
};
